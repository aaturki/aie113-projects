"""Shared test helpers: a stand-in model with known scores, request bodies, the golden file."""
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fraud_alerts.domain.payment import FEATURES, V_INPUTS

ROOT = Path(__file__).resolve().parent.parent
GOLDEN: dict[str, Any] = json.loads((ROOT / "golden" / "notebook_answers.json")
                                    .read_text(encoding="utf-8"))
RIYADH = ZoneInfo("Asia/Riyadh")
SECONDS_PER_DAY = 86_400

TYPICAL = dict.fromkeys(FEATURES, 0.0) | {"Amount": 20.0, "hour": 13.0, "V14": 0.09,
                                          "V10": -0.11}


def suspicious(row: Mapping[str, float]) -> float:
    """The stand-in's rule: a very low V14 is suspicious (review), a very low V10 adds to it
    (block when both). Everything else is quiet."""
    score = 0.02
    if row["V14"] < -3:
        score += 0.6
    if row["V10"] < -3:
        score += 0.3
    return score


class FakeModel:
    """A stand-in for the real model: known scores from a simple rule, so a test checks our
    code, not scikit-learn. It also records how many rows each call scored."""

    def __init__(self, rule: Callable[[Mapping[str, float]], float] = suspicious,
                 review_threshold: float = 0.4, version: str = "fake-1") -> None:
        self.rule = rule
        self._review_threshold = review_threshold
        self._version = version
        self.calls: list[int] = []

    @property
    def version(self) -> str:
        return self._version

    @property
    def review_threshold(self) -> float:
        return self._review_threshold

    @property
    def typical(self) -> Mapping[str, float]:
        return TYPICAL

    def scores(self, rows: Sequence[Mapping[str, float]]) -> list[float]:
        self.calls.append(len(rows))
        return [self.rule(row) for row in rows]


class FakeNotifier:
    """A stand-in fraud team: remembers every announcement it gets."""

    def __init__(self, reached: bool = True) -> None:
        self.reached = reached
        self.calls: list[dict[str, Any]] = []

    def payment_blocked(self, trace_id: str, score: float, reasons: Sequence[str],
                        model_version: str) -> bool:
        self.calls.append({"trace_id": trace_id, "score": score, "reasons": list(reasons),
                           "model_version": model_version})
        return self.reached


def request_body(**changes: Any) -> dict[str, Any]:
    """A valid request for a quiet payment, changed by keyword: request_body(V14=-6.0)."""
    body: dict[str, Any] = {"timestamp": "2026-11-24T18:51:18+03:00", "Amount": 25.0,
                            **dict.fromkeys(V_INPUTS, 0.0)}
    return body | changes


def dataset_request(raw: Mapping[str, float], day: date = date(2026, 11, 24)) -> dict[str, Any]:
    """A row of the dataset as an API request. Its Time becomes a moment on the bank's clock;
    any day works, because the model only uses the hour."""
    moment = (datetime.combine(day, time(0), tzinfo=RIYADH)
              + timedelta(seconds=raw["Time"] % SECONDS_PER_DAY))
    return {"timestamp": moment.isoformat(), "Amount": raw["Amount"],
            **{name: raw[name] for name in V_INPUTS}}
