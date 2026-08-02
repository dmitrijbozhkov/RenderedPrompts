"""Standalone OpenAI agent with file tools and local Python execution.

The file tools are restricted to ``--workspace`` (the current directory by
default). Python code runs directly on the host with the current interpreter;
only use this example with trusted prompts.

Set ``OPENAI_API_KEY``, then run::

    python examples/file_tools_python_agent.py "Create hello.py and run it"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

from agents import Agent, Runner, function_tool


class FileToolsPythonAgent:
    """Agent with workspace-scoped file operations and Python execution."""

    def __init__(
        self,
        workspace: Path,
        *,
        python_timeout_seconds: float = 30.0,
    ) -> None:
        self.workspace = workspace.resolve()
        self.python_timeout_seconds = python_timeout_seconds

    def resolve_path(self, path: str) -> Path:
        """Resolve a relative path and reject access outside the workspace."""
        candidate = (self.workspace / path).resolve()
        if not candidate.is_relative_to(self.workspace):
            raise ValueError(f"Path is outside the workspace: {path}")
        return candidate

    async def read_file(self, path: str) -> str:
        """Read a UTF-8 text file from the workspace."""
        target = self.resolve_path(path)
        return await asyncio.to_thread(target.read_text, encoding="utf-8")

    async def write_file(self, path: str, content: str) -> str:
        """Write a UTF-8 text file, creating its parent directories."""
        target = self.resolve_path(path)
        await asyncio.to_thread(target.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(target.write_text, content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {path}"

    async def edit_file(self, path: str, old: str, new: str) -> str:
        """Replace one exact substring in a UTF-8 text file."""
        if not old:
            raise ValueError("The substring to replace must not be empty")

        target = self.resolve_path(path)
        content = await asyncio.to_thread(target.read_text, encoding="utf-8")
        occurrences = content.count(old)
        if occurrences == 0:
            raise ValueError("The exact substring was not found")
        if occurrences > 1:
            raise ValueError(
                f"The exact substring occurs {occurrences} times; provide more context"
            )

        updated = content.replace(old, new, 1)
        await asyncio.to_thread(target.write_text, updated, encoding="utf-8")
        return f"Replaced the exact substring in {path}"

    async def run_python(self, code: str) -> str:
        """Run Python code and return stdout, stderr, and the exit code as JSON."""
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            code,
            cwd=self.workspace,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                process.communicate(),
                timeout=self.python_timeout_seconds,
            )
        except TimeoutError:
            process.kill()
            stdout_bytes, stderr_bytes = await process.communicate()
            return json.dumps(
                {
                    "exit_code": None,
                    "stdout": stdout_bytes.decode(errors="replace"),
                    "stderr": stderr_bytes.decode(errors="replace"),
                    "timed_out": True,
                }
            )

        return json.dumps(
            {
                "exit_code": process.returncode,
                "stdout": stdout_bytes.decode(errors="replace"),
                "stderr": stderr_bytes.decode(errors="replace"),
                "timed_out": False,
            }
        )

    def build(self) -> Agent[Any]:
        """Build the OpenAI Agents SDK agent and register its tools."""

        @function_tool
        async def read_file(path: str) -> str:
            """Read a UTF-8 file. The path must be relative to the workspace."""
            return await self.read_file(path)

        @function_tool
        async def write_file(path: str, content: str) -> str:
            """Write a UTF-8 file, replacing it if it exists."""
            return await self.write_file(path, content)

        @function_tool
        async def edit_file(path: str, old: str, new: str) -> str:
            """Replace exactly one occurrence of an exact substring in a file."""
            return await self.edit_file(path, old, new)

        @function_tool
        async def run_python(code: str) -> str:
            """Run Python code and return JSON with stdout, stderr, and exit code."""
            return await self.run_python(code)

        return Agent(
            name="File and Python assistant",
            instructions=(
                "Help the user work with files and Python. Inspect files before "
                "editing them. Use edit_file for focused changes and write_file "
                "for new or complete replacement files. Use run_python to verify "
                "Python behavior, and report both stdout and stderr when relevant."
            ),
            tools=[read_file, write_file, edit_file, run_python],
        )

    async def run(self, prompt: str) -> Any:
        """Run the agent on a user prompt."""
        return await Runner.run(self.build(), prompt)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Task for the agent")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path.cwd(),
        help="Directory available to file tools and Python (default: current directory)",
    )
    args = parser.parse_args()

    agent = FileToolsPythonAgent(args.workspace)
    result = await agent.run(args.prompt)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
