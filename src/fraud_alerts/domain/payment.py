"""A card payment as the model sees it: 28 anonymous numbers, the amount and the hour."""
from pydantic import BaseModel, ConfigDict, Field

V_INPUTS = tuple(f"V{i}" for i in range(1, 29))
FEATURES = (*V_INPUTS, "Amount", "hour")   # the model's inputs, in the order it was trained on

SECONDS_PER_HOUR = 3600
HOURS_PER_DAY = 24


def hour_of_day(time_seconds: float) -> float:
    """The hour, assuming the data starts at midnight, exactly as the notebook makes it."""
    return (time_seconds // SECONDS_PER_HOUR) % HOURS_PER_DAY


class Payment(BaseModel):
    """One payment in the dataset's own terms."""
    model_config = ConfigDict(frozen=True)

    time: float = Field(ge=0, description="Seconds since the first payment in the data")
    amount: float = Field(ge=0)
    v: tuple[float, ...] = Field(min_length=len(V_INPUTS), max_length=len(V_INPUTS))

    def features(self) -> dict[str, float]:
        """The one place where a payment becomes the model's inputs. Training builds the same
        columns with the same hour_of_day rule, so serving and training cannot drift apart."""
        return {**dict(zip(V_INPUTS, self.v, strict=True)),
                "Amount": self.amount, "hour": hour_of_day(self.time)}
