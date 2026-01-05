"""Compiler module for the tracer bullet pipeline."""

import ast


def compile_expression(expression: str) -> int:
    """
    Compiles and evaluates a mathematical expression.

    Args:
        expression (str): The mathematical expression to evaluate.

    Returns:
        int: The result of the evaluated expression.

    Raises:
        ValueError: If the expression is invalid or unsafe.
    """
    try:
        # Parse the expression into an AST node
        node = ast.parse(expression, mode="eval")

        # Ensure the node is safe to evaluate
        if not all(
            isinstance(n, (ast.Expression, ast.BinOp, ast.Num, ast.UnaryOp, ast.operator))
            for n in ast.walk(node)
        ):
            raise ValueError("Unsafe expression")

        # Compile and evaluate the expression
        compiled = compile(node, "<string>", "eval")
        return eval(compiled)
    except Exception as e:
        raise ValueError(f"Invalid expression: {e}")


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
