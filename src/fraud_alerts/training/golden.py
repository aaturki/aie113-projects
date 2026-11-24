"""Keep the notebook's answers.

Before any code was moved, the answers printed in the notebook's saved outputs were copied into
golden/notebook_answers.json: the threshold table on the validation payments, the chosen
threshold, the test numbers, and the score and top reasons of three payments (the payment in the
last cell, the first real fraud caught in the test period, and the first false alarm). Every
training run recomputes all of them with this project's code, the payments through the service's
own path, and must give the same answers to the notebook's rounding.
"""
import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import pandas as pd

from fraud_alerts.adapters.model_bundle import ModelBundle
from fraud_alerts.domain.payment import V_INPUTS, Payment
from fraud_alerts.service.alerts import AlertService

GOLDEN_PATH = Path("golden/notebook_answers.json")
SCORE_TOLERANCE = 0.0005 + 1e-9  # scores are printed with 3 decimals: at most half the last digit
VALUE_TOLERANCE = 0.005 + 1e-9   # input values are printed with 2 decimals
RAW_INPUTS = ("Time", *V_INPUTS, "Amount")
NO_BLOCK = 1.0                   # the notebook has no block threshold: every alert gets reasons

Check = dict[str, Any]


def check(what: str, ours: Any, notebook: Any, same: bool) -> Check:
    return {"what": what, "ours": ours, "notebook": notebook, "same": bool(same)}


def close(ours: float, notebook: float, tolerance: float) -> bool:
    return abs(ours - notebook) <= tolerance


def as_payment(raw: Mapping[str, float]) -> Payment:
    return Payment(time=raw["Time"], amount=raw["Amount"],
                   v=tuple(raw[name] for name in V_INPUTS))


def table_checks(table: Sequence[Mapping[str, float]], threshold: float,
                 golden: Mapping[str, Any]) -> list[Check]:
    checks = []
    for ours, saved in zip(table, golden["validation_thresholds"], strict=True):
        mine = (ours["threshold"], int(ours["alerts"]), int(ours["caught"]))
        theirs = (saved["threshold"], saved["alerts"], saved["caught"])
        checks.append(check(f"validation at {saved['threshold']}: alerts, frauds among them",
                            list(mine[1:]), list(theirs[1:]), mine == theirs))
    checks.append(check("chosen threshold", threshold, golden["chosen_threshold"],
                        threshold == golden["chosen_threshold"]))
    return checks


def test_checks(metrics: Mapping[str, Any], golden: Mapping[str, Any]) -> list[Check]:
    saved = golden["test"]
    checks = [check(f"test: {name}", metrics[name], saved[name], metrics[name] == saved[name])
              for name in ("alerts", "frauds_caught", "false_alarms", "missed_frauds")]
    ap = metrics["average_precision"]
    checks.append(check("test: average precision", round(ap, 4), saved["average_precision"],
                        close(ap, saved["average_precision"], SCORE_TOLERANCE)))
    return checks


def payment_checks(service: AlertService, saved: Mapping[str, Any],
                   raw: Mapping[str, float]) -> list[Check]:
    name = saved["name"]
    result = service.assess(as_payment(raw))
    checks = [check(f"{name}: score", round(result.score, 4), saved["score"],
                    close(result.score, saved["score"], SCORE_TOLERANCE))]
    ours = [reason.input for reason in result.reasons]
    theirs = [reason["input"] for reason in saved["top_reasons"]]
    checks.append(check(f"{name}: top reasons, strongest first", ours, theirs, ours == theirs))
    for reason, kept in zip(result.reasons, saved["top_reasons"], strict=False):
        checks.append(check(f"{name}: score if {kept['input']} were typical",
                            round(reason.score_if_typical, 4), kept["score_if_typical"],
                            close(reason.score_if_typical, kept["score_if_typical"],
                                  SCORE_TOLERANCE)))
        for part in ("value", "typical"):
            checks.append(check(f"{name}: {kept['input']} {part}",
                                round(getattr(reason, part), 4), kept[part],
                                close(getattr(reason, part), kept[part], VALUE_TOLERANCE)))
    return checks


def row_checks(df: pd.DataFrame, saved: Mapping[str, Any]) -> tuple[list[Check], dict[str, float]]:
    """A payment the notebook named by its row: check it is the same payment in our data."""
    name, row = saved["name"], saved["row"]
    if row not in df.index:
        return [check(f"{name}: row {row} is in the data", False, True, False)], {}
    found = df.loc[row]
    raw = {column: float(found[column]) for column in RAW_INPUTS}
    checks = [check(f"{name}: amount", raw["Amount"], saved["amount"],
                    close(raw["Amount"], saved["amount"], VALUE_TOLERANCE)),
              check(f"{name}: is fraud", bool(found["Class"] == 1), saved["is_fraud"],
                    bool(found["Class"] == 1) == saved["is_fraud"])]
    if "hour" in saved:
        hour = as_payment(raw).features()["hour"]
        checks.append(check(f"{name}: hour", hour, saved["hour"], hour == saved["hour"]))
    if "payment" in saved:
        stored = saved["payment"]
        same = all(math.isclose(raw[column], stored[column], rel_tol=1e-12, abs_tol=1e-12)
                   for column in RAW_INPUTS)
        checks.append(check(f"{name}: all 30 inputs equal the golden file's copy", same, True,
                            same))
    return checks, raw


def serving_checks(bundle: ModelBundle, test: pd.DataFrame, training_scores: Sequence[float],
                   threshold: float, golden: Mapping[str, Any]) -> list[Check]:
    """Every test payment again, but the way the service sees it: a Payment, its features()
    and the bundle. Any difference here is training/serving skew."""
    payments = [as_payment(raw) for raw in test[list(RAW_INPUTS)].to_dict("records")]
    serving = bundle.scores([payment.features() for payment in payments])
    largest = max(abs(a - b) for a, b in zip(serving, training_scores, strict=True))
    alerts = sum(score >= threshold for score in serving)
    return [check("all test payments: largest score difference, service path vs training",
                  largest, 0.0, largest <= 1e-12),
            check("all test payments: alerts through the service path", alerts,
                  golden["test"]["alerts"], alerts == golden["test"]["alerts"])]


def compare(folder: Path, df: pd.DataFrame, test: pd.DataFrame, training_scores: Sequence[float],
            table: Sequence[Mapping[str, float]], threshold: float,
            metrics: Mapping[str, Any], path: Path = GOLDEN_PATH) -> dict[str, Any]:
    golden = json.loads(path.read_text(encoding="utf-8"))
    bundle = ModelBundle.load(folder)
    service = AlertService(model=bundle, block_threshold=NO_BLOCK)
    checks = table_checks(table, threshold, golden) + test_checks(metrics, golden)
    from_data: dict[str, dict[str, float]] = {}
    for saved in golden["payments"]:
        raw: Mapping[str, float] = saved.get("payment", {})
        if "row" in saved:
            found, raw = row_checks(df, saved)
            checks += found
            from_data[saved["name"]] = raw
        if raw:
            checks += payment_checks(service, saved, raw)
    checks += serving_checks(bundle, test, training_scores, threshold, golden)
    return {"checks": checks, "payments_from_data": from_data,
            "matches": all(item["same"] for item in checks)}


def report(result: Mapping[str, Any]) -> None:
    for item in result["checks"]:
        mark = "same" if item["same"] else "DIFFERENT"
        print(f"  {mark:9s} {item['what']}: ours {item['ours']}, notebook {item['notebook']}")
    same = sum(item["same"] for item in result["checks"])
    print(f"matches the notebook: {result['matches']} ({same} of {len(result['checks'])} "
          "answers the same)")
    if result["payments_from_data"]:
        print("payments the notebook named by row, as found in the data:")
        print(json.dumps(result["payments_from_data"]))
