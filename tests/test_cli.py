import json
from pathlib import Path

from choppy_water.cli import main
from choppy_water.stl_io import read_stl

DEFAULT_TOML = Path(__file__).resolve().parents[1] / "config" / "default.toml"
FAST = ["--set", "mesh.grid_spacing=0.04", "--set", "mesh.edge_segments=235"]


def test_check_with_defaults(capsys):
    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "disc, diameter 3 in" in out
    assert "Configuration OK." in out


def test_check_with_default_toml_file():
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


def test_run_writes_stl_preview_and_record(tmp_path, capsys):
    stl = tmp_path / "out" / "sea.stl"
    assert main([*FAST, "-o", str(stl)]) == 0
    out = capsys.readouterr().out
    assert "triangles" in out

    triangles = read_stl(stl)
    assert len(triangles) > 1000
    assert triangles[..., 2].min() == 0  # flat bottom on the build plane
    assert (tmp_path / "out" / "sea.png").is_file()

    record = json.loads((tmp_path / "out" / "sea.json").read_text(encoding="utf-8"))
    assert record["mesh"]["watertight"] is True
    assert record["mesh"]["triangles"] == len(triangles)
    assert record["config"]["part"]["diameter"] == 3.0
    assert record["surface"]["relief"] == record["surface"]["relief"] > 6


def test_run_in_inches_and_rect(tmp_path):
    stl = tmp_path / "r.stl"
    args = [
        *FAST,
        "--set", "part.shape=rect",
        "--set", "output.stl_units='in'",
        "--set", "output.preview=false",
        "-o", str(stl),
    ]  # fmt: skip
    assert main(args) == 0
    tri = read_stl(stl)
    assert tri[..., 0].max() == 2.0  # half of the default 4 in width, now in inches
    assert not (tmp_path / "r.png").exists()


def test_run_reports_folded_surface(tmp_path, capsys):
    args = [*FAST, "--set", "water.choppiness=3", "-o", str(tmp_path / "a.stl")]
    assert main(args) == 0
    assert "folds over itself" in capsys.readouterr().err
