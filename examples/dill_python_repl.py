from __future__ import annotations

import types
from typing import Any

import dill


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

class ContextDict(dict[str, Any]):
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

    def __setitem__(self, key: Any, value: Any) -> None:
        super().__setitem__(key, value)

    def update(self, other=(), /, **kwargs: Any) -> None:
        values = dict(other, **kwargs)

        super().update(values)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        if key not in self:
            self[key] = default

        return self[key]

    def __ior__(self, other: Any) -> "ContextDict":
        self.update(other)
        return self

    def validate_all(self) -> None:
        validate_state_value(
            self,
            path="context",
            allowed_types=self.allowed_types,
        )

class SnippetEnvironment:
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
            raise ValueError(
                f"Provided names are reserved: {sorted(invalid)}"
            )

    def run(
        self,
        source: str,
        *,
        result_name: str | None = None,
    ) -> Any:
        original_context = self.context

        namespace = {
            "__builtins__": SAFE_BUILTINS.copy(),
            "context": original_context,
            **self.provided,
        }

        exec(source, namespace, namespace)

        if namespace.get("context") is not original_context:
            raise RuntimeError(
                "The context variable cannot be replaced; "
                "modify context entries instead"
            )

        # Detect invalid values inserted through nested mutation.
        original_context.validate_all()

        if result_name is None:
            return None

        return namespace.get(result_name)

    def dumps(self) -> bytes:
        self.context.validate_all()

        # Serialize plain state rather than the ContextDict implementation.
        return dill.dumps(dict(self.context))

    @classmethod
    def loads(
        cls,
        data: bytes,
        *,
        provided: dict[str, Any] | None = None,
        allowed_context_types: tuple[type, ...] = (),
    ) -> "SnippetEnvironment":
        context = dill.loads(data)

        if not isinstance(context, dict):
            raise TypeError("Serialized context must contain a dict")

        return cls(
            provided=provided,
            context=context,
            allowed_context_types=allowed_context_types,
        )