"""Shaded-relief PNG preview (needs the optional ``matplotlib`` dependency)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from choppy_water.heightfield import Heightfield


def save_preview(hf: Heightfield, path: str | Path, vert_exag: float = 1.0) -> Path:
    """Render a lit, wood-toned view of the surface; pixels outside the outline are transparent."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        from matplotlib.colors import LightSource
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("previews need matplotlib: pip install 'choppy-water[preview]'") from exc

    light = LightSource(azdeg=315, altdeg=40)
    rgba = light.shade(
        hf.z,
        cmap=plt.get_cmap("copper"),
        blend_mode="soft",
        vert_exag=vert_exag,
        dx=hf.spacing,
        dy=hf.spacing,
    )
    rgba[..., 3] = np.where(hf.mask, 1.0, 0.0)

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    # origin="lower" puts +y up; one image pixel per grid cell.
    plt.imsave(out, rgba, origin="lower")
    return out
