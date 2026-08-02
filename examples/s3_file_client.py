"""Use the S3 Python API with SeaweedFS or another S3-compatible store."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Protocol


class S3Client(Protocol):
    """Subset of the boto3 S3 client used by this example."""

    def upload_file(self, filename: str, bucket: str, key: str) -> Any: ...

    def download_file(self, bucket: str, key: str, filename: str) -> Any: ...

    def delete_object(self, *, Bucket: str, Key: str) -> Any: ...

    def head_object(self, *, Bucket: str, Key: str) -> Any: ...

    def get_paginator(self, operation_name: str) -> Any: ...


def create_s3_client() -> S3Client:
    """Create an S3 client from environment variables.

    Required variables are ``S3_ENDPOINT_URL``, ``S3_ACCESS_KEY_ID``, and
    ``S3_SECRET_ACCESS_KEY``. The endpoint for an in-cluster SeaweedFS release
    is commonly ``http://seaweedfs-s3:8333``.
    """
    import boto3
    from botocore.config import Config

    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["S3_SECRET_ACCESS_KEY"],
        region_name=os.getenv("S3_REGION", "us-east-1"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def upload_file(
    client: S3Client,
    bucket: str,
    object_key: str,
    source: str | Path,
) -> None:
    """Upload a local file to an S3 object key."""
    client.upload_file(str(source), bucket, object_key)


def download_file(
    client: S3Client,
    bucket: str,
    object_key: str,
    destination: str | Path,
) -> None:
    """Download an S3 object to a local file."""
    client.download_file(bucket, object_key, str(destination))


def list_items_in_path(
    client: S3Client,
    bucket: str,
    path: str = "",
) -> list[str]:
    """List every object key beneath an S3 prefix, across all pages."""
    paginator = client.get_paginator("list_objects_v2")
    return [
        item["Key"]
        for page in paginator.paginate(Bucket=bucket, Prefix=path)
        for item in page.get("Contents", [])
    ]


def delete_file(client: S3Client, bucket: str, object_key: str) -> None:
    """Delete an object. S3 treats a missing object as a successful delete."""
    client.delete_object(Bucket=bucket, Key=object_key)


def file_exists(client: S3Client, bucket: str, object_key: str) -> bool:
    """Return whether an object exists, while preserving unexpected errors."""
    try:
        client.head_object(Bucket=bucket, Key=object_key)
    except Exception as error:
        response = getattr(error, "response", {})
        error_details = response.get("Error", {})
        code = str(error_details.get("Code", ""))
        status = response.get("ResponseMetadata", {}).get("HTTPStatusCode")
        if code in {"404", "NoSuchKey", "NotFound"} or status == 404:
            return False
        raise
    return True


if __name__ == "__main__":
    s3 = create_s3_client()
    bucket_name = "artefacts"
    key = "examples/example.txt"
    local_source = Path("example.txt")
    local_download = Path("downloaded-example.txt")

    upload_file(s3, bucket_name, key, local_source)
    print(list_items_in_path(s3, bucket_name, "examples/"))
    print(f"Exists after upload: {file_exists(s3, bucket_name, key)}")
    download_file(s3, bucket_name, key, local_download)
    delete_file(s3, bucket_name, key)
    print(f"Exists after delete: {file_exists(s3, bucket_name, key)}")
