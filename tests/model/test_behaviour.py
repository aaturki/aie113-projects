"""How the real model behaves: direction (a reason really pushes the score), invariance (what
the model does not use changes nothing), repeatability."""
import json
from collections.abc import Mapping
from datetime import UTC, date, datetime

import pytest
from fastapi.testclient import TestClient

from fraud_alerts.adapters.model_bundle import ModelBundle
from fraud_alerts.domain.payment import FEATURES, V_INPUTS, Payment
from fraud_alerts.service.alerts import AlertService
from helpers import GOLDEN, ROOT, dataset_request

pytestmark = pytest.mark.model
PAYMENTS = {saved["name"]: saved["payment"] for saved in GOLDEN["payments"]}


def from_dataset(raw: Mapping[str, float]) -> Payment:
    return Payment.from_dataset(raw["Time"], raw["Amount"], [raw[name] for name in V_INPUTS])


def with_inputs(features: Mapping[str, float]) -> Payment:
    return Payment(hour=features["hour"], amount=features["Amount"],
                   v=tuple(features[name] for name in V_INPUTS))


@pytest.mark.parametrize("name", PAYMENTS)
def test_making_the_top_reason_typical_lowers_the_score(bundle: ModelBundle, name: str) -> None:
    service = AlertService(bundle, block_threshold=0.9)
    payment = from_dataset(PAYMENTS[name])
    before = service.assess(payment)
    top = before.reasons[0]
    after = service.assess(with_inputs(payment.features() | {top.input: top.typical}))
    assert after.score < before.score
    assert after.score == pytest.approx(top.score_if_typical, abs=1e-12)


@pytest.mark.parametrize("name", PAYMENTS)
def test_every_reason_names_a_real_input_and_lowers_the_score(bundle: ModelBundle,
                                                              name: str) -> None:
    result = AlertService(bundle, block_threshold=0.9).assess(from_dataset(PAYMENTS[name]))
    assert result.reasons
    for reason in result.reasons:
        assert reason.input in FEATURES
        assert reason.score_if_typical < result.score


def test_the_day_does_not_matter_only_the_hour(api: TestClient) -> None:
    days = (date(2026, 11, 24), date(2027, 3, 1), date(2030, 1, 15))
    scores = {api.post("/v1/assess", json=dataset_request(PAYMENTS["last cell"], day))
              .json()["score"] for day in days}
    assert len(scores) == 1


def test_the_same_moment_written_in_utc_gets_the_same_score(api: TestClient) -> None:
    body = dataset_request(PAYMENTS["last cell"])
    in_utc = body | {"timestamp": datetime.fromisoformat(body["timestamp"])
                     .astimezone(UTC).isoformat()}
    assert (api.post("/v1/assess", json=body).json()["score"]
            == api.post("/v1/assess", json=in_utc).json()["score"])


def test_the_typical_payment_is_allowed_with_a_tiny_score(api: TestClient) -> None:
    typical = json.loads((ROOT / "payloads" / "typical.json").read_text(encoding="utf-8"))
    answer = api.post("/v1/assess", json=typical).json()
    assert answer["decision"] == "allow"
    assert answer["score"] < 0.01
    assert answer["reasons"] == []


def test_the_same_payment_always_gets_the_same_score(api: TestClient) -> None:
    body = dataset_request(PAYMENTS["first false alarm"])
    assert len({api.post("/v1/assess", json=body).json()["score"] for _ in range(5)}) == 1
