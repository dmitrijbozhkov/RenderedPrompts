"""Listen for typed JSON events and print their contents."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

from websockets.asyncio.client import connect


def event_contents(message: str | bytes) -> Any:
    """Parse one event and return its contents."""
    event = json.loads(message)
    if not isinstance(event, dict):
        raise TypeError("event must be a JSON object")
    if not isinstance(event.get("type"), str):
        raise TypeError("event must contain a string 'type' field")
    if "contents" not in event:
        raise KeyError("event must contain a 'contents' field")
    return event["contents"]


def print_contents(contents: Any) -> None:
    """Print strings directly and preserve structure for other JSON values."""
    if isinstance(contents, str):
        print(contents, flush=True)
    else:
        print(
            json.dumps(contents, ensure_ascii=False, separators=(",", ":")),
            flush=True,
        )


async def listen(url: str) -> None:
    """Connect to a WebSocket endpoint and process events until disconnected."""
    async with connect(url) as websocket:
        async for message in websocket:
            try:
                print_contents(event_contents(message))
            except (json.JSONDecodeError, KeyError, TypeError) as error:
                print(f"Ignoring invalid event: {error}", file=sys.stderr, flush=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print the contents field from typed WebSocket JSON events.",
    )
    parser.add_argument(
        "url",
        nargs="?",
        default="ws://localhost:8000/events",
        help="WebSocket endpoint (default: %(default)s)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        asyncio.run(listen(args.url))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
