"""What a real cutter can do with the heightfield, and a plain-language milling report.

**Tool reach.** A ball-nose cutter cannot enter a valley narrower than itself, so the
surface it actually leaves is the *morphological closing* of the ideal surface by the ball:
dilate by the ball's profile (where the tool centre may go), then erode by it (what the
swept tool carves). Closing only ever adds material, never removes it, and leaves peaks
alone. With ``milling.enforce_tool_limits`` the STL is replaced by that achievable surface;
either way the report says how much of the part the cutter cannot reach.

Everything here is millimetres; the report text converts back to the config's units.
"""

from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass

import numpy as np
from scipy import ndimage

from choppy_water.config import Config
from choppy_water.heightfield import Heightfield, footprint_mask, slope_degrees

# Extra material thinner than this (mm) is not worth reporting as "unreachable".
FILL_TOLERANCE_MM = 0.01
UNREACHABLE_WARN_FRACTION = 0.01


def close_with_ball(z: np.ndarray, radius: float, spacing: float) -> np.ndarray:
    """Surface left by a ball-nose cutter of ``radius`` (grey-scale closing of ``z``)."""
    n = int(radius // spacing)
    if n == 0:
        return z.copy()
    offsets = np.arange(-n, n + 1) * spacing
    dist2 = offsets[:, None] ** 2 + offsets[None, :] ** 2
    footprint = dist2 <= radius**2
    # Height of the ball's lower surface relative to its tip, at each offset (<= 0 form).
    profile = np.where(footprint, np.sqrt(np.maximum(radius**2 - dist2, 0.0)) - radius, 0.0)
    centre_height = ndimage.grey_dilation(z, footprint=footprint, structure=profile, mode="nearest")
    return ndimage.grey_erosion(
        centre_height, footprint=footprint, structure=profile, mode="nearest"
    )


def finishing_path_length(hf: Heightfield, cfg: Config, stepover: float) -> float:
    """3D length of a raster finishing pass along X, lines ``stepover`` apart (mm)."""
    height = cfg.part.extent[1]
    lines = np.arange(-height / 2, height / 2 + 1e-9, stepover)
    xs, ys = np.meshgrid(hf.x, lines)
    inside = footprint_mask(cfg.part, xs, ys)
    z = hf.sample(xs, ys, method="linear")
    segment = np.hypot(hf.spacing, np.diff(z, axis=1))
    both_inside = inside[:, :-1] & inside[:, 1:]
    return float(segment[both_inside].sum())


@dataclass(frozen=True)
class MillingReport:
    tool_diameter: float
    tool_limits_applied: bool
    unreachable_fraction: float  # share of the part where the cutter leaves extra material
    max_fill_depth: float
    filled_volume: float
    max_slope_deg: float
    steep_fraction: float  # share of the part steeper than milling.max_slope_deg
    stepover: float
    scallop_height: float  # cusp left between passes on a flat area
    finishing_path_length: float
    finishing_minutes: float
    roughing_layers: int
    deepest_cut_z: float  # lowest point of the milled surface (height above the bottom)
    top_z: float  # highest point of the milled surface
    stock_margin: float  # stock thickness minus top_z
    warnings: tuple[str, ...]


def plan_milling(config: Config, ideal: Heightfield) -> tuple[Heightfield, MillingReport]:
    """Return the heightfield as the cutter will leave it, plus a report on the job."""
    cfg = config.to_mm()
    ml = cfg.milling
    radius = ml.tool_diameter / 2
    mask = ideal.mask

    closed = close_with_ball(ideal.z, radius, ideal.spacing)
    extra = (closed - ideal.z)[mask]
    unreachable = float(np.mean(extra > FILL_TOLERANCE_MM))

    z = closed if ml.enforce_tool_limits else ideal.z
    stats = dataclasses.replace(
        ideal.stats,
        relief=float(np.ptp(z[mask])),
        max_slope_deg=float(slope_degrees(z, ideal.spacing)[mask].max()),
    )
    milled = dataclasses.replace(ideal, z=z, stats=stats)

    steep = float(np.mean(slope_degrees(z, ideal.spacing)[mask] > ml.max_slope_deg))
    stepover = ml.tool_diameter * ml.stepover_pct / 100
    scallop = radius - math.sqrt(radius**2 - (stepover / 2) ** 2)
    path = finishing_path_length(milled, cfg, stepover)
    z_in = z[mask]
    deepest = float(z_in.min())
    top = float(z_in.max())

    warnings = []
    if unreachable > UNREACHABLE_WARN_FRACTION:
        outcome = (
            "filled in the STL"
            if ml.enforce_tool_limits
            else "still in the STL (enforce_tool_limits is off)"
        )
        warnings.append(
            f"{unreachable:.1%} of the part is finer than the {ml.tool_diameter:.2f} mm cutter "
            f"can reach; those valleys are {outcome}"
        )
    if steep > 0:
        warnings.append(
            f"{steep:.1%} of the surface is steeper than {ml.max_slope_deg:g} deg; "
            "expect a rougher finish there (try a smaller tool or lower choppiness)"
        )
    if ideal.stats.unresolved_fraction > 0.01:
        warnings.append(
            f"surface folds over itself on {ideal.stats.unresolved_fraction:.1%} of the part; "
            "lower water.choppiness for clean crests"
        )

    report = MillingReport(
        tool_diameter=ml.tool_diameter,
        tool_limits_applied=ml.enforce_tool_limits,
        unreachable_fraction=unreachable,
        max_fill_depth=float(extra.max()),
        filled_volume=float(extra.sum() * ideal.spacing**2),
        max_slope_deg=stats.max_slope_deg,
        steep_fraction=steep,
        stepover=stepover,
        scallop_height=scallop,
        finishing_path_length=path,
        finishing_minutes=path / ml.feed_rate,
        roughing_layers=math.ceil((ml.stock_thickness - deepest) / ml.stepdown),
        deepest_cut_z=deepest,
        top_z=top,
        stock_margin=ml.stock_thickness - top,
        warnings=tuple(warnings),
    )
    return milled, report


def format_report(report: MillingReport, config: Config) -> str:
    """Human-readable milling summary in the config's length unit."""
    u = config.units.length
    s = 1 / config.mm_per_unit

    def length(mm: float, digits: int = 3) -> str:
        return f"{mm * s:.{digits}f} {u}"

    r, ml = report, config.milling
    action = "filled in the STL" if r.tool_limits_applied else "left in the STL"
    lines = [
        "CHOPPY WATER MILLING REPORT",
        "",
        "Setup",
        f"  Stock thickness:        {ml.stock_thickness:g} {u}",
        f"  Model height:           {length(r.deepest_cut_z)} (trough)"
        f" to {length(r.top_z)} (crest)",
        f"  Clearance under stock:  {length(r.stock_margin)} above the highest crest",
        "  Z zero:                 stock bottom (the model's flat bottom is z = 0)",
        "",
        "Tool",
        f"  Ball nose diameter:     {length(r.tool_diameter)}",
        f"  Valleys too fine to cut: {r.unreachable_fraction:.1%} of the part"
        f" (up to {length(r.max_fill_depth)} deep, {action})",
        f"  Steepest slope:         {r.max_slope_deg:.0f} deg"
        f" ({r.steep_fraction:.1%} of the part over {ml.max_slope_deg:g} deg)",
        "",
        "Finishing pass (raster along X)",
        f"  Stepover:               {length(r.stepover)} ({ml.stepover_pct:g}% of the tool)",
        f"  Scallop height (flat):  {length(r.scallop_height, 4)}",
        f"  Path length:            {r.finishing_path_length * s:.1f} {u}",
        f"  Estimated time:         {r.finishing_minutes:.0f} min at {ml.feed_rate:g} {u}/min",
        "",
        "Roughing",
        f"  Layers to clear:        {r.roughing_layers} at {ml.stepdown:g} {u} per pass",
        "",
        "Estimates cover the finishing pass only; they exclude roughing time, rapids,",
        "ramping and the profile cut that frees the part from the stock.",
    ]
    if r.warnings:
        lines += ["", "Warnings"] + [f"  - {w}" for w in r.warnings]
    return "\n".join(lines) + "\n"
