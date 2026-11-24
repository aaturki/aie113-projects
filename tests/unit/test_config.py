"""The settings: defaults, environment variables, and wrong values stopping the start."""
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from fraud_alerts.config import Settings

pytestmark = pytest.mark.unit
NAMES = ("FRAUD_MODEL_DIR", "FRAUD_BLOCK_THRESHOLD", "FRAUD_BANK_TIMEZONE", "FRAUD_LOG_LEVEL",
         "FRAUD_ALERT_WEBHOOK_URL", "FRAUD_ALERT_WEBHOOK_TOKEN")
URL = "https://fraud-team.example/alerts"


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def settings(**kwargs: Any) -> Settings:
    """Settings from the environment only: a developer's own .env file must not change tests."""
    return Settings(_env_file=None, **kwargs)


def test_the_defaults() -> None:
    defaults = settings()
    assert defaults.model_dir == Path("artifacts")
    assert defaults.block_threshold == 0.9
    assert defaults.bank_timezone == "Asia/Riyadh"
    assert defaults.log_level == "INFO"
    assert (defaults.alert_webhook_url, defaults.alert_webhook_token) == (None, None)


def test_an_environment_variable_changes_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRAUD_BLOCK_THRESHOLD", "0.95")
    assert settings().block_threshold == 0.95


def test_the_token_is_a_secret_that_never_prints(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRAUD_ALERT_WEBHOOK_URL", URL)
    made_up = "practice-token-123"  # gitleaks:allow (made up for this test)
    monkeypatch.setenv("FRAUD_ALERT_WEBHOOK_TOKEN", made_up)
    loaded = settings()
    assert loaded.alert_webhook_token is not None
    assert loaded.alert_webhook_token.get_secret_value() == "practice-token-123"
    assert "practice-token-123" not in repr(loaded)
    assert "practice-token-123" not in str(loaded)


def test_the_token_can_come_from_a_secret_file(tmp_path: Path,
                                               monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "fraud_alert_webhook_token").write_text("from-a-file\n", encoding="utf-8")
    monkeypatch.setenv("FRAUD_ALERT_WEBHOOK_URL", URL)
    loaded = settings(_secrets_dir=tmp_path)
    assert loaded.alert_webhook_token is not None
    assert loaded.alert_webhook_token.get_secret_value() == "from-a-file"


@pytest.mark.parametrize(("name", "value"), [("FRAUD_ALERT_WEBHOOK_URL", URL),
                                             ("FRAUD_ALERT_WEBHOOK_TOKEN", "t")])
def test_the_webhook_needs_both_its_address_and_its_token(
        monkeypatch: pytest.MonkeyPatch, name: str, value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError, match="both"):
        settings()


@pytest.mark.parametrize(("name", "value"), [
    ("FRAUD_BLOCK_THRESHOLD", "1.5"), ("FRAUD_BLOCK_THRESHOLD", "high"),
    ("FRAUD_BANK_TIMEZONE", "Mars/Olympus_Mons"), ("FRAUD_LOG_LEVEL", "LOUD")])
def test_a_wrong_setting_stops_the_start(monkeypatch: pytest.MonkeyPatch, name: str,
                                         value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        settings()
