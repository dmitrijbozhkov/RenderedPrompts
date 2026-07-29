"""A constrained command-line tool for read-only repository exploration."""

import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from agents import RunContextWrapper, function_tool


ALLOWED_COMMANDS = frozenset(
    {
        "cat",
        "cut",
        "find",
        "grep",
        "head",
        "ls",
        "pwd",
        "rg",
        "seq",
        "sort",
        "tail",
        "wc",
    }
)
CONTROL_OPERATORS = frozenset({";", "&&", "||", "&", "<", ">", "<<", ">>"})
FORBIDDEN_OPTIONS = {
    "find": frozenset(
        {
            "-delete",
            "-exec",
            "-execdir",
            "-fls",
            "-fprint",
            "-fprint0",
            "-fprintf",
            "-ok",
            "-okdir",
            "-L",
        }
    ),
    "grep": frozenset({"-R", "--dereference-recursive"}),
    "rg": frozenset({"-L", "--follow"}),
    "sort": frozenset({"-o", "--output"}),
}
PATH_OPTION_PREFIXES = {
    "find": ("-fls", "-fprint", "-fprintf"),
    "grep": ("-f",),
    "rg": ("-f",),
    "sort": ("-o",),
}


class ReadonlyShellError(ValueError):
    """Raised when a command violates the read-only shell policy."""


@dataclass(frozen=True)
class ScoutContext:
    """Trusted per-run configuration for repository scouting."""

    directory: Path
    timeout_seconds: float = 10.0
    max_output_bytes: int = 100_000

    def __post_init__(self) -> None:
        resolved = Path(self.directory).expanduser().resolve(strict=True)
        if not resolved.is_dir():
            raise NotADirectoryError(resolved)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.max_output_bytes <= 0:
            raise ValueError("max_output_bytes must be positive")
        object.__setattr__(self, "directory", resolved)


def _parse_pipeline(command: str) -> list[list[str]]:
    if not command.strip():
        raise ReadonlyShellError("command cannot be empty")
    if "\n" in command or "\x00" in command:
        raise ReadonlyShellError("newlines and null bytes are not allowed")

    lexer = shlex.shlex(command, posix=True, punctuation_chars="|&;<>")
    lexer.whitespace_split = True
    tokens = list(lexer)
    if any(token in CONTROL_OPERATORS for token in tokens):
        raise ReadonlyShellError("redirection, chaining, and background execution are not allowed")

    pipeline: list[list[str]] = [[]]
    for token in tokens:
        if token == "|":
            if not pipeline[-1]:
                raise ReadonlyShellError("pipeline contains an empty command")
            pipeline.append([])
        else:
            pipeline[-1].append(token)
    if not pipeline[-1]:
        raise ReadonlyShellError("pipeline contains an empty command")
    return pipeline


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _validate_paths(arguments: list[str], root: Path) -> None:
    for argument in arguments:
        candidate = argument.split("=", 1)[-1] if "=" in argument else argument
        if candidate in {".", ".."} or "/" in candidate or candidate.startswith("~"):
            path = Path(candidate).expanduser()
            resolved = (root / path).resolve(strict=False) if not path.is_absolute() else path.resolve(strict=False)
            if not _is_within(resolved, root):
                raise ReadonlyShellError(f"path escapes the search root: {candidate}")


def _validate_stage(stage: list[str], root: Path) -> None:
    executable = Path(stage[0]).name
    if stage[0] != executable or executable not in ALLOWED_COMMANDS:
        raise ReadonlyShellError(f"command is not allowed: {stage[0]}")

    forbidden = FORBIDDEN_OPTIONS.get(executable, frozenset())
    for argument in stage[1:]:
        option = argument.split("=", 1)[0]
        if option in forbidden:
            raise ReadonlyShellError(f"option is not allowed for {executable}: {option}")
        for prefix in PATH_OPTION_PREFIXES.get(executable, ()):
            if argument.startswith(prefix) and argument != prefix:
                embedded_path = argument[len(prefix) :]
                if prefix in {"-o", "-fls", "-fprint", "-fprintf"}:
                    raise ReadonlyShellError(
                        f"option is not allowed for {executable}: {prefix}"
                    )
                _validate_paths([embedded_path], root)
    _validate_paths(stage[1:], root)


def _run_readonly_command(command: str, context: ScoutContext) -> str:
    """Validate and execute an allowlisted read-only command pipeline."""
    pipeline = _parse_pipeline(command)
    for stage in pipeline:
        _validate_stage(stage, context.directory)

    stdin: bytes | None = None
    for stage in pipeline:
        try:
            result = subprocess.run(
                stage,
                cwd=context.directory,
                input=stdin,
                capture_output=True,
                check=False,
                timeout=context.timeout_seconds,
            )
        except FileNotFoundError as error:
            raise ReadonlyShellError(f"command is unavailable: {stage[0]}") from error
        except subprocess.TimeoutExpired as error:
            raise ReadonlyShellError(
                f"command exceeded {context.timeout_seconds:g} seconds"
            ) from error

        stdin = result.stdout[: context.max_output_bytes + 1]
        accepted_statuses = {0, 1} if stage[0] in {"grep", "rg"} else {0}
        if result.returncode not in accepted_statuses:
            stderr = result.stderr.decode(errors="replace").strip()
            raise ReadonlyShellError(
                f"{stage[0]} exited with status {result.returncode}: {stderr}"
            )

    assert stdin is not None
    truncated = len(stdin) > context.max_output_bytes
    output = stdin[: context.max_output_bytes].decode(errors="replace")
    if truncated:
        output += f"\n... output truncated after {context.max_output_bytes} bytes"
    return output or "(no output)"


@function_tool
async def readonly_bash(
    wrapper: RunContextWrapper[ScoutContext],
    command: str,
) -> str:
    """Run a read-only navigation or search command inside the assigned directory.

    Allowed commands are ``ls``, ``grep``, ``find``, ``cat``, ``seq``, ``pwd``,
    ``rg``, ``head``, ``tail``, ``wc``, ``sort``, and ``cut``. Pipelines are
    supported. Redirection, command chaining, mutating options, and paths outside
    the assigned directory are rejected.

    Args:
        command: The command line to execute, for example ``find . -name '*.py'``
            or ``rg TODO src | head -n 20``.
    """
    return _run_readonly_command(command, wrapper.context)
