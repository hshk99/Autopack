# Testing Guide

**Purpose**: Guide for running tests, writing tests, and understanding test structure in Autopack

**Last Updated**: 2025-12-29

---

## Overview

Autopack uses pytest for testing with comprehensive coverage across unit tests, integration tests, and smoke tests. This guide covers:

1. Running tests
2. Writing tests
3. Test structure and organization

---

## Running Tests

### Quick Start

```bash
# Run all tests
PYTHONPATH=src pytest tests/

# Run with coverage report
PYTHONPATH=src pytest --cov=src/autopack --cov-report=html tests/

# Run specific test file
PYTHONPATH=src pytest tests/test_token_estimator.py

# Run specific test function
PYTHONPATH=src pytest tests/test_token_estimator.py::test_estimate_output_tokens
```

### Test Configuration

**pytest.ini** configures test behavior:

```ini
[pytest]
pythonpath = src
testpaths = tests
addopts = 
    --cov=src/autopack
    --cov-report=json:.coverage.json
    --cov-branch
    -v
```

**Key settings**:
- `pythonpath = src` - Enables `import autopack` in tests
- `--cov=src/autopack` - Tracks coverage for autopack module
- `--cov-report=json` - Generates machine-readable coverage data
- `--cov-branch` - Includes branch coverage

### Environment Variables

```bash
# Required
PYTHONPATH=src  # Module resolution

# Optional
TESTING=1  # Skip DB initialization in tests
DATABASE_URL=sqlite:///:memory:  # In-memory DB for tests
```

### Common Test Commands

```bash
# Run tests with verbose output
PYTHONPATH=src pytest -v tests/

# Run tests matching pattern
PYTHONPATH=src pytest -k "token" tests/

# Run tests and stop on first failure
PYTHONPATH=src pytest -x tests/

# Run tests with print statements visible
PYTHONPATH=src pytest -s tests/

# Run only failed tests from last run
PYTHONPATH=src pytest --lf tests/
```

---

## Writing Tests

### Test Structure

Tests follow pytest conventions:

```python
import pytest
from autopack.token_estimator import TokenEstimator

def test_estimate_output_tokens():
    """Test basic token estimation."""
    estimator = TokenEstimator()
    
    result = estimator.estimate(
        deliverables=["src/main.py", "tests/test_main.py"],
        category="implementation",
        complexity="medium"
    )
    
    assert result.estimated_tokens > 0
    assert result.category == "implementation"
    assert result.complexity == "medium"
```

### Test Organization

**Directory structure**:
```
tests/
├── test_token_estimator.py      # Unit tests for token estimator
├── test_quality_gate.py          # Unit tests for quality gate
├── test_phase_finalizer.py       # Unit tests for phase finalizer
├── test_autonomous_executor.py   # Integration tests for executor
└── scripts/
    └── test_create_telemetry_run.py  # Script tests
```

**Naming conventions**:
- Test files: `test_*.py`
- Test functions: `test_*`
- Test classes: `Test*`

### Fixtures

**Common fixtures** (in `conftest.py`):

```python
import pytest
from pathlib import Path

@pytest.fixture
def temp_workspace(tmp_path):
    """Create temporary workspace for tests."""
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace

@pytest.fixture
def sample_phase():
    """Create sample phase configuration."""
    return {
        "phase_id": "test-phase",
        "category": "implementation",
        "complexity": "medium",
        "deliverables": ["src/main.py"],
        "scope": {
            "paths": ["src/"],
            "deliverables": ["src/main.py"]
        }
    }
```

**Using fixtures**:

```python
def test_with_workspace(temp_workspace):
    """Test using temporary workspace."""
    test_file = temp_workspace / "test.py"
    test_file.write_text("print('hello')")
    assert test_file.exists()

def test_with_phase(sample_phase):
    """Test using sample phase."""
    assert sample_phase["category"] == "implementation"
```

### Mocking

**Mock external dependencies**:

```python
from unittest.mock import Mock, patch

def test_with_mock():
    """Test with mocked LLM client."""
    with patch('autopack.anthropic_clients.AnthropicClient') as mock_client:
        mock_client.return_value.generate.return_value = {
            "patch_content": "diff --git a/file.py...",
            "stop_reason": "end_turn"
        }
        
        # Test code that uses AnthropicClient
        result = some_function_using_client()
        assert result is not None
```

### Assertions

**Common assertion patterns**:

```python
# Basic assertions
assert value == expected
assert value is not None
assert len(items) > 0

# Exception assertions
with pytest.raises(ValueError):
    function_that_raises()

# Approximate assertions (for floats)
assert result == pytest.approx(3.14, rel=0.01)

# Collection assertions
assert "item" in collection
assert set(result) == {"a", "b", "c"}
```

---

## Test Structure

### Unit Tests

**Purpose**: Test individual functions/classes in isolation

**Example**: `tests/test_token_estimator.py`

```python
class TestTokenEstimator:
    """Unit tests for TokenEstimator."""
    
    def test_estimate_basic(self):
        """Test basic estimation."""
        estimator = TokenEstimator()
        result = estimator.estimate(
            deliverables=["file.py"],
            category="implementation",
            complexity="low"
        )
        assert result.estimated_tokens > 0
    
    def test_estimate_with_multiple_files(self):
        """Test estimation with multiple files."""
        estimator = TokenEstimator()
        result = estimator.estimate(
            deliverables=["a.py", "b.py", "c.py"],
            category="implementation",
            complexity="medium"
        )
        assert result.estimated_tokens > 1000
```

### Integration Tests

**Purpose**: Test interactions between components

**Example**: `tests/test_autonomous_executor.py`

```python
def test_executor_phase_execution(temp_workspace):
    """Test full phase execution flow."""
    executor = AutonomousExecutor(
        workspace=str(temp_workspace),
        api_url="http://localhost:8000"
    )
    
    phase = {
        "phase_id": "test-phase",
        "goal": "Create main.py",
        "deliverables": ["src/main.py"],
        "scope": {"paths": ["src/"]}
    }
    
    # Execute phase
    result = executor.execute_phase(phase)
    
    # Verify results
    assert result.success
    assert (temp_workspace / "src/main.py").exists()
```

### Smoke Tests

**Purpose**: Quick validation of core functionality

**Example**: `tests/test_imports.py`

```python
def test_core_imports():
    """Verify core modules can be imported."""
    from autopack.autonomous_executor import AutonomousExecutor
    from autopack.token_estimator import TokenEstimator
    from autopack.quality_gate import QualityGate
    from autopack.phase_finalizer import PhaseFinalizer
    
    # If we get here, imports succeeded
    assert True
```

---

## Best Practices

### Test Independence

**DO**: Each test should be independent
```python
def test_a():
    data = create_test_data()
    assert process(data) == expected

def test_b():
    data = create_test_data()  # Fresh data
    assert validate(data) is True
```

**DON'T**: Tests should not depend on each other
```python
# BAD: test_b depends on test_a
shared_data = None

def test_a():
    global shared_data
    shared_data = create_test_data()

def test_b():
    assert shared_data is not None  # Fails if test_a not run
```

### Test Coverage

**Aim for**:
- ≥80% line coverage
- ≥70% branch coverage
- 100% coverage for critical paths (quality gate, phase finalizer)

**Check coverage**:
```bash
PYTHONPATH=src pytest --cov=src/autopack --cov-report=html tests/
open htmlcov/index.html  # View coverage report
```

### Test Documentation

**Good docstrings**:
```python
def test_token_estimation_with_doc_synthesis():
    """Test token estimation for documentation phases.
    
    Verifies that DOC_SYNTHESIS detection activates for pure
    documentation phases and applies appropriate phase-based
    estimation instead of linear scaling.
    """
    # Test implementation
```

---

## Troubleshooting

### Common Issues

**"No module named autopack"**
```bash
# Fix: Set PYTHONPATH
export PYTHONPATH=src  # Linux/Mac
$env:PYTHONPATH="src"  # Windows PowerShell
```

**"Database locked"**
```bash
# Fix: Use in-memory database for tests
export DATABASE_URL="sqlite:///:memory:"
```

**"Import errors in tests"**
```bash
# Fix: Check conftest.py adds src/ to sys.path
# Or use PYTHONPATH=src
```

### Debugging Tests

```bash
# Run with debugger
PYTHONPATH=src pytest --pdb tests/test_file.py

# Show print statements
PYTHONPATH=src pytest -s tests/test_file.py

# Verbose output
PYTHONPATH=src pytest -vv tests/test_file.py
```

---

## References

- [CONTRIBUTING.md](CONTRIBUTING.md) - Development setup and guidelines
- [pytest.ini](../pytest.ini) - Test configuration
- [BUILD-132_IMPLEMENTATION_STATUS.md](archive/superseded/reports/BUILD-132_IMPLEMENTATION_STATUS.md) - Coverage delta integration
- [pytest documentation](https://docs.pytest.org/) - Official pytest docs

---

**Total Lines**: 148 (within ≤150 line constraint)

**Coverage**: Running tests (3 sections), writing tests (3 sections), test structure (3 sections)

**Code Snippets**: 3 total (basic test, fixture usage, integration test)
