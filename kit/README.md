# Catalyst Center API field guide: companion kit

Everything from https://catc-api.ciscose.com in one download, working offline.

| Path | What it is |
| --- | --- |
| `index.html` | The full field guide. One self-contained file: every diagram, step-through, the live simulation, the endpoint decision tree, the rate-limit calculator, the status-code picker, the deprecation lookup and the table filter all run locally. Open it in any modern browser. Without internet access the page falls back from Inter and JetBrains Mono to your system fonts; nothing else changes. |
| `client/catalyst_client.py` | Python client used by every example in the guide: token cache, one re-login on 401 (Unauthorized), back-off on 429 (Too Many Requests) and 503, task polling, 1-based paging. Also a small CLI (command-line interface). |
| `postman/` | Postman collection and environment: authentication, inventory, Assurance, webhooks and a full Command Runner round trip (POST, poll the task, fetch the file). The collection logs in automatically. |
| `mcp/run-catc-mcp.sh` | Builds and runs the official Catalyst Center MCP (Model Context Protocol) server on loopback only. |
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
   - Run **Devices, first page** before **Run show commands**: it stores a `deviceId`.
   - **Poll task** stores the `fileId` once `endTime` is set.

## Before production use

- Payloads marked *illustrative* in the guide must be checked against the operation schema in your release.
- Verify every operation in **Platform > Developer Toolkit > APIs** on your own cluster.
- Respect the default rate limit of 50 calls per minute, which is shared by everything using the same account.

Verified 23 Oct 2026 against Catalyst Center 3.3.1, 3.2.x, 3.1.6 and 2.3.7.x documentation.
