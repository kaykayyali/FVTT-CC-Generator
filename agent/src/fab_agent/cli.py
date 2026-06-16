"""``fab-agent`` command-line interface.

This module is intentionally small — it parses a handful of flags,
overrides :class:`FabConfig` with their values, and either runs the
self-check (a connectivity smoke test) or starts the WebSocket server.

Usage examples::

    fab-agent                       # use values from .env
    fab-agent --port 8888           # override port
    fab-agent --token s3cret        # override token
    fab-agent --model anthropic/claude-sonnet-4-20250514
    fab-agent --check               # smoke-test and exit
    fab-agent --help
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import List, Optional, Sequence

from .config import AGENT_NAME, AGENT_VERSION, FabConfig, configure_logging, load_config
from .llm import LLM, is_litellm_available
from .protocol import HelloResponse
from .server import run as run_server
from .skills_loader import load_all_skills, summarise as summarise_skills

log = logging.getLogger(__name__)


# -----------------------------------------------------------------------------#
# argparse setup                                                                 #
# -----------------------------------------------------------------------------#


def build_parser() -> argparse.ArgumentParser:
    """Construct the :class:`argparse.ArgumentParser` for the CLI.

    Kept as a free function so tests and the ``--check`` subcommand can
    re-use the same flag definitions.
    """
    parser = argparse.ArgumentParser(
        prog=AGENT_NAME,
        description=(
            "Local WebSocket agent for the FVTT-CC-Generator Foundry VTT "
            "module. Streams AI-generated Campaign Codex sheets to the "
            "module preview/commit flow."
        ),
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Interface to bind the WebSocket server to (default: FAB_AGENT_HOST or 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="TCP port to bind (default: FAB_AGENT_PORT or 7777).",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Shared secret for the fab.v1.token Sec-WebSocket-Protocol "
        "(default: FAB_AGENT_TOKEN).",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model name, e.g. 'gpt-4o' or "
        "'anthropic/claude-sonnet-4-20250514' (default: FAB_LLM_MODEL).",
    )
    parser.add_argument(
        "--provider",
        default=None,
        help="LLM provider, e.g. openai|anthropic|openrouter|ollama "
        "(default: FAB_LLM_PROVIDER).",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Override the LLM base URL (FAB_LLM_BASE_URL).",
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Log verbosity (default: FAB_LOG_LEVEL or INFO).",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate config, skills, and LLM connectivity, print a report, and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{AGENT_NAME} {AGENT_VERSION}",
    )
    return parser


def apply_overrides(cfg: FabConfig, args: argparse.Namespace) -> FabConfig:
    """Return a new :class:`FabConfig` with CLI overrides applied.

    Pydantic Settings does not let us mutate ``cfg`` in place and
    re-run validators, so we build a shallow copy with the override
    dict and re-construct.
    """
    overrides: dict = {}
    if args.host is not None:
        overrides["agent_host"] = args.host
    if args.port is not None:
        overrides["agent_port"] = args.port
    if args.token is not None:
        overrides["agent_token"] = args.token
    if args.model is not None:
        overrides["llm_model"] = args.model
    if args.provider is not None:
        overrides["llm_provider"] = args.provider
    if args.base_url is not None:
        overrides["llm_base_url"] = args.base_url
    if args.log_level is not None:
        overrides["log_level"] = args.log_level
    if not overrides:
        return cfg
    return cfg.model_copy(update=overrides)


# -----------------------------------------------------------------------------#
# main                                                                          #
# -----------------------------------------------------------------------------#


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Parse arguments, then dispatch to ``--check`` or :func:`run_server`.

    Returns:
        Process exit code. ``0`` on success, ``1`` on configuration
        errors, ``2`` on ``--check`` connectivity failures.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Pre-configure logging from the env so --check output looks tidy.
    cfg0 = load_config()
    effective_level = (
        args.log_level or cfg0.log_level or "INFO"
    )
    configure_logging(effective_level)

    try:
        cfg = apply_overrides(load_config(), args)
    except Exception as exc:
        print(f"{AGENT_NAME}: invalid configuration: {exc}", file=sys.stderr)
        return 1

    if args.check:
        return _run_check(cfg)

    try:
        run_server(cfg)
        return 0
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        log.exception("server failed to start: %s", exc)
        print(f"{AGENT_NAME}: server error: {exc}", file=sys.stderr)
        return 1


# -----------------------------------------------------------------------------#
# --check                                                                       #
# -----------------------------------------------------------------------------#


def _run_check(cfg: FabConfig) -> int:
    """Self-check: validate config, skills, and LLM connectivity.

    Exits ``0`` if everything is fine, ``2`` if the LLM call failed
    (config + skills passed). We treat litellm-missing as ``2`` too.
    """
    print("┌─ fab-agent self-check")
    print(f"│  agent:        {AGENT_NAME} {AGENT_VERSION}")
    print(f"│  python:       {sys.version.split()[0]}")
    print(f"│  host:         {cfg.agent_host}")
    print(f"│  port:         {cfg.agent_port}")
    print(f"│  token set:    {'yes' if cfg.agent_token and not cfg.agent_token.startswith('change') else 'NO (placeholder!)'}")
    print(f"│  llm provider: {cfg.llm_provider}")
    print(f"│  llm model:    {cfg.llm_model}")
    print(f"│  litellm:      {'available' if is_litellm_available() else 'NOT INSTALLED'}")
    print(f"│  api key:      {'set' if cfg.api_key_value() else 'not set'}")
    if cfg.llm_base_url:
        print(f"│  base url:     {cfg.llm_base_url}")
    print("│")

    # --- skills ---
    try:
        skills_text = load_all_skills(Path(__file__).resolve().parent / "skills")
        print(f"│  skills:       loaded {summarise_skills(skills_text)}")
    except Exception as exc:
        print(f"│  skills:       FAILED — {exc}")
        print("└─")
        return 1
    print("│")

    # --- LLM connectivity ---
    if not is_litellm_available():
        print("│  llm ping:     skipped (litellm not installed)")
        print("└─")
        return 2

    llm = LLM(
        provider=cfg.llm_provider,
        model=cfg.litellm_model,
        api_key=cfg.api_key_value(),
        base_url=cfg.llm_base_url,
    )
    try:
        info = asyncio.run(llm.test_connection())
    except Exception as exc:
        print(f"│  llm ping:     crashed — {type(exc).__name__}: {exc}")
        print("└─")
        return 2

    if info.get("ok"):
        sample = (info.get("sample") or "").strip().replace("\n", " ")[:40]
        print(f"│  llm ping:     OK — model={info.get('model')!r} reply={sample!r}")
        print("└─ self-check passed")
        return 0

    print(f"│  llm ping:     FAILED — {info.get('error', 'unknown error')}")
    print("└─ self-check failed")
    return 2


# -----------------------------------------------------------------------------#
# Module exports                                                                #
# -----------------------------------------------------------------------------#


__all__ = ("main", "build_parser", "apply_overrides")
