"""Regenerate the README gallery: one preview PNG per example config.

Run from the repository root:  python scripts/make_gallery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from choppy_water.config import load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.milling import plan_milling
from choppy_water.preview import save_preview

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out_dir = ROOT / "docs" / "images"
    for config_path in sorted((ROOT / "examples").glob("*.toml")):
        config = load_config(config_path)
        hf, report = plan_milling(config, generate_heightfield(config))
        png = save_preview(hf, out_dir / f"{config_path.stem}.png")
        print(f"{config_path.name}: {png.relative_to(ROOT)}")
        for warning in report.warnings:
            print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
