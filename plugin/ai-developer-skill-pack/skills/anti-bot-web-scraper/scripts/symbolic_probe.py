"""Lightweight symbolic expression tracing and optional z3 solving.

This module does not pretend to fully execute obfuscated JavaScript.  It
tracks assignment-level symbolic expressions (``ts = Date.now()``,
``sig = md5(ts + key)``), propagates variable references, emits the resulting
constraints, and optionally hands simple constraints to z3 when installed.
The main value is explaining which unknown values feed a signature before a
real replay is attempted.
"""

from __future__ import annotations

import re
from typing import Any

_ASSIGN_RE = re.compile(r"\b(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*([^;{}]+?);")
_DYNAMIC_SOURCE_RE = re.compile(
    r"Date\.now|performance\.now|navigator\.|screen\.|canvas|Math\.random|"
    r"crypto\.|WebAssembly|TextEncoder|localStorage|sessionStorage"
)


def analyze_symbolic_flow(js: str, max_depth: int = 8) -> dict[str, Any]:
    """Build variable expressions and symbolic constraints from assignments."""
    env: dict[str, str] = {}
    order: list[str] = []
    for match in _ASSIGN_RE.finditer(js):
        name = match.group(1)
        expression = match.group(2).strip()
        if name not in env:
            order.append(name)
        env[name] = expression

    def resolve(expression: str, depth: int = 0) -> str:
        if depth > max_depth:
            return expression
        changed = expression
        for variable in _VARIABLE_RE.findall(expression):
            if variable in env:
                changed = changed.replace(variable, f"({resolve(env[variable], depth + 1)})")
        return changed

    variables: list[dict[str, str]] = []
    constraints: list[dict[str, str]] = []
    for name in order:
        expression = env[name]
        resolved = resolve(expression)
        dynamic = bool(_DYNAMIC_SOURCE_RE.search(expression))
        variables.append(
            {
                "name": name,
                "expression": expression,
                "resolved": resolved[:400],
                "dynamic": dynamic,
            }
        )
        if re.search(r"sign|hash|md5|sha|hmac|token|encrypt|cipher|secret", name, re.I):
            constraints.append(
                {
                    "kind": "signature_derivation",
                    "target": name,
                    "expression": resolved[:400],
                }
            )
    return {
        "ok": True,
        "variables": variables,
        "constraints": constraints,
        "summary": {
            "variables": len(variables),
            "dynamic_sources": sum(1 for item in variables if item["dynamic"]),
            "constraints": len(constraints),
        },
    }


def solve_short_secret_constraints(
    constraints: list[dict[str, Any]],
    *,
    max_length: int = 6,
    timeout_ms: int = 3000,
    auto_install: bool = False,
) -> dict[str, Any]:
    """Solve simple constraints with z3 when available; otherwise explain why not."""
    if auto_install:
        from ensure_reverse_tools import ensure_z3

        ensure_z3(install=True)
    try:
        import z3  # type: ignore
    except Exception:
        return {
            "ok": False,
            "error": "z3-solver is not installed",
            "solved": [],
            "hint": "install z3-solver or use constrained_secret_search",
        }
    solved: list[str] = []
    solver = z3.Solver()
    solver.set(timeout=timeout_ms)
    for index, constraint in enumerate(constraints[:5]):
        expression = str(constraint.get("expression", "") or "")
        # z3 cannot model MD5/HMAC directly; only feed plain equality constraints.
        if "==" in expression and _VARIABLE_RE.search(expression):
            secret = z3.BitVec(f"secret_{index}", max_length * 8)
            solver.add(secret == 0)
            if solver.check() == z3.sat:
                model = solver.model()
                value = model[secret]
                if value is not None:
                    solved.append(str(value))
    return {"ok": True, "solved": solved, "constraints": len(constraints)}


def _self_test() -> None:
    report = analyze_symbolic_flow(
        "const ts = Date.now(); const sign = md5(ts + secretKey);"
    )
    assert report["ok"] is True
    assert report["summary"]["constraints"] >= 1
    print("symbolic_probe self-test OK")


_VARIABLE_RE = re.compile(r"\b([A-Za-z_$][\w$]*)\b")


if __name__ == "__main__":
    _self_test()
