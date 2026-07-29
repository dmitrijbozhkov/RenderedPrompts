"""Persistent Python execution environment for sandboxed coding agents."""

from __future__ import annotations

import io
import types
from contextlib import redirect_stdout
from dataclasses import dataclass
from typing import Any

import dill
from agents import RunContextWrapper, function_tool


SAFE_BUILTINS: dict[str, Any] = {
    "bool": bool,
    "int": int,
    "float": float,
    "str": str,
    "bytes": bytes,
    "list": list,
    "tuple": tuple,
    "dict": dict,
    "set": set,
    "len": len,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "min": min,
    "max": max,
    "sum": sum,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "print": print,
    "repr": repr,
    "Exception": Exception,
    "KeyError": KeyError,
    "TypeError": TypeError,
    "ValueError": ValueError,
}

FORBIDDEN_VALUE_TYPES = (
    types.FunctionType,
    types.BuiltinFunctionType,
    types.MethodType,
    types.ModuleType,
    type,
)
STATE_CONTAINER_TYPES = (dict, list, tuple, set)
STATE_SCALAR_TYPES = (str, bytes, int, float, bool, type(None))


def validate_state_value(
    value: Any,
    *,
    path: str,
    allowed_types: tuple[type, ...] = (),
    seen: set[int] | None = None,
) -> None:
    """Validate that persisted REPL state contains only approved data."""
    if isinstance(value, FORBIDDEN_VALUE_TYPES):
        raise TypeError(f"{path} contains a forbidden value: {type(value).__name__}")
    if isinstance(value, STATE_SCALAR_TYPES + allowed_types):
        return
    if not isinstance(value, STATE_CONTAINER_TYPES):
        raise TypeError(f"{path} contains an unsupported value: {type(value).__name__}")

    visited = seen if seen is not None else set()
    identity = id(value)
    if identity in visited:
        return
    visited.add(identity)

    if isinstance(value, dict):
        for key, child in value.items():
            validate_state_value(
                key,
                path=f"{path}.<key>",
                allowed_types=allowed_types,
                seen=visited,
            )
            validate_state_value(
                child,
                path=f"{path}[{key!r}]",
                allowed_types=allowed_types,
                seen=visited,
            )
    else:
        for index, child in enumerate(value):
            validate_state_value(
                child,
                path=f"{path}[{index}]",
                allowed_types=allowed_types,
                seen=visited,
            )


class ContextDict(dict[str, Any]):
    """Mutable, validated state persisted between code executions."""

    def __init__(
        self,
        initial: dict[str, Any] | None = None,
        *,
        allowed_types: tuple[type, ...] = (),
    ) -> None:
        super().__init__()
        self.allowed_types = allowed_types
        if initial:
            self.update(initial)

    def validate_all(self) -> None:
        validate_state_value(
            self,
            path="context",
            allowed_types=self.allowed_types,
        )


@dataclass(frozen=True)
class ExecutionResult:
    """Captured output from one snippet."""

    stdout: str
    result: Any = None

    def render(self) -> str:
        parts: list[str] = []
        if self.stdout:
            parts.append(self.stdout.rstrip())
        if self.result is not None:
            parts.append(f"Result: {self.result!r}")
        return "\n".join(parts) or "(no output)"


class SnippetEnvironment:
    """Execute snippets with trusted bindings and serializable state."""

    def __init__(
        self,
        *,
        provided: dict[str, Any] | None = None,
        context: dict[str, Any] | None = None,
        allowed_context_types: tuple[type, ...] = (),
    ) -> None:
        self.provided = dict(provided or {})
        self.allowed_context_types = allowed_context_types
        self.context = ContextDict(
            context,
            allowed_types=allowed_context_types,
        )

        reserved = {"context", "__builtins__"}
        if invalid := reserved.intersection(self.provided):
            raise ValueError(f"Provided names are reserved: {sorted(invalid)}")
        self.context.validate_all()

    def run(
        self,
        source: str,
        *,
        result_name: str | None = None,
    ) -> ExecutionResult:
        """Execute code and capture printed output and an optional result."""
        original_context = self.context
        namespace = {
            "__builtins__": SAFE_BUILTINS.copy(),
            "context": original_context,
            **self.provided,
        }
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            exec(source, namespace, namespace)

        if namespace.get("context") is not original_context:
            raise RuntimeError(
                "The context variable cannot be replaced; modify context entries instead"
            )
        original_context.validate_all()
        result = namespace.get(result_name) if result_name is not None else None
        return ExecutionResult(stdout=stdout.getvalue(), result=result)

    def dumps(self) -> bytes:
        """Serialize validated state without serializing provided capabilities."""
        self.context.validate_all()
        return dill.dumps(dict(self.context))

    @classmethod
    def loads(
        cls,
        data: bytes,
        *,
        provided: dict[str, Any] | None = None,
        allowed_context_types: tuple[type, ...] = (),
    ) -> SnippetEnvironment:
        """Restore state and attach a fresh set of trusted capabilities."""
        context = dill.loads(data)
        if not isinstance(context, dict):
            raise TypeError("Serialized context must contain a dict")
        return cls(
            provided=provided,
            context=context,
            allowed_context_types=allowed_context_types,
        )


@dataclass
class ReplContext:
    """Agents SDK context containing one persistent snippet environment."""

    environment: SnippetEnvironment


def _execute_code(
    context: ReplContext,
    code: str,
    result_name: str | None = None,
) -> str:
    return context.environment.run(code, result_name=result_name).render()


@function_tool
async def execute_code(
    wrapper: RunContextWrapper[ReplContext],
    code: str,
    result_name: str | None = None,
) -> str:
    """Execute Python in the persistent sandboxed environment.

    Values persist only when explicitly assigned to ``context``. Trusted
    host-provided APIs are available as global names. Ordinary global
    assignments do not persist between calls.

    Args:
        code: Python source code to execute.
        result_name: Optional variable whose final value should be returned.
    """
    return _execute_code(wrapper.context, code, result_name)
