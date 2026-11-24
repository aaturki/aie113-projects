"""The API from the outside, like a real client, with a stand-in model."""
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from fraud_alerts.api.app import create_app
from fraud_alerts.config import Settings
from fraud_alerts.domain.payment import FEATURES
from helpers import FakeModel, request_body

pytestmark = pytest.mark.integration
ANSWER_KEYS = {"score", "decision", "review_threshold", "block_threshold", "hour", "reasons",
               "model_version", "trace_id"}


def settings(**changes: Any) -> Settings:
    return Settings(**({"block_threshold": 0.9, "bank_timezone": "Asia/Riyadh",
                        "log_level": "INFO"} | changes))


@pytest.fixture
def client() -> Iterator[TestClient]:
    with TestClient(create_app(settings(), model=FakeModel())) as test_client:
        yield test_client


def assess(client: TestClient, body: Any, **headers: str) -> Any:
    return client.post("/v1/assess", json=body, headers=headers)


def problems(response: Any) -> list[str]:
    return [problem["field"] for problem in response.json()["error"]["problems"]]


# ---------- good requests ----------

def test_a_quiet_payment_is_allowed_with_no_reasons(client: TestClient) -> None:
    response = assess(client, request_body())
    assert response.status_code == 200
    answer = response.json()
    assert set(answer) == ANSWER_KEYS
    assert (answer["decision"], answer["reasons"], answer["score"]) == ("allow", [], 0.02)
    assert (answer["review_threshold"], answer["block_threshold"]) == (0.4, 0.9)
    assert (answer["hour"], answer["model_version"]) == (18, "fake-1")


def test_a_suspicious_payment_is_reviewed_and_its_reason_names_a_field_sent(
        client: TestClient) -> None:
    answer = assess(client, request_body(V14=-6.0)).json()
    assert answer["decision"] == "review"
    reason = answer["reasons"][0]
    assert (reason["input"], reason["value"], reason["typical"]) == ("V14", -6.0, 0.09)
    assert reason["score_if_typical"] < answer["score"]


def test_a_very_suspicious_payment_is_blocked(client: TestClient) -> None:
    answer = assess(client, request_body(V14=-6.0, V10=-4.0)).json()
    assert answer["decision"] == "block"
    assert [reason["input"] for reason in answer["reasons"]] == ["V14", "V10"]
    assert all(reason["input"] in FEATURES for reason in answer["reasons"])


def test_the_same_moment_in_two_time_zones_gets_the_same_answer(client: TestClient) -> None:
    riyadh = assess(client, request_body(timestamp="2026-11-24T18:51:18+03:00")).json()
    utc = assess(client, request_body(timestamp="2026-11-24T15:51:18Z")).json()
    assert riyadh["hour"] == utc["hour"] == 18
    assert riyadh["score"] == utc["score"]


def test_the_trace_id_is_kept_when_sensible_and_made_when_not(client: TestClient) -> None:
    kept = assess(client, request_body(), **{"X-Trace-Id": "case-42"})
    assert kept.headers["x-trace-id"] == kept.json()["trace_id"] == "case-42"
    replaced = assess(client, request_body(), **{"X-Trace-Id": "<script>alert(1)</script>"})
    assert replaced.json()["trace_id"] != "<script>alert(1)</script>"
    assert len(replaced.json()["trace_id"]) == 32


# ---------- bad requests: refused at the door, with the field named ----------

@pytest.mark.parametrize(("change", "field"), [
    ({"Amount": "25.0"}, "Amount"),                    # a number sent as text
    ({"Amount": True}, "Amount"),
    ({"Amount": -1.0}, "Amount"),                      # a negative amount
    ({"Amount": 2e6}, "Amount"),                       # far beyond any real payment
    ({"V3": 1e5}, "V3"),
    ({"V14": None}, "V14"),
    ({"timestamp": "2026-11-24T18:51:18"}, "timestamp"),   # no time zone
    ({"timestamp": 1_764_000_000}, "timestamp"),           # a bare number
    ({"timestamp": "yesterday"}, "timestamp"),
    ({"colour": "red"}, "colour"),                         # not part of the contract
])
def test_a_bad_field_is_refused_and_named(client: TestClient, change: dict[str, Any],
                                          field: str) -> None:
    response = assess(client, request_body(**change))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert problems(response) == [field]


def test_a_missing_field_is_named(client: TestClient) -> None:
    body = request_body()
    del body["V14"]
    response = assess(client, body)
    assert (response.status_code, problems(response)) == (422, ["V14"])


@pytest.mark.parametrize("number", ["NaN", "Infinity", "-Infinity"])
def test_not_a_number_and_infinity_are_refused(client: TestClient, number: str) -> None:
    text = json.dumps(request_body()).replace('"Amount": 25.0', f'"Amount": {number}')
    response = client.post("/v1/assess", content=text,
                           headers={"content-type": "application/json"})
    assert (response.status_code, problems(response)) == (422, ["Amount"])


@pytest.mark.parametrize("body", ["hello", "", "[1, 2]", "{}"])
def test_a_body_that_is_not_a_payment_is_refused(client: TestClient, body: str) -> None:
    response = client.post("/v1/assess", content=body,
                           headers={"content-type": "application/json"})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_an_oversized_body_is_refused_before_it_is_read(client: TestClient) -> None:
    response = client.post("/v1/assess", content="x" * 20_000,
                           headers={"content-type": "application/json"})
    assert (response.status_code, response.json()["error"]["code"]) == (413, "too_large")


# ---------- errors leak nothing ----------

def test_an_error_never_repeats_the_values_sent(client: TestClient) -> None:
    body = request_body(Amount="MARKER-1234.56", V5="MARKER-V5", timestamp="MARKER-TIME")
    text = assess(client, body).text
    assert "MARKER" not in text
    assert "1234.56" not in text


def test_a_field_name_that_could_hold_data_is_not_repeated(client: TestClient) -> None:
    response = assess(client, request_body(card_4111111111111111=1))
    assert "4111" not in response.text
    assert problems(response) == ["(an unknown field, name not shown)"]


def test_an_unexpected_failure_says_nothing_about_its_cause() -> None:
    def broken(_: Any) -> float:
        raise RuntimeError("database password is hunter2")

    app = create_app(settings(), model=FakeModel(rule=broken))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = assess(client, request_body())
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "hunter2" not in response.text
    assert "RuntimeError" not in response.text


@pytest.mark.parametrize(("method", "path", "status", "code"), [
    ("GET", "/v2/assess", 404, "not_found"), ("GET", "/v1/assess", 405, "method_not_allowed")])
def test_a_wrong_address_or_method_gets_the_same_error_shape(
        client: TestClient, method: str, path: str, status: int, code: str) -> None:
    response = client.request(method, path)
    assert (response.status_code, response.json()["error"]["code"]) == (status, code)
    assert set(response.json()) == {"error", "trace_id"}


# ---------- health and readiness ----------

def test_health_and_readiness_when_the_model_is_loaded(client: TestClient) -> None:
    assert client.get("/v1/health").json() == {"status": "alive"}
    assert client.get("/v1/ready").json() == {
        "status": "ready", "model_version": "fake-1", "review_threshold": 0.4,
        "block_threshold": 0.9, "bank_timezone": "Asia/Riyadh"}


def test_without_a_model_the_service_is_alive_but_not_ready(tmp_path: Path) -> None:
    with TestClient(create_app(settings(model_dir=tmp_path))) as client:
        assert client.get("/v1/health").status_code == 200
        ready = client.get("/v1/ready")
        assert (ready.status_code, ready.json()["status"]) == (503, "not_ready")
        refused = assess(client, request_body())
        assert (refused.status_code, refused.json()["error"]["code"]) == (503, "not_ready")


def test_a_block_threshold_below_the_review_threshold_means_not_ready() -> None:
    app = create_app(settings(block_threshold=0.3), model=FakeModel(review_threshold=0.4))
    with TestClient(app) as client:
        assert client.get("/v1/ready").status_code == 503


def test_the_contract_is_published(client: TestClient) -> None:
    assert client.get("/").json()["contract"] == "/docs"
    assert client.get("/docs").status_code == 200
    contract = client.get("/openapi.json").json()
    assert {"/v1/assess", "/v1/health", "/v1/ready"} <= set(contract["paths"])


# ---------- the log ----------

def test_the_log_holds_the_decision_but_no_payment_value(
        client: TestClient, capsys: pytest.CaptureFixture[str]) -> None:
    assess(client, request_body(Amount=1234.56, V14=-6.789), **{"X-Trace-Id": "log-1"})
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()
             if line.startswith("{")]
    assessed = [line for line in lines if line["event"] == "assessed"]
    assert assessed
    assert assessed[0]["trace_id"] == "log-1"
    assert assessed[0]["decision"] == "review"
    text = json.dumps(lines)
    assert "1234.56" not in text
    assert "6.789" not in text
