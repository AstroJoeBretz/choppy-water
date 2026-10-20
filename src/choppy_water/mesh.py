"""Watertight solid for the milled piece: choppy top, flat bottom, vertical walls.

The solid is a closed triangle mesh with outward-facing normals (counter-clockwise winding
seen from outside). Millimetres throughout; call with ``config`` in any length unit.

* **Top surface.** A disc uses a hexagonal point lattice plus a dense boundary ring,
  Delaunay-triangulated; a rectangle uses a regular grid whose edges land exactly on the
  outline. Heights come from the heightfield.
* **Walls** join the top boundary loop to a copy of it at ``z = 0``.
* **Bottom** is a flat fan from the centre to that lower loop.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
from scipy.spatial import Delaunay

from choppy_water.config import Config, Part
from choppy_water.heightfield import Heightfield


@dataclass(frozen=True)
class Solid:
    """Indexed triangle mesh: ``faces`` index rows of ``vertices``."""

    vertices: np.ndarray  # (n, 3) float64, mm
    faces: np.ndarray  # (m, 3) int64

    @property
    def triangles(self) -> np.ndarray:
        """Per-face corner coordinates, shape ``(m, 3, 3)``."""
        return self.vertices[self.faces]

    @property
    def bounds(self) -> tuple[np.ndarray, np.ndarray]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def volume(self) -> float:
        """Enclosed volume from the divergence theorem (positive for outward winding)."""
        a, b, c = self.triangles.transpose(1, 0, 2)
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    def edge_defects(self) -> int:
        """Directed edges that are duplicated or lack an opposite partner.

        Zero means every edge is shared by exactly two faces that traverse it in opposite
        directions: a closed, consistently oriented surface.
        """
        f = self.faces
        a = np.concatenate([f[:, 0], f[:, 1], f[:, 2]]).astype(np.int64)
        b = np.concatenate([f[:, 1], f[:, 2], f[:, 0]]).astype(np.int64)
        n = len(self.vertices)
        forward = a * n + b
        reverse = b * n + a
        unique, counts = np.unique(forward, return_counts=True)
        duplicated = int((counts > 1).sum())
        unmatched = int((~np.isin(unique, reverse)).sum())
        return duplicated + unmatched

    @property
    def is_watertight(self) -> bool:
        return self.edge_defects() == 0

    def min_triangle_area(self) -> float:
        a, b, c = self.triangles.transpose(1, 0, 2)
        return float((np.linalg.norm(np.cross(b - a, c - a), axis=1) / 2).min())


@dataclass(frozen=True)
class _Surface:
    """Planar triangulation of the outline: points, CCW triangles, CCW boundary loop."""

    xy: np.ndarray
    triangles: np.ndarray
    boundary: np.ndarray


def _orient_ccw(xy: np.ndarray, tri: np.ndarray) -> np.ndarray:
    p = xy[tri]
    cross = (p[:, 1, 0] - p[:, 0, 0]) * (p[:, 2, 1] - p[:, 0, 1]) - (p[:, 1, 1] - p[:, 0, 1]) * (
        p[:, 2, 0] - p[:, 0, 0]
    )
    flipped = tri.copy()
    flipped[cross < 0] = tri[cross < 0][:, ::-1]
    return flipped


def _disc_surface(diameter: float, spacing: float, edge_segments: int) -> _Surface:
    radius = diameter / 2
    angles = 2 * math.pi * np.arange(edge_segments) / edge_segments
    ring = np.column_stack([radius * np.cos(angles), radius * np.sin(angles)])

    # Hexagonal lattice, kept clear of the ring so no sliver triangles form against it.
    row_height = spacing * math.sqrt(3) / 2
    rows = int(radius / row_height) + 1
    points = []
    for j in range(-rows, rows + 1):
        cols = int(radius / spacing) + 2
        x = (np.arange(-cols, cols + 1) + 0.5 * (j % 2)) * spacing
        points.append(np.column_stack([x, np.full_like(x, j * row_height)]))
    lattice = np.concatenate(points)
    lattice = lattice[np.hypot(lattice[:, 0], lattice[:, 1]) <= radius - 0.5 * spacing]

    xy = np.concatenate([ring, lattice])
    tri = _orient_ccw(xy, Delaunay(xy).simplices)
    return _Surface(xy=xy, triangles=tri, boundary=np.arange(edge_segments))


def _rect_surface(width: float, length: float, spacing: float) -> _Surface:
    nx, ny = max(1, math.ceil(width / spacing)), max(1, math.ceil(length / spacing))
    xs = np.linspace(-width / 2, width / 2, nx + 1)
    ys = np.linspace(-length / 2, length / 2, ny + 1)
    gx, gy = np.meshgrid(xs, ys)
    xy = np.column_stack([gx.ravel(), gy.ravel()])

    i, j = np.meshgrid(np.arange(nx), np.arange(ny))
    i, j = i.ravel(), j.ravel()
    a = j * (nx + 1) + i
    b, c, d = a + 1, a + nx + 2, a + nx + 1
    even = (i + j) % 2 == 0  # alternate the diagonal so the grid has no directional bias
    tri = np.concatenate(
        [
            np.column_stack([a, b, c])[even],
            np.column_stack([a, c, d])[even],
            np.column_stack([a, b, d])[~even],
            np.column_stack([b, c, d])[~even],
        ]
    )

    def index(ii: np.ndarray, jj: np.ndarray) -> np.ndarray:
        return jj * (nx + 1) + ii

    boundary = np.concatenate(
        [
            index(np.arange(0, nx), np.zeros(nx, int)),  # bottom edge, left to right
            index(np.full(ny, nx), np.arange(0, ny)),  # right edge, upward
            index(np.arange(nx, 0, -1), np.full(nx, ny)),  # top edge, right to left
            index(np.zeros(ny, int), np.arange(ny, 0, -1)),  # left edge, downward
        ]
    )
    return _Surface(xy=xy, triangles=tri, boundary=boundary)


def _surface_for(part: Part, spacing: float, edge_segments: int) -> _Surface:
    if part.shape == "disc":
        return _disc_surface(part.diameter, spacing, edge_segments)
    return _rect_surface(part.width, part.length, spacing)


def build_solid(config: Config, heightfield: Heightfield) -> Solid:
    """Close the heightfield into a printable/millable solid (millimetres)."""
    cfg = config.to_mm()
    part = cfg.part
    surface = _surface_for(part, cfg.mesh.grid_spacing, cfg.mesh.edge_segments)

    # Cubic sampling can overshoot a crest by a hair; clamp so the part stays inside its stock.
    top_z = np.clip(
        heightfield.sample(surface.xy[:, 0], surface.xy[:, 1], method="cubic"),
        part.base_thickness,
        part.base_thickness + cfg.total_relief,
    )
    n_top = len(surface.xy)
    top = np.column_stack([surface.xy, top_z])

    loop = surface.boundary
    m = len(loop)
    lower = np.column_stack([surface.xy[loop], np.zeros(m)])
    lower_index = n_top + np.arange(m)
    centre_index = n_top + m
    vertices = np.concatenate([top, lower, [[0.0, 0.0, 0.0]]])

    nxt = np.roll(np.arange(m), -1)
    t0, t1 = loop, loop[nxt]
    b0, b1 = lower_index, lower_index[nxt]
    walls = np.concatenate(
        [np.column_stack([b0, b1, t1]), np.column_stack([b0, t1, t0])]
    )  # counter-clockwise seen from outside
    bottom = np.column_stack([np.full(m, centre_index), b1, b0])  # facing down

    faces = np.concatenate([surface.triangles, walls, bottom]).astype(np.int64)
    return Solid(vertices=vertices, faces=faces)
