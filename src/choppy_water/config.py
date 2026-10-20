"""Typed configuration: load from TOML, validate, and convert units.

Every section is a frozen dataclass whose defaults mirror the packaged ``default.toml``
(see :func:`default_config_text`).
A user config only needs to list the keys it changes. Lengths are expressed in
``units.length`` ("in" or "mm"); call :meth:`Config.to_mm` to get a copy in
millimetres for the geometry code.
"""

from __future__ import annotations

import dataclasses
import difflib
import math
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, fields
from importlib import resources
from pathlib import Path
from typing import Any, get_type_hints

MM_PER_INCH = 25.4

LENGTH_UNITS = ("in", "mm")
SHAPES = ("disc", "rect")
WATER_METHODS = ("fft", "gerstner")
TOOL_TYPES = ("ball",)
LAYER_NAMES = ("water", "water.chop")


def _length(default: float) -> Any:
    """Dataclass field holding a length (or length-per-minute) that unit conversion scales."""
    return field(default=default, metadata={"length": True})


class ConfigError(ValueError):
    """Raised when a configuration cannot be loaded or fails validation."""

    def __init__(self, errors: Sequence[str]) -> None:
        self.errors = list(errors)
        super().__init__("Invalid configuration:\n" + "\n".join(f"  - {e}" for e in self.errors))


@dataclass(frozen=True)
class Units:
    length: str = "in"


@dataclass(frozen=True)
class Part:
    shape: str = "disc"
    diameter: float = _length(3.0)
    width: float = _length(4.0)
    length: float = _length(3.0)
    base_thickness: float = _length(0.25)
    max_thickness: float = _length(0.50)

    @property
    def extent(self) -> tuple[float, float]:
        """Bounding-box (x, y) size of the outline."""
        if self.shape == "disc":
            return (self.diameter, self.diameter)
        return (self.width, self.length)


@dataclass(frozen=True)
class Water:
    method: str = "fft"
    seed: int = 42
    patch_size: float = _length(6.0)
    wavelength_dominant: float = _length(0.8)
    wavelength_min: float = _length(0.3)
    wavelength_max: float = _length(1.6)
    wind_direction_deg: float = 0.0
    directional_spread_deg: float = 40.0
    choppiness: float = 0.8
    relief: float = _length(0.25)
    smoothing: float = _length(0.0)


@dataclass(frozen=True)
class ChopLayer:
    """Optional second wave layer (``[water.chop]``): shorter, sharper waves on the swell.

    Shares ``water.patch_size``. ``seed = -1`` means ``water.seed + 1``.
    """

    method: str = "fft"
    seed: int = -1
    wavelength_dominant: float = _length(0.5)
    wavelength_min: float = _length(0.25)
    wavelength_max: float = _length(0.9)
    wind_direction_deg: float = 0.0
    directional_spread_deg: float = 70.0
    choppiness: float = 0.9
    relief: float = _length(0.08)
    smoothing: float = _length(0.0)


@dataclass(frozen=True)
class Mesh:
    grid_spacing: float = _length(0.01)
    edge_segments: int = 720


@dataclass(frozen=True)
class Milling:
    stock_thickness: float = _length(1.0)
    tool_type: str = "ball"
    tool_diameter: float = _length(0.125)
    max_slope_deg: float = 70.0
    enforce_tool_limits: bool = True
    stepover_pct: float = 10.0
    stepdown: float = _length(0.1)
    feed_rate: float = _length(60.0)
    plunge_rate: float = _length(20.0)
    spindle_rpm: int = 16000


@dataclass(frozen=True)
class Output:
    stl_path: str = "output/choppy_water.stl"
    stl_units: str = "mm"
    preview: bool = True


_SECTIONS: dict[str, type] = {
    "units": Units,
    "part": Part,
    "water": Water,
    "mesh": Mesh,
    "milling": Milling,
    "output": Output,
}

_BAD = object()


def _coerce(value: Any, expected: type) -> Any:
    """Return ``value`` as ``expected`` (ints are accepted as floats) or ``_BAD``."""
    if expected is bool:
        return value if isinstance(value, bool) else _BAD
    if expected is int:
        return value if isinstance(value, int) and not isinstance(value, bool) else _BAD
    if expected is float:
        if isinstance(value, bool) or not isinstance(value, int | float):
            return _BAD
        return float(value) if math.isfinite(value) else _BAD
    if expected is str:
        return value if isinstance(value, str) else _BAD
    return _BAD


def _build_section(cls: type, raw: Any, name: str, errors: list[str]) -> Any:
    if not isinstance(raw, Mapping):
        errors.append(f"[{name}] must be a table")
        return cls()
    hints = get_type_hints(cls)
    known = {f.name for f in fields(cls)}
    for key in raw:
        if key not in known:
            close = difflib.get_close_matches(key, known, n=1)
            hint = f" (did you mean '{close[0]}'?)" if close else ""
            errors.append(f"{name}.{key}: unknown key{hint}")
    kwargs: dict[str, Any] = {}
    for f in fields(cls):
        if f.name not in raw:
            continue
        coerced = _coerce(raw[f.name], hints[f.name])
        if coerced is _BAD:
            got = repr(raw[f.name])
            errors.append(f"{name}.{f.name}: expected {hints[f.name].__name__}, got {got}")
        else:
            kwargs[f.name] = coerced
    return cls(**kwargs)


@dataclass(frozen=True)
class Config:
    units: Units = field(default_factory=Units)
    part: Part = field(default_factory=Part)
    water: Water = field(default_factory=Water)
    chop: ChopLayer | None = None  # TOML: the [water.chop] table
    mesh: Mesh = field(default_factory=Mesh)
    milling: Milling = field(default_factory=Milling)
    output: Output = field(default_factory=Output)

    # -- construction ---------------------------------------------------------------------

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> Config:
        """Build and validate a config from parsed TOML; raises :class:`ConfigError`."""
        errors: list[str] = []
        for key in raw:
            if key not in _SECTIONS:
                close = difflib.get_close_matches(key, _SECTIONS, n=1)
                hint = f" (did you mean '[{close[0]}]'?)" if close else ""
                errors.append(f"[{key}]: unknown section{hint}")
        raw = dict(raw)
        chop_raw = None
        if isinstance(raw.get("water"), Mapping) and "chop" in raw["water"]:
            water_raw = dict(raw["water"])
            chop_raw = water_raw.pop("chop")
            raw["water"] = water_raw
        sections = {
            name: _build_section(section_cls, raw[name], name, errors) if name in raw else None
            for name, section_cls in _SECTIONS.items()
        }
        kwargs = {k: v for k, v in sections.items() if v is not None}
        if chop_raw is not None:
            kwargs["chop"] = _build_section(ChopLayer, chop_raw, "water.chop", errors)
        config = cls(**kwargs)
        if not errors:  # semantic checks assume correctly typed values
            errors.extend(config.validate())
        if errors:
            raise ConfigError(errors)
        return config

    def to_dict(self) -> dict[str, dict[str, Any]]:
        """Plain dict in TOML layout (``chop`` nested under ``water``); feeds ``from_dict``."""
        data = dataclasses.asdict(self)
        chop = data.pop("chop")
        if chop is not None:
            data["water"]["chop"] = chop
        return data

    def wave_layers(self) -> list[Water]:
        """The wave layers to synthesize: the main sea, then the chop layer if configured."""
        layers = [self.water]
        if self.chop is not None:
            values = {f.name: getattr(self.chop, f.name) for f in fields(ChopLayer)}
            if values["seed"] == -1:
                values["seed"] = self.water.seed + 1
            layers.append(Water(**values, patch_size=self.water.patch_size))
        return layers

    @property
    def total_relief(self) -> float:
        """Combined peak-to-peak height budget of all wave layers."""
        return sum(layer.relief for layer in self.wave_layers())

    # -- units ----------------------------------------------------------------------------

    @property
    def mm_per_unit(self) -> float:
        return MM_PER_INCH if self.units.length == "in" else 1.0

    def to_mm(self) -> Config:
        """Return a copy with every length expressed in millimetres."""
        scale = self.mm_per_unit
        changes: dict[str, Any] = {}
        for name in _SECTIONS:
            section = getattr(self, name)
            scaled = {
                f.name: getattr(section, f.name) * scale
                for f in fields(section)
                if f.metadata.get("length")
            }
            changes[name] = dataclasses.replace(section, **scaled)
        changes["units"] = Units(length="mm")
        if self.chop is not None:
            changes["chop"] = dataclasses.replace(
                self.chop,
                **{
                    f.name: getattr(self.chop, f.name) * scale
                    for f in fields(ChopLayer)
                    if f.metadata.get("length")
                },
            )
        return dataclasses.replace(self, **changes)

    # -- validation -----------------------------------------------------------------------

    def validate(self) -> list[str]:
        """Return a list of error messages (empty when the config is usable)."""
        p, m, ml, o = self.part, self.mesh, self.milling, self.output
        errors: list[str] = []

        def need(ok: bool, message: str) -> None:
            if not ok:
                errors.append(message)

        need(self.units.length in LENGTH_UNITS, f"units.length: must be one of {LENGTH_UNITS}")

        need(p.shape in SHAPES, f"part.shape: must be one of {SHAPES}")
        if p.shape == "disc":
            need(p.diameter > 0, "part.diameter: must be > 0")
        elif p.shape == "rect":
            need(p.width > 0, "part.width: must be > 0")
            need(p.length > 0, "part.length: must be > 0")
        need(p.base_thickness > 0, "part.base_thickness: must be > 0")
        need(p.max_thickness > p.base_thickness, "part.max_thickness: must exceed base_thickness")
        need(
            p.max_thickness <= ml.stock_thickness,
            "part.max_thickness: must not exceed milling.stock_thickness",
        )

        for name, layer in zip(LAYER_NAMES, self.wave_layers(), strict=False):
            need(layer.method in WATER_METHODS, f"{name}.method: must be one of {WATER_METHODS}")
            need(layer.patch_size > 0, f"{name}.patch_size: must be > 0")
            need(layer.wavelength_min > 0, f"{name}.wavelength_min: must be > 0")
            need(
                layer.wavelength_min <= layer.wavelength_dominant <= layer.wavelength_max,
                f"{name}: need wavelength_min <= wavelength_dominant <= wavelength_max",
            )
            need(
                layer.wavelength_max <= layer.patch_size,
                f"{name}.wavelength_max: must not exceed water.patch_size",
            )
            need(
                0 <= layer.directional_spread_deg <= 180,
                f"{name}.directional_spread_deg: must be between 0 and 180",
            )
            need(layer.choppiness >= 0, f"{name}.choppiness: must be >= 0")
            need(layer.relief > 0, f"{name}.relief: must be > 0")
            need(layer.smoothing >= 0, f"{name}.smoothing: must be >= 0")
            need(layer.seed >= 0, f"{name}.seed: must be >= 0")
        if self.chop is not None:
            need(self.chop.seed >= -1, "water.chop.seed: must be >= 0 (or -1 for water.seed + 1)")
        label = "water.relief + water.chop.relief" if self.chop is not None else "water.relief"
        need(
            self.total_relief <= p.max_thickness - p.base_thickness,
            f"{label}: must fit within max_thickness - base_thickness",
        )

        need(m.grid_spacing > 0, "mesh.grid_spacing: must be > 0")
        need(m.edge_segments >= 16, "mesh.edge_segments: must be >= 16")

        need(ml.stock_thickness > 0, "milling.stock_thickness: must be > 0")
        need(ml.tool_type in TOOL_TYPES, f"milling.tool_type: must be one of {TOOL_TYPES}")
        need(ml.tool_diameter > 0, "milling.tool_diameter: must be > 0")
        need(0 < ml.max_slope_deg < 90, "milling.max_slope_deg: must be between 0 and 90")
        need(0 < ml.stepover_pct <= 100, "milling.stepover_pct: must be in (0, 100]")
        need(ml.stepdown > 0, "milling.stepdown: must be > 0")
        need(ml.feed_rate > 0, "milling.feed_rate: must be > 0")
        need(ml.plunge_rate > 0, "milling.plunge_rate: must be > 0")
        need(ml.spindle_rpm > 0, "milling.spindle_rpm: must be > 0")

        need(o.stl_units in LENGTH_UNITS, f"output.stl_units: must be one of {LENGTH_UNITS}")
        need(bool(o.stl_path.strip()), "output.stl_path: must not be empty")
        return errors

    def warnings(self) -> list[str]:
        """Return non-fatal advisories about settings that are legal but probably unwise."""
        p, w, m, ml = self.part, self.water, self.mesh, self.milling
        notes: list[str] = []
        layers = list(zip(LAYER_NAMES, self.wave_layers(), strict=False))
        if w.patch_size < max(p.extent):
            notes.append(
                "water.patch_size is smaller than the part: the wave pattern will visibly repeat"
            )
        for name, layer in layers:
            if m.grid_spacing > layer.wavelength_min / 10:
                notes.append(
                    f"mesh.grid_spacing is coarse for {name}.wavelength_min "
                    "(< 10 samples per wavelength)"
                )
        if p.shape == "disc":
            ring_spacing = math.pi * p.diameter / m.edge_segments
            if not 0.5 * m.grid_spacing <= ring_spacing <= 2 * m.grid_spacing:
                notes.append(
                    "mesh.edge_segments gives a rim point spacing far from mesh.grid_spacing; "
                    "keep them within 2x of each other to avoid sliver triangles"
                )
        if m.grid_spacing > ml.tool_diameter / 10:
            notes.append(
                "mesh.grid_spacing is coarse relative to milling.tool_diameter "
                "(< 10 cells across the cutter): tool-reach estimates will be unreliable"
            )
        for name, layer in layers:
            if ml.enforce_tool_limits and layer.wavelength_min < 2 * ml.tool_diameter:
                notes.append(
                    f"{name}.wavelength_min < 2 x tool_diameter: the finest ripples will be "
                    "smoothed out by the cutter"
                )
        return notes


# -- loading ------------------------------------------------------------------------------


def default_config_text() -> str:
    """The commented default config shipped with the package (a starting point to copy)."""
    return resources.files("choppy_water").joinpath("default.toml").read_text(encoding="utf-8")


def parse_override(text: str) -> tuple[str, str, Any]:
    """Parse ``section.key=value`` (value in TOML syntax, bare words treated as strings)."""
    target, sep, raw_value = text.partition("=")
    section, dot, key = target.strip().partition(".")
    if not sep or not dot or not section or not key:
        raise ConfigError([f"override '{text}': expected the form section.key=value"])
    try:
        value = tomllib.loads(f"v = {raw_value.strip()}")["v"]
    except tomllib.TOMLDecodeError:
        value = raw_value.strip()
    return section, key, value


def load_config(path: str | Path | None = None, overrides: Sequence[str] = ()) -> Config:
    """Load a config file (or pure defaults) and apply ``section.key=value`` overrides."""
    raw: dict[str, dict[str, Any]] = {}
    if path is not None:
        try:
            with open(path, "rb") as fh:
                raw = tomllib.load(fh)
        except FileNotFoundError:
            raise ConfigError([f"config file not found: {path}"]) from None
        except tomllib.TOMLDecodeError as exc:
            raise ConfigError([f"{path}: invalid TOML: {exc}"]) from None
    for text in overrides:
        section, key, value = parse_override(text)
        table = raw.setdefault(section, {})
        if not isinstance(table, dict):
            raise ConfigError([f"override '{text}': [{section}] is not a table"])
        sub, dot, leaf = key.partition(".")  # e.g. water.chop.relief
        if dot:
            table = table.setdefault(sub, {})
            if not isinstance(table, dict):
                raise ConfigError([f"override '{text}': {section}.{sub} is not a table"])
            key = leaf
        table[key] = value
    return Config.from_dict(raw)
