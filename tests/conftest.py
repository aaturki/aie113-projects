"""Fixtures for the tests that need the real model or the real data.

Neither is stored in git: the pipeline trains the model into artifacts/ and downloads the data
into data/. On a laptop without them, these tests are skipped and the reason is shown. In the
pipeline (where CI=true) a missing model or data file is a failure, never a skip, so these
checks cannot be switched off there without anyone noticing.
"""
import os
from collections.abc import Iterator
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from fraud_alerts.adapters.model_bundle import MODEL_FILE, ModelBundle
from fraud_alerts.api.app import create_app
from fraud_alerts.config import Settings
from fraud_alerts.training.data import load
from helpers import ROOT

MODEL_DIR = Path(os.environ.get("FRAUD_MODEL_DIR", ROOT / "artifacts"))
DATA_FILE = ROOT / "data" / "creditcard.csv"


def need(path: Path, how: str) -> None:
    if path.exists():
        return
    message = f"{path} is missing: {how}"
    if os.environ.get("CI"):
        pytest.fail(message)
    pytest.skip(message)


@pytest.fixture(scope="session")
def bundle() -> ModelBundle:
    need(MODEL_DIR / MODEL_FILE, "train it with: python -m fraud_alerts.training.train")
    return ModelBundle.load(MODEL_DIR)


@pytest.fixture(scope="session")
def data_file() -> Path:
    need(DATA_FILE, "python -m fraud_alerts.training.train downloads it (150 MB)")
    return DATA_FILE


@pytest.fixture(scope="session")
def raw_data(data_file: Path) -> pd.DataFrame:
    """The file exactly as downloaded."""
    return pd.read_csv(data_file)


@pytest.fixture(scope="session")
def data(data_file: Path) -> pd.DataFrame:
    """The file as training sees it: sorted by time, with the hour column."""
    return load(data_file)


@pytest.fixture(scope="module")
def api(bundle: ModelBundle) -> Iterator[TestClient]:
    """The real service with the real model, as a client sees it."""
    settings = Settings(_env_file=None, block_threshold=0.9, bank_timezone="Asia/Riyadh")
    with TestClient(create_app(settings, model=bundle)) as client:
        yield client
