"""The log's safety net: secret-sounding fields and known secret values never come out."""
import json
from collections.abc import Sequence
from typing import Any

import pytest

from fraud_alerts.api.logs import HIDDEN, MaskingRenderer

pytestmark = pytest.mark.unit


def render(event: dict[str, Any], secrets: Sequence[str] = ()) -> dict[str, Any]:
    line: dict[str, Any] = json.loads(MaskingRenderer(secrets)(None, "info", dict(event)))
    return line


def test_a_field_whose_name_sounds_secret_is_hidden() -> None:
    line = render({"event": "x", "authorization": "Bearer abc", "api_key": "k",
                   "webhook_token": "t", "db_password": "p"})
    assert {line[name] for name in ("authorization", "api_key", "webhook_token",
                                     "db_password")} == {HIDDEN}


def test_a_known_secret_is_hidden_wherever_it_appears() -> None:
    line = render({"event": "called https://x.example/?t=s3cr3t-value",
                   "detail": ["first", "s3cr3t-value"]}, secrets=["s3cr3t-value"])
    assert "s3cr3t-value" not in json.dumps(line)
    assert line["detail"] == ["first", HIDDEN]


def test_ordinary_fields_are_kept_as_they_are() -> None:
    event = {"event": "assessed", "decision": "block", "trace_id": "t-1", "score": 0.999}
    assert render(event, secrets=["s3cr3t-value"]) == event
