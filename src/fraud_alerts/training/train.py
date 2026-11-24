"""Train the model exactly as the notebook does, check it, and save it with its facts.

    python -m fraud_alerts.training.train --data data/creditcard.csv --out artifacts

The data is downloaded once if it is missing. The model is saved only if it passes the agreed
quality gates on the test payments. Then the saved model is checked, through the same code the
service uses, against the answers saved in the notebook for its last payment.
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

from fraud_alerts.adapters.model_bundle import INFO_FILE, MODEL_FILE, ModelBundle
from fraud_alerts.domain.payment import FEATURES, V_INPUTS, Payment
from fraud_alerts.service.alerts import AlertService
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
GOLDEN_PATH = Path("golden/notebook_last_cell.json")
NOTEBOOK_TOLERANCE = 0.01  # the notebook rounds to 3 decimals; another library version moves a bit


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


def golden_payment() -> tuple[Payment, dict[str, Any]]:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    raw = golden["payment"]
    payment = Payment(time=raw["Time"], amount=raw["Amount"],
                      v=tuple(raw[name] for name in V_INPUTS))
    return payment, golden["notebook_outputs"]


def check_against_notebook(folder: Path) -> dict[str, Any]:
    """Score the notebook's last payment through the service's own code (bundle, service,
    reasons) and compare with the answers saved in the notebook."""
    payment, notebook = golden_payment()
    service = AlertService(model=ModelBundle.load(folder), block_threshold=1.0)
    result = service.assess(payment)
    top: list[dict[str, Any]] = [{"input": r.input, "score_if_typical": r.score_if_typical}
                                 for r in result.reasons]
    ours: dict[str, Any] = {"score": result.score, "top_reasons": top}
    same_reasons = [r["input"] for r in top] == [r["input"] for r in notebook["top_reasons"]]
    deltas = [abs(result.score - notebook["score"])] + [
        abs(a["score_if_typical"] - b["score_if_typical"])
        for a, b in zip(top, notebook["top_reasons"], strict=False)]
    return {"ours": ours, "notebook": notebook, "same_top_reasons_in_order": same_reasons,
            "largest_difference": max(deltas),
            "matches": same_reasons and max(deltas) <= NOTEBOOK_TOLERANCE}


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

    check = check_against_notebook(args.out)
    (args.out / "notebook_check.json").write_text(json.dumps(check, indent=2), encoding="utf-8")
    print("notebook's last payment, ours vs notebook:")
    print(f"  score {check['ours']['score']:.4f} vs {check['notebook']['score']}")
    for ours, theirs in zip(check["ours"]["top_reasons"], check["notebook"]["top_reasons"],
                            strict=False):
        print(f"  {ours['input']} -> {ours['score_if_typical']:.4f} vs "
              f"{theirs['input']} -> {theirs['score_if_typical']}")
    print(f"matches the notebook: {check['matches']} "
          f"(largest difference {check['largest_difference']:.4f})")
    return 0 if check["matches"] else 2


if __name__ == "__main__":
    np.seterr(all="ignore")
    sys.exit(main())
