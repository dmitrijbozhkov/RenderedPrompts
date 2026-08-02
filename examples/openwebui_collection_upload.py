"""Upload a local file directly into an Open WebUI knowledge collection."""

from __future__ import annotations

import argparse
import asyncio
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Protocol


class HttpResponse(Protocol):
    def raise_for_status(self) -> None: ...

    def json(self) -> Any: ...


class AsyncHttpClient(Protocol):
    async def post(self, url: str, **kwargs: Any) -> HttpResponse: ...


async def upload_file_to_collection(
    client: AsyncHttpClient,
    file_path: str | Path,
    knowledge_id: str,
) -> dict[str, Any]:
    """Upload, process, and attach a file to an Open WebUI collection.

    ``client`` should have an Open WebUI base URL and a bearer API key already
    configured. Setting ``process_in_background`` to false makes the endpoint
    wait for extraction, embedding, and collection linking before returning.
    """
    path = Path(file_path)
    content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    metadata = json.dumps({"knowledge_id": knowledge_id})

    with path.open("rb") as file:
        response = await client.post(
            "/api/v1/files/",
            params={
                "process": "true",
                "process_in_background": "false",
            },
            data={"metadata": metadata},
            files={"file": (path.name, file, content_type)},
        )

    response.raise_for_status()
    result = response.json()
    if not isinstance(result, dict) or not isinstance(result.get("id"), str):
        raise ValueError("Open WebUI upload response did not contain a file ID")
    return result


async def main() -> None:
    """Upload the command-line file using environment-based configuration."""
    import httpx

    parser = argparse.ArgumentParser(
        description="Upload a file into an Open WebUI knowledge collection.",
    )
    parser.add_argument("file", type=Path, help="Local file to upload")
    parser.add_argument("knowledge_id", help="Target knowledge collection ID")
    args = parser.parse_args()

    base_url = os.environ["OPENWEBUI_URL"].rstrip("/")
    api_key = os.environ["OPENWEBUI_API_KEY"]

    async with httpx.AsyncClient(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
        timeout=300,
    ) as client:
        uploaded_file = await upload_file_to_collection(
            client,
            args.file,
            args.knowledge_id,
        )

    print(
        json.dumps(
            {
                "id": uploaded_file["id"],
                "filename": uploaded_file.get("filename"),
                "knowledge_id": args.knowledge_id,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
