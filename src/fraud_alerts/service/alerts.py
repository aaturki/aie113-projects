"""Use case: assess one payment, giving its fraud score, the decision, and the reasons for an
alert."""
from dataclasses import dataclass

from fraud_alerts.domain.payment import Payment
from fraud_alerts.domain.policy import Decision, decide
from fraud_alerts.domain.reasons import Reason, top_reasons, typical_variants
from fraud_alerts.service.interfaces import FraudModel


@dataclass(frozen=True)
class Assessment:
    score: float
    decision: Decision
    reasons: list[Reason]
    model_version: str
    review_threshold: float
    block_threshold: float


@dataclass
class AlertService:
    model: FraudModel
    block_threshold: float

    def assess(self, payment: Payment) -> Assessment:
        features = payment.features()
        score = self.model.scores([features])[0]
        decision = decide(score, self.model.review_threshold, self.block_threshold)
        # An allowed payment needs no reasons and costs no extra model call.
        reasons = [] if decision is Decision.ALLOW else self.reasons(score, features)
        return Assessment(score=score, decision=decision, reasons=reasons,
                          model_version=self.model.version,
                          review_threshold=self.model.review_threshold,
                          block_threshold=self.block_threshold)

    def reasons(self, score: float, features: dict[str, float]) -> list[Reason]:
        """Every what-if variant, scored in one batched call."""
        variants = typical_variants(features, self.model.typical)
        scores = self.model.scores(list(variants.values()))
        return top_reasons(score, features, self.model.typical,
                           dict(zip(variants, scores, strict=True)))
