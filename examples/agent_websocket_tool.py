"""An OpenAI Agents SDK tool backed by a WebSocket request."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from agents import Agent, Runner, function_tool
from websockets.asyncio.client import connect


async def send_websocket_request(
    websocket_url: str,
    question: str,
    *,
    request_id: str | None = None,
    timeout_seconds: float = 30,
) -> str:
    """Send a request and return the answer event with the same request ID.

    The remote service is expected to reply with::

        {
            "type": "answer",
            "request_id": "request-identifier",
            "answer": "answer text"
        }

    Unrelated events and answers for other requests are ignored.
    """
    correlation_id = request_id or str(uuid4())

    async with asyncio.timeout(timeout_seconds):
        async with connect(websocket_url) as websocket:
            await websocket.send(
                json.dumps(
                    {
                        "type": "question",
                        "request_id": correlation_id,
                        "question": question,
                    },
                    separators=(",", ":"),
                )
            )

            async for raw_message in websocket:
                event = json.loads(raw_message)
                if not isinstance(event, dict):
                    continue
                if event.get("type") != "answer":
                    continue
                if event.get("request_id") != correlation_id:
                    continue

                answer = event.get("answer")
                if not isinstance(answer, str):
                    raise TypeError("matching answer event must contain text")
                return answer

    raise ConnectionError("WebSocket closed before the matching answer arrived")


def build_agent(
    websocket_url: str,
    *,
    timeout_seconds: float = 30,
) -> Agent[Any]:
    """Build an agent with a tool that asks the remote WebSocket service."""

    @function_tool
    async def ask_remote_service(question: str) -> str:
        """Ask the remote service a question and return its answer."""
        return await send_websocket_request(
            websocket_url,
            question,
            timeout_seconds=timeout_seconds,
        )

    return Agent(
        name="WebSocket assistant",
        instructions=(
            "Use ask_remote_service when the user asks for information from "
            "the remote service, then explain its answer clearly."
        ),
        tools=[ask_remote_service],
    )


async def run(
    prompt: str,
    websocket_url: str,
    *,
    timeout_seconds: float = 30,
) -> Any:
    """Build and run the standalone WebSocket-tool agent."""
    agent = build_agent(websocket_url, timeout_seconds=timeout_seconds)
    return await Runner.run(agent, prompt)
