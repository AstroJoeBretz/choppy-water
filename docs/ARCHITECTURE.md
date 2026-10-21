# How it works

This page explains the method and the code layout. For using the tool, see the
[README](../README.md) and the [configuration reference](CONFIG.md).

## The idea

A 3-axis mill can only cut a surface that has one height at each (x, y), so the model is a
**heightfield** `z(x, y)` on top of a flat bottom, with no overhangs. The pipeline is:

```
config (TOML)
   |
   v
wave layers ---- spectrum -> FFT or Gerstner waves -> choppy warp -> normalize   (one per layer)
   |
   v
sum layers -> stretch to total relief -> heightfield on a regular grid
   |
   v
ball-nose reach (closing)  ->  milling report (slope, scallop, time, layers)
   |
   v
mesh: top surface + walls + flat bottom  ->  STL, previews, run record
```

## 1. Wave spectrum

The shape of the sea is a random-wave spectrum, described in carver-friendly terms
(wavelengths, direction spread, relief) rather than wind speed and fetch. The height energy
per unit wavenumber follows the Phillips saturation form,

```
E(k) ~ k^-3 * exp(-1.5 (k_peak / k)^2)
```

which peaks at the dominant wavelength and falls off as `k^-3` toward shorter waves, multiplied
by smooth band limits so nothing falls outside `[wavelength_min, wavelength_max]`. The 2D
spectrum is `P(kx, ky) = E(k) / k * D(theta)`, where `D` is a wrapped Gaussian around the wind
direction whose width is `directional_spread_deg`. The overall amplitude is arbitrary here: each
layer is later scaled to the relief you ask for.

## 2. Two ways to make waves

- **FFT (`method = "fft"`, the default).** This is Tessendorf-style ocean synthesis. Random
  complex Gaussian numbers are scaled by `sqrt(P)` and inverse-FFT'd to a height field on a
  periodic patch (`water.patch_size`, on an FFT-friendly grid size). A second transform gives
  the horizontal displacement `D = IFFT(-i k/|k| * h(k))` used for choppiness. Fields are
  sampled with cubic splines.
- **Gerstner (`method = "gerstner"`).** A sum of 64 sine waves with log-spaced wavenumbers,
  directions drawn around the wind direction, random phases and amplitudes taken from the same
  spectrum. Each wave carries its own Gerstner horizontal displacement. It is slightly more
  regular and cheaper than FFT.

Both are deterministic: the same seed and settings give the same surface.

## 3. Choppiness

Real choppy water has sharp crests and broad troughs. The standard trick is to move every surface
point horizontally toward the crests: `x = x0 - c * D(x0)`, where `c` is `water.choppiness`
scaled so it means the same thing at any relief. Around `c = 1` the crests become cusps; beyond
that the surface folds over itself.

The mill needs height at regular grid points, not at moved points, so the mapping is inverted:
for every output grid point `x` the code solves `x0 = x + c * D(x0)` by fixed-point iteration
(up to 40 steps) and reads `h(x0)`. Where the surface folds, the iteration cannot converge and
that share of the part is reported as "folds over itself" so you can lower the choppiness.

## 4. Layers

`[water]` is always the first layer. The optional `[water.chop]` is a second, independently
generated layer. Each layer is warped separately (so chop keeps sharp crests even on a calm
swell), scaled so its peak-to-peak height over the part equals its own relief, and the layers are
added. The sum is then stretched to exactly the combined relief, because crests of the two
layers rarely line up, and offset so the lowest point sits at `part.base_thickness`.

## 5. What the cutter can actually cut

A ball-nose cutter cannot enter a valley narrower than itself. The surface it leaves is the
**grey-scale morphological closing** of the ideal surface by the ball's profile: dilate (where
the tool centre may go), then erode (what the swept tool carves). Closing only adds material,
never removes it, and leaves peaks alone. With `milling.enforce_tool_limits` the STL is replaced
by that surface; either way the report says how much of the part the cutter cannot reach. The
height grid is padded by the cutter radius so there is no artificial edge at the outline. The
closing is verified against the analytic depth a ball reaches in a trench.

The report also gives slope statistics, the scallop height between passes
(`r - sqrt(r^2 - (stepover/2)^2)`), a finishing-pass path length and time estimate (a raster along
X over the actual 3D surface), and the roughing layer count.

## 6. The solid

- **Disc:** interior points on a hexagonal lattice plus a dense boundary ring, Delaunay
  triangulated, so the rim is round rather than jagged.
- **Rectangle:** a regular grid whose edges land exactly on the outline.
- **Walls** join the top boundary loop to a copy at z = 0, and the **bottom** is a flat fan.

Heights at mesh vertices come from cubic interpolation of the grid, clamped to the thickness
budget. The mesh is checked to be closed and consistently oriented (every directed edge has
exactly one opposite partner) before anything is written, and the volume is positive, so normals
point outward.

## Code layout

```
src/choppy_water/
  config.py       TOML -> typed dataclasses, validation, unit conversion, packaged examples
  default.toml    commented defaults (a test keeps it in sync with the code)
  examples/       the built-in example configs (calm, choppy, choppy_gerstner, plaque)
  spectrum.py     the wave spectrum
  heightfield.py  FFT and Gerstner wave fields, choppy warp, layers, grid, sampling
  milling.py      ball-nose reach (closing), slope/stock checks, milling report
  mesh.py         disc and rectangle solids, watertight check
  stl_io.py       binary STL writer and reader
  record.py       JSON run record written next to the STL
  preview.py      top-down and 3D PNG previews (optional matplotlib)
  cli.py          command line
tests/            pytest suite (config, waves, mesh, STL, milling, CLI, docs guards)
scripts/          make_gallery.py regenerates docs/images
```

## Design decisions and assumptions

1. Heightfield only: no overhangs, so the part is millable on a 3-axis machine.
2. Only the top is milled; the stock underside is the flat bottom, and the outline is cut free
   afterwards. `part.max_thickness` must not exceed `milling.stock_thickness`.
3. STL is written in mm by default (`output.stl_units`); STL files carry no unit.
4. Machine and CAM software are unknown, so tool defaults are generic (1/8 in ball nose).
5. Quantities that depend on grid resolution (tool reach) assume at least about ten grid cells
   across the cutter; the config warns when the grid is coarser.

## Testing

Unit tests cover config validation, unit conversion, determinism by seed, the spectrum, the choppy
warp (single-wave sharpening and inversion against the forward map), both outline shapes (closed
mesh, volume, flat bottom, stock limits, exact outline), the STL layout, tool reach (analytic
trench), the CLI, and guards that keep the docs, examples and version in sync with the code.

## Roadmap ideas

Not planned for the first release: a time parameter for different frozen moments of the same sea,
a raised rim or bevel, rounded rectangle corners, G-code output, a simple GUI.

## References

- Jerry Tessendorf, *Simulating Ocean Water* (SIGGRAPH course notes, 2001): FFT ocean spectrum and
  choppy-wave displacement.
- Gerstner waves (trochoidal waves), as used in real-time water rendering.
- O. M. Phillips, equilibrium range of wind-wave spectra (the `k^-3` saturation form).
