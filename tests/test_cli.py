import json
from pathlib import Path

from choppy_water.cli import main

DEFAULT_TOML = Path(__file__).resolve().parents[1] / "config" / "default.toml"


def test_check_with_defaults(capsys):
    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "disc, diameter 3 in" in out
    assert "Configuration OK." in out


def test_check_with_default_toml_file(capsys):
    assert main(["--config", str(DEFAULT_TOML), "--check"]) == 0


def test_rect_override(capsys):
    code = main(["--check", "--set", "part.shape=rect", "--set", "part.width=5"])
    assert code == 0
    assert "rectangle, 5 x 3 in" in capsys.readouterr().out


def test_show_config_is_json(capsys):
    assert main(["--check", "--show-config", "--seed", "11"]) == 0
    out = capsys.readouterr().out
    data = json.loads(out[: out.rindex("}") + 1])
    assert data["water"]["seed"] == 11


def test_invalid_config_returns_1(capsys):
    assert main(["--check", "--set", "part.shape=hexagon"]) == 1
    assert "part.shape" in capsys.readouterr().err


def test_output_shortcut_handles_windows_paths(capsys):
    assert main(["--check", "--show-config", "-o", r"C:\out dir\x.stl"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[: out.rindex("}") + 1])["output"]["stl_path"] == r"C:\out dir\x.stl"


def test_generation_not_yet_implemented(capsys):
    assert main([]) == 2
    assert "not implemented" in capsys.readouterr().err
