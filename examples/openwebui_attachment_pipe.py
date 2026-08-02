"""
title: Attachment Forwarding Pipe
author: example
version: 0.1.0
requirements: httpx
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

try:
    from pydantic import BaseModel, Field
except ImportError:  # Allows testing helpers outside an Open WebUI installation.
    class BaseModel:
        pass

    def Field(default: Any, **_: Any) -> Any:  # noqa: N802
        return default


def _is_http_url(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _attachment_key(item: dict[str, Any]) -> tuple[str, ...]:
    """Build a stable key for references repeated in multiple body locations."""
    return tuple(
        str(item.get(field, ""))
        for field in ("type", "id", "url", "name", "collection_name")
    )


def extract_last_message_images(body: dict[str, Any]) -> list[str]:
    """Return image URLs or Base64 data URLs from the final message."""
    messages = body.get("messages")
    if not isinstance(messages, list) or not messages:
        return []
    last_message = messages[-1]
    if not isinstance(last_message, dict):
        return []
    content = last_message.get("content")
    if not isinstance(content, list):
        return []

    images: list[str] = []
    for part in content:
        if not isinstance(part, dict) or part.get("type") != "image_url":
            continue
        image_url = part.get("image_url")
        # Open WebUI normally uses {"image_url": {"url": "data:image/..."}}.
        # Accept a direct string too, since some OpenAI-compatible clients emit
        # that shorter representation.
        url = image_url.get("url") if isinstance(image_url, dict) else image_url
        if isinstance(url, str) and (
            url.startswith("data:image/") or _is_http_url(url)
        ):
            images.append(url)
    return images


def extract_attachments(body: dict[str, Any]) -> dict[str, list[Any]]:
    """Extract images and classify attachment references from one request."""
    metadata = body.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    messages = body.get("messages")
    messages = messages if isinstance(messages, list) else []
    last_message = messages[-1] if messages and isinstance(messages[-1], dict) else {}

    # Open WebUI can expose the same attachment references in multiple places:
    #
    # * body["files"] is the current request's top-level attachment list.
    # * body["metadata"]["files"] is the list after internal middleware moves
    #   request-only fields into metadata.
    # * body["messages"][-1]["files"] supports request shapes that retain the
    #   references directly on the latest chat message.
    #
    # These values are descriptors (IDs, names, types, URLs, and collection
    # names), not uploaded file bytes and not retrieved RAG chunk contents.
    candidates: list[Any] = []
    for source in (
        body.get("files"),
        metadata.get("files"),
        last_message.get("files"),
    ):
        if isinstance(source, list):
            candidates.extend(source)

    unique_items: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        key = _attachment_key(candidate)
        if key not in seen:
            seen.add(key)
            unique_items.append(candidate)

    attachments: dict[str, list[Any]] = {
        "files": [],
        "collections": [],
        "websites": [],
        # Images are not Open WebUI file descriptors. They arrive inline in the
        # final message, usually as Base64 data URLs, and are forwarded as-is.
        "images": extract_last_message_images(body),
    }
    for item in unique_items:
        attachment_type = str(item.get("type", "")).lower()

        # Website attachments may be explicitly typed as web/url/website. Newer
        # Open WebUI versions can also represent processed web pages as "text"
        # items backed by collection names, so a real HTTP(S) field or name is
        # the strongest signal that the original attachment is a website.
        website_url = next(
            (
                value
                for value in (item.get("url"), item.get("name"))
                if _is_http_url(value)
            ),
            None,
        )
        if attachment_type in {"web", "url", "website"} or website_url:
            attachments["websites"].append(item)
        elif (
            attachment_type == "collection"
            or item.get("collection_name")
            or item.get("collection_names")
        ):
            attachments["collections"].append(item)
        else:
            # File references normally include an Open WebUI file ID, filename,
            # MIME metadata, and sometimes an internal content URL. This example
            # forwards that reference as received; it does not download content.
            attachments["files"].append(item)

    return attachments


class Pipe:
    """Forward every request's attachment references to an external API."""

    class Valves(BaseModel):
        API_URL: str = Field(
            default="http://example-api:8000/v1/model-request",
            description="External API endpoint that receives attachment metadata.",
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
        """Forward request-scoped attachment references and return API output."""
        import httpx

        attachments = extract_attachments(body)
        messages = body.get("messages")
        messages = messages if isinstance(messages, list) else []

        payload = {
            # Selected Pipe/model identifier for routing or audit purposes.
            "model": body.get("model"),
            # Whether Open WebUI requested a streamed response. This example API
            # still responds once; add client.stream() if upstream supports SSE.
            "stream_requested": bool(body.get("stream", False)),
            # Only the current user's opaque Open WebUI ID is forwarded. Email,
            # name, role, and other __user__ fields are intentionally excluded.
            "user_id": __user__.get("id") if __user__ else None,
            # The latest message is included so the external API knows which
            # prompt the attached resources apply to. Earlier history is omitted.
            "message": messages[-1] if messages else None,
            # File/collection/web values are descriptors. Image values are URLs
            # or inline Base64 data URLs extracted from the final message.
            "attachments": attachments,
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

        # A minimal example API can return {"answer": "..."}. If it returns a
        # different JSON structure, Open WebUI receives that structure unchanged.
        if isinstance(result, dict) and isinstance(result.get("answer"), str):
            return result["answer"]
        return result
