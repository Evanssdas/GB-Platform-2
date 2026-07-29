"""Battery-state and frequency-security screening utilities."""

from __future__ import annotations

import numpy as np
import pandas as pd


def update_battery_soc(
    power_mw: pd.Series,
    initial_soc_mwh: float,
    capacity_mwh: float,
    charge_efficiency: float = 0.93,
    discharge_efficiency: float = 0.93,
) -> pd.Series:
    """Integrate half-hourly battery power into state of charge.

    Positive power means discharge to the grid; negative power means charging.
    """
    if capacity_mwh <= 0:
        raise ValueError("capacity_mwh must be positive")
    soc = float(np.clip(initial_soc_mwh, 0, capacity_mwh))
    values = []
    for power in power_mw.astype(float):
        if power >= 0:
            soc -= 0.5 * power / discharge_efficiency
        else:
            soc += 0.5 * (-power) * charge_efficiency
        soc = float(np.clip(soc, 0, capacity_mwh))
        values.append(soc)
    return pd.Series(values, index=power_mw.index, name="battery_soc_mwh")


def frequency_security_screen(
    inertia_gvas: pd.Series,
    largest_loss_mw: float,
    response_mw: float,
    response_delivery_seconds: float = 1.0,
    nominal_hz: float = 50.0,
    warning_nadir_hz: float = 49.2,
) -> pd.DataFrame:
    """Return a transparent RoCoF/nadir screening proxy.

    This is not a dynamic certification model. It deliberately exposes the
    assumptions rather than claiming that inertia alone guarantees 50 Hz.
    """
    inertia = inertia_gvas.astype(float).clip(lower=1.0)
    imbalance_gw = max(largest_loss_mw - response_mw, 0.0) / 1000.0
    initial_rocof_hz_s = -nominal_hz * (largest_loss_mw / 1000.0) / (2.0 * inertia)
    estimated_drop_hz = np.abs(initial_rocof_hz_s) * response_delivery_seconds
    estimated_nadir_hz = nominal_hz - estimated_drop_hz - 0.02 * imbalance_gw
    return pd.DataFrame(
        {
            "initial_rocof_hz_per_s": initial_rocof_hz_s,
            "estimated_nadir_hz": estimated_nadir_hz,
            "low_frequency_warning": estimated_nadir_hz < warning_nadir_hz,
        },
        index=inertia.index,
    )
