"""Standalone OpenAI Agents SDK example for visual question answering.

The image may be a public HTTP(S) URL or a local PNG, JPEG, WEBP, or
non-animated GIF. Set ``OPENAI_API_KEY``, then run::

    python examples/visual_question_answering_agent.py image.png \
        "What objects are visible, and what are they doing?"
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import mimetypes
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agents import Agent, Runner

SUPPORTED_IMAGE_TYPES = {
    "image/gif",
    "image/jpeg",
    "image/png",
    "image/webp",
}


def build_agent() -> Agent[Any]:
    """Build a visual question answering agent."""
    return Agent(
        name="Visual question answering assistant",
        instructions=(
            "Answer questions about the supplied image. Distinguish clearly "
            "between what is directly visible and what you infer. Mention "
            "uncertainty when details are ambiguous or too small to inspect."
        ),
    )


def is_image_url(image: str) -> bool:
    """Return whether the image argument is an HTTP(S) URL."""
    parsed = urlparse(image)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


async def image_to_data_url(image_path: Path) -> str:
    """Encode a supported local image as a Base64 data URL."""
    path = image_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Image file does not exist: {image_path}")

    media_type, _ = mimetypes.guess_type(path.name)
    if media_type not in SUPPORTED_IMAGE_TYPES:
        supported = ", ".join(sorted(SUPPORTED_IMAGE_TYPES))
        raise ValueError(f"Unsupported image type {media_type!r}; expected {supported}")

    image_bytes = await asyncio.to_thread(path.read_bytes)
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{media_type};base64,{encoded}"


async def build_input(question: str, image: str) -> list[dict[str, Any]]:
    """Build one multimodal Agents SDK input message."""
    image_url = image if is_image_url(image) else await image_to_data_url(Path(image))
    return [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": question},
                {
                    "type": "input_image",
                    "image_url": image_url,
                    "detail": "auto",
                },
            ],
        }
    ]


async def run(question: str, image: str) -> Any:
    """Ask the agent a question about an image."""
    agent_input = await build_input(question, image)
    return await Runner.run(build_agent(), agent_input)


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Local image path or public HTTP(S) URL")
    parser.add_argument("question", help="Question to answer about the image")
    args = parser.parse_args()

    result = await run(args.question, args.image)
    print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main())
