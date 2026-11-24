"""The use case, with a stand-in model: what it asks the model, and what it decides."""
import pytest

from fraud_alerts.domain.payment import Payment
from fraud_alerts.domain.policy import Decision
from fraud_alerts.service.alerts import AlertService
from helpers import FakeModel

pytestmark = pytest.mark.unit


def payment(v14: float = 0.0, v10: float = 0.0) -> Payment:
    v = [0.0] * 28
    v[13], v[9] = v14, v10
    return Payment(hour=13, amount=25.0, v=tuple(v))


def test_an_allowed_payment_costs_one_model_call_and_has_no_reasons() -> None:
    model = FakeModel()
    result = AlertService(model, block_threshold=0.9).assess(payment())
    assert (result.decision, result.reasons) == (Decision.ALLOW, [])
    assert model.calls == [1]


def test_an_alert_gets_its_reasons_from_one_batched_call() -> None:
    model = FakeModel()
    result = AlertService(model, block_threshold=0.9).assess(payment(v14=-6.0))
    assert result.decision is Decision.REVIEW
    assert model.calls == [1, 30]          # the payment, then all 30 what-ifs at once
    assert [reason.input for reason in result.reasons] == ["V14"]
    assert result.reasons[0].score_if_typical < result.score


def test_a_blocked_payment_has_its_reasons_strongest_first() -> None:
    result = AlertService(FakeModel(), block_threshold=0.9).assess(payment(v14=-6.0, v10=-4.0))
    assert result.decision is Decision.BLOCK
    assert [reason.input for reason in result.reasons] == ["V14", "V10"]


def test_the_review_threshold_comes_with_the_model_and_block_from_the_business() -> None:
    service = AlertService(FakeModel(review_threshold=0.4), block_threshold=0.9)
    assert (service.thresholds.review_at, service.thresholds.block_at) == (0.4, 0.9)
    assert service.assess(payment()).model_version == "fake-1"


def test_a_block_threshold_below_the_models_review_threshold_is_refused() -> None:
    with pytest.raises(ValueError, match="thresholds"):
        AlertService(FakeModel(review_threshold=0.4), block_threshold=0.3)
