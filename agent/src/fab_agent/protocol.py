"""Pydantic models for the fab-agent WebSocket protocol.

The wire protocol is intentionally small and uses **request/response** for
anything the client initiates and **server-pushed events** for streaming
output (LLM "thinking" deltas, final drafts, errors).

Wire format
-----------

* **Request**  (C → S)::

      { "id": "fab-...", "type": "hello", "payload": {...} }

* **Response** (S → C)::

      { "id": "fab-...", "type": "hello.result", "ok": true, "result": {...} }

* **Pushed**   (S → C) — no ``id`` field, just a ``type``::

      { "type": "design.thinking", "sessionId": "...", "delta": "..." }
      { "type": "design.preview",   "sessionId": "...", "draft": {...} }
      { "type": "design.committed", "sessionId": "...", "uuid": "..." }
      { "type": "design.error",     "sessionId": "...", "error": "..." }

The models in this file are used both for **validation on the boundary**
(the server runs every incoming frame through ``parse_client_message``)
and as the source of truth for the response shapes the agent emits.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Literal, Mapping, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

# -----------------------------------------------------------------------------#
# Helpers                                                                      #
# -----------------------------------------------------------------------------#


def new_request_id() -> str:
    """Generate a unique request id.

    Mirrors the JS client's ``fab-<ts36>-<seq36>`` format so log lines from
    both sides are visually correlatable.
    """
    ts = int(time.time() * 1000)
    return f"fab-{ts:x}-{uuid.uuid4().int & 0x7fffffff:x}"


def new_session_id() -> str:
    """Generate a new design session id."""
    return f"sess-{uuid.uuid4().hex[:12]}"


# -----------------------------------------------------------------------------#
# Common base                                                                  #
# -----------------------------------------------------------------------------#


class _Base(BaseModel):
    """Common Pydantic config: tolerate extra keys, serialise by alias."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)


# -----------------------------------------------------------------------------#
# Client → Server requests                                                     #
# -----------------------------------------------------------------------------#


class HelloRequest(_Base):
    """``{"type": "hello", "payload": {}}`` — handshake."""

    id: str
    type: Literal["hello"] = "hello"
    payload: Dict[str, Any] = Field(default_factory=dict)


class DesignStartRequest(_Base):
    """``{"type": "design.start", ...}`` — kick off a new design session.

    ``sessionId`` is optional; the server will mint one if absent so the
    client can use a deterministic id when it wants to resume a session.
    """

    id: str
    type: Literal["design.start"] = "design.start"
    payload: Dict[str, Any] = Field(default_factory=dict)

    # Convenience accessors (the server unpacks payload; these let the
    # handler do ``req.doc_type`` rather than ``req.payload["docType"]``).
    @property
    def doc_type(self) -> str:
        return str(self.payload.get("docType", "") or "")

    @property
    def prompt(self) -> str:
        return str(self.payload.get("prompt", "") or "")

    @property
    def context(self) -> Dict[str, Any]:
        ctx = self.payload.get("context")
        return ctx if isinstance(ctx, dict) else {}

    @property
    def session_id(self) -> Optional[str]:
        s = self.payload.get("sessionId")
        return str(s) if s else None


class DesignRefineRequest(_Base):
    """``{"type": "design.refine", ...}`` — iterate on a session's draft."""

    id: str
    type: Literal["design.refine"] = "design.refine"
    payload: Dict[str, Any] = Field(default_factory=dict)

    @property
    def session_id(self) -> str:
        return str(self.payload.get("sessionId", "") or "")

    @property
    def feedback(self) -> str:
        return str(self.payload.get("feedback", "") or "")


class DesignCommitRequest(_Base):
    """``{"type": "design.commit", ...}`` — finalise the current draft.

    The actual ``JournalEntry.create`` happens client-side inside the
    Foundry module; the agent just acknowledges so the round trip is
    symmetric and the client can shut the session down cleanly.
    """

    id: str
    type: Literal["design.commit"] = "design.commit"
    payload: Dict[str, Any] = Field(default_factory=dict)

    @property
    def session_id(self) -> str:
        return str(self.payload.get("sessionId", "") or "")

    @property
    def options(self) -> Dict[str, Any]:
        opts = self.payload.get("options")
        return opts if isinstance(opts, dict) else {}


# The discriminated union of all inbound message types.
ClientRequest = Union[
    HelloRequest,
    DesignStartRequest,
    DesignRefineRequest,
    DesignCommitRequest,
]


# -----------------------------------------------------------------------------#
# Server → Client responses (request/response)                                 #
# -----------------------------------------------------------------------------#


class HelloResponse(_Base):
    """Sent in response to :class:`HelloRequest`."""

    id: str
    type: Literal["hello.result"] = "hello.result"
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


class DesignStartResponse(_Base):
    """Sent in response to :class:`DesignStartRequest`."""

    id: str
    type: Literal["design.start.result"] = "design.start.result"
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


class DesignRefineResponse(_Base):
    """Sent in response to :class:`DesignRefineRequest`."""

    id: str
    type: Literal["design.refine.result"] = "design.refine.result"
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


class DesignCommitResponse(_Base):
    """Sent in response to :class:`DesignCommitRequest`."""

    id: str
    type: Literal["design.commit.result"] = "design.commit.result"
    ok: bool = True
    result: Dict[str, Any] = Field(default_factory=dict)


class ErrorResponse(_Base):
    """Returned (with ``ok=false``) for any failed request."""

    id: Optional[str] = None
    type: str
    ok: bool = False
    error: str
    errors: List[str] = Field(default_factory=list)


# -----------------------------------------------------------------------------#
# Server → Client pushed events (no id)                                        #
# -----------------------------------------------------------------------------#


class DesignThinking(_Base):
    """A streamed chunk of the LLM's text output."""

    type: Literal["design.thinking"] = "design.thinking"
    sessionId: str
    delta: str


class DesignPreview(_Base):
    """A complete, validated draft ready for the client to render."""

    type: Literal["design.preview"] = "design.preview"
    sessionId: str
    draft: Dict[str, Any]


class DesignCommitted(_Base):
    """Pushed after a successful client-side commit to confirm."""

    type: Literal["design.committed"] = "design.committed"
    sessionId: str
    uuid: Optional[str] = None
    note: Optional[str] = None


class DesignError(_Base):
    """A non-fatal error in the design stream (replaces design.preview)."""

    type: Literal["design.error"] = "design.error"
    sessionId: str
    error: str
    errors: List[str] = Field(default_factory=list)


ServerEvent = Union[
    DesignThinking,
    DesignPreview,
    DesignCommitted,
    DesignError,
]


# -----------------------------------------------------------------------------#
# Parsing / serialisation helpers                                              #
# -----------------------------------------------------------------------------#


def parse_client_message(data: Mapping[str, Any]) -> ClientRequest:
    """Validate and dispatch an incoming frame to the right Pydantic model.

    Raises:
        ValueError: if the frame is missing a known ``type`` field, or if
            the payload is structurally invalid.
    """
    if not isinstance(data, Mapping):
        raise ValueError("message must be a JSON object")

    msg_type = data.get("type")
    msg_id = data.get("id")
    payload = data.get("payload") or {}
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    if not msg_id or not isinstance(msg_id, str):
        raise ValueError("missing or invalid 'id' field")

    base: Dict[str, Any] = {"id": msg_id, "payload": payload}

    if msg_type == "hello":
        return HelloRequest(**base)
    if msg_type == "design.start":
        return DesignStartRequest(**base)
    if msg_type == "design.refine":
        return DesignRefineRequest(**base)
    if msg_type == "design.commit":
        return DesignCommitRequest(**base)
    raise ValueError(f"unknown message type: {msg_type!r}")


def to_json(model: BaseModel) -> str:
    """Serialise a Pydantic model to a compact JSON string.

    Pydantic v2's ``model_dump_json`` is fine, but it doesn't always
    include all fields by alias consistently. We use a small wrapper so
    the rest of the codebase can stay terse.
    """
    return model.model_dump_json(exclude_none=True)


def make_error(message: Any, *, type_: str = "error", id_: Optional[str] = None) -> ErrorResponse:
    """Build a generic error response for unexpected failure paths."""
    err = message if isinstance(message, str) else str(message)
    return ErrorResponse(id=id_, type=type_, ok=False, error=err)
