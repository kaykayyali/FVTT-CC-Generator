"""LLM abstraction over ``litellm``.

The agent's LLM usage is intentionally simple: it has a ``system`` prompt
(the four skills + a per-request preamble) and a list of ``messages``
(conversation history, plus the current design request). We need two
operations:

* :meth:`LLM.complete` — send the prompt, get a single string back. Used
  for short prompts where streaming is overkill (e.g. ``--check``).
* :meth:`LLM.stream` — send the prompt, get an async iterator of text
  deltas. Used by the design handlers to push ``design.thinking``
  events to the Foundry client as the model produces them.

``litellm`` is the routing layer, so the same code path supports OpenAI,
Anthropic, OpenRouter, Ollama, Azure, Bedrock, VertexAI, etc. with no
configuration changes — pick the provider via ``FAB_LLM_PROVIDER`` /
``FAB_LLM_MODEL`` in ``.env`` and you're done.

The :class:`LLM` class is a thin, async-friendly wrapper. It is cheap to
instantiate (no long-lived state) so the server constructs one per
process and shares it across connections.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, AsyncIterator, Dict, Iterable, List, Optional, Sequence

log = logging.getLogger(__name__)

# litellm is a soft import — the agent still starts without it so that
# ``--check`` can warn and exit cleanly when the operator hasn't installed
# deps yet.
try:
    import litellm  # type: ignore

    # Be polite in logs: litellm is *very* chatty.
    litellm.suppress_debug_info = True
    litellm.set_verbose = False
    _LITELLM_AVAILABLE = True
except Exception as exc:  # pragma: no cover - exercised on missing install
    litellm = None  # type: ignore
    _LITELLM_AVAILABLE = False
    log.debug("litellm import failed: %s", exc)


# -----------------------------------------------------------------------------#
# JSON extraction                                                               #
# -----------------------------------------------------------------------------#


# Match the first balanced {...} block in a string, or the first fenced
# ```json ... ``` block. Used to pull a structured draft out of an LLM
# completion that wrapped the JSON in prose (most do, even when asked
# to emit JSON-only).
_JSON_FENCE_RE = re.compile(
    r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```",
    flags=re.DOTALL | re.IGNORECASE,
)
_FIRST_OBJECT_RE = re.compile(r"\{.*\}", flags=re.DOTALL)


def extract_json_object(text: str) -> Optional[Dict[str, Any]]:
    """Find the first JSON object in ``text`` and decode it.

    Tries (in order):
      1. A ```json ... ``` fenced block.
      2. The first balanced ``{...}`` substring.
      3. The entire string, in case the model emitted pure JSON.

    Returns:
        A ``dict`` if a JSON object was found and parsed, else ``None``.
    """
    if not text:
        return None
    # Fenced block first.
    m = _JSON_FENCE_RE.search(text)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # Greedy first object. This may over-match on nested braces inside
    # strings, so we use a brace-counting fallback below.
    candidate = _slice_first_balanced_object(text)
    if candidate is not None:
        try:
            obj = json.loads(candidate)
            if isinstance(obj, dict):
                return obj
        except json.JSONDecodeError:
            pass
    # Last-ditch: the whole string.
    try:
        obj = json.loads(text.strip())
        if isinstance(obj, dict):
            return obj
    except json.JSONDecodeError:
        return None
    return None


def _slice_first_balanced_object(text: str) -> Optional[str]:
    """Return the first balanced ``{...}`` substring, or ``None``."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


# -----------------------------------------------------------------------------#
# LLM wrapper                                                                  #
# -----------------------------------------------------------------------------#


class LLM:
    """A thin async wrapper around :mod:`litellm`.

    The constructor takes the four pieces of configuration the agent
    already collects in :mod:`fab_agent.config`:

    >>> llm = LLM(provider="openai", model="gpt-4o", api_key="sk-…")
    >>> await llm.test_connection()  # doctest: +SKIP

    Two methods are exposed:

    * :meth:`complete` — returns a single ``str``.
    * :meth:`stream` — returns an :class:`AsyncIterator` of ``str`` chunks.

    Both accept a ``system`` prompt and a list of ``messages``. Extra
    litellm kwargs (``temperature``, ``max_tokens``, ``timeout``, …) can
    be passed through.
    """

    def __init__(
        self,
        provider: str,
        model: str,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.provider = (provider or "").strip()
        self.api_key = api_key
        self.base_url = base_url
        # Resolve the fully-qualified litellm model name lazily so the
        # config layer can override it at runtime.
        self._raw_model = (model or "").strip()
        self._resolved_model: Optional[str] = None

    # ------------------------------------------------------------------ model name
    @property
    def model(self) -> str:
        if self._resolved_model is None:
            self._resolved_model = self._resolve_model(self._raw_model, self.provider)
        return self._resolved_model

    @staticmethod
    def _resolve_model(model: str, provider: str) -> str:
        """Mirror :attr:`FabConfig.litellm_model` so we don't depend on it here."""
        if not model:
            return model
        if "/" in model:
            return model
        p = (provider or "").strip()
        # Heuristic: bare "openai" + bare gpt-* names work without prefix.
        if p in ("", "openai") and model.lower().startswith(("gpt-", "o1", "o3", "o4")):
            return model
        if not p:
            return model
        return f"{p}/{model}"

    # ------------------------------------------------------------------ low-level
    def _common_kwargs(self, **extra: Any) -> Dict[str, Any]:
        """Build the litellm kwargs shared by both complete and stream."""
        kw: Dict[str, Any] = {
            "model": self.model,
        }
        if self.api_key:
            kw["api_key"] = self.api_key
        if self.base_url:
            kw["base_url"] = self.base_url
        # Sensible defaults — operators can still override via ``**extra``.
        kw.setdefault("timeout", 60)
        kw.setdefault("stream", False)
        for k, v in extra.items():
            if v is not None:
                kw[k] = v
        return kw

    def _build_messages(
        self, system: str, messages: Sequence[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Compose the message list litellm expects.

        A non-empty ``system`` is prepended as a ``system``-role message.
        ``messages`` is copied so the caller's list is not mutated.
        """
        out: List[Dict[str, Any]] = []
        if system:
            out.append({"role": "system", "content": system})
        for m in messages or []:
            if not isinstance(m, dict):
                continue
            role = m.get("role", "user")
            content = m.get("content", "")
            if content is None:
                content = ""
            out.append({"role": str(role), "content": str(content)})
        return out

    # ------------------------------------------------------------------ complete
    async def complete(
        self,
        system: str,
        messages: Sequence[Dict[str, Any]],
        **kwargs: Any,
    ) -> str:
        """Run a non-streaming completion and return the text.

        Raises:
            RuntimeError: if litellm is not installed.
            Exception: whatever the underlying provider raises.
        """
        if not _LITELLM_AVAILABLE:
            raise RuntimeError(
                "litellm is not installed. Run `uv sync` or "
                "`pip install litellm>=1.40` in the agent's environment."
            )
        kw = self._common_kwargs(**{**kwargs, "stream": False})
        msgs = self._build_messages(system, messages)
        log.debug("llm.complete model=%s messages=%d", kw["model"], len(msgs))

        def _call() -> str:
            resp = litellm.completion(messages=msgs, **kw)
            # litellm returns ModelResponse; pull the text out.
            try:
                return resp.choices[0].message.content or ""
            except (AttributeError, IndexError, KeyError):
                return str(resp)

        return await asyncio.to_thread(_call)

    # ------------------------------------------------------------------ stream
    async def stream(
        self,
        system: str,
        messages: Sequence[Dict[str, Any]],
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Run a streaming completion; yield text deltas as they arrive.

        Implementation note: litellm's stream is synchronous and blocks
        the thread for the duration of the response, so we run it in
        :func:`asyncio.to_thread` and yield each chunk back through a
        :class:`queue.Queue`. This keeps the event loop responsive.
        """
        if not _LITELLM_AVAILABLE:
            raise RuntimeError(
                "litellm is not installed. Run `uv sync` or "
                "`pip install litellm>=1.40` in the agent's environment."
            )
        kw = self._common_kwargs(**{**kwargs, "stream": True})
        msgs = self._build_messages(system, messages)
        log.debug("llm.stream model=%s messages=%d", kw["model"], len(msgs))

        import queue
        import threading

        q: "queue.Queue[Any]" = queue.Queue(maxsize=128)
        sentinel = object()

        def _producer() -> None:
            try:
                for chunk in litellm.completion(messages=msgs, **kw):
                    delta = _delta_text(chunk)
                    if delta:
                        q.put(delta)
            except Exception as exc:  # pragma: no cover - defensive
                q.put(exc)
            finally:
                q.put(sentinel)

        threading.Thread(target=_producer, daemon=True).start()

        while True:
            item = await asyncio.to_thread(q.get)
            if item is sentinel:
                return
            if isinstance(item, Exception):
                raise item
            yield item

    # ------------------------------------------------------------------ test
    async def test_connection(self) -> Dict[str, Any]:
        """Run a tiny completion to verify credentials and routing.

        Returns a small dict with ``ok``, ``model``, and either
        ``sample`` (the first ~60 chars of the model's reply) or
        ``error`` (the failure message).
        """
        info: Dict[str, Any] = {"ok": False, "model": self.model}
        if not _LITELLM_AVAILABLE:
            info["error"] = "litellm is not installed"
            return info
        if not self._raw_model:
            info["error"] = "FAB_LLM_MODEL is not set"
            return info
        try:
            text = await self.complete(
                system="You are a connectivity test. Reply with the single word 'ok'.",
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=8,
                temperature=0.0,
            )
            info["ok"] = True
            info["sample"] = (text or "").strip()[:60]
        except Exception as exc:
            info["error"] = f"{type(exc).__name__}: {exc}"
        return info


# -----------------------------------------------------------------------------#
# helpers                                                                       #
# -----------------------------------------------------------------------------#


def _delta_text(chunk: Any) -> str:
    """Pull a text delta out of a litellm streaming chunk.

    litellm's chunk shape varies by provider; we try the common paths
    and return an empty string when no text is present in the chunk.
    """
    try:
        # OpenAI-style
        delta = chunk.choices[0].delta
        text = getattr(delta, "content", None) or delta.get("content")  # type: ignore[union-attr]
        if text:
            return text
        # Anthropic-style (sometimes wraps in a list)
        text = getattr(delta, "text", None) or delta.get("text")  # type: ignore[union-attr]
        if text:
            return text
    except (AttributeError, IndexError, KeyError, TypeError):
        return ""
    return ""


# -----------------------------------------------------------------------------#
# module exports                                                                #
# -----------------------------------------------------------------------------#


__all__: Iterable[str] = (
    "LLM",
    "extract_json_object",
    "is_litellm_available",
)


def is_litellm_available() -> bool:
    """Whether :mod:`litellm` was successfully imported."""
    return _LITELLM_AVAILABLE
