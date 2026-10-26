import html, json

E = html.escape

# One entry per step in each sequence figure, same order as svg.py steps.
# t = title, d = what happens, c = request/response sample (illustrative values).
STEPS = {
"f2": [
  {"t": "Request a token", "d": "HTTP Basic authentication against the system API. Use a dedicated service account, never a personal login.",
   "c": "POST /dna/system/api/v1/auth/token\nAuthorization: Basic <base64(username:password)>\nContent-Type: application/json"},
  {"t": "Receive the token", "d": "The body carries one field, Token. The API reference gives a 60-minute lifetime; the 3.1.x to 3.3.x Platform User Guides say 60 seconds, so always handle 401.",
   "c": "200 OK\n{\n  \"Token\": \"eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9...\"\n}"},
  {"t": "Call the Intent API with the token", "d": "Send the token in X-Auth-Token on every request. Page list calls at up to 500 records with a 1-based offset.",
   "c": "GET /dna/intent/api/v1/network-device?offset=1&limit=500\nX-Auth-Token: eyJ0eXAiOiJKV1Qi...\nContent-Type: application/json"},
  {"t": "Token and RBAC check", "d": "The controller validates the token and checks the caller's role and access groups. A missing permission returns 403, and access groups can silently narrow what a list returns.",
   "c": "403 Forbidden   <- role lacks the feature\n200 OK          <- allowed (results scoped to the account's sites)"},
  {"t": "Response", "d": "Intent API responses wrap results in a response field (an array for lists, an object for single items) plus a version field.",
   "c": "200 OK\n{\n  \"response\": [\n    {\"hostname\": \"cat9k-access-01\",\n     \"managementIpAddress\": \"10.10.20.81\",\n     \"reachabilityStatus\": \"Reachable\",\n     \"id\": \"6d3eaa5d-bb39-4cc4-8881-4a2b2668d2dc\"}\n  ],\n  \"version\": \"1.0\"\n}"},
  {"t": "Time passes", "d": "Cache the token and reuse it. Logging in per call wastes rate-limit budget and adds latency.", "c": ""},
  {"t": "Call with an expired token", "d": "Any operation can be the one that hits expiry, so the retry logic belongs in your client wrapper, not in each call.",
   "c": "GET /dna/intent/api/v1/site-health\nX-Auth-Token: <expired token>"},
  {"t": "401 Unauthorized", "d": "The token is no longer valid. This is expected, not an outage.", "c": "401 Unauthorized"},
  {"t": "Re-authenticate once, then retry", "d": "Get a new token and replay the request one time. If it fails again, stop and alert: the credentials or account are the problem.",
   "c": "if r.status_code == 401 and not relogged:\n    self._login(); relogged = True\n    r = self.s.request(method, url, **kw)"},
],
"f3": [
  {"t": "Submit the write", "d": "Provisioning, SWIM, discovery and most configuration changes are asynchronous. This example provisions a wired device to its site, the step before it can take a fabric role.",
   "c": "POST /dna/intent/api/v1/sda/provisionDevices\n[{\n  \"siteId\": \"<building or floor id>\",\n  \"networkDeviceId\": \"<device id>\"\n}]"},
  {"t": "202 Accepted with a taskId", "d": "202 means queued, not done. Keep the taskId. The url field still points at the older /task path; poll /tasks/{id} instead.",
   "c": "202 Accepted\n{\n  \"response\": {\n    \"taskId\": \"85c95140-50fc-4a57-994d-db58d3afe6b3\",\n    \"url\": \"/dna/intent/api/v1/task/85c95140-50fc-4a57-994d-db58d3afe6b3\"\n  },\n  \"version\": \"1.0\"\n}"},
  {"t": "Task created", "d": "The task engine owns the job from here, independent of your HTTP connection.", "c": ""},
  {"t": "The controller reaches devices", "d": "This is the only part of the flow that touches the network. It takes seconds to minutes depending on scope.", "c": ""},
  {"t": "Poll the task", "d": "Poll every 5 to 10 seconds with an overall timeout sized to the job. /tasks/{id} replaced /task/{taskId}, Sunset since 2.3.7.6.",
   "c": "GET /dna/intent/api/v1/tasks/85c95140-50fc-4a57-994d-db58d3afe6b3"},
  {"t": "Still running", "d": "Status PENDING means the task has not finished.",
   "c": "{\n  \"response\": {\n    \"id\": \"85c95140-50fc-4a57-994d-db58d3afe6b3\",\n    \"status\": \"PENDING\",\n    \"startTime\": 1761220000000\n  },\n  \"version\": \"1.0\"\n}"},
  {"t": "Wait and repeat", "d": "Back off between polls and stop at your timeout. A task that never ends usually means an unreachable device.", "c": ""},
  {"t": "Poll again", "d": "Same call.", "c": "GET /dna/intent/api/v1/tasks/85c95140-50fc-4a57-994d-db58d3afe6b3"},
  {"t": "Finished", "d": "Status SUCCESS or FAILURE, with endTime set. On FAILURE read failureReason from /tasks/{id}/detail. resultLocation points to task-specific results (for example a new object's ID or an exported file).",
   "c": "{\n  \"response\": {\n    \"status\": \"SUCCESS\",\n    \"endTime\": 1761220042000,\n    \"resultLocation\": \"<server-relative URL>\"\n  }\n}\n\nGET /dna/intent/api/v1/tasks/{id}/detail   <- failureReason, progress, data"},
],
"f5": [
  {"t": "Find devices off the golden image", "d": "networkDeviceImages (2.3.7.9+) reports each device's status against the golden image tagged for its site and product. Filter to OUTDATED.", "c": "GET /dna/intent/api/v1/networkDeviceImages?networkDeviceImageStatus=OUTDATED&siteId=<id>&sortBy=id&order=asc&offset=1&limit=500"},
  {"t": "Image status", "d": "OUTDATED devices are ready for update. UNKNOWN means no golden image is tagged: tag one first with POST /images/{id}/sites/{siteId}/tagGolden.", "c": ""},
  {"t": "Run readiness checks", "d": "Each check is a task. Wait for it, read the results at the task's resultLocation, and drop devices with a FAILED result.", "c": "POST /dna/intent/api/v1/networkDeviceImages/{id}/readinessChecks\nGET  /dna/intent/api/v1/tasks/{taskId}          -> resultLocation\nGET  <resultLocation>                             -> validation results"},
  {"t": "Open a change request", "d": "Attach the device list and readiness results to the change in your ITSM tool.", "c": ""},
  {"t": "Change approved", "d": "The approval fixes the maintenance window. Record it in Catalyst Center so Assurance does not alert while devices reload.", "c": "POST /dna/intent/api/v1/networkDeviceMaintenanceSchedules\n{\"description\": \"CHG0012345\",\n \"networkDeviceIds\": [...],\n \"maintenanceSchedule\": {\"startTime\": <epoch ms>, \"endTime\": <epoch ms>}}"},
  {"t": "Bulk distribute", "d": "Copies the image to flash ahead of the window, for devices that passed readiness. Build the body from the operation schema in your release.", "c": "POST /dna/intent/api/v1/networkDeviceImages/distribute/bulk"},
  {"t": "Task returned", "d": "Distribution is asynchronous; read the taskId from the response.", "c": "{\"response\": {\"taskId\": \"...\"}, \"version\": \"1.0\"}"},
  {"t": "Image copied to devices", "d": "Runs before the window, so the window only covers install and reload.", "c": ""},
  {"t": "Wait for distribution", "d": "Poll with a long timeout; per-device progress is in networkDeviceImageUpdates.", "c": "GET /dna/intent/api/v1/tasks/{taskId}\nGET /dna/intent/api/v1/networkDeviceImageUpdates?parentId={taskId}"},
  {"t": "Window opens", "d": "Devices show managementState UNDER_MAINTENANCE. Activation causes a reload: only proceed inside the approved window.", "c": ""},
  {"t": "Bulk activate", "d": "Installs and reloads the devices in the wave.", "c": "POST /dna/intent/api/v1/networkDeviceImages/activate/bulk"},
  {"t": "Install and reload", "d": "Devices are unavailable during reload; the maintenance schedule keeps Assurance from raising alerts.", "c": ""},
  {"t": "Check validation results", "d": "Compare custom post-checks with the pre-checks.", "c": "GET /dna/intent/api/v1/networkDeviceImages/validationResults?networkDeviceId=<id>&type=POST_VALIDATION"},
  {"t": "Close the change", "d": "Attach validation results and task outcomes as evidence.", "c": ""},
],
"f8": [
  {"t": "Register a webhook destination", "d": "Tell the controller where to send events. Confirm the cluster can reach the URL first. Keep trustCert false so the controller checks your listener's certificate.",
   "c": "POST /dna/intent/api/v1/event/webhook\n{\n  \"name\": \"noc-listener\",\n  \"url\": \"https://hooks.example.com/catc\",\n  \"method\": \"POST\",\n  \"trustCert\": false\n}"},
  {"t": "Subscribe events to it", "d": "The create call returns no ID: read the destination's instanceId by name, then use the REST subscription operation (the generic /event/subscription is deprecated).",
   "c": "GET /dna/intent/api/v1/event/subscription-details/rest?name=noc-listener\n\nPOST /dna/intent/api/v1/event/subscription/rest\n[{\n  \"name\": \"device-unreachable\",\n  \"subscriptionEndpoints\": [{\"instanceId\": \"<instanceId>\",\n     \"subscriptionDetails\": {\"connectorType\": \"REST\"}}],\n  \"filter\": {\"eventIds\": [\"NETWORK-NON-FABRIC_WIRED-1-200\"]}\n}]"},
  {"t": "Setup done", "d": "Everything after this point runs without your code polling anything.", "c": ""},
  {"t": "Something happens in the network", "d": "A switch stops answering the controller's reachability checks.", "c": ""},
  {"t": "Correlated into an event", "d": "Assurance turns the signal into a catalog event with severity and category.", "c": ""},
  {"t": "Event pushed to your listener", "d": "An HTTP POST with a JSON body. The exact fields depend on the event; this sample is abridged.",
   "c": "POST https://hooks.example.com/catc\n{\n  \"eventId\": \"NETWORK-NON-FABRIC_WIRED-1-200\",\n  \"name\": \"Switch Unreachable\",\n  \"category\": \"ALERT\",\n  \"severity\": 1,\n  \"details\": {\"Device IP\": \"10.10.20.81\"}\n}"},
  {"t": "Acknowledge fast", "d": "Return 200 immediately and queue the work, so slow processing never blocks delivery.", "c": "200 OK"},
  {"t": "Reconcile hourly", "d": "List the notifications published in the last hour and process any your listener missed during an outage.",
   "c": "GET /dna/intent/api/v1/event/event-series?eventIds=NETWORK-NON-FABRIC_WIRED-1-200&startTime=<epoch ms>&endTime=<epoch ms>"},
],
"f9": [
  {"t": "Find the target devices", "d": "Filter the device list, for example by platform.", "c": "GET /dna/intent/api/v1/network-device?platformId=C9300-48P"},
  {"t": "Device UUIDs", "d": "Collect the id (UUID, universally unique identifier) of each device you will run commands on.", "c": "{\"response\": [{\"id\": \"6d3eaa5d-...\", \"hostname\": \"cat9k-access-01\"}], \"version\": \"1.0\"}"},
  {"t": "Submit read-only commands", "d": "Command Runner runs read-only commands; GET /network-device-poller/cli/legit-reads lists the allowed keywords. The optional timeout is in seconds (300 if omitted).",
   "c": "POST /dna/intent/api/v1/network-device-poller/cli/read-request\n{\n  \"commands\": [\"show version\", \"show ip int brief\"],\n  \"deviceUuids\": [\"6d3eaa5d-...\"]\n}"},
  {"t": "Task returned", "d": "Like most writes, this is asynchronous.", "c": "202 Accepted\n{\"response\": {\"taskId\": \"...\", \"url\": \"/dna/intent/api/v1/task/...\"}, \"version\": \"1.0\"}"},
  {"t": "Queued", "d": "The task engine schedules the job.", "c": ""},
  {"t": "The controller connects to the device", "d": "This touches the device: run it on demand, for a handful of devices, never on a timer.", "c": ""},
  {"t": "Output collected", "d": "The controller stores the output as a file.", "c": ""},
  {"t": "Poll the task", "d": "Same task API as any other write: wait for status SUCCESS.", "c": "GET /dna/intent/api/v1/tasks/{taskId}"},
  {"t": "fileId in progress", "d": "The task's progress text is a JSON string that contains the fileId. Cisco's Command Runner guide reads it from the older /task/{taskId}, which still answers; try /tasks/{taskId}/detail first and fall back to it.", "c": "GET /dna/intent/api/v1/tasks/{taskId}/detail\n{\"response\": {\"progress\": \"{\\\"fileId\\\":\\\"d3a7...\\\"}\"}}"},
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
          "text": "Becomes a task in which the controller connects to devices. On demand only, for a handful of devices.",
          "code": "POST /dna/intent/api/v1/network-device-poller/cli/read-request\n-> 202 {taskId}"},
}

CHOOSE = {
  "start": {"q": "What is the scope of your question?", "opts": [["Many devices, sites or clients", "many"], ["One device or one flow", "one"]]},
  "many": {"q": "What do you need?", "opts": [["Current state", "r_state"], ["A trend over a time range", "r_trend"], ["To be told when it changes", "r_event"]]},
  "one": {"q": "What do you need?", "opts": [["Its stored details", "r_detail"], ["Live CLI output", "r_cli"], ["The path between two hosts", "r_path"]]},
  "r_state": {"out": "o0", "t": "Intent health and query APIs", "b": "read",
              "d": "Fleet-wide state from the controller. Schedule every 5 to 15 minutes. Page site-health at up to 50 (areas and buildings separately) and the device query at up to 500.",
              "c": "GET /dna/intent/api/v1/site-health?siteType=BUILDING&offset=1&limit=50\nPOST /dna/intent/api/v1/networkDevices/query"},
  "r_trend": {"out": "o1", "t": "Assurance data APIs", "b": "read",
              "d": "Let the controller aggregate over time instead of pulling raw rows.",
              "c": "POST /dna/data/api/v1/networkDevices/trendAnalytics\nPOST /dna/data/api/v1/assuranceIssues/trendAnalytics"},
  "r_event": {"out": "o2", "t": "Event subscriptions (webhooks)", "b": "read",
              "d": "Register a webhook, subscribe events, reconcile hourly from /event/event-series. No polling loop.",
              "c": "POST /dna/intent/api/v1/event/webhook\nPOST /dna/intent/api/v1/event/subscription/rest"},
  "r_detail": {"out": "o0", "t": "Device detail from inventory", "b": "read",
               "d": "Stored details come from the controller database; no device is contacted. /networkDevices/{id} needs 2.3.7.9 or later; use /network-device/{id} before that.",
               "c": "GET /dna/intent/api/v1/networkDevices/{id}"},
  "r_cli": {"out": "o3", "t": "Command Runner", "b": "dev",
            "d": "Read-only commands (allowed keywords from /network-device-poller/cli/legit-reads). On demand, never scheduled.",
            "c": "POST /dna/intent/api/v1/network-device-poller/cli/read-request"},
  "r_path": {"out": "o3", "t": "Path Trace", "b": "dev",
             "d": "Traces the path between two endpoints. Use /pathTraces from 3.2.2; /flow-analysis, deprecated in the 3.2.x specification, only on earlier releases.",
             "c": "POST /dna/intent/api/v1/pathTraces          (3.2.2+)\nPOST /dna/intent/api/v1/flow-analysis       (before 3.2.2)"},
}

CODES = {
  "200": ["c0", "Parse the body", "Read response[] and version. An empty list is valid; see the symptom picker below if you expected data.", "data = r.json()[\"response\"]"],
  "202": ["c1", "Poll the task", "Queued, not done. Poll /tasks/{id} until status is SUCCESS or FAILURE, with a timeout; on FAILURE read failureReason from /tasks/{id}/detail.", "task = cc.wait_task(r.json()[\"response\"][\"taskId\"])"],
  "401": ["c2", "Re-authenticate once", "Token expired or invalid. Get a new token, retry once, then fail loudly.", "self._login(); r = self.s.request(method, url, **kw)"],
  "403": ["c4", "Do not retry", "The account's role or access group does not allow this operation or site. Fix RBAC, not the code.", "raise PermissionError(r.text)"],
  "404": ["c4", "Do not retry", "Wrong path, wrong ID, or an operation your release does not have (check the deprecation lookup).", "log.error(\"%s %s -> 404\", method, path)"],
  "429": ["c3", "Back off and retry", "Per-operation rate limit or concurrency cap hit. No rate-limit headers are documented, so back off 2 s, 4 s, 8 s up to 60 s (honour Retry-After if present).", "time.sleep(delay); delay = min(delay * 2, 60)"],
  "500": ["c3", "Reads: back off. Writes: check first", "Retry a GET a few times with backoff. For a POST, PUT or DELETE, check whether the task or object already exists before resending, or you may apply the change twice. If it persists, capture URL, body and response for a TAC (Technical Assistance Center) case.", "if method == \"GET\": time.sleep(delay)  # writes: look up the object first"],
  "503": ["c3", "Reads: back off. Writes: check first", "The service is temporarily unavailable. Retry reads with backoff; for writes, confirm the change did not land before resending.", "if method == \"GET\": time.sleep(delay)  # writes: look up the object first"],
}

SYMPTOMS = {
  "s1": ["202 but nothing changed", ["top", "L0", "L1", "L2"], "Read the task: status is FAILURE and failureReason in /tasks/{id}/detail says why (bad payload, device state, missing prerequisite)."],
  "s2": ["Task never finishes", ["top", "L0", "L1", "L3"], "Status stays PENDING: the device is busy or unreachable, or the job is large. Enforce a timeout and alert."],
  "s3": ["Empty list", ["top", "R0", "R1", "R2", "R3"], "Check filters and the offset (1-based on most operations, 0 on some event ones), then the account's access groups. If the UI shows data and the API does not, open a TAC case."],
  "s4": ["Different rows on each page", ["top", "R0", "R1"], "Before the 3.2.3 SMU 75346.100, repeated calls with the same limit and offset could return different site IDs (CSCwu68404, now resolved). On older builds, sort client-side and de-duplicate by ID."],
}

DEPRECATED = [
  {"p": r"/discovery(/|\?|$)", "label": "/discovery v1 (13 operations)", "rel": "3.2.2 (Sunset)", "year": 2026, "mon": 5, "rep": "POST /dna/intent/api/v1/discoverys, then POST /discoverys/{id}/jobs", "note": "Cisco's SDK labels it 3.2.1, a build not in the release notes."},
  {"p": r"/intent/api/v1/issues(/|\?|$)|^/issues(/|\?|$)", "label": "GET /dna/intent/api/v1/issues", "rel": "3.2.2", "year": 2026, "mon": 5, "rep": "GET /dna/data/api/v1/assuranceIssues or POST /dna/data/api/v1/assuranceIssues/query", "note": ""},
  {"p": r"/licenses/(device|term)", "label": "/licenses/device/..., /licenses/term/... (4 operations)", "rel": "3.2.2", "year": 2026, "mon": 5, "rep": "/dna/intent/api/v1/networkDeviceLicenses family, /licenseUsage", "note": ""},
  {"p": r"/wireless/accesspoint-configuration", "label": "/wireless/accesspoint-configuration (5 operations)", "rel": "3.2.2", "year": 2026, "mon": 5, "rep": "POST /dna/intent/api/v1/wirelessAccessPoints/configurations", "note": ""},
  {"p": r"/flow-analysis", "label": "/flow-analysis (4 operations)", "rel": "3.2.x API specification", "year": 2026, "mon": 5, "rep": "/dna/intent/api/v1/pathTraces (3.2.2 and later)", "note": "Use /flow-analysis only on releases before 3.2.2."},
  {"p": r"/intent/api/v1/task(/|\?|$)|^/task(/|\?|$)", "label": "/task, /task/{taskId}, /task/count, /task/{taskId}/tree, /task/operation/...", "rel": "2.3.7.6 (Sunset)", "year": 2024, "mon": 8, "rep": "GET /dna/intent/api/v1/tasks/{id} and /tasks/{id}/detail", "note": "The 202 response's url field and Cisco's Command Runner guide still use /task/{taskId}."},
  {"p": r"/v2/site/count|/site/count", "label": "/site/count, /v2/site/count", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites/count", "note": "Part of the legacy site family."},
  {"p": r"/site-member/|/membership/", "label": "/site-member/{id}/member, /membership/{siteId}", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites and device-to-site operations", "note": ""},
  {"p": r"/assign-device-to-site/", "label": "POST /assign-device-to-site/{siteId}/device", "rel": "2.3.7.6 (Sunset banner)", "year": 2024, "mon": 8, "rep": "POST /dna/intent/api/v1/networkDevices/assignToSite/apply", "note": ""},
  {"p": r"/credential-to-site/", "label": "/v1 and /v2 credential-to-site/{siteId}", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "PUT /dna/intent/api/v1/sites/{id}/deviceCredentials, then POST /dna/intent/api/v1/sites/deviceCredentials/apply", "note": ""},
  {"p": r"/(v1|v2)/network(/|\?|$)", "label": "/network, /network/{siteId} (v1 and v2)", "rel": "2.3.7.6 (Sunset)", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites/{id}/...Settings (aaa, dns, dhcp, ntp, timeZone, banner, telemetry)", "note": ""},
  {"p": r"(^|/v1|/v2)/site(/|\?|$)", "label": "/site, /v2/site (create, get, update, delete)", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/dna/intent/api/v1/sites family (GET /sites/{id} from 3.1.6; POST /v2/floors etc.)", "note": "DevNet's own Sites guide still shows /site; many tutorials use it."},
  {"p": r"/wireless/(profile|rf-profile|provision|ap-provision|dynamic-interface)|/wireless-profile/|/enterprise-ssid|/business/ssid", "label": "Legacy wireless: /wireless/profile, /wireless/rf-profile, /enterprise-ssid, /business/ssid, /wireless/provision, /wireless/ap-provision", "rel": "2.3.7.6", "year": 2024, "mon": 8, "rep": "/wirelessProfiles, /wirelessSettings/rfProfiles, /sites/{siteId}/wirelessSettings/ssids, /wirelessControllers/{deviceId}/provision, /wirelessAccessPoints/provision", "note": ""},
  {"p": r"/reserve-ip-subpool|/global-pool", "label": "/reserve-ip-subpool, /global-pool (all methods)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/ipam/siteIpAddressPools, /ipam/globalIpAddressPools", "note": ""},
  {"p": r"/business/sda", "label": "/business/sda/* (about 45 operations)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/sda/* (fabricSites, layer3VirtualNetworks, anycastGateways, fabricDevices, transitNetworks, portAssignments, provisionDevices)", "note": "Still answering with a Sunset banner."},
  {"p": r"/virtual-network(/|\?|$)", "label": "/virtual-network", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/sda/layer3VirtualNetworks", "note": ""},
  {"p": r"/event/subscription/?($|\?)", "label": "/event/subscription (generic POST/PUT/GET)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/event/subscription/rest and the per-channel subscription operations", "note": "Cisco's SDK says deprecated since 2.3.3.x."},
  {"p": r"/security-advisory/", "label": "/security-advisory/* (5 operations)", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "/dna/intent/api/v1/securityAdvisories/... results and triggerScan", "note": ""},
  {"p": r"/image/importation", "label": "/image/importation, /image/importation/golden...", "rel": "2.3.7.9", "year": 2025, "mon": 3, "rep": "GET /images; POST /images/{id}/sites/{siteId}/tagGolden and /untagGolden", "note": ""},
  {"p": r"/image/distribution", "label": "POST /image/distribution", "rel": "3.1.3 (Sunset)", "year": 2025, "mon": 6, "rep": "/networkDeviceImages/{id}/distribute or /networkDeviceImages/distribute/bulk", "note": ""},
  {"p": r"/image/activation/device", "label": "POST /image/activation/device", "rel": "3.1.3 (Sunset)", "year": 2025, "mon": 6, "rep": "/networkDeviceImages/{id}/activate or /networkDeviceImages/activate/bulk", "note": ""},
  {"p": r"/network-device-config/?($|\?)", "label": "GET /network-device-config", "rel": "3.1.3", "year": 2025, "mon": 6, "rep": "/dna/intent/api/v1/networkDeviceConfigFiles", "note": "The operation itself says deprecated since 2.3.7.9. /network-device-config/write-memory and /task are not deprecated."},
  {"p": r"/system/api/v1/(role|roles)(/|\?|$)", "label": "/dna/system/api/v1/role, /roles, /role/permissions", "rel": "3.1.5 (Sunset)", "year": 2025, "mon": 10, "rep": "/dna/system/api/v2/roles, /dna/system/api/v2/roles/permissions, /dna/system/api/v1/accessGroups", "note": ""},
  {"p": r"BLUECAT_V1API", "label": "BLUECAT_V1API IPAM provider value", "rel": "3.3.1: planned for deprecation", "year": None, "mon": None, "rep": "BLUECAT_V2API", "note": ""},
  {"p": r"cisco\.dnac", "label": "Ansible collection cisco.dnac", "rel": "Removed from the Ansible 14 community package (June 2026)", "year": None, "mon": None, "rep": "cisco.catalystcenter", "note": "Still installable from Galaxy."},
  {"p": r"multivendor", "label": "Multivendor SDK (device packs)", "rel": "Deprecated", "year": None, "mon": None, "rep": "SNMP MIB-II third-party device visibility", "note": "Inventory, reachability-based health and limited Assurance; no provisioning."},
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
    ex = ["/dna/intent/api/v1/task/{taskId}", "/dna/intent/api/v1/issues", "/dna/intent/api/v1/discovery", "/dna/intent/api/v1/site", "/business/sda/fabric", "/sites/{id}/dnsSettings"]
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
    if (window.catcFlow) window.catcFlow(steps[cur]);
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
if (dt) { var inp = $('#dep-in'), out = $('#dep-out'), now = new Date();
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
      row('Next step', 'Open the operation in Platform > Developer Toolkit > APIs on your cluster and look for a Deprecated or Sunset banner. This list covers deprecations through 3.3.1 (3.2.3 and 3.3.1 add none).');
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
