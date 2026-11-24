"""Get the data and shape it exactly as the notebook does. The data is downloaded, never
stored in git."""
import hashlib
import urllib.request
from pathlib import Path

import pandas as pd

from fraud_alerts.domain.payment import HOURS_PER_DAY, SECONDS_PER_HOUR

# ULB credit-card fraud data: the original CSV, in the public copy kept for TensorFlow's
# tutorials (the same data is on OpenML, dataset 1597, if this address ever fails).
DATA_URL = "https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv"
DEFAULT_PATH = Path("data/creditcard.csv")
TRAIN_SHARE = 0.6        # the first 60% of the time line: training
VALID_SHARE = 0.2        # the next 20%: choosing the threshold; the last 20% is the test


def download(path: Path = DEFAULT_PATH, url: str = DATA_URL) -> Path:
    """Download once; a half-finished download never looks like the real file."""
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        part = path.with_suffix(path.suffix + ".part")
        urllib.request.urlretrieve(url, part)
        part.replace(path)
    return path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> pd.DataFrame:
    """Sorted by time, with the hour column built by the same rule as the domain's."""
    df = pd.read_csv(path)
    df["Class"] = df["Class"].astype(int)
    df = df.sort_values("Time", kind="stable").reset_index(drop=True)
    df["hour"] = (df["Time"] // SECONDS_PER_HOUR) % HOURS_PER_DAY
    return df


def split_by_time(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Learn from the past, choose on the near future, judge on the far future."""
    n = len(df)
    train_end = int(n * TRAIN_SHARE)
    valid_end = int(n * (TRAIN_SHARE + VALID_SHARE))
    return df.iloc[:train_end], df.iloc[train_end:valid_end], df.iloc[valid_end:]
