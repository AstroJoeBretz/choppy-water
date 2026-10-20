import numpy as np
import pytest

from choppy_water.config import MM_PER_INCH
from choppy_water.mesh import Solid
from choppy_water.stl_io import read_stl, write_stl


@pytest.fixture
def tetra():
    vertices = np.array([[0, 0, 0], [10, 0, 0], [0, 10, 0], [0, 0, 10]], dtype=float)
    faces = np.array([[0, 2, 1], [0, 1, 3], [0, 3, 2], [1, 2, 3]])  # outward winding
    return Solid(vertices=vertices, faces=faces)


def test_fixture_is_a_valid_outward_solid(tetra):
    assert tetra.is_watertight
    assert tetra.volume() == pytest.approx(1000 / 6)


def test_binary_layout_and_roundtrip(tmp_path, tetra):
    path = write_stl(tetra, tmp_path / "sub" / "t.stl")
    raw = path.read_bytes()
    assert len(raw) == 80 + 4 + 50 * 4
    assert int.from_bytes(raw[80:84], "little") == 4
    assert not raw.startswith(b"solid")  # some readers mistake that for ASCII STL
    assert np.array_equal(read_stl(path), tetra.triangles.astype(np.float32))


def test_normals_are_unit_length_and_outward(tmp_path, tetra):
    path = write_stl(tetra, tmp_path / "t.stl")
    records = np.frombuffer(
        path.read_bytes()[84:],
        dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]),
    )
    assert np.allclose(np.linalg.norm(records["n"], axis=1), 1.0)
    centroid = tetra.vertices.mean(axis=0)
    face_centres = records["v"].mean(axis=1)
    assert ((face_centres - centroid) * records["n"]).sum(axis=1).min() > 0


def test_inch_output_scales_coordinates(tmp_path, tetra):
    path = write_stl(tetra, tmp_path / "t.stl", units="in")
    assert read_stl(path).max() == pytest.approx(10 / MM_PER_INCH, rel=1e-6)


def test_unknown_units_rejected(tmp_path, tetra):
    with pytest.raises(ValueError, match="units"):
        write_stl(tetra, tmp_path / "t.stl", units="cm")


def test_read_rejects_truncated_file(tmp_path, tetra):
    path = write_stl(tetra, tmp_path / "t.stl")
    path.write_bytes(path.read_bytes()[:-10])
    with pytest.raises(ValueError, match="size mismatch"):
        read_stl(path)
    path.write_bytes(b"short")
    with pytest.raises(ValueError, match="too short"):
        read_stl(path)


def test_degenerate_triangle_gets_zero_normal_not_nan(tmp_path):
    flat = Solid(
        vertices=np.array([[0, 0, 0], [1, 0, 0], [2, 0, 0]], dtype=float),
        faces=np.array([[0, 1, 2]]),
    )
    path = write_stl(flat, tmp_path / "d.stl")
    normal = np.frombuffer(path.read_bytes()[84:96], dtype="<f4")
    assert (normal == 0).all()
