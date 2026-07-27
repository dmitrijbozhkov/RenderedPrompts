import asyncio
from typing import Any

import httpx

from app.main import ConnectionManager, app


class FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = False
        self.messages: list[dict[str, Any]] = []

    async def accept(self) -> None:
        self.accepted = True

    async def send_json(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


async def request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)


def test_health() -> None:
    response = asyncio.run(request("GET", "/health"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_message_is_delivered_to_the_correct_channel() -> None:
    async def scenario() -> None:
        relay = ConnectionManager()
        sender = FakeWebSocket()
        news = FakeWebSocket()
        sports = FakeWebSocket()
        await relay.connect("news", sender)  # type: ignore[arg-type]
        await relay.connect("news", news)  # type: ignore[arg-type]
        await relay.connect("sports", sports)  # type: ignore[arg-type]

        await relay.relay(
            "news", sender, {"data": {"headline": "Hello"}}  # type: ignore[arg-type]
        )

        assert sender.messages == []
        assert news.messages == [{"data": {"headline": "Hello"}}]
        assert sports.messages == []

    asyncio.run(scenario())


def test_message_is_relayed_to_all_other_channel_connections() -> None:
    async def scenario() -> None:
        relay = ConnectionManager()
        first = FakeWebSocket()
        second = FakeWebSocket()
        third = FakeWebSocket()
        await relay.connect("shared", first)  # type: ignore[arg-type]
        await relay.connect("shared", second)  # type: ignore[arg-type]
        await relay.connect("shared", third)  # type: ignore[arg-type]

        await relay.relay(
            "shared", first, {"data": "hello"}  # type: ignore[arg-type]
        )

        assert first.messages == []
        assert second.messages == [{"data": "hello"}]
        assert third.messages == [{"data": "hello"}]

    asyncio.run(scenario())


def test_message_without_consumers_is_discarded() -> None:
    async def scenario() -> None:
        relay = ConnectionManager()
        sender = FakeWebSocket()
        await relay.connect("empty", sender)  # type: ignore[arg-type]

        await relay.relay("empty", sender, [1, 2, 3])  # type: ignore[arg-type]

        assert sender.messages == []

    asyncio.run(scenario())
