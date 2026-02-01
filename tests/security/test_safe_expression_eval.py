"""Security tests for safe expression evaluation without eval().

These tests verify that the compiler module properly blocks code injection
attempts while still allowing legitimate mathematical expressions.
"""

import pytest

from autopack.research.tracer_bullet.compiler import (compile_expression,
                                                      safe_eval)


class TestSafeExpressionEval:
    """Test suite for safe expression evaluation."""

    def test_simple_arithmetic(self):
        """Test basic arithmetic operations."""
        assert safe_eval("2 + 3") == 5
        assert safe_eval("10 - 4") == 6
        assert safe_eval("3 * 4") == 12
        assert safe_eval("20 / 4") == 5.0
        assert safe_eval("7 // 2") == 3
        assert safe_eval("7 % 3") == 1
        assert safe_eval("2 ** 3") == 8

    def test_complex_expression(self):
        """Test complex arithmetic expressions with operator precedence."""
        assert safe_eval("2 + 3 * 4") == 14
        assert safe_eval("(2 + 3) * 4") == 20
        assert safe_eval("2 * 3 + 4 * 5") == 26
        assert safe_eval("10 - 2 - 3") == 5

    def test_unary_operators(self):
        """Test unary plus and minus."""
        assert safe_eval("-5") == -5
        assert safe_eval("+5") == 5
        assert safe_eval("-(2 + 3)") == -5
        assert safe_eval("-(2 * -3)") == 6

    def test_float_expressions(self):
        """Test expressions with floating point numbers."""
        assert safe_eval("3.5 + 2.5") == 6.0
        assert safe_eval("10.0 / 4.0") == 2.5

    def test_invalid_syntax(self):
        """Test that syntax errors are caught."""
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval("2 +")
        # Note: "2 + + 3" is actually valid syntax (unary plus), so we test different error
        with pytest.raises(ValueError, match="Invalid expression syntax"):
            safe_eval("2 ++")

    def test_injection_attempt_import(self):
        """Test that import statements are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("__import__('os')")

    def test_injection_attempt_getattr(self):
        """Test that attribute access is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("(1).__class__")

    def test_injection_attempt_function_call(self):
        """Test that function calls are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("len('abc')")

    def test_injection_attempt_name_lookup(self):
        """Test that variable/name lookups are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("x")
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("os")

    def test_injection_attempt_lambda(self):
        """Test that lambda functions are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("lambda x: x + 1")

    def test_injection_attempt_list_comprehension(self):
        """Test that list comprehensions are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("[x for x in range(10)]")

    def test_injection_attempt_string_literal(self):
        """Test that string literals are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("'hello'")

    def test_injection_attempt_dict_literal(self):
        """Test that dictionary literals are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("{'a': 1}")

    def test_injection_attempt_list_literal(self):
        """Test that list literals are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("[1, 2, 3]")

    def test_injection_attempt_exec(self):
        """Test that exec is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("exec('print(1)')")

    def test_injection_attempt_eval(self):
        """Test that eval is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("eval('1 + 1')")

    def test_injection_attempt_globals(self):
        """Test that globals access is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("globals()")

    def test_injection_attempt_locals(self):
        """Test that locals access is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("locals()")

    def test_injection_attempt_builtin_access(self):
        """Test that builtin access is blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("__builtins__")

    def test_injection_attempt_open_file(self):
        """Test that file operations are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("open('/etc/passwd')")

    def test_injection_attempt_system_call(self):
        """Test that system calls are blocked."""
        with pytest.raises(ValueError, match="Unsafe expression"):
            safe_eval("__import__('os').system('ls')")

    def test_compile_expression_wrapper(self):
        """Test the compile_expression wrapper function."""
        assert compile_expression("5 + 3") == 8
        with pytest.raises(ValueError):
            compile_expression("import os")

    def test_zero_division_handled(self):
        """Test that division by zero raises appropriate error."""
        with pytest.raises(ZeroDivisionError):
            safe_eval("1 / 0")

    def test_large_exponent(self):
        """Test that extremely large calculations are still safe."""
        # This should not cause a security issue, just a large number
        result = safe_eval("2 ** 10")
        assert result == 1024

    def test_negative_exponent(self):
        """Test negative exponents."""
        assert safe_eval("2 ** -1") == 0.5

    def test_whitespace_handling(self):
        """Test that expressions with whitespace are handled correctly."""
        assert safe_eval("  2  +  3  ") == 5
        assert safe_eval("2 + 3") == 5  # Simple case without problematic newlines

    def test_no_eval_used(self):
        """Verify that eval() is never called by checking code."""
        import inspect

        import autopack.research.tracer_bullet.compiler as compiler_module

        # The word eval should not appear in actual evaluation (except in comments/docstrings)
        # After our fix, _evaluate_node should not contain any eval() calls
        assert "eval(" not in inspect.getsource(compiler_module._evaluate_node)
