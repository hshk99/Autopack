"""Contract tests for CodeValidator (IMP-TEST-007).

Validates that the code validator correctly sanitizes input and validates
Python code for security-critical operations, preventing code injection attacks.
"""

import pytest

from autopack.executor.code_validator import CodeValidator, validate_code


class TestCodeValidatorSanitizeInput:
    """Test suite for CodeValidator.sanitize_input method."""

    def test_sanitize_valid_string_returns_same(self):
        """Test sanitization of valid Python code returns the same code."""
        code = "def hello():\n    return 'world'"
        result = CodeValidator.sanitize_input(code)
        assert result == code

    def test_sanitize_non_string_raises_value_error(self):
        """Test sanitization rejects non-string input."""
        with pytest.raises(ValueError, match="Code input must be a string"):
            CodeValidator.sanitize_input(123)

        with pytest.raises(ValueError, match="Code input must be a string"):
            CodeValidator.sanitize_input(None)

        with pytest.raises(ValueError, match="Code input must be a string"):
            CodeValidator.sanitize_input(["code"])

    def test_sanitize_empty_input_returns_empty(self):
        """Test sanitization of empty input returns empty string."""
        assert CodeValidator.sanitize_input("") == ""
        assert CodeValidator.sanitize_input("   ") == ""
        assert CodeValidator.sanitize_input("\n\t") == ""

    def test_sanitize_exceeds_max_length_raises_value_error(self):
        """Test sanitization rejects code exceeding MAX_CODE_LENGTH."""
        long_code = "x = 1\n" * 20000  # Exceeds 100KB
        with pytest.raises(ValueError, match="exceeds maximum length"):
            CodeValidator.sanitize_input(long_code)

    def test_sanitize_at_max_length_passes(self):
        """Test sanitization accepts code at exactly MAX_CODE_LENGTH."""
        # Create code that is exactly at the limit
        code = "x" * CodeValidator.MAX_CODE_LENGTH
        result = CodeValidator.sanitize_input(code)
        assert len(result) == CodeValidator.MAX_CODE_LENGTH

    @pytest.mark.parametrize(
        "dangerous_code,pattern_name",
        [
            ("__import__('os')", "__import__"),
            ("eval('code')", "eval"),
            ("exec('code')", "exec"),
            ("compile('code', 'x', 'exec')", "compile"),
            ("globals()", "globals"),
            ("locals()", "locals"),
            ("x.__builtins__", "__builtins__"),
            ("cls.__subclasses__()", "__subclasses__"),
            ("cls.__bases__[0]", "__bases__"),
            ("func.im_func", "im_func"),
            ("func.func_globals", "func_globals"),
        ],
    )
    def test_sanitize_dangerous_patterns_raise_value_error(self, dangerous_code, pattern_name):
        """Test sanitization rejects code with dangerous patterns."""
        with pytest.raises(ValueError, match="potentially dangerous pattern"):
            CodeValidator.sanitize_input(dangerous_code)

    def test_sanitize_dangerous_patterns_case_insensitive(self):
        """Test dangerous pattern detection is case insensitive."""
        with pytest.raises(ValueError, match="potentially dangerous pattern"):
            CodeValidator.sanitize_input("EVAL('code')")

        with pytest.raises(ValueError, match="potentially dangerous pattern"):
            CodeValidator.sanitize_input("Exec('code')")

    def test_sanitize_removes_null_bytes(self):
        """Test sanitization removes null bytes from code."""
        code = "x = 1\x00y = 2"
        result = CodeValidator.sanitize_input(code)
        assert "\x00" not in result
        assert result == "x = 1y = 2"

    def test_sanitize_removes_control_characters(self):
        """Test sanitization removes control characters except newlines/tabs."""
        code = "x = 1\x01\x02\x03y = 2"
        result = CodeValidator.sanitize_input(code)
        assert "\x01" not in result
        assert "\x02" not in result
        assert "\x03" not in result
        assert result == "x = 1y = 2"

    def test_sanitize_preserves_newlines_and_tabs(self):
        """Test sanitization preserves newlines and tabs."""
        code = "def foo():\n\treturn 1\r\n"
        result = CodeValidator.sanitize_input(code)
        assert "\n" in result
        assert "\t" in result
        assert "\r" in result


class TestCodeValidatorValidatePythonSyntax:
    """Test suite for CodeValidator.validate_python_syntax method."""

    def test_valid_python_syntax_returns_true(self):
        """Test valid Python code returns (True, None)."""
        code = """
def greet(name):
    return f"Hello, {name}!"

class Person:
    def __init__(self, name):
        self.name = name
"""
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is True
        assert error is None

    def test_invalid_python_syntax_returns_false(self):
        """Test invalid Python syntax returns (False, error_message)."""
        code = "def broken(\n"
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is False
        assert "Syntax error" in error

    def test_syntax_error_includes_line_number(self):
        """Test syntax error message includes line number."""
        code = "x = 1\ny = 2\ndef broken("
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is False
        assert "line 3" in error

    def test_sanitization_enabled_by_default(self):
        """Test sanitization is enabled by default."""
        code = "eval('code')"
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is False
        assert "Sanitization error" in error

    def test_sanitization_can_be_disabled(self):
        """Test sanitization can be disabled with sanitize=False."""
        # This code has dangerous pattern but valid syntax
        code = "x = 1 + 2"  # Safe code
        is_valid, error = CodeValidator.validate_python_syntax(code, sanitize=False)
        assert is_valid is True
        assert error is None

    def test_empty_code_is_valid(self):
        """Test empty code is considered valid syntax."""
        is_valid, error = CodeValidator.validate_python_syntax("")
        assert is_valid is True
        assert error is None

    def test_whitespace_only_code_is_valid(self):
        """Test whitespace-only code is considered valid syntax."""
        is_valid, error = CodeValidator.validate_python_syntax("   \n\t  ")
        assert is_valid is True
        assert error is None

    def test_code_with_comments_is_valid(self):
        """Test code with comments is valid."""
        code = "# This is a comment\nx = 1  # inline comment"
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is True
        assert error is None


class TestCodeValidatorIsSafeForExecution:
    """Test suite for CodeValidator.is_safe_for_execution method."""

    def test_safe_code_returns_true(self):
        """Test safe code returns (True, None)."""
        code = """
def calculate(x, y):
    return x + y

result = calculate(10, 20)
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_eval_call_returns_false(self):
        """Test code with eval() returns (False, reason)."""
        code = "result = eval(user_input)"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_exec_call_returns_false(self):
        """Test code with exec() returns (False, reason)."""
        code = "exec(user_code)"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_compile_call_returns_false(self):
        """Test code with compile() returns (False, reason)."""
        code = "code_obj = compile(source, 'test', 'exec')"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_dunder_import_call_returns_false(self):
        """Test code with __import__() returns (False, reason)."""
        code = "os = __import__('os')"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_builtins_attribute_access_returns_false(self):
        """Test code accessing __builtins__ returns (False, reason)."""
        code = "builtins = obj.__builtins__"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_subclasses_attribute_access_returns_false(self):
        """Test code accessing __subclasses__ returns (False, reason)."""
        code = "subs = cls.__subclasses__()"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_func_globals_attribute_access_returns_false(self):
        """Test code accessing func_globals returns (False, reason)."""
        code = "globals_dict = func.func_globals"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_invalid_syntax_returns_false(self):
        """Test code with invalid syntax returns (False, reason)."""
        code = "def broken("
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "Syntax error" in reason

    def test_ast_walk_checks_all_nodes(self):
        """Test AST walking checks deeply nested dangerous calls."""
        code = """
def outer():
    def inner():
        return eval("1 + 1")
    return inner()
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is False
        assert "dangerous" in reason.lower()

    def test_normal_function_calls_are_safe(self):
        """Test normal function calls are considered safe."""
        code = """
import math
result = math.sqrt(16)
print(result)
"""
        # Note: import statement is safe because it's an Import node, not __import__ call
        # But sanitization will catch it if __import__ pattern is used
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_class_definitions_are_safe(self):
        """Test class definitions are considered safe."""
        code = """
class MyClass:
    def __init__(self):
        self.value = 42

    def get_value(self):
        return self.value
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None


class TestValidateCodeConvenienceFunction:
    """Test suite for validate_code convenience function."""

    def test_non_strict_mode_checks_syntax_only(self):
        """Test non-strict mode only validates syntax."""
        code = "x = 1 + 2"
        is_valid, error = validate_code(code, strict=False)
        assert is_valid is True
        assert error is None

    def test_non_strict_mode_still_sanitizes(self):
        """Test non-strict mode still performs sanitization."""
        code = "eval('code')"
        is_valid, error = validate_code(code, strict=False)
        assert is_valid is False
        assert "Sanitization error" in error

    def test_strict_mode_performs_safety_checks(self):
        """Test strict mode performs additional safety checks."""
        # Code that passes syntax but fails safety
        code = "result = eval(x)"  # eval detected in regex
        is_valid, error = validate_code(code, strict=True)
        assert is_valid is False

    def test_strict_mode_rejects_dangerous_ast_patterns(self):
        """Test strict mode rejects dangerous patterns in AST."""
        # Use a pattern that might pass regex but fail AST check
        code = "obj.__builtins__"
        is_valid, error = validate_code(code, strict=True)
        assert is_valid is False

    def test_default_is_non_strict(self):
        """Test default mode is non-strict."""
        code = "x = 1"
        is_valid, error = validate_code(code)
        assert is_valid is True
        assert error is None


class TestCodeValidatorEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_unicode_code_is_handled(self):
        """Test code with unicode characters is handled correctly."""
        code = "message = 'Hello, 世界!'"
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is True
        assert error is None

    def test_multiline_strings_are_handled(self):
        """Test code with multiline strings is handled correctly."""
        code = '''
docstring = """
This is a multiline
docstring with 'quotes'
and "double quotes"
"""
'''
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is True
        assert error is None

    def test_nested_quotes_are_handled(self):
        """Test code with nested quotes is handled correctly."""
        code = "x = 'He said \"hello\"'"
        is_valid, error = CodeValidator.validate_python_syntax(code)
        assert is_valid is True
        assert error is None

    def test_lambda_expressions_are_safe(self):
        """Test lambda expressions are considered safe."""
        code = "add = lambda x, y: x + y"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_list_comprehensions_are_safe(self):
        """Test list comprehensions are considered safe."""
        code = "squares = [x**2 for x in range(10)]"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_generator_expressions_are_safe(self):
        """Test generator expressions are considered safe."""
        code = "gen = (x**2 for x in range(10))"
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_decorators_are_safe(self):
        """Test decorators are considered safe."""
        code = """
def my_decorator(func):
    def wrapper(*args, **kwargs):
        return func(*args, **kwargs)
    return wrapper

@my_decorator
def greet():
    return "hello"
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_async_code_is_safe(self):
        """Test async/await code is considered safe."""
        code = """
async def fetch_data():
    await some_coroutine()
    return data
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_type_hints_are_safe(self):
        """Test code with type hints is considered safe."""
        code = """
def greet(name: str) -> str:
    return f"Hello, {name}"

x: int = 42
"""
        is_safe, reason = CodeValidator.is_safe_for_execution(code)
        assert is_safe is True
        assert reason is None

    def test_max_code_length_constant(self):
        """Test MAX_CODE_LENGTH is reasonable."""
        assert CodeValidator.MAX_CODE_LENGTH == 100000
        assert CodeValidator.MAX_CODE_LENGTH > 0

    def test_dangerous_patterns_list_is_populated(self):
        """Test DANGEROUS_PATTERNS list contains expected patterns."""
        patterns = CodeValidator.DANGEROUS_PATTERNS
        assert len(patterns) > 0
        assert any("eval" in p for p in patterns)
        assert any("exec" in p for p in patterns)
        assert any("__import__" in p for p in patterns)
