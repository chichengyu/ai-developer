"""Bounded concolic dependency tracing for JavaScript functions.

Full symbolic execution of obfuscated JS is not practical with MD5/HMAC
models, but a function's *input dependency graph* is: run the function with
concrete arguments, then mutate one argument at a time and observe which
mutations change the output.  The result is a bounded concolic trace that
shows exactly which parameters feed a signature.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ConcolicResult:
    function: str
    ok: bool = False
    error: str | None = None
    base_result: Any = None
    dependencies: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "function": self.function,
            "ok": self.ok,
            "error": self.error,
            "base_result": self.base_result,
            "dependencies": self.dependencies,
            "summary": {
                "dependency_count": len(self.dependencies),
                "changed": sum(1 for item in self.dependencies if item.get("changed")),
            },
        }


def run_concolic_function(
    js: str,
    function_name: str,
    concrete_args: list[Any],
    *,
    timeout: float = 5.0,
) -> ConcolicResult:
    """Run a JS function and mutate args one-by-one to find dependencies."""
    try:
        from deep_reverse import node_available, run_signature_function
    except Exception:
        return ConcolicResult(function_name, ok=False, error="deep_reverse unavailable")
    if not node_available():
        return ConcolicResult(function_name, ok=False, error="node is not available")
    base = run_signature_function(js, function_name, concrete_args)
    if not base.get("ok"):
        return ConcolicResult(
            function_name,
            ok=False,
            error=str(base.get("error") or "base execution failed"),
        )
    base_value = base.get("value")
    dependencies: list[dict[str, Any]] = []
    for index, argument in enumerate(concrete_args):
        mutated = copy.deepcopy(concrete_args)
        mutated[index] = _mutate(argument)
        result = run_signature_function(js, function_name, mutated)
        changed = bool(
            result.get("ok")
            and _values_differ(base_value, result.get("value"))
        )
        dependencies.append(
            {
                "arg_index": index,
                "arg": argument,
                "mutated": mutated[index],
                "changed": changed,
                "mutated_result": result.get("value"),
                "ok": bool(result.get("ok")),
            }
        )
    return ConcolicResult(
        function_name,
        ok=True,
        base_result=base_value,
        dependencies=dependencies,
    )


def _mutate(value: Any) -> Any:
    if isinstance(value, dict):
        out = copy.deepcopy(value)
        out["__symbolic__"] = True
        return out
    if isinstance(value, list):
        out = copy.deepcopy(value)
        out.append("__symbolic__")
        return out
    if isinstance(value, bool):
        return not value
    if isinstance(value, int | float):
        return value + 1
    return f"{value}__SYMBOLIC__"


def _values_differ(left: Any, right: Any) -> bool:
    if isinstance(left, dict | list) or isinstance(right, dict | list):
        return left != right
    if left is None or right is None:
        return left != right
    return str(left) != str(right)


def _self_test() -> None:
    js = "function add(a,b){return a+':'+b;}"
    result = run_concolic_function(js, "add", ["x", "y"])
    assert result.ok is True
    assert all(item["changed"] for item in result.dependencies)
    print("concolic_runner self-test OK")


if __name__ == "__main__":
    _self_test()
