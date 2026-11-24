"""A pretend fraud team for the smoke test: it receives the "payment blocked" webhook and checks
the caller's token, as the real fraud team's system would. Standard library only.

    GET  /health    200
    POST /alerts    202 if the token is right, 401 if not; remembers what arrived
    GET  /received  what arrived: the trace id, the score, the reasons, and whether the token
                    was right. Never the token itself.

The token comes from the same secret file the service gets: /run/secrets/fraud_alert_webhook_token.
"""
import hmac
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

TOKEN = Path("/run/secrets/fraud_alert_webhook_token").read_text(encoding="utf-8").strip()
KEPT = ("event", "trace_id", "score", "reasons", "model_version")
received: list[dict[str, Any]] = []


class FraudTeam(BaseHTTPRequestHandler):
    def log_message(self, *args: Any) -> None:
        pass                                  # request lines would only be noise here

    def reply(self, status: int, body: Any) -> None:
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.reply(200, {"status": "ok"})
        elif self.path == "/received":
            self.reply(200, received)
        else:
            self.reply(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/alerts":
            self.reply(404, {"error": "not found"})
            return
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or b"{}")
        given = self.headers.get("Authorization", "").encode()
        authorized = hmac.compare_digest(given, f"Bearer {TOKEN}".encode())
        received.append({"authorized": authorized, **{key: body.get(key) for key in KEPT}})
        self.reply(202 if authorized else 401, {"accepted": authorized})


ThreadingHTTPServer(("0.0.0.0", 8080), FraudTeam).serve_forever()
