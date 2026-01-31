"""Compiler module for the tracer bullet pipeline."""

import ast
import operator
from typing import Any, Callable, Union

# Safe AST node types for mathematical expression evaluation.
# This strict whitelist prevents arbitrary code execution by only allowing
# numeric constants and basic arithmetic operators.
_SAFE_NODES = (
    ast.Expression,
    ast.Constant,  # Python 3.8+ for all constant values
    ast.BinOp,
    ast.UnaryOp,
    # Binary operators
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.FloorDiv,
    ast.Mod,
    ast.Pow,
    # Unary operators
    ast.USub,
    ast.UAdd,
)

# Mapping of AST operator nodes to Python operators
_BINARY_OPS: dict[type[ast.operator], Callable[[Any, Any], Any]] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Callable[[Any], Any]] = {
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _evaluate_node(node: ast.expr) -> Union[int, float]:
    """
    Recursively evaluate an AST node without executing dangerous code.

    This function safely interprets the AST tree by directly computing
    results from allowed node types, completely eliminating the security
    risks associated with code execution via dynamic interpretation.

    Args:
        node: An AST expression node.

    Returns:
        The numeric result.

    Raises:
        ValueError: If an unsafe node type is encountered.
    """
    if isinstance(node, ast.Constant):
        if not isinstance(node.value, (int, float)):
            raise ValueError(f"Unsafe expression: non-numeric constant {type(node.value).__name__}")
        return node.value

    if isinstance(node, ast.BinOp):
        left = _evaluate_node(node.left)
        right = _evaluate_node(node.right)
        binary_op = _BINARY_OPS.get(type(node.op))
        if binary_op is None:
            raise ValueError(f"Unsafe expression: unsupported operator {type(node.op).__name__}")
        return binary_op(left, right)

    if isinstance(node, ast.UnaryOp):
        operand = _evaluate_node(node.operand)
        unary_op = _UNARY_OPS.get(type(node.op))
        if unary_op is None:
            raise ValueError(
                f"Unsafe expression: unsupported unary operator {type(node.op).__name__}"
            )
        return unary_op(operand)

    raise ValueError(f"Unsafe expression: contains {type(node).__name__}")


def safe_eval(expression: str) -> Union[int, float]:
    """
    Safely evaluate a mathematical expression without executing arbitrary code.

    Only allows basic arithmetic operations (+, -, *, /, //, %, **) on numbers.
    No function calls, attribute access, name lookups, or other potentially
    unsafe operations are permitted.

    Args:
        expression: A string containing a mathematical expression.

    Returns:
        The numeric result of the expression.

    Raises:
        ValueError: If the expression contains unsafe node types or is invalid.
    """
    try:
        tree = ast.parse(expression.strip(), mode="eval")
    except SyntaxError as e:
        raise ValueError(f"Invalid expression syntax: {e}")

    # Validate all nodes in the AST are in the safe whitelist
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_NODES):
            raise ValueError(f"Unsafe expression: contains {type(node).__name__}")

    # Additional check: ensure Constant nodes only contain numeric values
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant):
            if not isinstance(node.value, (int, float)):
                raise ValueError(
                    f"Unsafe expression: non-numeric constant {type(node.value).__name__}"
                )

    # Evaluate the AST without using eval()
    return _evaluate_node(tree.body)


def compile_expression(expression: str) -> Union[int, float]:
    """
    Compiles and evaluates a mathematical expression safely.

    Args:
        expression (str): The mathematical expression to evaluate.

    Returns:
        Union[int, float]: The result of the evaluated expression.

    Raises:
        ValueError: If the expression is invalid or unsafe.
    """
    return safe_eval(expression)


if __name__ == "__main__":
    # Example usage
    expression = "2 + 3 * (4 - 1)"
    try:
        result = compile_expression(expression)
        print(f"The result of '{expression}' is {result}.")
    except ValueError as e:
        print(f"Error: {e}")

# Note: This is a simplified example and should not be used for untrusted input.
# In a production environment, consider using a safe math expression evaluator.
