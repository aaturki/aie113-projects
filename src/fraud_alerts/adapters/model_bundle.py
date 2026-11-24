"""The trained model and its facts, loaded from one folder. The only serving module that
imports joblib, pandas or scikit-learn."""
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib
import pandas as pd
import sklearn

from fraud_alerts.domain.payment import FEATURES

MODEL_FILE = "fraud_model.joblib"
INFO_FILE = "model_info.json"


@dataclass(frozen=True)
class ModelBundle:
    estimator: Any
    info: Mapping[str, Any]

    @classmethod
    def load(cls, folder: Path) -> "ModelBundle":
        """Fail at start-up, with a clear message, rather than score with the wrong model."""
        info = json.loads((folder / INFO_FILE).read_text(encoding="utf-8"))
        if tuple(info["features"]) != FEATURES:
            raise ValueError("the model was trained on other inputs than this service sends")
        if info["scikit_learn_version"] != sklearn.__version__:
            raise ValueError(f"the model was saved with scikit-learn "
                             f"{info['scikit_learn_version']}, this service runs "
                             f"{sklearn.__version__}")
        return cls(estimator=joblib.load(folder / MODEL_FILE), info=info)

    @property
    def version(self) -> str:
        return str(self.info["model_version"])

    @property
    def review_threshold(self) -> float:
        return float(self.info["threshold"])

    @property
    def typical(self) -> Mapping[str, float]:
        return {name: float(value) for name, value in self.info["typical_values"].items()}

    def scores(self, rows: Sequence[Mapping[str, float]]) -> list[float]:
        frame = pd.DataFrame(list(rows), columns=list(FEATURES))
        return [float(p) for p in self.estimator.predict_proba(frame)[:, 1]]
