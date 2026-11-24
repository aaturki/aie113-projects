"""Why a payment was flagged: what if one input were typical?

For each input, take the same payment with only that input set to its typical value (its median
among the normal training payments) and score it again. The inputs whose typical value lowers the
score the most are the reasons. This only needs the model's scores, so it works for any model.
"""
from collections.abc import Mapping

from pydantic import BaseModel

TOP_REASONS = 3


class Reason(BaseModel):
    input: str               # the input's name, for example "V14"
    value: float             # its value in this payment
    typical: float           # its typical value among normal payments
    score_if_typical: float  # the fraud score if only this input were typical


def typical_variants(features: Mapping[str, float],
                     typical: Mapping[str, float]) -> dict[str, dict[str, float]]:
    """One variant per input: the same payment with only that input made typical."""
    return {name: {**features, name: typical[name]} for name in features}


def top_reasons(score: float, features: Mapping[str, float], typical: Mapping[str, float],
                score_if_typical: Mapping[str, float], limit: int = TOP_REASONS) -> list[Reason]:
    """The inputs whose typical value lowers the score the most, strongest first. An input whose
    typical value does not lower the score is not a reason."""
    ranked = sorted(features, key=lambda name: score - score_if_typical[name], reverse=True)
    return [Reason(input=name, value=features[name], typical=typical[name],
                   score_if_typical=score_if_typical[name])
            for name in ranked if score_if_typical[name] < score][:limit]
