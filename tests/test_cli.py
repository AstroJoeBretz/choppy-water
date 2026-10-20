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


def test_run_writes_preview_next_to_stl_path(tmp_path, capsys):
    stl = tmp_path / "sea.stl"
    assert main(["--set", "mesh.grid_spacing=0.04", "-o", str(stl)]) == 0
    captured = capsys.readouterr()
    assert (tmp_path / "sea.png").is_file()
    assert "relief 6.35 mm" in captured.out
    assert "STL export is not implemented" in captured.err  # arrives in Phase 2


def test_run_without_preview_writes_nothing(tmp_path, capsys):
    stl = tmp_path / "sea.stl"
    args = ["--set", "mesh.grid_spacing=0.04", "--set", "output.preview=false", "-o", str(stl)]
    assert main(args) == 0
    assert list(tmp_path.iterdir()) == []


def test_run_reports_folded_surface(tmp_path, capsys):
    args = [
        "--set",
        "mesh.grid_spacing=0.04",
        "--set",
        "water.choppiness=3",
        "-o",
        str(tmp_path / "a.stl"),
    ]
    assert main(args) == 0
    assert "folds over itself" in capsys.readouterr().err
