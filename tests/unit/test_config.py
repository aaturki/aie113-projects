"""The settings: defaults, environment variables, and wrong values stopping the start."""
from pathlib import Path

import pytest
from pydantic import ValidationError

from fraud_alerts.config import Settings

pytestmark = pytest.mark.unit
NAMES = ("FRAUD_MODEL_DIR", "FRAUD_BLOCK_THRESHOLD", "FRAUD_BANK_TIMEZONE", "FRAUD_LOG_LEVEL")


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)


def test_the_defaults() -> None:
    settings = Settings()
    assert settings.model_dir == Path("artifacts")
    assert settings.block_threshold == 0.9
    assert settings.bank_timezone == "Asia/Riyadh"
    assert settings.log_level == "INFO"


def test_an_environment_variable_changes_a_setting(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FRAUD_BLOCK_THRESHOLD", "0.95")
    assert Settings().block_threshold == 0.95


@pytest.mark.parametrize(("name", "value"), [
    ("FRAUD_BLOCK_THRESHOLD", "1.5"), ("FRAUD_BLOCK_THRESHOLD", "high"),
    ("FRAUD_BANK_TIMEZONE", "Mars/Olympus_Mons"), ("FRAUD_LOG_LEVEL", "LOUD")])
def test_a_wrong_setting_stops_the_start(monkeypatch: pytest.MonkeyPatch, name: str,
                                         value: str) -> None:
    monkeypatch.setenv(name, value)
    with pytest.raises(ValidationError):
        Settings()
