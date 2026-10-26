#!/usr/bin/env python3
"""
catalyst_client.py - minimal Cisco Catalyst Center REST client from the CiscoSE API field guide.

What it handles for you
  * Token login (POST /dna/system/api/v1/auth/token) with a cached X-Auth-Token
  * One re-login on HTTP 401; back-off on 429, and on 500/503 for reads only
    (a write that returned 500 may already have run: check before resending)
  * Task polling with GET /tasks/{id} (2.3.7.6+; the older /task/{taskId} is Sunset)
  * Paging: 1-based offset with limit 500 on most list operations (site-health allows 50)

Usage (credentials come from environment variables, never the command line):
  export CATC_HOST=catc.example.com CATC_USER=svc-api CATC_PASS='***'
  export CATC_VERIFY=true            # false only for lab clusters with self-signed certificates
  python3 catalyst_client.py token                  # check login and RBAC
  python3 catalyst_client.py count                  # number of managed devices
  python3 catalyst_client.py devices --family "Switches and Hubs"
  python3 catalyst_client.py site-health
  python3 catalyst_client.py cli --ip 10.0.0.1 --command "show version"
  python3 catalyst_client.py task <taskId>

Written for Catalyst Center 3.2.3 (generally available), with 2.3.7.6+ and 3.3.1 in mind. Confirm each operation in
Platform > Developer Toolkit > APIs on your own cluster before production use.
Requires: requests  (pip install requests)
"""
import argparse, json, os, sys, time

import requests
from requests.auth import HTTPBasicAuth


class CatalystCenter:
    def __init__(self, host, user, password, verify=True, token_ttl=55 * 60):
        self.base = host if host.startswith("http") else f"https://{host}"
        self.s = requests.Session()
        self.s.verify = verify
        self.auth = HTTPBasicAuth(user, password)
        self.ttl, self.exp = token_ttl, 0

    def _login(self):
        r = self.s.post(f"{self.base}/dna/system/api/v1/auth/token", auth=self.auth, timeout=30)
        r.raise_for_status()
        self.s.headers.update({"X-Auth-Token": r.json()["Token"], "Content-Type": "application/json"})
        self.exp = time.time() + self.ttl

    def call(self, method, path, **kw):
        if time.time() > self.exp:
            self._login()
        kw.setdefault("timeout", 60)
        delay, relogged = 2, False
        for _ in range(6):
            r = self.s.request(method, self.base + path, **kw)
            if r.status_code == 401 and not relogged:
                self._login(); relogged = True; continue
            if r.status_code == 429 or (r.status_code in (500, 503) and method.upper() == "GET"):
                # No rate-limit headers are documented; honour Retry-After if one is ever sent
                time.sleep(int(r.headers.get("Retry-After", delay))); delay = min(delay * 2, 60); continue
            r.raise_for_status()
            return r.json() if r.content else {}
        raise RuntimeError(f"gave up after retries: {method} {path}")

    def wait_task(self, task_id, timeout=900, every=5):
        """Poll GET /tasks/{id} until status is SUCCESS or FAILURE."""
        t0 = time.time()
        while time.time() - t0 < timeout:
            t = self.call("GET", f"/dna/intent/api/v1/tasks/{task_id}")["response"]
            if t.get("status") == "FAILURE":
                d = self.task_detail(task_id)
                raise RuntimeError(d.get("failureReason") or d.get("errorCode") or "task failed")
            if t.get("status") == "SUCCESS":
                return t                              # endTime and resultLocation are set
            time.sleep(every)                         # PENDING
        raise TimeoutError(task_id)

    def task_detail(self, task_id):
        """GET /tasks/{id}/detail: progress, data, failureReason, errorCode."""
        return self.call("GET", f"/dna/intent/api/v1/tasks/{task_id}/detail")["response"]

    def pages(self, path, params=None, limit=500, start=1):
        """Yield rows page by page. Most list operations use a 1-based offset and
        allow up to 500 per page; check each operation (site-health allows 50)."""
        offset = start
        while True:
            rows = self.call("GET", path, params={**(params or {}), "offset": offset, "limit": limit})["response"]
            yield from rows
            if len(rows) < limit:
                return
            offset += limit

    def run_cli(self, device_ids, commands, timeout=900):
        job = self.call("POST", "/dna/intent/api/v1/network-device-poller/cli/read-request",
                        json={"commands": commands, "deviceUuids": device_ids, "timeout": 0})
        task_id = job["response"]["taskId"]
        self.wait_task(task_id, timeout=timeout)
        # Command Runner reports its output file in the task's progress text
        file_id = json.loads(self.task_detail(task_id)["progress"])["fileId"]
        return self.call("GET", f"/dna/intent/api/v1/file/{file_id}")


def from_env():
    missing = [k for k in ("CATC_HOST", "CATC_USER", "CATC_PASS") if not os.environ.get(k)]
    if missing:
        sys.exit("Set environment variables: " + ", ".join(missing))
    verify = os.environ.get("CATC_VERIFY", "true").lower() not in ("0", "false", "no")
    if not verify:
        requests.packages.urllib3.disable_warnings()
    return CatalystCenter(os.environ["CATC_HOST"], os.environ["CATC_USER"], os.environ["CATC_PASS"], verify)


def main():
    ap = argparse.ArgumentParser(description="Catalyst Center API field guide client")
    sub = ap.add_subparsers(dest="action", required=True)
    sub.add_parser("token", help="log in and confirm the token works")
    sub.add_parser("count", help="managed device count")
    d = sub.add_parser("devices", help="list devices (paged)")
    d.add_argument("--family", help='e.g. "Switches and Hubs", "Routers", "Unified AP"')
    sub.add_parser("site-health", help="health per site")
    c = sub.add_parser("cli", help="run read-only show commands through Command Runner")
    c.add_argument("--ip", required=True, help="device management IP address")
    c.add_argument("--command", dest="commands", action="append", required=True, help="show command (repeatable)")
    t = sub.add_parser("task", help="show a task")
    t.add_argument("task_id")
    a = ap.parse_args()

    cc = from_env()
    if a.action == "token":
        cc._login(); print("Login OK, token cached for", cc.ttl // 60, "minutes")
    elif a.action == "count":
        print(cc.call("GET", "/dna/intent/api/v1/network-device/count")["response"])
    elif a.action == "devices":
        params = {"family": a.family} if a.family else {}
        for dev in cc.pages("/dna/intent/api/v1/network-device", params):
            print(f'{dev.get("hostname") or "-":32} {dev.get("managementIpAddress") or "-":16} '
                  f'{dev.get("platformId") or "-":20} {dev.get("softwareVersion") or "-":12} {dev.get("reachabilityStatus") or "-"}')
    elif a.action == "site-health":
        # site-health returns at most 50 per page (default 25, areas only): page areas and buildings
        for site_type in ("AREA", "BUILDING"):
            for s in cc.pages("/dna/intent/api/v1/site-health", {"siteType": site_type}, limit=50):
                print(f'{s.get("siteName") or "-":40} {s.get("siteType") or "-":10} health={s.get("networkHealthAverage")}')
    elif a.action == "cli":
        dev = cc.call("GET", "/dna/intent/api/v1/network-device", params={"managementIpAddress": a.ip})["response"]
        if not dev:
            sys.exit(f"No managed device with IP {a.ip} (or the account's RBAC scope hides it)")
        print(json.dumps(cc.run_cli([dev[0]["id"]], a.commands), indent=2))
    elif a.action == "task":
        print(json.dumps({"task": cc.call("GET", f"/dna/intent/api/v1/tasks/{a.task_id}")["response"],
                          "detail": cc.task_detail(a.task_id)}, indent=2))


if __name__ == "__main__":
    main()
