#!/usr/bin/env python3
"""End-to-end check that the running stack actually works.

Unit tests pass on a machine where nothing is running. This script is the
answer to "it works on my machine": it talks to the real containers over HTTP
and fails loudly when the stack is up but broken.

Usage:
    docker compose up -d
    python scripts/smoke_test.py

Environment:
    BACKEND_URL   default http://localhost:8000
    FRONTEND_URL  default http://localhost:3000
    TIMEOUT       seconds to wait for the stack to come up, default 120

Exits 1 on the first failed check. Standard library only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request

BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000").rstrip("/")
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:3000").rstrip("/")
TIMEOUT = int(os.environ.get("TIMEOUT", "120"))

failures: list[str] = []


def fetch(url: str, timeout: int = 10) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "bilingers-smoke"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


def post_json(url: str, payload: dict, timeout: int = 10) -> tuple[int, str]:
    """POST JSON and return the status even when it is an error status.

    urllib raises on 4xx, but a 4xx is exactly what some checks expect: an
    endpoint that refuses bad input is working, and one that accepts it is not.
    """
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": "bilingers-smoke", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8", errors="replace")


def wait_for(url: str, label: str) -> bool:
    """Poll until the URL answers, or give up after TIMEOUT seconds."""
    deadline = time.monotonic() + TIMEOUT
    last_error = "no attempt made"
    while time.monotonic() < deadline:
        try:
            status, _ = fetch(url, timeout=5)
            if status == 200:
                return True
            last_error = f"HTTP {status}"
        except (urllib.error.URLError, OSError) as error:
            last_error = str(error)
        time.sleep(2)
    failures.append(f"{label}: never became ready within {TIMEOUT}s ({last_error})")
    return False


def check(label: str, condition: bool, detail: str = "") -> None:
    if condition:
        print(f"  ok    {label}")
    else:
        print(f"  FAIL  {label} {detail}".rstrip())
        failures.append(f"{label} {detail}".strip())


def check_backend() -> None:
    print("backend")
    if not wait_for(f"{BACKEND_URL}/health", "backend /health"):
        return

    status, body = fetch(f"{BACKEND_URL}/health")
    check("liveness returns ok", json.loads(body) == {"status": "ok"}, body)

    try:
        status, body = fetch(f"{BACKEND_URL}/health/db")
        payload = json.loads(body)
    except urllib.error.HTTPError as error:
        check("database is reachable", False, f"HTTP {error.code}")
        return
    check("database is reachable", payload.get("database") == "reachable", body)

    status, body = fetch(f"{BACKEND_URL}/openapi.json")
    check("openapi schema is served", "/health" in json.loads(body)["paths"])

    # A 401 here means the request reached the database: the account has to be
    # looked up before anything can refuse it, so this also proves the panel
    # migration ran. It leaves one row in the login audit, which is correct -
    # somebody really did try to log in with an account that does not exist.
    status, body = post_json(
        f"{BACKEND_URL}/api/panel/sessions",
        {"email": "smoke@bilingers.test", "password": "nie-ma-takiego-konta"},
    )
    check("panel refuses an unknown account", status == 401, f"got {status}: {body}")


def check_frontend() -> None:
    print("frontend")
    if not wait_for(FRONTEND_URL, "frontend root"):
        return

    status, body = fetch(FRONTEND_URL)
    check("root responds 200", status == 200, f"got {status}")
    check("page renders the product name", "Bilingers" in body)
    check("page is served as Polish", 'lang="pl"' in body)


def main() -> int:
    print(f"backend  {BACKEND_URL}")
    print(f"frontend {FRONTEND_URL}")
    print()

    check_backend()
    print()
    check_frontend()
    print()

    if failures:
        print(f"Smoke test failed ({len(failures)} problems):")
        for failure in failures:
            print(f"  {failure}")
        return 1

    print("Smoke test passed: the stack is up and answering.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
