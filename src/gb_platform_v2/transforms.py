"""Signed transforms for electricity prices."""

from __future__ import annotations

import numpy as np


def arcsinh_transform(values, scale: float = 50.0):
    """Scaled arcsinh transform supporting negative, zero and positive prices."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return np.arcsinh(np.asarray(values, dtype=float) / scale)


def inverse_arcsinh(values, scale: float = 50.0):
    """Reverse :func:`arcsinh_transform`."""
    if scale <= 0:
        raise ValueError("scale must be positive")
    return np.sinh(np.asarray(values, dtype=float)) * scale
