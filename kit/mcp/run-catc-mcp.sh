#!/usr/bin/env bash
# Official Catalyst Center MCP (Model Context Protocol) server, beta, from the CiscoSE API field guide.
# Run it on loopback only, with a read-only (Observer role) service account:
# the server adds no access control of its own, so RBAC on that account is the real limit.
#
#   export CATC_RELEASE=3.2.3     # branches today: 2.3.7.11, 3.1.6, 3.2.3 (git ls-remote to check)
#   export CATALYST_CENTER_HOST=https://catalyst-center.example.com
#   export CATALYST_CENTER_USERNAME=mcp-observer
#   export CATALYST_CENTER_PASSWORD='***'
#   ./run-catc-mcp.sh
set -euo pipefail
: "${CATC_RELEASE:?set CATC_RELEASE to the release branch suffix for your cluster}"
: "${CATALYST_CENTER_HOST:?}" "${CATALYST_CENTER_USERNAME:?}" "${CATALYST_CENTER_PASSWORD:?}"
export CATALYST_CENTER_VERIFY_SSL="${CATALYST_CENTER_VERIFY_SSL:-true}"   # the server's own default is false

[ -d catc-mcp-oss ] || git clone https://github.com/cisco-en-programmability/catc-mcp-oss
cd catc-mcp-oss
git fetch --all --quiet
git checkout "release/${CATC_RELEASE}" || { echo "No branch release/${CATC_RELEASE}. Available:"; git branch -r | grep release/; exit 1; }
docker build -t catalyst-center-mcp:local .
docker rm -f catalyst-center-mcp >/dev/null 2>&1 || true
docker run -d --name catalyst-center-mcp -p 127.0.0.1:7001:7001 \
  -e CATALYST_CENTER_HOST -e CATALYST_CENTER_USERNAME -e CATALYST_CENTER_PASSWORD \
  -e CATALYST_CENTER_VERIFY_SSL catalyst-center-mcp:local
sleep 5
curl -fsS http://localhost:7001/v1/health && echo " <- server up"
cat <<'JSON'
Cursor, VS Code or Codex: add this to the MCP client configuration
{"mcpServers": {"catalyst-center": {"url": "http://localhost:7001/v1/mcp"}}}

Claude Desktop connects to URL-based servers from Anthropic's cloud, so localhost will not
work there. Use the STDIO (standard input/output) configuration from the main-branch README.
JSON
