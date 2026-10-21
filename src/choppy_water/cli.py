"""Command-line interface."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from choppy_water import __version__
from choppy_water.config import Config, ConfigError, default_config_text, load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.mesh import build_solid
from choppy_water.milling import format_report, plan_milling
from choppy_water.preview import save_preview
from choppy_water.record import write_run_record
from choppy_water.stl_io import write_stl


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="choppy-water",
        description="Generate a choppy-water surface as an STL for CNC milling.",
    )
    parser.add_argument("-c", "--config", help="path to a TOML config (defaults if omitted)")
    parser.add_argument(
        "-s",
        "--set",
        dest="overrides",
        action="append",
        default=[],
        metavar="SECTION.KEY=VALUE",
        help="override a config value, e.g. --set water.choppiness=1.4 (repeatable)",
    )
    parser.add_argument("--seed", type=int, help="shortcut for --set water.seed=N")
    parser.add_argument(
        "-o",
        "--output",
        metavar="DIR",
        help="parent folder for results (shortcut for --set output.directory=DIR); "
        "files go in DIR/<config name>/. Default: output",
    )
    parser.add_argument("--check", action="store_true", help="validate the configuration and exit")
    parser.add_argument(
        "--show-config", action="store_true", help="print the resolved configuration as JSON"
    )
    parser.add_argument(
        "--write-config",
        metavar="PATH",
        help="write a commented copy of the default config to PATH and exit",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


DEFAULT_RUN_NAME = "choppy_water"


def resolve_stl_path(config: Config, config_path: str | Path | None) -> Path:
    """Where the STL goes: ``output.stl_path`` if set, else ``<directory>/<name>/<name>.stl``.

    ``name`` is the config file's name without extension (``choppy_water`` with no file), so
    each config gets its own folder holding the STL, preview, report and run record.
    """
    if config.output.stl_path:
        return Path(config.output.stl_path)
    name = Path(config_path).stem if config_path else DEFAULT_RUN_NAME
    return Path(config.output.directory) / name / f"{name}.stl"


def describe(config: Config, stl_path: Path) -> str:
    """One-screen human summary of what the config describes."""
    u = config.units.length
    p, w, ml = config.part, config.water, config.milling
    if p.shape == "disc":
        outline = f"disc, diameter {p.diameter:g} {u}"
    else:
        outline = f"rectangle, {p.width:g} x {p.length:g} {u}"
    return "\n".join(
        [
            f"Part:    {outline}",
            f"         thickness {p.base_thickness:g} to {p.max_thickness:g} {u}"
            f" (stock {ml.stock_thickness:g} {u})",
            f"Water:   method {w.method}, seed {w.seed}, relief {w.relief:g} {u},"
            f" choppiness {w.choppiness:g}",
            *(
                [
                    f"Chop:    method {c.method}, relief {c.relief:g} {u},"
                    f" choppiness {c.choppiness:g}, wavelengths {c.wavelength_min:g}"
                    f" to {c.wavelength_max:g} {u}"
                ]
                if (c := config.chop) is not None
                else []
            ),
            f"Tool:    {ml.tool_type} nose, {ml.tool_diameter:g} {u} diameter",
            f"Output:  {stl_path} ({config.output.stl_units})",
        ]
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.write_config:
        target = Path(args.write_config)
        if target.exists():
            print(f"error: {target} already exists; not overwriting", file=sys.stderr)
            return 1
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(default_config_text(), encoding="utf-8")
        print(f"Wrote {target}")
        return 0
    overrides = list(args.overrides)
    if args.seed is not None:
        overrides.append(f"water.seed={args.seed}")
    if args.output is not None:
        if args.output.lower().endswith(".stl"):
            print(
                "error: -o now takes a folder, and results go in a subfolder named after the "
                "config. For an exact file use --set output.stl_path=PATH",
                file=sys.stderr,
            )
            return 1
        overrides.append(f"output.directory={json.dumps(args.output)}")

    try:
        config = load_config(args.config, overrides)
    except ConfigError as exc:
        print(exc, file=sys.stderr)
        return 1

    stl_path = resolve_stl_path(config, args.config)
    if args.show_config:
        print(json.dumps(config.to_dict(), indent=2))
    else:
        print(describe(config, stl_path))
    for note in config.warnings():
        print(f"warning: {note}", file=sys.stderr)

    if args.check:
        print("Configuration OK.")
        return 0

    try:
        ideal = generate_heightfield(config)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    hf, report = plan_milling(config, ideal)
    print(
        f"Surface: {hf.z.shape[1]} x {hf.z.shape[0]} grid, relief {hf.stats.relief:.2f} mm, "
        f"steepest slope {hf.stats.max_slope_deg:.0f} deg"
    )
    for note in report.warnings:
        print(f"warning: {note}", file=sys.stderr)

    solid = build_solid(config, hf)
    if not solid.is_watertight:  # a bug, not a user error; never hand a broken STL to a CAM tool
        print("error: internal error: generated mesh is not watertight", file=sys.stderr)
        return 1
    write_stl(solid, stl_path, config.output.stl_units)
    write_run_record(stl_path.with_suffix(".json"), config, hf, solid, report)
    report_path = stl_path.with_name(stl_path.stem + "_milling.txt")
    report_path.write_text(format_report(report, config), encoding="utf-8")
    low, high = solid.bounds
    size = high - low
    print(
        f"Mesh:    {len(solid.faces):,} triangles,"
        f" {size[0]:.1f} x {size[1]:.1f} x {size[2]:.1f} mm,"
        f" volume {solid.volume() / 1000:.1f} cm^3"
    )
    print(f"STL:     {stl_path} ({config.output.stl_units})")
    print(f"Report:  {report_path}")
    print(
        f"Milling: ~{report.finishing_minutes:.0f} min finishing pass,"
        f" {report.unreachable_fraction:.1%} of the part finer than the cutter"
    )

    if config.output.preview:
        try:
            png = save_preview(hf, stl_path.with_suffix(".png"))
        except RuntimeError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"Preview: {png}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
