# choppy-water

Generate a choppy-water surface and export it as a watertight STL for CNC milling in wood.
The piece is either a **disc** or a **rectangle** with a flat bottom and a choppy-water top.
Every model and milling parameter lives in a TOML config file.

> **Status:** Phase 3 (milling awareness). Generates a watertight STL, a PNG preview, a JSON
> run record and a milling report. Polish and presets for v0.1 are next. See
> [docs/PLAN.md](docs/PLAN.md).

## Install

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
```

## Usage

```bash
choppy-water                                          # write output/choppy_water.{stl,png,json} + _milling.txt
choppy-water --seed 7 --set water.choppiness=0.5      # try another sea
choppy-water --check                                  # validate the built-in defaults
choppy-water --config config/default.toml --check
choppy-water --set part.shape=rect --set part.width=5 --check
choppy-water --show-config                            # print the resolved settings as JSON
```

## Configuration

Copy [config/default.toml](config/default.toml) and edit it. You only need to list the
keys you change; everything else falls back to the defaults. Typos are reported with a
suggestion. Lengths use `units.length` (`"in"` or `"mm"`).

Choose the outline in `[part]`:

```toml
[part]
shape    = "disc"   # diameter = 3.0
diameter = 3.0
```

```toml
[part]
shape  = "rect"
width  = 4.0        # X
length = 3.0        # Y
```

Defaults: 3 in diameter disc, 1 in milling stock.

## Milling awareness

A ball-nose cutter cannot enter a valley narrower than itself. With
`milling.enforce_tool_limits = true` (the default) the STL contains the surface the cutter can
actually leave (the morphological closing of the ideal surface by the ball), so what you see is
what you can cut. The `*_milling.txt` report lists how much of the part was finer than the
cutter, the steepest slope, stepover and scallop height, an estimated finishing time, and the
number of roughing layers. Estimates are for the finishing pass only. For reliable tool-reach
numbers keep `mesh.grid_spacing` at or below one tenth of `milling.tool_diameter`.

## Development

```bash
pytest
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
