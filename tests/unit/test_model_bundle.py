"""The model adapter refuses a model it cannot trust, and scores rows in order."""
import json
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import pytest
import sklearn
from sklearn.dummy import DummyClassifier

from fraud_alerts.adapters.model_bundle import INFO_FILE, MODEL_FILE, ModelBundle
from fraud_alerts.domain.payment import FEATURES

pytestmark = pytest.mark.unit


def write_info(folder: Path, **changes: Any) -> None:
    info = {"model_version": "t-1", "features": list(FEATURES), "threshold": 0.4,
            "scikit_learn_version": sklearn.__version__,
            "typical_values": dict.fromkeys(FEATURES, 0.0)} | changes
    (folder / INFO_FILE).write_text(json.dumps(info), encoding="utf-8")


def test_a_model_trained_on_other_inputs_is_refused(tmp_path: Path) -> None:
    write_info(tmp_path, features=list(reversed(FEATURES)))
    with pytest.raises(ValueError, match="other inputs"):
        ModelBundle.load(tmp_path)


def test_a_model_saved_with_another_scikit_learn_is_refused(tmp_path: Path) -> None:
    write_info(tmp_path, scikit_learn_version="0.0.1")
    with pytest.raises(ValueError, match="scikit-learn"):
        ModelBundle.load(tmp_path)


def test_a_loaded_model_scores_every_row_in_order(tmp_path: Path) -> None:
    rows = pd.DataFrame([dict.fromkeys(FEATURES, 0.0), dict.fromkeys(FEATURES, 1.0)])
    joblib.dump(DummyClassifier(strategy="prior").fit(rows, [0, 1]), tmp_path / MODEL_FILE)
    write_info(tmp_path)
    bundle = ModelBundle.load(tmp_path)
    assert bundle.scores([dict.fromkeys(FEATURES, 0.0)] * 3) == [0.5, 0.5, 0.5]
    assert (bundle.version, bundle.review_threshold) == ("t-1", 0.4)
    assert set(bundle.typical) == set(FEATURES)
