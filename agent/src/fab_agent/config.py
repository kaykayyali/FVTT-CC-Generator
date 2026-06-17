"""Pydantic Settings for the fab-agent.

All values come from environment variables (or a ``.env`` file in the
current working directory, or the directory containing ``fab_agent/``).
The prefix is ``FAB_`` so that the agent can safely coexist with other
Python tools in the same shell.

Usage::

    from fab_agent.config import load_config

    cfg = load_config()
    print(cfg.llm_model, cfg.agent_port)
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Optional

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

log = logging.getLogger(__name__)

# Default agent version string surfaced to the Foundry client during hello.
AGENT_VERSION = "0.1.0"
AGENT_NAME = "fab-agent"


class FabConfig(BaseSettings):
    """Strongly-typed view of the agent's runtime configuration.

    All fields are sourced from environment variables prefixed with
    ``FAB_``. The mapping is::

        FAB_LLM_PROVIDER   -> llm_provider
        FAB_LLM_MODEL      -> llm_model
        FAB_LLM_API_KEY    -> llm_api_key   (SecretStr)
        FAB_LLM_BASE_URL   -> llm_base_url  (optional)

        FAB_AGENT_HOST     -> agent_host
        FAB_AGENT_PORT     -> agent_port
        FAB_AGENT_TOKEN    -> agent_token

        FAB_LOG_LEVEL      -> log_level

    Defaults are tuned for the common OpenAI-on-laptop case.
    """

    # --- LLM -----------------------------------------------------------------
    llm_provider: str = Field(
        default="openai",
        description="Provider identifier passed to litellm. Bare name "
        "('openai', 'anthropic', 'ollama', ...) is fine; litellm maps it.",
    )
    llm_model: str = Field(
        default="gpt-4o",
        description="Model name. May be a fully-qualified litellm model "
        "string (e.g. 'anthropic/claude-sonnet-4-20250514').",
    )
    llm_api_key: Optional[SecretStr] = Field(
        default=None,
        description="Provider API key. Optional for local providers like Ollama.",
    )
    llm_base_url: Optional[str] = Field(
        default=None,
        description="Optional base URL override (OpenRouter, OpenAI-compatible "
        "proxies, remote Ollama, ...).",
    )

    # --- Server --------------------------------------------------------------
    agent_host: str = Field(
        default="0.0.0.0",
        description="Interface the WebSocket server binds to. Default 0.0.0.0 (all interfaces) so Tailscale and other overlays can reach it. Set to 127.0.0.1 to restrict to loopback only.",
    )
    agent_port: int = Field(
        default=7777,
        ge=1,
        le=65535,
        description="TCP port the WebSocket server listens on.",
    )
    agent_token: str = Field(
        default="change-me-in-module-settings",
        min_length=4,
        description="Shared secret validated against the "
        "`Sec-WebSocket-Protocol: fab.v1.token=<token>` header.",
    )

    # --- Misc ----------------------------------------------------------------
    log_level: str = Field(
        default="INFO",
        description="Standard log level name (DEBUG/INFO/WARNING/ERROR/CRITICAL).",
    )

    # --- Pydantic Settings wiring -------------------------------------------
    model_config = SettingsConfigDict(
        env_prefix="FAB_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_ignore_empty=True,
        extra="ignore",
        case_sensitive=False,
    )

    # ------------------------------------------------------------------ Validators
    @field_validator("log_level")
    @classmethod
    def _normalise_log_level(cls, v: str) -> str:
        v = (v or "INFO").upper().strip()
        if v not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError(
                f"Invalid log level {v!r}. "
                "Use one of: DEBUG, INFO, WARNING, ERROR, CRITICAL."
            )
        return v

    @field_validator("agent_host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        v = (v or "").strip() or "0.0.0.0"
        return v

    @field_validator("agent_token")
    @classmethod
    def _validate_token(cls, v: str) -> str:
        v = (v or "").strip()
        if v.startswith("change") and v.endswith("module-settings"):
            # Not a hard error — we let the server start, but warn loudly so
            # the operator sees it in the very first log line.
            log.warning(
                "fab-agent | using the default placeholder token. Set "
                "FAB_AGENT_TOKEN in .env (and update the Foundry module's "
                "matching setting) before connecting from a real client."
            )
        return v

    # ------------------------------------------------------------------ Helpers
    @property
    def ws_url(self) -> str:
        """The full WebSocket URL the agent listens on."""
        return f"ws://{self.agent_host}:{self.agent_port}/ws/v1"

    @property
    def litellm_model(self) -> str:
        """A model name suitable for passing to ``litellm.completion``.

        If ``llm_provider`` is already a prefix (e.g. ``openrouter/``,
        ``anthropic/``) we leave the model alone. Otherwise we prepend
        ``llm_provider/`` so litellm can route correctly.
        """
        model = (self.llm_model or "").strip()
        if not model:
            return model
        # If the model already has a routing prefix, don't double-prefix.
        if "/" in model:
            return model
        provider = (self.llm_provider or "").strip()
        if not provider or provider == "openai" and model.startswith("gpt-"):
            # Heuristic: bare "openai" + bare gpt-* names work without a prefix.
            return model
        if not provider:
            return model
        return f"{provider}/{model}"

    def api_key_value(self) -> Optional[str]:
        """Return the API key as a plain ``str`` (or ``None``).

        ``SecretStr`` keeps the key out of repr/str by default, which is
        what we want for logging. litellm needs the raw value, so we expose
        it through this explicit accessor.
        """
        if self.llm_api_key is None:
            return None
        return self.llm_api_key.get_secret_value()


def _locate_env_file() -> Optional[Path]:
    """Find the most appropriate ``.env`` file.

    Search order:
      1. ``FAB_ENV_FILE`` environment variable (explicit override)
      2. ``$CWD/.env``
      3. ``agent/.env`` (one directory above the package source)
      4. ``agent/src/fab_agent/.env`` (sibling of the package)
    """
    explicit = os.environ.get("FAB_ENV_FILE")
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None

    candidates = [
        Path.cwd() / ".env",
        Path.cwd() / "agent" / ".env",
    ]
    # Walk up to the package source.
    try:
        package_dir = Path(__file__).resolve().parent
        candidates.append(package_dir.parent.parent / ".env")
        candidates.append(package_dir / ".env")
    except Exception:  # pragma: no cover
        pass

    for p in candidates:
        if p.exists():
            return p
    return None


def load_config(env_file: Optional[Path] = None) -> FabConfig:
    """Build a :class:`FabConfig` from the current process environment.

    Args:
        env_file: Optional explicit path to a ``.env`` file. When omitted,
            :func:`_locate_env_file` is used.

    Returns:
        A fully validated :class:`FabConfig`.

    Note:
        We *also* call :func:`dotenv.load_dotenv` so that any vars not
        declared on :class:`FabConfig` (e.g. ``OPENAI_API_KEY`` when the
        user prefers the native convention) are visible to litellm.
    """
    try:
        from dotenv import load_dotenv  # type: ignore

        chosen = env_file or _locate_env_file()
        if chosen is not None:
            load_dotenv(chosen, override=False)
    except Exception as exc:  # pragma: no cover
        log.debug("dotenv not available or failed: %s", exc)

    # The settings model still gets the path through FAB_ENV_FILE / CWD.
    cfg = FabConfig(_env_file=(str(env_file) if env_file else None))
    return cfg


def configure_logging(level: str) -> None:
    """Set up the root logger in a single, idempotent call.

    Honours the ``FAB_LOG_LEVEL`` env var via :func:`load_config` but also
    accepts an explicit override (used by the CLI).
    """
    lvl = (level or "INFO").upper().strip()
    handler = logging.StreamHandler(stream=sys.stderr)
    fmt = "%(asctime)s %(levelname)-5s %(name)s — %(message)s"
    handler.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    # Idempotent: clear any previously installed handlers (notably the
    # basicConfig one that pydantic-settings may install during its boot).
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(lvl)
    # Quiet down a couple of chatty third-party loggers.
    logging.getLogger("websockets").setLevel(max(lvl_value(lvl), logging.INFO))
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("litellm").setLevel(logging.WARNING)


def lvl_value(name: str) -> int:
    return {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
        "CRITICAL": logging.CRITICAL,
    }.get(name.upper(), logging.INFO)
