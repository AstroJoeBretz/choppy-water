"""PNG previews of the surface (need the optional ``matplotlib`` dependency)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from choppy_water.heightfield import Heightfield

# Samples across the part in the 3D view: enough to look smooth, few enough to render quickly.
VIEW_3D_SAMPLES = 170


def _matplotlib():
    """Import matplotlib lazily (headless backend) or explain how to install it."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        from matplotlib import pyplot as plt
        from matplotlib.colors import LightSource
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("previews need matplotlib: pip install 'choppy-water[preview]'") from exc
    return plt, LightSource


def save_preview(hf: Heightfield, path: str | Path, vert_exag: float = 1.0) -> Path:
    """Top-down lit, wood-toned view of the surface; pixels outside the outline are transparent."""
    plt, light_source = _matplotlib()
    light = light_source(azdeg=315, altdeg=40)
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


def save_preview_3d(
    hf: Heightfield, path: str | Path, vert_exag: float = 1.0, elev: float = 35, azim: float = -58
) -> Path:
    """Angled 3D view of the surface at true proportions (``vert_exag`` scales heights)."""
    plt, light_source = _matplotlib()
    step = max(1, round(hf.z.shape[1] / VIEW_3D_SAMPLES))
    z = hf.z[::step, ::step]
    mask = hf.mask[::step, ::step]
    x, y = np.meshgrid(hf.x[::step], hf.y[::step])

    light = light_source(azdeg=315, altdeg=40)
    colors = light.shade(
        z,
        cmap=plt.get_cmap("copper"),
        blend_mode="soft",
        vert_exag=vert_exag,
        dx=hf.spacing * step,
        dy=hf.spacing * step,
    )
    z_plot = np.where(mask, z, np.nan)  # leave out the padding around the outline

    fig = plt.figure(figsize=(6.4, 4.8), dpi=150)
    ax = fig.add_subplot(projection="3d")
    ax.plot_surface(
        x, y, z_plot, facecolors=colors, rstride=1, cstride=1, linewidth=0, antialiased=False,
        shade=False,
    )  # fmt: skip
    ax.set_box_aspect((np.ptp(x[mask]), np.ptp(y[mask]), max(np.ptp(z[mask]) * vert_exag, 1e-6)))
    ax.view_init(elev=elev, azim=azim)
    ax.set_axis_off()

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, transparent=True, bbox_inches="tight", pad_inches=0.05)
    plt.close(fig)
    return out
