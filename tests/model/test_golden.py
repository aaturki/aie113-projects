"""The golden check through the front door: the notebook's three payments, sent to the API the
way a client would, must get the notebook's answers."""
from typing import Any

import pytest
from fastapi.testclient import TestClient

from helpers import GOLDEN, dataset_request

pytestmark = pytest.mark.model
SCORE = 0.0005 + 1e-9    # the notebook prints scores with 3 decimals
VALUE = 0.005 + 1e-9     # and input values with 2


@pytest.mark.parametrize("saved", GOLDEN["payments"], ids=lambda saved: saved["name"])
def test_the_api_gives_the_notebooks_answer(api: TestClient, saved: dict[str, Any]) -> None:
    answer = api.post("/v1/assess", json=dataset_request(saved["payment"])).json()
    assert answer["score"] == pytest.approx(saved["score"], abs=SCORE)
    assert ([reason["input"] for reason in answer["reasons"]]
            == [reason["input"] for reason in saved["top_reasons"]])
    for ours, kept in zip(answer["reasons"], saved["top_reasons"], strict=True):
        assert ours["score_if_typical"] == pytest.approx(kept["score_if_typical"], abs=SCORE)
        assert ours["value"] == pytest.approx(kept["value"], abs=VALUE)
        assert ours["typical"] == pytest.approx(kept["typical"], abs=VALUE)
