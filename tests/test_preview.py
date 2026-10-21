import pytest

from choppy_water.config import load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.preview import save_preview

pytest.importorskip("matplotlib")


def test_preview_is_rgba_with_transparent_corners(tmp_path):
    from matplotlib import image

    hf = generate_heightfield(load_config(None, ["mesh.grid_spacing=0.04"]))
    out = save_preview(hf, tmp_path / "nested" / "p.png")
    img = image.imread(out)
    assert img.shape == (*hf.z.shape, 4)
    assert img[0, 0, 3] == 0  # corner is outside the disc
    assert img[hf.z.shape[0] // 2, hf.z.shape[1] // 2, 3] == 1


def test_3d_preview_is_a_transparent_png_with_content(tmp_path):
    from matplotlib import image

    from choppy_water.preview import save_preview_3d

    hf = generate_heightfield(load_config(None, ["mesh.grid_spacing=0.04"]))
    out = save_preview_3d(hf, tmp_path / "deep" / "p3d.png")
    img = image.imread(out)
    assert img.ndim == 3 and img.shape[2] == 4
    assert img[..., 3].max() == 1.0  # surface pixels
    assert img[0, 0, 3] == 0  # transparent background
    assert 0.05 < (img[..., 3] > 0).mean() < 0.9  # neither empty nor full frame
