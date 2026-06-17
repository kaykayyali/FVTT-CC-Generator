"""
WebSocket roundtrip test for the fab-agent.

Spins up the agent on a random free port, opens a WebSocket client,
sends a `hello` message, verifies the response, and shuts down.

This catches:
- Server fails to bind (wrong host/port)
- Server fails to handle the upgrade
- The hello handler is missing or broken
- The request/response correlation is broken (id not echoed back)
- The agent crashes on a simple protocol exchange

It does NOT call the LLM (no API key required). It only exercises
the network and protocol layers.

Run from project root (use `uv run` to get the agent's deps):
    uv run --project agent python tests/test_ws_protocol.py
"""

from __future__ import annotations

import asyncio
import json
import socket
import sys
import time
from pathlib import Path
from typing import Optional

# Make the agent importable. The agent is in agent/src/fab_agent/.
# When run via `uv run --project agent`, this is on sys.path already;
# we add it explicitly to also work when run as a plain script.
AGENT_SRC = Path(__file__).resolve().parent.parent / "agent" / "src"
if str(AGENT_SRC) not in sys.path:
    sys.path.insert(0, str(AGENT_SRC))


def _find_free_port() -> int:
    """Find a TCP port that's free right now."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


async def _roundtrip(port: int, timeout: float = 5.0) -> Optional[dict]:
    """Connect to the agent on `port`, send a hello, return the response."""
    import websockets

    uri = f"ws://127.0.0.1:{port}/ws/v1"
    try:
        async with websockets.connect(uri, open_timeout=timeout) as ws:
            # Send a hello with a known id
            request_id = f"test-{int(time.time() * 1000)}"
            await ws.send(json.dumps({
                "id": request_id,
                "type": "hello",
                "payload": {},
            }))
            # Wait for the matching response
            deadline = time.time() + timeout
            while time.time() < deadline:
                raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
                msg = json.loads(raw)
                if msg.get("id") == request_id:
                    return msg
            return None
    except Exception as e:
        return {"_error": f"{type(e).__name__}: {e}"}


async def _run_test() -> int:
    # Find a free port
    port = _find_free_port()

    # Import the agent components
    from fab_agent.config import FabConfig
    from fab_agent.server import serve

    # Build a minimal config (no LLM, no skills, no nothing — we only
    # need the server to start and the hello handler to fire)
    cfg = FabConfig(
        agent_host="127.0.0.1",
        agent_port=port,
    )

    print(f"=== WS roundtrip test (port {port}) ===")

    # The hello handler doesn't call the LLM, so we can pass None.
    # skills_text isn't needed for the hello path either.
    server_task = asyncio.create_task(
        serve(cfg, llm=None, skills_text="")
    )

    # Give the server a moment to bind
    await asyncio.sleep(0.3)

    try:
        # Try the roundtrip
        response = await _roundtrip(port, timeout=5.0)
    finally:
        server_task.cancel()
        try:
            await server_task
        except asyncio.CancelledError:
            pass

    if response is None:
        print("  ✗ no response from agent")
        return 1

    if "_error" in response:
        print(f"  ✗ connection failed: {response['_error']}")
        return 1

    print(f"  ← response: {json.dumps(response, indent=4)[:500]}")

    # Verify the response has the expected fields
    if response.get("type") != "hello.result":
        print(f"  ✗ expected type='hello.result', got {response.get('type')!r}")
        return 1
    if response.get("ok") is not True:
        print(f"  ✗ expected ok=True, got {response.get('ok')!r}")
        return 1
    if "id" not in response:
        print("  ✗ response missing 'id' field")
        return 1

    print()
    print("  ✓ agent accepts connections, handles hello, returns a valid response")
    return 0


def main() -> int:
    try:
        return asyncio.run(_run_test())
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
