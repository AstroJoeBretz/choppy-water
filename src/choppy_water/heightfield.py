"""Choppy-water heightfield synthesis.

A *wave field* supplies, at any point ``x0`` on the undisturbed water, a height ``h`` and a
horizontal displacement ``D`` (Tessendorf's "choppy waves"). Each surface point is moved to
``x = x0 - choppiness * D(x0)``, which pulls points toward crests and sharpens them.

A CNC mill needs a single-valued surface ``z(x, y)`` on a regular grid, so we invert that
mapping: for every output grid point ``x`` we solve ``x0 = x + choppiness * D(x0)`` by
fixed-point iteration and read ``h(x0)``. Where the surface would fold over itself (crests
that curl), the iteration does not converge; the unconverged fraction is reported so callers
can lower the choppiness.

All lengths here are millimetres: pass a config through :meth:`Config.to_mm` first.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Protocol

import numpy as np
from scipy import ndimage
from scipy.fft import next_fast_len

from choppy_water.config import Config, Part, Water
from choppy_water.spectrum import WaveBand, energy, spectrum_2d, spread_sigma

MAX_SIM_GRID = 4096
MAX_ITERATIONS = 40
GERSTNER_WAVES = 64


class WaveField(Protocol):
    def height(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        """Wave height ``h`` at undisturbed positions ``(x, y)``."""

    def displacement(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Horizontal choppy displacement ``(Dx, Dy)`` at undisturbed positions."""


class FFTWaveField:
    """Periodic random sea synthesized on an FFT grid, spline-interpolated on demand."""

    def __init__(self, water: Water, grid_spacing: float, rng: np.random.Generator) -> None:
        wanted = max(math.ceil(water.patch_size / grid_spacing), 8)
        n = next_fast_len(wanted + wanted % 2)  # smooth composite size, not a power of two
        if n > MAX_SIM_GRID:
            raise ValueError(
                f"water.patch_size / mesh.grid_spacing needs a {n}x{n} FFT grid "
                f"(limit {MAX_SIM_GRID}); use a larger grid_spacing or smaller patch_size"
            )
        self.n = n
        self.dx = water.patch_size / n

        k1 = 2 * math.pi * np.fft.fftfreq(n, d=self.dx)
        kx, ky = np.meshgrid(k1, k1)  # arrays are indexed [row = y, col = x]
        kmag = np.hypot(kx, ky)

        noise = rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))
        h = np.fft.ifft2(noise * np.sqrt(spectrum_2d(kx, ky, water))).real
        hk = np.fft.fft2(h)  # re-transform so the spectrum is exactly Hermitian
        if water.smoothing > 0:
            hk = hk * np.exp(-0.5 * (water.smoothing * kmag) ** 2)
            h = np.fft.ifft2(hk).real

        safe = np.where(kmag > 0, kmag, 1.0)
        dxk = np.where(kmag > 0, -1j * kx / safe, 0) * hk
        dyk = np.where(kmag > 0, -1j * ky / safe, 0) * hk
        self._h, self._dx, self._dy = (
            ndimage.spline_filter(field, order=3, mode="grid-wrap")
            for field in (h, np.fft.ifft2(dxk).real, np.fft.ifft2(dyk).real)
        )

    def _sample(self, coeffs: np.ndarray, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        coords = np.stack([y / self.dx + self.n / 2, x / self.dx + self.n / 2])
        return ndimage.map_coordinates(coeffs, coords, order=3, mode="grid-wrap", prefilter=False)

    def height(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        return self._sample(self._h, x, y)

    def displacement(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self._sample(self._dx, x, y), self._sample(self._dy, x, y)


class GerstnerWaveField:
    """Sum of directional sine waves with the matching Gerstner horizontal displacement."""

    def __init__(self, water: Water, rng: np.random.Generator, n_waves: int = GERSTNER_WAVES):
        band = WaveBand.from_water(water)
        step = math.log(band.k_max / band.k_min) / n_waves
        # Stratified log-spaced wavenumbers (less clumpy than purely random draws).
        k = np.exp(math.log(band.k_min) + (np.arange(n_waves) + rng.uniform(size=n_waves)) * step)
        angle = math.radians(water.wind_direction_deg) + rng.normal(
            0.0, spread_sigma(water), n_waves
        )
        self.kx = k * np.cos(angle)
        self.ky = k * np.sin(angle)
        self.phase = rng.uniform(0, 2 * math.pi, n_waves)
        # Equal-width bins in ln k: amplitude^2 ~ E(k) * k.
        self.amp = np.sqrt(energy(k, band) * k)
        self.unit_x = np.cos(angle)
        self.unit_y = np.sin(angle)

    def height(self, x: np.ndarray, y: np.ndarray) -> np.ndarray:
        h = np.zeros_like(x, dtype=float)
        for kx, ky, phase, amp in zip(self.kx, self.ky, self.phase, self.amp, strict=True):
            h += amp * np.cos(kx * x + ky * y + phase)
        return h

    def displacement(self, x: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        dx = np.zeros_like(x, dtype=float)
        dy = np.zeros_like(dx)
        for kx, ky, phase, amp, ux, uy in zip(
            self.kx, self.ky, self.phase, self.amp, self.unit_x, self.unit_y, strict=True
        ):
            s = amp * np.sin(kx * x + ky * y + phase)
            dx += ux * s
            dy += uy * s
        return dx, dy


def make_wave_field(water: Water, grid_spacing: float) -> WaveField:
    rng = np.random.default_rng(water.seed)
    if water.method == "fft":
        return FFTWaveField(water, grid_spacing, rng)
    return GerstnerWaveField(water, rng)


def footprint_mask(part: Part, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """True where ``(x, y)`` lies inside the part outline (centred on the origin)."""
    if part.shape == "disc":
        return np.hypot(x, y) <= part.diameter / 2
    return (np.abs(x) <= part.width / 2) & (np.abs(y) <= part.length / 2)


@dataclass(frozen=True)
class SurfaceStats:
    relief: float  # peak-to-peak height over the part (mm)
    max_slope_deg: float
    unresolved_fraction: float  # share of the part where choppy inversion did not converge
    iterations: int


@dataclass(frozen=True)
class Heightfield:
    """Surface thickness ``z[row=y, col=x]`` (mm above the flat bottom) on a regular grid."""

    x: np.ndarray
    y: np.ndarray
    z: np.ndarray
    spacing: float
    mask: np.ndarray  # True inside the part outline
    stats: SurfaceStats

    def sample(self, x: np.ndarray, y: np.ndarray, method: str = "linear") -> np.ndarray:
        """Interpolate the thickness at points inside the grid.

        ``method`` is ``"linear"`` (bounded by the neighbouring samples) or ``"cubic"``
        (smoother, but can overshoot slightly at sharp crests).
        """
        x, y = np.broadcast_arrays(np.asarray(x, dtype=float), np.asarray(y, dtype=float))
        shape = x.shape
        x, y = x.ravel(), y.ravel()
        slack = 1e-9 * self.spacing
        if (
            x.min() < self.x[0] - slack
            or x.max() > self.x[-1] + slack
            or y.min() < self.y[0] - slack
            or y.max() > self.y[-1] + slack
        ):
            raise ValueError("sample points fall outside the heightfield grid")
        order = {"linear": 1, "cubic": 3}[method]
        coords = np.stack([(y - self.y[0]) / self.spacing, (x - self.x[0]) / self.spacing])
        values = ndimage.map_coordinates(self.z, coords, order=order, mode="nearest")
        return values.reshape(shape)


def _axis(half_extent: float, spacing: float, margin_cells: int) -> np.ndarray:
    """Symmetric axis through 0 covering ``[-half_extent, half_extent]`` plus a margin."""
    count = math.ceil(half_extent / spacing) + margin_cells
    return np.arange(-count, count + 1) * spacing


def slope_degrees(z: np.ndarray, spacing: float) -> np.ndarray:
    """Surface inclination from horizontal at every grid point (0 = flat, 90 = vertical)."""
    slope_y, slope_x = np.gradient(z, spacing)
    return np.degrees(np.arctan(np.hypot(slope_x, slope_y)))


def warp_surface(
    field: WaveField, gx: np.ndarray, gy: np.ndarray, c: float, tolerance: float
) -> tuple[np.ndarray, np.ndarray, int]:
    """Heights on the grid ``(gx, gy)`` of the choppy surface ``x = x0 - c * D(x0)``.

    Inverts the mapping by fixed-point iteration ``x0 <- x + c * D(x0)``. Returns the
    (unit-gain) heights, the final per-point step size (large where the surface folds and
    the iteration cannot converge) and the number of iterations used.
    """
    x0, y0 = gx.copy(), gy.copy()
    residual = np.zeros_like(gx)
    iterations = 0
    while c != 0 and iterations < MAX_ITERATIONS:
        iterations += 1
        dx, dy = field.displacement(x0, y0)
        nx0, ny0 = gx + c * dx, gy + c * dy
        residual = np.maximum(np.abs(nx0 - x0), np.abs(ny0 - y0))
        x0, y0 = nx0, ny0
        if residual.max() < tolerance:
            break
    return field.height(x0, y0), residual, iterations


def generate_heightfield(config: Config) -> Heightfield:
    """Synthesize the choppy-water thickness map for ``config`` (any length unit)."""
    cfg = config.to_mm()
    part, water, spacing = cfg.part, cfg.water, cfg.mesh.grid_spacing

    field = make_wave_field(water, spacing)  # first: rejects oversized FFT grids cheaply

    # Pad the grid by the cutter radius so the tool-reach filter sees real surface (not an
    # artificial edge) right up to the outline.
    margin = math.ceil(cfg.milling.tool_diameter / 2 / spacing) + 2
    width, height = part.extent
    x_axis = _axis(width / 2, spacing, margin)
    y_axis = _axis(height / 2, spacing, margin)
    gx, gy = np.meshgrid(x_axis, y_axis)
    mask = footprint_mask(part, gx, gy)

    # The field's amplitude is arbitrary. Scale displacement by the gain that would give the
    # requested relief, so `choppiness` means the same thing for every seed and spectrum.
    spread = np.ptp(field.height(gx, gy)[mask])
    if spread <= 0:
        raise ValueError("wave field is flat over the part; check the water settings")
    gain = water.relief / spread

    tolerance = 0.05 * spacing
    h, residual, iterations = warp_surface(
        field, gx, gy, water.choppiness * gain, tolerance=tolerance
    )
    # Warping shifts the extremes slightly, so renormalize to exactly `relief` over the part.
    low, high = h[mask].min(), h[mask].max()
    z = part.base_thickness + (h - low) / (high - low) * water.relief

    stats = SurfaceStats(
        relief=float(np.ptp(z[mask])),
        max_slope_deg=float(slope_degrees(z, spacing)[mask].max()),
        unresolved_fraction=float(np.mean(residual[mask] > tolerance)),
        iterations=iterations,
    )
    return Heightfield(x=x_axis, y=y_axis, z=z, spacing=spacing, mask=mask, stats=stats)
