import dataclasses
import tomllib

import pytest

from choppy_water.config import (
    MM_PER_INCH,
    Config,
    ConfigError,
    default_config_text,
    load_config,
    parse_override,
)


def test_defaults_match_requested_values():
    cfg = Config()
    assert cfg.part.shape == "disc"
    assert cfg.part.diameter == 3.0
    assert cfg.milling.stock_thickness == 1.0
    assert cfg.units.length == "in"
    assert cfg.validate() == []


def test_default_toml_equals_dataclass_defaults():
    """default.toml is what users copy and edit; it must not drift from the code."""
    assert Config.from_dict(tomllib.loads(default_config_text())) == Config()


def test_default_toml_documents_every_key():
    raw = tomllib.loads(default_config_text())
    expected = {
        section: {f.name for f in dataclasses.fields(getattr(Config(), section))}
        for section in Config().to_dict()
    }
    assert {section: set(keys) for section, keys in raw.items()} == expected


def test_partial_config_fills_in_defaults():
    cfg = Config.from_dict({"part": {"shape": "rect", "width": 5, "length": 2}})
    assert cfg.part.shape == "rect"
    assert cfg.part.width == 5.0  # int accepted as float
    assert cfg.part.extent == (5.0, 2.0)
    assert cfg.water == Config().water


def test_disc_extent():
    assert Config().part.extent == (3.0, 3.0)


def test_rect_does_not_require_diameter_and_disc_does_not_require_width():
    Config.from_dict({"part": {"shape": "rect", "diameter": 0}})
    Config.from_dict({"part": {"shape": "disc", "width": 0, "length": 0}})


def test_rect_dimensions_must_be_positive():
    with pytest.raises(ConfigError) as exc:
        Config.from_dict({"part": {"shape": "rect", "width": 0, "length": -1}})
    assert any("part.width" in e for e in exc.value.errors)
    assert any("part.length" in e for e in exc.value.errors)


def test_unknown_key_suggests_correction():
    with pytest.raises(ConfigError) as exc:
        Config.from_dict({"part": {"diamter": 3.0}})
    assert "did you mean 'diameter'" in str(exc.value)


def test_unknown_section_is_rejected():
    with pytest.raises(ConfigError, match="unknown section"):
        Config.from_dict({"parts": {}})


def test_wrong_types_are_reported_together():
    with pytest.raises(ConfigError) as exc:
        Config.from_dict({"part": {"diameter": "big"}, "water": {"seed": 1.5}})
    assert len(exc.value.errors) == 2


def test_bool_is_not_accepted_as_number():
    with pytest.raises(ConfigError):
        Config.from_dict({"part": {"diameter": True}})


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ({"part": {"shape": "triangle"}}, "part.shape"),
        ({"part": {"max_thickness": 0.1}}, "max_thickness"),
        ({"part": {"max_thickness": 1.5}}, "stock_thickness"),
        ({"water": {"relief": 0.4}}, "water.relief"),
        ({"water": {"wavelength_min": 1.0}}, "wavelength_min"),
        ({"water": {"directional_spread_deg": 200}}, "directional_spread"),
        ({"milling": {"max_slope_deg": 90}}, "max_slope_deg"),
        ({"units": {"length": "cm"}}, "units.length"),
        ({"output": {"stl_units": "ft"}}, "output.stl_units"),
    ],
)
def test_invalid_values_are_rejected(raw, fragment):
    with pytest.raises(ConfigError) as exc:
        Config.from_dict(raw)
    assert fragment in str(exc.value)


def test_to_mm_scales_lengths_only():
    cfg = Config().to_mm()
    assert cfg.units.length == "mm"
    assert cfg.part.diameter == pytest.approx(3.0 * MM_PER_INCH)
    assert cfg.milling.stock_thickness == pytest.approx(25.4)
    assert cfg.milling.feed_rate == pytest.approx(60.0 * MM_PER_INCH)
    assert cfg.water.choppiness == Config().water.choppiness
    assert cfg.milling.max_slope_deg == 70.0
    assert cfg.milling.spindle_rpm == 16000
    assert cfg.validate() == []


def test_to_mm_is_noop_for_mm_configs():
    cfg = Config.from_dict(
        {
            "units": {"length": "mm"},
            "part": {"diameter": 76.2, "base_thickness": 6, "max_thickness": 12},
            "water": {
                "relief": 6,
                "patch_size": 150,
                "wavelength_dominant": 20,
                "wavelength_min": 8,
                "wavelength_max": 40,
            },
            "mesh": {"grid_spacing": 0.25},
            "milling": {
                "stock_thickness": 25.4,
                "tool_diameter": 3.175,
                "stepdown": 2.5,
                "feed_rate": 1500,
                "plunge_rate": 500,
            },
        }
    )
    assert cfg.to_mm() == dataclasses.replace(cfg)


def test_warnings_flag_fine_ripples_and_small_patch():
    cfg = Config.from_dict(
        {
            "water": {"wavelength_min": 0.2, "wavelength_dominant": 0.8},
            "mesh": {"grid_spacing": 0.05},
        }
    )
    text = " ".join(cfg.warnings())
    assert "tool_diameter" in text
    assert "grid_spacing" in text
    small = Config.from_dict({"water": {"patch_size": 2.0, "wavelength_max": 1.6}})
    assert any("repeat" in n for n in small.warnings())
    assert Config().warnings() == []


def test_parse_override_handles_numbers_strings_and_bools():
    assert parse_override("water.seed=7") == ("water", "seed", 7)
    assert parse_override("water.choppiness=1.4") == ("water", "choppiness", 1.4)
    assert parse_override("part.shape=rect") == ("part", "shape", "rect")
    assert parse_override('part.shape="rect"') == ("part", "shape", "rect")
    assert parse_override("milling.enforce_tool_limits=false") == (
        "milling",
        "enforce_tool_limits",
        False,
    )


@pytest.mark.parametrize("bad", ["nonsense", "water=3", ".key=1", "a.=1"])
def test_parse_override_rejects_malformed(bad):
    with pytest.raises(ConfigError):
        parse_override(bad)


def test_load_config_from_file_with_overrides(tmp_path):
    path = tmp_path / "c.toml"
    path.write_text('[part]\nshape = "rect"\nwidth = 5.0\nlength = 2.0\n', encoding="utf-8")
    cfg = load_config(path, ["water.seed=9", "part.length=2.5"])
    assert cfg.part.width == 5.0
    assert cfg.part.length == 2.5
    assert cfg.water.seed == 9


def test_load_config_errors(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(tmp_path / "missing.toml")
    bad = tmp_path / "bad.toml"
    bad.write_text("[part\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="invalid TOML"):
        load_config(bad)


def test_load_config_without_path_gives_defaults():
    assert load_config() == Config()
