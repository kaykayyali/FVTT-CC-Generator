"""
JS syntax check for the Foundry module.

Runs `node --check` on every .js file under foundry-module/scripts/.
This catches the "Cannot use import statement outside a module" class
of error before we ship the zip. It does NOT execute the code — that's
Foundry's job. It only verifies the JS is parseable.

Run from project root:
    python tests/test_js_syntax.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import List, Tuple


def check_file(path: Path) -> Tuple[bool, str]:
    """Run `node --check` on a file. Returns (ok, message)."""
    try:
        r = subprocess.run(
            ["node", "--check", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return (False, "node not found on PATH")
    except subprocess.TimeoutExpired:
        return (False, "node --check timed out")

    if r.returncode == 0:
        return (True, "ok")
    return (False, (r.stderr or r.stdout).strip())


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent
    scripts_dir = repo_root / "foundry-module" / "scripts"

    if not scripts_dir.exists():
        print(f"NOT FOUND: {scripts_dir}", file=sys.stderr)
        return 2

    js_files = sorted(scripts_dir.rglob("*.js"))
    if not js_files:
        print(f"  (no .js files found in {scripts_dir})")
        return 0

    print(f"=== JS syntax check ({len(js_files)} files) ===")
    failed: List[Tuple[Path, str]] = []

    for p in js_files:
        ok, msg = check_file(p)
        rel = p.relative_to(repo_root)
        status = "✓" if ok else "✗"
        print(f"  {status} {rel}")
        if not ok:
            failed.append((p, msg))
            print(f"      {msg}")

    print()
    if failed:
        print(f"  ✗ {len(failed)} file(s) failed syntax check")
        return 1
    print(f"  ✓ all {len(js_files)} files parse cleanly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
