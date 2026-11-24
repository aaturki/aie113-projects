"""Train the model exactly as the notebook does, check it, and save it with its facts.

    python -m fraud_alerts.training.train --data data/creditcard.csv --out artifacts

The data is downloaded once if it is missing. The model is saved only if it passes the agreed
quality gates on the test payments. Then every answer saved in the notebook is recomputed with
this project's code (see golden.py) and must be the same.
"""
import argparse
import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import average_precision_score

from fraud_alerts.adapters.model_bundle import INFO_FILE, MODEL_FILE
from fraud_alerts.domain.payment import FEATURES
from fraud_alerts.training import golden
from fraud_alerts.training.data import (
    DATA_URL,
    DEFAULT_PATH,
    download,
    load,
    sha256,
    split_by_time,
)

MODEL_VERSION = "1.0.0"
RANDOM_SEED = 42
MIN_PRECISION = 0.80      # the fraud team's rule: at least 8 of every 10 alerts are real fraud
THRESHOLDS_TO_TRY = (0.01, 0.02, 0.05, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95, 0.99)
AMOUNT_RULE = 1000        # baseline: alert on every payment above this amount
GATE_RECALL = 0.70        # agreed: the model must catch at least 70% of the test frauds
GATE_PRECISION = 0.80     # agreed: at least 80% of its test alerts must be real fraud


def fit(train: pd.DataFrame) -> HistGradientBoostingClassifier:
    """The notebook's model, with the notebook's settings."""
    model = HistGradientBoostingClassifier(learning_rate=0.05, max_iter=300, max_leaf_nodes=15,
                                           l2_regularization=1.0, early_stopping=False,
                                           random_state=RANDOM_SEED)
    return model.fit(train[list(FEATURES)], train["Class"])


def choose_threshold(scores: Any, frauds: Any) -> tuple[float, list[dict[str, float]]]:
    """The lowest tried threshold whose validation alerts meet the fraud team's rule."""
    table = []
    for threshold in THRESHOLDS_TO_TRY:
        alert = scores >= threshold
        caught = int((alert & frauds).sum())
        alerts = int(alert.sum())
        table.append({"threshold": threshold, "alerts": alerts, "caught": caught,
                      "precision": caught / alerts if alerts else float("nan"),
                      "recall": caught / int(frauds.sum())})
    meeting = [row["threshold"] for row in table if row["precision"] >= MIN_PRECISION]
    if not meeting:
        raise SystemExit("no threshold meets the fraud team's rule on the validation payments")
    return min(meeting), table


def share(part: int, whole: int) -> float | None:
    """A share, or None when there is nothing to share: no alerts means no precision."""
    return part / whole if whole else None


def evaluate(scores: Any, test: pd.DataFrame, threshold: float) -> dict[str, float | None]:
    frauds = test["Class"].to_numpy() == 1
    alert = scores >= threshold
    caught = int((alert & frauds).sum())
    return {"alerts": int(alert.sum()), "frauds_caught": caught,
            "precision": share(caught, int(alert.sum())),
            "recall": share(caught, int(frauds.sum())),
            "false_alarms": int((alert & ~frauds).sum()),
            "missed_frauds": int((~alert & frauds).sum()),
            "average_precision": float(average_precision_score(frauds, scores)),
            "accuracy": float((alert == frauds).mean())}


def baselines(test: pd.DataFrame) -> dict[str, float | None]:
    frauds = test["Class"].to_numpy() == 1
    rule = test["Amount"].to_numpy() > AMOUNT_RULE
    caught = int((rule & frauds).sum())
    return {"always_not_fraud_accuracy": float((~frauds).mean()),
            "amount_rule_recall": share(caught, int(frauds.sum())),
            "amount_rule_precision": share(caught, int(rule.sum()))}


def passes_gates(metrics: dict[str, float | None]) -> bool:
    recall, precision = metrics["recall"], metrics["precision"]
    return (recall is not None and precision is not None
            and recall >= GATE_RECALL and precision >= GATE_PRECISION)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Train the fraud model as the notebook does.")
    parser.add_argument("--data", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--out", type=Path, default=Path("artifacts"))
    args = parser.parse_args(argv)

    data_path = download(args.data)
    df = load(data_path)
    train, valid, test = split_by_time(df)
    for name, part in (("train", train), ("valid", valid), ("test", test)):
        print(f"{name:5s}: {len(part):7,} payments, {int(part['Class'].sum()):3d} frauds, "
              f"hours {part['Time'].min() / 3600:4.1f} to {part['Time'].max() / 3600:4.1f}")

    start = time.time()
    model = fit(train)
    print(f"trained in {time.time() - start:.1f} s")
    valid_scores = model.predict_proba(valid[list(FEATURES)])[:, 1]
    threshold, table = choose_threshold(valid_scores, valid["Class"].to_numpy() == 1)
    for row in table:
        print(f"  threshold {row['threshold']:4}: {row['alerts']:3.0f} alerts, "
              f"{row['caught']:2.0f} frauds, precision {row['precision']:.0%}, "
              f"recall {row['recall']:.0%}")
    print(f"chosen threshold: {threshold}")

    test_scores = model.predict_proba(test[list(FEATURES)])[:, 1]
    metrics = evaluate(test_scores, test, threshold)
    print("test:", json.dumps({k: v if v is None else round(v, 4) for k, v in metrics.items()}))
    if not passes_gates(metrics):
        print(f"FAILED the quality gates (recall >= {GATE_RECALL}, precision >= "
              f"{GATE_PRECISION}): the model is not saved")
        return 1

    typical = train.loc[train["Class"] == 0, list(FEATURES)].median()
    # Every fact is computed before anything is written: a failure leaves no half-saved model.
    info = {
        "model_version": MODEL_VERSION,
        "model_type": "HistGradientBoostingClassifier",
        "trained_on": datetime.now(UTC).strftime("%Y-%m-%d"),
        "scikit_learn_version": sklearn.__version__,
        "features": list(FEATURES),
        "threshold": threshold,
        "threshold_rule": f"lowest tried threshold where at least {MIN_PRECISION:.0%} of "
                          "validation alerts are real fraud",
        "typical_values": {name: float(value) for name, value in typical.items()},
        "data": {"source": DATA_URL, "sha256": sha256(data_path), "rows": len(df),
                 "frauds": int(df["Class"].sum()), "train_rows": len(train),
                 "train_frauds": int(train["Class"].sum()),
                 "train_hours": [float(train["Time"].min() / 3600),
                                 float(train["Time"].max() / 3600)],
                 "valid_rows": len(valid), "test_rows": len(test),
                 "test_frauds": int(test["Class"].sum())},
        "test_metrics": metrics,
        "gates": {"recall": GATE_RECALL, "precision": GATE_PRECISION},
        "baselines_on_test": baselines(test),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, args.out / MODEL_FILE)
    (args.out / INFO_FILE).write_text(json.dumps(info, indent=2), encoding="utf-8")
    print(f"saved {args.out / MODEL_FILE} and {args.out / INFO_FILE}")

    print("the notebook's saved answers, recomputed with this project's code:")
    check = golden.compare(args.out, df, test, [float(s) for s in test_scores], table,
                           threshold, metrics)
    (args.out / "notebook_check.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    golden.report(check)
    return 0 if check["matches"] else 2


if __name__ == "__main__":
    np.seterr(all="ignore")
    sys.exit(main())
