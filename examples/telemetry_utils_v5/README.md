# Telemetry Utils v5

A comprehensive collection of utility functions for common programming tasks in Python. This package provides well-tested, documented utilities for string manipulation, number operations, list processing, dictionary handling, validation, date operations, file I/O, and more.

## Features

- **String Utilities**: Text manipulation, case conversion, truncation
- **Number Utilities**: Prime checking, GCD/LCM calculations, even/odd detection
- **List Utilities**: Chunking, flattening, deduplication, rotation
- **Dictionary Utilities**: Deep merging, nested access, filtering, inversion
- **Validation Utilities**: Email/URL validation, type checking, range validation
- **Date Utilities**: Date formatting, parsing, arithmetic, weekend detection
- **Path Utilities**: Path joining, extension handling, subpath checking
- **File I/O Utilities**: Safe file reading/writing with encoding support
- **JSON Utilities**: JSON loading, saving, validation, pretty printing
- **CSV Utilities**: CSV reading, writing, dict conversion
- **INI Utilities**: INI file reading, writing, value access
- **Logging Utilities**: Logger setup, file logging configuration
- **Retry Utilities**: Exponential backoff, retry decorators
- **Text Wrapping Utilities**: Text wrapping, indentation, dedentation

## Installation

### From Source

```bash
# Clone the repository
git clone <repository-url>
cd <repository-directory>

# Install in development mode
pip install -e .
```

### Requirements

- Python 3.7+
- No external dependencies (uses only Python standard library)

## Quick Start

### String Utilities

```python
from examples.telemetry_utils_v5.string_utils import (
    capitalize_words,
    reverse_string,
    snake_to_camel,
    truncate,
)

# Capitalize words
text = "hello world"
print(capitalize_words(text))  # "Hello World"

# Reverse string
print(reverse_string("Python"))  # "nohtyP"

# Convert snake_case to camelCase
print(snake_to_camel("my_variable_name"))  # "myVariableName"
print(snake_to_camel("my_variable_name", upper_first=True))  # "MyVariableName"

# Truncate text
long_text = "This is a very long string"
print(truncate(long_text, 15))  # "This is a ve..."
```

### Number Utilities

```python
from examples.telemetry_utils_v5.number_utils import (
    is_even,
    is_prime,
    gcd,
    lcm,
)

# Check if even
print(is_even(4))  # True
print(is_even(7))  # False

# Check if prime
print(is_prime(17))  # True
print(is_prime(4))   # False

# Calculate GCD and LCM
print(gcd(48, 18))  # 6
print(lcm(4, 6))    # 12
```

### List Utilities

```python
from examples.telemetry_utils_v5.list_utils import (
    chunk,
    flatten,
    unique,
    rotate,
)

# Split list into chunks
data = [1, 2, 3, 4, 5, 6, 7]
print(chunk(data, 3))  # [[1, 2, 3], [4, 5, 6], [7]]

# Flatten nested lists
nested = [1, [2, 3], [4, [5, 6]]]
print(flatten(nested))  # [1, 2, 3, 4, 5, 6]

# Remove duplicates while preserving order
duplicates = [1, 2, 2, 3, 1, 4]
print(unique(duplicates))  # [1, 2, 3, 4]

# Rotate list
print(rotate([1, 2, 3, 4, 5], 2))  # [4, 5, 1, 2, 3]
```

### Dictionary Utilities

```python
from examples.telemetry_utils_v5.dict_utils import (
    merge,
    get_nested,
    filter_keys,
    invert,
)

# Deep merge dictionaries
dict1 = {'a': 1, 'b': {'x': 10}}
dict2 = {'b': {'y': 20}, 'c': 3}
print(merge(dict1, dict2))  # {'a': 1, 'b': {'x': 10, 'y': 20}, 'c': 3}

# Access nested values
data = {'user': {'profile': {'name': 'John'}}}
print(get_nested(data, 'user.profile.name'))  # 'John'

# Filter dictionary keys
data = {'a': 1, 'b': 2, 'c': 3}
print(filter_keys(data, ['a', 'c']))  # {'a': 1, 'c': 3}

# Invert dictionary
print(invert({'a': 1, 'b': 2}))  # {1: 'a', 2: 'b'}
```

### Validation Utilities

```python
from examples.telemetry_utils_v5.validation_utils import (
    is_email,
    is_url,
    is_int,
    is_float,
    validate_range,
)

# Validate email
print(is_email('user@example.com'))  # True
print(is_email('invalid.email'))     # False

# Validate URL
print(is_url('https://www.example.com'))  # True
print(is_url('not a url'))                # False

# Check if string is integer/float
print(is_int('123'))    # True
print(is_float('3.14')) # True

# Validate numeric range
print(validate_range(5, min_value=0, max_value=10))  # True
print(validate_range(15, min_value=0, max_value=10)) # False
```

### Date Utilities

```python
from datetime import date
from examples.telemetry_utils_v5.date_utils import (
    format_date,
    parse_date,
    add_days,
    diff_days,
    is_weekend,
)

# Format date
dt = date(2023, 12, 25)
print(format_date(dt))  # '2023-12-25'
print(format_date(dt, "%m/%d/%Y"))  # '12/25/2023'

# Parse date string
dt = parse_date("2023-12-25")
print(dt)  # date(2023, 12, 25)

# Add days
print(add_days(date(2023, 12, 25), 7))  # date(2024, 1, 1)

# Calculate difference
print(diff_days(date(2023, 12, 25), date(2024, 1, 1)))  # 7

# Check if weekend
print(is_weekend(date(2023, 12, 23)))  # True (Saturday)
```

### File I/O Utilities

```python
from examples.telemetry_utils_v5.io_utils import (
    read_file,
    write_file,
    read_lines,
    write_lines,
)

# Read entire file
content = read_file('data.txt')

# Write to file
write_file('output.txt', 'Hello, World!')

# Read file as lines
lines = read_lines('data.txt')

# Write lines to file
write_lines('output.txt', ['Line 1', 'Line 2', 'Line 3'])
```

### JSON Utilities

```python
from examples.telemetry_utils_v5.json_utils import (
    load_json,
    save_json,
    pretty_print,
    validate_json,
)

# Load JSON file
data = load_json('config.json')

# Save to JSON file
save_json('output.json', {'name': 'Alice', 'age': 30})

# Pretty print JSON
print(pretty_print({'name': 'Bob', 'age': 25}))

# Validate JSON string
print(validate_json('{"valid": true}'))  # True
```

### Retry Utilities

```python
from examples.telemetry_utils_v5.retry_utils import (
    retry_on_exception,
    exponential_backoff,
)

# Retry function on exception
@retry_on_exception(max_attempts=3, base_delay=1.0)
def flaky_api_call():
    # Your code that might fail
    pass

# Calculate backoff delay
delay = exponential_backoff(attempt=2, base_delay=1.0)
```

## CLI Demo

The package includes a command-line demo to showcase all utilities:

```bash
# Run all demos
python -m examples.telemetry_utils_v5.cli --all

# Run specific demos
python -m examples.telemetry_utils_v5.cli --string
python -m examples.telemetry_utils_v5.cli --number
python -m examples.telemetry_utils_v5.cli --list
python -m examples.telemetry_utils_v5.cli --dict
python -m examples.telemetry_utils_v5.cli --validation

# Show help
python -m examples.telemetry_utils_v5.cli --help
```

## Testing

The package includes comprehensive test coverage using pytest:

```bash
# Run all tests
pytest examples/telemetry_utils_v5/

# Run specific test file
pytest examples/telemetry_utils_v5/test_string_utils.py

# Run with coverage
pytest --cov=examples.telemetry_utils_v5 examples/telemetry_utils_v5/
```

## Module Overview

### Core Modules

- `string_utils.py` - String manipulation functions
- `number_utils.py` - Number operations and math utilities
- `list_utils.py` - List processing and manipulation
- `dict_utils.py` - Dictionary operations
- `validation_utils.py` - Data validation functions
- `date_utils.py` - Date and time utilities

### File Operations

- `io_utils.py` - Safe file reading and writing
- `json_utils.py` - JSON file operations
- `csv_utils.py` - CSV file operations
- `ini_utils.py` - INI file operations
- `path_utils.py` - Path manipulation utilities

### Advanced Utilities

- `logging_utils.py` - Logging configuration
- `retry_utils.py` - Retry logic with exponential backoff
- `textwrap_utils.py` - Text wrapping and formatting

## API Documentation

All functions include comprehensive docstrings with:
- Detailed parameter descriptions
- Return value documentation
- Usage examples
- Exception information

Use Python's built-in help system:

```python
from examples.telemetry_utils_v5 import string_utils
help(string_utils.capitalize_words)
```

## Design Principles

1. **Pure Python**: No external dependencies, uses only standard library
2. **Type Hints**: Full type annotations for better IDE support
3. **Comprehensive Testing**: Extensive test coverage with pytest
4. **Clear Documentation**: Detailed docstrings with examples
5. **Error Handling**: Proper exception handling with informative messages
6. **Consistent API**: Uniform function signatures and behavior

## Contributing

Contributions are welcome! Please ensure:

1. All new functions include comprehensive docstrings
2. Type hints are provided for all parameters and return values
3. Unit tests are included with good coverage
4. Code follows existing style conventions
5. Examples are provided in docstrings

## License

This project is provided as-is for educational and utility purposes.

## Version

Current version: 5.0.0

## Support

For issues, questions, or contributions, please refer to the project repository.
