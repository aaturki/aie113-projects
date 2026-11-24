"""A payment and its inputs: the hour rules, the order of the inputs, impossible payments."""
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from fraud_alerts.domain.payment import FEATURES, Payment, hour_of_day, hour_on_clock

pytestmark = pytest.mark.unit
RIYADH = ZoneInfo("Asia/Riyadh")


@pytest.mark.parametrize(("seconds", "hour"), [
    (0, 0), (3599, 0), (3600, 1), (86_399, 23), (86_400, 0), (154_278, 18)])
def test_the_dataset_hour_follows_the_notebooks_rule(seconds: float, hour: float) -> None:
    assert hour_of_day(seconds) == hour


def test_the_same_moment_in_three_time_zones_has_the_same_hour() -> None:
    in_riyadh = datetime(2026, 11, 24, 18, 51, 18, tzinfo=RIYADH)
    hours = {hour_on_clock(moment, RIYADH) for moment in (
        in_riyadh, in_riyadh.astimezone(UTC), in_riyadh.astimezone(ZoneInfo("America/New_York")))}
    assert hours == {18.0}


def test_a_moment_without_a_time_zone_is_refused() -> None:
    with pytest.raises(ValueError, match="time zone"):
        hour_on_clock(datetime(2026, 11, 24, 18, 51), RIYADH)


def test_the_inputs_come_out_in_the_order_the_model_was_trained_on() -> None:
    payment = Payment(hour=18, amount=1504.93, v=tuple(float(i) for i in range(1, 29)))
    features = payment.features()
    assert tuple(features) == FEATURES
    assert (features["V1"], features["V28"]) == (1.0, 28.0)
    assert (features["Amount"], features["hour"]) == (1504.93, 18)


def test_a_dataset_row_gets_its_hour_from_the_notebooks_rule() -> None:
    assert Payment.from_dataset(154_278.0, 1504.93, [0.0] * 28).hour == 18


@pytest.mark.parametrize("change", [
    {"amount": -1.0}, {"amount": float("nan")}, {"hour": 24.0}, {"hour": 3.5},
    {"v": (0.0,) * 27}, {"v": (float("inf"),) + (0.0,) * 27}])
def test_an_impossible_payment_is_refused(change: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Payment(**({"hour": 12.0, "amount": 10.0, "v": (0.0,) * 28} | change))
