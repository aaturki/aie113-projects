"""What the service needs from a model, and nothing more. Any object with these members works:
the real model bundle, or a stand-in in the tests."""
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
