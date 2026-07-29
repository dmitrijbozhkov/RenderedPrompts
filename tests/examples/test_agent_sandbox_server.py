import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

SERVER_PATH = (
    Path(__file__).parents[2] / "examples" / "agent_sandbox_server.py"
)
SPEC = importlib.util.spec_from_file_location("agent_sandbox_server", SERVER_PATH)
assert SPEC is not None and SPEC.loader is not None
server = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(server)


@pytest.mark.asyncio
async def test_execute_parses_code_and_returns_context_updates() -> None:
    server.repl_environment = server.SnippetEnvironment()
    request = server.ExecuteRequest(
        command=json.dumps(
            {
                "code": (
                    "context['count'] = context.get('count', 0) + 1; "
                    "print('updated')"
                )
            }
        )
    )

    response = await server.execute_command(request)
    payload = json.loads(response.stdout)

    assert response.exit_code == 0
    assert payload == {
        "output": "updated\n",
        "context_updates": {"count": 1},
        "deleted_context_keys": [],
    }


@pytest.mark.asyncio
async def test_execute_rejects_missing_code() -> None:
    request = server.ExecuteRequest(command=json.dumps({"source": "print(1)"}))

    response = await server.execute_command(request)

    assert response.exit_code == 1
    assert response.stdout == ""
    assert "string 'code' field" in response.stderr
