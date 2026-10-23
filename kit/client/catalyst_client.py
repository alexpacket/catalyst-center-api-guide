#!/usr/bin/env python3
"""
catalyst_client.py - minimal Cisco Catalyst Center REST client from the CiscoSE API field guide.

What it handles for you
  * Token login (POST /dna/system/api/v1/auth/token) with a cached X-Auth-Token
  * One re-login on HTTP 401, exponential back-off on 429 and 503
  * Task polling for asynchronous (HTTP 202) operations
  * 1-based offset paging with limit 500

Usage (credentials come from environment variables, never the command line):
  export CATC_HOST=catc.example.com CATC_USER=svc-api CATC_PASS='***'
  export CATC_VERIFY=true            # false only for lab clusters with self-signed certificates
  python3 catalyst_client.py token                  # check login and RBAC
  python3 catalyst_client.py count                  # number of managed devices
  python3 catalyst_client.py devices --family "Switches and Hubs"
  python3 catalyst_client.py site-health
  python3 catalyst_client.py cli --ip 10.0.0.1 --command "show version"
  python3 catalyst_client.py task <taskId>

Payloads and parameters are documented for 3.1.x to 3.3.x. Confirm each operation in
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
            if r.status_code in (429, 503):          # no rate-limit headers are documented: back off
                time.sleep(delay); delay = min(delay * 2, 60); continue
            r.raise_for_status()
            return r.json() if r.content else {}
        raise RuntimeError(f"gave up after retries: {method} {path}")

    def wait_task(self, task_id, timeout=900, every=5):
        t0 = time.time()
        while time.time() - t0 < timeout:
            t = self.call("GET", f"/dna/intent/api/v1/task/{task_id}")["response"]
            if t.get("endTime"):
                if t.get("isError"):
                    raise RuntimeError(t.get("failureReason") or t.get("progress"))
                return t
            time.sleep(every)
        raise TimeoutError(task_id)

    def pages(self, path, params=None, limit=500):
        offset = 1                                   # offset is 1-based
        while True:
            rows = self.call("GET", path, params={**(params or {}), "offset": offset, "limit": limit})["response"]
            yield from rows
            if len(rows) < limit:
                return
            offset += limit

    def run_cli(self, device_ids, commands, timeout=900):
        job = self.call("POST", "/dna/intent/api/v1/network-device-poller/cli/read-request",
                        json={"commands": commands, "deviceUuids": device_ids, "timeout": 0})
        task = self.wait_task(job["response"]["taskId"], timeout=timeout)
        file_id = json.loads(task["progress"])["fileId"]
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
        for s in cc.call("GET", "/dna/intent/api/v1/site-health")["response"]:
            print(f'{s.get("siteName") or "-":40} {s.get("siteType") or "-":10} health={s.get("networkHealthAverage")}')
    elif a.action == "cli":
        dev = cc.call("GET", "/dna/intent/api/v1/network-device", params={"managementIpAddress": a.ip})["response"]
        if not dev:
            sys.exit(f"No managed device with IP {a.ip} (or the account's RBAC scope hides it)")
        print(json.dumps(cc.run_cli([dev[0]["id"]], a.commands), indent=2))
    elif a.action == "task":
        print(json.dumps(cc.call("GET", f"/dna/intent/api/v1/task/{a.task_id}")["response"], indent=2))


if __name__ == "__main__":
    main()
