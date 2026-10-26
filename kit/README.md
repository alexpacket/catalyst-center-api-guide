# Catalyst Center API field guide: companion kit

Everything from https://catc-api.ciscose.com in one download, working offline.

| Path | What it is |
| --- | --- |
| `index.html` | The full field guide. One self-contained file: every diagram, step-through, the live simulation, the endpoint decision tree, the rate-limit calculator, the status-code picker, the deprecation lookup and the table filter all run locally. Open it in any modern browser. Without internet access the page falls back from Inter and JetBrains Mono to your system fonts; nothing else changes. |
| `client/catalyst_client.py` | Python client used by every example in the guide: token cache, one re-login on 401 (Unauthorized), back-off on 429 (Too Many Requests) and on 500/503 for reads only, task polling with `/tasks/{id}`, paging. Also a small CLI (command-line interface). |
| `postman/` | Postman collection and environment: authentication, inventory, Assurance (site health paged at 50, active issues), webhooks and notifications, and a full Command Runner round trip (find a reachable switch, POST, poll `/tasks/{id}`, read the fileId from the task detail, fetch the file). The collection logs in automatically. |
| `mcp/run-catc-mcp.sh` | Builds and runs the official Catalyst Center MCP (Model Context Protocol) server on loopback only, from the release branch you choose (2.3.7.11, 3.1.6 or 3.2.3). |
| `src/` | The generator for `index.html` (Python 3, no third-party packages). `python3 src/gen.py index.html` rebuilds the page. |

## Python client

```bash
pip install -r client/requirements.txt
export CATC_HOST=catc.example.com CATC_USER=svc-api CATC_PASS='***'
export CATC_VERIFY=true        # false only for lab clusters with self-signed certificates
python3 client/catalyst_client.py token
python3 client/catalyst_client.py count
python3 client/catalyst_client.py devices --family "Switches and Hubs"
python3 client/catalyst_client.py site-health
python3 client/catalyst_client.py cli --ip 10.0.0.1 --command "show version"
```

Use it as a library with `from catalyst_client import CatalystCenter`.
Use an account with the least privilege the job needs: Observer for reads.

## Postman

1. Import both files from `postman/`.
2. Select the **Catalyst Center (lab)** environment.
3. Set `baseUrl`, `username` and `password`.
4. Run the folders in order.
   - In folder 5, **Find a reachable switch** stores a `deviceId` for **Run show commands**.
   - Send **Poll task** until the status is SUCCESS, then **Task detail** stores the `fileId`.

## Before production use

- Payloads marked *illustrative* in the guide must be checked against the operation schema in your release.
- Verify every operation in **Platform > Developer Toolkit > APIs** on your own cluster.
- Respect the rate limits. They are set per operation and counted per client IP address; Cisco documents a default of 50 requests, and each operation's real limit is on its Features tab in Platform > Developer Toolkit > APIs.

Verified 26 Oct 2026. Baseline: Catalyst Center 3.2.3 (generally available), with 3.3.1 (controlled availability) and 2.3.7.x deltas.
