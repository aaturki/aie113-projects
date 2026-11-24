"""The API's contract: exactly what a client sends, and what it gets back.

FastAPI checks every request against these classes before our code runs, rejects anything else
with a clear error, and shows the contract at /docs.
"""
from typing import Annotated, Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StrictFloat, field_validator
from pydantic.config import JsonDict

from fraud_alerts.domain.payment import V_INPUTS
from fraud_alerts.domain.policy import Decision

LARGEST_AMOUNT = 1_000_000.0  # far above any payment in the data; a bigger one is a broken client
LARGEST_V = 1_000.0           # far outside any V value in the data

# Strict numbers: 12.5 and 12 are numbers, "12.5" (text), true, NaN and Infinity are not.
Amount = Annotated[StrictFloat, Field(ge=0, le=LARGEST_AMOUNT, allow_inf_nan=False,
                                      description="The amount paid. Never negative.")]
VNumber = Annotated[StrictFloat, Field(ge=-LARGEST_V, le=LARGEST_V, allow_inf_nan=False,
                                       description="An anonymous input made by the bank")]

EXAMPLE: JsonDict = {  # the notebook's last-cell payment, at its hour (18:51) on the bank's clock
    "timestamp": "2026-11-24T18:51:18+03:00", "Amount": 1504.93,
    "V1": -1.60021129907252, "V2": -3.48813018118561, "V3": -6.45930280667571,
    "V4": 3.24681566349703, "V5": -1.61460769860713, "V6": -1.26037454854632,
    "V7": 0.288223321921388, "V8": -0.0489639910109505, "V9": -0.734974617920653,
    "V10": -4.44148408070017, "V11": 2.94437484242405, "V12": -3.80546898374331,
    "V13": -2.10222683492697, "V14": -6.1061832734711, "V15": -0.641736399701777,
    "V16": -1.55596289626148, "V17": -2.08406707082134, "V18": 0.394247352869229,
    "V19": 0.0833797227600835, "V20": 3.18935489592753, "V21": 1.19117480721903,
    "V22": -0.96714144500067, "V23": -1.46342052446637, "V24": -0.624230851495284,
    "V25": -0.176461532068143, "V26": 0.400348351070197, "V27": 0.152946864261687,
    "V28": 0.477774924576796,
}


class PaymentRequest(BaseModel):
    """One card payment. Amount and V1 to V28 keep the dataset's names, so the reasons in the
    answer name exactly the fields that were sent."""
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [EXAMPLE]})

    timestamp: AwareDatetime = Field(
        description="When the payment happened: ISO 8601 text with a time zone, for example "
                    "2026-11-24T18:51:18+03:00. The model uses its hour on the bank's clock.")
    Amount: Amount
    V1: VNumber
    V2: VNumber
    V3: VNumber
    V4: VNumber
    V5: VNumber
    V6: VNumber
    V7: VNumber
    V8: VNumber
    V9: VNumber
    V10: VNumber
    V11: VNumber
    V12: VNumber
    V13: VNumber
    V14: VNumber
    V15: VNumber
    V16: VNumber
    V17: VNumber
    V18: VNumber
    V19: VNumber
    V20: VNumber
    V21: VNumber
    V22: VNumber
    V23: VNumber
    V24: VNumber
    V25: VNumber
    V26: VNumber
    V27: VNumber
    V28: VNumber

    @field_validator("timestamp", mode="before")
    @classmethod
    def text_only(cls, value: Any) -> Any:
        """A bare number could be seconds or milliseconds, in any time zone: refuse it."""
        if not isinstance(value, str):
            raise ValueError("must be ISO 8601 text with a time zone")
        return value

    def v(self) -> tuple[float, ...]:
        return tuple(getattr(self, name) for name in V_INPUTS)


class ReasonOut(BaseModel):
    input: str = Field(description="V1 to V28, Amount, or hour (the hour on the bank's clock)")
    value: float = Field(description="Its value in this payment")
    typical: float = Field(description="Its typical value among normal payments")
    score_if_typical: float = Field(description="The fraud score if only this input were typical")


class AssessmentResponse(BaseModel):
    score: float = Field(ge=0, le=1, description="Fraud score from 0 to 1. A ranking, not a "
                                                 "promise: 0.9 means more suspicious than 0.5.")
    decision: Decision = Field(description="allow; review (the fraud team checks it); block "
                                           "(stopped now, a person confirms or releases it)")
    review_threshold: float = Field(description="From the model: the fraud team's rule")
    block_threshold: float = Field(description="From the configuration: a business rule")
    hour: int = Field(description="The hour of the day the model used, on the bank's clock")
    reasons: list[ReasonOut] = Field(description="The top reasons, strongest first. Empty when "
                                                 "the payment is allowed.")
    model_version: str
    trace_id: str = Field(description="Quote it to find this request in the service's log")


class Problem(BaseModel):
    field: str
    problem: str


class ErrorBody(BaseModel):
    code: str
    message: str
    problems: list[Problem] = Field(default_factory=list)


class ErrorResponse(BaseModel):
    """Every error has this one shape. It never repeats the values that were sent."""
    error: ErrorBody
    trace_id: str


class Alive(BaseModel):
    status: str = "alive"


class Ready(BaseModel):
    status: str = "ready"
    model_version: str
    review_threshold: float
    block_threshold: float
    bank_timezone: str
    alerts_to_fraud_team: bool = Field(description="Whether blocked payments are announced to "
                                                   "the fraud team's webhook (never the token)")


class NotReady(BaseModel):
    status: str = "not_ready"
    reason: str
