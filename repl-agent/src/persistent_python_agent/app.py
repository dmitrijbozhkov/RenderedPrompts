from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import os
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, List, Mapping

import httpx
from agents import Agent, RunContextWrapper, Runner, function_tool
from jinja2 import Environment, StrictUndefined
from openai import AsyncOpenAI
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine

from .executor import PersistentPythonExecutor
from .rag import build_hybrid_rrf_query


@dataclass
class AgentContext:
    """Local data made available while initializing an agent run."""

    instruction_data: Mapping[str, Any] = field(default_factory=dict)
    http_client: httpx.AsyncClient | None = None
    rag_engine: AsyncEngine | None = None
    embedding_client: AsyncOpenAI | None = None
    embedding_model: str = "text-embedding-3-small"


class HaikuInput(BaseModel):
    """Typed input accepted by the haiku agent tool."""

    prompt: str = Field(description="The original prompt to inspire the haikus")


class HaikuOutput(BaseModel):
    """Compose multiple distinct haikus inspired by the supplied prompt.

    Return each complete haiku as one item in `haikus`. Each haiku must contain
    three lines separated by newline characters and should follow a 5-7-5
    syllable pattern. Return no commentary outside the structured result.
    """

    haikus: List[str]


def output_model_instructions(output_model: type[BaseModel]) -> str:
    """Return the semantic generation guidance stored on an output model."""
    guidance = inspect.getdoc(output_model)
    if not guidance:
        raise ValueError(f"{output_model.__name__} must define a docstring")

    paragraphs = (
        " ".join(line.strip() for line in paragraph.splitlines())
        for paragraph in guidance.split("\n\n")
    )
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def _load_instructions_template():
    template_source = (
        files("persistent_python_agent")
        .joinpath("templates/instructions.jinja2")
        .read_text(encoding="utf-8")
    )
    environment = Environment(
        autoescape=False,
        keep_trailing_newline=False,
        trim_blocks=True,
        lstrip_blocks=True,
        undefined=StrictUndefined,
    )
    return environment.from_string(template_source)


_INSTRUCTIONS_TEMPLATE = _load_instructions_template()


def build_instructions(
    context: RunContextWrapper[AgentContext],
    agent: Agent[AgentContext],
) -> str:
    """Render model-visible instructions from the current runner context."""
    return _INSTRUCTIONS_TEMPLATE.render(
        agent_name=agent.name,
        instruction_data=context.context.instruction_data,
    )


def build_agent(state_dir: str | Path | None = None) -> Agent[AgentContext]:
    executor = PersistentPythonExecutor(
        state_dir or os.environ.get("PYTHON_AGENT_STATE_DIR", ".agent_state")
    )
    model = os.environ.get("OPENAI_MODEL", "gpt-5.6-sol")

    haiku_agent = Agent[AgentContext](
        name="Haiku Composer",
        model=model,
        instructions=output_model_instructions(HaikuOutput),
        output_type=HaikuOutput,
    )
    compose_haikus = haiku_agent.as_tool(
        tool_name="compose_haikus",
        tool_description=(
            "Compose multiple haikus inspired by the original user's prompt."
        ),
        parameters=HaikuInput,
    )

    @function_tool
    def execute_code(code: str) -> str:
        """Execute Python code in a persistent interpreter state.

        The global dictionary named `state` is available to every snippet. All
        globals in Python's `__main__` module are restored before execution and
        serialized again afterward. The result is JSON containing `ok`, `stdout`,
        `stderr`, `error`, and `traceback`.

        Args:
            code: Complete Python source code to execute.
        """
        return executor.execute(code).to_tool_output()

    @function_tool
    async def web_fetch(
        context: RunContextWrapper[AgentContext],
        url: str,
    ) -> str:
        """Fetch a web page and return its text content.

        Args:
            url: The HTTP or HTTPS URL to fetch.
        """
        client = context.context.http_client
        if client is None:
            raise RuntimeError("web_fetch requires an HTTP client in AgentContext")

        response = await client.get(url)
        response.raise_for_status()
        return response.text[:20_000]

    @function_tool
    async def search_rag(
        context: RunContextWrapper[AgentContext],
        query: str,
        limit: int = 5,
    ) -> str:
        """Search the example ParadeDB RAG corpus using hybrid reciprocal rank fusion.

        The tool embeds the query with an OpenAI-compatible embeddings endpoint,
        then fuses ParadeDB BM25 and pgvector cosine-distance rankings.

        Args:
            query: Natural-language search query.
            limit: Maximum number of matching documents to return, from 1 to 20.
        """
        engine = context.context.rag_engine
        if engine is None:
            raise RuntimeError(
                "search_rag requires an AsyncEngine in AgentContext.rag_engine"
            )
        embedding_client = context.context.embedding_client
        if embedding_client is None:
            raise RuntimeError(
                "search_rag requires an AsyncOpenAI client in "
                "AgentContext.embedding_client"
            )

        if not query.split():
            raise ValueError("query must contain at least one search term")
        result_limit = max(1, min(limit, 20))
        embedding_response = await embedding_client.embeddings.create(
            model=context.context.embedding_model,
            input=query,
        )
        query_embedding = embedding_response.data[0].embedding
        statement = build_hybrid_rrf_query(
            query,
            query_embedding,
            limit=result_limit,
        )

        async with AsyncSession(engine) as session:
            result = await session.execute(statement)
            rows = [dict(row._mapping) for row in result]
        return json.dumps(rows, ensure_ascii=False)

    return Agent[AgentContext](
        name="Persistent Python Agent",
        model=model,
        instructions=build_instructions,
        tools=[execute_code, web_fetch, search_rag, compose_haikus],
    )


async def run(
    prompt: str,
    context: AgentContext,
    state_dir: str | Path | None = None,
) -> str:
    result = await Runner.run(
        build_agent(state_dir),
        prompt,
        context=context,
    )
    return str(result.final_output)


def _parse_context_json(value: str) -> AgentContext:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise argparse.ArgumentTypeError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise argparse.ArgumentTypeError("context JSON must be an object")
    return AgentContext(instruction_data=data)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an OpenAI agent with persistent Python and web-fetch tools."
    )
    parser.add_argument("prompt", nargs="+", help="Task for the agent")
    parser.add_argument(
        "--state-dir",
        help="Directory containing the dill session (default: .agent_state)",
    )
    parser.add_argument(
        "--context-json",
        type=_parse_context_json,
        default=AgentContext(),
        metavar="JSON",
        help="JSON object rendered into the Jinja instructions template",
    )
    args = parser.parse_args()

    async def run_cli() -> str:
        database_url = os.environ.get("DATABASE_URL")
        rag_engine = create_async_engine(database_url) if database_url else None
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(15.0),
            follow_redirects=True,
            headers={"User-Agent": "persistent-python-agent/0.1"},
        ) as http_client:
            embedding_client = AsyncOpenAI(
                api_key=(
                    os.environ.get("EMBEDDING_API_KEY")
                    or os.environ.get("OPENAI_API_KEY")
                    or "not-needed"
                ),
                base_url=(
                    os.environ.get("EMBEDDING_BASE_URL")
                    or os.environ.get("OPENAI_BASE_URL")
                ),
                http_client=http_client,
            )
            args.context_json.http_client = http_client
            args.context_json.rag_engine = rag_engine
            args.context_json.embedding_client = embedding_client
            args.context_json.embedding_model = os.environ.get(
                "EMBEDDING_MODEL",
                "text-embedding-3-small",
            )
            try:
                return await run(
                    " ".join(args.prompt),
                    context=args.context_json,
                    state_dir=args.state_dir,
                )
            finally:
                if rag_engine is not None:
                    await rag_engine.dispose()

    print(asyncio.run(run_cli()))


if __name__ == "__main__":
    main()
