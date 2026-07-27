from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from filelock import FileLock


@dataclass(frozen=True)
class ExecutionResult:
    ok: bool
    stdout: str
    stderr: str
    error: str | None = None
    traceback: str | None = None

    @classmethod
    def from_dict(cls, value: dict[str, object]) -> "ExecutionResult":
        return cls(
            ok=bool(value["ok"]),
            stdout=str(value.get("stdout", "")),
            stderr=str(value.get("stderr", "")),
            error=str(value["error"]) if value.get("error") is not None else None,
            traceback=(
                str(value["traceback"])
                if value.get("traceback") is not None
                else None
            ),
        )

    def to_tool_output(self) -> str:
        """Return stable JSON so the model can reliably inspect success and errors."""
        return json.dumps(
            {
                "ok": self.ok,
                "stdout": self.stdout,
                "stderr": self.stderr,
                "error": self.error,
                "traceback": self.traceback,
            },
            ensure_ascii=False,
        )


class PersistentPythonExecutor:
    """Execute snippets in a dill-persisted Python ``__main__`` module."""

    def __init__(self, state_dir: str | Path = ".agent_state") -> None:
        self.state_dir = Path(state_dir).expanduser().resolve()
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.session_path = self.state_dir / "session.pkl"
        self.lock = FileLock(self.state_dir / "session.lock")

    def execute(self, code: str) -> ExecutionResult:
        if not code.strip():
            return ExecutionResult(
                ok=False,
                stdout="",
                stderr="",
                error="ValueError: code must not be empty",
            )

        result_fd, result_name = tempfile.mkstemp(
            prefix="result-", suffix=".json", dir=self.state_dir
        )
        os.close(result_fd)
        result_path = Path(result_name)

        command = [
            sys.executable,
            "-c",
            "from persistent_python_agent._worker import main; main()",
            str(self.session_path),
            str(result_path),
        ]

        try:
            with self.lock:
                completed = subprocess.run(
                    command,
                    input=code,
                    text=True,
                    capture_output=True,
                    check=False,
                )

                if completed.returncode != 0:
                    return ExecutionResult(
                        ok=False,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                        error=(
                            "Python worker failed with exit code "
                            f"{completed.returncode}"
                        ),
                    )

                try:
                    payload = json.loads(result_path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    return ExecutionResult(
                        ok=False,
                        stdout=completed.stdout,
                        stderr=completed.stderr,
                        error=f"Invalid worker response: {type(exc).__name__}: {exc}",
                    )
                return ExecutionResult.from_dict(payload)
        finally:
            result_path.unlink(missing_ok=True)
