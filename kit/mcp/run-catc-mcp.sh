#!/usr/bin/env bash
# Official Catalyst Center MCP (Model Context Protocol) server, beta, from the CiscoSE API field guide.
# Run it on loopback only, with a read-only (Observer role) service account:
# the server adds no access control of its own, so RBAC on that account is the real limit.
#
#   export CATC_RELEASE=<branch suffix from the repository README, matching your Catalyst Center release>
#   export CATALYST_CENTER_HOST=https://catalyst-center.example.com
#   export CATALYST_CENTER_USERNAME=mcp-observer
#   export CATALYST_CENTER_PASSWORD='***'
#   ./run-catc-mcp.sh
set -euo pipefail
: "${CATC_RELEASE:?set CATC_RELEASE to the release branch suffix for your cluster}"
: "${CATALYST_CENTER_HOST:?}" "${CATALYST_CENTER_USERNAME:?}" "${CATALYST_CENTER_PASSWORD:?}"
export CATALYST_CENTER_VERIFY_SSL="${CATALYST_CENTER_VERIFY_SSL:-true}"

[ -d catc-mcp-oss ] || git clone https://github.com/cisco-en-programmability/catc-mcp-oss
cd catc-mcp-oss
git fetch --all --quiet
git checkout "release/${CATC_RELEASE}"
docker build -t catalyst-center-mcp:local .
docker rm -f catalyst-center-mcp >/dev/null 2>&1 || true
docker run -d --name catalyst-center-mcp -p 127.0.0.1:7001:7001 \
  -e CATALYST_CENTER_HOST -e CATALYST_CENTER_USERNAME -e CATALYST_CENTER_PASSWORD \
  -e CATALYST_CENTER_VERIFY_SSL catalyst-center-mcp:local
sleep 5
curl -fsS http://localhost:7001/v1/health && echo " <- server up"
cat <<'JSON'
Add this to your MCP client configuration (for example Claude Desktop):
{"mcpServers": {"catalyst-center": {"url": "http://localhost:7001/v1/mcp"}}}
JSON
