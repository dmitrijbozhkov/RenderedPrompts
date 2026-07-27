from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

import dill


def _persist_main(session_path: Path) -> None:
    session_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_name = tempfile.mkstemp(
        prefix="session-", suffix=".tmp", dir=session_path.parent
    )
    os.close(fd)
    temporary_path = Path(temporary_name)
    try:
        dill.dump_module(str(temporary_path), module=sys.modules["__main__"])
        os.replace(temporary_path, session_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def main() -> None:
    session_path = Path(sys.argv[1])
    result_path = Path(sys.argv[2])
    code = sys.stdin.read()
    main_module = sys.modules["__main__"]

    stdout = io.StringIO()
    stderr = io.StringIO()
    error: str | None = None
    formatted_traceback: str | None = None

    if session_path.exists():
        dill.load_module(str(session_path), module=main_module)

    # This object is deliberately a normal dictionary available to every snippet.
    # It is part of __main__, so dill persists it along with imports, functions,
    # classes, and other globals created by executed code.
    main_module.__dict__.setdefault("state", {})

    try:
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            exec(compile(code, "<agent-code>", "exec"), main_module.__dict__)
    except BaseException as exc:
        error = f"{type(exc).__name__}: {exc}"
        formatted_traceback = traceback.format_exc()

    try:
        _persist_main(session_path)
    except BaseException as exc:
        serialization_error = f"{type(exc).__name__}: {exc}"
        error = (
            f"{error}; state serialization failed: {serialization_error}"
            if error
            else f"State serialization failed: {serialization_error}"
        )
        formatted_traceback = traceback.format_exc()

    result_path.write_text(
        json.dumps(
            {
                "ok": error is None,
                "stdout": stdout.getvalue(),
                "stderr": stderr.getvalue(),
                "error": error,
                "traceback": formatted_traceback,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
