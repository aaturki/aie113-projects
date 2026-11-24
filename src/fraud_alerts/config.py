"""Every setting of the service, in one place.

Each one can be changed with an environment variable that starts with FRAUD_, for example
FRAUD_BLOCK_THRESHOLD=0.95. Nothing else in the code reads the environment. A wrong value
stops the service at start-up with a clear message, instead of running with it.
"""
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="FRAUD_", frozen=True)

    model_dir: Path = Field(Path("artifacts"),
                            description="The folder with fraud_model.joblib and model_info.json")
    block_threshold: float = Field(
        0.9, gt=0, le=1,
        description="A business rule: at or above this score a payment is blocked. On the "
                    "validation payments, 38 of the 39 payments that scored 0.9 or more were "
                    "real fraud.")
    bank_timezone: str = Field("Asia/Riyadh",
                               description="The clock that gives a payment its hour of the day")
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    @field_validator("bank_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown time zone {value!r}") from error
        return value

    @property
    def bank_clock(self) -> ZoneInfo:
        return ZoneInfo(self.bank_timezone)
