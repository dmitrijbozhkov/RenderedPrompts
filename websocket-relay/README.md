# FastAPI Message Relay

An in-memory WebSocket-to-WebSocket message relay. WebSockets connected to the
same channel receive each other's JSON messages. Messages with no other active
connections are discarded.

## Run locally

Requires Python 3.10 or newer.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Connect two WebSockets to the same channel:

```bash
websocat ws://localhost:8000/message/my-channel
websocat ws://localhost:8000/message/my-channel
```

Send any JSON value from either connection:

```bash
{"text":"hello"}
```

The other connection receives:

```json
{"text":"hello"}
```

Messages are also relayed to any additional connections on the same channel.
Channels are isolated, and there is no message history or persistence.

## Docker

```bash
docker build -t fastapi-message-relay .
docker run --rm -p 8000:8000 fastapi-message-relay
```

The health endpoint is available at `GET /health`.

## Test

```bash
pytest
```
