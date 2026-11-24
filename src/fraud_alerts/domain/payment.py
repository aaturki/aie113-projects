"""A card payment as the model sees it: 28 anonymous numbers, the amount and the hour of the day.

The hour has two sources, with one rule each:
- the dataset counts seconds from its first payment, and the file is assumed to start at midnight;
- a real payment happens at a moment in time, and its hour is read on the bank's clock.
"""
from collections.abc import Sequence
from datetime import datetime
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field

V_INPUTS = tuple(f"V{i}" for i in range(1, 29))
FEATURES = (*V_INPUTS, "Amount", "hour")   # the model's inputs, in the order it was trained on

SECONDS_PER_HOUR = 3600
HOURS_PER_DAY = 24

Finite = Annotated[float, Field(allow_inf_nan=False)]


def hour_of_day(time_seconds: float) -> float:
    """The dataset's hour, assuming the data starts at midnight, exactly as the notebook makes
    it."""
    return (time_seconds // SECONDS_PER_HOUR) % HOURS_PER_DAY


def hour_on_clock(moment: datetime, clock: ZoneInfo) -> float:
    """The hour of a real moment on the bank's clock. The same moment written in two time zones
    gets the same hour. A moment without a time zone is ambiguous, so it is refused."""
    if moment.utcoffset() is None:
        raise ValueError("a moment without a time zone has no hour on the bank's clock")
    return float(moment.astimezone(clock).hour)


class Payment(BaseModel):
    """One payment, in the model's own terms."""
    model_config = ConfigDict(frozen=True)

    hour: Finite = Field(ge=0, lt=HOURS_PER_DAY, multiple_of=1.0,
                         description="Hour of the day, 0 to 23")
    amount: Finite = Field(ge=0)
    v: tuple[Finite, ...] = Field(min_length=len(V_INPUTS), max_length=len(V_INPUTS))

    @classmethod
    def from_dataset(cls, time_seconds: float, amount: float, v: Sequence[float]) -> "Payment":
        """A row of the dataset, with its Time in seconds."""
        return cls(hour=hour_of_day(time_seconds), amount=amount, v=tuple(v))

    def features(self) -> dict[str, float]:
        """The one place where a payment becomes the model's inputs. Training builds the same
        columns with the same hour_of_day rule, so serving and training cannot drift apart."""
        return {**dict(zip(V_INPUTS, self.v, strict=True)),
                "Amount": self.amount, "hour": self.hour}
