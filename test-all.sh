#!/usr/bin/env bash
# test-all.sh — run every test suite we have, exit non-zero on any failure.
#
# Suites:
#   1. Manifest validator  (python, no agent deps)
#   2. JS syntax check     (node --check, no agent deps)
#   3. Agent unit tests    (pytest, needs the agent venv)
#   4. WS roundtrip        (asyncio, needs the agent venv)
#
# Use:
#   ./test-all.sh
#   ./test-all.sh --skip-agent   # for CI environments without the agent venv

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "${REPO_ROOT}"

SKIP_AGENT=0
if [ "${1:-}" = "--skip-agent" ]; then
    SKIP_AGENT=1
fi

GREEN=''
RED=''
YELLOW=''
NC=''

# Enable colors if stdout is a TTY
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    YELLOW='\033[0;33m'
    NC='\033[0m'
fi

PASS=0
FAIL=0
SKIPPED=0

run_suite() {
    local name="$1"
    local cmd="$2"
    echo ""
    echo "=== ${name} ==="
    if eval "${cmd}"; then
        echo -e "${GREEN}  ✓ ${name} passed${NC}"
        PASS=$((PASS + 1))
    else
        echo -e "${RED}  ✗ ${name} FAILED${NC}"
        FAIL=$((FAIL + 1))
    fi
}

skip_suite() {
    local name="$1"
    local reason="$2"
    echo ""
    echo "=== ${name} ==="
    echo -e "${YELLOW}  ⊘ ${name} SKIPPED (${reason})${NC}"
    SKIPPED=$((SKIPPED + 1))
}

# 1. Manifest validator
run_suite "Manifest validator" "python3 tests/test_module_manifest.py"

# 2. JS syntax check
run_suite "JS syntax check" "python3 tests/test_js_syntax.py"

if [ "${SKIP_AGENT}" = "1" ]; then
    skip_suite "Agent unit tests" "--skip-agent"
    skip_suite "WS roundtrip" "--skip-agent"
else
    # Find the agent venv
    AGENT_VENV="${REPO_ROOT}/agent/.venv/Scripts/python.exe"
    if [ ! -f "${AGENT_VENV}" ]; then
        echo ""
        echo -e "${YELLOW}  ⚠ agent venv not found at ${AGENT_VENV}"
        echo "  Run: uv sync --project agent --all-extras"
        skip_suite "Agent unit tests" "agent venv missing"
        skip_suite "WS roundtrip" "agent venv missing"
    else
        # 3. Agent unit tests
        run_suite "Agent unit tests" "cd ${REPO_ROOT}/agent && .venv/Scripts/python.exe -m pytest tests/"

        # 4. WS roundtrip
        run_suite "WS roundtrip" "${AGENT_VENV} ${REPO_ROOT}/tests/test_ws_protocol.py"
    fi
fi

echo ""
echo "=========================================="
echo "  Test results:"
echo "    ${GREEN}passed:   ${PASS}${NC}"
if [ "${FAIL}" -gt 0 ]; then
    echo "    ${RED}failed:   ${FAIL}${NC}"
else
    echo "    failed:   ${FAIL}"
fi
if [ "${SKIPPED}" -gt 0 ]; then
    echo "    ${YELLOW}skipped:  ${SKIPPED}${NC}"
fi
echo "=========================================="

exit "${FAIL}"
