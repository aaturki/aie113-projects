"""The business rule: which fraud scores are allowed, reviewed or blocked.

The review threshold comes with the model: the notebook chose it on the validation payments
with the fraud team's rule (at least 8 of every 10 alerts are real fraud). The block threshold
is a business decision on top of it, set in the configuration.
"""
from enum import StrEnum


class Decision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"    # the payment goes to the fraud team for a check
    BLOCK = "block"      # the payment is stopped now, and the fraud team is told


def decide(score: float, review_at: float, block_at: float) -> Decision:
    """A score at a threshold counts as above it: the notebook alerts on score >= threshold."""
    if score >= block_at:
        return Decision.BLOCK
    if score >= review_at:
        return Decision.REVIEW
    return Decision.ALLOW
