# choppy-water

Generate a choppy-water surface and export it as a watertight STL for CNC milling in wood.
The piece is either a **disc** or a **rectangle** with a flat bottom and a choppy-water top.
Every model and milling parameter lives in a TOML config file.

> **Status:** Phase 0 (scaffolding). Config loading, validation and the CLI work;
> surface generation and STL export are next. See [docs/PLAN.md](docs/PLAN.md).

## Install

Requires Python 3.11+.

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows; use `source .venv/bin/activate` elsewhere
pip install -e ".[dev]"
```

## Usage

```bash
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

## Development

```bash
pytest
ruff check .
```

## License

MIT. See [LICENSE](LICENSE).
