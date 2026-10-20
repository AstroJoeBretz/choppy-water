# Project plan

## Goal

Python code that synthesizes a choppy-water heightfield and writes a watertight STL that can be
milled from wood. The piece is a thin **disc** or **rectangle**: flat bottom, choppy-water top.
All parameters are in a TOML config.

## Approach

A 3-axis mill can only cut single-valued surfaces z(x, y), so the model is a heightfield
(no overhangs).

- **Waves:** Tessendorf FFT ocean synthesis. A random spectrum is shaped by a Phillips/JONSWAP-like
  filter, an inverse FFT gives height `h(x, y)`, and a second FFT gives horizontal displacement `D`.
  Moving points by `choppiness * D` sharpens crests. The spectrum is defined in carver terms
  (wavelengths, spread, relief) and normalized to the requested relief.
- **Outline:** `part.shape` is `"disc"` (set `diameter`) or `"rect"` (set `width`, `length`).
  - Disc: interior samples plus a dense boundary ring, Delaunay-triangulated, with a cylindrical wall.
  - Rectangle: regular grid with four flat walls (optional corner radius is a stretch goal).
- **Milling workflow (assumed):** carve the top of the stock, then cut the outline free. The flat
  bottom is the stock underside. `max_thickness <= stock_thickness`.
- **Tool awareness:** a morphological pass fills valleys narrower than the cutter so the STL
  matches what can be cut. Slope and stock checks produce a report.

## Risks

- Choppiness can fold the surface over itself (negative Jacobian): cap it or z-buffer the top surface.
- Disc rim: avoid jagged edges from clipping a square grid; use boundary-ring triangulation.
- Reachability: ball-nose cutter cannot enter valleys narrower than itself.

## Repo layout

```
src/choppy_water/
  default.toml            commented defaults (kept in sync with code by a test)
  config.py               TOML -> typed dataclasses, validation, unit conversion
  cli.py                  command line
  spectrum.py             (Phase 1)
  heightfield.py          (Phase 1)
  mesh.py                 disc and rectangle solids, watertight check
  stl_io.py               binary STL writer/reader
  record.py               JSON run record next to the STL
  milling.py              tool-reach filter (closing), slope/stock checks, report
  preview.py              (Phase 1, optional matplotlib)
tests/
examples/
.github/workflows/ci.yml
```

## Phases

| Phase | Deliverable | Done when |
|---|---|---|
| 0. Scaffold (done) | Repo, `pyproject.toml`, config loader + validation (disc or rect), CLI skeleton, CI, license | `pytest` and `ruff` pass; bad configs give clear errors |
| 1. Heightfield (done) | Spectrum, FFT height field, choppiness, relief normalization, PNG preview | Same seed gives same surface; preview looks like choppy water |
| 2. Solid and STL (done) | Disc and rectangle meshes, flat bottom, walls, binary STL, unit handling | Watertight, outward normals, correct volume and bounding box for both shapes |
| 3. Milling awareness (done) | Tool-reachability filter, slope/stock checks, report | Warns or fixes features the cutter cannot make |
| 4. Polish, v0.1 (done) | README gallery, presets, docs, ~80% coverage | A stranger gets an STL in three commands |
| 5. Stretch | Time parameter, rim/bevel, rect corner radius, G-code, GUI | Optional |

## Testing

- Config: invalid/conflicting values rejected; inch <-> mm conversion; `default.toml` matches code defaults.
- Determinism: same seed and config give identical arrays.
- Spectrum: output relief equals config; dominant wavelength visible in a spectral check.
- Mesh (both shapes): every edge shared by exactly two triangles, positive volume, z within
  `[0, max_thickness]`, exactly flat bottom, disc/rect area matches the config.
- Milling: after the tool filter, no valley is narrower than the cutter.

## Assumptions

1. Default disc: 3 in diameter, 1 in stock, 0.25 in base, 0.5 in max thickness, 0.25 in relief.
2. Only the top is milled; the stock underside is the flat bottom.
3. STL written in mm by default (`output.stl_units`).
4. Machine/CAM unknown; tool defaults are generic (1/8 in ball nose, 16k rpm).
5. MIT license; G-code is out of scope for v0.1.
