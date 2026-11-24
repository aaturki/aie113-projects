"""Every setting of the service, in one place.

Each one can be changed with an environment variable that starts with FRAUD_, for example
FRAUD_BLOCK_THRESHOLD=0.95, or with the same line in a git-ignored .env file (see
.env.example). Nothing else in the code reads the environment. A wrong value stops the service
at start-up with a clear message, instead of running with it.

The one secret, the fraud team's webhook token, is better given as a FILE: Docker, Kubernetes
and most secret stores mount secrets as files under /run/secrets, which never show up in
`docker inspect`, in the process list, or in a crash report that dumps the environment.
"""
from pathlib import Path
from typing import Literal, Self
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, HttpUrl, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")   # where containers receive their secrets as files


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="FRAUD_", env_file=".env", extra="ignore", frozen=True,
        secrets_dir=SECRETS_DIR if SECRETS_DIR.is_dir() else None)

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
    alert_webhook_url: HttpUrl | None = Field(
        None, description="The fraud team's webhook. When set, every blocked payment is "
                          "announced there.")
    alert_webhook_token: SecretStr | None = Field(
        None, description="SECRET: proves to the webhook that the call comes from us. Best "
                          "given as the file /run/secrets/fraud_alert_webhook_token. It prints "
                          "as '**********'.")

    @field_validator("bank_timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError(f"unknown time zone {value!r}") from error
        return value

    @model_validator(mode="after")
    def webhook_needs_its_token(self) -> Self:
        if (self.alert_webhook_url is None) != (self.alert_webhook_token is None):
            raise ValueError("set both the alert webhook's URL and its token, or neither")
        return self

    @property
    def bank_clock(self) -> ZoneInfo:
        return ZoneInfo(self.bank_timezone)

    def secret_values(self) -> list[str]:
        """The secrets' plain values, only so the log can mask them if one ever slips in."""
        token = self.alert_webhook_token
        return [token.get_secret_value()] if token is not None else []
