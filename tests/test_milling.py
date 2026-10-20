import dataclasses
import math

import numpy as np
import pytest

from choppy_water.config import load_config
from choppy_water.heightfield import (
    Heightfield,
    SurfaceStats,
    footprint_mask,
    generate_heightfield,
)
from choppy_water.milling import (
    close_with_ball,
    format_report,
    plan_milling,
)

MM = 25.4


# -- tool reach (morphological closing) -------------------------------------------------------


def trench_surface(radius, spacing):
    """Flat at z=10 with a narrow trench (width r) and a wide one (width 4r), both at z=5."""
    z = np.full((200, 200), 10.0)
    z[:, 40 : 40 + int(radius / spacing)] = 5.0
    z[:, 100 : 100 + int(4 * radius / spacing)] = 5.0
    return z


def test_narrow_trench_is_filled_to_the_depth_a_ball_can_reach():
    radius, spacing = 1.5875, 0.05
    closed = close_with_ball(trench_surface(radius, spacing), radius, spacing)
    width = radius  # trench width
    reachable_depth = radius - math.sqrt(radius**2 - (width / 2) ** 2)
    floor = closed[100, 40 + int(radius / spacing) // 2]
    assert floor == pytest.approx(10 - reachable_depth, abs=0.02)


def test_wide_trench_centre_is_cut_fully():
    radius, spacing = 1.5875, 0.05
    closed = close_with_ball(trench_surface(radius, spacing), radius, spacing)
    assert closed[100, 100 + int(2 * radius / spacing)] == pytest.approx(5.0)


def test_closing_only_adds_material_keeps_peaks_and_is_idempotent():
    radius, spacing = 1.5875, 0.05
    z = trench_surface(radius, spacing) + np.random.default_rng(0).normal(0, 0.05, (200, 200))
    closed = close_with_ball(z, radius, spacing)
    assert (closed >= z - 1e-12).all()
    assert closed.max() == pytest.approx(z.max())
    assert np.allclose(close_with_ball(closed, radius, spacing), closed)


def test_tool_smaller_than_a_cell_changes_nothing():
    z = np.random.default_rng(1).normal(size=(30, 30))
    assert np.array_equal(close_with_ball(z, 0.01, 0.05), z)


# -- planning on synthetic and generated surfaces -------------------------------------------


def synthetic(overrides, height):
    """A rectangle-outline heightfield whose thickness is ``height(x, y)`` (mm)."""
    cfg = load_config(
        None,
        [
            "part.shape='rect'",
            "part.width=1.6",
            "part.length=0.8",
            "mesh.grid_spacing=0.02",
            *overrides,
        ],
    )
    mm = cfg.to_mm()
    spacing = mm.mesh.grid_spacing
    count = math.ceil(max(mm.part.extent) / 2 / spacing) + 10
    axis = np.arange(-count, count + 1) * spacing
    gx, gy = np.meshgrid(axis, axis)
    z = height(gx, gy)
    mask = footprint_mask(mm.part, gx, gy)
    stats = SurfaceStats(
        relief=float(np.ptp(z[mask])), max_slope_deg=0.0, unresolved_fraction=0.0, iterations=0
    )
    return cfg, Heightfield(x=axis, y=axis, z=z, spacing=spacing, mask=mask, stats=stats)


def test_flat_surface_path_length_and_time():
    cfg, hf = synthetic([], lambda x, y: np.full_like(x, 8.0))
    mm = cfg.to_mm()
    _, report = plan_milling(cfg, hf)
    lines = math.floor(mm.part.length / report.stepover) + 1
    assert report.finishing_path_length == pytest.approx(lines * mm.part.width, rel=0.02)
    assert report.finishing_minutes == pytest.approx(
        report.finishing_path_length / mm.milling.feed_rate
    )
    assert report.unreachable_fraction == 0.0
    assert report.steep_fraction == 0.0


def test_sloped_plane_lengthens_the_path_and_trips_the_slope_limit():
    tilt = math.radians(30)
    cfg, flat = synthetic([], lambda x, y: np.full_like(x, 20.0))
    _, ramp = synthetic(["milling.max_slope_deg=20"], lambda x, y: 20 + np.tan(tilt) * x)
    _, flat_report = plan_milling(cfg, flat)
    milled, report = plan_milling(cfg, ramp)
    assert report.finishing_path_length == pytest.approx(
        flat_report.finishing_path_length / math.cos(tilt), rel=0.02
    )
    assert report.max_slope_deg == pytest.approx(30, abs=0.5)
    assert milled.stats.max_slope_deg == pytest.approx(30, abs=0.5)
    assert any("steeper than 20" in w for w in report.warnings) or report.steep_fraction == 0

    steep_cfg, steep_hf = synthetic(
        ["milling.max_slope_deg=20"], lambda x, y: 20 + np.tan(tilt) * x
    )
    _, steep_report = plan_milling(steep_cfg, steep_hf)
    assert steep_report.steep_fraction > 0.99
    assert any("steeper than 20" in w for w in steep_report.warnings)
    _, ok_report = plan_milling(cfg, ramp)  # default limit is 70 deg
    assert ok_report.steep_fraction == 0.0


def test_roughing_layers_stock_margin_and_heights():
    cfg, hf = synthetic([], lambda x, y: np.full_like(x, 6.35))
    _, report = plan_milling(cfg, hf)
    assert report.deepest_cut_z == pytest.approx(6.35)
    assert report.top_z == pytest.approx(6.35)
    assert report.stock_margin == pytest.approx(25.4 - 6.35)
    assert report.roughing_layers == 8  # ceil((25.4 - 6.35) / 2.54)


def test_scallop_height_formula():
    cfg, hf = synthetic(["milling.stepover_pct=20"], lambda x, y: np.full_like(x, 8.0))
    _, report = plan_milling(cfg, hf)
    radius, stepover = 0.125 * MM / 2, 0.2 * 0.125 * MM
    assert report.stepover == pytest.approx(stepover)
    assert report.scallop_height == pytest.approx(radius - math.sqrt(radius**2 - stepover**2 / 4))


@pytest.fixture(scope="module")
def sea():
    cfg = load_config(None, ["mesh.grid_spacing=0.04", "mesh.edge_segments=235"])
    return cfg, generate_heightfield(cfg)


def with_tool(cfg, diameter, enforce):
    return load_config(None, [
        "mesh.grid_spacing=0.04", "mesh.edge_segments=235",
        f"milling.tool_diameter={diameter}", f"milling.enforce_tool_limits={str(enforce).lower()}",
    ])  # fmt: skip


def test_big_tool_leaves_more_unreachable_material_than_small_tool():
    small = with_tool(None, 0.0625, True)
    big = with_tool(None, 0.5, True)
    _, small_report = plan_milling(small, generate_heightfield(small))
    _, big_report = plan_milling(big, generate_heightfield(big))
    assert big_report.unreachable_fraction > small_report.unreachable_fraction
    assert big_report.max_fill_depth > small_report.max_fill_depth
    assert any("finer than" in w for w in big_report.warnings)


def test_enforcing_limits_fills_valleys_but_stays_inside_stock():
    cfg = with_tool(None, 0.5, True)
    ideal = generate_heightfield(cfg)
    milled, report = plan_milling(cfg, ideal)
    assert (milled.z >= ideal.z - 1e-9).all()
    assert (milled.z > ideal.z + 0.01).any()
    inside = milled.z[milled.mask]
    assert inside.min() >= cfg.part.base_thickness * MM - 1e-9
    assert inside.max() <= ideal.z[ideal.mask].max() + 1e-9
    assert milled.stats.relief == pytest.approx(np.ptp(inside))
    assert milled.stats.relief < ideal.stats.relief
    assert report.tool_limits_applied
    assert "filled in the STL" in " ".join(report.warnings)


def test_not_enforcing_keeps_the_ideal_surface_but_still_reports_the_gap():
    enforced_cfg, free_cfg = with_tool(None, 0.5, True), with_tool(None, 0.5, False)
    ideal = generate_heightfield(free_cfg)
    milled, free = plan_milling(free_cfg, ideal)
    _, enforced = plan_milling(enforced_cfg, ideal)
    assert np.array_equal(milled.z, ideal.z)
    assert not free.tool_limits_applied
    assert free.unreachable_fraction == pytest.approx(enforced.unreachable_fraction)
    assert "enforce_tool_limits is off" in " ".join(free.warnings)


def test_default_tool_barely_changes_the_default_surface():
    # The reach estimate needs ~10 cells across the cutter, so use the production grid spacing.
    cfg = load_config(None)
    _, report = plan_milling(cfg, generate_heightfield(cfg))
    assert report.unreachable_fraction < 0.02


def test_heightfield_is_padded_by_the_cutter_radius(sea):
    cfg, ideal = sea
    radius = cfg.to_mm().milling.tool_diameter / 2
    assert ideal.x[-1] - cfg.to_mm().part.diameter / 2 >= radius


# -- report text ------------------------------------------------------------------------------


def test_report_uses_config_units_and_lists_warnings(sea):
    cfg = with_tool(None, 0.5, True)
    _, report = plan_milling(cfg, generate_heightfield(cfg))
    text = format_report(report, cfg)
    assert "Ball nose diameter:     0.500 in" in text
    assert "Stock thickness:        1 in" in text
    assert "Warnings" in text
    assert "finishing pass only" in text

    mm_cfg = dataclasses.replace(cfg, units=dataclasses.replace(cfg.units, length="mm"))
    assert " mm" in format_report(report, mm_cfg)
