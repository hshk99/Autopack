"""Tests for safe expression evaluator in tracer_bullet compiler.

This module tests the safe_eval function to ensure it:
1. Correctly evaluates valid mathematical expressions
2. Rejects unsafe expressions that could lead to code execution
3. Handles edge cases appropriately
"""

import pytest

from autopack.research.tracer_bullet.compiler import compile_expression, safe_eval


class TestSafeEvalValidExpressions:
    """Tests for valid mathematical expressions."""

    def test_simple_addition(self):
        """Test basic addition."""
        assert safe_eval("2 + 3") == 5

    def test_simple_subtraction(self):
        """Test basic subtraction."""
        assert safe_eval("10 - 4") == 6

    def test_simple_multiplication(self):
        """Test basic multiplication."""
        assert safe_eval("6 * 7") == 42

    def test_simple_division(self):
        """Test basic division."""
        assert safe_eval("20 / 4") == 5.0

    def test_floor_division(self):
        """Test floor division."""
        assert safe_eval("17 // 5") == 3

    def test_modulo(self):
        """Test modulo operation."""
        assert safe_eval("17 % 5") == 2

    def test_power(self):
        """Test exponentiation."""
        assert safe_eval("2 ** 10") == 1024

    def test_unary_negative(self):
        """Test unary negative."""
        assert safe_eval("-5") == -5

    def test_unary_positive(self):
        """Test unary positive."""
        assert safe_eval("+5") == 5

    def test_complex_expression(self):
        """Test complex expression with multiple operators."""
        assert safe_eval("2 + 3 * (4 - 1)") == 11

    def test_nested_parentheses(self):
        """Test nested parentheses."""
        assert safe_eval("((2 + 3) * (4 - 1))") == 15

    def test_float_numbers(self):
        """Test floating point numbers."""
        assert safe_eval("3.14 * 2") == pytest.approx(6.28)

    def test_negative_result(self):
        """Test expression resulting in negative number."""
        assert safe_eval("5 - 10") == -5

    def test_zero(self):
        """Test zero value."""
        assert safe_eval("0") == 0

    def test_large_number(self):
        """Test large number calculation."""
        assert safe_eval("1000000 * 1000000") == 1000000000000


class TestSafeEvalSecurityRejections:
    """Tests ensuring unsafe expressions are rejected."""

    def test_rejects_function_call(self):
        """Test that function calls are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("print('hello')")

    def test_rejects_builtin_function(self):
        """Test that built-in functions are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("len('test')")

    def test_rejects_import(self):
        """Test that import statements are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression|Invalid expression"):
            safe_eval("__import__('os')")

    def test_rejects_attribute_access(self):
        """Test that attribute access is rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("''.join(['a'])")

    def test_rejects_variable_name(self):
        """Test that variable names are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("x + 1")

    def test_rejects_string_literal(self):
        """Test that string literals are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression|non-numeric constant"):
            safe_eval("'hello'")

    def test_rejects_list_literal(self):
        """Test that list literals are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("[1, 2, 3]")

    def test_rejects_dict_literal(self):
        """Test that dict literals are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("{'a': 1}")

    def test_rejects_lambda(self):
        """Test that lambda expressions are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("(lambda x: x)(5)")

    def test_rejects_comprehension(self):
        """Test that list comprehensions are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("[x for x in range(10)]")

    def test_rejects_exec_attempt(self):
        """Test that exec attempts are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("exec('print(1)')")

    def test_rejects_eval_nested(self):
        """Test that nested eval attempts are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("eval('1+1')")

    def test_rejects_dunder_access(self):
        """Test that dunder attribute access is rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("().__class__.__bases__")

    def test_rejects_getattr(self):
        """Test that getattr is rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("getattr(object, '__class__')")

    def test_rejects_comparison(self):
        """Test that comparison operators are rejected (not in whitelist)."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("1 < 2")

    def test_rejects_boolean_operators(self):
        """Test that boolean operators are rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("True and False")

    def test_rejects_subscript(self):
        """Test that subscript access is rejected."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("'abc'[0]")


class TestSafeEvalEdgeCases:
    """Tests for edge cases and error handling."""

    def test_invalid_syntax(self):
        """Test that invalid syntax raises ValueError."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval("2 +")

    def test_empty_string(self):
        """Test that empty string raises ValueError."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval("")

    def test_whitespace_only(self):
        """Test that whitespace only raises ValueError."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval("   ")

    def test_division_by_zero(self):
        """Test division by zero raises appropriate error."""
        with pytest.raises((ValueError, ZeroDivisionError)):
            safe_eval("1 / 0")

    def test_very_deep_nesting(self):
        """Test deeply nested expression (reasonable depth)."""
        expr = "((((1 + 2) * 3) - 4) / 2)"
        result = safe_eval(expr)
        assert result == 2.5


class TestCompileExpressionWrapper:
    """Tests for the compile_expression wrapper function."""

    def test_compile_expression_delegates_to_safe_eval(self):
        """Test that compile_expression uses safe_eval internally."""
        assert compile_expression("2 + 3 * (4 - 1)") == 11

    def test_compile_expression_rejects_unsafe(self):
        """Test that compile_expression rejects unsafe expressions."""
        with pytest.raises(ValueError):
            compile_expression("print('hello')")

    def test_compile_expression_returns_numeric(self):
        """Test that compile_expression returns numeric result."""
        result = compile_expression("10 / 4")
        assert isinstance(result, (int, float))
        assert result == 2.5
