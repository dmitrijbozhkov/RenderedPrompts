"""Run inline Python asynchronously in warm, in-cluster Agent Sandboxes."""

from __future__ import annotations

import argparse
import asyncio
import json
import shlex
import uuid

from k8s_agent_sandbox import AsyncSandboxClient
from k8s_agent_sandbox.models import SandboxInClusterConnectionConfig


NAMESPACE = "agent-sandbox-demo"
WARM_POOL = "python-shared"
DEFAULT_CODE = """
import os
print(f"hello from {os.uname().nodename}")
""".strip()


async def run_or_raise(sandbox: object, command: str) -> str:
    """Run a command and turn a non-zero exit into a useful local exception."""
    result = await sandbox.commands.run(command)
    if result.exit_code != 0:
        raise RuntimeError(
            f"command exited with {result.exit_code}: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code", default=DEFAULT_CODE, help="inline Python source")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="keep SandboxClaims after the example exits",
    )
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    shared_file = f"/shared/example-{uuid.uuid4().hex}.json"

    # Uses the pod's ServiceAccount for Kubernetes API calls and connects
    # directly to each sandbox through stable cluster DNS.
    connection = SandboxInClusterConnectionConfig()
    async with AsyncSandboxClient(connection_config=connection) as client:
        sandboxes = []
        try:
            writer, reader = await asyncio.gather(
                client.create_sandbox(warmpool=WARM_POOL, namespace=NAMESPACE),
                client.create_sandbox(warmpool=WARM_POOL, namespace=NAMESPACE),
            )
            sandboxes.extend((writer, reader))

            command = f"python3 -c {shlex.quote(args.code)}"
            stdout = await run_or_raise(writer, command)
            print("inline Python:", stdout)

            payload = {
                "message": "written by one sandbox and read by another",
                "writer_claim": writer.claim_name,
            }
            write_code = (
                "from pathlib import Path; "
                f"Path({shared_file!r}).write_text({json.dumps(payload)!r} + '\\n')"
            )
            await run_or_raise(writer, f"python3 -c {shlex.quote(write_code)}")

            raw = await run_or_raise(reader, f"cat {shlex.quote(shared_file)}")
            print("reader:", json.dumps(json.loads(raw), indent=2))
            print(f"shared file: {shared_file}")
        finally:
            if not args.keep:
                await asyncio.gather(
                    *(sandbox.terminate() for sandbox in reversed(sandboxes))
                )


if __name__ == "__main__":
    asyncio.run(main())
