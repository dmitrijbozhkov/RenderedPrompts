"""CodeAct-style agent backed by a persistent Python execution tool."""

from pathlib import Path
from typing import Any

from agents import Agent

from tools.python_repl import ReplContext, SnippetEnvironment, execute_code

from .base import AgentBuilder


class ReplAgent(AgentBuilder):
    """Build an agent that solves tasks through sandboxed Python snippets."""

    def __init__(
        self,
        *,
        provided: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        allowed_context_types: tuple[type, ...] = (),
        stubs: str | None = None,
        model: str | None = None,
        template_directory: Path | None = None,
    ) -> None:
        super().__init__(template_directory)
        self.model = model
        self.stubs = stubs
        self.environment = SnippetEnvironment(
            provided=provided,
            context=context,
            allowed_context_types=allowed_context_types,
        )
        self._agent: Agent[ReplContext] | None = None

    def build(self) -> Agent[ReplContext]:
        instructions = self.build_instructions(
            instruction=(
                "Solve the user's task by calling execute_code. Trusted APIs documented "
                "below are already available as global names; do not import them. Store "
                "values needed by later calls explicitly in context. Use print for "
                "observations and return a concise answer grounded in execution results."
            ),
            stubs=self.stubs,
            environment=(
                "Python execution occurs in an agent sandbox. The context dictionary is "
                "validated and persists between calls. Ordinary global assignments do not "
                "persist."
            ),
        )
        kwargs: dict[str, Any] = {
            "name": "Python REPL Agent",
            "instructions": instructions,
            "tools": [execute_code],
        }
        if self.model is not None:
            kwargs["model"] = self.model
        self._agent = Agent(**kwargs)
        return self._agent

    async def run(self, prompt: str) -> Any:
        agent = self._agent or self.build()
        context = ReplContext(environment=self.environment)
        return await self._run(agent, prompt, context=context)

    def dumps_context(self) -> bytes:
        """Serialize the agent's persistent context."""
        return self.environment.dumps()
