"""Regenerate the README gallery: top-down and 3D preview PNGs for every built-in example.

Run from the repository root:  python scripts/make_gallery.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from choppy_water.config import example_names, example_text, load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.milling import plan_milling
from choppy_water.preview import save_preview, save_preview_3d

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    out_dir = ROOT / "docs" / "images"
    for name in example_names():
        config = load_config(text=example_text(name))
        hf, report = plan_milling(config, generate_heightfield(config))
        top = save_preview(hf, out_dir / f"{name}.png")
        view = save_preview_3d(hf, out_dir / f"{name}_3d.png")
        print(f"{name}: {top.relative_to(ROOT)}, {view.relative_to(ROOT)}")
        for warning in report.warnings:
            print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
