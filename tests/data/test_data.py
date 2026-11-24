"""The downloaded data is what we expect: the columns, the size, sensible values, and no future
payments mixed into training."""
from pathlib import Path

import pandas as pd
import pytest

from fraud_alerts.api.schemas import LARGEST_AMOUNT, LARGEST_V
from fraud_alerts.domain.payment import V_INPUTS, hour_of_day
from fraud_alerts.training.data import DATA_SHA256, sha256, split_by_time
from helpers import GOLDEN

pytestmark = pytest.mark.data
TWO_DAYS = 2 * 86_400


def test_the_file_is_the_one_that_reproduced_the_notebook(data_file: Path) -> None:
    assert sha256(data_file) == DATA_SHA256


def test_the_columns_are_exactly_the_expected_ones(raw_data: pd.DataFrame) -> None:
    assert list(raw_data.columns) == ["Time", *V_INPUTS, "Amount", "Class"]


def test_the_size_and_the_number_of_frauds(raw_data: pd.DataFrame) -> None:
    assert len(raw_data) == 284_807
    assert int(raw_data["Class"].sum()) == 492


def test_nothing_is_missing(raw_data: pd.DataFrame) -> None:
    assert not raw_data.isna().any().any()


def test_every_value_is_in_a_sensible_range(raw_data: pd.DataFrame) -> None:
    assert set(raw_data["Class"].unique()) == {0, 1}
    assert raw_data["Time"].between(0, TWO_DAYS).all()
    # Every real payment fits the API's limits, so the limits refuse only broken clients.
    assert raw_data["Amount"].between(0, LARGEST_AMOUNT).all()
    assert float(raw_data[list(V_INPUTS)].abs().max().max()) < LARGEST_V


def test_the_split_keeps_future_payments_out_of_training(data: pd.DataFrame) -> None:
    train, valid, test = split_by_time(data)
    assert train["Time"].max() <= valid["Time"].min()
    assert valid["Time"].max() <= test["Time"].min()
    assert (len(train), len(valid), len(test)) == (170_884, 56_961, 56_962)
    assert [int(part["Class"].sum()) for part in (train, valid, test)] == [360, 57, 75]


def test_the_hour_column_is_built_by_the_domain_rule(data: pd.DataFrame) -> None:
    sample = data.sample(2_000, random_state=0)
    assert all(hour_of_day(time) == hour
               for time, hour in zip(sample["Time"], sample["hour"], strict=True))


def test_the_rows_the_notebook_named_are_unchanged(data: pd.DataFrame) -> None:
    for saved in GOLDEN["payments"]:
        if "row" in saved:
            row = data.loc[saved["row"]]
            for column, value in saved["payment"].items():
                assert float(row[column]) == pytest.approx(value, rel=1e-12, abs=1e-12)
