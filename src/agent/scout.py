"""A file-system scouting agent with a deliberately read-only tool."""

from pathlib import Path
from typing import Any

from agents import Agent

from tools.readonly_shell import ALLOWED_COMMANDS, ScoutContext, readonly_bash

from .base import AgentBuilder


class ScoutingAgent(AgentBuilder):
    """Build an agent that can only locate files beneath its per-run directory."""

    def __init__(
        self,
        *,
        model: str | None = None,
        template_directory: Path | None = None,
    ) -> None:
        super().__init__(template_directory)
        self.model = model
        self._agent: Agent[ScoutContext] | None = None

    def build(self) -> Agent[ScoutContext]:
        instructions = self.build_instructions(
            instruction=(
                "Scout the assigned directory for files relevant to the user's request. "
                "Use the readonly_bash tool to navigate, list files, and search content. "
                "Choose focused commands, summarize relevant paths clearly, and never "
                "attempt to modify, create, rename, or delete anything."
            ),
            environment=(
                "The search root is provided by trusted application context for each run. "
                "Access is limited to reading and searching. Allowed commands: "
                f"{', '.join(sorted(ALLOWED_COMMANDS))}. Pipelines are supported, but "
                "redirection, chaining, and commands outside this list are forbidden."
            ),
        )
        kwargs: dict[str, Any] = {
            "name": "File Scout",
            "instructions": instructions,
            "tools": [readonly_bash],
        }
        if self.model is not None:
            kwargs["model"] = self.model
        self._agent = Agent(**kwargs)
        return self._agent

    async def run(self, prompt: str, directory: str | Path) -> Any:
        agent = self._agent or self.build()
        context = ScoutContext(directory=Path(directory))
        return await self._run(agent, prompt, context=context)
