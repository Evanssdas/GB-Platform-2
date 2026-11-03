"""Check if a complete V2 shadow forecast exists for the next GB delivery day."""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd

LONDON = ZoneInfo("Europe/London")

def expected_periods(day) -> int:
    start = pd.Timestamp(day).tz_localize(LONDON)
    end = (pd.Timestamp(day) + pd.Timedelta(days=1)).tz_localize(LONDON)
    return int((end - start) / pd.Timedelta(minutes=30))

def check(path: Path, version: str, delivery) -> tuple[bool, str]:
    if not path.exists() or path.stat().st_size == 0:
        return False, f"Forecast file missing: {path}"
    df = pd.read_csv(path)
    needed = {"model_version", "delivery_time_utc"}
    if not needed.issubset(df.columns):
        return False, f"Forecast file lacks {sorted(needed - set(df.columns))}"
    df = df.loc[df["model_version"].astype(str) == version]
    ts = pd.to_datetime(df["delivery_time_utc"], utc=True, errors="coerce")
    subset = ts.loc[ts.dt.tz_convert(LONDON).dt.date == delivery]
    count = int(subset.nunique())
    expected = expected_periods(delivery)
    return count >= expected, f"{count}/{expected} unique settlement periods for {delivery}"

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--forecasts", default="live/v2/forecasts.csv")
    parser.add_argument("--model-version", default="core-regime-operational-v2")
    parser.add_argument("--enforce-window", action="store_true")
    args = parser.parse_args()
    local_now = datetime.now(timezone.utc).astimezone(LONDON)
    if args.enforce_window and not (
        (local_now.hour == 13 and local_now.minute >= 15) or
        (local_now.hour == 14 and local_now.minute < 15)
    ):
        print(f"Outside 13:15–14:15 GB local watch window: {local_now:%H:%M}")
        return 2
    day = (local_now + timedelta(days=1)).date()
    ok, message = check(Path(args.forecasts), args.model_version, day)
    print(message)
    return 0 if ok else 1

if __name__ == "__main__":
    sys.exit(main())
