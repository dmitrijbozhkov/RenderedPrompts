"""Resolve OpenAI Agents SDK tool approvals through a WebSocket."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from agents import Agent, Runner, function_tool
from websockets.asyncio.client import connect
from websockets.asyncio.connection import Connection


class ApprovalInterruption(Protocol):
    """Fields used from an Agents SDK ``ToolApprovalItem``."""

    agent: Agent[Any]
    arguments: str | None
    call_id: str
    name: str | None


@dataclass(frozen=True)
class ApprovalDecision:
    """A correlated decision returned by the approval service."""

    decision: Literal["approved", "rejected"]
    reason: str | None = None


async def request_tool_approval(
    websocket: Connection,
    interruption: ApprovalInterruption,
) -> ApprovalDecision:
    """Send one approval request and wait for its correlated decision event.

    Expected response events have this form::

        {
            "type": "tool_approval_decision",
            "call_id": "call_123",
            "decision": "approved" | "rejected",
            "reason": "optional explanation"
        }

    Other event types and decisions for other call IDs are ignored.
    """
    await websocket.send(
        json.dumps(
            {
                "type": "tool_approval_requested",
                "call_id": interruption.call_id,
                "agent": interruption.agent.name,
                "tool": interruption.name,
                "arguments": interruption.arguments,
            },
            separators=(",", ":"),
        )
    )

    async for raw_message in websocket:
        event = json.loads(raw_message)
        if not isinstance(event, dict):
            continue
        if event.get("type") != "tool_approval_decision":
            continue
        if event.get("call_id") != interruption.call_id:
            continue

        decision = event.get("decision")
        if decision not in {"approved", "rejected"}:
            raise ValueError("approval decision must be 'approved' or 'rejected'")
        reason = event.get("reason")
        if reason is not None and not isinstance(reason, str):
            raise TypeError("approval reason must be a string")
        return ApprovalDecision(decision=decision, reason=reason)

    raise ConnectionError("WebSocket closed before an approval decision arrived")


async def run_with_websocket_approvals(
    agent: Agent[Any],
    prompt: str,
    websocket_url: str,
) -> Any:
    """Run an agent, resolving every tool interruption over a WebSocket."""
    async with connect(websocket_url) as websocket:
        result = await Runner.run(agent, prompt)

        while result.interruptions:
            state = result.to_state()

            for interruption in result.interruptions:
                decision = await request_tool_approval(websocket, interruption)
                if decision.decision == "approved":
                    state.approve(interruption)
                elif decision.reason:
                    state.reject(
                        interruption,
                        rejection_message=decision.reason,
                    )
                else:
                    state.reject(interruption)

            result = await Runner.run(agent, state)

    return result


@function_tool(needs_approval=True)
async def delete_record(record_id: str) -> dict[str, str]:
    """Delete a record after a reviewer approves the tool call."""
    return {"record_id": record_id, "status": "deleted"}


def build_agent() -> Agent[Any]:
    """Build the standalone example agent."""
    return Agent(
        name="Record manager",
        instructions=(
            "Manage records with the available tools. Clearly report when "
            "a requested operation is rejected."
        ),
        tools=[delete_record],
    )


async def run(prompt: str, websocket_url: str) -> Any:
    """Build and run the example agent with WebSocket-based approvals."""
    return await run_with_websocket_approvals(
        build_agent(),
        prompt,
        websocket_url,
    )
