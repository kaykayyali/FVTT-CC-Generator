"""``python -m fab_agent`` entry point.

Forwards straight to :func:`fab_agent.cli.main`. Kept intentionally thin so
that the CLI is the single source of truth for argument parsing, config
loading, and runtime selection.
"""

from __future__ import annotations

import sys
from typing import NoReturn

from .cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        # SIGINT is not an error in the CLI sense — exit 130 is the
        # conventional code for Ctrl-C.
        sys.exit(130)
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover — defensive
        print(f"fab-agent: fatal: {exc}", file=sys.stderr)
        sys.exit(1)

# Re-exported for the type checker / static analysis tools.
_ = NoReturn
