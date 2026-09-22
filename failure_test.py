#!/usr/bin/env python3
"""failure_test.py — Reproducible failure/recovery test for BARQ Academy."""

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request

BASE_URL = "http://localhost:8080"
TIMEOUT = 2
TRAFFIC_REQUESTS = 20

results = []

def record(label: str, passed: bool, detail: str = "") -> bool:
    tag = "PASS" if passed else "FAIL"
    msg = f"{tag}: {label}"
    if detail:
        msg += f" — {detail}"
    print(msg)
    results.append((label, passed))
    return passed

def run_docker(*args, timeout=10) -> tuple[int, str]:
    cmd = ["docker"] + list(args)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return proc.returncode, proc.stdout.strip()
    except subprocess.TimeoutExpired:
        return 1, ""
    except FileNotFoundError:
        return 1, ""

def is_running(container_name: str) -> bool:
    rc, out = run_docker("inspect", "-f", "{{.State.Running}}", container_name)
    return rc == 0 and out.lower() == "true"

def is_healthy(container_name: str) -> bool:
    rc, out = run_docker("inspect", "-f", "{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}", container_name)
    return rc == 0 and out.lower() == "healthy"

def get_instance_info() -> tuple[int, str]:
    url = BASE_URL + "/instance"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return resp.status, body.get("instance_id")
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception:
        return 0, None

def run_traffic_batch(num_requests: int = TRAFFIC_REQUESTS, delay: float = 0.1) -> dict:
    stats = {"total": num_requests, "success": 0, "failures": 0, "instances": set()}
    for _ in range(num_requests):
        status, iid = get_instance_info()
        if status == 200 and iid:
            stats["success"] += 1
            stats["instances"].add(iid)
        else:
            stats["failures"] += 1
        time.sleep(delay)
    return stats

def main():
    print("=== BARQ Academy Failure / Recovery Test ===")

    try:
        print("\n--- 1. Pre-check ---")
        app1_up = is_running("app-01")
        app2_up = is_running("app-02")
        record("Pre-check: app-01 is running", app1_up)
        record("Pre-check: app-02 is running", app2_up)

        status, iid = get_instance_info()
        record("Pre-check: /instance endpoint is reachable", status == 200, f"status={status} instance={iid}")

        if not (app1_up and app2_up and status == 200):
            print("INFO: Environment not ready for failure test. Aborting.")
            return

        print("\n--- 2. Baseline Traffic ---")
        stats_base = run_traffic_batch()
        record(
            "Baseline: Both apps serving traffic",
            "app-01" in stats_base["instances"] and "app-02" in stats_base["instances"],
            f"Success: {stats_base['success']}/{stats_base['total']}, Instances: {sorted(stats_base['instances'])}"
        )

        print("\n--- 3. Inject Failure (Stopping app-01) ---")
        rc, _ = run_docker("stop", "app-01")
        record("docker stop app-01 command succeeded", rc == 0)

        app1_stopped = not is_running("app-01")
        record("app-01 is actually stopped", app1_stopped)

        print("\n--- 4. Test Traffic (app-01 stopped) ---")
        stats_fail = run_traffic_batch(num_requests=30, delay=0.1)

        app2_served_only = "app-02" in stats_fail["instances"] and "app-01" not in stats_fail["instances"]
        record(
            "app-02 continued serving traffic",
            stats_fail["success"] > 0 and app2_served_only,
            f"Success: {stats_fail['success']}/{stats_fail['total']}, Failures: {stats_fail['failures']}, Instances: {sorted(stats_fail['instances'])}"
        )

        print("\n--- 5. Recovery (Starting app-01) ---")
        rc, _ = run_docker("start", "app-01")
        record("docker start app-01 command succeeded", rc == 0)

        recovered = False
        print("Waiting up to 15 seconds for app-01 to become healthy...", flush=True)
        for _ in range(15):
            if is_healthy("app-01"):
                recovered = True
                break
            time.sleep(1)

        record("app-01 became healthy after restart", recovered)

        if recovered:
            stats_rec = run_traffic_batch(num_requests=40, delay=0.1)
            record(
                "Both apps serving traffic after recovery",
                "app-01" in stats_rec["instances"] and "app-02" in stats_rec["instances"],
                f"Success: {stats_rec['success']}/{stats_rec['total']}, Failures: {stats_rec['failures']}, Instances: {sorted(stats_rec['instances'])}"
            )

    finally:
        print("\n--- 6. Cleanup ---")
        if not is_running("app-01"):
            print("Restarting app-01 in cleanup...")
            run_docker("start", "app-01")
        if not is_running("app-02"):
            print("Restarting app-02 in cleanup...")
            run_docker("start", "app-02")

        cl_app1 = is_running("app-01")
        cl_app2 = is_running("app-02")
        record("Cleanup confirmed app-01 is running", cl_app1)
        record("Cleanup confirmed app-02 is running", cl_app2)

        print("\n=== Summary ===")
        total_checks = len(results)
        passed_checks = sum(1 for _, passed in results if passed)
        failed_checks = total_checks - passed_checks

        for label, passed in results:
            print(f"{'PASS' if passed else 'FAIL'}: {label}")

        print()
        if failed_checks == 0:
            print("Failure test PASSED (0 failures)")
            sys.exit(0)
        else:
            print(f"Failure test FAILED ({failed_checks} failures)")
            sys.exit(1)

if __name__ == "__main__":
    main()
