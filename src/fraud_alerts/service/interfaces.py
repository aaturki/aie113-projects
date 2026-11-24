"""What the service needs from the outside world, and nothing more. Any object with these members
works: the real adapters, or stand-ins in the tests."""
from collections.abc import Mapping, Sequence
from typing import Protocol


class FraudModel(Protocol):
    @property
    def version(self) -> str: ...

    @property
    def review_threshold(self) -> float: ...

    @property
    def typical(self) -> Mapping[str, float]: ...

    def scores(self, rows: Sequence[Mapping[str, float]]) -> list[float]:
        """One fraud score between 0 and 1 for each row of inputs, in the same order."""
        ...


class BlockNotifier(Protocol):
    def payment_blocked(self, trace_id: str, score: float, reasons: Sequence[str],
                        model_version: str) -> bool:
        """Tell the fraud team a payment was blocked. Only what they need to find it and
        judge it; never the payment's values. True if they got the message."""
        ...
