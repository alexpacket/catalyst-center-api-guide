import html, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from svg import *
from interactive import stepper, path_tool, rate_tool, choose_tool, code_tool, sym_tool, dep_tool, search_tool, data_script, JS as IJS

E = html.escape


def code(lang, src, title):
    return (f'<div class="code"><div class="code-h"><span>{E(title)}</span>'
            f'<button type="button" class="copy">Copy</button></div><pre><code>{E(src.strip())}</code></pre></div>')


def fig(svgs, num, cap, extra=""):
    return f'<figure class="fig"><div class="fig-scroll">{svgs}</div>{extra}<figcaption><b>Figure {num}.</b> {cap}</figcaption></figure>'


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
                 ("sources", "Sources")]),
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
        self.exp = time.time() + 55 * 60          # token lives 60 min

    def call(self, method, path, **kw):
        if time.time() > self.exp:
            self._login()
        delay, relogged = 2, False
        for _ in range(6):
            r = self.s.request(method, self.base + path, **kw)
            if r.status_code == 401 and not relogged:
                self._login(); relogged = True; continue
            if r.status_code in (429, 503):       # no rate-limit headers: back off
                time.sleep(delay); delay = min(delay * 2, 60); continue
            r.raise_for_status()
            return r.json() if r.content else {}
        raise RuntimeError(f"gave up: {method} {path}")

    def wait_task(self, task_id, timeout=900, every=5):
        t0 = time.time()
        while time.time() - t0 < timeout:
            t = self.call("GET", f"/dna/intent/api/v1/task/{task_id}")["response"]
            if t.get("endTime"):
                if t.get("isError"):
                    raise RuntimeError(t.get("failureReason"))
                return t
            time.sleep(every)
        raise TimeoutError(task_id)

    def pages(self, path, params=None, limit=500):
        offset = 1                                 # offset is 1-based
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
task = cc.wait_task(job["response"]["taskId"])
file_id = json.loads(task["progress"])["fileId"]
output = cc.call("GET", f"/dna/intent/api/v1/file/{file_id}")
'''

PY_EVENTS = r'''
# Illustrative payloads: confirm field names in Platform > Developer Toolkit > APIs
hook = cc.call("POST", "/dna/intent/api/v1/event/webhook", json={
    "name": "noc-listener", "description": "NOC event intake",
    "url": "https://hooks.example.com/catc", "method": "POST",
    "trustCert": True})
cc.call("POST", "/dna/intent/api/v1/event/subscription/rest", json=[{
    "name": "network-device-unreachable",
    "subscriptionEndpoints": [{"instanceId": WEBHOOK_ID,
        "subscriptionDetails": {"connectorType": "REST"}}],
    "filter": {"eventIds": ["NETWORK-DEVICES-3-506"]}}])

# Hourly reconcile: pull what the webhook may have missed
events = cc.call("GET", "/dna/data/api/v1/assuranceEvents",
                 params={"deviceFamily": "Switches and Hubs",
                         "startTime": int((time.time() - 3600) * 1000)})
'''

PY_SWIM = r'''
# 1. Who is off the golden image?  2. readiness  3. bulk distribute  4. bulk activate
offenders = list(cc.pages("/dna/intent/api/v1/networkDeviceImages"))
for dev in offenders:
    cc.call("POST", f"/dna/intent/api/v1/networkDeviceImages/{dev['id']}/readinessChecks")
# Build the bulk body from the operation schema for your release
t = cc.call("POST", "/dna/intent/api/v1/networkDeviceImages/distribute/bulk", json=dist_body)
cc.wait_task(t["response"]["taskId"], timeout=3600)
# ...change window opens...
t = cc.call("POST", "/dna/intent/api/v1/networkDeviceImages/activate/bulk", json=act_body)
cc.wait_task(t["response"]["taskId"], timeout=5400)
results = cc.call("GET", "/dna/intent/api/v1/networkDeviceImages/validationResults")
'''

MCP_CFG = r'''
# Run the official server on loopback with a read-only (Observer) account
git clone https://github.com/cisco-en-programmability/catc-mcp-oss && cd catc-mcp-oss
git checkout release/<M.N.P.Q>            # match your Catalyst Center release
export CATALYST_CENTER_HOST="https://catalyst-center.example.com"
export CATALYST_CENTER_USERNAME="mcp-observer"
export CATALYST_CENTER_PASSWORD="***"
export CATALYST_CENTER_VERIFY_SSL=true
docker build -t catalyst-center-mcp:local .
docker run --rm -p 127.0.0.1:7001:7001 -e CATALYST_CENTER_HOST \
  -e CATALYST_CENTER_USERNAME -e CATALYST_CENTER_PASSWORD \
  -e CATALYST_CENTER_VERIFY_SSL catalyst-center-mcp:local
curl http://localhost:7001/v1/health      # process up
# Claude Desktop: {"mcpServers": {"catalyst-center": {"url": "http://localhost:7001/v1/mcp"}}}
'''

S = []
A = S.append

# ---------------- INTRO (first content block) ----------------
A(f'''
<div class="intro">
  <div class="stats">
    <div><b>1,000+</b><span>API operations</span></div>
    <div><b>3 + 1</b><span>path families: intent, data, system; campus from 3.3</span></div>
    <div><b>500</b><span>records per page on the operations checked</span></div>
    <div><b>1 h</b><span>token lifetime per the API reference</span></div>
  </div>
  <div class="legend-row">{badge("read")}{badge("write")}{badge("dev")}</div>
</div>''')

# ---------------- FOUNDATIONS ----------------
A(f'''<section id="overview"><h2>Overview and the four interfaces</h2>
<p>Catalyst Center exposes a northbound REST (Representational State Transfer) API over HTTPS with JSON bodies, called the Intent API. Around it sit an eastbound event channel, a westbound ITSM (IT Service Management) integration, and a southbound multivendor SDK (Software Development Kit) that Cisco has deprecated. Every call goes to <code>https://&lt;cluster&gt;</code> plus a path prefix.</p>
{fig(fig_interfaces(), 0, "The three live integration directions. Third-party devices are now added through SNMP (Simple Network Management Protocol) MIB-II and get inventory, topology and reachability only.")}
{table(["Prefix", "Serves", "Example"], [
    [c("/dna/intent/api/v1/ (v2)"), "Automation and inventory: sites, devices, provisioning, SD-Access, wireless, templates, events", c("GET /dna/intent/api/v1/network-device")],
    [c("/dna/data/api/v1/"), "Assurance analytics: query, count, trend, top-N, energy", c("POST /dna/data/api/v1/assuranceEvents/query")],
    [c("/dna/system/api/v1/ (v2)"), "Platform: authentication, users and roles, backup and restore, system upgrade", c("POST /dna/system/api/v1/auth/token")],
    [c("/dna/campus/api/v1/"), "New in the 3.3.x Platform User Guide (campus networks)", c("POST /dna/campus/api/v1/networks")],
])}
<p class="note">Naming shifted in 2.3.7: older operations use hyphenated singular paths (<code>/network-device</code>); newer ones use camelCase collections with <code>/count</code> and <code>/query</code> siblings (<code>/networkDevices</code>, <code>/networkDevices/query</code>). Prefer the newer form; the older ones are the usual deprecation candidates.</p>
</section>''')

A(f'''<section id="stops"><h2>Where a call stops</h2>
<p>Most reads are answered from the controller's own stores and never touch a device. Writes and live CLI (command-line interface) queries become tasks, and only tasks reach devices. Cost, freshness and safety all follow from which path you hit.</p>
{fig(fig_stops(), 1, "A teaching model built from documented API behaviour; Cisco does not publish this as a single diagram. Solid paths are safe to schedule; the dashed amber path is on demand.", path_tool())}
<div class="cards">
  <div class="card c-read"><h4>Inventory and design DB</h4><p>Sites, settings, devices, configuration archive. Paged with <code>offset</code>/<code>limit</code> (max 500).</p><p class="fresh">Freshness: last device sync. Periodic resync minimum is 6 hours from 3.1.5, plus event-driven updates.</p></div>
  <div class="card c-asr"><h4>Assurance data</h4><p>Health scores, issues, events, analytics. Intent health endpoints plus <code>/dna/data</code> query and trend operations.</p><p class="fresh">Freshness: telemetry ingest from devices (SNMP, syslog, NetFlow, streaming telemetry).</p></div>
  <div class="card c-write"><h4>Task engine</h4><p>Provisioning, SWIM (Software Image Management), discovery, Command Runner. Returns 202 with a <code>taskId</code>.</p><p class="fresh">Freshness: the result exists only once <code>endTime</code> is set.</p></div>
</div>
</section>''')

A(f'''<section id="auth"><h2>Authentication and RBAC</h2>
<p>Authenticate once with HTTP Basic (RFC 7617), then send the returned JWT (JSON Web Token) in <code>X-Auth-Token</code> on every call for up to one hour. Every call is then checked against the caller's RBAC (Role-Based Access Control) role.</p>
{fig(fig_auth(), 2, "One login per hour. An expired token returns 401; re-authenticate once and retry. Step through to see each request and response.", stepper("f2"))}
{table(["Item", "Detail"], [
    ["Token endpoint", c("POST /dna/system/api/v1/auth/token") + " with Basic credentials; response " + c('{"Token": "..."}')],
    ["Header", c("X-Auth-Token: <token>") + " plus " + c("Content-Type: application/json")],
    ["Lifetime", "1 hour per the Authentication API specification. The 3.3.x Platform User Guide's API prerequisites page states 60 seconds. Treat the lifetime as unreliable: cache the token, and re-authenticate on any 401."],
    ["Code previews", "Developer Toolkit generates code in Shell, Node, Python, Ruby, JavaScript, jQuery, PHP, Go and Ansible. Generated Python needs the " + c("requests") + " library."],
    ["Optional AES mode", "If enabled in system configuration, the Authorization header carries a Base64-encoded 256-bit AES (Advanced Encryption Standard) key instead of Basic credentials."],
    ["RBAC", "Use RBAC v2 roles (" + c("/dna/system/api/v2/roles") + ") and access groups (" + c("/dna/system/api/v1/accessGroups") + ") from 3.1.5; v1 role operations are Sunset."],
    ["Getting a token for testing", "Platform &gt; Developer Toolkit &gt; Authentication &gt; Authentication API &gt; Try, or Postman / Bruno with Basic auth. Cisco's tech note sets the token once as a collection-level header."],
    ["Service accounts", "Cisco's lab examples use a SUPER-ADMIN login; in production use one account per integration. Observer role for read-only collectors and MCP; a narrow custom role for writers."],
    ["TLS (Transport Layer Security)", "Labs disable verification for self-signed certificates; in production import the cluster CA (Certificate Authority) and keep verification on."],
])}
{code("python", PY_CLIENT, "Python · minimal client used by every example in this guide")}
</section>''')

A(f'''<section id="mech"><h2>Async tasks, pagination, rate limits</h2>
<h3>Every write is a task</h3>
<p>A 202 Accepted means the request was queued, not that it worked. Poll the task until <code>endTime</code> is set and check <code>isError</code>. Orchestration (business) APIs such as SD-Access return <code>executionId</code> and <code>executionStatusUrl</code> instead; poll <code>/dna/intent/api/v1/dnacaap/management/execution-status/{{executionId}}</code>.</p>
{fig(fig_async(), 3, "The asynchronous pattern. Tasks that produce a file (Command Runner, config export) carry a fileId in progress.", stepper("f3"))}
<h3>Pagination and filtering</h3>
{table(["Rule", "Detail"], [
    ["Page size", c("limit") + " 1 to 500 on the list operations checked (for example validation workflows, SD-Access virtual networks). Not a global rule: read each operation's limit."],
    ["Offset", c("offset") + " is 1-based. Loop until a page returns fewer than " + c("limit") + " rows."],
    ["Size first", "Call the matching " + c("/count") + " operation to size a job."],
    ["Complex filters", "Prefer " + c("POST …/query") + " operations for filters, sorting and aggregation."],
    ["Known issue", "3.2.3 release notes: repeated calls with the same limit and offset can return different site IDs; a documented sort parameter was reported unsupported. Sort client-side and de-duplicate by ID."],
])}
<h3>Rate limits</h3>
{table(["Source", "What it says"], [
    ["OpenAPI specs on DevNet", "Per operation: many show 100 requests per minute, some 50 per minute"],
    ["Platform User Guide 3.2.x and 3.3.x", "\"The intent APIs have a default API rate limit of 50 requests\" (no time window stated); per-operation limits are on the Features tab in Platform &gt; Developer Toolkit &gt; APIs"],
    ["Python SDK", "Waits and retries on 429 by default (" + c("CATALYST_CENTER_WAIT_ON_RATE_LIMIT") + ")"],
    ["Headers", "No rate-limit response headers are documented. Treat 429 as normal and back off."],
])}
{rate_tool()}
</section>''')

# ---------------- AUTOMATE ----------------
A(f'''<section id="sites"><h2>Sites and network settings {badge("write")}</h2>
<p>From 2.3.7.6 the site hierarchy and per-site settings moved to a new resource model. Build a site in five steps; the first three only change design intent in the controller, the last two reach devices.</p>
{fig(fig_site(), 4, "Day-0 site build. Each step returns a task to poll before the next one.")}
{table(["Endpoint", "Function", "Use case"], [
    [c("/dna/intent/api/v1/sites") + ", " + c("GET /sites/{id}") + " (3.1.6)", "Site hierarchy: areas, buildings, floors", "Site-as-code, CMDB location sync"],
    [c("GET /sites?nameHierarchy=Global/Area/Building") + ", then " + c("POST /dna/intent/api/v2/floors"), "Resolve the parent ID by name, then create the child (pattern from Cisco tech note 226435)", "Create floors under an existing building"],
    [c("PUT /sites/{id}/aaaSettings") + ", " + c("dnsSettings") + ", " + c("dhcpSettings") + ", " + c("ntpSettings") + ", " + c("timeZoneSettings") + ", " + c("bannerSettings") + ", " + c("telemetrySettings"), "Per-site network settings with inheritance", "Standard settings per region"],
    [c("PUT /sites/{id}/deviceCredentials") + ", " + c("…/deviceCredentials/apply"), "Credentials per site and sync to devices", "Credential rotation"],
    [c("POST /dna/intent/api/v1/networkDevices/assignToSite/apply"), "Assign devices to a site (returns 202)", "Place discovered devices before provisioning"],
    [c("/dna/intent/api/v1/globalCredentials") + " (3.1.6 v2)", "CLI, SNMP, NETCONF, HTTP credentials", "Vault-driven credential lifecycle"],
    [c("/ipam/globalIpAddressPools") + ", " + c("/ipam/siteIpAddressPools"), "Global pools and site subpools", "IPAM (IP Address Management) alignment"],
])}
</section>''')

A(f'''<section id="inventory"><h2>Inventory, discovery and onboarding {badge("read")} {badge("dev")}</h2>
<p>Inventory reads come from the controller database. Discovery, PnP (Plug and Play) claims and resyncs make the controller talk to devices.</p>
{table(["Endpoint", "Function", "Use case"], [
    [c("GET /dna/intent/api/v1/network-device"), "Device list with basic filters (classic)", "Quick lookups, Command Runner targeting"],
    [c("POST /dna/intent/api/v1/networkDevices/query"), "Device query with complex filters and aggregation", "CMDB sync, compliance reporting"],
    [c("POST /networkDevices") + ", " + c("PUT /networkDevices/{id}") + ", " + c("…/validateDevice") + " (3.1.6)", "Add, update and validate devices", "Brownfield onboarding"],
    [c("/dna/intent/api/v1/discoverys") + " (3.1.6)", "Discovery v2: create, edit, jobs, discovered devices", "Scan ranges, CDP or LLDP (Cisco / Link Layer Discovery Protocol)"],
    ["PnP device, workflow and settings operations", "Zero-touch claim of new devices", "Greenfield branch and closet rollouts"],
    [c("PUT /networkDevices/resyncIntervalSettings"), "Global resync interval (minimum 6 hours from 3.1.5)", "Do not lower; event-driven sync keeps data current"],
    ["Device Replacement operations", "RMA (Return Merchandise Authorization) workflow", "Swap a failed device with its config, image and license"],
])}
</section>''')

A(f'''<section id="templates"><h2>Templates and provisioning {badge("write")} {badge("dev")}</h2>
<p>Configuration templates (CLI or Velocity/Jinja) are the main way to push custom configuration in both fabric and non-fabric networks. The safe sequence is author, version, preview, then deploy.</p>
{steps(["Create a project and template in Template Programmer", "Commit a version (deployments use committed versions)", "Preview the rendered config for one device", "Deploy to devices or by site; get a task", "Poll the task, then run compliance"])}
{table(["Endpoint family", "Function"], [
    [c("GET /dna/intent/api/v2/template-programmer/project"), "Find projects and template IDs"],
    [c("POST /dna/intent/api/v1/template-programmer/template/deploy"), "Deploy a committed template; returns a deployment ID"],
    [c("GET /dna/intent/api/v1/template-programmer/template/deploy/status/{deploymentId}"), "Poll deployment status until it reports success or failure"],
    ["Network profiles and site assignment", "Bind templates to sites through profiles so new devices inherit them"],
    ["Wired and wireless provisioning operations", "Assign a device to a site and push the site's intent"],
])}
<p class="note amber">Template deployment is tracked by a deployment ID and its own status endpoint, not by the generic task API. Template variables are usually filled from a CMDB or IPAM record. Keep templates idempotent and avoid lines that the controller's own intent also writes, or compliance will flag drift.</p>
</section>''')

A(f'''<section id="swim"><h2>Software images (SWIM) {badge("write")} {badge("dev")}</h2>
<p>From 3.1.3, SWIM moved to the <code>networkDeviceImages</code> family with readiness checks, custom validations and bulk operations. The v1 <code>image/distribution</code> and <code>image/activation/device</code> operations are Sunset.</p>
{fig(fig_swim(), 5, "An upgrade wave gated by change approval. Distribution and activation are separate tasks so activation can wait for the maintenance window.", stepper("f5"))}
{table(["Endpoint", "Function"], [
    [c("GET /dna/intent/api/v1/networkDeviceImages") + ", " + c("/count"), "Devices with image details and golden-image status"],
    [c("POST …/networkDeviceImages/{id}/readinessChecks"), "Pre-upgrade readiness for one device"],
    [c("…/networkDeviceImages/validations"), "Custom pre and post checks (show commands per product series)"],
    [c("POST …/distribute/bulk") + ", " + c("…/activate/bulk"), "Bulk distribute and activate; each returns a task"],
    [c("GET …/networkDeviceImages/validationResults"), "Pre and post validation results"],
    [c("/dna/intent/api/v1/productSeries"), "Product series used to scope golden images and validations"],
])}
{code("python", PY_SWIM, "Python · upgrade wave skeleton")}
</section>''')

A(f'''<section id="fabric"><h2>Fabric vs non-fabric: same API?</h2>
<p>Yes for the platform, no for the overlay. Authentication, sites and settings, inventory, discovery, PnP, templates, SWIM, compliance, Assurance and events are the same operations in both. SD-Access adds its own domains for the fabric overlay, and wireless splits into a non-fabric and a fabric family.</p>
{table(["Area", "Non-fabric (traditional campus)", "SD-Access fabric"], [
    ["Platform, auth, RBAC, tasks", "Same", "Same"],
    ["Sites, settings, IP pools", "Same " + c("/sites") + " and " + c("/ipam") + " model", "Same, plus pools bound to virtual networks"],
    ["Inventory, discovery, PnP, SWIM, compliance", "Same", "Same"],
    ["Templates", "Primary way to configure VLANs, uplinks, policies", "Used for day-N extras; avoid lines the fabric intent owns"],
    ["Overlay and segmentation", "VLANs and ACLs (Access Control Lists) through templates", c("/sda/fabricSites") + ", " + c("layer3VirtualNetworks") + ", " + c("anycastGateways") + ", " + c("fabricDevices") + ", " + c("transitNetworks")],
    ["Underlay", "Your own design, often templates", "LAN Automation (" + c("/lanAutomation") + ") or manual underlay"],
    ["Wireless", "Wireless domain: SSIDs (Service Set Identifiers), wireless and RF (Radio Frequency) profiles, WLC (Wireless LAN Controller) provisioning", "Fabric Wireless domain: VLAN-to-SSID mapping (" + c("/sda/fabrics/{id}/vlanToSsids") + ") on top of the wireless profiles"],
    ["Policy", "Application QoS (Quality of Service) policy", "Group-based policy with ISE (Identity Services Engine) scalable groups, plus application policy"],
    ["Assurance", "Device, client, application health", "Same, plus fabric-specific health and issues"],
])}
</section>''')

A(f'''<section id="sda"><h2>SD-Access fabric {badge("write")} {badge("dev")}</h2>
<p>Use the <code>/dna/intent/api/v1/sda/...</code> family. The older <code>/business/sda/...</code> operations (fabric, fabric-site, edge, border, control-plane device, virtual network, multicast) are deprecated.</p>
{fig(fig_sda(), 6, "Fabric build order. Each step depends on the previous one existing.")}
{table(["Endpoint", "Function"], [
    [c("/sda/fabricSites"), "Create, update, delete fabric sites"],
    [c("/sda/layer3VirtualNetworks"), "Layer 3 virtual networks (VRF-based segments)"],
    [c("/sda/anycastGateways"), "Anycast gateways: pool plus VN (Virtual Network) per fabric site"],
    [c("/sda/fabricDevices"), "Assign border, control-plane and edge roles; border handoff settings"],
    [c("/sda/transitNetworks"), "IP-based or SD-Access transits for multi-site"],
    [c("/sda/fabrics/{id}/vlanToSsids"), "Fabric wireless VLAN-to-SSID mapping"],
    [c("/dna/intent/api/v1/trafficSteeringPolicys") + ", " + c("…Contracts") + " (3.1.6)", "Security service insertion and traffic steering"],
])}
<p class="note">Before scripting a role, check the device and release in the SD-Access compatibility matrix (see <a href="#compat">Compatibility matrix</a>). Example from the matrix: C9350 in the edge role needs its control-plane node on IOS XE 17.18.5 and does not support IPv6.</p>
</section>''')

A(f'''<section id="wireless"><h2>Wireless {badge("write")}</h2>
{table(["Endpoint family", "Function"], [
    ["Enterprise and guest SSID operations", "Create and update SSIDs per site"],
    ["Wireless profiles and RF profiles", "Bind SSIDs to sites; radio settings"],
    [c("/wirelessSettings/dot11beProfiles"), "802.11be (Wi-Fi 7) profiles; MLO (Multi-Link Operation) settings changed in 3.1.6"],
    [c("POST /wirelessControllers/{deviceId}/provision"), "Provision a WLC; 3.1.6 adds LSC (Locally Significant Certificate) parameters"],
    [c("/wirelessSettings/certificateRenewalProfiles") + " (3.1.6)", "LSC renewal profiles for access points"],
    [c("GET /wirelessControllers/{deviceId}/siteTags") + " (3.1.6)", "Site tags on a controller"],
])}
<p class="note">On IOS XE 17.18.2 and later, 802.11be <code>ofdma*</code> and <code>muMimo*</code> parameters are ignored at provisioning. 3.3.1 removed fields from wireless PDC and MDC operations; retest wireless automation after upgrading.</p>
</section>''')

# ---------------- OBSERVE ----------------
A(f'''<section id="choose"><h2>How to choose</h2>
<p>Pick the API family by the question, not by the endpoint you already know.</p>
{choose_tool()}
{fig(fig_choose(), 7, "Fleet-wide and historical questions stay on the controller; only the one-device-now case reaches a device.")}
</section>''')

A(f'''<section id="questions"><h2>Customer questions to endpoints</h2>
<p>NOC (Network Operations Center), helpdesk and security teams ask in business terms. This table maps the question to the scalable endpoint and to the heavier troubleshooting-only alternative.</p>
{search_tool()}
{table(["Question", "Scalable endpoint (safe to schedule)", "Troubleshooting only"], [
    ["What devices do we have, and are they reachable?", c("POST /networkDevices/query"), "—"],
    ["How healthy is each site?", c("GET /dna/intent/api/v1/site-health"), "—"],
    ["How healthy is each device tier?", c("GET /dna/intent/api/v1/network-health"), "Command Runner on one device"],
    ["How are clients doing?", c("GET /dna/intent/api/v1/client-health"), c("GET /client-detail?macAddress=")],
    ["What issues are open, and where?", c("GET /dna/intent/api/v1/issues"), "—"],
    ["What happened in the last 24 hours?", c("POST /dna/data/api/v1/assuranceEvents/query"), "—"],
    ["Which devices are exposed to a PSIRT advisory?", c("GET /securityAdvisories/results/networkDevices"), "—"],
    ["Which devices are out of compliance, and why?", c("GET /compliance") + " + " + c("/compliance/networkDevices/{id}/detail/policys"), "—"],
    ["Which devices are not on the golden image?", c("GET /networkDeviceImages"), "—"],
    ["What did the config look like last week?", c("GET /networkDeviceConfigFiles"), "—"],
    ["What does this device show right now?", "—", c("POST /network-device-poller/cli/read-request")],
    ["Why can host A not reach host B?", "—", "Path Trace (" + c("/pathTraces") + " from 3.2.2; " + c("/flow-analysis") + " before)"],
    ["How much power is the network using?", c("/dna/data/api/v1/energy/...") + " (3.1.3)", "—"],
], tid="qtable")}
<p class="note">PSIRT is Cisco's Product Security Incident Response Team. Push beats poll: subscribe to issue and event webhooks instead of looping on <code>/issues</code>.</p>
</section>''')

A(f'''<section id="assurance"><h2>Health, issues and Assurance events {badge("asr")}</h2>
{table(["Endpoint", "Returns", "Use case"], [
    [c("GET /site-health") + ", " + c("/network-health") + ", " + c("/client-health"), "Health scores by site, device tier, client type", "NOC dashboards, every 5 to 15 minutes"],
    [c("GET /dna/intent/api/v1/issues") + "; custom issue definitions", "Open issues with priority and site", "Ticketing, triage queues"],
    [c("/dna/data/api/v1/assuranceEvents") + ", " + c("/count") + ", " + c("/query"), "Raw Assurance events with filters", "Reconcile missed webhooks, forensics"],
    [c("POST /dna/data/api/v1/…/trendAnalytics") + ", " + c("summaryAnalytics"), "Server-side aggregation over time", "SLA (Service-Level Agreement) and capacity reports"],
    [c("/dna/intent/api/v2/…-enrichment-details") + " (2.3.7.10)", "Device, client, user, issue context in one call", "Ticket enrichment"],
    [c("/dna/data/api/v1/thousandEyesTestResults") + " (3.1.3)", "ThousandEyes test results and trends", "Application experience reports"],
])}
</section>''')

A(f'''<section id="events"><h2>Events and webhooks {badge("asr")}</h2>
<p>When a subscribed event fires, Catalyst Center makes an HTTP POST or PUT to your listener with a JSON payload. Destinations can be REST webhook, email, syslog, SNMP trap or Webex (listed in the 3.3.x Platform User Guide), plus ITSM. Event definitions are fixed and cannot be edited.</p>
{fig(fig_webhook(), 8, "Webhooks are the primary path; the hourly Assurance events query reconciles anything missed.", stepper("f8"))}
{code("python", PY_EVENTS, "Python · register a webhook, subscribe, reconcile")}
<p class="note">Cisco's stated practice: confirm HTTP/HTTPS reachability from the cluster to your listener before subscribing. An HTTP/S proxy can be set for outbound notifications. The event ID above is an example; pick IDs from Platform &gt; Developer Toolkit &gt; Event Notifications &gt; Event Catalog.</p>
</section>''')

A(f'''<section id="tools"><h2>Troubleshooting tools {badge("dev")}</h2>
<p>Command Runner runs read-only CLI commands on devices; Path Trace (<code>POST /pathTraces</code> from 3.2.2, <code>POST /flow-analysis</code> earlier) analyses the path between two endpoints. Both are tasks that reach devices: run them for one device or flow, on demand, never on a schedule.</p>
{fig(fig_cmdrunner(), 9, "Command Runner round trip. The output lands in a file you fetch by fileId.", stepper("f9"))}
{code("python", PY_CMD, "Python · Command Runner")}
{usewhen(["An engineer is investigating one device or a handful", "Cached inventory or Assurance data cannot answer the question"],
         ["On a timer, in a loop, or across the whole fleet", "For configuration changes (Command Runner is read-only)"])}
</section>''')

# ---------------- INTEGRATE ----------------
A(f'''<section id="itsm"><h2>ITSM and ServiceNow</h2>
<p>ITSM integration ships as pre-built bundles configured in the GUI. Add the ITSM instance at System &gt; Settings &gt; Destinations &gt; ITSM, test connectivity, then enable bundles under Platform &gt; Manage &gt; Bundles.</p>
{fig(fig_itsm(), 10, "Events land in ServiceNow import set tables; transform maps route them; the Cisco DNA App calls back for enrichment.")}
{table(["Bundle", "What it does"], [
    ["Basic ServiceNow CMDB synchronization", "Pushes inventory into CMDB (Configuration Management Database) CIs"],
    ["Network Issue Monitor and Enrichment", "Creates incidents from Assurance issues with network context"],
    ["Automation (SWIM) events for ITSM", "Change requests around image updates"],
    ["Endpoint Attribute Retrieval", "Endpoint data for profiling"],
    ["Rogue and aWIPS", "Rogue and adaptive Wireless Intrusion Prevention System events"],
])}
<p class="note">Platform &gt; Runtime Dashboard shows call counts and durations for the ServiceNow integration only. A "post to staging table" destination sends raw data to any REST endpoint for your own scripts.</p>
</section>''')

PB = [
    ("ITSM incident with context", "ServiceNow, Jira Service Management",
     ["Issue or event webhook", "ITSM creates the incident", "ITSM calls " + c("/v2/device-enrichment-details") + " and client/issue variants", "Engineer works the ticket", "Resolve issue in Catalyst Center"],
     ["Turning Assurance issues into tickets with device and client context"], ["Polling " + c("/issues") + " every minute"]),
    ("CMDB and asset sync", "ServiceNow CMDB, NetBox",
     ["Nightly " + c("/networkDevices/query") + " with " + c("/count"), "Page at 500", "Enrich with EOX (end-of-life) and license data", "Upsert into the CMDB", "Events for changes between runs"],
     ["The inventory of record lives outside Catalyst Center"], ["Real-time asset changes; use events"]),
    ("IPAM alignment", "Infoblox, BlueCat, other IPAM",
     ["Read " + c("/ipam/globalIpAddressPools"), "Reconcile with IPAM blocks", "Create site subpools with " + c("/ipam/siteIpAddressPools"), "Or configure Catalyst Center to use the external IPAM"],
     ["Address plans are owned centrally"], ["The Sunset " + c("reserve-ip-subpool") + " operations"]),
    ("Security posture report", "SIEM (Security Information and Event Management), GRC (Governance, Risk and Compliance)",
     [c("securityAdvisories") + " results", c("fieldNotices") + " and " + c("networkBugs") + " results", c("compliance") + " status", "Weekly report or SIEM feed"],
     ["Weekly risk and audit reporting"], ["Triggering scans in a tight loop"]),
    ("Upgrade pipeline", "CI/CD (Continuous Integration / Continuous Delivery), change management",
     ["Readiness checks", "Change approval gate", c("distribute/bulk"), c("activate/bulk") + " in window", "Validation results attached to the change"],
     ["Planned SWIM waves with pre and post checks"], ["v1 " + c("image/distribution") + " and " + c("image/activation/device")]),
    ("Day-0 site as code", "Terraform, Ansible, GitOps",
     [c("/sites") + " hierarchy", c("/sites/{id}/…Settings"), "IP pools", "Discovery v2 or PnP", "Provision; SD-Access: " + c("/sda/...")],
     ["New sites from version-controlled definitions"], ["Legacy " + c("/site") + " and " + c("/business/sda") + " paths"]),
]
pb_html = ""
for t, other, st, y, n in PB:
    pb_html += f'<article class="pb"><h3>{t}</h3><p class="pb-o">Other system: {other}</p>{steps(st)}{usewhen(y, n)}</article>'
A(f'''<section id="playbooks"><h2>Integration playbooks</h2>
<p>Six patterns cover most customer integrations. Each lists the flow in order and the most expensive mistake to avoid.</p>
<div class="pbs">{pb_html}</div>
</section>''')

A(f'''<section id="mcp"><h2>AI agents and MCP</h2>
<p>Cisco's open-source Catalyst Center MCP server, in beta since August 2026, lets any MCP-capable AI client call generated Catalyst Center API tools. It runs inside your network, so data and the model can stay within an air-gapped boundary.</p>
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
<li><b>It is not read-only by design.</b> The README states the server adds no authorization layer, does not enforce read-only, and the catalog may include configuration-changing operations. Enforce read-only with an Observer-role account.</li>
<li><b>One dedicated, least-privilege account</b> per deployment. Treat every connected client as able to call anything that account can.</li>
<li><b>Keep the endpoint private.</b> Bind to 127.0.0.1; if shared, put it behind your gateway with authentication and TLS.</li>
<li><b>Keep certificate verification on</b> (<code>CATALYST_CENTER_VERIFY_SSL=true</code>) except in labs.</li>
<li><b>Match the release branch to the controller</b> and rebuild after each controller upgrade.</li>
<li><b>State the safety boundary in prompts</b> ("read-only, do not change anything"). It is a backstop, not a control.</li>
<li><b>Mind rate limits.</b> Agents chain many calls; the same per-operation limits and 500-row pages apply.</li>
<li><b>Choose the model deliberately.</b> For regulated or air-gapped sites, pair the local server with an approved private model.</li>
<li><b>Log tool calls on your side.</b> The controller sees only one service account.</li>
<li><b>Beta can change.</b> Pin a commit and retest on updates.</li>
</ol>
{code("bash", MCP_CFG, "Shell · run the official MCP server")}
<p class="note">Companion: the DevNet Content Search MCP (<code>https://devnet.cisco.com/v1/foundation-search-mcp/mcp</code>) searches Catalyst Center and Meraki API documentation; it has no live network data. Community MCP servers exist but are not Cisco-supported.</p>
</section>''')

# ---------------- OPERATE ----------------
A(f'''<section id="prechange"><h2>Change prerequisites: fabric and non-fabric</h2>
<p>Most failed API changes trace back to a device that was not in a clean state before the change. Gate every automated change on the checks below. Items marked "practice" are general engineering practice; the rest map to documented Catalyst Center features.</p>
<h3>Before any change (both)</h3>
{table(["Check", "How", "Why"], [
    ["Controller backup is recent", c("GET /dna/system/api/v1/backups") + " (3.1.3+)", "Rollback point for the controller itself"],
    ["Device config archived", c("GET /networkDeviceConfigFiles") + " for target devices", "Known-good config to compare and restore"],
    ["Devices Managed and Reachable", c("POST /networkDevices/query") + ": collection status Managed, reachability Reachable", "Tasks against unmanaged or unreachable devices fail or hang"],
    ["No open critical issues on targets", c("GET /issues") + " filtered by site and priority", "Do not change a device that is already degraded"],
    ["Compliance is clean or understood", c("GET /compliance") + " for targets", "Separates new drift from existing drift"],
    ["Release and device are supported", "Compatibility matrix (next section)", "Unsupported combinations fail in provisioning"],
    ["Pre-checks captured", "Network validation workflows (" + c("/diagnosticValidationWorkflows") + ") or SWIM custom validations", "Before/after comparison"],
    ["Change approved, window set", "ITSM change; " + c("POST /dna/intent/api/v1/networkDeviceMaintenanceSchedules"), "Practice: and audit trail"],
    ["Right account", "Narrow RBAC role scoped by access group", "Limits blast radius of a script error"],
    ["Pilot first", "One site or a few devices, then waves", "Practice"],
])}
<h3>Additional checks for SD-Access</h3>
{table(["Check", "Why"], [
    ["ISE (Identity Services Engine) integration healthy and trusted", "Fabric sites, authentication profiles and group-based policy depend on it"],
    ["Underlay ready: routing, MTU and loopbacks (LAN Automation or manual)", "Fabric overlay rides on a working underlay"],
    ["IP pools reserved at the site and mapped to the right virtual network", "Anycast gateways need pool plus VN"],
    ["Border, control-plane and edge roles fit the compatibility matrix for your release and IOS XE version", "Role support differs by platform and version"],
    ["Build in order: fabric site, VNs, gateways, devices, transits", "Each object depends on the previous one (Figure 6)"],
    ["Wait for each task or execution status before the next call", "Fabric operations are orchestrated and long-running"],
    ["Avoid template lines that overlap fabric-owned config", "Templates and fabric intent will fight; compliance flags drift"],
])}
<h3>Additional checks for non-fabric</h3>
{table(["Check", "Why"], [
    ["Templates committed, versioned and previewed for one device", "Catches variable and syntax errors before scale"],
    ["Network profile binds the template to the right sites", "New devices inherit the right config"],
    ["VLAN, trunk and uplink changes staged to avoid cutting management access", "Practice: a bad uplink change strands the device"],
    ["Wireless: SSID, profile and WLC provisioning in that order; retest after upgrades", "Wireless field changes in 3.1.6 and 3.3.1"],
])}
<h3>After the change (both)</h3>
{steps(["Task or execution status succeeded", "Post-checks or validation results match pre-checks", "Run compliance on targets", "Site and device health unchanged or better", "Close the change with evidence"])}
</section>''')

A(f'''<section id="compat"><h2>Compatibility matrix</h2>
<p>Cisco's Catalyst Center compatibility matrix lists which devices each release supports, with an SD-Access mode and a Non-Fabric mode, filters by device role (ISE, fabric edge, border and control plane, wireless, extended node), and an upgrade-path view. It is a web page with a JSON download, not an API.</p>
{table(["What it tells an integrator", "How to use it"], [
    ["Whether a device model supports a fabric role on a given release", "Check before scripting " + c("/sda/fabricDevices") + " assignments"],
    ["Supported upgrade paths between Catalyst Center releases", "Plan controller upgrades, then re-test integrations against the target release"],
    ["Devices at Last Day of Support are removed", "Those devices lose TAC (Technical Assistance Center) support; exclude them from automation scope"],
    ["Third-party devices (RFC 1213 SNMP MIB-II) monitored from 2.3.7.x", "Visibility only; no provisioning API for them"],
    ["EoX scanning from 2.3.3.x for connected customers", "Use the in-product EOX data for lifecycle reports"],
    ["Platform caveats, e.g. C9350 edge needs control plane on IOS XE 17.18.5, no IPv6", "Encode as pre-checks in fabric automation"],
])}
<p class="note">Load the matrix's JSON download into your pipeline as a static gate, refreshed per release. Recommended device software versions come from the Cisco Software Download page.</p>
</section>''')

A(f'''<section id="errors"><h2>Errors and resilience</h2>
{code_tool()}
{fig(fig_retry(), 12, "Retry only 401 (once), 429, 500 and 503. Surface other 4xx client errors immediately. Pick a status code above to highlight its branch.")}
{sym_tool()}
{fig(fig_tree(), 13, "When a task fails or a list comes back empty, separate a real failure from a filter or RBAC scope problem before touching code.")}
{table(["Symptom", "Likely cause", "Fix"], [
    ["202 but nothing changed", "Task failed", "Read the task's " + c("failureReason")],
    ["401 mid-run", "Token expired after 60 minutes", "Cache the token, re-authenticate once"],
    ["403 with a valid token", "RBAC role or access group lacks the feature or site", "Adjust the service account role"],
    ["429", "Per-operation rate limit", "Back off 2 s to 60 s; serialize writes"],
    ["Empty list", "Wrong filter, 0-based offset, RBAC scope", "Offset starts at 1; check access groups"],
    ["Different rows on the same page", "Known paging issue in 3.2.3", "Sort client-side, de-duplicate by ID"],
    ["Inventory looks stale", "Resync is 6 hours minimum", "Trust event-driven sync; do not force resync loops"],
])}
</section>''')

A(f'''<section id="delta237"><h2>2.3.7.x to 3.x deltas</h2>
<p>2.3.7.x is the long-lived train many customers still run, and it received 2.3.7.10 in August 2025 alongside 3.1.x. An integration written on 2.3.7.x keeps working on 3.x except where it uses deprecated operations; the gains in 3.x are mostly new API families.</p>
{table(["Capability", "2.3.7.x", "3.1.x and later", "Action when upgrading"], [
    ["Sites and per-site settings (" + c("/sites") + ", " + c("…Settings") + ")", "Yes, from 2.3.7.6", "Yes; " + c("GET /sites/{id}") + " added in 3.1.6", "Move off legacy " + c("/site")],
    ["IPAM pools (" + c("/ipam/...") + ")", "Yes", "Yes; overlapping pools in 3.1.5", "Move off " + c("reserve-ip-subpool")],
    ["SD-Access " + c("/sda/...") + " family", "Yes", "Yes; traffic steering in 3.1.6", "Move off " + c("/business/sda")],
    ["Assurance events " + c("/dna/data/.../assuranceEvents"), "Yes, from 2.3.7.6", "Yes", "—"],
    ["Enrichment v2", "2.3.7.10", "Yes", "—"],
    ["SWIM v2 " + c("networkDeviceImages") + " with bulk and validations", "No", "3.1.3", "Rewrite upgrade pipelines; v1 is Sunset"],
    ["Backup and restore APIs", "No", "3.1.3", "Automate controller backups"],
    ["Energy analytics, ThousandEyes results", "No", "3.1.3", "New reporting options"],
    ["Industrial REP/MRP rings, LAN Automation port channels", "No", "3.1.3", "—"],
    ["Compliance policies, rules, variables", "No", "3.1.5", "Custom compliance as code"],
    ["RBAC v2 roles and access groups", "No", "3.1.5", "Migrate role scripts; v1 is Sunset"],
    ["Discovery v2, global credentials v2, device add/validate", "No", "3.1.6", "Prefer v2 for new code"],
    ["System software upgrade APIs", "No", "3.1.6", "Automate controller upgrades"],
    ["Minimum resync interval", "25 minutes", "6 hours (3.1.5)", "Remove resync tuning from scripts"],
    ["Tooling", "SDK 2.3.7.6.x / 2.3.7.9.x; Ansible " + c("cisco.catalystcenter") + " 1.0.0 / 2.1.4", "SDK 3.1.x to 3.2.3.0.x; Ansible 2.2.x / 2.3.x", "Pin tools to the target release"],
])}
<h3>What is new in 3.2.x and 3.3.1</h3>
<p>DevNet's full reference stops at 3.1.6, so these come from the Platform User Guides 3.2.x and 3.3.x. Neither guide lists any deprecated API operation or breaking change for 3.2.2, 3.2.3 or 3.3.1. Release 3.2.2 shipped as controlled availability; 3.3.1 marks some operations BETA in the catalog and in the spec's banner field.</p>
{table(["Release", "Area", "New operations"], [
    ["3.3.1", "Clients", c("/dna/intent/api/v1/trackedClients") + " with " + c("/query") + ", " + c("/{id}") + ", " + c("/bulkCreate") + ", " + c("/bulkUpdate") + ", " + c("/bulkDelete")],
    ["3.3.1", "Campus connectivity", c("/dna/campus/api/v1/networks") + ", " + c("/{id}") + ", " + c("/count") + " (new " + c("/dna/campus") + " prefix)"],
    ["3.3.1", "Devices", c("/networkDevices/refresh") + ", " + c("/networkDevices/refreshRequests/...") + "; new " + c("syncProgress") + " and " + c("fullSyncDuration") + " fields"],
    ["3.3.1", "Wireless backhaul", c("/dna/data/api/v1/urwbNetworks") + " with links, nodes, query and analytics (URWB: Ultra-Reliable Wireless Backhaul)"],
    ["3.3.1", "Industrial", "PRP (Parallel Redundancy Protocol) " + c("/iot/fabric/prp/...") + "; REP rings " + c("/iot/repRings/...")],
    ["3.3.1", "Network settings", c("GET/PUT /sites/{id}/aaaTrustSecSettings") + "; RADIUS over DTLS and TACACS+ over TLS in AAA settings"],
    ["3.3.1", "Intelligent Capture", c("POST /dna/data/api/v1/icap/captureFiles/{id}/analyze") + ", " + c("/icap/settings")],
    ["3.3.1", "Maps", c("/outdoorAreas") + ", access point positions, " + c("/maps/accessPointAntennas")],
    ["3.3.1", "IPAM", c("ipam/serverSetting/validationReports") + ", " + c("ipam/serverSetting/exports") + "; BLUECAT_V2API provider"],
    ["3.3.1", "Wireless", c("/wirelessSettings/wlanSchedulers") + ", " + c("/wirelessControllers/regulatoryActivations")],
    ["3.3.1", "LAN Automation", "OSPF underlay as well as IS-IS through " + c("POST /dna/intent/api/v2/lan-automation")],
    ["3.2.3", "Industrial", c("/iot/fabric/penUpgrade/configurationModels")],
    ["3.2.2", "Troubleshooting", c("/dna/intent/api/v1/pathTraces")],
    ["3.2.2", "Devices and onboarding", c("POST /networkDevices") + ", " + c("/pnpNetworkDevices") + ", " + c("/networkDeviceReplacements/workflow/deploy")],
    ["3.2.2", "Events", c("/event/sftp/configurations")],
    ["3.2.2", "SD-Access and images", c("/sda/switchNetworkProfiles") + ", " + c("/images/transferProtocolSettings")],
    ["3.2.2", "Other", c("/licenseUsage") + ", " + c("/clientEnrichmentDetails") + ", " + c("/issueEnrichmentDetails") + ", " + c("/userEnrichmentDetails") + ", " + c("/wirelessAccessPoints/configurations") + ", " + c("/sites/{id}/locationServerSettings")],
])}
</section>''')

A(f'''<section id="changes"><h2>Deprecated and sunset APIs</h2>
<p><b>Deprecated</b> means a better alternative exists. <b>Sunset</b> means support ends once the deprecation period elapses. A deprecated operation stays for two GA (Generally Available) releases or one year, whichever is longer; after that Cisco may remove it in any release.</p>
{dep_tool()}
{fig(fig_timeline(), 14, "Releases (grey: 2.3.7 train, blue: 3.x) and the minimum one-year window after each major deprecation. Past the bar, removal is allowed in any release.")}
{table(["Area", "Deprecated or Sunset", "Flagged in", "Replace with"], [
    ["Site hierarchy", c("/site") + ", " + c("/v2/site") + ", " + c("/site/count") + ", " + c("/site-member/{id}/member") + ", " + c("/assign-device-to-site/{siteId}/device") + " (Sunset banner)", "2.3.7.6", c("/sites") + " family; " + c("POST /networkDevices/assignToSite/apply")],
    ["Site credentials", c("/v1/credential-to-site/{siteId}") + ", " + c("/v2/credential-to-site/{siteId}"), "2.3.7.6", c("PUT /sites/{id}/deviceCredentials")],
    ["IP pools", c("POST/PUT /reserve-ip-subpool/{siteId}") + " (Sunset banner)", "3.1.6 reference", c("/ipam/siteIpAddressPools")],
    ["SD-Access", c("/business/sda/...") + " (about 40 operations: fabric, site, zone, devices, auth profile, VN, multicast)", "2.3.7.9", c("/sda/...") + " family"],
    ["Event subscriptions", c("POST/PUT/GET /dna/intent/api/v1/event/subscription") + " (generic)", "2.3.7.9", c("/event/subscription/rest") + " and the other per-channel subscription operations"],
    ["Path Trace", c("POST /dna/intent/api/v1/flow-analysis") + " (still available)", "Superseded in 3.2.2", c("POST /dna/intent/api/v1/pathTraces")],
    ["IPAM provider", "BLUECAT_V1API provider value", "3.3.1: planned for deprecation", "BLUECAT_V2API"],
    ["SWIM", c("POST /image/distribution") + ", " + c("POST /image/activation/device"), "3.1.3 (Sunset)", c("/networkDeviceImages/...") + " incl. bulk"],
    ["Config archive", c("GET /network-device-config"), "3.1.3", c("/networkDeviceConfigFiles")],
    ["Users and roles", c("/dna/system/api/v1/role") + ", " + c("/roles") + ", " + c("/role/permissions"), "3.1.5 (Sunset)", c("/dna/system/api/v2/roles") + ", " + c("/accessGroups")],
    ["Southbound", "Multivendor SDK", "Deprecated", "SNMP MIB-II third-party visibility"],
    ["Ansible", c("cisco.dnac") + " collection", "Slated for removal from Ansible 14", c("cisco.catalystcenter")],
])}
<p class="note amber">Many tutorials still use legacy paths. For example, a September 2025 Cisco Community lab creates sites with <code>POST /dna/intent/api/v1/site</code> and credentials with <code>/v2/global-credential</code>; both work on older releases but the site path is deprecated. Translate examples to the replacement column before reuse.</p>
<p class="note">Behaviour changes without a path change: 3.1.5 raised the minimum resync to 6 hours and made system performance APIs ignore time parameters; 3.1.6 ignores some 802.11be parameters on IOS XE 17.18.2+; 3.3.1 removed wireless PDC and MDC fields. For a definitive list on your build, filter the in-product API catalog by Deprecated and Sunset banners.</p>
</section>''')

A(f'''<section id="tooling"><h2>Tooling</h2>
{table(["Tool", "Package", "Latest seen (Oct 2026)", "Notes"], [
    ["Python SDK", c("pip install catalystcentersdk"), "3.2.3.0.x", "Version matches the controller release; auto token refresh and rate-limit wait"],
    ["Ansible", c("cisco.catalystcenter"), "2.3.x for 3.1.6", "Red Hat certified, about 1,100 modules; " + c("cisco.dnac") + " is deprecated"],
    ["Cisco Validated Playbooks", c("catalyst-center-ansible-iac"), "—", "Discovery, inventory, PnP, SWIM, compliance, RMA, notifications"],
    ["Terraform", c("CiscoDevNet/catalystcenter"), "v0.3.x", "Network as Code provider, tested against 2.3.7.9"],
    ["Terraform (SDK-based)", c("cisco-en-programmability/catalystcenter"), "1.2.0-beta", "Beta"],
    ["MCP server", c("cisco-en-programmability/catc-mcp-oss"), "Release branch per controller", "Beta, self-hosted, see Part 4"],
    ["Sandbox", c("sandboxdnac.cisco.com"), "2.3.3.6, read-only", "Good for GET practice; newer endpoints may return 404"],
])}
</section>''')

RULES = [
    ("Pin to your release.", "API version equals controller version; pin SDK, Ansible and Terraform to it."),
    ("Read Deprecated and Breaking sections before every upgrade,", "then test integrations against the target release in a lab."),
    ("One service account per integration,", "least privilege, RBAC v2 roles and access groups."),
    ("Cache the token and re-authenticate once on 401;", "documented lifetimes differ (1 hour vs 60 seconds)."),
    ("Keep TLS verification on in production.", ""),
    ("Treat 202 as accepted, not done.", "Poll the task with a timeout and surface failureReason."),
    ("Page at 500 with a 1-based offset;", "size with /count, filter with /query, de-duplicate by ID."),
    ("Design for 429.", "Per-operation limits of 50 to 100 per minute; back off and serialize writes."),
    ("Push, don't poll.", "Webhooks for events and issues; reconcile hourly."),
    ("Never schedule device-touching calls.", "Command Runner and Path Trace are on demand, one device at a time."),
    ("Prefer the new resource model:", "/sites, /ipam, /sda, /networkDevices, /networkDeviceImages."),
    ("Gate every change on prerequisites:", "backup, archive, Managed and Reachable, no critical issues, compatibility."),
    ("Use bulk operations in waves by site.", ""),
    ("Validate before and after:", "readiness checks, validation workflows, compliance, health."),
    ("Put MCP behind an Observer account on loopback.", "The server does not enforce read-only."),
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
]
A('<section id="sources"><h2>Sources</h2><ul class="src">' +
  "".join(f'<li><a href="{u}" target="_blank" rel="noopener">{E(t)}</a></li>' for t, u in SRC) +
  '</ul><p class="note">Payloads marked illustrative must be checked against the operation schema in your release. Verify endpoints in Platform &gt; Developer Toolkit &gt; APIs before production use.</p></section>')

CSS = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "style.css")).read()
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
(function(){ var b=document.getElementById('theme-toggle'); var r=document.documentElement;
  try { var t=localStorage.getItem('catc-theme'); if (t) r.setAttribute('data-theme', t); } catch(e){}
  b.addEventListener('click', function(){ var dark = r.getAttribute('data-theme') ? r.getAttribute('data-theme')==='dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    var n = dark ? 'light' : 'dark'; r.setAttribute('data-theme', n); try { localStorage.setItem('catc-theme', n); } catch(e){} }); })();
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
for sid, part in PART_OF.items():
    body = body.replace(f'<section id="{sid}"><h2>', f'<section id="{sid}"><p class="eyebrow">{part}</p><h2>', 1)
FIRST = {part: items[0][0] for part, items in NAV}
top_nav = "".join(f'<a href="#{FIRST[p]}" data-part="{p}">{p}</a>' for p, _ in NAV)

page = f'''<meta charset="utf-8">
<title>Catalyst Center API Field Guide</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap">
<style>{CSS}</style>
<header class="site"><div class="in">
<a class="brand" href="#top"><b>Cisco<span>SE</span></b><small>Field reference</small></a>
<nav aria-label="Guide parts">{top_nav}</nav>
<button type="button" class="pill" id="theme-toggle">Light / dark</button>
</div></header>
<div class="strip"><b>CiscoSE</b> · Catalyst Center API field guide for customers integrating with other systems</div>
<div class="hero" id="top"><div class="in">
  <p class="eyebrow">Field guide · Release 3.3.1 (with 3.1.6 and 2.3.7.x deltas)</p>
  <h1>Cisco Catalyst Center API</h1>
  <p class="lead">A working reference for integrating Cisco Catalyst Center (formerly DNA Center) with other systems: how a call is served, which endpoint answers which question, how to automate safely in SD-Access (Software-Defined Access) and non-fabric networks, what is deprecated, and how to put AI agents on top through MCP (Model Context Protocol).</p>
  <p class="meta">Built from the Cisco DevNet Catalyst Center API reference (full spec through 3.1.6), the Platform User Guides 3.1.x, 3.2.x and 3.3.x, release notes through 3.3.1 (9 Sep 2026) and 3.2.3 (21 Sep 2026), the compatibility matrix, Cisco tech note 226435 and the official MCP server repository. Verified 23 Oct 2026. Confirm 3.2/3.3-only operations in <b>Platform &gt; Developer Toolkit &gt; APIs</b> on your cluster.</p>
  <div class="hbtns"><a class="hbtn solid" href="#overview">Start with the foundations</a><a class="hbtn" href="#changes">Deprecated APIs</a></div>
</div></div>
<div class="layout">
<aside class="side" aria-label="Sections"><details open><summary>Contents</summary>{nav_html}</details>
<div class="legend"><div><span class="sw" style="background:var(--accent)"></span>Stops at the controller (safe to poll)</div><div><span class="sw" style="background:var(--amber)"></span>Reaches the device (on demand)</div><div><span class="sw" style="background:var(--green)"></span>Writes configuration (async task)</div></div></aside>
<main>{body}</main></div>
<footer class="site"><div class="in"><b>Cisco<span>SE</span></b> · Catalyst Center API field guide · Release 3.3.1 with 3.1.6 and 2.3.7.x deltas · verified 23 Oct 2026</div></footer>
{data_script()}
<script>{JS}
{IJS}</script>'''
open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "index.html"), "w").write(page)
print(len(page))
