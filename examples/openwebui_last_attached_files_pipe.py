"""
title: Latest User Attachments Pipe
author: example
version: 0.1.0
requirements: httpx
"""

from __future__ import annotations

from typing import Any

try:
    from pydantic import BaseModel, Field
except ImportError:  # Allows testing helpers outside an Open WebUI installation.
    class BaseModel:
        pass

    def Field(default: Any, **_: Any) -> Any:  # noqa: N802
        return default


def get_last_attached_files(body: dict[str, Any]) -> list[dict[str, Any]]:
    """Return file references attached directly to the final user message."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        raise ValueError("Expected at least one message")

    last_message = messages[-1]
    if not isinstance(last_message, dict):
        raise TypeError("Expected the final message to be an object")
    if last_message.get("role") != "user":
        raise ValueError("Expected the final message to be from the user")

    # This reads only references stored on the final user message. It does not
    # merge body["files"] or body["metadata"]["files"], because those locations
    # can contain model-level knowledge or references added by middleware.
    files = last_message.get("files")
    if files is None:
        return []
    if not isinstance(files, list):
        raise TypeError("Expected the final user message's files to be a list")

    # Open WebUI attachment entries are descriptor objects containing fields
    # such as id, name, type, URL, or collection names. No file bytes or RAG
    # chunks are read or sent by this example.
    return [item for item in files if isinstance(item, dict)]


class Pipe:
    """Forward only the final user message's attachment references."""

    class Valves(BaseModel):
        API_URL: str = Field(
            default="http://example-api:8000/v1/message-attachments",
            description="API that receives the latest attachment references.",
        )
        API_KEY: str = Field(
            default="",
            description="Optional bearer token for the external API.",
        )
        TIMEOUT_SECONDS: float = Field(default=60, ge=1)

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any] | None = None,
    ) -> Any:
        """Send latest file references to the API and return its answer."""
        import httpx

        last_message = body["messages"][-1]
        payload = {
            # Opaque ID of the Open WebUI user making this request.
            "user_id": __user__.get("id") if __user__ else None,
            # Text or multimodal content from the final user message.
            "message": last_message.get("content"),
            # Only references attached directly to that final user message.
            "files": get_last_attached_files(body),
        }

        headers = {"Accept": "application/json"}
        if self.valves.API_KEY:
            headers["Authorization"] = f"Bearer {self.valves.API_KEY}"

        async with httpx.AsyncClient(timeout=self.valves.TIMEOUT_SECONDS) as client:
            response = await client.post(
                self.valves.API_URL,
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            result = response.json()

        if isinstance(result, dict) and isinstance(result.get("answer"), str):
            return result["answer"]
        return result
