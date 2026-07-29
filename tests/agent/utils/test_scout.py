import os
from pathlib import Path

import pytest

from agent.utils.scout import ScoutFSError, ScoutFS


def test_list_and_glob(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "guide.md").write_text("# Guide\n", encoding="utf-8")
    (tmp_path / "config.json").write_text("{}", encoding="utf-8")
    scout = ScoutFS(tmp_path)

    assert [entry.path for entry in scout.list()] == ["config.json", "docs"]
    assert scout.glob("**/*.md") == ["docs/guide.md"]


def test_grep_and_bounded_read(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("one\nTODO: first\nthree\nTODO: second\n", encoding="utf-8")
    scout = ScoutFS(tmp_path)

    matches = scout.grep("todo", "**/*.md", case_sensitive=False)

    assert [(match.line, match.text) for match in matches] == [
        (2, "TODO: first"),
        (4, "TODO: second"),
    ]
    assert scout.read("notes.md", offset=1, limit=2) == "TODO: first\nthree"


def test_markdown_outline_and_section(tmp_path: Path) -> None:
    (tmp_path / "guide.md").write_text(
        "# Guide\nintro\n## Install\nsteps\n## Usage\nexample\n",
        encoding="utf-8",
    )
    scout = ScoutFS(tmp_path)

    outline = scout.outline("guide.md")

    assert [item.path for item in outline.items] == [
        "Guide",
        "Guide/Install",
        "Guide/Usage",
    ]
    assert scout.query("guide.md", "Guide/Install") == "## Install\nsteps"


def test_json_and_toml_queries(tmp_path: Path) -> None:
    (tmp_path / "config.json").write_text(
        '{"server": {"ports": [80, 443]}}',
        encoding="utf-8",
    )
    (tmp_path / "project.toml").write_text(
        "[tool.pytest]\nmode = \"auto\"\n",
        encoding="utf-8",
    )
    scout = ScoutFS(tmp_path)

    assert scout.query("config.json", "/server/ports/1") == 443
    assert scout.query("project.toml", "tool.pytest.mode") == "auto"


def test_rejects_parent_and_symlink_escapes(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("secret", encoding="utf-8")
    os.symlink(outside, tmp_path / "escape")
    scout = ScoutFS(tmp_path)

    with pytest.raises(ScoutFSError, match="escapes scout root"):
        scout.read("../" + outside.name)
    with pytest.raises(ScoutFSError, match="escapes scout root"):
        scout.read("escape")
