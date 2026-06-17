#!/usr/bin/env bash
# release.sh — build a Foundry VTT module release and publish it to GitHub.
#
# Usage:
#   ./release.sh <version>
#   ./release.sh 0.2.2
#
# What it does:
#   1. Bumps the version in foundry-module/module.json
#   2. Builds foundry-module/dist/fvtt-cc-generator-<version>.zip
#   3. Creates (or updates) a GitHub release with tag v<version>
#   4. Uploads the zip AND the module.json as separate assets
#      (Foundry needs both — see https://foundryvtt.com/article/manifest/)
#   5. Prints the install manifest URL the user should paste into Foundry
#
# Requirements:
#   - gh CLI OR curl + GITHUB_TOKEN env var
#   - The local git repo's "origin" remote must point at the GitHub repo
#
# This script is intentionally simple — it does NOT run the agent's
# tests, bump the Python agent's version, or push to main. The agent
# version is bumped separately (see agent/pyproject.toml).

set -euo pipefail

VERSION="${1:-}"
if [ -z "$VERSION" ]; then
  echo "Usage: $0 <version>"
  echo "  Example: $0 0.2.2"
  exit 1
fi

# Strip leading 'v' if present
VERSION="${VERSION#v}"
TAG="v${VERSION}"

REPO_ROOT="$(git rev-parse --show-toplevel)"
MODULE_DIR="${REPO_ROOT}/foundry-module"
DIST_DIR="${REPO_ROOT}/dist"
mkdir -p "${DIST_DIR}"

MODULE_JSON="${MODULE_DIR}/module.json"
ZIP_PATH="${DIST_DIR}/fvtt-cc-generator-${VERSION}.zip"

echo "=== Releasing ${TAG} ==="
echo "  module: ${MODULE_JSON}"
echo "  zip:    ${ZIP_PATH}"
echo ""

# Pre-release test gate. The release script refuses to publish if any
# test suite is failing. To bypass (e.g. for a docs-only release), pass
# --skip-tests.
if [ "${SKIP_TESTS:-0}" = "1" ]; then
    echo -e "  ⚠ test gate skipped (--skip-tests)"
else
    echo "  Running test gate..."
    if ! bash "${REPO_ROOT}/test-all.sh" --skip-agent; then
        echo "  ✗ pre-release test gate failed; aborting"
        exit 1
    fi
fi

# Detect repo from git remote
REMOTE_URL=$(git config --get remote.origin.url)
# e.g. https://github.com/owner/repo.git  or  git@github.com:owner/repo.git
REPO=$(echo "${REMOTE_URL}" | sed -E 's#.*github\.com[:/]([^/]+/[^/]+)\.git$#\1#')
echo "  repo:  ${REPO}"
echo ""

# Bump version in module.json (Python json is required for safe in-place edit)
python3 -c "
import json
p = '${MODULE_JSON}'
d = json.load(open(p))
d['version'] = '${VERSION}'
json.dump(d, open(p, 'w'), indent=2)
print(f'  Bumped module.json to ${VERSION}')
"

# Build the zip
python3 <<EOF
import zipfile
from pathlib import Path
source = Path('${MODULE_DIR}')
out = Path('${ZIP_PATH}')
if out.exists():
    out.unlink()
with zipfile.ZipFile(out, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for p in sorted(source.rglob('*')):
        if p.is_file():
            zf.write(p, p.relative_to(source).as_posix())
print(f'  Built: {out.name} ({out.stat().st_size:,} bytes)')
EOF

# Detect auth method
if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
  USE_GH=1
  echo "  auth:  gh CLI"
else
  USE_GH=0
  if [ -z "${GITHUB_TOKEN:-}" ]; then
    echo "ERROR: neither gh CLI auth nor GITHUB_TOKEN is available."
    echo "  Run: source ~/.hermes/skills/github/github-auth/scripts/gh-env.sh"
    echo "  or:  export GITHUB_TOKEN=<your-token>"
    exit 1
  fi
  echo "  auth:  GITHUB_TOKEN env var"
fi

# Create the release (idempotent: --draft flag prevents duplication; we
# publish at the end after assets are uploaded)
if [ "${USE_GH}" = "1" ]; then
  echo ""
  echo "=== Creating release ${TAG} ==="
  if gh release view "${TAG}" --repo "${REPO}" &>/dev/null; then
    echo "  Release ${TAG} already exists, will update assets"
  else
    gh release create "${TAG}" \
      --repo "${REPO}" \
      --title "${TAG} — Foundry module release" \
      --notes "Auto-published by ./release.sh" \
      --target main
  fi
else
  # curl-based: check if tag exists
  EXISTING=$(curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
    "https://api.github.com/repos/${REPO}/releases/tags/${TAG}" \
    | python3 -c "import sys, json; d = json.load(sys.stdin); print(d.get('id', ''))" 2>/dev/null || echo "")
  if [ -n "${EXISTING}" ]; then
    echo "  Release ${TAG} already exists (id=${EXISTING})"
    RID="${EXISTING}"
  else
    echo "  Creating release ${TAG} via API..."
    cat > /tmp/release-body-${VERSION}.json <<JSON
{
  "tag_name": "${TAG}",
  "target_commitish": "main",
  "name": "${TAG} — Foundry module release",
  "body": "Auto-published by ./release.sh",
  "draft": false,
  "prerelease": false
}
JSON
    RID=$(curl -s -X POST \
      -H "Authorization: token ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "Content-Type: application/json" \
      --data-binary @/tmp/release-body-${VERSION}.json \
      "https://api.github.com/repos/${REPO}/releases" \
      | python3 -c "import sys, json; print(json.load(sys.stdin)['id'])")
    echo "  Created release id=${RID}"
  fi
fi

# Upload assets. Note: GitHub will reject an upload with the same
# filename as an existing asset. We always try to delete the old
# asset first; if the token lacks delete scope (classic PAT), the
# user must remove it manually from the GitHub web UI.
UPLOAD_ASSET() {
  local filename="$1"
  local filepath="$2"
  local content_type="$3"
  if [ "${USE_GH}" = "1" ]; then
    gh release upload "${TAG}" "${filepath}" \
      --repo "${REPO}" \
      --clobber \
      || echo "  (clobber failed — try removing '${filename}' from ${TAG} manually)"
  else
    # Best-effort delete of any existing asset with the same name.
    # Note: classic PATs lack delete_repo scope, so this often fails
    # silently. The user will need to remove the old asset manually
    # in the GitHub web UI for the upload to succeed.
    ASSET_ID=$(curl -s -H "Authorization: token ${GITHUB_TOKEN}" \
      "https://api.github.com/repos/${REPO}/releases/${RID}/assets" \
      | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    for a in d:
        if a.get('name') == '${filename}':
            print(a['id'])
            break
except: pass" 2>/dev/null || true)
    if [ -n "${ASSET_ID}" ]; then
      echo "  Deleting old asset ${filename} (id=${ASSET_ID})"
      curl -s -X DELETE \
        -H "Authorization: token ${GITHUB_TOKEN}" \
        "https://api.github.com/repos/${REPO}/releases/assets/${ASSET_ID}" \
        > /dev/null || echo "  (delete failed — remove ${filename} manually from the GitHub web UI)"
    fi

    # Upload. Use a real temp file for the response (mktemp -t).
    RESP=$(mktemp -t fab-release-XXXXXX.json)
    HTTP_CODE=$(curl -s -o "${RESP}" -w "%{http_code}" -X POST \
      -H "Authorization: token ${GITHUB_TOKEN}" \
      -H "Accept: application/vnd.github+json" \
      -H "Content-Type: ${content_type}" \
      --data-binary "@${filepath}" \
      "https://uploads.github.com/repos/${REPO}/releases/${RID}/assets?name=${filename}")
    python3 -c "
import json, sys
d = json.load(open('${RESP}'))
if 'id' in d:
    print(f'  ✓ Uploaded: {d[\"name\"]} ({d[\"size\"]:,} bytes)')
    print(f'    URL: {d[\"browser_download_url\"]}')
else:
    print(f'  ✗ ERROR ({sys.argv[1]}): {d}')
    sys.exit(1)
" "${HTTP_CODE}" || true
    rm -f "${RESP}"
  fi
}

echo ""
echo "=== Uploading assets ==="
UPLOAD_ASSET "fvtt-cc-generator.zip" "${ZIP_PATH}" "application/zip"
UPLOAD_ASSET "module.json" "${MODULE_JSON}" "application/json"

echo ""
echo "=== Done ==="
echo "  Manifest URL: https://github.com/${REPO}/releases/latest/download/module.json"
echo "  Install: paste the manifest URL in Foundry's 'Add-on Modules > Install Module'"
