"""The business rule: which fraud scores are allowed, reviewed or blocked.

The review threshold comes with the model: the notebook chose it on the validation payments
with the fraud team's rule (at least 8 of every 10 alerts are real fraud). The block threshold
is a business decision on top of it, set in the configuration.
"""
from dataclasses import dataclass
from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"    # the payment goes to the fraud team for a check
    BLOCK = "block"      # the payment is stopped now and the fraud team is told; a person
                         # still confirms or releases it (the track's README: no block
                         # without a human check)


@dataclass(frozen=True)
class Thresholds:
    """Checked once, when the service starts: a block threshold below the review threshold,
    or a threshold outside 0 to 1, is a configuration mistake, not something to run with."""
    review_at: float
    block_at: float

    def __post_init__(self) -> None:
        if not 0 < self.review_at <= self.block_at <= 1:
            raise ValueError(f"the thresholds need 0 < review ({self.review_at}) "
                             f"<= block ({self.block_at}) <= 1")


def decide(score: float, thresholds: Thresholds) -> Decision:
    """A score at a threshold counts as above it: the notebook alerts on score >= threshold."""
    if score >= thresholds.block_at:
        return Decision.BLOCK
    if score >= thresholds.review_at:
        return Decision.REVIEW
    return Decision.ALLOW
