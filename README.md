# Catalyst Center API field guide

CiscoSE field reference for customers integrating Cisco Catalyst Center (formerly DNA Center) with other systems through its APIs.

Live at **https://catc-api.ciscose.com** · Offline download: [catalyst-center-api-kit.zip](https://catc-api.ciscose.com/catalyst-center-api-kit.zip)

## What it covers

- How a call is served: controller stores vs. tasks that reach devices
- Authentication, RBAC (Role-Based Access Control), async tasks, pagination and rate limits
- Automation: sites and settings, inventory, templates, SWIM (Software Image Management), SD-Access fabric, wireless
- Assurance, events and webhooks, troubleshooting tools
- ITSM (IT Service Management) integration, six integration playbooks, and AI agents through MCP (Model Context Protocol)
- A live simulation of a day of API traffic and the shared rate limit, plus animated packet flows on every flow diagram
- Change prerequisites for fabric and non-fabric networks, compatibility matrix, 2.3.7.x and 3.2/3.3 deltas, deprecated APIs

Release baseline: Catalyst Center 3.3.1, with 3.1.6 and 2.3.7.x deltas. Verified 23 Oct 2026.

## Structure

| Path | Purpose |
|---|---|
| `index.html` | The published page (single self-contained file) |
| `src/gen.py` | Builds `index.html` from the content and diagram sources |
| `src/svg.py` | Diagram drawing (inline SVG) |
| `src/interactive.py` | Step-through data, widgets and page script |
| `src/anim.py` | Animated packet flows, play bars and the live simulation |
| `src/style.css` | SE-brand styles |
| `src/build_kit.py` | Rebuilds `index.html` and packages the companion kit |
| `kit/` | Companion kit sources: Python client, Postman collection, MCP run script |
| `catalyst-center-api-kit.zip` | The offline download (guide, client, collection, MCP script, generator) |
| `404.html`, `favicon.svg` | Site extras |
| `CNAME` | Custom domain for GitHub Pages |

## Rebuild

```bash
python3 src/gen.py         # writes index.html
python3 src/build_kit.py   # writes index.html and catalyst-center-api-kit.zip
```

Payload samples in the page are illustrative. Confirm field names in Platform > Developer Toolkit > APIs on your release before production use.
