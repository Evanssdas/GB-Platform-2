"""Reproducible synthetic data for testing the software path only."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .features import add_cyclical_time_features, add_system_balance_features, add_weather_features


def make_synthetic_history(days: int = 220, seed: int = 42) -> pd.DataFrame:
    if days < 30:
        raise ValueError("days must be at least 30")
    rng = np.random.default_rng(seed)
    index = pd.date_range("2025-01-01", periods=days * 48, freq="30min", tz="UTC")
    frame = pd.DataFrame({"timestamp": index})
    frame = add_cyclical_time_features(frame)

    half_hour = np.arange(len(frame)) % 48
    annual = 2 * np.pi * np.arange(len(frame)) / (365.25 * 48)
    temperature = 10 + 7 * np.sin(annual - 1.2) + rng.normal(0, 1.8, len(frame))
    wind = np.clip(8 + 3 * np.sin(annual * 3) + rng.normal(0, 2.2, len(frame)), 0, None)
    solar_shape = np.maximum(0, np.sin(np.pi * (half_hour - 12) / 24))
    solar_rad = 650 * solar_shape * np.clip(1 + rng.normal(0, 0.18, len(frame)), 0, None)
    frame["temperature_c"] = temperature
    frame["wind_speed_ms"] = wind
    frame["solar_radiation_wm2"] = solar_rad
    frame = add_weather_features(frame)

    demand = (
        26000
        + 6500 * np.maximum(0, np.sin(np.pi * (half_hour - 10) / 24))
        + 450 * frame["hdd"]
        - 1300 * frame["is_weekend"]
        + rng.normal(0, 700, len(frame))
    )
    embedded_wind = np.clip(700 + 18 * wind**3 + rng.normal(0, 180, len(frame)), 0, 4500)
    transmission_wind = np.clip(1800 + 42 * wind**3 + rng.normal(0, 500, len(frame)), 0, 16000)
    embedded_solar = np.clip(11000 * solar_shape + rng.normal(0, 350, len(frame)), 0, 14500)
    nuclear_available = 5200 - 900 * (rng.random(len(frame)) < 0.035)
    nuclear_modulation = np.maximum(0, 3500 - demand / 10 - transmission_wind / 4)
    nuclear = np.clip(nuclear_available - nuclear_modulation, 1800, None)
    net_import = 2200 + rng.normal(0, 800, len(frame))
    battery = np.clip(-0.12 * (transmission_wind + embedded_solar - 9000), -3500, 3500)
    inertia = np.clip(95 + nuclear / 170 + np.maximum(demand - 25000, 0) / 1200 + rng.normal(0, 4, len(frame)), 70, 180)

    wind_potential = embedded_wind + transmission_wind
    wind_curtailment = np.maximum(0, wind_potential + embedded_solar - demand * 0.55 - 8000)
    transmission_wind = np.maximum(0, transmission_wind - wind_curtailment)

    frame["demand_mw"] = demand
    frame["embedded_wind_mw"] = embedded_wind
    frame["embedded_solar_mw"] = embedded_solar
    frame["transmission_wind_mw"] = transmission_wind
    frame["curtailed_wind_mw"] = wind_curtailment
    frame["curtailed_solar_mw"] = np.maximum(0, embedded_solar - demand * 0.35 - 5000)
    frame["nuclear_available_mw"] = nuclear_available
    frame["nuclear_mw"] = nuclear
    frame["net_import_mw"] = net_import
    frame["battery_net_mw"] = battery
    frame["inertia_gvas"] = inertia
    frame = add_system_balance_features(frame)

    tightness = frame["net_system_short_mw"]
    price = (
        42
        + 0.0030 * tightness
        + 0.00000007 * np.maximum(tightness, 0) ** 2
        - 0.0045 * frame["curtailed_wind_mw"]
        - 0.0030 * frame["curtailed_solar_mw"]
        + 0.18 * np.maximum(105 - inertia, 0)
        + rng.normal(0, 9, len(frame))
    )
    frame["price_gbp_mwh"] = price

    conditions = [
        frame["price_gbp_mwh"] < 0,
        frame["net_system_short_mw"] > 14000,
        frame["battery_net_mw"] > 1600,
        frame["net_import_mw"] > 3500,
    ]
    choices = ["renewable_or_negative_price", "scarcity_or_other", "battery", "interconnector"]
    frame["marginal_technology"] = np.select(conditions, choices, default="CCGT")
    return frame.set_index("timestamp", drop=False)
