import json
from pathlib import Path

import pytest

from choppy_water.cli import main
from choppy_water.stl_io import read_stl

DEFAULT_TOML = Path(__file__).resolve().parents[1] / "src" / "choppy_water" / "default.toml"
FAST = ["--set", "mesh.grid_spacing=0.04", "--set", "mesh.edge_segments=235"]


def test_check_with_defaults(capsys):
    assert main(["--check"]) == 0
    out = capsys.readouterr().out
    assert "disc, diameter 3 in" in out
    assert "Configuration OK." in out


def test_check_with_default_toml_file():
    assert main(["--config", str(DEFAULT_TOML), "--check"]) == 0


def test_chop_layer_shows_in_the_summary(capsys):
    args = ["--check", "--set", "water.relief=0.15", "--set", "water.chop.relief=0.06"]
    assert main(args) == 0
    assert "Chop:    method fft, relief 0.06 in" in capsys.readouterr().out


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
    assert main(["--check", "--show-config", "-o", r"C:\out dir"]) == 0
    out = capsys.readouterr().out
    assert json.loads(out[: out.rindex("}") + 1])["output"]["directory"] == r"C:\out dir"


def test_output_option_rejects_a_file_name(capsys):
    assert main(["--check", "-o", "output/sea.stl"]) == 1
    assert "takes a folder" in capsys.readouterr().err


def test_run_writes_stl_preview_and_record(tmp_path, capsys):
    assert main([*FAST, "-o", str(tmp_path / "out")]) == 0
    out = capsys.readouterr().out
    assert "triangles" in out

    folder = tmp_path / "out" / "choppy_water"  # a subfolder, never the parent itself
    assert not list((tmp_path / "out").glob("*.*"))
    triangles = read_stl(folder / "choppy_water.stl")
    assert len(triangles) > 1000
    assert triangles[..., 2].min() == 0  # flat bottom on the build plane
    assert (folder / "choppy_water.png").is_file()

    record = json.loads((folder / "choppy_water.json").read_text(encoding="utf-8"))
    assert record["mesh"]["watertight"] is True
    assert record["mesh"]["triangles"] == len(triangles)
    assert record["config"]["part"]["diameter"] == 3.0
    assert record["surface"]["relief"] == record["surface"]["relief"] > 6


def test_run_in_inches_and_rect(tmp_path):
    args = [
        *FAST,
        "--set", "part.shape=rect",
        "--set", "output.stl_units='in'",
        "--set", "output.preview=false",
        "-o", str(tmp_path),
    ]  # fmt: skip
    assert main(args) == 0
    tri = read_stl(tmp_path / "choppy_water" / "choppy_water.stl")
    assert tri[..., 0].max() == 2.0  # half of the default 4 in width, now in inches
    assert not (tmp_path / "choppy_water" / "choppy_water.png").exists()


def test_run_reports_folded_surface(tmp_path, capsys):
    args = [*FAST, "--set", "water.choppiness=3", "-o", str(tmp_path)]
    assert main(args) == 0
    assert "folds over itself" in capsys.readouterr().err


def test_outputs_go_in_a_folder_named_after_the_config(tmp_path, monkeypatch):
    config = tmp_path / "my_sea.toml"
    config.write_text('[output]\ndirectory = "results"\n', encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert main(["--config", "my_sea.toml", *FAST]) == 0
    folder = tmp_path / "results" / "my_sea"
    assert sorted(p.name for p in folder.iterdir()) == [
        "my_sea.json",
        "my_sea.png",
        "my_sea.stl",
        "my_sea_3d.png",
        "my_sea_milling.txt",
    ]


def test_default_run_uses_the_choppy_water_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([*FAST, "--set", "output.preview=false"]) == 0
    assert (tmp_path / "output" / "choppy_water" / "choppy_water.stl").is_file()


def test_two_configs_do_not_overwrite_each_other(tmp_path, monkeypatch):
    for name, seed in (("a", 1), ("b", 2)):
        (tmp_path / f"{name}.toml").write_text(f"[water]\nseed = {seed}\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    for name in ("a", "b"):
        assert main(["--config", f"{name}.toml", *FAST, "--set", "output.preview=false"]) == 0
    a = (tmp_path / "output" / "a" / "a.stl").read_bytes()
    b = (tmp_path / "output" / "b" / "b.stl").read_bytes()
    assert a != b


def test_explicit_output_path_overrides_the_folder_layout(tmp_path, monkeypatch):
    config = tmp_path / "x.toml"
    config.write_text("", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    target = tmp_path / "flat" / "exact.stl"
    args = ["--config", "x.toml", *FAST, "--set", "output.preview=false",
            "--set", f"output.stl_path={json.dumps(str(target))}"]  # fmt: skip
    assert main(args) == 0
    assert target.is_file()
    assert not (tmp_path / "output").exists()


# -- examples, progress, previews, reproducing a run ---------------------------------------------


def test_list_examples(capsys):
    assert main(["--list-examples"]) == 0
    out = capsys.readouterr().out
    assert "calm" in out and "plaque" in out and "Gerstner" in out


def test_example_option_runs_a_built_in_config(tmp_path, capsys):
    args = ["--example", "calm", "--check", "-o", str(tmp_path)]
    assert main(args) == 0
    assert str(tmp_path / "calm" / "calm.stl") in capsys.readouterr().out


def test_unknown_example_fails_cleanly(capsys):
    assert main(["--example", "nope", "--check"]) == 1
    assert "available:" in capsys.readouterr().err


def test_config_and_example_are_mutually_exclusive(capsys):
    with pytest.raises(SystemExit):
        main(["--config", "a.toml", "--example", "calm"])


def test_run_writes_both_previews_and_reports_progress(tmp_path, capsys):
    assert main(["--example", "plaque", *FAST, "-o", str(tmp_path)]) == 0
    folder = tmp_path / "plaque"
    assert (folder / "plaque_3d.png").stat().st_size > 1000
    assert (folder / "plaque.png").is_file()
    err = capsys.readouterr().err
    assert "generating the surface (2 wave layers)" in err
    assert "building the mesh" in err and "rendering previews" in err


def test_missing_matplotlib_skips_previews_but_still_succeeds(tmp_path, monkeypatch, capsys):
    def no_matplotlib(*args, **kwargs):
        raise RuntimeError("previews need matplotlib")

    monkeypatch.setattr("choppy_water.cli.save_preview", no_matplotlib)
    assert main([*FAST, "-o", str(tmp_path)]) == 0
    folder = tmp_path / "choppy_water"
    assert (folder / "choppy_water.stl").is_file()
    assert not (folder / "choppy_water.png").exists()
    assert "skipped previews" in capsys.readouterr().err


def test_a_json_run_record_reproduces_the_run_exactly(tmp_path):
    first = tmp_path / "first"
    args = ["--example", "plaque", *FAST, "--seed", "5", "--set", "output.preview=false"]
    assert main([*args, "-o", str(first)]) == 0
    record = first / "plaque" / "plaque.json"

    again = tmp_path / "again"
    assert main(["--config", str(record), "--set", "output.preview=false", "-o", str(again)]) == 0
    one = (first / "plaque" / "plaque.stl").read_bytes()
    two = (again / "plaque" / "plaque.stl").read_bytes()
    assert one == two
