"""Compile-only sanity check for the fab-agent Python source tree.

Run with::

    python -m compileall -q src tests

This file is kept as a no-op marker so the ``tests`` package still
imports cleanly under pytest's collection (which would otherwise
import every module — including ones that need litellm/websockets —
and fail at import time in a barebones env).
"""
