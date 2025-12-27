from __future__ import annotations

import ast


def compile_expression(expression: str) -> int:
    """Safely evaluate a simple arithmetic expression used by tests."""
    node = ast.parse(expression, mode="eval")
    allowed = (ast.Expression, ast.BinOp, ast.UnaryOp, ast.Num, ast.Constant, ast.operator, ast.unaryop)
    if not all(isinstance(n, allowed) for n in ast.walk(node)):
        raise ValueError("Unsafe expression")
    compiled = compile(node, "<expr>", "eval")
    return int(eval(compiled, {"__builtins__": {}}, {}))


