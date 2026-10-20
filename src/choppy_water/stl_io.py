"""Binary STL reading and writing (numpy only)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from choppy_water.config import MM_PER_INCH
from choppy_water.mesh import Solid

_RECORD = np.dtype([("normal", "<f4", 3), ("vertices", "<f4", (3, 3)), ("attribute", "<u2")])
_HEADER_BYTES = 80
_HEADER_TEXT = b"choppy-water binary STL"


def write_stl(solid: Solid, path: str | Path, units: str = "mm") -> Path:
    """Write ``solid`` (millimetres) as binary STL in ``units`` (``"mm"`` or ``"in"``)."""
    if units not in ("mm", "in"):
        raise ValueError(f"unsupported STL units: {units!r}")
    scale = 1.0 if units == "mm" else 1.0 / MM_PER_INCH
    tri = solid.triangles * scale

    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = np.divide(normals, length, out=np.zeros_like(normals), where=length > 0)

    records = np.zeros(len(tri), dtype=_RECORD)
    records["normal"] = normals
    records["vertices"] = tri

    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "wb") as fh:
        fh.write(_HEADER_TEXT.ljust(_HEADER_BYTES, b" "))
        fh.write(np.uint32(len(records)).tobytes())
        fh.write(records.tobytes())
    return out


def read_stl(path: str | Path) -> np.ndarray:
    """Read a binary STL into an ``(m, 3, 3)`` float32 array of triangle corners."""
    data = Path(path).read_bytes()
    if len(data) < _HEADER_BYTES + 4:
        raise ValueError("file is too short to be a binary STL")
    count = int(np.frombuffer(data, dtype="<u4", count=1, offset=_HEADER_BYTES)[0])
    expected = _HEADER_BYTES + 4 + count * _RECORD.itemsize
    if len(data) != expected:
        raise ValueError(f"binary STL size mismatch: expected {expected} bytes, got {len(data)}")
    records = np.frombuffer(data, dtype=_RECORD, count=count, offset=_HEADER_BYTES + 4)
    return records["vertices"].copy()
