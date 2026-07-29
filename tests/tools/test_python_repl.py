from pathlib import Path

import pytest

from agent.repl import ReplAgent
from agent.utils.scout import ScoutFS
from tools.python_repl import ReplContext, SnippetEnvironment, _execute_code


def test_execute_code_uses_provided_api_and_persists_explicit_context(
    tmp_path: Path,
) -> None:
    (tmp_path / "guide.md").write_text("# Guide\n", encoding="utf-8")
    environment = SnippetEnvironment(provided={"fs": ScoutFS(tmp_path)})
    repl_context = ReplContext(environment)

    first = _execute_code(
        repl_context,
        "context['files'] = fs.glob('**/*.md'); print(context['files'])",
    )
    second = _execute_code(repl_context, "count = len(context['files'])", "count")

    assert "guide.md" in first
    assert second == "Result: 1"
    assert environment.context == {"files": ["guide.md"]}


def test_context_rejects_capabilities() -> None:
    environment = SnippetEnvironment()

    with pytest.raises(TypeError, match="forbidden value"):
        environment.run("context['callable'] = print")


def test_ordinary_globals_do_not_update_context() -> None:
    environment = SnippetEnvironment(context={"answer": 42})

    environment.run("answer = 7; temporary = 1")

    assert environment.context == {"answer": 42}


def test_serialization_restores_state_and_rebinds_capabilities(tmp_path: Path) -> None:
    original = SnippetEnvironment(context={"answer": 42})
    restored = SnippetEnvironment.loads(
        original.dumps(),
        provided={"fs": ScoutFS(tmp_path)},
    )

    assert restored.context == {"answer": 42}
    assert "fs" in restored.provided


def test_repl_agent_exposes_only_execute_code() -> None:
    agent = ReplAgent(stubs="class Example: ...").build()

    assert [tool.name for tool in agent.tools] == ["execute_code"]
    assert "code" in agent.tools[0].params_json_schema["properties"]
    assert "context" not in agent.tools[0].params_json_schema["properties"]
