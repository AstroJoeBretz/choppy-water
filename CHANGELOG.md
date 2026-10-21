# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- Optional `[water.chop]` layer: a second wave layer (own wavelengths, relief, choppiness,
  direction spread, seed) added on top of the main sea for composite swell-and-chop surfaces.
  `--set water.chop.relief=...` works from the command line. The `plaque` example demonstrates it.

### Changed
- Results are written to `output/<config name>/` (a folder per config) instead of a flat `output/`.
  `-o` now names the parent folder; set `output.stl_path` for an exact file. New `output.directory`.
- Examples: `stormy` replaced by `choppy_gerstner`; `plaque` is now a 6 x 3.5 in swell-and-chop plaque.
- `water.relief` is now the budget of its own layer; with a chop layer the reliefs add up and
  must together fit within `max_thickness - base_thickness`.

## [0.1.0] - 2026-10-19

First release.

### Added
- Disc or rectangular parts (`part.shape`), flat bottom, choppy-water top.
- Wave synthesis by FFT spectrum (Tessendorf-style) or Gerstner waves, with a choppiness control
  that sharpens crests, and detection of surfaces that fold over themselves.
- Watertight, outward-oriented binary STL export in mm or inches.
- Milling awareness: ball-nose reach (valleys narrower than the cutter), optional enforcement in
  the STL, slope check, scallop height, finishing time estimate, roughing layers, and a text report.
- TOML configuration with validation, typo suggestions, unit conversion and `--set` overrides;
  `--write-config` writes a commented default file.
- Shaded PNG preview and a JSON run record that reproduces the STL.
- Example presets: calm, choppy, stormy, plaque.
