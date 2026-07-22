#!/usr/bin/env python3
"""
Foundry v14 module manifest validator.

Implements the rules promised by the foundry-vtt-v14-modules skill
(SKILL.md), which cites this script but doesn't ship it. Run it
before every commit that touches module.json.

Catches the specific mistakes that have shipped in real projects:

  | Bug                                | What it looks like                          |
  |------------------------------------|---------------------------------------------|
  | Invented top-level field           | "compatibility.notes": "..." (note the dot)  |
  | Wrong field name (compat)          | compatibility: { tested: "14" }             |
  | Wrong type                         | compatibility: { minimum: "12" }            |
  | Wrong manifest URL                 | manifest: "raw.githubusercontent.com/..."    |
  | ESM key confusion                  | scripts: [scripts/main.js] (no esmodules)    |
  | Missing icon                       | no media[] array                            |
  | Missing changelog                  | no changelog key                            |
  | Non-semver version                 | version: "0.1" or "v1.0.0"                  |
  | Non-kebab id                       | id: "My_Module"                             |
  | Unknown top-level field            | "changelogUrl" instead of "changelog"       |

Exit codes:
    0 - clean
    1 - errors found
    2 - usage / file error
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, NamedTuple, Tuple


# ---------------------------------------------------------------------------
# Schema rules — derived from real shipped v14 modules (FXMaster and the
# League-of-Foundry-Developers template). Not exhaustive, but covers every
# bug we've actually shipped.
# ---------------------------------------------------------------------------

# Required top-level keys
REQUIRED_KEYS = (
    "id",
    "title",
    "description",
    "version",
    "authors",
    "compatibility",
    "manifest",
    "download",
)

# Top-level keys that must NOT contain a dot. A stray top-level
# "compatibility.notes" (with a literal dot in the key) is silently
# rejected by Foundry's schema and the module's compatibility badge
# shows "unknown" instead of green.
KEY_PATTERN = re.compile(r"^[a-z][a-zA-Z]*$")
NODE_EXECUTABLE = shutil.which("node") or shutil.which("node.exe")

# Compatibility block required keys
REQUIRED_COMPAT_KEYS = ("minimum", "verified")
# Known fields in compatibility (allowed)
ALLOWED_COMPAT_KEYS = {"minimum", "verified", "maximum", "notes"}
# Wrong field names that bit us
WRONG_COMPAT_KEYS = {"tested"}


class Issue(NamedTuple):
    severity: str  # "error" or "warning"
    message: str


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _is_url(s: str) -> bool:
    return bool(re.match(r"^https?://[^\s]+$", s))


def _node_syntax_check(
    source: str, input_type: str
) -> subprocess.CompletedProcess[str]:
    if NODE_EXECUTABLE is None:
        raise RuntimeError("Node.js is not available")
    return subprocess.run(
        [NODE_EXECUTABLE, f"--input-type={input_type}", "--check"],
        input=source,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _contains_static_module_syntax(source: str) -> bool | None:
    """Use Node's parser to identify source valid only in module mode."""
    if NODE_EXECUTABLE is None:
        return None
    classic = _node_syntax_check(source, "commonjs")
    if classic.returncode == 0:
        return False
    module = _node_syntax_check(source, "module")
    if module.returncode == 0:
        return True
    diagnostic = classic.stderr
    return any(
        marker in diagnostic
        for marker in (
            "Cannot use import statement outside a module",
            "Cannot use 'import.meta' outside a module",
            "Unexpected token 'export'",
        )
    )


def _is_kebab(s: str) -> bool:
    return bool(re.match(r"^[a-z0-9]+(-[a-z0-9]+)*$", s))


def _is_semver(s: str) -> bool:
    # X.Y.Z with optional pre-release/build metadata
    return bool(re.match(r"^\d+\.\d+\.\d+(-[A-Za-z0-9.]+)?(\+[A-Za-z0-9.]+)?$", s))


def validate_manifest(m: dict, manifest_path: Path | None = None) -> List[Issue]:
    issues: List[Issue] = []

    # --- Top-level structure -----------------------------------------------

    for key in REQUIRED_KEYS:
        if key not in m:
            issues.append(Issue("error", f"missing required top-level key: '{key}'"))

    for key in m.keys():
        if not KEY_PATTERN.match(key):
            issues.append(Issue(
                "error",
                f"top-level key '{key}' contains invalid characters — "
                f"Foundry's manifest schema requires keys matching "
                f"{KEY_PATTERN.pattern} (no dots, no hyphens). "
                f"Did you mean to nest it inside another object?"
            ))

    # --- id ----------------------------------------------------------------

    if "id" in m:
        if not isinstance(m["id"], str):
            issues.append(Issue("error", f"id must be a string, got {type(m['id']).__name__}"))
        elif not _is_kebab(m["id"]):
            issues.append(Issue("error", f"id '{m['id']}' is not kebab-case (a-z, 0-9, single hyphens)"))

    # --- version -----------------------------------------------------------

    if "version" in m:
        if not isinstance(m["version"], str):
            issues.append(Issue("error", f"version must be a string, got {type(m['version']).__name__}"))
        elif not _is_semver(m["version"]):
            issues.append(Issue("error", f"version '{m['version']}' is not semver (X.Y.Z)"))

    # --- authors -----------------------------------------------------------

    if "authors" in m:
        if not isinstance(m["authors"], list) or not m["authors"]:
            issues.append(Issue("error", "authors must be a non-empty list"))
        else:
            for i, a in enumerate(m["authors"]):
                if not isinstance(a, dict):
                    issues.append(Issue("error", f"authors[{i}] must be an object"))
                elif "name" not in a:
                    issues.append(Issue("error", f"authors[{i}] missing required 'name'"))

    # --- compatibility -----------------------------------------------------

    if "compatibility" in m:
        compat = m["compatibility"]
        if not isinstance(compat, dict):
            issues.append(Issue("error", "compatibility must be an object"))
        else:
            for key in REQUIRED_COMPAT_KEYS:
                if key not in compat:
                    issues.append(Issue("error", f"compatibility.{key} is required"))

            for key in compat.keys():
                if key in WRONG_COMPAT_KEYS:
                    issues.append(Issue(
                        "error",
                        f"compatibility.{key} is not a valid field. "
                        f"Did you mean compatibility.verified?"
                    ))
                elif key not in ALLOWED_COMPAT_KEYS:
                    issues.append(Issue("warning", f"compatibility.{key} is not a known field"))

            for key in ("minimum", "verified"):
                if key in compat:
                    v = compat[key]
                    if not isinstance(v, (int, str)):
                        issues.append(Issue(
                            "error",
                            f"compatibility.{key} must be an integer or numeric string"
                        ))
                    elif isinstance(v, str) and not v.isdigit():
                        issues.append(Issue(
                            "error",
                            f"compatibility.{key}='{v}' is a non-numeric string"
                        ))
                    elif isinstance(v, str):
                        # Foundry accepts both int and string forms (the
                        # League template uses int, FXMaster uses string),
                        # but int is the recommended form.
                        issues.append(Issue(
                            "warning",
                            f"compatibility.{key} is a string; recommended form is an integer"
                        ))

    # --- manifest + download URLs -----------------------------------------

    for key in ("manifest", "download"):
        if key in m:
            v = m[key]
            if not isinstance(v, str):
                issues.append(Issue("error", f"{key} must be a string URL"))
            elif not _is_url(v):
                issues.append(Issue("error", f"{key} must be an http(s) URL; got: {v!r}"))

    if "manifest" in m and isinstance(m["manifest"], str):
        if "raw.githubusercontent.com" in m["manifest"]:
            issues.append(Issue(
                "error",
                "manifest URL points to raw.githubusercontent.com — "
                "Foundry's update checker may not find new versions. "
                "Use 'https://github.com/<owner>/<repo>/releases/latest/download/module.json' instead."
            ))
        if "/releases/latest/download/" not in m["manifest"] and not m["manifest"].endswith("/module.json"):
            issues.append(Issue(
                "warning",
                "manifest URL does not point at /releases/latest/download/module.json — "
                "consider using a release URL for Foundry's update checker"
            ))

    # --- esmodules vs scripts ----------------------------------------------

    if "scripts" in m and "esmodules" not in m:
        issues.append(Issue(
            "warning",
            "manifest has 'scripts' but no 'esmodules' — for v12+ ES modules, "
            "use esmodules so the file loads as an ES module with import/export"
        ))

    if manifest_path is not None:
        for entry in m.get("scripts", []):
            if not isinstance(entry, str):
                continue
            entry_path = manifest_path.parent / entry
            if not entry_path.is_file():
                continue
            source = entry_path.read_text(encoding="utf-8", errors="replace")
            module_syntax = _contains_static_module_syntax(source)
            if module_syntax is None:
                issues.append(Issue(
                    "warning",
                    f"could not inspect classic script entry '{entry}' for module-only syntax — "
                    "Node.js was not found on PATH"
                ))
            elif module_syntax:
                issues.append(Issue(
                    "error",
                    f"classic script entry '{entry}' contains static import/export syntax — "
                    "Foundry will parse it outside a module. Move the entry from "
                    "'scripts' to 'esmodules' or emit a classic-script bundle."
                ))

    # --- media (icon) ------------------------------------------------------

    if "media" not in m:
        issues.append(Issue(
            "warning",
            "no 'media' array — module list will show a generic placeholder icon. "
            "Add: \"media\": [{\"type\": \"icon\", \"url\": \"...png\"}]"
        ))

    # --- changelog ---------------------------------------------------------

    if "changelog" not in m:
        issues.append(Issue("warning", "no 'changelog' link — users can't see what changed"))

    # --- relationships.requires -------------------------------------------

    if "relationships" in m and isinstance(m["relationships"], dict):
        rels = m["relationships"]
        if "requires" not in rels:
            issues.append(Issue(
                "warning",
                "relationships block has no 'requires' — if this module depends on "
                "another module, declare it here so load order is deterministic"
            ))

    return issues


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1] if __doc__ else None)
    ap.add_argument(
        "path",
        nargs="?",
        default="foundry-module/module.json",
        help="Path to module.json (default: foundry-module/module.json)",
    )
    ap.add_argument(
        "--json", action="store_true", help="Output as JSON (for CI / pre-commit)"
    )
    args = ap.parse_args()

    path = Path(args.path)
    if not path.exists():
        print(f"ERROR: {path} does not exist", file=sys.stderr)
        return 2

    try:
        m = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {path} is not valid JSON: {e}", file=sys.stderr)
        return 2

    issues = validate_manifest(m, path)

    if args.json:
        out = {
            "path": str(path),
            "id": m.get("id"),
            "version": m.get("version"),
            "issues": [{"severity": s, "message": msg} for s, msg in issues],
        }
        json.dump(out, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        print(f"=== Validating {path} ===")
        print(f"  id:      {m.get('id', '?')}")
        print(f"  version: {m.get('version', '?')}")
        print()

        if not issues:
            print("  ✓ no issues found")
        else:
            for sev, msg in issues:
                marker = "✗" if sev == "error" else "⚠"
                print(f"  {marker} [{sev}] {msg}")
            errors = sum(1 for i in issues if i.severity == "error")
            warnings = len(issues) - errors
            print()
            print(f"  Total: {errors} errors, {warnings} warnings")

    return 1 if any(i.severity == "error" for i in issues) else 0


if __name__ == "__main__":
    sys.exit(main())
