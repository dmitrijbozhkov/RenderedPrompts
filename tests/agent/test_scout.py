from pathlib import Path

import pytest

from agent.scout import ScoutingAgent
from tools.readonly_shell import ReadonlyShellError, ScoutContext, _run_readonly_command


def test_readonly_shell_finds_and_filters_files(tmp_path: Path) -> None:
    (tmp_path / "package").mkdir()
    (tmp_path / "package" / "agent.py").write_text("TODO: test\n", encoding="utf-8")
    (tmp_path / "package" / "notes.txt").write_text("", encoding="utf-8")

    result = _run_readonly_command(
        "find . -name '*.py' | grep agent",
        ScoutContext(tmp_path),
    )

    assert result.strip() == "./package/agent.py"


@pytest.mark.parametrize(
    "command",
    [
        "rm -rf .",
        "cat README > copy",
        "ls && pwd",
        "find . -delete",
        "find . -exec cat /etc/passwd ;",
        "sort -o changed.txt input.txt",
        "sort -ochanged.txt input.txt",
    ],
)
def test_readonly_shell_rejects_mutating_commands(tmp_path: Path, command: str) -> None:
    with pytest.raises(ReadonlyShellError):
        _run_readonly_command(command, ScoutContext(tmp_path))


@pytest.mark.parametrize(
    "command",
    [
        "cat /etc/passwd",
        "ls ..",
        "grep token ../secret",
        "grep -f/etc/passwd file.txt",
    ],
)
def test_readonly_shell_rejects_paths_outside_root(tmp_path: Path, command: str) -> None:
    with pytest.raises(ReadonlyShellError, match="escapes the search root"):
        _run_readonly_command(command, ScoutContext(tmp_path))


def test_readonly_shell_does_not_interpret_substitutions(tmp_path: Path) -> None:
    protected = tmp_path / "keep.txt"
    protected.write_text("keep", encoding="utf-8")

    with pytest.raises(ReadonlyShellError, match="No such file"):
        _run_readonly_command("cat '$(rm keep.txt)'", ScoutContext(tmp_path))

    assert protected.read_text(encoding="utf-8") == "keep"


def test_context_requires_a_directory(tmp_path: Path) -> None:
    file_path = tmp_path / "file.txt"
    file_path.write_text("", encoding="utf-8")

    with pytest.raises(NotADirectoryError):
        ScoutContext(file_path)


def test_scout_builds_with_only_the_find_tool(tmp_path: Path) -> None:
    agent = ScoutingAgent().build()

    assert [tool.name for tool in agent.tools] == ["readonly_bash"]
    assert "directory" not in agent.tools[0].params_json_schema["properties"]
