import dataclasses
import math

import numpy as np
import pytest

from choppy_water.config import Config
from choppy_water.spectrum import (
    MIN_SPREAD_RAD,
    WaveBand,
    directional,
    energy,
    spectrum_2d,
    spread_sigma,
)


def water(**changes):
    return dataclasses.replace(Config().to_mm().water, **changes)


def test_band_from_water_converts_wavelength_to_wavenumber():
    band = WaveBand.from_water(
        water(wavelength_min=10.0, wavelength_dominant=20.0, wavelength_max=40.0)
    )
    assert band.k_max == pytest.approx(2 * math.pi / 10)
    assert band.k_peak == pytest.approx(2 * math.pi / 20)
    assert band.k_min == pytest.approx(2 * math.pi / 40)


def test_energy_peaks_at_dominant_wavenumber():
    # A very wide band so the band-limiting window does not move the peak.
    band = WaveBand.from_water(
        water(wavelength_min=0.5, wavelength_dominant=20.0, wavelength_max=140.0, patch_size=150.0)
    )
    k = np.linspace(band.k_peak / 5, band.k_peak * 5, 20001)
    assert k[np.argmax(energy(k, band))] == pytest.approx(band.k_peak, rel=0.01)


def test_energy_is_band_limited_and_zero_at_origin():
    band = WaveBand.from_water(water())
    peak = energy(np.array([band.k_peak]), band)[0]
    assert energy(np.array([0.0]), band)[0] == 0.0
    assert energy(np.array([band.k_min * 0.3]), band)[0] < 1e-3 * peak
    assert energy(np.array([band.k_max * 3.0]), band)[0] < 1e-3 * peak


def test_directional_peaks_at_wind_and_wraps():
    wind = math.radians(30)
    angles = np.array([wind, wind + math.pi / 2, wind + 2 * math.pi, wind - 2 * math.pi])
    d = directional(angles, wind, sigma=0.5)
    assert d[0] == pytest.approx(1.0)
    assert d[1] < 0.1
    assert d[2] == pytest.approx(1.0)
    assert d[3] == pytest.approx(1.0)


def test_zero_spread_still_has_finite_width():
    assert spread_sigma(water(directional_spread_deg=0.0)) == MIN_SPREAD_RAD


def test_spectrum_2d_is_zero_at_origin_and_peaks_along_wind():
    w = water(wind_direction_deg=0.0, directional_spread_deg=20.0)
    band = WaveBand.from_water(w)
    kx = np.array([0.0, band.k_peak, 0.0])
    ky = np.array([0.0, 0.0, band.k_peak])
    p = spectrum_2d(kx, ky, w)
    assert p[0] == 0.0
    assert p[1] > 10 * p[2]
