"""The fraud team's webhook: what it sends, and why a broken fraud team never breaks the service."""
import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest
from pydantic import SecretStr

from fraud_alerts.adapters.webhook import WebhookNotifier

pytestmark = pytest.mark.unit
TOKEN = "practice-token-123"   # gitleaks:allow (made up for this test)


class Receiver(BaseHTTPRequestHandler):
    status: ClassVar[int] = 202
    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        length = int(self.headers["Content-Length"])
        Receiver.received.append({"authorization": self.headers["Authorization"],
                                  "body": json.loads(self.rfile.read(length))})
        self.send_response(Receiver.status)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


@pytest.fixture
def receiver() -> Iterator[str]:
    Receiver.received, Receiver.status = [], 202
    server = HTTPServer(("127.0.0.1", 0), Receiver)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/alerts"
    server.shutdown()
    server.server_close()


def notifier(url: str) -> WebhookNotifier:
    return WebhookNotifier(url=url, token=SecretStr(TOKEN))


def test_a_blocked_payment_is_announced_with_the_token_and_no_payment_values(
        receiver: str) -> None:
    assert notifier(receiver).payment_blocked("trace-1", 0.99886, ["V14", "V10"], "1.0.0")
    [call] = Receiver.received
    assert call["authorization"] == f"Bearer {TOKEN}"
    assert call["body"] == {"event": "payment_blocked", "trace_id": "trace-1", "score": 0.9989,
                            "reasons": ["V14", "V10"], "model_version": "1.0.0"}


def test_a_fraud_team_answering_with_an_error_counts_as_not_reached(receiver: str) -> None:
    Receiver.status = 500
    assert notifier(receiver).payment_blocked("trace-2", 0.95, [], "1.0.0") is False


def test_an_unreachable_fraud_team_never_breaks_the_service() -> None:
    assert notifier("http://127.0.0.1:9/alerts").payment_blocked("t", 0.95, [], "1.0.0") is False


def test_the_token_never_shows_when_the_notifier_is_printed() -> None:
    shown = notifier("https://fraud-team.example/alerts")
    assert TOKEN not in repr(shown)
    assert TOKEN not in str(shown)
