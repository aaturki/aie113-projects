"""The reasons rule: what if this one input were typical?"""
import pytest

from fraud_alerts.domain.reasons import top_reasons, typical_variants

pytestmark = pytest.mark.unit
FEATURES = {"V14": -6.0, "V10": -4.0, "Amount": 100.0}
TYPICAL = {"V14": 0.1, "V10": -0.1, "Amount": 20.0}


def test_each_variant_changes_exactly_one_input_to_its_typical_value() -> None:
    variants = typical_variants(FEATURES, TYPICAL)
    assert set(variants) == set(FEATURES)
    for name, variant in variants.items():
        assert {key for key in variant if variant[key] != FEATURES[key]} == {name}
        assert variant[name] == TYPICAL[name]


def test_reasons_are_ranked_by_how_far_the_score_falls() -> None:
    reasons = top_reasons(0.99, FEATURES, TYPICAL, {"V14": 0.10, "V10": 0.50, "Amount": 0.95})
    assert [reason.input for reason in reasons] == ["V14", "V10", "Amount"]
    assert (reasons[0].value, reasons[0].typical, reasons[0].score_if_typical) == (-6.0, 0.1, 0.10)


def test_an_input_whose_typical_value_does_not_lower_the_score_is_no_reason() -> None:
    reasons = top_reasons(0.5, FEATURES, TYPICAL, {"V14": 0.2, "V10": 0.5, "Amount": 0.7})
    assert [reason.input for reason in reasons] == ["V14"]


def test_there_are_at_most_three_reasons() -> None:
    features = {f"V{i}": -1.0 for i in range(1, 11)}
    falls = {name: 0.5 - i * 0.01 for i, name in enumerate(features)}
    assert len(top_reasons(0.9, features, dict.fromkeys(features, 0.0), falls)) == 3


def test_a_reason_holds_only_the_input_name_and_numbers() -> None:
    reason = top_reasons(0.99, FEATURES, TYPICAL, {"V14": 0.1, "V10": 0.99, "Amount": 0.99})[0]
    assert set(reason.model_dump()) == {"input", "value", "typical", "score_if_typical"}
