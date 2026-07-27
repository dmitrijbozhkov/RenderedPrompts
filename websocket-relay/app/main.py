from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect


class ConnectionManager:
    """Tracks websocket connections and relays messages between them."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def connect(self, channel_id: str, websocket: WebSocket) -> None:
        await websocket.accept()
        async with self._lock:
            self._connections[channel_id].add(websocket)

    async def disconnect(self, channel_id: str, websocket: WebSocket) -> None:
        async with self._lock:
            connections = self._connections.get(channel_id)
            if connections is None:
                return
            connections.discard(websocket)
            if not connections:
                self._connections.pop(channel_id, None)

    async def relay(
        self, channel_id: str, sender: WebSocket, message: Any
    ) -> None:
        async with self._lock:
            connections = tuple(
                connection
                for connection in self._connections.get(channel_id, ())
                if connection is not sender
            )

        if not connections:
            return

        results = await asyncio.gather(
            *(connection.send_json(message) for connection in connections),
            return_exceptions=True,
        )

        failed = [
            connection
            for connection, result in zip(connections, results, strict=True)
            if isinstance(result, Exception)
        ]
        for connection in failed:
            await self.disconnect(channel_id, connection)


app = FastAPI(title="Message Relay", version="1.0.0")
manager = ConnectionManager()


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.websocket("/message/{channel_id}")
async def relay(websocket: WebSocket, channel_id: str) -> None:
    await manager.connect(channel_id, websocket)
    try:
        while True:
            message = await websocket.receive_json()
            await manager.relay(channel_id, websocket, message)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(channel_id, websocket)
