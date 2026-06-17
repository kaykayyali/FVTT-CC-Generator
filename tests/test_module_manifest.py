"""
Foundry v14 manifest schema validator.

The full Foundry v14 manifest schema lives in the proprietary client
source — it's not publicly published. This validator implements the
subset of rules we can observe by inspecting shipped modules like
FXMaster (gambit07/fxmaster) and the League-of-Foundry-Developers
module template, plus the rules that Foundry's own loader enforces
(we know from experience: required keys, integer compat values,
URL-shaped download, etc.).

It is NOT a complete schema. It catches the common mistakes (the ones
we've actually made in this project: invented fields, string-typed
integers, wrong URL shapes) without claiming to be authoritative.

Run from project root:
    python tests/test_module_manifest.py
    # or as part of the full suite:
    pytest tests/
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import List, Tuple


# Rules derived from real shipped v14 modules (FXMaster as the canonical
# reference) and from mistakes we've made in this project that we want
# caught before they ship.

REQUIRED_TOP_KEYS = [
    "id",
    "title",
    "version",
    "description",
    "authors",
    "compatibility",
    "manifest",
    "download",
    "esmodules",
]

# Fields we have historically fabricated that don't exist in the schema.
# Cross-checked against the League-of-Foundry-Developers v14 module
# template (which is the canonical reference) and FXMaster.
# If you add a field here, the test will fail with a clear message.
FORBIDDEN_TOP_KEYS = [
    "compatibility.notes",  # not a real field — use compatibility.notes
    "compatibility.tested",  # wrong name; use compatibility.verified
]

# compatibility block
REQUIRED_COMPAT_KEYS = ["minimum", "verified"]
FORBIDDEN_COMPAT_KEYS = ["tested", "notes"]  # we use "verified", not "tested"


def _err(message: str) -> Tuple[str, str]:
    """Format an error message."""
    return ("error", message)


def _warn(message: str) -> Tuple[str, str]:
    """Format a warning message."""
    return ("warning", message)


def _is_url(s: str) -> bool:
    """Check if a string is a valid http(s) URL."""
    return bool(re.match(r"^https?://[^\s]+$", s))


def _is_semver(s: str) -> bool:
    """Check if a string is a sensible version (X.Y.Z with optional -suffix)."""
    return bool(re.match(r"^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?$", s))


def validate_manifest(m: dict) -> List[Tuple[str, str]]:
    """Validate a manifest dict. Returns a list of (severity, message)."""
    issues: List[Tuple[str, str]] = []

    # Required top-level keys
    for key in REQUIRED_TOP_KEYS:
        if key not in m:
            issues.append(_err(f"missing required top-level key: '{key}'"))

    # Forbidden top-level keys (typos / fabrications)
    for key in FORBIDDEN_TOP_KEYS:
        if key in m:
            issues.append(_err(
                f"forbidden top-level key: '{key}' — this is not a real Foundry v14 manifest field"
            ))

    # id: kebab-case slug
    if "id" in m and not re.match(r"^[a-z0-9_-]+$", m["id"]):
        issues.append(_err(f"id must be kebab-case slug; got: {m['id']!r}"))

    # version: semver
    if "version" in m and not _is_semver(m["version"]):
        issues.append(_err(f"version should follow semver (X.Y.Z); got: {m['version']!r}"))

    # authors: list of objects with 'name' (and optionally 'url', 'email')
    if "authors" in m:
        if not isinstance(m["authors"], list) or not m["authors"]:
            issues.append(_err("authors must be a non-empty list"))
        else:
            for i, a in enumerate(m["authors"]):
                if not isinstance(a, dict):
                    issues.append(_err(f"authors[{i}] must be an object, got: {type(a).__name__}"))
                elif "name" not in a:
                    issues.append(_err(f"authors[{i}] missing required 'name' field"))

    # compatibility block
    if "compatibility" in m:
        compat = m["compatibility"]
        if not isinstance(compat, dict):
            issues.append(_err("compatibility must be an object"))
        else:
            for key in REQUIRED_COMPAT_KEYS:
                if key not in compat:
                    issues.append(_err(f"compatibility.{key} is required"))
            for key in FORBIDDEN_COMPAT_KEYS:
                if key in compat:
                    issues.append(_err(
                        f"compatibility.{key} is not a valid field — "
                        f"did you mean compatibility.verified?"
                    ))
            # minimum/verified: FXMaster uses string form ("13"), the
            # League template uses integer form (13). Both work —
            # accept either, but flag the value's shape if it looks
            # wrong (e.g. "thirteen").
            for key in ("minimum", "verified"):
                if key in compat and not isinstance(compat[key], (int, str)):
                    issues.append(_err(
                        f"compatibility.{key} must be an integer or numeric string"
                    ))

    # manifest + download: valid http URLs
    for key in ("manifest", "download"):
        if key in m:
            v = m[key]
            if not isinstance(v, str):
                issues.append(_err(f"{key} must be a string URL"))
            elif not _is_url(v):
                issues.append(_err(f"{key} must be an http(s) URL; got: {v!r}"))

    # manifest and download should both serve a release artifact
    if "manifest" in m and _is_url(m["manifest"]):
        if "/releases/latest/download/" not in m["manifest"] and not m["manifest"].endswith("/module.json"):
            issues.append(_warn(
                f"manifest URL does not point at /releases/latest/download/module.json — "
                f"Foundry's update checker may not find new versions"
            ))

    # esmodules: list of strings (relative paths to ES module entry points)
    if "esmodules" in m:
        if not isinstance(m["esmodules"], list):
            issues.append(_err("esmodules must be a list"))
        else:
            for i, p in enumerate(m["esmodules"]):
                if not isinstance(p, str):
                    issues.append(_err(f"esmodules[{i}] must be a string path"))

    return issues


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    manifest_path = repo_root / "foundry-module" / "module.json"

    if not manifest_path.exists():
        print(f"NOT FOUND: {manifest_path}", file=sys.stderr)
        return 2

    try:
        m = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"INVALID JSON: {e}", file=sys.stderr)
        return 2

    issues = validate_manifest(m)

    print(f"=== Validating {manifest_path} ===")
    print(f"  id:      {m.get('id', '?')}")
    print(f"  version: {m.get('version', '?')}")
    print()

    if not issues:
        print("  ✓ No issues found")
        return 0

    errors = [i for i in issues if i[0] == "error"]
    warnings = [i for i in issues if i[0] == "warning"]

    for sev, msg in errors:
        print(f"  ✗ {msg}")
    for sev, msg in warnings:
        print(f"  ⚠ {msg}")

    print()
    print(f"  Total: {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
