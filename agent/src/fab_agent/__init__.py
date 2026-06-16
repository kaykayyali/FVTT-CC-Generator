"""fab-agent — local WebSocket agent for the FVTT-CC-Generator Foundry module.

This package implements the Python side of the FVTT-CC-Generator project:
a loopback WebSocket server that talks to the Foundry VTT v14 module
``fvtt-cc-generator`` and produces structured Campaign Codex sheets
(location, npc, region, shop, group, quest) via a provider-agnostic LLM
interface (powered by ``litellm``).

The package is **standalone**: it has no dependency on the Hermes Agent
runtime. It loads four SKILL.md files from ``fab_agent/skills/`` and feeds
them, together with a world-context snapshot, to the LLM as the system
prompt. The Foundry module previews the generated draft and commits it to
the world as a ``JournalEntry`` with the appropriate Campaign Codex flag
payload.
"""

from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["__version__"]
