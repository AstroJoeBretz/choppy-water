# Changelog

All notable changes are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] - 2026-10-21

First release.

### Added
- Disc or rectangular parts (`part.shape`), flat bottom, choppy-water top.
- Wave synthesis by FFT spectrum (Tessendorf-style) or Gerstner waves, with a choppiness control
  that sharpens crests, and detection of surfaces that fold over themselves.
- Optional `[water.chop]` layer: a second wave layer (own wavelengths, relief, choppiness,
  direction spread, seed) added on top of the main sea for swell-and-chop surfaces.
- Watertight, outward-oriented binary STL export in mm or inches.
- Milling awareness: ball-nose reach (valleys narrower than the cutter), optional enforcement in
  the STL, slope check, scallop height, finishing time estimate, roughing layers, and a text report.
- TOML configuration with validation, typo suggestions, unit conversion and `--set` overrides;
  `--write-config` writes a commented default file.
- Each run writes to `output/<config name>/`: the STL, top-down and 3D PNG previews, the milling
  report and a JSON run record. `choppy-water --config <name>.json` reproduces a run exactly.
- Built-in examples packaged with the tool: `calm`, `choppy`, `choppy_gerstner`, `plaque` (a
  6 x 3.5 in swell-and-chop plaque). `--list-examples` and `--example NAME`.
- Progress messages while generating. A missing matplotlib skips the previews with a warning
  instead of failing.
- Documentation: README with the generation method and limitations, configuration reference,
  milling guide and architecture notes.
