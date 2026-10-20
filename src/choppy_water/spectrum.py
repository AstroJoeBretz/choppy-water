"""Wave spectrum shared by the FFT and Gerstner surface generators.

The spectrum is described in carver-friendly terms (wavelengths and a spread angle)
rather than wind speed and fetch. It follows the Phillips saturation form: height
energy per unit wavenumber ``E(k) ~ k**-3`` above the peak, rolling off below it, with
a smooth band limit so no energy falls outside ``[wavelength_min, wavelength_max]``.
Overall amplitude is arbitrary here; the generators normalize to the requested relief.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from choppy_water.config import Water

# Narrowest directional lobe we allow, so "spread = 0" is still representable on a grid.
MIN_SPREAD_RAD = math.radians(2.0)


@dataclass(frozen=True)
class WaveBand:
    """Wavenumbers (rad per length unit) derived from the configured wavelengths."""

    k_min: float
    k_peak: float
    k_max: float

    @classmethod
    def from_water(cls, water: Water) -> WaveBand:
        return cls(
            k_min=2 * math.pi / water.wavelength_max,
            k_peak=2 * math.pi / water.wavelength_dominant,
            k_max=2 * math.pi / water.wavelength_min,
        )


def spread_sigma(water: Water) -> float:
    """Directional standard deviation in radians."""
    return max(math.radians(water.directional_spread_deg), MIN_SPREAD_RAD)


def energy(k: np.ndarray, band: WaveBand) -> np.ndarray:
    """Height energy per unit wavenumber ``E(k)``; peaks at ``k_peak`` before band-limiting."""
    k = np.asarray(k, dtype=float)
    out = np.zeros_like(k)
    pos = k > 0
    kp = k[pos]
    out[pos] = (
        kp**-3
        * np.exp(-1.5 * (band.k_peak / kp) ** 2)
        * np.exp(-((band.k_min / kp) ** 4))
        * np.exp(-((kp / band.k_max) ** 4))
    )
    return out


def directional(theta: np.ndarray, wind_rad: float, sigma: float) -> np.ndarray:
    """Wrapped-Gaussian angular distribution centred on the wind direction."""
    delta = (np.asarray(theta) - wind_rad + math.pi) % (2 * math.pi) - math.pi
    return np.exp(-0.5 * (delta / sigma) ** 2)


def spectrum_2d(kx: np.ndarray, ky: np.ndarray, water: Water) -> np.ndarray:
    """Two-dimensional power spectrum ``P(kx, ky)``; zero at ``k = 0``.

    ``P = E(k) / k * D(theta)`` so that integrating over angle recovers ``E(k)``.
    """
    band = WaveBand.from_water(water)
    k = np.hypot(kx, ky)
    theta = np.arctan2(ky, kx)
    radial = np.zeros_like(k)
    pos = k > 0
    radial[pos] = energy(k[pos], band) / k[pos]
    return radial * directional(theta, math.radians(water.wind_direction_deg), spread_sigma(water))
