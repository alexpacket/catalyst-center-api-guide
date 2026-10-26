import html, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from svg import *
from anim import sim_controls, sim_log, JS as AJS
from interactive import stepper, path_tool, rate_tool, choose_tool, code_tool, sym_tool, dep_tool, search_tool, data_script, JS as IJS

E = html.escape


def code(lang, src, title):
    return (f'<div class="code"><div class="code-h"><span>{E(title)}</span>'
            f'<button type="button" class="copy">Copy</button></div><pre><code>{E(src.strip())}</code></pre></div>')


FIGS = []
FIG_T = {0: "Integration directions", 1: "Where a call stops", 2: "Token authentication and re-authentication", 3: "Asynchronous task pattern",
         4: "Day-0 site build", 5: "SWIM upgrade wave", 6: "SD-Access fabric dependencies", 7: "Choosing the right data source",
         8: "Webhooks with hourly reconcile", 9: "Command Runner round trip", 10: "ServiceNow ITSM integration", 11: "MCP server trust boundary",
         12: "Retry decision by status code", 13: "Separating failures from filter or RBAC scope", 14: "Release and deprecation timeline"}
KIT = "https://catc-api.ciscose.com/catalyst-center-api-kit.zip"


def fig(svgs, num, cap, extra="", pre="", title=None):
    FIGS.append((num, title or FIG_T.get(num, cap.split(". ")[0])))
    return f'<figure class="fig" id="fig-{num}">{pre}<div class="fig-scroll">{svgs}</div>{extra}<figcaption><b>Figure {num}.</b> {cap}</figcaption></figure>'


def table(head, rows, cls="", tid=""):
    h = "".join(f"<th>{c}</th>" for c in head)
    r = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows)
    idattr = f' id="{tid}"' if tid else ""
    return f'<div class="tbl {cls}"><table{idattr}><thead><tr>{h}</tr></thead><tbody>{r}</tbody></table></div>'


def c(t):
    return f"<code>{E(t)}</code>"


def badge(kind):
    names = {"read": "Stops at the controller", "asr": "Stops at the controller", "dev": "Reaches the device", "write": "Writes config (async)"}
    return f'<span class="bdg bdg-{kind}">{names[kind]}</span>'


def steps(items):
    return '<ol class="chain">' + "".join(f"<li>{i}</li>" for i in items) + "</ol>"


def usewhen(yes, no):
    return ('<div class="uw"><div class="uw-y"><h4>Use when</h4><ul>' + "".join(f"<li>{x}</li>" for x in yes) +
            '</ul></div><div class="uw-n"><h4>Do not use</h4><ul>' + "".join(f"<li>{x}</li>" for x in no) + "</ul></div></div>")


NAV = [
    ("Foundations", [("overview", "Overview and interfaces"), ("stops", "Where a call stops"), ("auth", "Authentication and RBAC"),
                     ("mech", "Async, paging, limits")]),
    ("Automate", [("sites", "Sites and settings"), ("inventory", "Inventory and onboarding"), ("templates", "Templates and provisioning"),
                  ("swim", "Software images (SWIM)"), ("fabric", "Fabric vs non-fabric"), ("sda", "SD-Access fabric"), ("wireless", "Wireless")]),
    ("Observe", [("choose", "How to choose"), ("questions", "Questions to endpoints"), ("assurance", "Health, issues, events"),
                 ("events", "Webhooks"), ("tools", "Troubleshooting tools")]),
    ("Integrate", [("itsm", "ITSM and ServiceNow"), ("playbooks", "Integration playbooks"), ("mcp", "AI agents and MCP")]),
    ("Operate", [("prechange", "Change prerequisites"), ("compat", "Compatibility matrix"), ("errors", "Errors and resilience"),
                 ("delta237", "2.3.7.x to 3.x deltas"), ("changes", "Deprecated APIs"), ("tooling", "Tooling"), ("checklist", "Guidance checklist"),
                 ("figures", "Figure index"), ("sources", "Sources")]),
]

nav_html = ""
for part, items in NAV:
    nav_html += f'<p class="nav-part">{part}</p><ul>' + "".join(f'<li><a href="#{i}" data-part="{part}">{t}</a></li>' for i, t in items) + "</ul>"

PY_CLIENT = r'''
# catalyst_client.py: token cache, 401 re-auth, 429 backoff, task poller, pager
import json, time, requests
from requests.auth import HTTPBasicAuth

class CatalystCenter:
    def __init__(self, host, user, password, verify=True):
        self.base = f"https://{host}"
        self.s = requests.Session(); self.s.verify = verify
        self.auth = HTTPBasicAuth(user, password); self.exp = 0

    def _login(self):
        r = self.s.post(f"{self.base}/dna/system/api/v1/auth/token", auth=self.auth)
        r.raise_for_status()
        self.s.headers.update({"X-Auth-Token": r.json()["Token"],
                               "Content-Type": "application/json"})
        self.exp = time.time() + 55 * 60          # API reference: 60 min

    def call(self, method, path, **kw):
        if time.time() > self.exp:
            self._login()
        delay, relogged = 2, False
        for _ in range(6):
            r = self.s.request(method, self.base + path, **kw)
            if r.status_code == 401 and not relogged:
                self._login(); relogged = True; continue
            # 429 any method; 500/503 only for reads (a write may already have run)
            if r.status_code == 429 or (r.status_code in (500, 503) and method == "GET"):
                time.sleep(int(r.headers.get("Retry-After", delay)))
                delay = min(delay * 2, 60); continue
            r.raise_for_status()
            return r.json() if r.content else {}
        raise RuntimeError(f"gave up: {method} {path}")

    def wait_task(self, task_id, timeout=900, every=5):
        # GET /tasks/{id} (2.3.7.6+); the older /task/{taskId} is Sunset
        t0 = time.time()
        while time.time() - t0 < timeout:
            t = self.call("GET", f"/dna/intent/api/v1/tasks/{task_id}")["response"]
            if t.get("status") == "FAILURE":
                d = self.task_detail(task_id)
                raise RuntimeError(d.get("failureReason") or d.get("errorCode"))
            if t.get("status") == "SUCCESS":
                return t                           # endTime, resultLocation set
            time.sleep(every)                      # PENDING
        raise TimeoutError(task_id)

    def task_detail(self, task_id):              # progress, data, failureReason
        return self.call("GET", f"/dna/intent/api/v1/tasks/{task_id}/detail")["response"]

    def pages(self, path, params=None, limit=500, start=1):
        # Most list operations: 1-based offset, limit up to 500. Check each one:
        # site-health allows 50, some event operations start at 0.
        offset = start
        while True:
            rows = self.call("GET", path, params={**(params or {}),
                             "offset": offset, "limit": limit})["response"]
            yield from rows
            if len(rows) < limit:
                return
            offset += limit
'''

PY_CMD = r'''
cc = CatalystCenter("catc.example.com", "svc-api", "***")
ids = [d["id"] for d in cc.pages("/dna/intent/api/v1/network-device",
                                 {"platformId": "C9300-48P"})]
job = cc.call("POST", "/dna/intent/api/v1/network-device-poller/cli/read-request",
              json={"commands": ["show version", "show ip int brief"],
                    "deviceUuids": ids[:10], "timeout": 0})
task_id = job["response"]["taskId"]
cc.wait_task(task_id)
# Command Runner reports the output file in the task's progress text
file_id = json.loads(cc.task_detail(task_id)["progress"])["fileId"]
output = cc.call("GET", f"/dna/intent/api/v1/file/{file_id}")
'''

PY_EVENTS = r'''
# 1. Webhook destination. trustCert True skips certificate checks: lab only.
cc.call("POST", "/dna/intent/api/v1/event/webhook", json={
    "name": "noc-listener", "description": "NOC event intake",
    "url": "https://hooks.example.com/catc", "method": "POST",
    "trustCert": False})
# 2. The create call returns no ID: look the destination up by name
dest = cc.call("GET", "/dna/intent/api/v1/event/subscription-details/rest",
               params={"name": "noc-listener"})
instance_id = dest[0]["instanceId"]
# 3. Subscribe unreachable events (switch, router, WLC) to it
UNREACHABLE = ["NETWORK-NON-FABRIC_WIRED-1-200",      # switch unreachable
               "NETWORK-NON-FABRIC_WIRED-1-250",      # router unreachable
               "NETWORK-NON-FABRIC_WIRELESS-1-150"]   # WLC unreachable
cc.call("POST", "/dna/intent/api/v1/event/subscription/rest", json=[{
    "name": "network-device-unreachable",
    "subscriptionEndpoints": [{"instanceId": instance_id,
        "subscriptionDetails": {"connectorType": "REST"}}],
    "filter": {"eventIds": UNREACHABLE}}])

# Hourly reconcile: published notifications the listener may have missed
now_ms = int(time.time() * 1000)
missed = [n for eid in UNREACHABLE
          for n in cc.call("GET", "/dna/intent/api/v1/event/event-series",
                           params={"eventIds": eid, "startTime": now_ms - 3600000,
                                   "endTime": now_ms})]
'''

PY_SWIM = r'''
# 1. Devices behind the golden image for one site (2.3.7.9+)
outdated = list(cc.pages("/dna/intent/api/v1/networkDeviceImages",
                         {"networkDeviceImageStatus": "OUTDATED",
                          "siteId": SITE_ID, "sortBy": "id", "order": "asc"}))
# 2. Readiness: start each check, wait for it, keep only devices that pass
ready = []
for dev in outdated:
    t = cc.call("POST", f"/dna/intent/api/v1/networkDeviceImages/{dev['id']}/readinessChecks")
    cc.wait_task(t["response"]["taskId"])
    failed = cc.call("GET", "/dna/intent/api/v1/networkDeviceImages/validationResults",
                     params={"networkDeviceId": dev["id"], "operationType": "READINESS_CHECK",
                             "status": "FAILED"})["response"]
    if not failed:
        ready.append(dev["id"])
# 3. Distribute ahead of the window (build the body from your release's schema)
t = cc.call("POST", "/dna/intent/api/v1/networkDeviceImages/distribute/bulk", json=dist_body(ready))
cc.wait_task(t["response"]["taskId"], timeout=3600)
# 4. Maintenance window for the approved change (suppresses Assurance alerts)
cc.call("POST", "/dna/intent/api/v1/networkDeviceMaintenanceSchedules", json={
    "description": "CHG0012345 image upgrade", "networkDeviceIds": ready,
    "maintenanceSchedule": {"startTime": WINDOW_START_MS, "endTime": WINDOW_END_MS}})
# 5. Activate inside the window, then read post-check results
t = cc.call("POST", "/dna/intent/api/v1/networkDeviceImages/activate/bulk", json=act_body(ready))
cc.wait_task(t["response"]["taskId"], timeout=5400)
for dev_id in ready:
    post = cc.call("GET", "/dna/intent/api/v1/networkDeviceImages/validationResults",
                   params={"networkDeviceId": dev_id, "type": "POST_VALIDATION"})
'''

MCP_CFG = r'''
# Run the official server on loopback with a read-only (Observer) account
git clone https://github.com/cisco-en-programmability/catc-mcp-oss && cd catc-mcp-oss
git checkout release/3.2.3        # branches: release/2.3.7.11, release/3.1.6, release/3.2.3
export CATALYST_CENTER_HOST="https://catalyst-center.example.com"
export CATALYST_CENTER_USERNAME="mcp-observer"
export CATALYST_CENTER_PASSWORD="***"
export CATALYST_CENTER_VERIFY_SSL=true    # the server's default is false
docker build -t catalyst-center-mcp:local .
docker run --rm -p 127.0.0.1:7001:7001 -e CATALYST_CENTER_HOST \
  -e CATALYST_CENTER_USERNAME -e CATALYST_CENTER_PASSWORD \
  -e CATALYST_CENTER_VERIFY_SSL catalyst-center-mcp:local
curl http://localhost:7001/v1/health      # process up
# Cursor, VS Code, Codex: {"mcpServers": {"catalyst-center": {"url": "http://localhost:7001/v1/mcp"}}}
# Claude Desktop reaches URL servers from Anthropic's cloud, so localhost will not work:
# use the README's STDIO (standard input/output) form, which runs the container per session.
'''

S = []
A = S.append

# ---------------- FOUNDATIONS ----------------
A(f'''<section id="overview"><h2>Overview and the four interfaces</h2>
<p>Catalyst Center exposes a northbound REST (Representational State Transfer) API (application programming interface) over HTTPS (HTTP Secure) with JSON (JavaScript Object Notation) bodies, called the Intent API. Around it sit an eastbound event channel, a westbound ITSM (IT Service Management) integration, and a southbound multivendor SDK (Software Development Kit) that Cisco has deprecated. Every call goes to <code>https://&lt;cluster&gt;</code> plus a path prefix.</p>
{fig(fig_interfaces(), 0, "The three live integration directions. Third-party devices are now added to inventory over SNMP (Simple Network Management Protocol) MIB-II (Management Information Base II): they get reachability-based health, limited Assurance and topology icons, but no provisioning.")}
{table(["Prefix", "Serves", "Example"], [
    [c("/dna/intent/api/v1/ (v2)"), "Automation and inventory: sites, devices, provisioning, SD-Access, wireless, templates, events", c("GET /dna/intent/api/v1/network-device")],
    [c("/dna/data/api/v1/"), "Assurance analytics: query, count, trend, top-N, energy", c("POST /dna/data/api/v1/assuranceEvents/query")],
    [c("/dna/system/api/v1/ (v2)"), "Platform: authentication, users and roles, backup and restore, system upgrade", c("POST /dna/system/api/v1/auth/token")],
    [c("/dna/campus/api/v1/"), "Campus switch and wireless controller configuration and provisioning (3.2.3+); campus networks (3.3.1, controlled availability)", c("POST /dna/campus/api/v1/switches/configs/status") + ", " + c("GET /dna/campus/api/v1/networks")],
])}
<p class="note">Naming shifted in 2.3.7: older operations use hyphenated singular paths (<code>/network-device</code>); newer ones use camelCase collections with <code>/count</code> and <code>/query</code> siblings (<code>/networkDevices</code>, <code>/networkDevices/query</code>). Prefer the newer form; the older ones are the usual deprecation candidates.</p>
</section>''')

A(f'''<section id="stops"><h2>Where a call stops</h2>
<p>Most reads are answered from the controller's own stores and never touch a device. Writes and live CLI (command-line interface) queries become tasks, and only tasks reach devices. Cost, freshness and safety all follow from which path you hit.</p>
{fig(fig_stops(), 1, "A teaching model built from documented API behaviour; Cisco does not publish this as a single diagram. Solid paths are safe to schedule; the dashed amber path is on demand.", path_tool())}
<div class="cards">
  <div class="card c-read"><h4>Inventory and design database</h4><p>Sites, settings, devices, configuration archive. Paged with <code>offset</code>/<code>limit</code> (max 500).</p><p class="fresh">Freshness: last device sync. Periodic resync minimum is 6 hours from 3.1.5, plus event-driven updates.</p></div>
  <div class="card c-asr"><h4>Assurance data</h4><p>Health scores, issues, events, analytics. Intent health endpoints plus <code>/dna/data</code> query and trend operations.</p><p class="fresh">Freshness: telemetry ingest from devices (SNMP, syslog, NetFlow, streaming telemetry).</p></div>
  <div class="card c-write"><h4>Task engine</h4><p>Provisioning, SWIM (Software Image Management), discovery, Command Runner. Returns 202 with a <code>taskId</code>.</p><p class="fresh">Freshness: the result exists only once <code>endTime</code> is set.</p></div>
</div>
<h3 id="live">Live simulation: a day of API traffic</h3>
<p>The same three stores, running. Devices stream telemetry into Assurance without any API call. Your dashboard polls site health every five minutes, a CMDB (configuration management database) sync pages through inventory nightly, and webhooks leave the event engine without touching the API gateway. Rate limits are set per operation and counted per client IP address, so each operation has its own meter. Fire a 120-call bulk script at one operation to see that operation reject the overflow with HTTP 429 while the others keep working.</p>
{fig(fig_sim(), "1b", "Teaching simulation; timings are compressed and the limits are illustrative: read each operation's real limit on its Features tab. Limits are counted per client IP address, so two scripts on the same host share one budget per operation; some orchestration operations also cap concurrent runs cluster-wide.", sim_log(), pre=sim_controls(), title="Live simulation of a day of API traffic")}
</section>''')

A(f'''<section id="auth"><h2>Authentication and RBAC</h2>
<p>Authenticate once with HTTP Basic (RFC, Request for Comments, 7617), then send the returned JWT (JSON Web Token) in <code>X-Auth-Token</code> on every call for up to one hour. Every call is then checked against the caller's RBAC (Role-Based Access Control) role.</p>
{fig(fig_auth(), 2, "One login per hour. An expired token returns 401; re-authenticate once and retry. Step through to see each request and response.", stepper("f2"))}
{table(["Item", "Detail"], [
    ["Token endpoint", c("POST /dna/system/api/v1/auth/token") + " with Basic credentials; response " + c('{"Token": "..."}')],
    ["Header", c("X-Auth-Token: <token>") + " plus " + c("Content-Type: application/json")],
    ["Lifetime", "1 hour per the Authentication API specification. The Platform User Guides 3.1.x to 3.3.x (API prerequisites) state 60 seconds. Treat the lifetime as unreliable: cache the token, and re-authenticate on any 401."],
    ["Code previews", "Developer Toolkit generates code in Shell, Node, Python, Ruby, JavaScript, jQuery, PHP, Go and Ansible. Generated Python needs the " + c("requests") + " library."],
    ["Optional AES mode", "If enabled in system configuration, the Authorization header carries " + c("CSCO-AES-256 credentials=") + " followed by the Base64 encoding of username:password encrypted with the 256-bit AES (Advanced Encryption Standard) key, instead of Basic credentials."],
    ["RBAC", "Use RBAC v2 roles (" + c("/dna/system/api/v2/roles") + ") and access groups (" + c("/dna/system/api/v1/accessGroups") + ") from 3.1.5; v1 role operations are Sunset."],
    ["Getting a token for testing", "Platform &gt; Developer Toolkit &gt; Authentication &gt; Authentication API &gt; Try, or Postman / Bruno with Basic auth. Cisco's tech note sets the token once as a collection-level header."],
    ["Service accounts", "Cisco's lab examples use a SUPER-ADMIN-ROLE login; in production use one account per integration. OBSERVER-ROLE for read-only collectors and MCP (Model Context Protocol) servers; a narrow custom role for writers."],
    ["TLS (Transport Layer Security)", "Labs disable verification for self-signed certificates; in production import the cluster CA (Certificate Authority) and keep verification on."],
])}
{code("python", PY_CLIENT, "Python · minimal client used by every example in this guide")}
</section>''')

A(f'''<section id="mech"><h2>Async tasks, pagination, rate limits</h2>
<h3>Most writes are tasks</h3>
<p>A 202 Accepted means the request was queued, not that it worked. Poll <code>GET /dna/intent/api/v1/tasks/{{id}}</code> until <code>status</code> is <code>SUCCESS</code> or <code>FAILURE</code>; on failure read <code>failureReason</code> from <code>/tasks/{{id}}/detail</code>. The older <code>GET /task/{{taskId}}</code> (with <code>endTime</code> and <code>isError</code>) has been Sunset since 2.3.7.6; it still answers, and the 202 body's <code>url</code> still points at it. The legacy <code>/business/sda/...</code> APIs return <code>executionId</code> instead; poll <code>/dna/intent/api/v1/dnacaap/management/execution-status/{{executionId}}</code>. A few writes return a status URL or answer synchronously; read each operation's response.</p>
{fig(fig_async(), 3, "The asynchronous pattern. Command Runner reports its output fileId in the task's progress text; a configuration export points to its file through resultLocation.", stepper("f3"))}
<h3>Pagination and filtering</h3>
{table(["Rule", "Detail"], [
    ["Page size", c("limit") + " 1 to 500 on most list operations (devices, sites, SD-Access objects). Not a global rule: " + c("site-health") + " allows 50, audit logs 25, the interfaces query 1,000. Read each operation's limit."],
    ["Offset", c("offset") + " is 1-based on most list operations; some event-management operations start at 0. Loop until a page returns fewer than " + c("limit") + " rows."],
    ["Size first", "Call the matching " + c("/count") + " operation to size a job."],
    ["Complex filters", "Prefer " + c("POST …/query") + " operations for filters, sorting and aggregation."],
    ["Unstable site paging", "Before the 3.2.3 software maintenance update (SMU) 75346.100, repeated calls with the same limit and offset could return different site IDs (CSCwu68404, listed as resolved in the 3.2.3 release notes). On older builds, sort client-side and de-duplicate by ID; 3.3.1 adds " + c("sortBy") + " and " + c("order") + " to Get Sites."],
])}
<h3>Rate limits</h3>
{table(["Source", "What it says"], [
    ["OpenAPI specs on DevNet", "Per operation, and they vary widely: 10 per minute (roles), 50 (add fabric site), 100 (get sites), 1,000 (get tasks)"],
    ["Platform User Guides 3.1.x to 3.3.x", "\"The intent APIs have a default API rate limit of 50 requests\" (no time window stated). Policies set the number of calls per time interval per client IP address; per-operation limits are on the Features or Policies tab in Platform &gt; Developer Toolkit &gt; APIs"],
    ["Concurrency", "Some orchestration operations also allow only a set number of concurrent runs across the cluster (429 with " + c("REJECTED_ABOVE_MAX_CONCURRENCY_LIMIT") + ")"],
    ["Python SDK", "Waits and retries on 429 by default (" + c("CATALYST_CENTER_WAIT_ON_RATE_LIMIT") + ")"],
    ["Headers", "No rate-limit response headers are documented; observed 429 bodies name the operation and its limit. Treat 429 as normal and back off; honour " + c("Retry-After") + " if a response carries it."],
])}
{rate_tool()}
</section>''')

# ---------------- AUTOMATE ----------------
A(f'''<section id="sites"><h2>Sites and network settings {badge("write")}</h2>
<p>From 2.3.7.6 the site hierarchy and per-site settings moved to a new resource model (IP pools followed in 2.3.7.9). Build a site in five steps; the first three only change design intent in the controller, the last two reach devices.</p>
{fig(fig_site(), 4, "Day-0 site build. Each step returns a task to poll before the next one.")}
{table(["Endpoint", "Function", "Use case"], [
    [c("/dna/intent/api/v1/sites") + ", " + c("GET /sites/{id}") + " (3.1.6)", "Site hierarchy: areas, buildings, floors", "Site-as-code, CMDB location sync"],
    [c("GET /sites?nameHierarchy=Global/Area/Building") + ", then " + c("POST /dna/intent/api/v2/floors"), "Resolve the parent ID by name, then create the child (pattern from Cisco tech note 226435)", "Create floors under an existing building"],
    [c("PUT /sites/{id}/aaaSettings") + " (AAA: authentication, authorization and accounting), " + c("dnsSettings") + ", " + c("dhcpSettings") + ", " + c("ntpSettings") + ", " + c("timeZoneSettings") + ", " + c("bannerSettings") + ", " + c("telemetrySettings"), "Per-site network settings with inheritance (DNS, DHCP and NTP: Domain Name System, Dynamic Host Configuration Protocol, Network Time Protocol)", "Standard settings per region"],
    [c("PUT /sites/{id}/deviceCredentials") + ", then " + c("POST /dna/intent/api/v1/sites/deviceCredentials/apply") + " (body: " + c("deviceCredentialId") + " and " + c("siteId") + ", one credential per call); status at " + c("GET /sites/{id}/deviceCredentials/status"), "Credentials per site and sync to devices", "Credential rotation"],
    [c("POST /dna/intent/api/v1/networkDevices/assignToSite/apply"), "Assign devices to a site (returns 202)", "Place discovered devices before provisioning"],
    [c("/dna/intent/api/v1/globalCredentials") + " (3.1.6; replaces the older " + c("/v2/global-credential") + ")", "CLI, SNMP, NETCONF (Network Configuration Protocol) and HTTP credentials", "Vault-driven credential lifecycle"],
    [c("/ipam/globalIpAddressPools") + ", " + c("/ipam/siteIpAddressPools") + " (2.3.7.9+)", "Global pools and site subpools", "IPAM (IP Address Management) alignment"],
])}
</section>''')

A(f'''<section id="inventory"><h2>Inventory, discovery and onboarding {badge("read")} {badge("dev")}</h2>
<p>Inventory reads come from the controller database. Discovery, PnP (Plug and Play) claims and resyncs make the controller talk to devices.</p>
{table(["Endpoint", "Function", "Use case"], [
    [c("GET /dna/intent/api/v1/network-device"), "Device list with basic filters (classic)", "Quick lookups, Command Runner targeting"],
    [c("POST /dna/intent/api/v1/networkDevices/query") + " (2.3.7.9+)", "Device query with filters, views and paging (aggregation lives in " + c("/dna/data/api/v1/networkDevices/query") + ")", "CMDB sync, compliance reporting"],
    [c("POST /networkDevices") + ", " + c("PUT /networkDevices/{id}") + ", " + c("…/validateDevice") + " (3.1.6)", "Add, update and validate devices", "Brownfield onboarding"],
    [c("/dna/intent/api/v1/discoverys") + " (3.1.6)", "Discovery: create, edit, start jobs (" + c("POST /discoverys/{id}/jobs") + "), discovered devices. Replaces " + c("/discovery") + ", Sunset in 3.2.2", "Scan ranges, CDP (Cisco Discovery Protocol) or LLDP (Link Layer Discovery Protocol)"],
    ["PnP device, workflow and settings operations; " + c("/pnpNetworkDevices") + " (3.2.x)", "Zero-touch claim of new devices", "Greenfield branch and closet rollouts"],
    [c("PUT /networkDevices/resyncIntervalSettings"), "Global resync interval (360 to 1,440 minutes from 3.1.5; it was 25 minutes before)", "Do not lower; event-driven sync keeps data current"],
    ["Device Replacement operations", "RMA (Return Merchandise Authorization) workflow", "Swap a failed device with its config, image and license"],
])}
</section>''')

A(f'''<section id="templates"><h2>Templates and provisioning {badge("write")} {badge("dev")}</h2>
<p>Configuration templates (CLI or Velocity/Jinja) are the main way to push custom configuration in both fabric and non-fabric networks. The safe sequence is author, version, preview, then deploy.</p>
{steps(["Create a project and template in Template Programmer", "Commit a version (deployments use committed versions)", "Preview the rendered config for one device", "Deploy with the v2 operation and get a taskId (v1 returns a deploymentId)", "Poll the task (or the v1 deployment status), then run compliance"])}
{table(["Endpoint family", "Function"], [
    [c("GET /dna/intent/api/v2/template-programmer/project"), "Find projects and template IDs"],
    [c("POST /dna/intent/api/v2/template-programmer/template/deploy"), "Deploy a committed template; returns a " + c("taskId") + " to poll with " + c("/tasks/{id}") + " (the Python SDK uses v2 by default from 3.2.3)"],
    [c("POST /dna/intent/api/v1/template-programmer/template/deploy"), "Older deploy operation, still supported; returns a " + c("deploymentId")],
    [c("GET /dna/intent/api/v1/template-programmer/template/deploy/status/{deploymentId}"), "Poll a v1 deployment until it reports success or failure"],
    ["Network profiles and site assignment", "Bind templates to sites through profiles so new devices inherit them"],
    ["Wired and wireless provisioning operations", "Assign a device to a site and push the site's intent"],
])}
<p class="note amber">Track a v2 deployment with the task API and a v1 deployment with its own status endpoint; do not mix them. Template variables are usually filled from a CMDB or IPAM record. Keep templates idempotent and avoid lines that the controller's own intent also writes, or compliance will flag drift.</p>
</section>''')

A(f'''<section id="swim"><h2>Software images (SWIM) {badge("write")} {badge("dev")}</h2>
<p>The <code>networkDeviceImages</code> family (available from 2.3.7.9, the recommended path from 3.1.3) adds image status per device, readiness checks, custom validations and bulk operations. The v1 <code>image/distribution</code> and <code>image/activation/device</code> operations were marked Sunset in 3.1.3; they still answer but should not be used for new work.</p>
{fig(fig_swim(), 5, "An upgrade wave gated by change approval. Distribution and activation are separate tasks so activation can wait for the maintenance window.", stepper("f5"))}
{table(["Endpoint", "Function"], [
    [c("POST /dna/intent/api/v1/images/{id}/sites/{siteId}/tagGolden") + ", " + c("…/untagGolden") + " (2.3.7.9+)", "Mark the golden image per site and product (replaces " + c("/image/importation/golden") + ")"],
    [c("GET /dna/intent/api/v1/networkDeviceImages?networkDeviceImageStatus=OUTDATED") + ", " + c("/count"), "Devices not running the golden image (other statuses: UP_TO_DATE, UNKNOWN, CONFLICTED, UNSUPPORTED)"],
    [c("POST …/networkDeviceImages/{id}/readinessChecks"), "Pre-upgrade readiness for one device"],
    [c("…/networkDeviceImages/validations"), "Custom pre and post checks (show commands per product series)"],
    [c("POST …/distribute/bulk") + ", " + c("…/activate/bulk"), "Bulk distribute and activate; each returns a task"],
    [c("GET …/networkDeviceImages/validationResults"), "Readiness, pre and post validation results; filter by " + c("operationType") + " and " + c("status")],
    [c("GET /dna/intent/api/v1/networkDeviceImageUpdates?parentId={taskId}"), "Per-device progress of a distribution or activation"],
    [c("POST /dna/intent/api/v1/networkDeviceMaintenanceSchedules") + " (2.3.7.9+)", "Maintenance window: devices show " + c("UNDER_MAINTENANCE") + " and Assurance raises no alerts while they reload"],
    [c("/dna/intent/api/v1/productSeries"), "Product series that scope custom validations (golden tags are scoped by site and product name)"],
])}
{code("python", PY_SWIM, "Python · upgrade wave skeleton (dist_body and act_body follow your release's schema)")}
</section>''')

A(f'''<section id="fabric"><h2>Fabric vs non-fabric: same API?</h2>
<p>Yes for the platform, no for the overlay. Authentication, sites and settings, inventory, discovery, PnP, templates, SWIM, compliance, Assurance and events are the same operations in both. SD-Access adds its own domains for the fabric overlay, and wireless splits into a non-fabric and a fabric family.</p>
{table(["Area", "Non-fabric (traditional campus)", "SD-Access fabric"], [
    ["Platform, auth, RBAC, tasks", "Same", "Same"],
    ["Sites, settings, IP pools", "Same " + c("/sites") + " and " + c("/ipam") + " model", "Same, plus pools bound to virtual networks"],
    ["Inventory, discovery, PnP, SWIM, compliance", "Same", "Same"],
    ["Templates and intent", "Templates, or the wired intent APIs for Layer 2 features (" + c("/wired/networkDevices/{id}/configFeatures/intended/layer2") + ", 2.3.7.9+) and " + c("/dna/campus/api/v1/...") + " switch configuration (3.2.3+), for VLANs (virtual LANs), uplinks and policies", "Used for day-N extras; avoid lines the fabric intent owns"],
    ["Overlay and segmentation", "VLANs and ACLs (Access Control Lists)", c("/sda/fabricSites") + ", " + c("layer3VirtualNetworks") + ", " + c("anycastGateways") + ", " + c("fabricDevices") + ", " + c("transitNetworks") + ", " + c("portAssignments")],
    ["Underlay", "Your own design, often templates", "LAN Automation (" + c("/lan-automation") + ", v1 and v2; port channels at " + c("/lanAutomation/portChannels") + ") or manual underlay"],
    ["Wireless", "Wireless domain: SSIDs (Service Set Identifiers), wireless and RF (Radio Frequency) profiles, WLC (Wireless LAN Controller) provisioning", "Fabric Wireless domain: VLAN-to-SSID mapping (" + c("GET/PUT /sda/fabrics/{fabricId}/vlanToSsids") + ") on top of the wireless profiles"],
    ["Policy", "Application QoS (Quality of Service) policy", "Group-based policy with ISE (Identity Services Engine) scalable groups, plus application policy"],
    ["Assurance", "Device, client, application health", "Same, plus fabric-specific health and issues"],
])}
</section>''')

A(f'''<section id="sda"><h2>SD-Access fabric {badge("write")} {badge("dev")}</h2>
<p>Use the <code>/dna/intent/api/v1/sda/...</code> family. The older <code>/business/sda/...</code> operations (about 45: fabric, fabric site and zone, edge, border and control-plane devices, authentication profile, host onboarding, provisioning, transits, virtual networks, multicast) were deprecated in 2.3.7.9; they still answer with a Sunset banner. Every <code>/sda</code> write returns a task, and Cisco asks that they run one at a time: wait for each task before the next request.</p>
{fig(fig_sda(), 6, "What each fabric object needs before it can be created. Objects in the same column do not depend on each other. Border handoffs come last because they need both a border device and a transit.")}
{table(["Endpoint", "Function"], [
    [c("/sda/provisionDevices"), "Provision wired devices to their site; required before a device can take a fabric role"],
    [c("/sda/fabricSites") + ", " + c("/sda/fabricZones"), "Create, update, delete fabric sites (" + c("siteId") + ", " + c("authenticationProfileName") + ", " + c("isPubSubEnabled") + ") and fabric zones"],
    [c("/sda/authenticationProfiles"), "Read and update the fabric's authentication templates"],
    [c("/sda/layer3VirtualNetworks") + ", " + c("/sda/layer2VirtualNetworks"), "Layer 3 virtual networks (VRF-based segments; VRF: virtual routing and forwarding) and Layer 2 segments"],
    [c("/sda/anycastGateways"), "Anycast gateways: IP pool plus VN (virtual network) per fabric site"],
    [c("/sda/fabricDevices"), "Assign border, control-plane, edge and wireless controller roles; border BGP (Border Gateway Protocol) settings"],
    [c("/sda/transitNetworks"), "IP-based or SD-Access transits for multi-site"],
    [c("/sda/fabricDevices/layer3Handoffs/ipTransits") + ", " + c("…/sdaTransits") + ", " + c("…/layer2Handoffs"), "Border handoffs to a transit or a Layer 2 network"],
    [c("/sda/portAssignments") + ", " + c("/sda/portChannels"), "Host onboarding: put edge ports and port channels into a VN; without these no endpoint connects"],
    [c("/sda/fabrics/{fabricId}/vlanToSsids"), "Fabric wireless VLAN-to-SSID mapping (GET and PUT)"],
    [c("/sda/extranetPolicies") + ", " + c("/sda/multicast") + ", " + c("/sda/pendingFabricEvents"), "Shared services between VNs, multicast, and pending fabric changes to apply"],
    [c("/dna/intent/api/v1/trafficSteeringPolicys") + ", " + c("…Contracts") + " (3.1.6; Security API family)", "Security service insertion and traffic steering"],
])}
<p class="note">Before scripting a role, check that the fabric site's SD-Access compliance is clean; the controller checks devices against the SD-Access compatibility matrix (see <a href="#compat">Compatibility matrix</a>). Example from the matrix: C9350 in the edge role needs its control-plane node on IOS XE 17.18.5 and does not support IPv6.</p>
</section>''')

A(f'''<section id="wireless"><h2>Wireless {badge("write")}</h2>
{table(["Endpoint family", "Function"], [
    [c("/sites/{siteId}/wirelessSettings/ssids") + " (2.3.7.6+), " + c("…/ssids/{id}/update") + " (2.3.7.9+)", "Create SSIDs (Service Set Identifiers) at Global, override them per site. Replaces " + c("/enterprise-ssid") + " and " + c("/business/ssid") + ", deprecated in 2.3.7.6"],
    [c("/wirelessProfiles") + ", " + c("/wirelessSettings/rfProfiles"), "Wireless profiles (SSIDs per profile) and RF (radio frequency) profiles; replace " + c("/wireless/profile") + " and " + c("/wireless/rf-profile")],
    [c("POST /networkProfilesForSites/{profileId}/siteAssignments"), "Assign a wireless profile to sites"],
    [c("/wirelessSettings/dot11beProfiles"), "802.11be (Wi-Fi 7) profiles; MLO (Multi-Link Operation) settings changed in 3.1.6"],
    [c("POST /wirelessControllers/{deviceId}/provision"), "Provision a WLC (Wireless LAN Controller); 3.1.6 adds LSC (Locally Significant Certificate) parameters. Replaces " + c("/wireless/provision")],
    [c("POST /wirelessAccessPoints/provision"), "Provision access points (APs) to their floor and controller; a separate step after the WLC"],
    [c("/wirelessAccessPoints/configurations") + " (3.2.x)", "AP configuration; replaces " + c("/wireless/accesspoint-configuration") + ", deprecated in 3.2.2"],
    [c("/wirelessSettings/certificateRenewalProfiles") + " (3.1.6)", "LSC renewal profiles for access points"],
    [c("GET /wirelessControllers/{deviceId}/siteTags") + " (3.1.6)", "Site tags on a controller"],
])}
<p class="note">Order: SSIDs, then wireless and RF profiles, then site assignment, then WLC provisioning, then AP provisioning. In 3.1.6 and 2.3.7.11, the 802.11be <code>ofdmaDownLink</code>, <code>ofdmaUpLink</code>, <code>muMimoDownLink</code> and <code>muMimoUpLink</code> parameters (OFDMA: Orthogonal Frequency-Division Multiple Access; MU-MIMO: multi-user multiple-input multiple-output) are ignored on IOS XE 17.18.2 and later. 3.3.1 removed unused attributes, including Layer 2 VTP (VLAN Trunking Protocol), from the wireless PDC and MDC API operations (Cisco does not expand these names); retest wireless automation after upgrading.</p>
</section>''')

# ---------------- OBSERVE ----------------
A(f'''<section id="choose"><h2>How to choose</h2>
<p>Pick the API family by the question, not by the endpoint you already know.</p>
{choose_tool()}
{fig(fig_choose(), 7, "Fleet-wide and historical questions stay on the controller; only the one-device-now case reaches a device.")}
</section>''')

A(f'''<section id="questions"><h2>Customer questions to endpoints</h2>
<p>NOC (network operations center), helpdesk and security teams ask in business terms. This table maps the question to the scalable endpoint and to the heavier troubleshooting-only alternative.</p>
{search_tool()}
{table(["Question", "Scalable endpoint (safe to schedule)", "Troubleshooting only"], [
    ["What devices do we have, and are they reachable?", c("POST /dna/intent/api/v1/networkDevices/query") + " (2.3.7.9+; request the RESYNC view for " + c("reachabilityStatus") + ")", "—"],
    ["How healthy is each site?", c("GET /dna/intent/api/v1/site-health") + " (50 per page; areas and buildings paged separately)", "—"],
    ["How healthy is each device tier?", c("GET /dna/intent/api/v1/network-health"), "Command Runner on one device"],
    ["How are clients doing?", c("GET /dna/intent/api/v1/client-health"), c("GET /client-detail?macAddress=")],
    ["What issues are open, and where?", c("GET /dna/data/api/v1/assuranceIssues?status=active") + " or " + c("POST …/assuranceIssues/query") + " (2.3.7.6+; " + c("GET /dna/intent/api/v1/issues") + " is deprecated in 3.2.2)", "—"],
    ["What happened on these devices in the last 24 hours?", c("POST /dna/data/api/v1/assuranceEvents/query") + " (one device family per call, 7-day maximum window)", "—"],
    ["Which devices are exposed to a PSIRT (Product Security Incident Response Team) advisory?", c("GET /securityAdvisories/results/networkDevices") + " (2.3.7.9+)", "—"],
    ["Which devices are out of compliance, and why?", c("GET /compliance") + " + " + c("/compliance/networkDevices/{id}/detail/policys") + " (3.1.5+)", "—"],
    ["Which devices are not on the golden image?", c("GET /networkDeviceImages?networkDeviceImageStatus=OUTDATED") + " (2.3.7.9+)", "—"],
    ["What did the config look like last week?", c("GET /networkDeviceConfigFiles") + " (2.3.7.9+)", "—"],
    ["What does this device show right now?", "—", c("POST /network-device-poller/cli/read-request")],
    ["Why can host A not reach host B?", "—", "Path Trace (" + c("/pathTraces") + " from 3.2.2; " + c("/flow-analysis") + " before)"],
    ["How much power is the network using?", c("/dna/data/api/v1/energy/...") + " (3.1.3)", "—"],
], tid="qtable")}
<p class="note">Push beats poll: subscribe to issue and event webhooks instead of looping on an issues query.</p>
</section>''')

A(f'''<section id="assurance"><h2>Health, issues and Assurance events {badge("asr")}</h2>
{table(["Endpoint", "Returns", "Use case"], [
    [c("GET /site-health") + ", " + c("/network-health") + ", " + c("/client-health"), "Health scores by site, device tier, client type", "NOC dashboards, every 5 to 15 minutes"],
    [c("/dna/data/api/v1/assuranceIssues") + " (GET, " + c("/query") + ", " + c("/count") + "); custom issue definitions", "Issues with priority, status and site; " + c("GET /dna/intent/api/v1/issues") + " is deprecated in 3.2.2", "Ticketing, triage queues"],
    [c("/dna/data/api/v1/assuranceEvents") + ", " + c("/count") + ", " + c("/query"), "Raw syslog, trap and device events for one device or client family (" + c("deviceFamily") + " required, times in epoch milliseconds)", "Forensics on a device or client"],
    ["GET or POST " + c("/dna/data/api/v1/…/trendAnalytics") + ", " + c("summaryAnalytics") + " (method varies by resource)", "Server-side aggregation over time", "SLA (service-level agreement) and capacity reports"],
    [c("/dna/intent/api/v2/…-enrichment-details") + " (2.3.7.10)", "Device, client, user, issue context in one call", "Ticket enrichment"],
    [c("/dna/data/api/v1/thousandEyesTestResults") + " (3.1.3)", "ThousandEyes test results and trends", "Application experience reports"],
])}
</section>''')

A(f'''<section id="events"><h2>Events and webhooks {badge("asr")}</h2>
<p>When a subscribed event fires, Catalyst Center makes an HTTP POST or PUT to your listener with a JSON payload. Destinations can be REST webhook, email, syslog or SNMP trap, each with its own API; Webex and ITSM destinations are set up in the UI (user interface). Event definitions are fixed and cannot be edited.</p>
{fig(fig_webhook(), 8, "Webhooks are the primary path; an hourly query of published notifications reconciles anything missed.", stepper("f8"))}
{code("python", PY_EVENTS, "Python · register a webhook, subscribe, reconcile")}
<p class="note">Cisco's stated practice: confirm HTTP/HTTPS reachability from the cluster to your listener before subscribing. An HTTP/S proxy can be set for outbound notifications. Keep <code>trustCert</code> false so the controller verifies your listener's certificate; true is for lab listeners with self-signed certificates. The unreachable event IDs above come from Cisco's Event Catalog (Platform &gt; Developer Toolkit &gt; Event Notifications); third-party devices use <code>NETWORK-NON-FABRIC_WIRED-1-273</code>.</p>
</section>''')

A(f'''<section id="tools"><h2>Troubleshooting tools {badge("dev")}</h2>
<p>Command Runner runs read-only CLI commands on a list of devices; the allowed command keywords are listed by <code>GET /network-device-poller/cli/legit-reads</code>. Path Trace (<code>POST /pathTraces</code> from 3.2.2; <code>/flow-analysis</code>, deprecated in the 3.2.x API specification, on earlier releases) analyses the path between two endpoints. Both are tasks that reach devices: run them on demand for a handful of devices or one flow, never on a schedule.</p>
{fig(fig_cmdrunner(), 9, "Command Runner round trip. The output lands in a file you fetch by fileId.", stepper("f9"))}
{code("python", PY_CMD, "Python · Command Runner (timeout is in seconds; 0 uses the default)")}
{usewhen(["An engineer is investigating one device or a handful", "Cached inventory or Assurance data cannot answer the question"],
         ["On a timer, in a loop, or across the whole fleet", "For configuration changes (Command Runner is read-only)"])}
</section>''')

# ---------------- INTEGRATE ----------------
A(f'''<section id="itsm"><h2>ITSM and ServiceNow</h2>
<p>ITSM integration ships as pre-built bundles configured in the GUI (graphical user interface). Prerequisites on the ServiceNow side: the Cisco Catalyst app from the ServiceNow Store and a MID (Management, Instrumentation and Discovery) server. Then add the ITSM instance at System &gt; Settings &gt; Destinations &gt; ITSM, test connectivity, and enable bundles under Platform &gt; Manage &gt; Bundles.</p>
{fig(fig_itsm(), 10, "Events land in a ServiceNow import set table (inventory in its own table); transform maps route them by type; the Cisco Catalyst app (formerly Cisco DNA app) calls back for enrichment.")}
{table(["Bundle (Platform User Guide name)", "What it does"], [
    ["Basic ITSM (ServiceNow) CMDB synchronization", "Triggers or schedules a one-way sync of Catalyst Center devices into ServiceNow CMDB CIs (configuration items)"],
    ["REST API", "The Intent API bundle itself: query network knowledge and start network programming"],
    ["Network Issue Monitor and Enrichment for ITSM (ServiceNow)", "Publishes Assurance and maintenance issues to ServiceNow, with APIs for network context"],
    ["Automation events for ITSM (ServiceNow)", "Publishes events that need software image updates, provisioning or other operational action"],
    ["Endpoint Attribute Retrieval with ITSM (ServiceNow)", "Retrieves endpoint details from ServiceNow into Catalyst Center, once or on a schedule"],
    ["Rogue and aWIPS", "Rogue management and aWIPS (adaptive Wireless Intrusion Prevention System) APIs; needs the Rogue and aWIPS package"],
])}
<p class="note">Platform &gt; Runtime Dashboard shows API and event activity for the integration flows; its API summary covers the ServiceNow bundles. For inventory, "Post device inventory details to a staging table" writes to a ServiceNow staging table instead of the CMDB; events can also go to a generic REST endpoint for your own scripts.</p>
</section>''')

PB = [
    ("ITSM incident with context", "ServiceNow, Jira Service Management",
     ["Issue or event webhook", "ITSM creates the incident", "ITSM calls " + c("/v2/device-enrichment-details") + " and client/issue variants (2.3.7.10+; v1 on older releases)", "Engineer works the ticket", "Resolve issue in Catalyst Center"],
     ["Turning Assurance issues into tickets with device and client context"], ["Polling an issues query every minute"]),
    ("CMDB and asset sync", "ServiceNow CMDB, NetBox",
     ["Nightly " + c("/networkDevices/query") + " with " + c("/count") + " (2.3.7.9+)", "Page at 500", "Enrich with EoX (end-of-sale, end-of-support and end-of-life) and license data", "Upsert into the CMDB", "Events for changes between runs"],
     ["The inventory of record lives outside Catalyst Center"], ["Real-time asset changes; use events"]),
    ("IPAM alignment", "Infoblox, BlueCat, other IPAM",
     ["Read " + c("/ipam/globalIpAddressPools"), "Reconcile with IPAM blocks", "Create site subpools with " + c("/ipam/siteIpAddressPools"), "Or configure Catalyst Center to use the external IPAM"],
     ["Address plans are owned centrally"], ["The Sunset " + c("reserve-ip-subpool") + " operations"]),
    ("Security posture report", "SIEM (Security Information and Event Management), GRC (Governance, Risk and Compliance)",
     [c("securityAdvisories") + " results", c("fieldNotices") + " and " + c("networkBugs") + " results", c("compliance") + " status", "Weekly report or SIEM feed"],
     ["Weekly risk and audit reporting"], ["Triggering scans in a tight loop"]),
    ("Upgrade pipeline", "CI/CD (Continuous Integration / Continuous Delivery), change management",
     ["Images marked golden; " + c("OUTDATED") + " devices listed", "Readiness checks pass", "Change approval and maintenance schedule", c("distribute/bulk") + ", then " + c("activate/bulk") + " in the window (2.3.7.9+)", "Validation results attached to the change"],
     ["Planned SWIM waves with pre and post checks"], ["v1 " + c("image/distribution") + " and " + c("image/activation/device")]),
    ("Day-0 site as code", "Terraform, Ansible, GitOps",
     [c("/sites") + " hierarchy", c("/sites/{id}/…Settings"), "IP pools", "Discovery (" + c("/discoverys") + ", 3.1.6+) or PnP (Plug and Play)", "Provision; SD-Access: " + c("/sda/...")],
     ["New sites from version-controlled definitions"], ["Legacy " + c("/site") + ", " + c("/discovery") + " and " + c("/business/sda") + " paths"]),
]
pb_html = ""
for t, other, st, y, n in PB:
    pb_html += f'<article class="pb"><h3>{t}</h3><p class="pb-o">Other system: {other}</p>{steps(st)}{usewhen(y, n)}</article>'
A(f'''<section id="playbooks"><h2>Integration playbooks</h2>
<p>Six patterns cover most customer integrations. Each lists the flow in order and the most expensive mistake to avoid.</p>
<div class="pbs">{pb_html}</div>
</section>''')

A(f'''<section id="mcp"><h2>AI agents and MCP</h2>
<p>Cisco's open-source Catalyst Center MCP (Model Context Protocol) server, in beta since August 2026, lets any MCP-capable AI client call generated Catalyst Center API tools. The server runs inside your network; the data stays inside only if the AI client and its model do too, so pair it with a private model where that matters.</p>
{fig(fig_mcp(), 11, "The MCP server authenticates as one account and adds no access control. RBAC on that account is the real limit.")}
<h3>When to use MCP vs the AI Assistant</h3>
<p>Cisco's rule: use the in-product AI Assistant when the work starts in the Cisco product; use MCP when the work starts in a workflow you are building around it, such as a helpdesk tool, self-service portal, cross-vendor copilot, automated report or custom agent.</p>
{table(["Use case", "Who benefits", "Example request"], [
    ["Ticket triage with network evidence", "L1 (first-line) helpdesk", "Is this one user, access point or location? Is the AP healthy? What belongs in the ticket?"],
    ["End-user self-service", "Employees", "Check my Wi-Fi connection before I open a case"],
    ["Inventory and health review", "NOC", "Summarize health for Global/San Jose; group POOR devices by role"],
    ["Wireless experience investigation", "Wireless team", "Worst APs, SSIDs and clients at HQ over 24 hours, and next checks"],
    ["Software and compliance risk review", "Security and operations", "Compliance issues, advisories, field notices, prioritized. Do not make any changes."],
    ["Cross-domain copilot", "Platform teams", "Combine Catalyst Center with Meraki, ITSM or other MCP servers in one agent"],
])}
<h3>MCP best practices</h3>
<ol class="rules">
<li><b>It is not read-only by design.</b> The README states the server adds no authorization layer and does not enforce read-only. The tool catalogs are mostly reads, but some include POST operations (the 2.3.7.11 bundle includes compliance remediation, which changes device configuration). Enforce read-only with an Observer-role account.</li>
<li><b>One dedicated, least-privilege account</b> per deployment. Treat every connected client as able to call anything that account can.</li>
<li><b>Keep the endpoint private.</b> Bind to 127.0.0.1; if shared, put it behind your gateway with authentication and TLS.</li>
<li><b>Turn certificate verification on</b> (<code>CATALYST_CENTER_VERIFY_SSL=true</code>): the server's default is off, and the repository's compose file binds port 7001 on all interfaces, so do not use it as-is.</li>
<li><b>Match the release branch to the controller</b>: <code>release/2.3.7.11</code>, <code>release/3.1.6</code> and <code>release/3.2.3</code> exist today. Rebuild after each controller upgrade; <code>/v1/readiness</code> checks the configuration.</li>
<li><b>State the safety boundary in prompts</b> ("read-only, do not change anything"). It is a backstop, not a control.</li>
<li><b>Mind rate limits.</b> Agents chain many calls; the same per-operation limits and 500-row pages apply.</li>
<li><b>Choose the model deliberately.</b> For regulated or air-gapped sites, pair the local server with an approved private model.</li>
<li><b>Log tool calls on your side.</b> The controller sees only one service account.</li>
<li><b>Beta can change.</b> Pin a commit and retest on updates.</li>
</ol>
{code("bash", MCP_CFG, "Shell · run the official MCP server")}
<p class="note">Claude Desktop connects to URL-based MCP servers from Anthropic's cloud, so a <code>localhost</code> URL cannot work there. Use the repository README's STDIO (standard input/output) configuration for Claude Desktop, and the URL form for Cursor, VS Code or Codex.</p>
<p class="note">Companion: the DevNet Content Search MCP (<code>https://devnet.cisco.com/v1/foundation-search-mcp/mcp</code>) searches Catalyst Center and Meraki API documentation; it has no live network data. Community MCP servers exist but are not Cisco-supported.</p>
</section>''')

# ---------------- OPERATE ----------------
A(f'''<section id="prechange"><h2>Change prerequisites: fabric and non-fabric</h2>
<p>Most failed API changes trace back to a device that was not in a clean state before the change. Gate every automated change on the checks below. Items marked "practice" are general engineering practice; the rest map to documented Catalyst Center features.</p>
<h3>Before any change (both)</h3>
{table(["Check", "How", "Why"], [
    ["Controller backup is recent", c("GET /dna/system/api/v1/backups") + " (3.1.3+)", "Rollback point for the controller itself"],
    ["Device config archived", c("GET /networkDeviceConfigFiles") + " for target devices", "Known-good config to compare and restore"],
    ["Devices managed and reachable (run before the window opens)", c("POST /dna/intent/api/v1/networkDevices/query") + ": " + c("managementState = MANAGED") + ", " + c("reachabilityStatus = REACHABLE"), "Tasks against unmanaged or unreachable devices fail or hang; inside a maintenance window devices show " + c("UNDER_MAINTENANCE")],
    ["No open critical issues on targets", c("GET /dna/data/api/v1/assuranceIssues") + " with site or device, " + c("priority=P1") + " and " + c("status=active"), "Do not change a device that is already degraded"],
    ["Compliance is clean or understood", c("GET /compliance") + " for targets", "Separates new drift from existing drift"],
    ["Release and device are supported", "Compatibility matrix and, for fabric sites, SD-Access compliance (next section)", "Unsupported combinations are flagged and can fail provisioning"],
    ["Pre-checks captured", "Network validation workflows (" + c("/diagnosticValidationWorkflows") + ") or SWIM custom validations", "Before/after comparison"],
    ["Change approved, window set", "ITSM change; " + c("POST /dna/intent/api/v1/networkDeviceMaintenanceSchedules") + " (2.3.7.9+)", "Practice: approval and audit trail; the schedule suppresses Assurance alerts during reloads"],
    ["Right account", "Narrow RBAC role scoped by access group", "Limits blast radius of a script error"],
    ["Pilot first", "One site or a few devices, then waves", "Practice"],
])}
<h3>Additional checks for SD-Access</h3>
{table(["Check", "Why"], [
    ["ISE (Identity Services Engine) integration healthy and trusted: " + c("GET /ise-integration-status") + ", " + c("GET /authentication-policy-servers"), "Fabric sites, authentication profiles and group-based policy depend on it"],
    ["Underlay ready: routing, MTU (maximum transmission unit) and loopbacks (LAN Automation or manual)", "Fabric overlay rides on a working underlay"],
    ["Devices provisioned to their site (" + c("/sda/provisionDevices") + ")", "A device needs provisioning before it can take a fabric role"],
    ["IP pools reserved at the site and mapped to the right virtual network", "Anycast gateways need pool plus VN"],
    ["Fabric site's SD-Access compliance is clean for your release and IOS XE version", "The controller checks roles against the SD-Access compatibility matrix"],
    ["Create objects in dependency order: site, then VNs and gateways; site, then devices; transits; handoffs last", "Gateways need the site and VN, devices need the site, border handoffs need a device and a transit (Figure 6)"],
    ["Wait for each task or execution status before the next call", "Fabric operations are orchestrated and long-running"],
    ["Avoid template lines that overlap fabric-owned config", "Templates and fabric intent will fight; compliance flags drift"],
])}
<h3>Additional checks for non-fabric</h3>
{table(["Check", "Why"], [
    ["Templates committed, versioned and previewed for one device", "Catches variable and syntax errors before scale"],
    ["Network profile binds the template to the right sites", "New devices inherit the right config"],
    ["VLAN, trunk and uplink changes staged to avoid cutting management access", "Practice: a bad uplink change strands the device"],
    ["Wireless: SSIDs, profiles, site assignment, WLC provisioning, then AP provisioning; retest after upgrades", "Wireless field changes in 3.1.6, 2.3.7.11 and 3.3.1"],
])}
<h3>After the change (both)</h3>
{steps(["Task or execution status succeeded", "Post-checks or validation results match pre-checks", "Run compliance on targets", "Site and device health unchanged or better", "Close the change with evidence"])}
</section>''')

A(f'''<section id="compat"><h2>Compatibility matrix</h2>
<p>Cisco publishes two matrices. The Catalyst Center compatibility matrix lists which devices each release supports, with an SD-Access mode and a Non-Fabric mode, filters by device role (ISE, fabric edge, border and control plane, wireless, extended node) and an upgrade-path view. The SD-Access compatibility matrix is what the controller itself uses: Catalyst Center downloads it daily and shows mismatches in each fabric site's SD-Access compliance. Neither is an API.</p>
{table(["What it tells an integrator", "How to use it"], [
    ["Whether a device model supports a fabric role on a given release", "Check before scripting " + c("/sda/fabricDevices") + " assignments"],
    ["Supported upgrade paths between Catalyst Center releases", "Plan controller upgrades, then re-test integrations against the target release"],
    ["Devices at Last Day of Support (LDoS) are removed", "Those devices lose TAC (Technical Assistance Center) support; exclude them from automation scope"],
    ["Third-party devices (RFC 1213 SNMP MIB-II) monitored from 2.3.7.x", "Visibility only; no provisioning API for them"],
    ["EoX (end-of-sale, end-of-support, end-of-life) scanning from 2.3.3.x for connected customers", "Use the in-product EoX data for lifecycle reports"],
    ["Platform caveats, e.g. C9350 edge needs control plane on IOS XE 17.18.5, no IPv6", "Encode as pre-checks in fabric automation"],
])}
<p class="note">Gate fabric automation on the fabric site's SD-Access compliance rather than your own copy of the matrix. Keep "SD-Access image compatibility checks" enabled (System &gt; Settings &gt; SD-Access Compatibility Matrix); the JSON download is for air-gapped clusters, which upload it by hand. Recommended device software versions come from the Cisco Software Download page.</p>
</section>''')

A(f'''<section id="errors"><h2>Errors and resilience</h2>
{code_tool()}
{fig(fig_retry(), 12, "Retry 401 once and 429 with back-off. Retry 500 and 503 only for reads; for a write, check whether the task or object already exists before resending. Surface other 4xx client errors immediately. Pick a status code above to highlight its branch.")}
{sym_tool()}
{fig(fig_tree(), 13, "When a task fails or a list comes back empty, separate a real failure from a filter or RBAC scope problem before touching code.")}
{table(["Symptom", "Likely cause", "Fix"], [
    ["202 but nothing changed", "Task failed", "Read " + c("failureReason") + " from " + c("/tasks/{id}/detail")],
    ["401 mid-run", "Token expired after 60 minutes", "Cache the token, re-authenticate once"],
    ["403 with a valid token", "RBAC role or access group lacks the feature or site", "Adjust the service account role"],
    ["429", "Per-operation rate limit (per client IP address) or a concurrency cap", "Back off 2 s to 60 s; serialize writes"],
    ["Empty list", "Wrong filter, wrong offset base, RBAC scope", "Offset starts at 1 on most operations; check access groups"],
    ["Different rows on the same page", "Unstable site paging before 3.2.3 SMU 75346.100 (CSCwu68404)", "Sort client-side, de-duplicate by ID"],
    ["Inventory looks stale", "Resync is 6 hours minimum", "Trust event-driven sync; do not force resync loops"],
])}
</section>''')

A(f'''<section id="delta237"><h2>2.3.7.x to 3.x deltas</h2>
<p>2.3.7.x is the long-lived train many customers still run. Its latest release is 2.3.7.11 (March 2026; recommended build 2.3.7.11.71047.100). Cisco ends software maintenance for 2.3.7.x on 17 December 2026, and the last date of support is 17 June 2027, so plan the move to 3.x now. An integration written on 2.3.7.x keeps working on 3.x except where it uses deprecated operations; the gains in 3.x are mostly new API families.</p>
{table(["Capability", "2.3.7.x", "3.1.x and later", "Action when upgrading"], [
    ["Sites and per-site settings (" + c("/sites") + ", " + c("…Settings") + ")", "Yes, from 2.3.7.6", "Yes; " + c("GET /sites/{id}") + " added in 3.1.6", "Move off legacy " + c("/site")],
    ["IPAM pools (" + c("/ipam/...") + ")", "Yes, from 2.3.7.9", "Yes; overlapping pools in 3.1.5", "Move off " + c("reserve-ip-subpool") + " and " + c("global-pool")],
    ["SD-Access " + c("/sda/...") + " family", "Yes", "Yes; traffic steering in 3.1.6", "Move off " + c("/business/sda")],
    ["Assurance events " + c("/dna/data/.../assuranceEvents"), "Yes, from 2.3.7.6", "Yes", "—"],
    ["Enrichment v2", "2.3.7.10", "Yes", "—"],
    ["SWIM " + c("networkDeviceImages") + " with bulk and validations", "In the 2.3.7.9 SDK; DevNet lists it from 3.1.3", "3.1.3", "Rewrite upgrade pipelines; v1 is Sunset"],
    ["Backup and restore APIs", "In the 2.3.7.9 SDK; DevNet lists it from 3.1.3", "3.1.3", "Automate controller backups"],
    ["Energy analytics, ThousandEyes results", "In the 2.3.7.9 SDK; DevNet lists it from 3.1.3", "3.1.3", "New reporting options"],
    ["Industrial REP and MRP rings (Resilient Ethernet Protocol, Media Redundancy Protocol), LAN Automation port channels", "In the 2.3.7.9 SDK; DevNet lists it from 3.1.3", "3.1.3", "—"],
    ["Compliance policies, rules, variables", "No", "3.1.5", "Custom compliance as code"],
    ["RBAC v2 roles and access groups", "No", "3.1.5", "Migrate role scripts; v1 is Sunset"],
    ["Discovery " + c("/discoverys") + ", global credentials " + c("/globalCredentials") + " (both v1 paths), device add and validate", "No", "3.1.6", "Use these for new code; " + c("/discovery") + " is Sunset in 3.2.2"],
    ["System software upgrade APIs", "No", "3.1.6", "Automate controller upgrades"],
    ["Minimum resync interval", "25 minutes", "6 hours (3.1.5)", "Remove resync tuning from scripts"],
    ["Tooling", "SDK 2.3.7.6.x / 2.3.7.9.x; Ansible " + c("cisco.catalystcenter") + " 1.0.0 / 2.1.4", "SDK 3.1.x to 3.2.3.0.x; Ansible 2.2.2 (3.1.3), 2.10.2+ (3.1.6), 2.11.0+ (3.2.3)", "Pin tools to the target release"],
])}
<h3>What is new in 3.2.x and 3.3.1</h3>
<p>DevNet's full reference stops at 3.1.6, so these come from the Platform User Guides 3.2.x and 3.3.x and Cisco's 3.2.3 Python SDK. 3.2.2 (May 2026) and 3.3.1 (September 2026) are controlled-availability releases; 3.2.3 (first released July 2026, SMU 75346.100 generally available) is the newest generally available release and this guide's baseline. 3.2.2 deprecates several API families (listed under <a href="#changes">Deprecated APIs</a>); 3.2.3 and 3.3.1 deprecate none and list no breaking changes. 3.3.1 marks some operations BETA in the catalog and in the specification's banner field.</p>
{table(["Release", "Area", "New operations"], [
    ["3.3.1", "Clients", c("/dna/intent/api/v1/trackedClients") + " with " + c("/query") + ", " + c("/{id}") + ", " + c("/bulkCreate") + ", " + c("/bulkUpdate") + ", " + c("/bulkDelete")],
    ["3.3.1", "Campus connectivity", c("/dna/campus/api/v1/networks") + ", " + c("/{id}") + ", " + c("/count")],
    ["3.3.1", "Devices", c("/networkDevices/refresh") + ", " + c("/networkDevices/refreshRequests/...") + "; new " + c("syncProgress") + " and " + c("fullSyncDuration") + " fields"],
    ["3.3.1", "Wireless backhaul", c("/dna/data/api/v1/urwbNetworks") + " with links, nodes, query and analytics (URWB: Ultra-Reliable Wireless Backhaul)"],
    ["3.3.1", "Industrial", "PRP (Parallel Redundancy Protocol) " + c("/iot/fabric/prp/...") + "; more REP ring operations under " + c("/iot/repRings/...")],
    ["3.3.1", "Network settings", c("GET/PUT /sites/{id}/aaaTrustSecSettings") + "; RADIUS (Remote Authentication Dial-In User Service) over DTLS (Datagram TLS) and TACACS+ (Terminal Access Controller Access-Control System Plus) over TLS in AAA settings"],
    ["3.3.1", "Intelligent Capture", c("POST /dna/data/api/v1/icap/captureFiles/{id}/analyze") + ", " + c("/icap/settings")],
    ["3.3.1", "Maps", c("/outdoorAreas") + ", access point positions, " + c("/maps/accessPointAntennas")],
    ["3.3.1", "IPAM", c("ipam/serverSetting/validationReports") + ", " + c("ipam/serverSetting/exports") + "; BLUECAT_V2API provider"],
    ["3.3.1", "Wireless", c("/wirelessSettings/wlanSchedulers") + ", " + c("/wirelessControllers/regulatoryActivations")],
    ["3.3.1", "LAN Automation", "OSPF (Open Shortest Path First) underlay as well as IS-IS (Intermediate System to Intermediate System) through " + c("POST /dna/intent/api/v2/lan-automation")],
    ["3.2.3", "Campus switches and controllers", c("/dna/campus/api/v1/switches/...") + ", " + c("/wirelessControllers/...") + ", " + c("/provision/switches/...") + " (new " + c("/dna/campus") + " prefix, about 430 operations)"],
    ["3.2.3", "Industrial", c("/iot/fabric/penUpgrade/configurationModels")],
    ["3.2.2", "Troubleshooting", c("/dna/intent/api/v1/pathTraces")],
    ["3.2.2", "Devices and onboarding", c("/pnpNetworkDevices") + ", " + c("/networkDeviceReplacements/workflow/deploy")],
    ["3.2.2", "Events", c("/event/sftp/configurations")],
    ["3.2.2", "SD-Access and images", c("/sda/switchNetworkProfiles") + ", " + c("/images/transferProtocolSettings")],
    ["3.2.2", "Other", c("/licenseUsage") + ", " + c("/networkDeviceLicenses") + ", " + c("/clientEnrichmentDetails") + ", " + c("/issueEnrichmentDetails") + ", " + c("/userEnrichmentDetails") + ", " + c("/wirelessAccessPoints/configurations") + ", " + c("/sites/{id}/locationServerSettings")],
])}
</section>''')

A(f'''<section id="changes"><h2>Deprecated and sunset APIs</h2>
<p><b>Deprecated</b> means a better alternative exists. <b>Sunset</b> means support ends once the deprecation period elapses. A deprecated operation stays for two GA (Generally Available) releases or one year, whichever is longer; after that Cisco may remove it in any release.</p>
{dep_tool()}
{fig(fig_timeline(), 14, "Releases (grey: 2.3.7 train, blue: 3.x) and the minimum one-year window after each major deprecation. Past the bar, removal is allowed in any release.")}
{table(["Area", "Deprecated or Sunset", "Flagged in", "Replace with"], [
    ["Discovery", c("/discovery") + " v1 (13 operations, including POST and PUT " + c("/discovery") + ")", "3.2.2 (Sunset)", c("POST /discoverys") + ", " + c("POST /discoverys/{id}/jobs")],
    ["Issues", c("GET /dna/intent/api/v1/issues"), "3.2.2", c("GET /dna/data/api/v1/assuranceIssues") + ", " + c("POST …/assuranceIssues/query")],
    ["Licenses", c("/licenses/device/count") + ", " + c("…/summary") + ", " + c("…/{uuid}/details") + ", " + c("/licenses/term/…"), "3.2.2", c("/networkDeviceLicenses") + " family, " + c("/licenseUsage")],
    ["Wireless AP configuration", c("/wireless/accesspoint-configuration") + " (5 operations, v1 and v2)", "3.2.2", c("POST /wirelessAccessPoints/configurations")],
    ["Path Trace", c("/flow-analysis") + " (4 operations)", "3.2.x API specification", c("/dna/intent/api/v1/pathTraces")],
    ["Tasks", c("GET /task") + ", " + c("/task/{taskId}") + ", " + c("/task/count") + ", " + c("/task/{taskId}/tree") + ", " + c("/task/operation/…"), "2.3.7.6", c("GET /tasks/{id}") + ", " + c("/tasks/{id}/detail") + ", " + c("/tasks") + ", " + c("/tasks/count")],
    ["Site hierarchy", c("/site") + ", " + c("/v2/site") + ", " + c("/site/count") + ", " + c("/site-member/{id}/member") + ", " + c("/membership/{siteId}") + ", " + c("/assign-device-to-site/{siteId}/device"), "2.3.7.6", c("/sites") + " family; " + c("POST /networkDevices/assignToSite/apply")],
    ["Network settings", c("/network") + " and " + c("/network/{siteId}") + " (v1 and v2)", "2.3.7.6", c("/sites/{id}/…Settings") + " (aaa, dns, dhcp, ntp, timeZone, banner, telemetry)"],
    ["Site credentials", c("/credential-to-site/{siteId}") + " (v1 and v2)", "2.3.7.6", c("PUT /sites/{id}/deviceCredentials") + ", then " + c("POST /sites/deviceCredentials/apply")],
    ["Wireless (legacy)", c("/wireless/profile") + ", " + c("/wireless/rf-profile") + ", " + c("/enterprise-ssid") + ", " + c("/business/ssid") + ", " + c("/wireless/provision") + ", " + c("/wireless/ap-provision"), "2.3.7.6", c("/wirelessProfiles") + ", " + c("/wirelessSettings/rfProfiles") + ", " + c("/sites/{siteId}/wirelessSettings/ssids") + ", " + c("/wirelessControllers/{deviceId}/provision") + ", " + c("/wirelessAccessPoints/provision")],
    ["IP pools", c("/reserve-ip-subpool") + " and " + c("/global-pool") + " (all methods)", "2.3.7.9", c("/ipam/siteIpAddressPools") + ", " + c("/ipam/globalIpAddressPools")],
    ["SD-Access", c("/business/sda/...") + " (about 45 operations)", "2.3.7.9", c("/sda/...") + " family"],
    ["Virtual networks", c("/virtual-network"), "2.3.7.9", c("/sda/layer3VirtualNetworks")],
    ["Event subscriptions", c("POST/PUT/GET /event/subscription") + " (generic)", "2.3.7.9 (the SDK says 2.3.3.x)", c("/event/subscription/rest") + " and the other per-channel subscription operations"],
    ["Security advisories", c("/security-advisory/...") + " (5 operations)", "2.3.7.9", c("/securityAdvisories/...") + " results and " + c("triggerScan")],
    ["Golden image", c("/image/importation/golden...") + ", " + c("GET /image/importation"), "2.3.7.9", c("POST /images/{id}/sites/{siteId}/tagGolden") + ", " + c("/untagGolden") + ", " + c("GET /images")],
    ["SWIM", c("POST /image/distribution") + ", " + c("POST /image/activation/device"), "3.1.3 (Sunset)", c("/networkDeviceImages/...") + " including bulk"],
    ["Config archive", c("GET /network-device-config"), "3.1.3 (the operation itself says 2.3.7.9)", c("/networkDeviceConfigFiles")],
    ["Users and roles", c("/dna/system/api/v1/role") + ", " + c("/roles") + ", " + c("/role/permissions"), "3.1.5 (Sunset)", c("/dna/system/api/v2/roles") + ", " + c("/dna/system/api/v2/roles/permissions") + ", " + c("/dna/system/api/v1/accessGroups")],
    ["IPAM provider", "BLUECAT_V1API provider value", "3.3.1: planned for deprecation", "BLUECAT_V2API"],
    ["Southbound", "Multivendor SDK", "Deprecated", "SNMP MIB-II third-party visibility"],
    ["Ansible", c("cisco.dnac") + " collection", "Removed from the Ansible 14 community package (June 2026); still on Galaxy", c("cisco.catalystcenter")],
])}
<p class="note amber">Many tutorials, and some of Cisco's own guides, still use legacy paths: DevNet's Command Runner and asynchronous-API guides poll <code>/task/{{taskId}}</code>, and a September 2025 Cisco Community lab creates sites with <code>POST /dna/intent/api/v1/site</code>. These still answer, but translate examples to the replacement column before reuse. <code>/v2/global-credential</code> is not deprecated, but 3.1.6 adds <code>/globalCredentials</code>.</p>
<p class="note">Release labels: Cisco's SDK marks the 3.2.2 deprecations "since 3.2.1", a build that does not appear in Cisco's release notes; 3.2.2 was the first published 3.2.x release. Behaviour changes without a path change: 3.1.5 raised the minimum resync to 6 hours and made system performance APIs ignore time parameters; 3.1.6 and 2.3.7.11 ignore four 802.11be parameters on IOS XE 17.18.2+; 3.3.1 removed unused wireless PDC and MDC attributes. For a definitive list on your build, filter the in-product API catalog by Deprecated and Sunset banners.</p>
</section>''')

A(f'''<section id="tooling"><h2>Tooling</h2>
{table(["Tool", "Package", "Latest seen (Oct 2026)", "Notes"], [
    ["Python SDK", c("pip install catalystcentersdk"), "3.2.3.0.4", "One package serves 2.3.7.6 to 3.2.3; set " + c("version=") + " (or " + c("CATALYST_CENTER_VERSION") + ") to your controller release, because the default is 3.1.6.0. Refreshes the token and waits on 429 by default"],
    ["Ansible", c("cisco.catalystcenter"), "2.14.0", "Red Hat certified, about 1,550 modules. Minimums: 2.2.2 for 3.1.3, 2.10.2 for 3.1.6, 2.11.0 for 3.2.3. " + c("cisco.dnac") + " left the Ansible 14 package"],
    ["Cisco Validated Playbooks", c("catalyst-center-ansible-iac") + "; also " + c("cvp/") + " in the collection", "—", "Discovery, inventory, PnP, SWIM, compliance, RMA (Return Merchandise Authorization), notifications"],
    ["Terraform", c("CiscoDevNet/catalystcenter"), "0.6.5", "Network as Code provider, tested against 2.3.7.10, 2.3.7.11, 3.1.5 and 3.2.3"],
    ["Terraform (SDK-based)", c("cisco-en-programmability/catalystcenter"), "1.2.0-beta", "Beta"],
    ["MCP server", c("cisco-en-programmability/catc-mcp-oss"), "Branches for 2.3.7.11, 3.1.6, 3.2.3", "Beta, self-hosted; see AI agents and MCP"],
    ["Sandbox", c("sandboxdnac.cisco.com"), "2.3.3.6 always-on; 2.3.7.9 reservable", "Good for GET practice; newer endpoints return 404 on the always-on sandbox"],
])}
</section>''')

RULES = [
    ("Pin to your release.", "Set the SDK's API version to your controller release and pin Ansible and Terraform to versions that support it."),
    ("Read Deprecated and Breaking sections before every upgrade,", "then test integrations against the target release in a lab."),
    ("One service account per integration,", "least privilege, RBAC v2 roles and access groups."),
    ("Cache the token and re-authenticate once on 401;", "documented lifetimes differ (1 hour vs 60 seconds)."),
    ("Keep TLS verification on in production.", ""),
    ("Treat 202 as accepted, not done.", "Poll /tasks/{id} with a timeout and surface failureReason from /tasks/{id}/detail."),
    ("Page with each operation's limit and offset base;", "usually 500 and 1-based. Size with /count, filter with /query, de-duplicate by ID."),
    ("Design for 429.", "Limits are per operation (from 10 to 1,000 per minute) and counted per client IP address; back off and serialize writes."),
    ("Retry writes carefully.", "Retry 500 and 503 only for reads; for a write, check the task or object first."),
    ("Push, don't poll.", "Webhooks for events and issues; reconcile hourly from the published notifications."),
    ("Never schedule device-touching calls.", "Command Runner and Path Trace are on demand, for a handful of devices or one flow."),
    ("Prefer the new resource model:", "/sites, /ipam, /sda, /networkDevices, /networkDeviceImages, /tasks, assuranceIssues."),
    ("Gate every change on prerequisites:", "backup, archive, managed and reachable, no critical issues, SD-Access compliance."),
    ("Use bulk operations in waves by site.", ""),
    ("Validate before and after:", "readiness checks, validation workflows, compliance, health."),
    ("Put MCP behind an Observer account on loopback.", "The server does not enforce read-only, and certificate checks are off unless you turn them on."),
]
A('<section id="checklist"><h2>Guidance checklist</h2><ol class="rules">' +
  "".join(f"<li><b>{a}</b> {E(b)}</li>" for a, b in RULES) + "</ol></section>")

SRC = [
    ("DevNet: Catalyst Center API overview", "https://developer.cisco.com/docs/catalyst-center/"),
    ("DevNet: Getting Started (3.1.6)", "https://developer.cisco.com/docs/catalyst-center/getting-started/"),
    ("DevNet: API changelog", "https://developer.cisco.com/docs/catalyst-center/api-changelog/"),
    ("DevNet: Authentication", "https://developer.cisco.com/docs/catalyst-center/authentication/"),
    ("DevNet: Asynchronous operations", "https://developer.cisco.com/docs/catalyst-center/asynchronous-api/"),
    ("DevNet: API versioning and deprecation", "https://developer.cisco.com/docs/catalyst-center/versioning/"),
    ("DevNet: Event management", "https://developer.cisco.com/docs/catalyst-center/event-management/"),
    ("DevNet: Command Runner guide", "https://developer.cisco.com/docs/dna-center/command-runner"),
    ("DevNet: Ansible for Catalyst Center", "https://developer.cisco.com/docs/catalyst-center/ansible/"),
    ("Cisco: Release notes index", "https://www.cisco.com/c/en/us/support/cloud-systems-management/dna-center/products-release-notes-list.html"),
    ("Cisco: Release notes 3.2.3", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-2-x/release-notes/3-2-3/cisco-catalyst-center-release-notes-323.html"),
    ("Cisco: Platform User Guide 3.2.x", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/3_2_x/user-guide/cisco-catalyst-center-platform-ug-3-2-x/b-dnac-platform-ug-3-2-x-chapter-01.html"),
    ("Cisco: Platform User Guide 3.3.x (PDF)", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/3-3-x/user-guide/cisco-catalyst-center-platform-ug-3-3-x.pdf"),
    ("Cisco: Catalyst Center compatibility matrix (SD-Access)", "https://www.cisco.com/c/dam/en/us/td/docs/Website/enterprise/catalyst_center_compatibility_matrix/index-sda.html"),
    ("Cisco: ServiceNow CMDB synchronization", "https://www.cisco.com/c/en/us/support/docs/cloud-systems-management/catalyst-center/222372-synchronize-catalyst-center-inventory-wi.html"),
    ("Cisco tech note 226435: Understand and use Catalyst Center APIs", "https://www.cisco.com/c/en/us/support/docs/software/dna-switching/226435-understand-and-use-catalyst-center-apis.html"),
    ("Cisco: Platform User Guide 3.3.x, About Intent APIs", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/3-3-x/user-guide/cisco-catalyst-center-platform-ug-3-3-x/b-dnac-platform-ug-3-3-x-chapter-01/c_about_intent_based_apis.html"),
    ("Cisco: Platform User Guide 3.3.x, API prerequisites", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/3-3-x/user-guide/cisco-catalyst-center-platform-ug-3-3-x/b-dnac-platform-ug-3-3-x-chapter-010/c_api_prereqs.html"),
    ("Cisco: Platform User Guide 3.3.x, APIs and event notifications chapter", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/3-3-x/user-guide/cisco-catalyst-center-platform-ug-3-3-x/b-dnac-platform-ug-3-3-x-chapter-0111.html"),
    ("Cisco Community: Working with Catalyst Center API", "https://community.cisco.com/t5/networking-knowledge-base/working-with-catalyst-center-api/ta-p/5329013"),
    ("PyPI: catalystcentersdk", "https://pypi.org/project/catalystcentersdk/"),
    ("Red Hat: cisco.catalystcenter collection", "https://catalog.redhat.com/en/software/collection/cisco/catalystcenter"),
    ("GitHub: catc-mcp-oss", "https://github.com/cisco-en-programmability/catc-mcp-oss"),
    ("Cisco Blogs: Meraki and Catalyst Center MCP servers", "https://blogs.cisco.com/cisco-devnet/build-agentic-networking-experiences-with-meraki-and-catalyst-center-mcp-servers"),
    ("DevNet: Event Catalog", "https://developer.cisco.com/docs/catalyst-center/event-catalog/"),
    ("Cisco: Release notes 3.3.x", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-3-x/release-notes/cisco-catalyst-center-release-notes-3-3-x.html"),
    ("Cisco: Release notes 2.3.7.x", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/2-3-7/release_notes/b_cisco_catalyst_center_237_release_notes.html"),
    ("Cisco: Catalyst Center end-of-life guideline", "https://www.cisco.com/c/en/us/products/collateral/cloud-systems-management/dna-center/eos-eol-notice-c51-743588.html"),
    ("Cisco: Platform User Guide 2.3.7, new and changed (2.3.7.9 deprecations)", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/Catalyst-Center-Platform-Documentation/2-3-7/user-guide/b-cisco-catalyst-center-platform-ug-2-3-7/m-new-and-changed-ug-2-3-7.html"),
    ("Cisco: SD-Access compatibility matrix JSON (air-gapped clusters)", "https://www.cisco.com/c/dam/en/us/td/docs/Website/enterprise/sda_compatibility_matrix/resources/json-information.html"),
    ("Cisco: Admin Guide 3.2.x, SD-Access compatibility matrix", "https://www.cisco.com/c/en/us/td/docs/cloud-systems-management/network-automation-and-management/catalyst-center/3-2-x/admin-guide/cisco-catalyst-center-admin-guide-3-2-x/configure-external-services/t_sd-access-compatibility-matrix.html"),
    ("GitHub: Cisco Catalyst Center Python SDK", "https://github.com/cisco-en-programmability/catalystcentersdk"),
    ("GitHub: cisco.catalystcenter Ansible collection", "https://github.com/cisco-en-programmability/catalystcenter-ansible"),
    ("Terraform Registry: CiscoDevNet/catalystcenter", "https://registry.terraform.io/providers/CiscoDevNet/catalystcenter/latest"),
    ("Ansible 14 changelog (cisco.dnac removed)", "https://raw.githubusercontent.com/ansible-community/ansible-build-data/main/14/CHANGELOG-v14.md"),
    ("Claude support: custom connectors using remote MCP", "https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp"),
]
A('@@FIGINDEX@@')
A('<section id="sources"><h2>Sources</h2><ul class="src">' +
  "".join(f'<li><a href="{u}" target="_blank" rel="noopener">{E(t)}</a></li>' for t, u in SRC) +
  '</ul><p class="note">Payloads marked illustrative must be checked against the operation schema in your release. Verify endpoints in Platform &gt; Developer Toolkit &gt; APIs before production use.</p></section>')

CSS = open(os.path.join(HERE, "style.css"), encoding="utf-8").read()
JS = r'''
document.querySelectorAll('.copy').forEach(function(b){
  b.addEventListener('click', function(){
    var t = b.closest('.code').querySelector('code').innerText;
    var done = function(){ b.textContent = 'Copied'; setTimeout(function(){ b.textContent = 'Copy'; }, 1500); };
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(t).then(done, function(){ sel(b); });
    } else { sel(b); }
  });
});
function sel(b){ var r = document.createRange(); r.selectNodeContents(b.closest('.code').querySelector('code'));
  var s = window.getSelection(); s.removeAllRanges(); s.addRange(r); b.textContent = 'Press Ctrl+C'; }
(function(){ var b=document.getElementById('theme-toggle'), r=document.documentElement, K='catc-theme', order=['dark','light','system'];
  function cur(){ return r.getAttribute('data-theme') || 'system'; }
  function show(){ var c=cur(); b.textContent = c==='system' ? 'Theme: system' : (c==='dark' ? 'Theme: dark' : 'Theme: light'); b.setAttribute('aria-label', 'Colour theme: ' + c + '. Select to change.'); }
  try { var t=localStorage.getItem(K); if (t==='dark'||t==='light') r.setAttribute('data-theme', t); } catch(e){}
  b.addEventListener('click', function(){ var n = order[(order.indexOf(cur()) + 1) % 3];
    if (n==='system') r.removeAttribute('data-theme'); else r.setAttribute('data-theme', n);
    try { localStorage.setItem(K, n); } catch(e){} show(); }); show(); })();
if (window.matchMedia('(max-width: 960px)').matches) { var d = document.querySelector('.side details'); if (d) d.open = false; }
var tops = Array.prototype.slice.call(document.querySelectorAll('header.site nav a'));
var links = Array.prototype.slice.call(document.querySelectorAll('.side a'));
if ('IntersectionObserver' in window) {
  var io = new IntersectionObserver(function(es){ es.forEach(function(e){ if (e.isIntersecting) {
    links.forEach(function(a){ a.classList.toggle('on', a.getAttribute('href') === '#' + e.target.id); });
    var part = (document.querySelector('.side a.on') || {}).dataset; tops.forEach(function(t){ t.setAttribute('aria-current', part && t.getAttribute('data-part') === part.part ? 'true' : 'false'); }); } }); },
    { rootMargin: '-20% 0px -70% 0px' });
  document.querySelectorAll('section[id]').forEach(function(s){ io.observe(s); });
}
'''

PART_OF = {i: part for part, items in NAV for i, _ in items}
body = "".join(S)
import re as _re
_sec, _rows = None, []
for m in _re.finditer(r'<section id="([^"]+)"|<figure class="fig" id="fig-([^"]+)"', body):
    if m.group(1): _sec = m.group(1); continue
    n = m.group(2); t = dict((str(k), v) for k, v in FIGS)[n]
    secname = next((tt for p, items in NAV for i, tt in items if i == _sec), _sec)
    _rows.append(f'<li><a href="#fig-{n}"><span class="fi-n">Figure {n}</span><span class="fi-t">{E(t)}</span><span class="fi-s">{E(secname)}</span></a></li>')
body = body.replace("@@FIGINDEX@@", '<section id="figures"><h2>Figure index</h2><p>Every diagram in the guide. Flow figures animate their packets (pause or replay from the bar above each one); step-through figures send a packet as you advance.</p><ol class="figidx">' + "".join(_rows) + '</ol></section>')
for sid, part in PART_OF.items():
    body = body.replace(f'<section id="{sid}"><h2>', f'<section id="{sid}"><p class="eyebrow">{part}</p><h2>', 1)
FIRST = {part: items[0][0] for part, items in NAV}
top_nav = "".join(f'<a href="#{FIRST[p]}" data-part="{p}">{p}</a>' for p, _ in NAV)

page = f'''<meta charset="utf-8">
<title>Catalyst Center API Field Guide</title>
<link rel="icon" type="image/svg+xml" href="data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 64 64%22 width=%2264%22 height=%2264%22%3E%3Crect width=%2264%22 height=%2264%22 rx=%2214%22 fill=%22%2312263A%22/%3E%3Cg stroke=%22%23049FD9%22 stroke-width=%224%22 stroke-linecap=%22round%22%3E%3Cline x1=%2232%22 y1=%2218%22 x2=%2218%22 y2=%2244%22/%3E%3Cline x1=%2232%22 y1=%2218%22 x2=%2246%22 y2=%2244%22/%3E%3Cline x1=%2218%22 y1=%2244%22 x2=%2246%22 y2=%2244%22/%3E%3C/g%3E%3Cg fill=%22%23049FD9%22%3E%3Ccircle cx=%2232%22 cy=%2218%22 r=%227%22/%3E%3Ccircle cx=%2218%22 cy=%2244%22 r=%227%22/%3E%3Ccircle cx=%2246%22 cy=%2244%22 r=%227%22/%3E%3C/g%3E%3C/svg%3E">\n<link rel="icon" type="image/png" sizes="32x32" href="favicon.png">
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<header class="site"><div class="in">
<a class="brand" href="#top"><b>Cisco<span>SE</span></b><small>Field reference</small></a>
<nav aria-label="Guide parts">{top_nav}</nav>
<button type="button" class="pill" id="theme-toggle">Theme: system</button>
</div></header>
<div class="hero" id="top"><div class="in">
  <p class="eyebrow">Field guide · Release 3.2.3 (generally available) · 3.3.1 controlled-availability additions · 2.3.7.x deltas</p>
  <h1>Cisco Catalyst Center API</h1>
  <p class="lead">A working reference for integrating Cisco Catalyst Center (formerly DNA Center) with other systems: how a call is served, which endpoint answers which question, how to automate safely in SD-Access (Software-Defined Access) and non-fabric networks, what is deprecated, and how to put AI agents on top through MCP (Model Context Protocol).</p>
  <div class="hbtns"><a class="hbtn solid" href="#overview">Start with the foundations</a><a class="hbtn" href="#changes">Deprecated APIs</a></div>
  <nav class="tiles" aria-label="Quick links">
    <a href="#live"><b>Live simulation</b><span>A day of API traffic and the rate limit</span></a>
    <a href="#auth"><b>Authentication</b><span>Token, RBAC and re-auth, step by step</span></a>
    <a href="#choose"><b>Which endpoint?</b><span>Decision tree from question to API</span></a>
    <a href="#changes"><b>Deprecation lookup</b><span>Paste a path, get its status</span></a>
    <a href="#mcp"><b>AI agents and MCP</b><span>Use cases and guard rails</span></a>
    <a href="#figures"><b>Figure index</b><span>All diagrams in one list</span></a>
  </nav>
</div></div>
<div class="layout">
<aside class="side" aria-label="Sections"><details open><summary>Contents</summary>{nav_html}</details>
<div class="legend"><div><span class="sw" style="background:var(--accent)"></span>Stops at the controller (safe to poll)</div><div><span class="sw" style="background:var(--amber)"></span>Reaches the device (on demand)</div><div><span class="sw" style="background:var(--green)"></span>Writes configuration (async task)</div></div></aside>
<main>{body}</main></div>
<footer class="site"><div class="in">
  <p class="brandline">Cisco<span>SE</span> · Field reference</p>
  <p>Catalyst Center API field guide · Release 3.2.3 with 3.3.1 and 2.3.7.x deltas · verified 26 Oct 2026. Built from the Cisco DevNet Catalyst Center API reference, the Catalyst Center Platform User Guides 3.1.x to 3.3.x, Cisco's Python SDK, the release notes and the compatibility matrices. Verify endpoints in <b>Platform &gt; Developer Toolkit &gt; APIs</b> on your cluster before production use.</p>
  <p>Not an official Cisco publication. Corrections are welcome as pull requests with the supporting document and release.</p>
</div></footer>
{data_script()}
<script>{JS}
{IJS}
{AJS}</script>'''
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(HERE), "index.html")
open(OUT, "w", encoding="utf-8").write(page)
print(len(page))
