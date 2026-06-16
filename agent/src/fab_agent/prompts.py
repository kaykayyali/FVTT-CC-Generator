"""System / user prompt construction for the design handlers.

The agent's LLM has two prompts:

* **System** — assembled once per request from:
    1. a hard-coded *rules* preamble (always emits JSON, never invents
       compendium items, links to existing world content, etc.)
    2. the four SKILL.md files, concatenated
    3. an optional *world context* snapshot of existing CC sheets
    4. a per-doc-type schema reminder

* **User** — the design request itself, with conversation history
  folded in (for refines).

Everything in this module is pure (no I/O, no LLM calls), so the
:func:`build_design_prompt` and :func:`build_user_prompt` functions are
trivial to unit-test.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Mapping, Sequence

# -----------------------------------------------------------------------------#
# Rules preamble                                                                 #
# -----------------------------------------------------------------------------#


# A short, strict rules block. The wording is deliberate: it sets the
# JSON-only contract, points at the compendium rule, and reminds the
# model to link to existing world content where possible.
_RULES = """\
You are **fab-agent**, the local AI assistant for the Foundry VTT v14
module "FVTT-CC-Generator". You produce structured Campaign Codex sheets
for a tabletop RPG campaign.

# Output contract

* You ALWAYS respond with a single valid JSON object — no prose, no
  markdown, no code fences. The object must conform to the schema for
  the requested sheet type.
* The object MUST contain a `sheetType` field set to the doc type the
  user asked for. Allowed values: location, npc, region, shop, group,
  quest.
* The object MUST contain a non-empty `name` field.
* You MAY include a `pages` array of JournalEntryPage objects for
  prose body content. When you do, set `text.format: 1` (HTML) and
  emit clean semantic HTML — no inline styles, no `<script>`, no
  inline event handlers. Cross-references inside prose use Foundry's
  `@UUID[JournalEntry.uuid]{Display Name}` v14 syntax.

# Compendium search first

* For shops, NPCs with gear, and quest rewards, ALWAYS prefer linking
  to existing SRD compendium items (dnd5e.items, dnd5e.monsters) over
  inventing new ones. When the world has a matching entry, link to it
  by UUID; when it doesn't, you may create a new item but you must
  search the dnd5e SRD compendia first.
* An inventory item with `linkToCompendium: true` MUST also carry a
  `compendiumUuid` field. The companion Foundry module uses
  `fromUuid()` to resolve it at commit time.

# World context

* The user passes a snapshot of their existing world content in the
  `context` block (existing CC sheets, NPC actors, etc.). Link to
  existing sheets via `@UUID[...]` instead of re-creating them.
* A name collision with an existing sheet is a bug. If your draft
  duplicates an existing name, rename it or weave the existing sheet
  in.

# Schema sanity

* Use the field names from the loaded `campaign-codex-sheets` skill
  EXACTLY. An unknown field is silently ignored by Campaign Codex.
* Tags are simple strings, NO commas inside individual tags.
* For location sheets, set `parentLocation` to the name of the
  containing location when known.
* For npc sheets, set `linkedLocation` when known.
* For shop sheets, inventory entries should look like:
  `{"name": "...", "qty": 1, "price": "10 gp", "currency": "gp",
  "linkToCompendium": true, "compendiumUuid": "Compendium.dnd5e.items.xxx"}`.

# Tone

* Be specific and concrete, not generic. "A low-beamed dockside tavern
  lit by bioluminescent jellyfish tanks" is good; "a tavern" is not.
* Give every NPC two-to-three memorable traits, a clear motivation, and
  a secret. NPCs without a `secret` are usually forgotten.

# When in doubt

* If the user's request is ambiguous, prefer producing a usable draft
  with sensible defaults over asking a clarifying question — the
  Foundry UI will let them iterate via `design.refine`.
"""


# -----------------------------------------------------------------------------#
# Per-doc-type schema reminders                                                  #
# -----------------------------------------------------------------------------#


_SCHEMA_REMINDERS: Dict[str, str] = {
    "location": (
        "Location schema reminder:\n"
        "- `sheetType`: \"location\"\n"
        "- `type`: one of settlement | structure | dungeon | wilderness | plane | region | other\n"
        "- `parentLocation`: string, name of the containing location\n"
        "- `denizens[]`: { name, role, linkToSheet?: bool }\n"
        "- `linkedNpcs[]`, `linkedShops[]`, `linkedQuests[]`: arrays of UUIDs\n"
        "- `rumors[]`, `secrets[]`: string arrays\n"
        "- `pages[]`: at least one Overview page with `text.format: 1`"
    ),
    "npc": (
        "NPC schema reminder:\n"
        "- `sheetType`: \"npc\"\n"
        "- `type`: one of ally | neutral | enemy | patron | rival | boss | commoner\n"
        "- `linkedLocation`: UUID of where they live/work\n"
        "- `personality`, `motivation`, `secret`, `voice`: short strings\n"
        "- `linkedNpcs[]`, `linkedQuests[]`: arrays of UUIDs\n"
        "- `actorUuid`: optional link to an existing Actor sheet"
    ),
    "region": (
        "Region schema reminder:\n"
        "- `sheetType`: \"region\"\n"
        "- `type`: one of kingdom | province | city | district | biome | plane\n"
        "- `parentLocation`: containing region (e.g. district -> city)\n"
        "- `linkedLocations[]`, `linkedNpcs[]`, `linkedQuests[]`: arrays of UUIDs"
    ),
    "shop": (
        "Shop schema reminder:\n"
        "- `sheetType`: \"shop\"\n"
        "- `type`: one of general | weapons | armor | magic | alchemy | tavern | black-market | other\n"
        "- `linkedLocation`, `linkedNpc`: UUIDs\n"
        "- `inventory[]`: { name, qty, price, currency, linkToCompendium: true, compendiumUuid }\n"
        "- `specialItems[]`: { name, description, price, linkToCompendium: true, compendiumUuid }\n"
        "- `buyMultiplier`, `sellMultiplier`: numbers, default 1.0"
    ),
    "group": (
        "Group schema reminder:\n"
        "- `sheetType`: \"group\"\n"
        "- `type`: one of faction | family | organization | creed | other\n"
        "- `goals[]`, `resources[]`: string arrays\n"
        "- `allies[]`, `enemies[]`: UUIDs of other groups\n"
        "- `linkedNpcs[]`, `linkedLocations[]`: UUIDs"
    ),
    "quest": (
        "Quest schema reminder:\n"
        "- `sheetType`: \"quest\"\n"
        "- `type`: one of main | side | personal | rumor | faction\n"
        "- `objectives[]`: { text, completed: bool, optional: bool }\n"
        "- `rewards[]`: string array\n"
        "- `linkedNpcs[]`, `linkedLocations[]`, `linkedItems[]`: arrays of UUIDs\n"
        "- `parentQuest`: optional UUID for chains"
    ),
}


# -----------------------------------------------------------------------------#
# Builders                                                                       #
# -----------------------------------------------------------------------------#


def build_design_prompt(
    skills_text: str,
    world_context: Mapping[str, Any] | None,
    doc_type: str,
    user_prompt: str,
    feedback_history: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """Build the full system prompt for a design request.

    The result is a single string with four sections, in order:

      1. ``# Rules`` — the hard-coded rules preamble.
      2. ``# Loaded skills`` — the four SKILL.md files concatenated.
      3. ``# World context`` — a compact summary of the user's world.
      4. ``# Schema reminder`` — a one-paragraph recap of the doc type.

    Args:
        skills_text: Output of :func:`skills_loader.load_all_skills`.
        world_context: Snapshot of the world (existing CC sheets,
            NPC actors, …) as produced by the JS side. May be ``None``.
        doc_type: One of the six sheet type strings.
        user_prompt: The user's design request (echoed back in the user
            message, but we also mention it in the system prompt so
            the model has all context in one place).
        feedback_history: Optional list of prior turns in this session
            (each entry is a ``{"role": ..., "content": ...}`` dict).
            Currently unused at the system-prompt level — the LLM sees
            it through the message list — but accepted so callers can
            keep the same signature as the user-prompt builder.
    """
    parts: List[str] = ["# Rules\n\n" + _RULES.strip()]
    if skills_text:
        parts.append("# Loaded skills\n\n" + skills_text.strip())
    parts.append(_format_world_context(world_context))
    parts.append(
        "# Current request\n\n"
        f"Requested sheet type: **{doc_type}**.\n"
        f"User prompt: {user_prompt.strip()}"
    )
    reminder = _SCHEMA_REMINDERS.get(doc_type)
    if reminder:
        parts.append("# Schema reminder\n\n" + reminder)
    return "\n\n---\n\n".join(parts) + "\n"


def build_user_prompt(
    doc_type: str,
    user_prompt: str,
    feedback: str | None = None,
) -> str:
    """Build the user-side message body.

    The Foundry module sends the design request as the user message; on
    a refine, it sends the feedback as a follow-up user message. We wrap
    the raw text in a small "reminder to emit JSON" block so the model
    stays on contract.

    Args:
        doc_type: Sheet type the user asked for.
        user_prompt: Original design request.
        feedback: Optional refinement feedback. When present, this is
            used as the user message and the original request is folded
            in as context.
    """
    schema_hint = (
        f"Respond with a single JSON object that matches the "
        f"**{doc_type}** schema. No prose, no markdown fences."
    )
    if feedback:
        return (
            f"{schema_hint}\n\n"
            f"Original request: {user_prompt.strip()}\n\n"
            f"Refinement feedback: {feedback.strip()}"
        )
    return f"{schema_hint}\n\nDesign request: {user_prompt.strip()}"


# -----------------------------------------------------------------------------#
# Helpers                                                                        #
# -----------------------------------------------------------------------------#


def _format_world_context(world_context: Mapping[str, Any] | None) -> str:
    """Render a compact, token-cheap summary of the user's world.

    The JS side sends a snapshot like::

        {
          "sheets": { "location": [...], "npc": [...], ... },
          "npcActors": [...],
          "scannedAt": 1718000000000
        }

    We do not need to reproduce every field — the LLM only needs to
    know *what exists* so it can avoid duplicates and link to existing
    sheets. We summarise each sheet by ``name`` + ``uuid`` + ``type``.
    """
    if not world_context:
        return (
            "# World context\n\n"
            "No world context was provided. Treat the world as empty "
            "and produce a self-contained draft."
        )
    try:
        sheets = world_context.get("sheets") or {}
        npc_actors = world_context.get("npcActors") or []
        scanned_at = world_context.get("scannedAt")
    except AttributeError:
        return "# World context\n\nMalformed world context; ignoring."

    lines: List[str] = ["# World context", ""]
    if scanned_at:
        try:
            from datetime import datetime, timezone
            ts = datetime.fromtimestamp(int(scanned_at) / 1000, tz=timezone.utc)
            lines.append(f"_Scanned at {ts.isoformat(timespec='seconds')}._")
            lines.append("")
        except Exception:
            pass

    any_sheet = False
    for sheet_type, items in sheets.items():
        if not items:
            continue
        any_sheet = True
        lines.append(f"## Existing {sheet_type} sheets ({len(items)})")
        for s in items[:50]:  # cap to keep the prompt sane
            if not isinstance(s, Mapping):
                continue
            name = s.get("name", "<unnamed>")
            uuid = s.get("uuid", "")
            typ = s.get("type") or ""
            tag_str = ""
            tags = s.get("tags") or []
            if isinstance(tags, list) and tags:
                tag_str = "  #" + " #".join(str(t) for t in tags[:6])
            line = f"- {name}"
            if typ:
                line += f"  ({typ})"
            if uuid:
                line += f"  — uuid `{uuid}`"
            if tag_str:
                line += tag_str
            lines.append(line)
        if len(items) > 50:
            lines.append(f"_(… and {len(items) - 50} more)_")
        lines.append("")

    if npc_actors:
        any_sheet = True
        lines.append(f"## Existing NPC actors ({len(npc_actors)})")
        for a in npc_actors[:30]:
            if not isinstance(a, Mapping):
                continue
            name = a.get("name", "<unnamed>")
            uuid = a.get("uuid", "")
            race = a.get("race") or ""
            line = f"- {name}"
            if race:
                line += f"  ({race})"
            if uuid:
                line += f"  — uuid `{uuid}`"
            lines.append(line)
        if len(npc_actors) > 30:
            lines.append(f"_(… and {len(npc_actors) - 30} more)_")
        lines.append("")

    if not any_sheet:
        lines.append("The world contains no existing Campaign Codex sheets or NPC actors.")
        lines.append("")

    return "\n".join(lines).rstrip()


def world_context_json_safe(world_context: Mapping[str, Any] | None) -> str:
    """Serialise the world context as a compact JSON string for logging."""
    if not world_context:
        return "(none)"
    try:
        return json.dumps(world_context, ensure_ascii=False, default=str)[:512]
    except (TypeError, ValueError):
        return "(unserialisable)"


__all__ = (
    "build_design_prompt",
    "build_user_prompt",
    "world_context_json_safe",
)
