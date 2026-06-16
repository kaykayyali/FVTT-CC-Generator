"""Loader for the four SKILL.md files that live alongside the package.

The agent feeds these into the LLM's system prompt so that the model has
the schema, the 5e mechanics, the compendium-search-first rule, and the
world-context-linking rules at its fingertips. The skills are read once
at process start and cached in memory.

Public entry point: :func:`load_all_skills`.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Tuple

log = logging.getLogger(__name__)

# Canonical list of skill directories. Order matters — the first skill
# (campaign-codex-sheets) is the schema reference, the others layer on
# domain knowledge and workflow rules.
SKILL_NAMES: Tuple[str, ...] = (
    "campaign-codex-sheets",
    "dnd5e-content-authoring",
    "compendium-search-first",
    "world-context-linking",
)


def _default_skills_dir() -> Path:
    """The default location of the skills tree.

    Layout::

        agent/src/fab_agent/
            skills_loader.py
            skills/
                <skill-name>/
                    SKILL.md
    """
    return Path(__file__).resolve().parent / "skills"


def _read_one(skill_dir: Path) -> str:
    """Read a single ``SKILL.md`` and return its raw text.

    Strips a single optional front-matter block (the ``---`` YAML header
    that every skill has) so we don't waste context tokens on metadata
    the LLM doesn't need.
    """
    md = skill_dir / "SKILL.md"
    if not md.exists():
        raise FileNotFoundError(f"missing SKILL.md in {skill_dir}")
    text = md.read_text(encoding="utf-8")

    # Strip front matter, if any.
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        if end != -1:
            text = text[end + len("\n---"):].lstrip("\n")
    return text


def discover_skills(skills_dir: Path) -> List[Path]:
    """Return a sorted list of skill directories containing a ``SKILL.md``.

    Exposes a single function callers can use to enumerate skills without
    depending on the hard-coded :data:`SKILL_NAMES` list (handy for tests
    and for future skills that are dropped into the directory at runtime).
    """
    if not skills_dir.exists():
        return []
    out: List[Path] = []
    for child in sorted(skills_dir.iterdir()):
        if not child.is_dir():
            continue
        if (child / "SKILL.md").exists():
            out.append(child)
    return out


def load_all_skills(
    skills_dir: Path | None = None,
    *,
    include_front_matter: bool = False,
) -> str:
    """Load every SKILL.md under ``skills_dir`` and concatenate them.

    The output is a single Markdown string ready to be pasted into the
    LLM's system prompt. Each skill is wrapped in a level-2 header so
    the model can tell where one ends and the next begins.

    Args:
        skills_dir: Directory containing skill subfolders. Defaults to
            :func:`_default_skills_dir`.
        include_front_matter: When ``True``, the original YAML front
            matter is preserved in the output. Off by default — the LLM
            does not need the ``name:``, ``description:`` etc. metadata.

    Returns:
        A Markdown string with all four skills.

    Raises:
        FileNotFoundError: if no SKILL.md files are found at all.
    """
    base = (skills_dir or _default_skills_dir()).resolve()
    if not base.exists():
        raise FileNotFoundError(f"skills directory not found: {base}")

    # Prefer the canonical order; fall back to discovery if a name is missing.
    by_name = {p.name: p for p in discover_skills(base)}
    ordered: List[Path] = []
    seen: set = set()
    for name in SKILL_NAMES:
        if name in by_name:
            ordered.append(by_name[name])
            seen.add(name)
    # Append any extra skills not in the canonical list (alphabetical).
    for name, p in sorted(by_name.items()):
        if name not in seen:
            ordered.append(p)

    if not ordered:
        raise FileNotFoundError(
            f"no SKILL.md files found in {base} "
            f"(expected one of: {', '.join(SKILL_NAMES)})"
        )

    sections: List[str] = []
    total_bytes = 0
    for i, skill_dir in enumerate(ordered):
        body = _read_one(skill_dir)
        if not include_front_matter:
            body = _strip_front_matter(body)
        header = f"## Skill: {skill_dir.name}"
        sections.append(f"{header}\n\n{body.rstrip()}")
        total_bytes += len(body)
        log.debug(
            "loaded skill %s (%d bytes, %d skills loaded so far)",
            skill_dir.name,
            len(body),
            i + 1,
        )

    out = "\n\n---\n\n".join(sections)
    log.info(
        "loaded %d skills (%d bytes total) from %s",
        len(ordered),
        total_bytes,
        base,
    )
    return out


def _strip_front_matter(text: str) -> str:
    """Remove a single YAML front-matter block, if present."""
    if not text.startswith("---"):
        return text
    end = text.find("\n---", 3)
    if end == -1:
        return text
    # Skip past the closing "---" and any blank line.
    tail = text[end + 4:].lstrip("\n")
    return tail


def list_skill_names(skills_dir: Path | None = None) -> List[str]:
    """Return the names of all skills under ``skills_dir`` (for diagnostics)."""
    base = (skills_dir or _default_skills_dir()).resolve()
    return [p.name for p in discover_skills(base)]


def summarise(skills_text: str, max_chars: int = 400) -> str:
    """Return a short single-line summary of the loaded skills text.

    Used by ``--check`` and the ``hello`` payload so the operator can
    confirm the skills were actually loaded without dumping tens of KB
    into a log line.
    """
    snippet = skills_text.strip().splitlines()[:3]
    s = " | ".join(line.strip("# ").strip() for line in snippet if line.strip())
    if len(s) > max_chars:
        s = s[: max_chars - 1] + "…"
    return f"{len(skills_text):,} bytes; first lines: {s!r}"


# Re-exported for tests / external introspection.
__all__: Iterable[str] = (
    "SKILL_NAMES",
    "load_all_skills",
    "discover_skills",
    "list_skill_names",
    "summarise",
)
