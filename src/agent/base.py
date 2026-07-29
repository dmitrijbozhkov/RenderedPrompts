"""Shared construction helpers for OpenAI Agents SDK agents."""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from agents import Agent, Runner
from jinja2 import Environment, FileSystemLoader, StrictUndefined


class AgentBuilder(ABC):
    """Abstract interface for constructing and running an SDK agent."""

    def __init__(self, template_directory: Path | None = None) -> None:
        templates = template_directory or Path(__file__).parents[2] / "templates"
        self.template_environment = Environment(
            loader=FileSystemLoader(templates),
            undefined=StrictUndefined,
            autoescape=False,
            trim_blocks=True,
            lstrip_blocks=True,
        )

    def build_instructions(
        self,
        *,
        instruction: str,
        stubs: str | None = None,
        skills: str | None = None,
        environment: str | None = None,
        kb: str | None = None,
    ) -> str:
        """Render the common instruction format, omitting empty sections."""
        template = self.template_environment.get_template("agent_instructions.md.j2")
        return template.render(
            instruction=instruction,
            stubs=stubs,
            skills=skills,
            environment=environment,
            kb=kb,
        ).strip()

    @abstractmethod
    def build(self) -> Agent[Any]:
        """Construct the configured SDK agent."""

    @abstractmethod
    async def run(self, prompt: str) -> Any:
        """Run the agent and return the SDK result."""

    async def _run(
        self,
        agent: Agent[Any],
        prompt: str,
        *,
        context: Any = None,
    ) -> Any:
        return await Runner.run(agent, prompt, context=context)
