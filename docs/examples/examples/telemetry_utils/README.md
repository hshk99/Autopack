# Telemetry Utils

A collection of utility functions for common programming tasks including string manipulation, number operations, list processing, date handling, and dictionary operations.

## Overview

This package provides well-tested, reusable utility functions organized into focused modules:

- **String Helper**: Text manipulation utilities
- **Number Helper**: Mathematical operations and checks
- **List Helper**: Collection processing functions
- **Date Helper**: Date formatting and arithmetic
- **Dictionary Helper**: Nested dictionary operations

## Installation

This package is part of the examples directory. To use it:

```python
from examples.telemetry_utils import capitalize_words, is_prime, chunk
```

## Modules

### String Helper (`string_helper.py`)

Utilities for string manipulation.

#### Functions

**`capitalize_words(text: str, delimiter: Optional[str] = None) -> str`**

Capitalize the first letter of each word in a string.

```python
from examples.telemetry_utils.string_helper import capitalize_words

# Basic usage
result = capitalize_words("hello world")
print(result)  # Output: "Hello World"

# With custom delimiter
result = capitalize_words("hello-world-example", delimiter="-")
print(result)  # Output: "Hello-World-Example"

# Empty string
result = capitalize_words("")
print(result)  # Output: ""
```

**`reverse_string(text: str) -> str`**

Reverse a string.

```python
from examples.telemetry_utils.string_helper import reverse_string

# Basic usage
result = reverse_string("hello")
print(result)  # Output: "olleh"

# Palindrome
result = reverse_string("racecar")
print(result)  # Output: "racecar"

# With spaces
result = reverse_string("hello world")
print(result)  # Output: "dlrow olleh"
```

### Number Helper (`number_helper.py`)

Utilities for number operations.

#### Functions

**`is_even(n: int) -> bool`**

Check if a number is even.

```python
from examples.telemetry_utils.number_helper import is_even

print(is_even(4))   # Output: True
print(is_even(7))   # Output: False
print(is_even(0))   # Output: True
print(is_even(-2))  # Output: True
```

**`is_prime(n: int) -> bool`**

Check if a number is prime.

```python
from examples.telemetry_utils.number_helper import is_prime

print(is_prime(2))   # Output: True
print(is_prime(17))  # Output: True
print(is_prime(4))   # Output: False
print(is_prime(1))   # Output: False
print(is_prime(-5))  # Output: False
```

**`factorial(n: int) -> int`**

Calculate the factorial of a non-negative integer.

```python
from examples.telemetry_utils.number_helper import factorial

print(factorial(0))   # Output: 1
print(factorial(5))   # Output: 120
print(factorial(10))  # Output: 3628800

# Raises ValueError for negative numbers
try:
    factorial(-1)
except ValueError as e:
    print(e)  # Output: "Factorial is not defined for negative numbers"
```

### List Helper (`list_helper.py`)

Utilities for list operations.

#### Functions

**`chunk(items: List[T], size: int) -> List[List[T]]`**

Split a list into chunks of specified size.

```python
from examples.telemetry_utils.list_helper import chunk

result = chunk([1, 2, 3, 4, 5], 2)
print(result)  # Output: [[1, 2], [3, 4], [5]]

result = chunk([1, 2, 3, 4, 5, 6], 3)
print(result)  # Output: [[1, 2, 3], [4, 5, 6]]

result = chunk([], 2)
print(result)  # Output: []
```

**`flatten(items: List[Any]) -> List[Any]`**

Flatten a nested list structure by one level.

```python
from examples.telemetry_utils.list_helper import flatten

result = flatten([[1, 2], [3, 4], [5]])
print(result)  # Output: [1, 2, 3, 4, 5]

result = flatten([1, [2, 3], 4])
print(result)  # Output: [1, 2, 3, 4]

result = flatten([])
print(result)  # Output: []
```

**`unique(items: List[T]) -> List[T]`**

Remove duplicate elements while preserving order.

```python
from examples.telemetry_utils.list_helper import unique

result = unique([1, 2, 2, 3, 1, 4])
print(result)  # Output: [1, 2, 3, 4]

result = unique(['a', 'b', 'a', 'c'])
print(result)  # Output: ['a', 'b', 'c']

result = unique([])
print(result)  # Output: []
```

**`group_by(items: List[T], key_func: Callable[[T], K]) -> Dict[K, List[T]]`**

Group list elements by a key function.

```python
from examples.telemetry_utils.list_helper import group_by

# Group by even/odd
result = group_by([1, 2, 3, 4, 5, 6], lambda x: x % 2)
print(result)  # Output: {1: [1, 3, 5], 0: [2, 4, 6]}

# Group by first letter
words = ['apple', 'apricot', 'banana', 'blueberry']
result = group_by(words, lambda x: x[0])
print(result)  # Output: {'a': ['apple', 'apricot'], 'b': ['banana', 'blueberry']}
```

### Date Helper (`date_helper.py`)

Utilities for date operations.

#### Functions

**`format_date(date: datetime, format_string: str = "%Y-%m-%d") -> str`**

Format a datetime object as a string.

```python
from datetime import datetime
from examples.telemetry_utils.date_helper import format_date

dt = datetime(2024, 1, 15, 10, 30, 45)

print(format_date(dt))  # Output: "2024-01-15"
print(format_date(dt, "%Y/%m/%d"))  # Output: "2024/01/15"
print(format_date(dt, "%B %d, %Y"))  # Output: "January 15, 2024"
print(format_date(dt, "%Y-%m-%d %H:%M:%S"))  # Output: "2024-01-15 10:30:45"
```

**`parse_date(date_string: str, format_string: str = "%Y-%m-%d") -> datetime`**

Parse a date string into a datetime object.

```python
from examples.telemetry_utils.date_helper import parse_date

dt = parse_date("2024-01-15")
print(dt)  # Output: datetime.datetime(2024, 1, 15, 0, 0)

dt = parse_date("2024/01/15", "%Y/%m/%d")
print(dt)  # Output: datetime.datetime(2024, 1, 15, 0, 0)

dt = parse_date("January 15, 2024", "%B %d, %Y")
print(dt)  # Output: datetime.datetime(2024, 1, 15, 0, 0)
```

**`add_days(date: datetime, days: int) -> datetime`**

Add a number of days to a date.

```python
from datetime import datetime
from examples.telemetry_utils.date_helper import add_days

dt = datetime(2024, 1, 15)

result = add_days(dt, 5)
print(result)  # Output: datetime.datetime(2024, 1, 20, 0, 0)

result = add_days(dt, -5)
print(result)  # Output: datetime.datetime(2024, 1, 10, 0, 0)

result = add_days(dt, 365)
print(result)  # Output: datetime.datetime(2025, 1, 15, 0, 0)
```

**`diff_days(date1: datetime, date2: datetime) -> int`**

Calculate the difference in days between two dates.

```python
from datetime import datetime
from examples.telemetry_utils.date_helper import diff_days

dt1 = datetime(2024, 1, 20)
dt2 = datetime(2024, 1, 15)

print(diff_days(dt1, dt2))  # Output: 5
print(diff_days(dt2, dt1))  # Output: -5
print(diff_days(dt1, dt1))  # Output: 0
```

### Dictionary Helper (`dict_helper.py`)

Utilities for dictionary operations.

#### Functions

**`deep_merge(dict1: Dict[str, Any], dict2: Dict[str, Any]) -> Dict[str, Any]`**

Deep merge two dictionaries.

```python
from examples.telemetry_utils.dict_helper import deep_merge

dict1 = {'a': 1, 'b': {'x': 10, 'y': 20}}
dict2 = {'b': {'y': 25, 'z': 30}, 'c': 3}
result = deep_merge(dict1, dict2)
print(result)  # Output: {'a': 1, 'b': {'x': 10, 'y': 25, 'z': 30}, 'c': 3}

dict3 = {'user': {'name': 'John', 'age': 30}}
dict4 = {'user': {'age': 31, 'city': 'NYC'}}
result = deep_merge(dict3, dict4)
print(result)  # Output: {'user': {'name': 'John', 'age': 31, 'city': 'NYC'}}
```

**`get_nested(data: Dict[str, Any], path: str, default: Any = None, separator: str = ".") -> Any`**

Get a value from a nested dictionary using a path string.

```python
from examples.telemetry_utils.dict_helper import get_nested

data = {
    'user': {
        'name': 'John',
        'address': {
            'city': 'NYC',
            'zip': '10001'
        }
    }
}

print(get_nested(data, 'user.name'))  # Output: 'John'
print(get_nested(data, 'user.address.city'))  # Output: 'NYC'
print(get_nested(data, 'user.age', default=0))  # Output: 0
```

**`set_nested(data: Dict[str, Any], path: str, value: Any, separator: str = ".") -> Dict[str, Any]`**

Set a value in a nested dictionary using a path string.

```python
from examples.telemetry_utils.dict_helper import set_nested

result = set_nested({}, 'user.name', 'John')
print(result)  # Output: {'user': {'name': 'John'}}

result = set_nested({'user': {'name': 'John'}}, 'user.age', 30)
print(result)  # Output: {'user': {'name': 'John', 'age': 30}}

result = set_nested({}, 'a.b.c.d', 'value')
print(result)  # Output: {'a': {'b': {'c': {'d': 'value'}}}}
```

**`filter_keys(data: Dict[str, Any], predicate: Callable[[str], bool]) -> Dict[str, Any]`**

Filter dictionary keys based on a predicate function.

```python
from examples.telemetry_utils.dict_helper import filter_keys

data = {'name': 'John', 'age': 30, 'city': 'NYC', 'country': 'USA'}

# Keep only specific keys
result = filter_keys(data, lambda k: k in ['name', 'age'])
print(result)  # Output: {'name': 'John', 'age': 30}

# Keep keys starting with 'c'
result = filter_keys(data, lambda k: k.startswith('c'))
print(result)  # Output: {'city': 'NYC', 'country': 'USA'}

# Keep keys with length <= 4
result = filter_keys(data, lambda k: len(k) <= 4)
print(result)  # Output: {'name': 'John', 'age': 30, 'city': 'NYC'}
```

## Running Examples

Each module includes a `__main__` block with demonstration code. Run them directly:

```bash
# String helper demo
python -m examples.telemetry_utils.string_helper

# Number helper demo
python -m examples.telemetry_utils.number_helper

# List helper demo
python -m examples.telemetry_utils.list_helper

# Date helper demo
python -m examples.telemetry_utils.date_helper

# Dictionary helper demo
python -m examples.telemetry_utils.dict_helper
```

## Running Tests

The package includes comprehensive test coverage using pytest:

```bash
# Run all tests
pytest examples/telemetry_utils/

# Run tests for a specific module
pytest examples/telemetry_utils/test_string_helper.py
pytest examples/telemetry_utils/test_number_helper.py
pytest examples/telemetry_utils/test_list_helper.py

# Run with coverage
pytest examples/telemetry_utils/ --cov=examples.telemetry_utils

# Run only fast tests (exclude slow tests)
pytest examples/telemetry_utils/ -m "not slow"

# Run only unit tests
pytest examples/telemetry_utils/ -m unit

# Verbose output
pytest examples/telemetry_utils/ -v
```

## Complete Usage Example

Here's a complete example combining multiple utilities:

```python
from datetime import datetime
from examples.telemetry_utils.string_helper import capitalize_words, reverse_string
from examples.telemetry_utils.number_helper import is_prime, factorial
from examples.telemetry_utils.list_helper import chunk, unique, group_by
from examples.telemetry_utils.date_helper import format_date, add_days
from examples.telemetry_utils.dict_helper import deep_merge, get_nested

# String operations
text = "hello world"
capitalized = capitalize_words(text)
reversed_text = reverse_string(capitalized)
print(f"Original: {text}")
print(f"Capitalized: {capitalized}")
print(f"Reversed: {reversed_text}")

# Number operations
numbers = [2, 3, 4, 5, 6, 7, 8, 9, 10]
primes = [n for n in numbers if is_prime(n)]
print(f"Prime numbers: {primes}")
print(f"5! = {factorial(5)}")

# List operations
data = [1, 2, 2, 3, 4, 4, 5, 6, 7, 8, 9, 10]
unique_data = unique(data)
chunked = chunk(unique_data, 3)
grouped = group_by(unique_data, lambda x: 'even' if x % 2 == 0 else 'odd')
print(f"Unique: {unique_data}")
print(f"Chunked: {chunked}")
print(f"Grouped: {grouped}")

# Date operations
today = datetime.now()
formatted = format_date(today, "%B %d, %Y")
future = add_days(today, 30)
print(f"Today: {formatted}")
print(f"30 days from now: {format_date(future)}")

# Dictionary operations
config1 = {'database': {'host': 'localhost', 'port': 5432}}
config2 = {'database': {'port': 5433, 'name': 'mydb'}, 'cache': {'enabled': True}}
merged_config = deep_merge(config1, config2)
db_host = get_nested(merged_config, 'database.host')
print(f"Merged config: {merged_config}")
print(f"Database host: {db_host}")
```

## Features

- **Type Hints**: All functions include comprehensive type hints for better IDE support
- **Docstrings**: Detailed docstrings with examples for every function
- **Error Handling**: Proper error handling with descriptive error messages
- **Test Coverage**: Comprehensive test suite with >95% coverage
- **Performance**: Optimized implementations for common operations
- **Pure Functions**: Most functions are pure with no side effects

## Design Principles

1. **Simplicity**: Each function does one thing well
2. **Immutability**: Functions return new values rather than modifying inputs
3. **Composability**: Functions can be easily combined
4. **Testability**: All functions are thoroughly tested
5. **Documentation**: Clear examples and usage patterns

## Contributing

When adding new utilities:

1. Add comprehensive docstrings with examples
2. Include type hints for all parameters and return values
3. Write comprehensive tests (aim for >95% coverage)
4. Add usage examples to this README
5. Include a `__main__` block with demonstration code

## License

This is example code for demonstration purposes.
