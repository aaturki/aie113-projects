"""The real model on the reference payments (the test period it never learned from): the agreed
quality floor, the two baselines, and reasons for every alert."""
import numpy as np
import pandas as pd
import pytest

from fraud_alerts.adapters.model_bundle import ModelBundle
from fraud_alerts.domain.payment import V_INPUTS, Payment
from fraud_alerts.service.alerts import AlertService
from fraud_alerts.training.data import split_by_time

pytestmark = [pytest.mark.model, pytest.mark.data]
AGREED_RECALL = 0.70        # catch at least 70% of the frauds
AGREED_PRECISION = 0.80     # at least 8 of every 10 alerts are real fraud
AMOUNT_RULE = 1000


@pytest.fixture(scope="module")
def reference(data: pd.DataFrame) -> pd.DataFrame:
    return split_by_time(data)[2]


@pytest.fixture(scope="module")
def payments(reference: pd.DataFrame) -> list[Payment]:
    return [Payment.from_dataset(row["Time"], row["Amount"], [row[name] for name in V_INPUTS])
            for row in reference.to_dict("records")]


@pytest.fixture(scope="module")
def alerts(bundle: ModelBundle, payments: list[Payment]) -> np.ndarray:
    scores = np.array(bundle.scores([payment.features() for payment in payments]))
    return scores >= bundle.review_threshold


def test_the_model_catches_the_agreed_share_of_frauds_with_few_false_alarms(
        reference: pd.DataFrame, alerts: np.ndarray) -> None:
    frauds = reference["Class"].to_numpy() == 1
    caught = int((alerts & frauds).sum())
    recall, precision = caught / int(frauds.sum()), caught / int(alerts.sum())
    assert recall >= AGREED_RECALL, f"caught only {recall:.1%} of the frauds"
    assert precision >= AGREED_PRECISION, f"only {precision:.1%} of the alerts are fraud"


def test_the_model_beats_both_baselines(reference: pd.DataFrame, alerts: np.ndarray) -> None:
    frauds = reference["Class"].to_numpy() == 1
    rule = reference["Amount"].to_numpy() > AMOUNT_RULE
    model_caught, rule_caught = int((alerts & frauds).sum()), int((rule & frauds).sum())
    assert model_caught > rule_caught > 0       # "always not fraud" catches none at all
    assert model_caught / int(alerts.sum()) > rule_caught / int(rule.sum())


def test_every_alert_has_reasons_and_its_top_reason_lowers_the_score(
        bundle: ModelBundle, payments: list[Payment], alerts: np.ndarray) -> None:
    service = AlertService(bundle, block_threshold=0.9)
    flagged = [payment for payment, alert in zip(payments, alerts, strict=True) if alert]
    assert flagged
    for payment in flagged:
        result = service.assess(payment)
        assert result.reasons, f"an alert scoring {result.score:.3f} has no reason"
        assert result.reasons[0].score_if_typical < result.score
