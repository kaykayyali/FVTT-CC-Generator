"""WebSocket server for fab-agent.

This is the only file that talks to the wire. The architecture is:

    websockets.serve(_connection_handler, host, port, ...)
        |
        v
    _connection_handler(ws)
        |   1. (no auth in v0.2.x — see commit history)
        |   2. enter a `while True` loop reading JSON frames
        |   3. route by `type` to one of the handlers in handlers.py
        |   4. send the response, or schedule streaming pushes
        v
    goodbye (close 1000)

The server is intentionally minimal: no per-connection state beyond the
common :class:`ServerState` (config + llm + skills + sessions). The
design handlers maintain their own per-session state inside
``state.sessions``.

``websockets`` v12+ exposes both the high-level coroutine API and the
``process_request`` hook. v0.2.x has no auth check — any client that
can complete the WebSocket upgrade can talk to the agent. Operators
are expected to run the agent behind a firewall or overlay network
(Tailscale, Cloudflare Tunnel, etc.). The original Sec-WebSocket-
Protocol-based token check was removed because the WS spec forbids
``=`` and ``.`` in subprotocol names.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import signal
import sys
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any, Dict, Optional, Set, TYPE_CHECKING

from .config import FabConfig, configure_logging
from .handlers import (
    ServerState,
    handle_design_commit,
    handle_design_refine,
    handle_design_start,
    handle_hello,
)
from .llm import LLM
from .protocol import (
    DesignCommitted,
    DesignError,
    DesignPreview,
    DesignThinking,
    ErrorResponse,
    parse_client_message,
    to_json,
)
from .skills_loader import load_all_skills, summarise as summarise_skills

if TYPE_CHECKING:  # pragma: no cover
    from websockets.legacy.server import WebSocketServerProtocol

log = logging.getLogger(__name__)

# Heartbeat: if we don't see a frame from the client within this many
# seconds, close the socket. Keeps idle sessions from leaking.
HEARTBEAT_TIMEOUT_S = 300.0

# Backlog of recent log lines surfaced in the `--check` report.
STARTUP_BANNER = (
    "┌──────────────────────────────────────────────────────────────┐\n"
    "│  fab-agent — FVTT-CC-Generator local AI agent                 │\n"
    "│  v{version:>5}                                                │\n"
    "└──────────────────────────────────────────────────────────────┘"
)


# -----------------------------------------------------------------------------#
# Public entry point                                                            #
# -----------------------------------------------------------------------------#


async def serve(
    config: FabConfig,
    llm: LLM,
    skills_text: str,
    *,
    host: Optional[str] = None,
    port: Optional[int] = None,
) -> None:
    """Start the WebSocket server and run forever.

    The signature accepts the already-built dependencies explicitly so
    that ``--check`` and integration tests can exercise the same code
    path without standing up a real socket.

    Args:
        config: Fully-validated runtime configuration.
        llm: A configured :class:`LLM` instance.
        skills_text: Output of :func:`skills_loader.load_all_skills`.
        host: Optional override for ``config.agent_host``.
        port: Optional override for ``config.agent_port``.
    """
    bind_host = host or config.agent_host
    bind_port = int(port or config.agent_port)

    state = ServerState(
        config=config,
        llm=llm,
        skills_text=skills_text,
    )

    # websockets v12 ships both `websockets.serve` (legacy, callback-style)
    # and `websockets.asyncio.server.serve` (native asyncio). The legacy
    # import is the most compatible across versions; the asyncio variant
    # is preferred when available. We probe at runtime.
    serve_fn, ws_kwargs = _resolve_serve_api()
    ws_kwargs.setdefault("ping_interval", 30)
    ws_kwargs.setdefault("ping_timeout", 20)
    ws_kwargs.setdefault("max_size", 4 * 1024 * 1024)

    log.info("listening on ws://%s:%d/ws/v1", bind_host, bind_port)
    log.info(
        "LLM: provider=%s model=%s base_url=%s",
        config.llm_provider,
        config.llm_model,
        config.llm_base_url or "(default)",
    )
    log.info("skills: %s", summarise_skills(skills_text))

    async with serve_fn(
        _make_connection_handler(state),
        bind_host,
        bind_port,
        **ws_kwargs,
    ):
        # Park the loop until Ctrl-C / SIGTERM.
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            with suppress(NotImplementedError):  # Windows doesn't accept add_signal_handler
                loop.add_signal_handler(sig, stop.set)
        try:
            await stop.wait()
        finally:
            log.info("shutting down")


# -----------------------------------------------------------------------------#
# Connection handler                                                            #
# -----------------------------------------------------------------------------#


def _make_connection_handler(state: ServerState):
    """Build the per-connection coroutine closed over ``state``.

    The factory pattern keeps the public ``serve`` signature clean and
    makes it trivial to swap the handler in tests.
    """
    async def handler(connection):  # type: ignore[no-untyped-def]
        # `connection` is either:
        #   - websockets.legacy.server.WebSocketServerProtocol  (callback API)
        #   - websockets.asyncio.server.ServerConnection        (asyncio API)
        # Both expose `request_headers` and `send`/`recv` (or `send`/`recv` awaitables).
        return await _connection_loop(state, connection)

    return handler


async def _connection_loop(state: ServerState, ws) -> None:
    """Run the per-connection message loop.

    v0.2.x: no auth check. Any client that can complete the WebSocket
    handshake can talk to the agent. Security is intentionally deferred
    (see docs/wiki/troubleshooting.md and the project roadmap). The
    agent is meant to run on a machine the operator controls, behind
    a firewall or overlay network (Tailscale, Cloudflare Tunnel, etc.).
    """
    remote = _remote_address(ws)
    log.info("connect from %s", remote)

    # --- Welcome banner ---------------------------------------------------
    log.info(
        "client accepted from %s (skills=%d bytes, model=%s)",
        remote, len(state.skills_text), state.config.llm_model,
    )

    # --- Message loop -----------------------------------------------------
    session_id_for_conn = uuid.uuid4().hex[:8]
    try:
        while True:
            try:
                raw = await asyncio.wait_for(
                    ws.recv(), timeout=HEARTBEAT_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                log.info(
                    "connection %s idle for %ds, closing",
                    session_id_for_conn, int(HEARTBEAT_TIMEOUT_S),
                )
                await _safe_close(ws, code=1000, reason="idle timeout")
                return
            except Exception as exc:  # ConnectionClosed, etc.
                log.info("connection %s closed: %s", session_id_for_conn, exc)
                return

            if not isinstance(raw, (str, bytes)):
                # Binary frames are not part of the v1 protocol.
                log.warning("ignoring non-text frame from %s", remote)
                continue
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                log.warning("bad JSON from %s: %s", remote, exc)
                await _send(ws, ErrorResponse(
                    type="error",
                    id=None,
                    error=f"invalid JSON: {exc}",
                ).model_dump(exclude_none=True))
                continue

            try:
                request = parse_client_message(data)
            except ValueError as exc:
                log.warning("bad message from %s: %s", remote, exc)
                await _send(ws, ErrorResponse(
                    type=str(data.get("type") or "error"),
                    id=data.get("id"),
                    error=str(exc),
                ).model_dump(exclude_none=True))
                continue

            log.info(
                "recv type=%s id=%s from=%s",
                request.type, request.id, remote,
            )
            await _dispatch(state, ws, request)
    except Exception as exc:  # noqa: BLE001
        log.exception("connection %s crashed: %s", remote, exc)
        with suppress(Exception):
            await _send(ws, ErrorResponse(
                type="error",
                id=None,
                error=f"server error: {exc}",
            ).model_dump(exclude_none=True))
    finally:
        log.info("disconnect %s", remote)


# -----------------------------------------------------------------------------#
# Dispatch                                                                      #
# -----------------------------------------------------------------------------#


async def _dispatch(state: ServerState, ws, request) -> None:
    """Route a parsed request to the matching handler and send a response.

    All streamed events (``design.thinking`` etc.) are sent by the
    handler itself via the ``send`` callable it receives — that is how
    the long-running LLM task pushes intermediate output.
    """
    send = _make_send(ws)

    try:
        if request.type == "hello":
            result = await handle_hello(state)
            await _send(ws, {
                "id": request.id,
                "type": "hello.result",
                "ok": True,
                "result": result,
            })
            return

        if request.type == "design.start":
            result = await handle_design_start(
                state,
                send,
                doc_type=request.doc_type,
                prompt=request.prompt,
                context=request.context,
                session_id=request.session_id,
            )
            await _send(ws, {
                "id": request.id,
                "type": "design.start.result",
                "ok": True,
                "result": result,
            })
            return

        if request.type == "design.refine":
            result = await handle_design_refine(
                state,
                send,
                session_id=request.session_id,
                feedback=request.feedback,
            )
            await _send(ws, {
                "id": request.id,
                "type": "design.refine.result",
                "ok": True,
                "result": result,
            })
            return

        if request.type == "design.commit":
            result = await handle_design_commit(
                state,
                send,
                session_id=request.session_id,
                options=request.options,
            )
            await _send(ws, {
                "id": request.id,
                "type": "design.commit.result",
                "ok": True,
                "result": result,
            })
            return

        # The discriminator should have caught this already, but be
        # defensive against future additions.
        raise ValueError(f"unhandled message type: {request.type!r}")
    except ValueError as exc:
        log.warning("dispatch error for %s: %s", request.type, exc)
        await _send(ws, {
            "id": request.id,
            "type": f"{request.type}.result",
            "ok": False,
            "error": str(exc),
        })
    except KeyError as exc:
        log.warning("dispatch key error for %s: %s", request.type, exc)
        await _send(ws, {
            "id": request.id,
            "type": f"{request.type}.result",
            "ok": False,
            "error": str(exc),
        })
    except Exception as exc:  # noqa: BLE001
        log.exception("dispatch failure for %s: %s", request.type, exc)
        await _send(ws, {
            "id": request.id,
            "type": f"{request.type}.result",
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
        })


# -----------------------------------------------------------------------------#
# Send / close helpers (accommodate both APIs)                                  #
# -----------------------------------------------------------------------------#


def _make_send(ws):
    """Return an async ``send(dict)`` callable bound to the connection.

    The handler API is uniform: ``await send({...})``. We wrap the
    raw socket so the handlers don't have to know about JSON encoding
    or which websockets version is in use.
    """
    async def send(payload: Dict[str, Any]) -> None:
        # Accept either pydantic models or plain dicts.
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump(exclude_none=True)
        await _send(ws, payload)
    return send


async def _send(ws, payload: Dict[str, Any]) -> None:
    """Send a JSON frame, swallowing ConnectionClosed at the edge."""
    if payload is None:
        return
    text = json.dumps(payload, ensure_ascii=False, default=str)
    try:
        await ws.send(text)
    except Exception as exc:
        # The connection is gone — log and move on. The handler task
        # may still be running; it'll get an exception on the next send.
        log.debug("send failed (client gone?): %s", exc)


async def _safe_close(ws, *, code: int = 1000, reason: str = "") -> None:
    """Close the socket, swallowing any error from a half-closed peer."""
    try:
        close = ws.close
    except AttributeError:
        return
    try:
        result = close(code=code, reason=reason)
        if inspect.isawaitable(result):
            await result
    except Exception as exc:  # noqa: BLE001
        log.debug("close failed: %s", exc)


def _remote_address(ws) -> str:
    """Best-effort ``addr:port`` for log lines."""
    try:
        # legacy API
        addr = ws.remote_address
    except AttributeError:
        try:
            # asyncio API
            addr = ws.get_remote_address()  # type: ignore[attr-defined]
        except Exception:
            return "?"
    if isinstance(addr, tuple) and len(addr) == 2:
        return f"{addr[0]}:{addr[1]}"
    return str(addr)


def _resolve_serve_api():
    """Pick the right ``serve()`` function for the installed websockets version.

    Returns a tuple ``(serve_fn, kwargs)``. The legacy API takes a
    callback; the asyncio API takes an async function. Both are
    callable, so we adapt by checking signatures at runtime.
    """
    try:
        from websockets.asyncio.server import serve as aio_serve  # type: ignore
        # The asyncio server returns a Server object directly usable as
        # an async context manager; pass-through of subprotocol is via
        # the handler / `process_request`.
        return aio_serve, {}
    except Exception:  # pragma: no cover - older websockets
        pass

    try:
        from websockets.legacy.server import serve as legacy_serve  # type: ignore
        # Legacy API: the `subprotocols` arg has been removed; clients
        # always send a single subprotocol and we read it from headers.
        return legacy_serve, {}
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "websockets is not importable. Run `uv sync` to install it. "
            f"(original error: {exc})"
        )


# -----------------------------------------------------------------------------#
# Entrypoint used by the CLI                                                     #
# -----------------------------------------------------------------------------#


def run(config: FabConfig, skills_dir: Optional[Path] = None) -> None:
    """Synchronous entry point: build deps, then start the async server.

    Used by :mod:`fab_agent.cli`. ``skills_dir`` defaults to the
    package's bundled ``skills/`` directory.
    """
    configure_logging(config.log_level)
    log.info(STARTUP_BANNER.format(version=config.__class__.__module__))

    skills_text = load_all_skills(skills_dir or (Path(__file__).parent / "skills"))

    llm = LLM(
        provider=config.llm_provider,
        model=config.litellm_model,
        api_key=config.api_key_value(),
        base_url=config.llm_base_url,
    )
    log.info(
        "LLM ready: provider=%s model=%s",
        config.llm_provider, config.litellm_model,
    )

    try:
        asyncio.run(serve(config, llm, skills_text))
    except KeyboardInterrupt:
        log.info("interrupted; exiting")
