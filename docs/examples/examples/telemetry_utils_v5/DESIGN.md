# Telemetry Utils v5 - Design Document

## Overview

Telemetry Utils v5 is a comprehensive utility library designed with a focus on simplicity, reliability, and maintainability. This document outlines the architectural decisions, design patterns, and principles that guide the implementation.

## Design Philosophy

### Core Principles

1. **Pure Python Standard Library Only**
   - No external dependencies to minimize installation complexity
   - Leverages Python's rich standard library for all functionality
   - Ensures compatibility across different Python environments

2. **Type Safety First**
   - Full type hints on all functions and methods
   - Enables static type checking with mypy
   - Improves IDE autocomplete and developer experience

3. **Comprehensive Documentation**
   - Every function includes detailed docstrings
   - Examples provided for all public APIs
   - Clear parameter and return value descriptions

4. **Defensive Programming**
   - Explicit error handling with informative messages
   - Input validation at function boundaries
   - Graceful degradation where appropriate

5. **Test-Driven Development**
   - Comprehensive test coverage using pytest
   - Tests serve as executable documentation
   - Edge cases and error conditions explicitly tested

## Architectural Decisions

### Module Organization

The library is organized into focused, single-responsibility modules:

```
examples/telemetry_utils_v5/
├── string_utils.py       # String manipulation
├── number_utils.py       # Mathematical operations
├── list_utils.py         # List processing
├── dict_utils.py         # Dictionary operations
├── validation_utils.py   # Data validation
├── date_utils.py         # Date/time utilities
├── path_utils.py         # Path manipulation
├── io_utils.py           # File I/O operations
├── json_utils.py         # JSON serialization
├── csv_utils.py          # CSV operations
├── ini_utils.py          # INI file handling
├── logging_utils.py      # Logging configuration
├── retry_utils.py        # Retry logic
└── textwrap_utils.py     # Text formatting
```

**Rationale:**
- Each module has a clear, focused purpose
- Easy to locate functionality by domain
- Minimal coupling between modules
- Supports tree-shaking for minimal imports

### Function Design Patterns

#### 1. Consistent Parameter Ordering

All functions follow a consistent parameter pattern:

```python
def function_name(
    primary_input: Type,           # Main data to operate on
    required_params: Type,         # Required configuration
    optional_params: Type = default,  # Optional configuration
    flags: bool = False,           # Boolean flags
) -> ReturnType:
```

**Example:**
```python
def truncate(
    text: str,              # Primary input
    max_length: int,        # Required parameter
    suffix: str = "...",   # Optional parameter
) -> str:
```

#### 2. Path Handling Pattern

All file operations accept both `str` and `Path` objects:

```python
from pathlib import Path
from typing import Union

def read_file(path: Union[str, Path], encoding: str = 'utf-8') -> str:
    file_path = Path(path)  # Normalize to Path object
    # ... implementation
```

**Rationale:**
- Flexibility for users preferring strings or Path objects
- Internal consistency using pathlib
- Cross-platform path handling

#### 3. Error Handling Pattern

Consistent error handling across all modules:

```python
def operation(path: Union[str, Path]) -> Any:
    file_path = Path(path)
    
    # Validate inputs
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    try:
        # Perform operation
        result = perform_operation()
        return result
    except SpecificError as e:
        raise SpecificError(f"Context: {e}")
    except Exception as e:
        raise IOError(f"Unexpected error: {e}")
```

**Rationale:**
- Clear error messages with context
- Specific exceptions for specific failures
- Preserves stack traces for debugging

#### 4. Optional Directory Creation Pattern

File writing functions support automatic directory creation:

```python
def write_file(
    path: Union[str, Path],
    content: str,
    create_dirs: bool = False,  # Explicit opt-in
) -> None:
    file_path = Path(path)
    
    if create_dirs and not file_path.parent.exists():
        file_path.parent.mkdir(parents=True, exist_ok=True)
    
    # ... write operation
```

**Rationale:**
- Explicit opt-in prevents unexpected directory creation
- Reduces boilerplate in user code
- Consistent across all file operations

### Design Patterns Used

#### 1. Decorator Pattern (Retry Logic)

```python
@retry_on_exception(max_attempts=3, base_delay=1.0)
def flaky_operation():
    # Operation that might fail
    pass
```

**Implementation:**
- Separates retry logic from business logic
- Configurable retry behavior
- Supports exponential backoff with jitter

**Benefits:**
- Clean separation of concerns
- Reusable across different operations
- Testable in isolation

#### 2. Strategy Pattern (Validation)

Validation functions are independent strategies:

```python
# Each validator is a separate strategy
is_email(value)      # Email validation strategy
is_url(value)        # URL validation strategy
is_int(value)        # Integer validation strategy
validate_range(...)  # Range validation strategy
```

**Benefits:**
- Easy to add new validation strategies
- Composable validation logic
- Clear, single-purpose functions

#### 3. Builder Pattern (Configuration)

```python
config = RetryConfig(
    max_attempts=5,
    base_delay=0.5,
    max_delay=30.0,
    exponential_base=2.0,
    jitter=True,
    exceptions=(IOError, TimeoutError),
)

@retry_with_config(config)
def operation():
    pass
```

**Benefits:**
- Explicit configuration
- Reusable configurations
- Type-safe parameter validation

#### 4. Template Method Pattern (File Operations)

Common file operation structure:

```python
def file_operation(path, data, create_dirs=False):
    # 1. Normalize path
    file_path = Path(path)
    
    # 2. Create directories if needed
    if create_dirs:
        ensure_directories(file_path)
    
    # 3. Perform operation (varies by function)
    perform_specific_operation(file_path, data)
    
    # 4. Handle errors consistently
```

**Benefits:**
- Consistent behavior across file operations
- Reduces code duplication
- Easy to maintain and extend

## Data Flow Architecture

### Immutability Preference

Functions prefer immutable operations:

```python
# Returns new list, doesn't modify input
def unique(lst: List[T]) -> List[T]:
    result = []
    # ... build new list
    return result

# Returns new dict, doesn't modify inputs
def merge(dict1: Dict, dict2: Dict) -> Dict:
    result = deepcopy(dict1)
    # ... merge into result
    return result
```

**Rationale:**
- Prevents unexpected side effects
- Easier to reason about code behavior
- Supports functional programming style

### Type Conversion Strategy

Explicit type conversions at boundaries:

```python
def set_value(path: Union[str, Path], section: str, key: str, value: Any) -> None:
    # Convert to Path at entry
    file_path = Path(path)
    
    # Convert value to string for INI format
    config.set(section, key, str(value))
```

**Benefits:**
- Clear type expectations
- Consistent internal representations
- Explicit conversion points

## Error Handling Strategy

### Exception Hierarchy

```
Exception
├── ValueError          # Invalid input values
├── TypeError           # Wrong types
├── FileNotFoundError   # Missing files
├── PermissionError     # Access denied
├── IOError             # General I/O errors
└── json.JSONDecodeError  # JSON parsing errors
```

### Error Message Format

Consistent error message structure:

```python
raise ErrorType(f"{context}: {specific_issue}")

# Examples:
raise FileNotFoundError(f"File not found: {path}")
raise ValueError(f"Chunk size must be at least 1")
raise IOError(f"Error reading file {path}: {e}")
```

**Benefits:**
- Clear context for debugging
- Consistent format across library
- Actionable error messages

## Performance Considerations

### Algorithm Choices

1. **GCD/LCM**: Euclidean algorithm (O(log min(a,b)))
2. **Prime checking**: Trial division up to √n (O(√n))
3. **List flattening**: Recursive approach (O(n) where n is total elements)
4. **Unique elements**: Set-based deduplication (O(n))

### Memory Efficiency

- Use generators where appropriate (not implemented yet, future consideration)
- Avoid unnecessary copies (use views when possible)
- Stream large files instead of loading entirely

### Lazy Evaluation

Currently not implemented, but future consideration for:
- Large file processing
- Expensive computations
- Optional operations

## Testing Strategy

### Test Organization

```
test_module_utils.py
├── TestFunctionName
│   ├── test_basic_case
│   ├── test_edge_case_1
│   ├── test_edge_case_2
│   ├── test_error_condition
│   └── test_special_input
```

### Test Coverage Goals

- **Line coverage**: >95%
- **Branch coverage**: >90%
- **Edge cases**: Explicitly tested
- **Error paths**: All error conditions tested

### Test Patterns

```python
class TestFunction:
    def test_basic_case(self):
        """Test normal, expected usage."""
        result = function(normal_input)
        assert result == expected_output
    
    def test_edge_case(self):
        """Test boundary conditions."""
        result = function(edge_input)
        assert result == edge_output
    
    def test_error_condition(self):
        """Test error handling."""
        with pytest.raises(ExpectedError):
            function(invalid_input)
```

## Security Considerations

### Path Traversal Prevention

```python
def is_subpath(path: Union[str, Path], parent: Union[str, Path]) -> bool:
    # Resolve to absolute paths to prevent traversal attacks
    path_obj = Path(path).resolve()
    parent_obj = Path(parent).resolve()
    # ... validation
```

### Input Validation

- All user inputs validated at function boundaries
- Type checking via type hints and runtime checks
- Range validation for numeric inputs
- Format validation for structured data (email, URL, etc.)

### Safe Defaults

- File operations default to safe modes (no overwrite without explicit flag)
- Directory creation requires explicit opt-in
- Encoding defaults to UTF-8
- Error on ambiguous operations

## Extensibility

### Adding New Utilities

To add a new utility module:

1. Create `new_utils.py` with focused functionality
2. Follow existing patterns (type hints, docstrings, error handling)
3. Create `test_new_utils.py` with comprehensive tests
4. Update `__init__.py` if exposing at package level
5. Document in README.md and USAGE.md

### Backward Compatibility

- Function signatures are stable
- New parameters added as optional with defaults
- Deprecation warnings before removal
- Semantic versioning for releases

## Future Enhancements

### Planned Features

1. **Async Support**: Async versions of I/O operations
2. **Streaming**: Generator-based processing for large files
3. **Caching**: Memoization decorators for expensive operations
4. **Validation**: Schema validation utilities
5. **Serialization**: Additional formats (YAML, TOML, XML)

### Performance Optimizations

1. **C Extensions**: Optional C extensions for hot paths
2. **Parallel Processing**: Multi-threaded/multi-process utilities
3. **Memory Mapping**: For large file operations

## Conclusion

Telemetry Utils v5 is designed to be:

- **Simple**: Easy to understand and use
- **Reliable**: Comprehensive error handling and testing
- **Maintainable**: Clear structure and documentation
- **Extensible**: Easy to add new functionality
- **Safe**: Defensive programming and input validation

The design prioritizes developer experience while maintaining high code quality and reliability standards.
