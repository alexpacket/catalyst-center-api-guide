import html, json

E = html.escape

# One entry per step in each sequence figure, same order as svg.py steps.
# t = title, d = what happens, c = request/response sample (illustrative values).
STEPS = {
"f2": [
  {"t": "Request a token", "d": "HTTP Basic authentication against the system API. Use a dedicated service account, never a personal login.",
   "c": "POST /dna/system/api/v1/auth/token\nAuthorization: Basic <base64(username:password)>\nContent-Type: application/json"},
  {"t": "Receive the token", "d": "The body carries one field, Token. The API reference gives a 60-minute lifetime; the 3.3.x prerequisites page says 60 seconds, so always handle 401.",
   "c": "200 OK\n{\n  \"Token\": \"eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...\"\n}"},
  {"t": "Call the Intent API with the token", "d": "Send the token in X-Auth-Token on every request. Page list calls at up to 500 records with a 1-based offset.",
   "c": "GET /dna/intent/api/v1/network-device?offset=1&limit=500\nX-Auth-Token: eyJ0eXAiOiJKV1Qi...\nContent-Type: application/json"},
  {"t": "Token and RBAC check", "d": "The controller validates the token and checks the caller's role and access groups. A missing permission returns 403, and access groups can silently narrow what a list returns.",
   "c": "403 Forbidden   <- role lacks the feature\n200 OK          <- allowed (results scoped to the account's sites)"},
  {"t": "Response", "d": "Intent API responses wrap results in a response array plus a version field.",
   "c": "200 OK\n{\n  \"response\": [\n    {\"hostname\": \"cat9k-access-01\",\n     \"managementIpAddress\": \"10.10.20.81\",\n     \"reachabilityStatus\": \"Reachable\",\n     \"id\": \"6d3eaa5d-bb39-4cc4-8881-4a2b2668d2dc\"}\n  ],\n  \"version\": \"1.0\"\n}"},
  {"t": "Time passes", "d": "Cache the token and reuse it. Logging in per call wastes rate-limit budget and adds latency.", "c": ""},
  {"t": "Call with an expired token", "d": "Any operation can be the one that hits expiry, so the retry logic belongs in your client wrapper, not in each call.",
   "c": "GET /dna/intent/api/v1/site-health\nX-Auth-Token: <expired token>"},
  {"t": "401 Unauthorized", "d": "The token is no longer valid. This is expected, not an outage.", "c": "401 Unauthorized"},
  {"t": "Re-authenticate once, then retry", "d": "Get a new token and replay the request one time. If it fails again, stop and alert: the credentials or account are the problem.",
   "c": "if r.status_code == 401 and not relogged:\n    self._login(); relogged = True\n    r = self.s.request(method, url, **kw)"},
],
"f3": [
  {"t": "Submit the write", "d": "Discovery, provisioning, SWIM and most configuration changes are asynchronous.",
   "c": "POST /dna/intent/api/v1/discovery\n{\n  \"name\": \"branch-42-scan\",\n  \"discoveryType\": \"Range\",\n  \"ipAddressList\": \"10.10.20.1-10.10.20.50\",\n  \"protocolOrder\": \"ssh\",\n  \"globalCredentialIdList\": [\"<cli-cred-id>\", \"<snmp-cred-id>\"]\n}"},
  {"t": "202 Accepted with a taskId", "d": "202 means queued, not done. Keep the taskId; the url field is a ready-made path to poll.",
   "c": "202 Accepted\n{\n  \"response\": {\n    \"taskId\": \"85c95140-50fc-4a57-994d-db58d3afe6b3\",\n    \"url\": \"/dna/intent/api/v1/task/85c95140-50fc-4a57-994d-db58d3afe6b3\"\n  },\n  \"version\": \"1.0\"\n}"},
  {"t": "Task created", "d": "The task engine owns the job from here, independent of your HTTP connection.", "c": ""},
  {"t": "The controller reaches devices", "d": "This is the only part of the flow that touches the network. It takes seconds to minutes depending on scope.", "c": ""},
  {"t": "Poll the task", "d": "Poll every 5 to 10 seconds with an overall timeout sized to the job.",
   "c": "GET /dna/intent/api/v1/task/85c95140-50fc-4a57-994d-db58d3afe6b3"},
  {"t": "Still running", "d": "No endTime yet means the task has not finished. Do not treat progress text as a result.",
   "c": "{\n  \"response\": {\n    \"isError\": false,\n    \"progress\": \"Discovery in progress\",\n    \"startTime\": 1761220000000\n  }\n}"},
  {"t": "Wait and repeat", "d": "Back off between polls and stop at your timeout. A task that never ends usually means an unreachable device.", "c": ""},
  {"t": "Poll again", "d": "Same call.", "c": "GET /dna/intent/api/v1/task/85c95140-50fc-4a57-994d-db58d3afe6b3"},
  {"t": "Finished", "d": "endTime is set. Check isError; on failure read failureReason. For some operations progress carries an ID you use next (for example the discovery ID or a fileId).",
   "c": "{\n  \"response\": {\n    \"isError\": false,\n    \"progress\": \"<discovery id>\",\n    \"endTime\": 1761220042000\n  }\n}"},
],
"f5": [
  {"t": "Find devices off the golden image", "d": "SWIM v2 (3.1.3+) lists devices with their image status.", "c": "GET /dna/intent/api/v1/networkDeviceImages?offset=1&limit=500"},
  {"t": "Image status", "d": "Build the wave from devices whose image is not the marked golden image for their product series.", "c": ""},
  {"t": "Run readiness checks", "d": "Checks flash space, connectivity and prerequisites per device before any change window.", "c": "POST /dna/intent/api/v1/networkDeviceImages/{id}/readinessChecks"},
  {"t": "Open a change request", "d": "Attach the device list and readiness results to the change in your ITSM tool.", "c": ""},
  {"t": "Change approved", "d": "The approval fixes the maintenance window for activation.", "c": ""},
  {"t": "Bulk distribute", "d": "Copies the image to flash ahead of the window. Build the body from the operation schema in your release.", "c": "POST /dna/intent/api/v1/networkDeviceImages/distribute/bulk"},
  {"t": "Task returned", "d": "Distribution is asynchronous.", "c": "202 Accepted\n{\"response\": {\"taskId\": \"...\"}, \"version\": \"1.0\"}"},
  {"t": "Image copied to devices", "d": "Runs before the window, so the window only covers install and reload.", "c": ""},
  {"t": "Wait for distribution", "d": "Poll with a long timeout; large waves take time.", "c": "GET /dna/intent/api/v1/task/{taskId}"},
  {"t": "Window opens", "d": "Activation causes a reload. Only proceed inside the approved window.", "c": ""},
  {"t": "Bulk activate", "d": "Installs and reloads the devices in the wave.", "c": "POST /dna/intent/api/v1/networkDeviceImages/activate/bulk"},
  {"t": "Install and reload", "d": "Devices are unavailable during reload; expect reachability events.", "c": ""},
  {"t": "Check validation results", "d": "Compare custom post-checks with the pre-checks.", "c": "GET /dna/intent/api/v1/networkDeviceImages/validationResults"},
  {"t": "Close the change", "d": "Attach validation results and task outcomes as evidence.", "c": ""},
],
"f8": [
  {"t": "Register a webhook destination", "d": "Tell the controller where to send events. Confirm the cluster can reach the URL first. Field names are illustrative; check your release.",
   "c": "POST /dna/intent/api/v1/event/webhook\n{\n  \"name\": \"noc-listener\",\n  \"url\": \"https://hooks.example.com/catc\",\n  \"method\": \"POST\",\n  \"trustCert\": true\n}"},
  {"t": "Subscribe events to it", "d": "Use the REST subscription operation; the generic /event/subscription was deprecated in 2.3.7.9.",
   "c": "POST /dna/intent/api/v1/event/subscription/rest\n[{\n  \"name\": \"device-unreachable\",\n  \"subscriptionEndpoints\": [{\"instanceId\": \"<webhook id>\",\n     \"subscriptionDetails\": {\"connectorType\": \"REST\"}}],\n  \"filter\": {\"eventIds\": [\"NETWORK-DEVICES-3-506\"]}\n}]"},
  {"t": "Setup done", "d": "Everything after this point runs without your code polling anything.", "c": ""},
  {"t": "Something happens in the network", "d": "Devices report through telemetry; the controller sees a device stop responding.", "c": ""},
  {"t": "Correlated into an event", "d": "Assurance turns raw signals into a catalog event with severity and category.", "c": ""},
  {"t": "Event pushed to your listener", "d": "An HTTP POST with a JSON body. The exact fields depend on the event; this sample is illustrative.",
   "c": "POST https://hooks.example.com/catc\n{\n  \"eventId\": \"NETWORK-DEVICES-3-506\",\n  \"name\": \"Network Device Unreachable\",\n  \"severity\": 1,\n  \"category\": \"ERROR\",\n  \"details\": {\"Device IP\": \"10.10.20.81\"}\n}"},
  {"t": "Acknowledge fast", "d": "Return 200 immediately and queue the work, so slow processing never blocks delivery.", "c": "200 OK"},
  {"t": "Reconcile hourly", "d": "Pull recent Assurance events to catch anything the listener missed during an outage.",
   "c": "GET /dna/data/api/v1/assuranceEvents?deviceFamily=Switches%20and%20Hubs&startTime=<epoch ms>"},
],
"f9": [
  {"t": "Find the target devices", "d": "Filter the device list, for example by platform.", "c": "GET /dna/intent/api/v1/network-device?platformId=C9300-48P"},
  {"t": "Device UUIDs", "d": "Collect the id of each device you will run commands on.", "c": "{\"response\": [{\"id\": \"6d3eaa5d-...\", \"hostname\": \"cat9k-access-01\"}], \"version\": \"1.0\"}"},
  {"t": "Submit read-only commands", "d": "Command Runner accepts show commands only.",
   "c": "POST /dna/intent/api/v1/network-device-poller/cli/read-request\n{\n  \"commands\": [\"show version\", \"show ip int brief\"],\n  \"deviceUuids\": [\"6d3eaa5d-...\"],\n  \"timeout\": 0\n}"},
  {"t": "Task returned", "d": "Like every write, this is asynchronous.", "c": "202 Accepted\n{\"response\": {\"taskId\": \"...\", \"url\": \"/dna/intent/api/v1/task/...\"}, \"version\": \"1.0\"}"},
  {"t": "Queued", "d": "The task engine schedules the job.", "c": ""},
  {"t": "SSH to the device", "d": "This touches the device: run it on demand, for a handful of devices, never on a timer.", "c": ""},
  {"t": "Output collected", "d": "The controller stores the output as a file.", "c": ""},
  {"t": "Poll the task", "d": "Same task API as any other write.", "c": "GET /dna/intent/api/v1/task/{taskId}"},
  {"t": "fileId in progress", "d": "When finished, progress is a JSON string that contains the fileId.", "c": "{\"response\": {\"progress\": \"{\\\"fileId\\\":\\\"d3a7...\\\"}\", \"endTime\": 1761220100000}}"},
  {"t": "Download the output", "d": "Fetch the file by its ID.", "c": "GET /dna/intent/api/v1/file/d3a7..."},
  {"t": "Output per device and command", "d": "Results are grouped by device and command, with success and failure buckets.",
   "c": "[{\"deviceUuid\": \"6d3eaa5d-...\",\n  \"commandResponses\": {\"SUCCESS\": {\"show version\": \"Cisco IOS XE Software...\"},\n                       \"FAILURE\": {}, \"BLACKLISTED\": {}}}]"},
],
}


def stepper(fid):
    return (f'<div class="stepbar" data-fig="{fid}" role="group" aria-label="Step through this flow">'
            f'<button type="button" class="sbtn" data-act="prev">Back</button>'
            f'<button type="button" class="sbtn solid" data-act="next">Step through</button>'
            f'<button type="button" class="sbtn" data-act="all">Show all</button>'
            f'<span class="scount" aria-live="polite">All steps shown</span></div>'
            f'<div class="steppanel" data-fig="{fid}" aria-live="polite" hidden>'
            f'<p class="sp-t"></p><p class="sp-d"></p><pre class="sp-c"><code></code></pre></div>')


PATHS = {
  "inv": {"label": "Inventory read", "keys": ["client", "gw", "inv"],
          "text": "Answered from the controller database. Safe to schedule; the data is as fresh as the last device sync.",
          "code": "GET /dna/intent/api/v1/network-device?offset=1&limit=500"},
  "asr": {"label": "Assurance query", "keys": ["client", "gw", "asr", "tel", "dev"],
          "text": "Answered from Assurance data that devices already exported. Safe to schedule; no device is contacted by your call.",
          "code": "GET /dna/intent/api/v1/site-health\nPOST /dna/data/api/v1/assuranceEvents/query"},
  "prov": {"label": "Provision or SWIM", "keys": ["client", "gw", "task", "push", "dev"],
           "text": "Becomes a task that changes devices. Returns 202 and a taskId; gate it on change prerequisites.",
           "code": "POST /dna/intent/api/v1/networkDeviceImages/distribute/bulk\n-> 202 {taskId}"},
  "cli": {"label": "Command Runner", "keys": ["client", "gw", "task", "push", "dev"],
          "text": "Becomes a task that opens SSH to devices. On demand only, for a handful of devices.",
          "code": "POST /dna/intent/api/v1/network-device-poller/cli/read-request\n-> 202 {taskId}"},
}

CHOOSE = {
  "start": {"q": "What is the scope of your question?", "opts": [["Many devices, sites or clients", "many"], ["One device or one flow", "one"]]},
  "many": {"q": "What do you need?", "opts": [["Current state", "r_state"], ["A trend over a time range", "r_trend"], ["To be told when it changes", "r_event"]]},
  "one": {"q": "What do you need?", "opts": [["Its stored details", "r_detail"], ["Live CLI output", "r_cli"], ["The path between two hosts", "r_path"]]},
  "r_state": {"out": "o0", "t": "Intent health and query APIs", "b": "read",
              "d": "Fleet-wide state from the controller. Schedule every 5 to 15 minutes; page at 500.",
              "c": "GET /dna/intent/api/v1/site-health\nPOST /dna/intent/api/v1/networkDevices/query"},
  "r_trend": {"out": "o1", "t": "Assurance data APIs", "b": "read",
              "d": "Let the controller aggregate over time instead of pulling raw rows.",
              "c": "POST /dna/data/api/v1/networkDevices/trendAnalytics\nPOST /dna/data/api/v1/assuranceEvents/query"},
  "r_event": {"out": "o2", "t": "Event subscriptions (webhooks)", "b": "read",
              "d": "Register a webhook, subscribe events, reconcile hourly. No polling loop.",
              "c": "POST /dna/intent/api/v1/event/webhook\nPOST /dna/intent/api/v1/event/subscription/rest"},
  "r_detail": {"out": "o0", "t": "Device detail from inventory", "b": "read",
               "d": "Stored details come from the controller database; no device is contacted.",
               "c": "GET /dna/intent/api/v1/networkDevices/{id}"},
  "r_cli": {"out": "o3", "t": "Command Runner", "b": "dev",
            "d": "Read-only show commands over SSH. On demand, never scheduled.",
            "c": "POST /dna/intent/api/v1/network-device-poller/cli/read-request"},
  "r_path": {"out": "o3", "t": "Path Trace", "b": "dev",
             "d": "Traces the path between two endpoints. Use /pathTraces from 3.2.2, /flow-analysis on earlier releases.",
             "c": "POST /dna/intent/api/v1/pathTraces          (3.2.2+)\nPOST /dna/intent/api/v1/flow-analysis       (earlier)"},
}

CODES = {
  "200": ["c0", "Parse the body", "Read response[] and version. An empty list is valid; see the symptom picker below if you expected data.", "data = r.json()[\"response\"]"],
  "202": ["c1", "Poll the task", "Queued, not done. Poll the task until endTime is set, with a timeout, then check isError.", "task = cc.wait_task(r.json()[\"response\"][\"taskId\"])"],
  "401": ["c2", "Re-authenticate once", "Token expired or invalid. Get a new token, retry once, then fail loudly.", "self._login(); r = self.s.request(method, url, **kw)"],
  "403": ["c4", "Do not retry", "The account's role or access group does not allow this operation or site. Fix RBAC, not the code.", "raise PermissionError(r.text)"],
  "404": ["c4", "Do not retry", "Wrong path, wrong ID, or an operation your release does not have (check the deprecation lookup).", "log.error(\"%s %s -> 404\", method, path)"],
  "429": ["c3", "Back off and retry", "Per-operation rate limit hit. No rate-limit headers are documented, so back off 2 s, 4 s, 8 s up to 60 s.", "time.sleep(delay); delay = min(delay * 2, 60)"],
  "500": ["c3", "Back off, then capture", "Retry a few times with backoff; if it persists, capture URL, body and response for a TAC case.", "time.sleep(delay); delay = min(delay * 2, 60)"],
  "503": ["c3", "Back off and retry", "The service is temporarily unavailable, often during controller maintenance.", "time.sleep(delay); delay = min(delay * 2, 60)"],
}

SYMPTOMS = {
  "s1": ["202 but nothing changed", ["top", "L0", "L1", "L2"], "Read the task: isError is true and failureReason says why (bad payload, device state, missing prerequisite)."],
  "s2": ["Task never finishes", ["top", "L0", "L1", "L3"], "endTime stays empty: the device is busy or unreachable, or the job is large. Enforce a timeout and alert."],
  "s3": ["Empty list", ["top", "R0", "R1", "R2", "R3"], "Check filters and the 1-based offset, then the account's access groups. If the UI shows data and the API does not, open a TAC case."],
  "s4": ["Different rows on each page", ["top", "R0", "R1"], "Known 3.2.3 issue: repeated calls with the same limit and offset can return different site IDs. Sort client-side and de-duplicate by ID."],
}

DEPRECATED = [
  {"p": r"/v2/site/count|/site/count", "label": "/site/count, /v2/site/count", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites count operations", "note": "Part of the legacy site family."},
  {"p": r"/site-member/", "label": "/site-member/{id}/member", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites and device-to-site operations", "note": ""},
  {"p": r"/assign-device-to-site/", "label": "POST /assign-device-to-site/{siteId}/device", "rel": "2.3.7.6 (Sunset banner)", "year": 2024, "mon": 8, "rep": "POST /dna/intent/api/v1/networkDevices/assignToSite/apply", "note": ""},
  {"p": r"/credential-to-site/", "label": "/v1 and /v2 credential-to-site/{siteId}", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "PUT /dna/intent/api/v1/sites/{id}/deviceCredentials, then …/deviceCredentials/apply", "note": ""},
  {"p": r"/(v1|v2)/site(/|\?|$)", "label": "/site, /v2/site (create, get, update, delete)", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites family (GET /sites/{id} from 3.1.6; POST /v2/floors etc.)", "note": "DevNet's own Sites guide still shows /site; many tutorials use it."},
  {"p": r"/reserve-ip-subpool", "label": "POST/PUT /reserve-ip-subpool/{siteId}", "rel": "Sunset banner (3.1.6 reference)", "year": None, "mon": None, "rep": "/dna/intent/api/v1/ipam/siteIpAddressPools", "note": ""},
  {"p": r"/business/sda", "label": "/business/sda/* (about 40 operations)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/sda/* (fabricSites, layer3VirtualNetworks, anycastGateways, fabricDevices, transitNetworks)", "note": ""},
  {"p": r"/event/subscription/?($|\?)", "label": "/event/subscription (generic POST/PUT/GET)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/event/subscription/rest and the per-channel subscription operations", "note": ""},
  {"p": r"/image/distribution", "label": "POST /image/distribution", "rel": "3.1.3 (Sunset)", "year": 2025, "mon": 6, "rep": "/networkDeviceImages/{id}/distribute or /networkDeviceImages/distribute/bulk", "note": ""},
  {"p": r"/image/activation/device", "label": "POST /image/activation/device", "rel": "3.1.3 (Sunset)", "year": 2025, "mon": 6, "rep": "/networkDeviceImages/{id}/activate or /networkDeviceImages/activate/bulk", "note": ""},
  {"p": r"/network-device-config", "label": "GET /network-device-config", "rel": "3.1.3", "year": 2025, "mon": 6, "rep": "/dna/intent/api/v1/networkDeviceConfigFiles", "note": ""},
  {"p": r"/system/api/v1/(role|roles)", "label": "/dna/system/api/v1/role, /roles, /role/permissions", "rel": "3.1.5 (Sunset)", "year": 2025, "mon": 10, "rep": "/dna/system/api/v2/roles, /v2/roles/Permissions, /dna/system/api/v1/accessGroups", "note": ""},
  {"p": r"/flow-analysis", "label": "POST /flow-analysis", "rel": "Superseded in 3.2.2 (not deprecated)", "year": None, "mon": None, "rep": "POST /dna/intent/api/v1/pathTraces on 3.2.2 and later", "note": "Still available; prefer the new operation on 3.2.2+."},
  {"p": r"cisco\.dnac", "label": "Ansible collection cisco.dnac", "rel": "Deprecated in the Ansible community package", "year": None, "mon": None, "rep": "cisco.catalystcenter", "note": "Slated for removal from Ansible 14."},
  {"p": r"multivendor", "label": "Multivendor SDK (device packs)", "rel": "Deprecated", "year": None, "mon": None, "rep": "SNMP MIB-II third-party device visibility", "note": "Inventory, topology and reachability only."},
]


def data_script():
    blob = {"steps": STEPS, "paths": PATHS, "choose": CHOOSE, "codes": CODES, "symptoms": SYMPTOMS, "dep": DEPRECATED}
    return '<script type="application/json" id="guide-data">' + json.dumps(blob).replace("</", "<\\/") + "</script>"


def path_tool():
    btns = "".join(f'<button type="button" class="chip" data-path="{k}" aria-pressed="false">{E(v["label"])}</button>' for k, v in PATHS.items())
    return (f'<div class="tool" id="pathtool"><p class="tool-h">Trace a call type through the diagram</p><div class="chips">{btns}'
            f'<button type="button" class="chip ghost" data-path="">Show all</button></div>'
            f'<div class="tool-out" aria-live="polite"><p class="to-d">Pick a call type to light up the path it takes.</p><pre class="to-c" hidden><code></code></pre></div></div>')


def rate_tool():
    return '''<div class="tool" id="ratetool"><p class="tool-h">Rate-limit budget calculator</p>
<div class="fields">
<label for="rt-rec">Records to fetch<input id="rt-rec" type="number" min="0" step="100" value="5000"></label>
<label for="rt-page">Page size (max 500)<input id="rt-page" type="number" min="1" max="500" value="500"></label>
<label for="rt-extra">Extra calls per record<input id="rt-extra" type="number" min="0" step="1" value="0"></label>
<label for="rt-limit">Operation limit per minute<input id="rt-limit" type="number" min="1" value="50"></label>
</div><div class="tool-out" aria-live="polite"><p class="to-d" id="rt-out"></p></div>
<p class="tool-note">Default 50 per the Platform User Guide; read the real limit on each operation's Features tab. Per-record detail calls are what usually blow the budget.</p></div>'''


def choose_tool():
    return ('<div class="tool" id="choosetool"><p class="tool-h">Answer two questions</p>'
            '<p class="ct-q"></p><div class="chips ct-opts"></div>'
            '<div class="tool-out" aria-live="polite" hidden><p class="ct-t"></p><p class="to-d ct-d"></p><pre class="to-c"><code></code></pre></div>'
            '<button type="button" class="chip ghost ct-reset">Start over</button></div>')


def code_tool():
    btns = "".join(f'<button type="button" class="chip mono" data-code="{k}" aria-pressed="false">{k}</button>' for k in CODES)
    return (f'<div class="tool" id="codetool"><p class="tool-h">Pick the status code you got</p><div class="chips">{btns}</div>'
            f'<div class="tool-out" aria-live="polite" hidden><p class="ct-t"></p><p class="to-d"></p><pre class="to-c"><code></code></pre></div></div>')


def sym_tool():
    btns = "".join(f'<button type="button" class="chip" data-sym="{k}" aria-pressed="false">{E(v[0])}</button>' for k, v in SYMPTOMS.items())
    return (f'<div class="tool" id="symtool"><p class="tool-h">Pick the symptom</p><div class="chips">{btns}'
            f'<button type="button" class="chip ghost" data-sym="">Show all</button></div>'
            f'<div class="tool-out" aria-live="polite" hidden><p class="to-d"></p></div></div>')


def dep_tool():
    ex = ["/dna/intent/api/v1/site", "/business/sda/fabric", "/image/distribution", "/reserve-ip-subpool/{siteId}", "/dna/system/api/v1/roles", "/sites/{id}/dnsSettings"]
    chips = "".join(f'<button type="button" class="chip mono" data-ex="{E(e)}">{E(e)}</button>' for e in ex)
    return f'''<div class="tool" id="deptool"><p class="tool-h">Is this API deprecated?</p>
<label for="dep-in" class="sr">API path or tool name</label>
<input id="dep-in" type="search" placeholder="Paste a path, e.g. /dna/intent/api/v1/site" autocomplete="off" spellcheck="false">
<div class="chips">{chips}</div>
<div class="tool-out" aria-live="polite" id="dep-out"><p class="to-d">Paste a path or click an example. Checks this guide's list of deprecated, Sunset and superseded operations.</p></div></div>'''


def search_tool():
    return '''<div class="tool slim"><label for="q-in" class="tool-h">Filter questions</label>
<input id="q-in" type="search" placeholder="Try health, compliance, image, client…" autocomplete="off"><p class="tool-note" id="q-count" aria-live="polite"></p></div>'''


JS = r'''
(function(){
var D = JSON.parse(document.getElementById('guide-data').textContent);
function $(s, r){ return (r || document).querySelector(s); }
function $$(s, r){ return Array.prototype.slice.call((r || document).querySelectorAll(s)); }
function figSvg(id){ var m = document.querySelector('marker[id^="' + id + '-"]'); return m ? m.closest('svg') : null; }
function dimKeys(svg, keys){ $$('[data-k]', svg).forEach(function(g){ g.classList.toggle('dim', !!keys && keys.indexOf(g.getAttribute('data-k')) < 0); }); }
function press(group, btn){ $$('.chip', group).forEach(function(b){ b.setAttribute('aria-pressed', b === btn ? 'true' : 'false'); }); }

/* Step-through sequence diagrams */
$$('.stepbar').forEach(function(bar){
  var fid = bar.getAttribute('data-fig'), svg = figSvg(fid), steps = $$('.st', svg), data = D.steps[fid] || [];
  var panel = $('.steppanel[data-fig="' + fid + '"]'), count = $('.scount', bar), cur = -1;
  function render(){
    steps.forEach(function(s, i){ s.classList.toggle('dim', cur >= 0 && i !== cur); s.classList.toggle('cur', i === cur); });
    if (cur < 0) { panel.hidden = true; count.textContent = 'All steps shown'; $('[data-act="next"]', bar).textContent = 'Step through'; return; }
    var d = data[cur] || {};
    panel.hidden = false;
    $('.sp-t', panel).textContent = (cur + 1) + '. ' + (d.t || '');
    $('.sp-d', panel).textContent = d.d || '';
    var pre = $('.sp-c', panel); pre.hidden = !d.c; $('code', pre).textContent = d.c || '';
    count.textContent = 'Step ' + (cur + 1) + ' of ' + steps.length;
    $('[data-act="next"]', bar).textContent = cur === steps.length - 1 ? 'Finish' : 'Next';
  }
  bar.addEventListener('click', function(e){
    var b = e.target.closest('button'); if (!b) return;
    var a = b.getAttribute('data-act');
    if (a === 'next') cur = cur >= steps.length - 1 ? -1 : cur + 1;
    if (a === 'prev') cur = cur <= 0 ? (cur === 0 ? -1 : steps.length - 1) : cur - 1;
    if (a === 'all') cur = -1;
    render();
  });
  steps.forEach(function(s, i){ s.addEventListener('click', function(){ cur = i; render(); }); });
});

/* Call path selector */
var pt = $('#pathtool');
if (pt) { var f1 = figSvg('f1');
  pt.addEventListener('click', function(e){ var b = e.target.closest('.chip'); if (!b) return; press(pt, b);
    var k = b.getAttribute('data-path'), p = D.paths[k];
    dimKeys(f1, p ? p.keys : null);
    $('.to-d', pt).textContent = p ? p.text : 'Pick a call type to light up the path it takes.';
    var pre = $('.to-c', pt); pre.hidden = !p; $('code', pre).textContent = p ? p.code : '';
  }); }

/* Rate calculator */
var rt = $('#ratetool');
if (rt) {
  function calc(){
    var rec = Math.max(0, +$('#rt-rec').value || 0), page = Math.min(500, Math.max(1, +$('#rt-page').value || 1));
    var extra = Math.max(0, +$('#rt-extra').value || 0), lim = Math.max(1, +$('#rt-limit').value || 1);
    var calls = Math.ceil(rec / page) + rec * extra, mins = calls / lim, pace = 60 / lim;
    var t = calls.toLocaleString() + ' calls. At ' + lim + ' per minute that takes at least ' +
      (mins < 1 ? Math.ceil(mins * 60) + ' seconds' : (Math.round(mins * 10) / 10).toLocaleString() + ' minutes') +
      '; pace one call every ' + (Math.round(pace * 10) / 10) + ' s to avoid 429.';
    if (extra > 0 && rec * extra > lim * 15) t += ' Most of this is per-record detail calls: use a /query or bulk operation instead.';
    $('#rt-out').textContent = t;
  }
  $$('input', rt).forEach(function(i){ i.addEventListener('input', calc); }); calc();
}

/* Decision tree */
var ct = $('#choosetool');
if (ct) { var f7 = figSvg('f7');
  function go(node){
    var n = D.choose[node], out = $('.tool-out', ct);
    if (n.q) { $('.ct-q', ct).textContent = n.q; out.hidden = true; dimKeys(f7, null);
      $('.ct-opts', ct).innerHTML = '';
      n.opts.forEach(function(o){ var b = document.createElement('button'); b.type = 'button'; b.className = 'chip'; b.textContent = o[0];
        b.addEventListener('click', function(){ go(o[1]); }); $('.ct-opts', ct).appendChild(b); });
    } else { $('.ct-q', ct).textContent = 'Use this:'; $('.ct-opts', ct).innerHTML = ''; out.hidden = false;
      $('.ct-t', out).innerHTML = ''; var tag = document.createElement('span'); tag.className = 'bdg bdg-' + n.b;
      tag.textContent = n.b === 'dev' ? 'Reaches the device' : 'Stops at the controller';
      $('.ct-t', out).appendChild(document.createTextNode(n.t + ' ')); $('.ct-t', out).appendChild(tag);
      $('.ct-d', out).textContent = n.d; $('code', out).textContent = n.c; dimKeys(f7, [n.out]); }
  }
  $('.ct-reset', ct).addEventListener('click', function(){ go('start'); }); go('start'); }

/* Status codes */
var cd = $('#codetool');
if (cd) { var f12 = figSvg('f12');
  cd.addEventListener('click', function(e){ var b = e.target.closest('.chip'); if (!b) return; press(cd, b);
    var c = D.codes[b.getAttribute('data-code')], out = $('.tool-out', cd); out.hidden = false;
    $('.ct-t', out).textContent = b.getAttribute('data-code') + ': ' + c[1]; $('.to-d', out).textContent = c[2]; $('code', out).textContent = c[3];
    dimKeys(f12, [c[0]]); }); }

/* Symptoms */
var sy = $('#symtool');
if (sy) { var f13 = figSvg('f13');
  sy.addEventListener('click', function(e){ var b = e.target.closest('.chip'); if (!b) return; press(sy, b);
    var s = D.symptoms[b.getAttribute('data-sym')], out = $('.tool-out', sy);
    out.hidden = !s; if (s) $('.to-d', out).textContent = s[2]; dimKeys(f13, s ? s[1] : null); }); }

/* Deprecation lookup */
var dt = $('#deptool');
if (dt) { var inp = $('#dep-in'), out = $('#dep-out'), now = new Date(2026, 9, 23);
  var res = D.dep.map(function(d){ return {d: d, re: new RegExp(d.p, 'i')}; });
  function look(){
    var q = inp.value.trim(); out.innerHTML = '';
    if (!q) { var p0 = document.createElement('p'); p0.className = 'to-d'; p0.textContent = 'Paste a path or click an example. Checks this guide’s list of deprecated, Sunset and superseded operations.'; out.appendChild(p0); return; }
    var hit = null; for (var i = 0; i < res.length; i++) { if (res[i].re.test(q)) { hit = res[i].d; break; } }
    var p = document.createElement('p'); p.className = 'dep-v ' + (hit ? 'warn' : 'ok');
    p.textContent = hit ? 'Deprecated or superseded: ' + hit.label : 'Not in this guide’s deprecation list';
    out.appendChild(p);
    var dl = document.createElement('dl');
    function row(k, v){ if (!v) return; var dt_ = document.createElement('dt'); dt_.textContent = k; var dd = document.createElement('dd'); dd.textContent = v; dl.appendChild(dt_); dl.appendChild(dd); }
    if (hit) {
      row('Flagged', hit.rel); row('Use instead', hit.rep);
      if (hit.year) { var e = new Date(hit.year + 1, hit.mon - 1, 1);
        var lbl = e.toLocaleDateString('en-US', {month: 'short', year: 'numeric'});
        row('Removal allowed from', lbl + (e <= now ? ' (window has passed: it can disappear in any release)' : ' (window still open)')); }
      row('Note', hit.note);
    } else {
      row('Next step', 'Open the operation in Platform > Developer Toolkit > APIs on your cluster and look for a Deprecated or Sunset banner. 3.2.x and 3.3.1 list no new API deprecations.');
    }
    out.appendChild(dl);
  }
  inp.addEventListener('input', look);
  $$('[data-ex]', dt).forEach(function(b){ b.addEventListener('click', function(){ inp.value = b.getAttribute('data-ex'); look(); }); });
}

/* Question table filter */
var qi = $('#q-in');
if (qi) { var rows = $$('#qtable tbody tr'), qc = $('#q-count');
  qi.addEventListener('input', function(){ var q = qi.value.trim().toLowerCase(), n = 0;
    rows.forEach(function(r){ var show = !q || r.textContent.toLowerCase().indexOf(q) >= 0; r.hidden = !show; if (show) n++; });
    qc.textContent = q ? n + ' of ' + rows.length + ' questions match' : ''; }); }
})();
'''
