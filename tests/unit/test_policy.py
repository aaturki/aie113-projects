"""The business rule: allow, review or block."""
import pytest

from fraud_alerts.domain.policy import Decision, Thresholds, decide

pytestmark = pytest.mark.unit
THRESHOLDS = Thresholds(review_at=0.4, block_at=0.9)


@pytest.mark.parametrize(("score", "expected"), [
    (0.0, Decision.ALLOW),
    (0.3999, Decision.ALLOW),
    (0.4, Decision.REVIEW),       # exactly at the threshold counts as above, as in the notebook
    (0.8999, Decision.REVIEW),
    (0.9, Decision.BLOCK),
    (1.0, Decision.BLOCK),
])
def test_the_decision_flips_exactly_at_each_threshold(score: float, expected: Decision) -> None:
    assert decide(score, THRESHOLDS) is expected


@pytest.mark.parametrize(("review", "block"), [(0.9, 0.4), (0.0, 0.9), (0.4, 1.5), (-0.1, 0.5)])
def test_thresholds_that_make_no_sense_are_refused(review: float, block: float) -> None:
    with pytest.raises(ValueError, match="thresholds"):
        Thresholds(review_at=review, block_at=block)


def test_equal_thresholds_mean_every_alert_is_blocked() -> None:
    assert decide(0.5, Thresholds(review_at=0.5, block_at=0.5)) is Decision.BLOCK
