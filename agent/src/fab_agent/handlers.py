"""Design request handlers.

The handler module owns the *session model*. A session is a dict
stored in :class:`ServerState` keyed by ``sessionId`` with the shape::

    {
        "docType": "location",
        "prompt": "Build a smuggler's tavern...",
        "context": {...} | None,
        "history": [{"role": "user", "content": "..."}, ...],
        "draft": {...} | None,        # the latest validated draft
        "llm_task": asyncio.Task | None,
        "createdAt": int,             # ms epoch
        "updatedAt": int,
    }

Long-running LLM work is dispatched with :func:`asyncio.create_task` so
the WebSocket handler can return the immediate response (e.g.
``design.start.result`` with a freshly-minted ``sessionId``) without
waiting for the model to finish. The task then streams
``design.thinking`` events to the client and finally emits
``design.preview`` (or ``design.error``) when the draft is ready.

A single global :class:`ServerState` instance is shared by all
connections in the same process. (v1 is single-tenant; multi-tenant
isolation is out of scope.)
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from .config import AGENT_NAME, AGENT_VERSION, FabConfig
from .llm import LLM, extract_json_object
from .prompts import build_design_prompt, build_user_prompt
from .protocol import (
    DesignCommitted,
    DesignError,
    DesignPreview,
    DesignThinking,
    new_session_id,
)
from .validators import validate_draft

log = logging.getLogger(__name__)

# -----------------------------------------------------------------------------#
# Server state                                                                  #
# -----------------------------------------------------------------------------#


@dataclass
class ServerState:
    """Process-wide state held by the agent.

    Currently a thin wrapper around an in-memory dict of sessions plus
    a small set of immutable references (config, llm, skills). Kept as
    a dataclass so future fields (e.g. metrics) can be added without
    breaking the handler signatures.
    """

    config: FabConfig
    llm: LLM
    skills_text: str
    sessions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

    # ------------------------------------------------------------------ stats
    def stats(self) -> Dict[str, Any]:
        return {
            "agent": AGENT_NAME,
            "version": AGENT_VERSION,
            "model": self.config.llm_model,
            "uptime_seconds": round(time.time() - self.started_at, 1),
            "active_sessions": len(self.sessions),
            "skills_bytes": len(self.skills_text),
        }

    # ------------------------------------------------------------------ sessions
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        return self.sessions.get(session_id)

    def create_session(
        self,
        doc_type: str,
        prompt: str,
        context: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = session_id or new_session_id()
        now = int(time.time() * 1000)
        session: Dict[str, Any] = {
            "sessionId": sid,
            "docType": doc_type,
            "prompt": prompt,
            "context": context or {},
            "history": [{"role": "user", "content": prompt}],
            "draft": None,
            "llm_task": None,
            "createdAt": now,
            "updatedAt": now,
        }
        self.sessions[sid] = session
        return session

    def drop_session(self, session_id: str) -> None:
        session = self.sessions.pop(session_id, None)
        if session and session.get("llm_task"):
            task: asyncio.Task = session["llm_task"]
            if not task.done():
                task.cancel()


# Type alias for the send callable the handlers receive.
SendCallable = Callable[[Dict[str, Any]], Awaitable[None]]


# -----------------------------------------------------------------------------#
# hello                                                                         #
# -----------------------------------------------------------------------------#


async def handle_hello(state: ServerState) -> Dict[str, Any]:
    """Respond to a client ``hello`` with the agent's identity card."""
    s = state.stats()
    log.info("hello -> %s v%s (model=%s)", s["agent"], s["version"], s["model"])
    return {
        "agent": s["agent"],
        "version": s["version"],
        "model": s["model"],
        "skillsBytes": s["skills_bytes"],
        "activeSessions": s["active_sessions"],
        "uptimeSeconds": s["uptime_seconds"],
    }


# -----------------------------------------------------------------------------#
# design.start                                                                  #
# -----------------------------------------------------------------------------#


async def handle_design_start(
    state: ServerState,
    send: SendCallable,
    *,
    doc_type: str,
    prompt: str,
    context: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Start a new design session and kick off LLM generation.

    Returns ``{"sessionId": "..."}`` immediately; the actual draft is
    delivered as ``design.thinking`` + ``design.preview`` pushes on the
    same WebSocket.
    """
    if not doc_type:
        raise ValueError("docType is required")
    if not prompt:
        raise ValueError("prompt is required")
    if doc_type not in (
        "location", "npc", "region", "shop", "group", "quest",
    ):
        raise ValueError(
            f"unsupported docType {doc_type!r}; "
            f"expected one of: location, npc, region, shop, group, quest"
        )

    session = state.create_session(doc_type, prompt, context, session_id)
    sid = session["sessionId"]
    log.info(
        "design.start session=%s docType=%s prompt=%d chars",
        sid, doc_type, len(prompt),
    )

    # Spawn the long-running LLM task. The task streams deltas via
    # `send()` and finally emits a `design.preview` (or `design.error`).
    task = asyncio.create_task(
        _run_design_task(
            state,
            send,
            sid,
            doc_type=doc_type,
            prompt=prompt,
            context=context or {},
            feedback=None,
        ),
        name=f"fab-design-{sid}",
    )
    session["llm_task"] = task
    return {"sessionId": sid}


# -----------------------------------------------------------------------------#
# design.refine                                                                 #
# -----------------------------------------------------------------------------#


async def handle_design_refine(
    state: ServerState,
    send: SendCallable,
    *,
    session_id: str,
    feedback: str,
) -> Dict[str, Any]:
    """Iterate on an existing session's draft."""
    if not session_id:
        raise ValueError("sessionId is required")
    if not feedback:
        raise ValueError("feedback is required")
    session = state.get_session(session_id)
    if session is None:
        raise KeyError(f"unknown sessionId: {session_id}")
    if session.get("llm_task") and not session["llm_task"].done():
        # Don't run two LLM streams concurrently on the same session —
        # let the first one finish (or cancel it) before starting a new one.
        log.warning("design.refine session=%s: cancelling prior LLM task", session_id)
        session["llm_task"].cancel()
        try:
            await session["llm_task"]
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    # Append the feedback to the conversation history so the LLM sees it
    # alongside the original request.
    session["history"].append({"role": "user", "content": feedback})
    session["updatedAt"] = int(time.time() * 1000)
    log.info("design.refine session=%s feedback=%d chars", session_id, len(feedback))

    task = asyncio.create_task(
        _run_design_task(
            state,
            send,
            session_id,
            doc_type=session["docType"],
            prompt=session["prompt"],
            context=session.get("context") or {},
            feedback=feedback,
        ),
        name=f"fab-refine-{session_id}",
    )
    session["llm_task"] = task
    return {"sessionId": session_id}


# -----------------------------------------------------------------------------#
# design.commit                                                                 #
# -----------------------------------------------------------------------------#


async def handle_design_commit(
    state: ServerState,
    send: SendCallable,
    *,
    session_id: str,
    options: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Acknowledge a client-side commit.

    The actual ``JournalEntry.create`` happens inside the Foundry
    module, not here. The agent just confirms the session, drops it
    from in-memory state, and pushes a ``design.committed`` event.
    """
    if not session_id:
        raise ValueError("sessionId is required")
    session = state.get_session(session_id)
    if session is None:
        # Be lenient — a client retrying after a reconnect may commit
        # against a session that was dropped at server restart. We still
        # return success because the work the user cares about (the
        # JournalEntry) was created client-side.
        log.warning("design.commit session=%s: unknown session; treating as ack", session_id)
        await send(
            DesignCommitted(
                sessionId=session_id,
                uuid=None,
                note="unknown session; acknowledged anyway",
            ).model_dump(exclude_none=True)
        )
        return {"committed": True, "note": "unknown session"}

    uuid = (options or {}).get("uuid") if isinstance(options, dict) else None
    log.info("design.commit session=%s uuid=%s", session_id, uuid)
    await send(
        DesignCommitted(
            sessionId=session_id,
            uuid=str(uuid) if uuid else None,
            note="client-side commit acknowledged",
        ).model_dump(exclude_none=True)
    )
    state.drop_session(session_id)
    return {"committed": True}


# -----------------------------------------------------------------------------#
# Internal: the long-running LLM task                                           #
# -----------------------------------------------------------------------------#


async def _run_design_task(
    state: ServerState,
    send: SendCallable,
    session_id: str,
    *,
    doc_type: str,
    prompt: str,
    context: Dict[str, Any],
    feedback: Optional[str],
) -> None:
    """Drive a single LLM call to completion and emit stream events.

    Sequence of events on the wire:

      1. ``design.thinking`` (many) — text deltas from the LLM
      2. ``design.preview`` (one) — the validated structured draft, OR
         ``design.error`` if the LLM didn't produce valid JSON

    Errors at any stage are caught and surfaced as ``design.error``;
    they never propagate out of this function (the WS handler must
    stay responsive).
    """
    session = state.get_session(session_id)
    history: List[Dict[str, Any]] = (
        list(session.get("history") or []) if session else []
    )
    try:
        system_prompt = build_design_prompt(
            state.skills_text, context, doc_type, prompt, history
        )
        user_prompt = build_user_prompt(doc_type, prompt, feedback)

        # We seed the message list with the conversation history. For a
        # refine, the history is [original, feedback, original, feedback, ...]
        # and the *current* user prompt is built from the latest feedback
        # so we don't duplicate it.
        messages: List[Dict[str, Any]] = list(history[:-1]) if feedback else list(history)
        messages.append({"role": "user", "content": user_prompt})

        log.debug(
            "llm.stream start session=%s docType=%s msgs=%d system=%d chars",
            session_id, doc_type, len(messages), len(system_prompt),
        )

        collected: List[str] = []
        async for delta in state.llm.stream(system_prompt, messages):
            if not delta:
                continue
            collected.append(delta)
            await send(
                DesignThinking(
                    sessionId=session_id, delta=delta
                ).model_dump(exclude_none=True)
            )

        full_text = "".join(collected)
        log.debug(
            "llm.stream end session=%s collected=%d chars",
            session_id, len(full_text),
        )

        # Parse the LLM output as JSON. Be liberal — the LLM often wraps
        # the object in prose or a code fence.
        parsed = extract_json_object(full_text)
        if parsed is None:
            log.warning("design session=%s: no JSON found in LLM output", session_id)
            await send(
                DesignError(
                    sessionId=session_id,
                    error="LLM output did not contain a valid JSON object",
                    errors=[full_text[:200]],
                ).model_dump(exclude_none=True)
            )
            return

        # Stamp the doc type in case the model omitted/forgot it.
        parsed.setdefault("sheetType", doc_type)
        if not parsed.get("name"):
            parsed["name"] = _best_effort_name(full_text, doc_type) or "Untitled"

        result = validate_draft(parsed)
        if not result["valid"]:
            log.warning(
                "design session=%s: validation errors: %s",
                session_id, result["errors"],
            )
            # Try to send the raw (but coerced) draft anyway so the user
            # can see what the model produced.
            await send(
                DesignPreview(
                    sessionId=session_id,
                    draft=result.get("normalized") or parsed,
                ).model_dump(exclude_none=True)
            )
            await send(
                DesignError(
                    sessionId=session_id,
                    error="Draft had validation issues",
                    errors=list(result["errors"]),
                ).model_dump(exclude_none=True)
            )
            if session is not None:
                session["draft"] = result.get("normalized") or parsed
            return

        draft = result["normalized"] or {}
        if session is not None:
            session["draft"] = draft
            # Add the assistant's final message to the history so a
            # subsequent refine has context.
            session["history"].append({
                "role": "assistant",
                "content": full_text,
            })
            session["updatedAt"] = int(time.time() * 1000)
        await send(
            DesignPreview(
                sessionId=session_id,
                draft=draft,
            ).model_dump(exclude_none=True)
        )
        log.info(
            "design session=%s: preview emitted (name=%s, fields=%d)",
            session_id, draft.get("name"), len(draft),
        )
    except asyncio.CancelledError:
        log.info("design session=%s: cancelled", session_id)
        raise
    except Exception as exc:  # noqa: BLE001
        log.exception("design session=%s: failed: %s", session_id, exc)
        try:
            await send(
                DesignError(
                    sessionId=session_id,
                    error=f"{type(exc).__name__}: {exc}",
                ).model_dump(exclude_none=True)
            )
        except Exception:  # pragma: no cover - defensive
            pass


# -----------------------------------------------------------------------------#
# Tiny helpers                                                                   #
# -----------------------------------------------------------------------------#


_NAME_RE = re.compile(
    r'"name"\s*:\s*"([^"]+)"',
    flags=re.IGNORECASE,
)


def _best_effort_name(text: str, doc_type: str) -> Optional[str]:
    """Last-ditch attempt to extract a name from raw LLM text."""
    m = _NAME_RE.search(text or "")
    if m:
        return m.group(1).strip()
    # Fall back to the first line that looks like a title.
    for line in (text or "").splitlines():
        line = line.strip().strip("#").strip('"').strip()
        if 2 < len(line) < 80 and "\n" not in line:
            return line
    return None
