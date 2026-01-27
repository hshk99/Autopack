import pytest

from autopack.sql_sanitizer import SQLSanitizer

SQL_INJECTION_PAYLOADS = [
    "'; DROP TABLE users--",
    "1' OR '1'='1",
    "admin'--",
    "' UNION SELECT * FROM passwords--",
    "1; DELETE FROM runs WHERE 1=1",
    "' OR 1=1--",
    "; exec xp_cmdshell('dir')",
    "test'; DROP TABLE runs; --",
]


@pytest.mark.parametrize("payload", SQL_INJECTION_PAYLOADS)
def test_sql_injection_blocked(payload):
    """Verify SQL injection payloads are blocked."""
    with pytest.raises(ValueError, match="Unsafe SQL pattern"):
        SQLSanitizer.validate_parameter(payload)


def test_safe_parameters_allowed():
    """Verify safe parameters pass validation."""
    assert SQLSanitizer.validate_parameter("test-run-123") == "test-run-123"
    assert SQLSanitizer.validate_parameter(42) == 42
    assert SQLSanitizer.validate_parameter(3.14) == 3.14
    assert SQLSanitizer.validate_parameter(True) is True
    assert SQLSanitizer.validate_parameter(None) is None


def test_invalid_types_rejected():
    """Verify invalid types are rejected."""
    with pytest.raises(ValueError, match="Invalid parameter type"):
        SQLSanitizer.validate_parameter([1, 2, 3])
    with pytest.raises(ValueError, match="Invalid parameter type"):
        SQLSanitizer.validate_parameter({"key": "value"})
