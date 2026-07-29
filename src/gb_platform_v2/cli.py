"""Command-line interface for the GB V2 platform."""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd
import yaml

from .collection import (
    collect_elexon_core,
    collect_neso_resource,
    collect_previous_run_weather,
)
from .dataset_builder import build_half_hourly_dataset
from .features import add_cyclical_time_features, add_system_balance_features, add_weather_features
from .live import collect_and_append_price_actuals, run_and_log_forecast
from .live_store import grade_forecasts
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


def _config(path: str) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="GB Power Market Platform V2")
    sub = parser.add_subparsers(dest="command", required=True)

    train = sub.add_parser("train", help="Train models on a prepared historical table")
    train.add_argument("--input", required=True)
    train.add_argument("--models", required=True)
    train.add_argument("--holdout-rows", type=int, default=4320)
    train.add_argument("--time-series-splits", type=int, default=5)

    forecast = sub.add_parser("forecast", help="Forecast from a prepared future feature table")
    forecast.add_argument("--input", required=True)
    forecast.add_argument("--models", required=True)
    forecast.add_argument("--output", required=True)
    forecast.add_argument("--scenarios", type=int, default=1000)

    live_forecast = sub.add_parser(
        "live-forecast",
        help="Run a frozen model and append immutable probabilistic forecasts",
    )
    live_forecast.add_argument("--input", required=True)
    live_forecast.add_argument("--models", required=True)
    live_forecast.add_argument("--output", required=True)
    live_forecast.add_argument("--forecasts", default="live/forecasts.csv")
    live_forecast.add_argument("--model-version", required=True)
    live_forecast.add_argument("--issue-time-utc", required=True)
    live_forecast.add_argument("--scenarios", type=int, default=1000)

    demo = sub.add_parser("demo", help="Run a complete synthetic demonstration")
    demo.add_argument("--days", type=int, default=220)
    demo.add_argument("--scenarios", type=int, default=1000)
    demo.add_argument("--models", default="models/demo")
    demo.add_argument("--output", default="outputs/demo")

    elexon = sub.add_parser("collect-elexon", help="Collect raw half-hourly Elexon core data")
    elexon.add_argument("--start", required=True)
    elexon.add_argument("--end", required=True)
    elexon.add_argument("--output", default="data/parsed/elexon")
    elexon.add_argument("--chunk-days", type=int, default=30)

    actuals = sub.add_parser("collect-actuals", help="Append APXMIDP actual prices")
    actuals.add_argument("--start", required=True)
    actuals.add_argument("--end", required=True)
    actuals.add_argument("--actuals", default="live/actuals.csv")
    actuals.add_argument("--revision", default="initial")

    neso = sub.add_parser("collect-neso", help="Collect one configured NESO CKAN resource")
    neso.add_argument("--resource-id", required=True)
    neso.add_argument("--output", required=True)

    weather = sub.add_parser(
        "collect-weather",
        help="Collect point-in-time Open-Meteo previous-run weather",
    )
    weather.add_argument("--config", default="config/example.yaml")
    weather.add_argument("--group", choices=["demand", "wind", "solar"], required=True)
    weather.add_argument("--start", required=True)
    weather.add_argument("--end", required=True)
    weather.add_argument("--output", required=True)
    weather.add_argument(
        "--variables",
        nargs="+",
        default=[
            "temperature_2m_previous_day1",
            "wind_speed_100m_previous_day1",
            "shortwave_radiation_previous_day1",
            "cloud_cover_previous_day1",
        ],
    )

    dataset = sub.add_parser("build-dataset", help="Assemble the mapped half-hourly table")
    dataset.add_argument("--mapping", default="config/data_mapping.yaml")
    dataset.add_argument("--output", default="data/processed/gb_half_hourly.parquet")

    grade = sub.add_parser("grade", help="Append scores without overwriting forecasts")
    grade.add_argument("--forecasts", required=True)
    grade.add_argument("--actuals", required=True)
    grade.add_argument("--scores", required=True)

    return parser


def main() -> None:
    args = build_parser().parse_args()
    if args.command == "train":
        frame = _prepare(_load_frame(args.input))
        metrics = train_platform(
            frame,
            args.models,
            args.holdout_rows,
            args.time_series_splits,
        )
        print(metrics)
    elif args.command == "forecast":
        frame = _prepare(_load_frame(args.input))
        report = forecast_platform(frame, args.models, args.output, args.scenarios)
        print(report)
    elif args.command == "live-forecast":
        print(
            run_and_log_forecast(
                args.input,
                args.models,
                args.output,
                args.forecasts,
                args.model_version,
                args.issue_time_utc,
                args.scenarios,
            )
        )
    elif args.command == "collect-elexon":
        print(collect_elexon_core(args.start, args.end, args.output, args.chunk_days))
    elif args.command == "collect-actuals":
        result = collect_and_append_price_actuals(
            args.start,
            args.end,
            args.actuals,
            args.revision,
        )
        print({"rows": len(result)})
    elif args.command == "collect-neso":
        print(collect_neso_resource(args.resource_id, args.output))
    elif args.command == "collect-weather":
        settings = _config(args.config)
        sites = settings["weather_sites"][args.group]
        print(
            collect_previous_run_weather(
                sites,
                args.variables,
                args.start,
                args.end,
                args.output,
            )
        )
    elif args.command == "build-dataset":
        frame = build_half_hourly_dataset(args.mapping, args.output)
        print({"rows": len(frame), "output": args.output})
    elif args.command == "grade":
        result = grade_forecasts(args.forecasts, args.actuals, args.scores)
        print({"rows_appended": len(result)})
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
