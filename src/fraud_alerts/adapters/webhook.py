"""The fraud team's webhook: tells them, within seconds, that a payment was blocked.

The token proves to the fraud team that the call comes from this service. It is kept as a
SecretStr, which prints as '**********', and is unwrapped in exactly one place: the
Authorization header of the request. It never goes into a log, an error or a return value.
"""
import json
import urllib.error
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import SecretStr

TIMEOUT_SECONDS = 3.0


@dataclass(frozen=True)
class WebhookNotifier:
    url: str
    token: SecretStr

    def payment_blocked(self, trace_id: str, score: float, reasons: Sequence[str],
                        model_version: str) -> bool:
        body = {"event": "payment_blocked", "trace_id": trace_id, "score": round(score, 4),
                "reasons": list(reasons), "model_version": model_version}
        request = urllib.request.Request(
            self.url, data=json.dumps(body).encode(), method="POST",
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.token.get_secret_value()}"})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return 200 <= int(response.status) < 300
        except (urllib.error.URLError, TimeoutError, OSError):
            # The caller logs "not reached" with the trace id; the error itself may hold the
            # request, so it is not passed on.
            return False
