"""
title: Brave LLM Context OpenWebUI Pipe
author: example
version: 0.2.0
requirements: openai-agents>=0.2, httpx>=0.27, pydantic>=2

Web research agent backed by Brave's LLM Context API.

Paste this file into OpenWebUI's Functions editor to use it as a Pipe. Search
results are attached to the assistant message as clickable website references.

Set ``OPENAI_API_KEY`` and ``BRAVE_SEARCH_API_KEY``, then run::

    python examples/brave_llm_context_agent.py "What changed in Python 3.14?"
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Any, Awaitable, Callable

import httpx
from agents import Agent, OpenAIProvider, RunConfig, Runner, function_tool
from pydantic import BaseModel, Field

BRAVE_LLM_CONTEXT_URL = "https://api.search.brave.com/res/v1/llm/context"
EventEmitter = Callable[[dict[str, Any]], Awaitable[None]]


def build_website_reference(source: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one Brave result into an OpenWebUI citation event."""
    url = source.get("url")
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return None

    title = source.get("title")
    title = title.strip() if isinstance(title, str) and title.strip() else url
    snippets = source.get("snippets")
    if isinstance(snippets, list):
        documents = [item.strip() for item in snippets if isinstance(item, str) and item.strip()]
    elif isinstance(snippets, str) and snippets.strip():
        documents = [snippets.strip()]
    else:
        documents = [title]

    return {
        "type": "citation",
        "data": {
            "source": {"name": title, "id": url},
            "document": documents,
            "metadata": [
                {"source": url, "name": title, "url": url}
                for _ in documents
            ],
        },
    }


class BraveLlmContextAgent:
    """Standalone agent that can retrieve LLM-ready web context."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 30.0,
        event_emitter: EventEmitter | None = None,
        openai_api_key: str | None = None,
        model: str = "gpt-5-mini",
    ) -> None:
        if not api_key:
            raise ValueError("A Brave Search API key is required")
        self.api_key = api_key
        self.client = client
        self.timeout_seconds = timeout_seconds
        self.event_emitter = event_emitter
        self.openai_api_key = openai_api_key
        self.model = model

    async def search_web(self, query: str) -> str:
        """Fetch extracted web context from Brave for one search query."""
        headers = {
            "Accept": "application/json",
            "X-Subscription-Token": self.api_key,
        }
        params = {
            "q": query,
            "count": 10,
            "maximum_number_of_urls": 10,
            "maximum_number_of_tokens": 4096,
        }

        if self.client is not None:
            response = await self.client.get(
                BRAVE_LLM_CONTEXT_URL,
                headers=headers,
                params=params,
                timeout=self.timeout_seconds,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    BRAVE_LLM_CONTEXT_URL,
                    headers=headers,
                    params=params,
                    timeout=self.timeout_seconds,
                )

        response.raise_for_status()
        payload = response.json()
        generic = payload.get("grounding", {}).get("generic", [])
        if not generic:
            return "No relevant web context was found."

        if self.event_emitter is not None:
            for source in generic:
                if not isinstance(source, dict):
                    continue
                reference = build_website_reference(source)
                if reference is not None:
                    await self.event_emitter(reference)

        # JSON preserves each snippet's association with its source URL and title.
        return json.dumps(generic, ensure_ascii=False)

    def build(self) -> Agent[Any]:
        """Construct the OpenAI Agents SDK agent and its Brave search tool."""

        @function_tool
        async def web_search(query: str) -> str:
            """Search the web and return extracted passages with source URLs."""
            return await self.search_web(query)

        return Agent(
            name="Brave web research assistant",
            instructions=(
                "You are a web research assistant. Use web_search for claims that "
                "need current or external information. Base the answer on the "
                "returned passages, cite source URLs inline, and say when the "
                "search context does not support a claim.\n\n"
                "Environment:\n"
                "web_search uses Brave Search's LLM Context API and returns JSON "
                "containing extracted web passages and their source metadata."
            ),
            tools=[web_search],
            model=self.model,
        )

    async def run(self, prompt: str) -> Any:
        """Run the agent on a user prompt."""
        if self.openai_api_key:
            return await Runner.run(
                self.build(),
                prompt,
                run_config=RunConfig(
                    model_provider=OpenAIProvider(api_key=self.openai_api_key),
                    workflow_name="Brave LLM Context OpenWebUI Pipe",
                ),
            )
        return await Runner.run(self.build(), prompt)


def _latest_user_text(body: dict[str, Any]) -> str:
    messages = body.get("messages")
    if not isinstance(messages, list):
        raise ValueError("body.messages must be a list")
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
    raise ValueError("No non-empty user message was found")


class Pipe:
    """OpenWebUI Pipe that renders Brave results as message references."""

    class Valves(BaseModel):
        OPENAI_API_KEY: str = Field(
            default="", description="OpenAI API key; environment fallback is supported"
        )
        BRAVE_SEARCH_API_KEY: str = Field(
            default="", description="Brave Search API subscription key"
        )
        MODEL: str = Field(default="gpt-5-mini", description="OpenAI model name")
        SEARCH_TIMEOUT_SECONDS: float = Field(default=30.0, ge=1)

    def __init__(self) -> None:
        self.valves = self.Valves()

    def pipes(self) -> list[dict[str, str]]:
        return [{"id": "brave-context", "name": "Brave Web Research Agent"}]

    async def pipe(
        self,
        body: dict[str, Any],
        __event_emitter__: EventEmitter | None = None,
    ) -> str:
        brave_key = self.valves.BRAVE_SEARCH_API_KEY or os.environ.get(
            "BRAVE_SEARCH_API_KEY", ""
        )
        openai_key = self.valves.OPENAI_API_KEY or os.environ.get("OPENAI_API_KEY", "")
        if not brave_key:
            raise RuntimeError("Configure BRAVE_SEARCH_API_KEY in the Pipe valves")
        if not openai_key:
            raise RuntimeError("Configure OPENAI_API_KEY in the Pipe valves")

        agent = BraveLlmContextAgent(
            brave_key,
            timeout_seconds=self.valves.SEARCH_TIMEOUT_SECONDS,
            event_emitter=__event_emitter__,
            openai_api_key=openai_key,
            model=self.valves.MODEL,
        )
        result = await agent.run(_latest_user_text(body))
        return str(result.final_output)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", help="Question for the research agent")
    args = parser.parse_args()

    brave_api_key = os.environ.get("BRAVE_SEARCH_API_KEY", "")
    agent = BraveLlmContextAgent(brave_api_key)
    result = await agent.run(args.prompt)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
