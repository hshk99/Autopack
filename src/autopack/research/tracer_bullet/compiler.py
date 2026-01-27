"""Compiler module for the tracer bullet pipeline."""

import ast
from typing import Union

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


def safe_eval(expression: str) -> Union[int, float]:
    """
    Safely evaluate a mathematical expression.

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
        tree = ast.parse(expression, mode="eval")
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

    # Safe to evaluate - compile and eval with empty builtins and locals
    # to prevent any access to Python built-ins or external variables
    compiled = compile(tree, "<expression>", "eval")
    return eval(compiled, {"__builtins__": {}}, {})


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
