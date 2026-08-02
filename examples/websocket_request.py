"""Coordinate an HTTP request with a WebSocket response."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

import httpx
from websockets.asyncio.client import connect
from websockets.typing import Data


async def send_request_and_wait_for_message(
    websocket_url: str,
    request_url: str,
    *,
    method: str = "POST",
    json: Any = None,
) -> tuple[httpx.Response, Data]:
    """Send an HTTP request and wait concurrently for one WebSocket message.

    The WebSocket connection is established before the HTTP request is sent so
    that a fast server response cannot be missed.
    """
    async with connect(websocket_url) as websocket:
        async with httpx.AsyncClient() as client:
            response, message = await asyncio.gather(
                client.request(method, request_url, json=json),
                websocket.recv(),
            )

    response.raise_for_status()
    return response, message


async def send_request_and_collect_messages(
    websocket_url: str,
    request_url: str,
    *,
    client: httpx.AsyncClient,
    method: str = "POST",
    json: Any = None,
) -> tuple[httpx.Response, list[Data]]:
    """Collect WebSocket messages while an HTTP request is in progress.

    Pass an application-lifetime ``AsyncClient`` when calling this function
    from an async HTTP server. The WebSocket is connected before the request
    starts, preventing early messages from being missed.
    """
    messages: list[Data] = []

    async with connect(websocket_url) as websocket:

        async def collect_messages() -> None:
            async for message in websocket:
                messages.append(message)

        collector = asyncio.create_task(collect_messages())
        try:
            response = await client.request(method, request_url, json=json)
            response.raise_for_status()
        finally:
            collector.cancel()
            with suppress(asyncio.CancelledError):
                await collector

    return response, messages
