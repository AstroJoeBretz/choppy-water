"""Sidecar JSON describing exactly how an STL was produced."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

from choppy_water import __version__
from choppy_water.config import Config
from choppy_water.heightfield import Heightfield
from choppy_water.mesh import Solid


def write_run_record(
    path: str | Path, config: Config, heightfield: Heightfield, solid: Solid
) -> Path:
    """Write ``path`` with the resolved config and the measured result.

    Feeding the ``config`` block back through ``load_config`` reproduces the same STL.
    """
    low, high = solid.bounds
    record = {
        "choppy_water_version": __version__,
        "config": config.to_dict(),
        "surface": dataclasses.asdict(heightfield.stats),
        "mesh": {
            "vertices": len(solid.vertices),
            "triangles": len(solid.faces),
            "watertight": solid.is_watertight,
            "volume_mm3": round(solid.volume(), 3),
            "bounds_min_mm": [round(float(v), 4) for v in low],
            "bounds_max_mm": [round(float(v), 4) for v in high],
        },
    }
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return out
