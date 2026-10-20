import dataclasses

import numpy as np
import pytest

from choppy_water.config import Config, load_config
from choppy_water.heightfield import (
    GerstnerWaveField,
    footprint_mask,
    generate_heightfield,
    warp_surface,
)

MM = 25.4
# A coarse grid keeps the suite fast; the production default spacing is 0.01 in.
FAST = ["mesh.grid_spacing=0.04"]


def make(*overrides):
    return load_config(None, [*FAST, *overrides])


def skewness(values):
    values = np.asarray(values)
    return float(((values - values.mean()) ** 3).mean() / values.std() ** 3)


class SingleWave:
    """h = a*cos(kx) with its Gerstner displacement D = a*sin(kx)."""

    k = 2 * np.pi / 20
    a = 3.0

    def height(self, x, y):
        return self.a * np.cos(self.k * x)

    def displacement(self, x, y):
        return self.a * np.sin(self.k * x), np.zeros_like(x)


def test_relief_and_base_are_exact_for_disc():
    cfg = make()
    hf = generate_heightfield(cfg)
    inside = hf.z[hf.mask]
    assert inside.min() == pytest.approx(cfg.part.base_thickness * MM)
    assert np.ptp(inside) == pytest.approx(cfg.water.relief * MM)
    assert hf.stats.relief == pytest.approx(cfg.water.relief * MM)


def test_rect_grid_covers_part_and_matches_mask():
    hf = generate_heightfield(make("part.shape='rect'", "part.width=5", "part.length=2"))
    assert hf.x.min() <= -5 * MM / 2 and hf.x.max() >= 5 * MM / 2
    assert hf.y.min() <= -2 * MM / 2 and hf.y.max() >= 2 * MM / 2
    assert hf.mask.shape == hf.z.shape
    assert hf.mask.sum() * hf.spacing**2 == pytest.approx(5 * MM * 2 * MM, rel=0.03)


def test_disc_mask_area():
    hf = generate_heightfield(make())
    r = 1.5 * MM
    assert hf.mask.sum() * hf.spacing**2 == pytest.approx(np.pi * r * r, rel=0.02)


def test_grid_is_symmetric_about_origin():
    hf = generate_heightfield(make())
    assert hf.x == pytest.approx(-hf.x[::-1])
    assert hf.y == pytest.approx(-hf.y[::-1])
    assert 0.0 in hf.x


def test_same_seed_is_deterministic_and_different_seed_differs():
    a = generate_heightfield(make("water.seed=5")).z
    b = generate_heightfield(make("water.seed=5")).z
    c = generate_heightfield(make("water.seed=6")).z
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)


@pytest.mark.parametrize("method", ["fft", "gerstner"])
def test_both_methods_stay_inside_the_stock(method):
    cfg = make(f"water.method='{method}'")
    hf = generate_heightfield(cfg)
    z = hf.z[hf.mask]
    assert z.min() >= cfg.part.base_thickness * MM - 1e-9
    assert z.max() <= cfg.part.max_thickness * MM + 1e-9
    assert z.max() <= cfg.milling.stock_thickness * MM


def test_wave_crests_run_perpendicular_to_wind():
    """With wind along +x and a narrow spread, the surface varies mostly along x."""
    hf = generate_heightfield(
        make("water.directional_spread_deg=5", "water.choppiness=0", "water.wind_direction_deg=0")
    )
    gy, gx = np.gradient(hf.z, hf.spacing)
    assert np.abs(gx[hf.mask]).mean() > 3 * np.abs(gy[hf.mask]).mean()


def test_smoothing_reduces_slope():
    sharp = generate_heightfield(make("water.choppiness=0")).stats.max_slope_deg
    smooth = generate_heightfield(make("water.choppiness=0", "water.smoothing=0.05")).stats
    assert smooth.max_slope_deg < sharp


def test_zero_choppiness_skips_the_inversion():
    assert generate_heightfield(make("water.choppiness=0")).stats.iterations == 0
    assert generate_heightfield(make("water.choppiness=0.5")).stats.iterations > 0


def test_choppiness_sharpens_crests_of_a_single_wave():
    x = np.linspace(-20, 20, 2001)
    gx, gy = np.meshgrid(x, np.zeros(1))
    flat, _, _ = warp_surface(SingleWave(), gx, gy, 0.0, 1e-6)
    chop, residual, _ = warp_surface(SingleWave(), gx, gy, 0.4, 1e-6)
    assert abs(skewness(flat)) < 0.01
    assert skewness(chop) > 0.3  # narrow crests, broad troughs
    assert residual.max() < 1e-5


def test_warp_matches_forward_mapping():
    """Resampling the forward-mapped surface x = x0 - c*D(x0) must agree with the inversion."""
    wave, c = SingleWave(), 0.3  # c*k*a < 1, so the forward map is monotonic
    x = np.linspace(-20, 20, 801)
    h, _, _ = warp_surface(wave, *np.meshgrid(x, np.zeros(1)), c, 1e-10)

    x0 = np.linspace(-60, 60, 200001)
    forward_x = x0 - c * wave.displacement(x0, 0)[0]
    expected = np.interp(x, forward_x, wave.height(x0, 0))
    assert h[0] == pytest.approx(expected, abs=1e-4)


def test_folding_is_reported_when_choppiness_is_extreme():
    assert generate_heightfield(make("water.choppiness=3")).stats.unresolved_fraction > 0.05
    assert generate_heightfield(make("water.choppiness=0.3")).stats.unresolved_fraction == 0.0


def test_sample_matches_grid_values_and_interpolates():
    hf = generate_heightfield(make())
    i, j = 40, 55
    assert hf.sample(hf.x[j], hf.y[i]) == pytest.approx(hf.z[i, j])
    mid = hf.sample((hf.x[j] + hf.x[j + 1]) / 2, hf.y[i])
    assert mid == pytest.approx((hf.z[i, j] + hf.z[i, j + 1]) / 2)


def test_oversized_fft_grid_is_rejected():
    with pytest.raises(ValueError, match="FFT grid"):
        generate_heightfield(load_config(None, ["mesh.grid_spacing=0.001"]))


def test_footprint_mask_shapes():
    part = Config().to_mm().part
    assert footprint_mask(part, np.array(0.0), np.array(0.0))
    assert not footprint_mask(part, np.array(part.diameter / 2 + 1), np.array(0.0))
    rect = dataclasses.replace(part, shape="rect", width=10.0, length=4.0)
    assert footprint_mask(rect, np.array(4.9), np.array(1.9))
    assert not footprint_mask(rect, np.array(0.0), np.array(2.1))


def test_gerstner_field_is_seeded():
    water = Config().to_mm().water
    pts = np.linspace(0, 10, 5)
    a = GerstnerWaveField(water, np.random.default_rng(1)).height(pts, pts)
    b = GerstnerWaveField(water, np.random.default_rng(1)).height(pts, pts)
    c = GerstnerWaveField(water, np.random.default_rng(2)).height(pts, pts)
    assert np.array_equal(a, b)
    assert not np.allclose(a, c)
