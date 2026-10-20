"""Guards that keep the docs, examples and packaging honest."""

import re
import tomllib
from pathlib import Path

import pytest

from choppy_water import __version__
from choppy_water.config import Config, default_config_text, load_config
from choppy_water.heightfield import generate_heightfield
from choppy_water.milling import plan_milling

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = sorted((ROOT / "examples").glob("*.toml"))


def test_version_matches_pyproject():
    with open(ROOT / "pyproject.toml", "rb") as fh:
        assert tomllib.load(fh)["project"]["version"] == __version__


def test_changelog_mentions_current_version():
    assert f"## [{__version__}]" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_config_reference_documents_every_key():
    doc = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    documented = set(re.findall(r"`([a-z_]+\.[a-z_]+)`", doc))
    keys = {f"{section}.{key}" for section, table in Config().to_dict().items() for key in table}
    assert keys <= documented, f"undocumented keys: {sorted(keys - documented)}"


def test_documented_defaults_match_the_code():
    """Spot-check the numbers quoted in the reference against the real defaults."""
    doc = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"\| `([a-z_.]+)` \| `([^`]+)` \|", doc))
    for section, table in Config().to_dict().items():
        for key, value in table.items():
            shown = rows[f"{section}.{key}"]
            if isinstance(value, bool):
                assert shown == str(value).lower(), (section, key)
            elif isinstance(value, str):
                assert shown == f'"{value}"', (section, key)
            else:
                assert float(shown) == pytest.approx(float(value)), (section, key)


def test_chop_layer_is_documented_with_matching_defaults():
    import dataclasses

    from choppy_water.config import ChopLayer

    doc = (ROOT / "docs" / "CONFIG.md").read_text(encoding="utf-8")
    rows = dict(re.findall(r"\| `(water\.chop\.[a-z_]+)` \| `([^`]+)` \|", doc))
    defaults = ChopLayer()
    assert set(rows) == {f"water.chop.{f.name}" for f in dataclasses.fields(ChopLayer)}
    for field in dataclasses.fields(ChopLayer):
        shown, value = rows[f"water.chop.{field.name}"], getattr(defaults, field.name)
        if isinstance(value, str):
            assert shown == f'"{value}"'
        else:
            assert float(shown) == pytest.approx(float(value)), field.name


def test_default_toml_shows_the_chop_block_with_the_real_defaults():
    from choppy_water.config import ChopLayer

    lines = default_config_text().splitlines()
    start = lines.index("# [water.chop]")
    block = []
    for line in lines[start:]:
        if not line.startswith("# "):
            break
        block.append(line[2:].split("#")[0].rstrip())  # uncomment, drop inline comments
    # The swell must make room for the chop, as the comment in the file says.
    text = "[water]\nrelief = 0.17\n" + "\n".join(block)
    cfg = Config.from_dict(tomllib.loads(text))
    assert cfg.chop == ChopLayer()


def test_there_is_at_least_a_calm_a_choppy_and_a_stormy_preset():
    assert {"calm", "choppy", "stormy"} <= {p.stem for p in EXAMPLES}


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_is_valid_and_has_a_gallery_image(path):
    load_config(path)
    assert (ROOT / "docs" / "images" / f"{path.stem}.png").is_file()


@pytest.mark.parametrize("path", EXAMPLES, ids=lambda p: p.stem)
def test_example_generates_within_its_stock(path):
    config = load_config(path, ["mesh.grid_spacing=0.04"])  # coarse: this checks wiring, not looks
    milled, report = plan_milling(config, generate_heightfield(config))
    inside = milled.z[milled.mask]
    mm = config.to_mm()
    assert inside.min() >= mm.part.base_thickness - 1e-9
    assert inside.max() <= mm.part.max_thickness + 1e-9
    assert report.stock_margin >= 0


def test_packaged_default_config_is_what_write_config_emits(tmp_path):
    from choppy_water.cli import main

    target = tmp_path / "cfg" / "mine.toml"
    assert main(["--write-config", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == default_config_text()
    assert main(["--write-config", str(target)]) == 1  # refuses to overwrite
    assert main(["--config", str(target), "--check"]) == 0
