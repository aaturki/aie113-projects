"""Smoke test: is a running service really up, and does it answer as promised?

    python scripts/smoke.py http://localhost:8000

It waits for /v1/ready, then sends the payment from the notebook's last cell (it must be
blocked, with V14 as its top reason), a typical payment if payloads/typical.json exists (it
must be allowed, with no reasons), and three bad requests (each must get the error shape, and
never see the values or names it sent echoed back). Standard library only, so it runs against
the service anywhere: a laptop, a container, the pipeline.
"""
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

PAYLOADS = Path(__file__).resolve().parent.parent / "payloads"
CARD_LIKE = "card_4111111111111111"     # a field name that carries data: must never come back
failures: list[str] = []


def call(base: str, path: str, body: Any = None,
         headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], str]:
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(base + path, data=data, method="GET" if data is None
                                     else "POST", headers={"content-type": "application/json",
                                                           **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, dict(response.headers), response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read().decode()


def expect(ok: bool, what: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        failures.append(what)


def wait_ready(base: str, seconds: int = 60) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            status, _, text = call(base, "/v1/ready")
            if status == 200:
                print(f"ready: {text}")
                return
        except OSError:
            pass
        time.sleep(1)
    sys.exit(f"not ready after {seconds} s")


def main(base: str) -> int:
    wait_ready(base)
    flagged = json.loads((PAYLOADS / "flagged.json").read_text(encoding="utf-8"))

    print("the notebook's last payment:")
    status, headers, text = call(base, "/v1/assess", flagged, {"X-Trace-Id": "smoke-1"})
    print(f"  {status} {text}")
    answer = json.loads(text)
    expect(status == 200, "answered 200")
    expect(answer.get("decision") == "block", "blocked")
    expect(bool(answer.get("reasons")) and answer["reasons"][0]["input"] == "V14",
           "top reason V14, as in the notebook")
    expect({k.lower(): v for k, v in headers.items()}.get("x-trace-id") == "smoke-1",
           "trace id sent back")

    typical_file = PAYLOADS / "typical.json"
    if typical_file.exists():
        print("a typical payment:")
        status, _, text = call(base, "/v1/assess",
                               json.loads(typical_file.read_text(encoding="utf-8")))
        print(f"  {status} {text}")
        answer = json.loads(text)
        expect(status == 200 and answer.get("decision") == "allow", "allowed")
        expect(answer.get("reasons") == [], "no reasons for an allowed payment")

    bad_requests = {
        "Amount as text": ({**flagged, "Amount": "1504.93"}, "Amount"),
        "V14 missing": ({k: v for k, v in flagged.items() if k != "V14"}, "V14"),
        "a field name holding a card number": ({**flagged, CARD_LIKE: 1}, "(an unknown field"),
    }
    for name, (body, field) in bad_requests.items():
        print(f"bad request, {name}:")
        status, _, text = call(base, "/v1/assess", body)
        print(f"  {status} {text}")
        error = json.loads(text).get("error", {})
        expect(status == 422 and error.get("code") == "invalid_request", "rejected with 422")
        expect(any(p["field"].startswith(field) for p in error.get("problems", [])),
               f"names the problem: {field}")
        expect("1504.93" not in text and "4111111111111111" not in text,
               "echoes nothing it was sent")

    print("smoke test passed" if not failures else f"smoke test FAILED: {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://localhost:8000"))
