"""Command-line interface for the GB V2 platform."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from .features import add_cyclical_time_features, add_system_balance_features, add_weather_features
from .pipeline import forecast_platform, train_platform
from .synthetic import make_synthetic_history


def _load_frame(path: str) -> pd.DataFrame:
    source = Path(path)
    if source.suffix == ".parquet":
        frame = pd.read_parquet(source)
    else:
        frame = pd.read_csv(source)
    if "timestamp" not in frame:
        raise KeyError("Input must contain a timestamp column")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True)
    return frame.set_index("timestamp", drop=False).sort_index()


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    out = add_cyclical_time_features(frame)
    out = add_weather_features(out)
    balance_columns = {
        "demand_mw",
        "embedded_wind_mw",
        "embedded_solar_mw",
        "transmission_wind_mw",
        "nuclear_mw",
        "net_import_mw",
        "battery_net_mw",
    }
    if balance_columns.issubset(out.columns):
        out = add_system_balance_features(out)
    return out


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GB Power Market Platform V2")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Train models on a prepared historical table")
    train.add_argument("--input", required=True)
    train.add_argument("--models", required=True)
    train.add_argument("--holdout-rows", type=int, default=4320)

    forecast = sub.add_parser("forecast", help="Forecast from a prepared future feature table")
    forecast.add_argument("--input", required=True)
    forecast.add_argument("--models", required=True)
    forecast.add_argument("--output", required=True)
    forecast.add_argument("--scenarios", type=int, default=1000)

    demo = sub.add_parser("demo", help="Run a complete synthetic demonstration")
    demo.add_argument("--days", type=int, default=220)
    demo.add_argument("--scenarios", type=int, default=1000)
    demo.add_argument("--models", default="models/demo")
    demo.add_argument("--output", default="outputs/demo")

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "train":
        frame = _prepare(_load_frame(args.input))
        metrics = train_platform(frame, args.models, args.holdout_rows)
        print(metrics)
    elif args.command == "forecast":
        frame = _prepare(_load_frame(args.input))
        report = forecast_platform(frame, args.models, args.output, args.scenarios)
        print(report)
    else:
        history = make_synthetic_history(args.days)
        holdout = min(48 * 30, max(96, len(history) // 5))
        train_platform(history, args.models, holdout)
        future = history.iloc[-48:].copy()
        for column in [
            "demand_mw",
            "embedded_wind_mw",
            "embedded_solar_mw",
            "transmission_wind_mw",
            "nuclear_mw",
            "net_import_mw",
            "battery_net_mw",
            "inertia_gvas",
            "price_gbp_mwh",
            "marginal_technology",
        ]:
            future = future.drop(columns=[column], errors="ignore")
        report = forecast_platform(future, args.models, args.output, args.scenarios)
        print(report)


if __name__ == "__main__":
    main()
