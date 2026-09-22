#!/usr/bin/env python3
"""validate.py — BARQ Academy environment validation script.

Checks:
  A. Public HTTP access through NGINX (/, /health, /ready, /records, /counter)
  B. Load-balancer distribution (both app-01 and app-02 observed)
  C. Docker/service health via Docker CLI
  D. Network/port isolation

Exit code: 0 if all required checks pass, 1 otherwise.
Uses Python 3 standard library only.
"""
import json
import subprocess
import sys
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8080"
TIMEOUT = 5          # seconds per HTTP request
INSTANCE_REQUESTS = 20   # total requests for load-balancer check
PROJECT = "barq-assessment"

results: list[tuple[str, bool]] = []


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def record(label: str, passed: bool, detail: str = "") -> bool:
    tag = "PASS" if passed else "FAIL"
    msg = f"{tag}: {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((label, passed))
    return passed


def http_get(path: str) -> tuple[int, dict]:
    url = BASE_URL + path
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = {}
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            pass
        return exc.code, body
    except Exception as exc:
        return 0, {"_error": str(exc)}


def http_post(path: str, payload: dict) -> tuple[int, dict]:
    url = BASE_URL + path
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body
    except urllib.error.HTTPError as exc:
        body = {}
        try:
            body = json.loads(exc.read().decode())
        except Exception:
            pass
        return exc.code, body
    except Exception as exc:
        return 0, {"_error": str(exc)}


def docker(*args, timeout: int = 10) -> tuple[int, str]:
    """Run a docker command and return (returncode, stdout)."""
    cmd = ["docker"] + list(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except FileNotFoundError:
        return 1, ""


def compose(*args, timeout: int = 15) -> tuple[int, str]:
    """Run docker compose with the project name and return (returncode, stdout)."""
    cmd = ["docker", "compose", "-p", PROJECT] + list(args)
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except FileNotFoundError:
        return 1, ""


def container_inspect(name: str) -> dict:
    rc, out = docker("inspect", "--format", "{{json .}}", name)
    if rc != 0 or not out:
        return {}
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return {}


# ---------------------------------------------------------------------------
# Section A — Public HTTP access through NGINX
# ---------------------------------------------------------------------------
print("\n=== A: Public HTTP access ===")

# A1 — root
code, body = http_get("/")
record(
    "GET / returns HTTP 200 with message field",
    code == 200 and "message" in body,
    f"status={code}",
)

# A2 — /health
code, body = http_get("/health")
record(
    "GET /health returns HTTP 200 with status=alive",
    code == 200 and body.get("status") == "alive",
    f"status={code} body_status={body.get('status')}",
)

# A3 — /ready: both postgres and redis must be ready
code, body = http_get("/ready")
deps = body.get("dependencies", {})
pg_ready = deps.get("postgres") == "ready"
redis_ready = deps.get("redis") == "ready"
record(
    "GET /ready returns HTTP 200 with postgres=ready",
    code == 200 and pg_ready,
    f"status={code} postgres={deps.get('postgres')}",
)
record(
    "GET /ready returns HTTP 200 with redis=ready",
    code == 200 and redis_ready,
    f"status={code} redis={deps.get('redis')}",
)

# A4 — POST /records (create) → 201 + record object with id and title
title = "validate-py-test"
code, body = http_post("/records", {"title": title})
created_id = body.get("record", {}).get("id")
record(
    "POST /records creates a record (HTTP 201, record.id present, record.title matches)",
    code == 201 and created_id is not None and body.get("record", {}).get("title") == title,
    f"status={code} id={created_id}",
)

# A5 — GET /records → 200 + records list (contains the record we just created)
code, body = http_get("/records")
records_list = body.get("records", [])
found = any(r.get("title") == title for r in records_list)
record(
    "GET /records returns HTTP 200 with a list containing created record",
    code == 200 and isinstance(records_list, list) and found,
    f"status={code} count={len(records_list)} found={found}",
)

# A6 — GET /counter → 200, counter field is an integer ≥ 1
code, body = http_get("/counter")
counter_val = body.get("counter")
record(
    "GET /counter returns HTTP 200 with integer counter ≥ 1",
    code == 200 and isinstance(counter_val, int) and counter_val >= 1,
    f"status={code} counter={counter_val}",
)

# ---------------------------------------------------------------------------
# Section B — Load-balancer: both instances observed
# ---------------------------------------------------------------------------
print("\n=== B: Load-balancer distribution ===")

observed_instances: set[str] = set()
req_errors = 0
for _ in range(INSTANCE_REQUESTS):
    url = BASE_URL + "/instance"
    try:
        with urllib.request.urlopen(
            urllib.request.Request(url), timeout=TIMEOUT
        ) as resp:
            data = json.loads(resp.read().decode())
            iid = data.get("instance_id")
            if iid:
                observed_instances.add(iid)
    except Exception:
        req_errors += 1

record(
    f"Both app-01 and app-02 observed across {INSTANCE_REQUESTS} requests to /instance",
    "app-01" in observed_instances and "app-02" in observed_instances,
    f"observed={sorted(observed_instances)} errors={req_errors}",
)

# ---------------------------------------------------------------------------
# Section C — Docker/service health
# ---------------------------------------------------------------------------
print("\n=== C: Docker service health ===")

REQUIRED_SERVICES = ["postgres", "redis", "nginx", "app-01", "app-02"]

rc, ps_out = compose("ps", "--format", "json")
if rc != 0 or not ps_out:
    record("docker compose ps succeeded", False, "command failed or no output")
    service_statuses: dict[str, dict] = {}
else:
    # docker compose ps --format json may emit one JSON object per line OR a JSON array
    service_statuses = {}
    for line in ps_out.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            if isinstance(obj, list):
                for item in obj:
                    name = item.get("Name") or item.get("Service") or ""
                    service_statuses[name] = item
            elif isinstance(obj, dict):
                name = obj.get("Name") or obj.get("Service") or ""
                service_statuses[name] = obj
        except json.JSONDecodeError:
            pass
    record("docker compose ps succeeded", True)

for svc in REQUIRED_SERVICES:
    # Match by exact Name or by Service field
    entry = service_statuses.get(svc) or next(
        (v for v in service_statuses.values()
         if v.get("Service") == svc or v.get("Name") == svc), None
    )
    if entry is None:
        record(f"Service {svc} is running", False, "not found in compose ps")
        continue
    state = (entry.get("State") or entry.get("Status") or "").lower()
    running = "running" in state or state == "running"
    record(f"Service {svc} is running", running, f"state={state}")

    # Healthcheck status for postgres and redis
    if svc in ("postgres", "redis"):
        health = (entry.get("Health") or "").lower()
        if health:
            record(f"Service {svc} is healthy", health == "healthy", f"health={health}")
        else:
            # Fall back to docker inspect
            info = container_inspect(svc)
            health_status = ""
            if isinstance(info, dict):
                health_status = (
                    (info.get("State") or {}).get("Health", {}) or {}
                ).get("Status", "")
            record(
                f"Service {svc} is healthy",
                health_status.lower() == "healthy",
                f"health={health_status}",
            )

# ---------------------------------------------------------------------------
# Section D — Network / port isolation
# ---------------------------------------------------------------------------
print("\n=== D: Network / port isolation ===")

SERVICES_NO_HOST_PORTS = ["postgres", "redis", "app-01", "app-02"]

for svc in SERVICES_NO_HOST_PORTS:
    info = container_inspect(svc)
    ports: dict = {}
    if isinstance(info, dict):
        ports = (info.get("NetworkSettings") or {}).get("Ports") or {}
    host_bound = any(
        v for v in ports.values() if v is not None
    )
    record(
        f"{svc} has NO host-published ports",
        not host_bound,
        f"ports={ports}" if host_bound else "no host ports",
    )

# Verify NGINX has port 8080 published
nginx_info = container_inspect("nginx")
nginx_ports: dict = {}
if isinstance(nginx_info, dict):
    nginx_ports = (nginx_info.get("NetworkSettings") or {}).get("Ports") or {}
nginx_published = any(v for v in nginx_ports.values() if v is not None)
record(
    "nginx has a host-published port (8080)",
    nginx_published,
    f"ports={nginx_ports}",
)

# Network membership checks via docker inspect
NETWORK_MEMBERSHIP = {
    "nginx":   (["frontend"], []),
    "app-01":  (["frontend", "backend"], []),
    "app-02":  (["frontend", "backend"], []),
    "postgres":(["backend"], []),
    "redis":   (["backend"], []),
}
for svc, (must_have, must_not) in NETWORK_MEMBERSHIP.items():
    info = container_inspect(svc)
    connected: set[str] = set()
    if isinstance(info, dict):
        networks_raw = ((info.get("NetworkSettings") or {}).get("Networks") or {})
        # Strip the project prefix from network names for comparison
        for net_key in networks_raw:
            short = net_key.split("_")[-1]  # e.g. barq-assessment_frontend → frontend
            connected.add(short)
            connected.add(net_key)          # also keep full name as fallback
    for net in must_have:
        in_net = net in connected
        record(
            f"{svc} is connected to network '{net}'",
            in_net,
            f"connected={sorted(connected)}",
        )

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
print("\n=== Summary ===")
total = len(results)
passed = sum(1 for _, ok in results if ok)
failed = total - passed
for label, ok in results:
    print(f"{'PASS' if ok else 'FAIL'}: {label}")

print()
if failed == 0:
    print(f"Validation PASSED ({passed}/{total} checks passed)")
    sys.exit(0)
else:
    print(f"Validation FAILED ({failed}/{total} checks failed)")
    sys.exit(1)
