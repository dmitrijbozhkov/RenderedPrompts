import json

import pytest

from examples.websocket_event_client import event_contents


@pytest.mark.parametrize(
    ("event_type", "contents"),
    [
        ("message", "hello"),
        ("progress", {"completed": 3, "total": 5}),
        ("finished", ["one", "two"]),
    ],
)
def test_event_contents_accepts_different_types(
    event_type: str,
    contents: object,
) -> None:
    message = json.dumps({"type": event_type, "contents": contents})

    assert event_contents(message) == contents


@pytest.mark.parametrize(
    "message",
    [
        "[]",
        '{"contents":"missing type"}',
        '{"type":1,"contents":"invalid type"}',
        '{"type":"message"}',
    ],
)
def test_event_contents_rejects_invalid_events(message: str) -> None:
    with pytest.raises((KeyError, TypeError)):
        event_contents(message)
