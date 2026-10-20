import numpy as np
import pytest

from choppy_water.config import load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.mesh import Solid, build_solid

MM = 25.4
# Coarse grid for speed; rim spacing is kept close to the grid spacing (pi*3in/235 ~ 0.04in).
FAST = ["mesh.grid_spacing=0.04", "mesh.edge_segments=235"]

SHAPES = {
    "disc": [],
    "rect": ["part.shape='rect'", "part.width=4", "part.length=2.5"],
}


@pytest.fixture(scope="module", params=sorted(SHAPES))
def built(request):
    cfg = load_config(None, [*FAST, *SHAPES[request.param]])
    hf = generate_heightfield(cfg)
    return request.param, cfg, hf, build_solid(cfg, hf)


def test_solid_is_closed_and_consistently_oriented(built):
    _, _, _, solid = built
    assert solid.edge_defects() == 0
    assert solid.is_watertight


def test_trimesh_agrees_the_solid_is_a_valid_volume(built):
    trimesh = pytest.importorskip("trimesh")
    _, _, _, solid = built
    mesh = trimesh.Trimesh(solid.vertices, solid.faces, process=False)
    assert mesh.is_watertight
    assert mesh.is_winding_consistent
    assert mesh.is_volume
    assert mesh.volume > 0  # positive volume means the normals point outward
    assert mesh.volume == pytest.approx(solid.volume())


def test_volume_matches_the_heightfield(built):
    _, _, hf, solid = built
    # Integrate the grid over the footprint (rough: the mask is a staircase of the outline).
    expected = hf.z[hf.mask].mean() * hf.mask.sum() * hf.spacing**2
    assert solid.volume() == pytest.approx(expected, rel=0.03)


def test_bottom_is_flat_and_top_stays_inside_the_stock(built):
    _, cfg, _, solid = built
    z = solid.vertices[:, 2]
    assert z.min() == 0.0
    assert (z == 0.0).sum() >= 2  # a real bottom face, not just one point
    assert z.max() <= cfg.part.max_thickness * MM + 1e-9
    assert z.max() <= cfg.milling.stock_thickness * MM
    top = z[z > 0]
    assert top.min() >= cfg.part.base_thickness * MM - 1e-9


def test_outline_has_the_requested_size(built):
    shape, cfg, _, solid = built
    low, high = solid.bounds
    if shape == "disc":
        assert high[0] - low[0] == pytest.approx(cfg.part.diameter * MM, rel=1e-3)
        assert high[1] - low[1] == pytest.approx(cfg.part.diameter * MM, rel=1e-3)
        radii = np.hypot(solid.vertices[:, 0], solid.vertices[:, 1])
        assert radii.max() == pytest.approx(cfg.part.diameter * MM / 2)
    else:
        assert low[0] == pytest.approx(-cfg.part.width * MM / 2)
        assert high[0] == pytest.approx(cfg.part.width * MM / 2)
        assert low[1] == pytest.approx(-cfg.part.length * MM / 2)
        assert high[1] == pytest.approx(cfg.part.length * MM / 2)


def test_no_degenerate_triangles(built):
    _, cfg, _, solid = built
    spacing = cfg.mesh.grid_spacing * MM
    assert solid.min_triangle_area() > 0.002 * spacing**2


def test_top_faces_point_up_and_wall_faces_point_outward(built):
    _, _, _, solid = built
    a, b, c = solid.triangles.transpose(1, 0, 2)
    normal = np.cross(b - a, c - a)
    area_up = normal[:, 2][normal[:, 2] > 0].sum() / 2  # projected area of upward faces
    area_down = -normal[:, 2][normal[:, 2] < 0].sum() / 2
    # The top surface projects onto the footprint once, and so does the flat bottom.
    assert area_up > 0.99 * area_down
    bottom = np.isclose(solid.triangles[:, :, 2], 0).all(axis=1)
    assert (normal[bottom, 2] < 0).all()


def test_removing_a_face_is_detected_as_a_defect(built):
    _, _, _, solid = built
    holed = Solid(vertices=solid.vertices, faces=solid.faces[1:])
    assert holed.edge_defects() > 0
    assert not holed.is_watertight


def test_flipping_a_face_is_detected_as_a_defect(built):
    _, _, _, solid = built
    faces = solid.faces.copy()
    faces[0] = faces[0][::-1]
    assert Solid(vertices=solid.vertices, faces=faces).edge_defects() > 0


def test_heightfield_sampling_outside_the_grid_is_rejected():
    hf = generate_heightfield(load_config(None, FAST))
    with pytest.raises(ValueError, match="outside"):
        hf.sample(np.array([hf.x[-1] + 1.0]), np.array([0.0]))


def test_cubic_and_linear_sampling_agree_on_grid_nodes():
    hf = generate_heightfield(load_config(None, FAST))
    x, y = hf.x[[10, 40, 70]], hf.y[[20, 35, 60]]
    assert hf.sample(x, y, "cubic") == pytest.approx(hf.sample(x, y, "linear"))
