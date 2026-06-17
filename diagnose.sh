#!/bin/bash
# FVTT-CC-Generator — connectivity diagnostic
# Run this in the same terminal you'll start the agent from.
# All 5 checks should pass before the Foundry module can talk to the agent.

echo "=== 1. Is the agent process running? ==="
# On Windows, an agent running would show in tasklist (with python in name)
tasklist 2>/dev/null | grep -i python | head -5 || echo "  (no python in tasklist — agent is not running)"
echo ""
echo "  If empty: start the agent first: cd agent && uv run fab-agent"
echo ""

echo "=== 2. Is anything listening on port 7777? ==="
netstat -an 2>/dev/null | grep "7777" | head -3 || echo "  (nothing on 7777 — agent is not bound)"
echo ""
echo "  If empty: agent is not running, or it's listening on a different port"
echo ""

echo "=== 3. Can the loopback address be reached at all? ==="
curl -s -o /dev/null -w "  HTTP from 127.0.0.1: HTTP %{http_code} in %{time_total}s\n" --max-time 3 http://127.0.0.1:7777/ 2>&1
echo ""
echo "  If you see 'connection refused' here, the agent is NOT listening."
echo "  If you see an HTTP code (200/404/etc), the agent IS listening and reachable."
echo ""

echo "=== 4. Is Windows Firewall blocking port 7777? ==="
# Check if there is an inbound rule allowing 7777
powershell -NoProfile -Command "Get-NetFirewallRule | Where-Object { \$_.DisplayName -like '*7777*' -or \$_.DisplayName -like '*FAB*' -or \$_.DisplayName -like '*Foundry*' } | Format-Table DisplayName, Enabled, Direction, Action" 2>&1 | head -10
echo ""
echo "  If empty: no explicit rule. Windows may still block by default for 'private' network."
echo ""

echo "=== 5. What IP should the browser use? ==="
# Get the local IPs
ipconfig 2>/dev/null | grep -E "IPv4|Subnet" | head -8
echo ""
echo "  When the agent binds to 0.0.0.0 (all interfaces), the browser can use ANY of these."
echo "  When the agent binds to 127.0.0.1, the browser MUST use 127.0.0.1."
echo ""

echo "=== Done. Share this output if you need more help. ==="
