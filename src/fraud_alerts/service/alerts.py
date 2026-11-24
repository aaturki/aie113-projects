"""Use case: assess one payment, giving its fraud score, the decision, and the reasons for an
alert."""
from dataclasses import dataclass

from fraud_alerts.domain.payment import Payment
from fraud_alerts.domain.policy import Decision, Thresholds, decide
from fraud_alerts.domain.reasons import Reason, top_reasons, typical_variants
from fraud_alerts.service.interfaces import FraudModel


@dataclass(frozen=True)
class Assessment:
    score: float
    decision: Decision
    reasons: list[Reason]
    model_version: str
    thresholds: Thresholds


class AlertService:
    def __init__(self, model: FraudModel, block_threshold: float) -> None:
        self.model = model
        # The review threshold travels with the model; the block threshold is the business's.
        self.thresholds = Thresholds(review_at=model.review_threshold, block_at=block_threshold)

    def assess(self, payment: Payment) -> Assessment:
        features = payment.features()
        score = self.model.scores([features])[0]
        decision = decide(score, self.thresholds)
        # An allowed payment needs no reasons and costs no extra model call.
        reasons = [] if decision is Decision.ALLOW else self.reasons(score, features)
        return Assessment(score=score, decision=decision, reasons=reasons,
                          model_version=self.model.version, thresholds=self.thresholds)

    def reasons(self, score: float, features: dict[str, float]) -> list[Reason]:
        """Every what-if variant, scored in one batched call."""
        variants = typical_variants(features, self.model.typical)
        scores = self.model.scores(list(variants.values()))
        return top_reasons(score, features, self.model.typical,
                           dict(zip(variants, scores, strict=True)))
