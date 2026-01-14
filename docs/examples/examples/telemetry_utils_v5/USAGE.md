# Telemetry Utils v5 - Usage Guide

This guide provides detailed examples for each utility module in the telemetry_utils_v5 package.

## Table of Contents

- [String Utilities](#string-utilities)
- [Number Utilities](#number-utilities)
- [List Utilities](#list-utilities)
- [Dictionary Utilities](#dictionary-utilities)
- [Validation Utilities](#validation-utilities)
- [Date Utilities](#date-utilities)
- [Path Utilities](#path-utilities)
- [File I/O Utilities](#file-io-utilities)
- [JSON Utilities](#json-utilities)
- [CSV Utilities](#csv-utilities)
- [INI Utilities](#ini-utilities)
- [Logging Utilities](#logging-utilities)
- [Retry Utilities](#retry-utilities)
- [Text Wrapping Utilities](#text-wrapping-utilities)

---

## String Utilities

Module: `string_utils.py`

### capitalize_words

Capitalize the first letter of each word in a string.

```python
from examples.telemetry_utils_v5.string_utils import capitalize_words

# Basic usage
text = "hello world from python"
result = capitalize_words(text)
print(result)  # "Hello World From Python"

# With mixed case
text = "tHe QuIcK bRoWn FoX"
result = capitalize_words(text)
print(result)  # "The Quick Brown Fox"

# Empty string
result = capitalize_words("")
print(result)  # ""

# Single word
result = capitalize_words("python")
print(result)  # "Python"
```

### reverse_string

Reverse the characters in a string.

```python
from examples.telemetry_utils_v5.string_utils import reverse_string

# Basic usage
text = "hello"
result = reverse_string(text)
print(result)  # "olleh"

# With spaces
text = "hello world"
result = reverse_string(text)
print(result)  # "dlrow olleh"

# Palindrome
text = "racecar"
result = reverse_string(text)
print(result)  # "racecar"

# Empty string
result = reverse_string("")
print(result)  # ""
```

### snake_to_camel

Convert snake_case strings to camelCase or PascalCase.

```python
from examples.telemetry_utils_v5.string_utils import snake_to_camel

# Convert to camelCase
snake = "my_variable_name"
result = snake_to_camel(snake)
print(result)  # "myVariableName"

# Convert to PascalCase
snake = "user_profile_data"
result = snake_to_camel(snake, upper_first=True)
print(result)  # "UserProfileData"

# Single word
result = snake_to_camel("hello")
print(result)  # "hello"

result = snake_to_camel("hello", upper_first=True)
print(result)  # "Hello"

# Empty string
result = snake_to_camel("")
print(result)  # ""
```

### truncate

Truncate a string to a maximum length with a suffix.

```python
from examples.telemetry_utils_v5.string_utils import truncate

# Basic truncation
long_text = "This is a very long string that needs to be truncated"
result = truncate(long_text, 20)
print(result)  # "This is a very lo..."

# Custom suffix
result = truncate(long_text, 20, suffix="…")
print(result)  # "This is a very lon…"

# No truncation needed
short_text = "Short"
result = truncate(short_text, 10)
print(result)  # "Short"

# Exact length
text = "Hello"
result = truncate(text, 5)
print(result)  # "Hello"
```

---

## Number Utilities

Module: `number_utils.py`

### is_even

Check if a number is even.

```python
from examples.telemetry_utils_v5.number_utils import is_even

# Positive numbers
print(is_even(4))   # True
print(is_even(7))   # False
print(is_even(100)) # True

# Zero
print(is_even(0))   # True

# Negative numbers
print(is_even(-2))  # True
print(is_even(-3))  # False

# Use in filtering
numbers = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
even_numbers = [n for n in numbers if is_even(n)]
print(even_numbers)  # [2, 4, 6, 8, 10]
```

### is_prime

Check if a number is prime.

```python
from examples.telemetry_utils_v5.number_utils import is_prime

# Small primes
print(is_prime(2))   # True
print(is_prime(3))   # True
print(is_prime(5))   # True
print(is_prime(7))   # True

# Composite numbers
print(is_prime(4))   # False
print(is_prime(9))   # False
print(is_prime(100)) # False

# Edge cases
print(is_prime(1))   # False
print(is_prime(0))   # False
print(is_prime(-5))  # False

# Larger primes
print(is_prime(17))  # True
print(is_prime(97))  # True

# Find primes in range
primes = [n for n in range(2, 20) if is_prime(n)]
print(primes)  # [2, 3, 5, 7, 11, 13, 17, 19]
```

### gcd

Calculate the greatest common divisor of two numbers.

```python
from examples.telemetry_utils_v5.number_utils import gcd

# Basic usage
print(gcd(48, 18))   # 6
print(gcd(100, 50))  # 50

# Coprime numbers (GCD = 1)
print(gcd(17, 19))   # 1
print(gcd(13, 7))    # 1

# With zero
print(gcd(0, 5))     # 5
print(gcd(10, 0))    # 10

# Negative numbers
print(gcd(-48, 18))  # 6
print(gcd(48, -18))  # 6

# Same numbers
print(gcd(42, 42))   # 42
```

### lcm

Calculate the least common multiple of two numbers.

```python
from examples.telemetry_utils_v5.number_utils import lcm

# Basic usage
print(lcm(4, 6))     # 12
print(lcm(21, 6))    # 42

# Coprime numbers
print(lcm(5, 7))     # 35
print(lcm(13, 17))   # 221

# Same numbers
print(lcm(10, 10))   # 10

# With one
print(lcm(1, 5))     # 5
print(lcm(10, 1))    # 10

# With zero
print(lcm(0, 5))     # 0
print(lcm(10, 0))    # 0

# Negative numbers
print(lcm(-4, 6))    # 12
print(lcm(4, -6))    # 12
```

---

## List Utilities

Module: `list_utils.py`

### chunk

Split a list into chunks of specified size.

```python
from examples.telemetry_utils_v5.list_utils import chunk

# Basic usage
data = [1, 2, 3, 4, 5, 6, 7, 8, 9]
result = chunk(data, 3)
print(result)  # [[1, 2, 3], [4, 5, 6], [7, 8, 9]]

# Uneven division
data = [1, 2, 3, 4, 5]
result = chunk(data, 2)
print(result)  # [[1, 2], [3, 4], [5]]

# Chunk size larger than list
data = [1, 2, 3]
result = chunk(data, 5)
print(result)  # [[1, 2, 3]]

# Empty list
result = chunk([], 2)
print(result)  # []

# Process data in batches
data = list(range(100))
for batch in chunk(data, 10):
    print(f"Processing batch of {len(batch)} items")
```

### flatten

Flatten a nested list structure.

```python
from examples.telemetry_utils_v5.list_utils import flatten

# Basic nested list
nested = [1, [2, 3], [4, [5, 6]]]
result = flatten(nested)
print(result)  # [1, 2, 3, 4, 5, 6]

# Deeply nested
nested = [1, [2, [3, [4]]]]
result = flatten(nested)
print(result)  # [1, 2, 3, 4]

# Already flat
flat = [1, 2, 3]
result = flatten(flat)
print(result)  # [1, 2, 3]

# Mixed types
nested = [1, ['a', 'b'], [2, [3, 'c']]]
result = flatten(nested)
print(result)  # [1, 'a', 'b', 2, 3, 'c']

# Empty list
result = flatten([])
print(result)  # []
```

### unique

Remove duplicate elements while preserving order.

```python
from examples.telemetry_utils_v5.list_utils import unique

# Basic usage
data = [1, 2, 2, 3, 1, 4]
result = unique(data)
print(result)  # [1, 2, 3, 4]

# Preserves order
data = [3, 1, 2, 1, 3, 2]
result = unique(data)
print(result)  # [3, 1, 2]

# No duplicates
data = [1, 2, 3]
result = unique(data)
print(result)  # [1, 2, 3]

# All same
data = [1, 1, 1, 1]
result = unique(data)
print(result)  # [1]

# Strings
data = ['a', 'b', 'a', 'c', 'b']
result = unique(data)
print(result)  # ['a', 'b', 'c']
```

### rotate

Rotate list elements by a specified number of positions.

```python
from examples.telemetry_utils_v5.list_utils import rotate

# Rotate right
data = [1, 2, 3, 4, 5]
result = rotate(data, 2)
print(result)  # [4, 5, 1, 2, 3]

# Rotate left
result = rotate(data, -2)
print(result)  # [3, 4, 5, 1, 2]

# No rotation
result = rotate(data, 0)
print(result)  # [1, 2, 3, 4, 5]

# Full cycle
result = rotate(data, 5)
print(result)  # [1, 2, 3, 4, 5]

# More than length
result = rotate(data, 7)  # Same as rotate by 2
print(result)  # [4, 5, 1, 2, 3]

# Empty list
result = rotate([], 5)
print(result)  # []
```

---

## Dictionary Utilities

Module: `dict_utils.py`

### merge

Deep merge two dictionaries.

```python
from examples.telemetry_utils_v5.dict_utils import merge

# Basic merge
dict1 = {'a': 1, 'b': 2}
dict2 = {'b': 3, 'c': 4}
result = merge(dict1, dict2)
print(result)  # {'a': 1, 'b': 3, 'c': 4}

# Deep merge
dict1 = {'a': {'x': 1, 'y': 2}}
dict2 = {'a': {'y': 3, 'z': 4}}
result = merge(dict1, dict2, deep=True)
print(result)  # {'a': {'x': 1, 'y': 3, 'z': 4}}

# Shallow merge
result = merge(dict1, dict2, deep=False)
print(result)  # {'a': {'y': 3, 'z': 4}}

# Empty dictionaries
result = merge({}, {'a': 1})
print(result)  # {'a': 1}

# Configuration merging
defaults = {'timeout': 30, 'retry': {'max': 3, 'delay': 1}}
user_config = {'retry': {'max': 5}}
config = merge(defaults, user_config, deep=True)
print(config)  # {'timeout': 30, 'retry': {'max': 5, 'delay': 1}}
```

### get_nested

Get a value from a nested dictionary using a key path.

```python
from examples.telemetry_utils_v5.dict_utils import get_nested

# Basic nested access
data = {'user': {'profile': {'name': 'John', 'age': 30}}}
result = get_nested(data, 'user.profile.name')
print(result)  # 'John'

# Single level
data = {'a': 1}
result = get_nested(data, 'a')
print(result)  # 1

# Missing key with default
result = get_nested(data, 'user.email', default='N/A')
print(result)  # 'N/A'

# Custom separator
data = {'a': {'b': 1}}
result = get_nested(data, 'a/b', separator='/')
print(result)  # 1

# API response parsing
api_response = {
    'data': {
        'user': {
            'profile': {
                'email': 'user@example.com'
            }
        }
    }
}
email = get_nested(api_response, 'data.user.profile.email')
print(email)  # 'user@example.com'
```

### filter_keys

Filter dictionary by keeping or excluding specified keys.

```python
from examples.telemetry_utils_v5.dict_utils import filter_keys

# Keep specific keys
data = {'a': 1, 'b': 2, 'c': 3, 'd': 4}
result = filter_keys(data, ['a', 'c'])
print(result)  # {'a': 1, 'c': 3}

# Exclude specific keys
result = filter_keys(data, ['b', 'd'], exclude=True)
print(result)  # {'a': 1, 'c': 3}

# Non-existent keys
result = filter_keys(data, ['x', 'y'])
print(result)  # {}

# Empty key list
result = filter_keys(data, [])
print(result)  # {}

result = filter_keys(data, [], exclude=True)
print(result)  # {'a': 1, 'b': 2, 'c': 3, 'd': 4}

# Sanitize sensitive data
user_data = {'name': 'John', 'email': 'john@example.com', 'password': 'secret'}
safe_data = filter_keys(user_data, ['password'], exclude=True)
print(safe_data)  # {'name': 'John', 'email': 'john@example.com'}
```

### invert

Invert a dictionary by swapping keys and values.

```python
from examples.telemetry_utils_v5.dict_utils import invert

# Basic inversion
data = {'a': 1, 'b': 2, 'c': 3}
result = invert(data)
print(result)  # {1: 'a', 2: 'b', 3: 'c'}

# String values
data = {'x': 'foo', 'y': 'bar'}
result = invert(data)
print(result)  # {'foo': 'x', 'bar': 'y'}

# Empty dictionary
result = invert({})
print(result)  # {}

# Lookup table inversion
status_codes = {200: 'OK', 404: 'Not Found', 500: 'Server Error'}
status_names = invert(status_codes)
print(status_names)  # {'OK': 200, 'Not Found': 404, 'Server Error': 500}
```

---

## Validation Utilities

Module: `validation_utils.py`

### is_email

Validate if a string is a valid email address.

```python
from examples.telemetry_utils_v5.validation_utils import is_email

# Valid emails
print(is_email('user@example.com'))        # True
print(is_email('john.doe@company.co.uk'))  # True
print(is_email('test+tag@domain.com'))     # True

# Invalid emails
print(is_email('invalid.email'))           # False
print(is_email('@nodomain.com'))           # False
print(is_email('missing@domain'))          # False
print(is_email(''))                        # False

# Form validation
email = input("Enter email: ")
if is_email(email):
    print("Valid email")
else:
    print("Invalid email format")
```

### is_url

Validate if a string is a valid URL.

```python
from examples.telemetry_utils_v5.validation_utils import is_url

# Valid URLs with scheme
print(is_url('https://www.example.com'))           # True
print(is_url('http://example.com/path?q=value'))  # True
print(is_url('ftp://files.example.com'))           # True

# Without scheme (require_scheme=False)
print(is_url('www.example.com'))                   # False
print(is_url('www.example.com', require_scheme=False))  # True

# Invalid URLs
print(is_url('not a url'))                         # False
print(is_url(''))                                  # False

# Link validation
link = 'https://github.com/user/repo'
if is_url(link):
    print(f"Valid URL: {link}")
```

### is_int and is_float

Check if strings can be converted to numbers.

```python
from examples.telemetry_utils_v5.validation_utils import is_int, is_float

# Integer validation
print(is_int('123'))      # True
print(is_int('-456'))     # True
print(is_int('  789  '))  # True
print(is_int('12.34'))    # False
print(is_int('abc'))      # False

# Float validation
print(is_float('123.45'))  # True
print(is_float('-67.89'))  # True
print(is_float('1e5'))     # True
print(is_float('123'))     # True (integers are valid floats)
print(is_float('abc'))     # False

# Input validation
user_input = input("Enter a number: ")
if is_int(user_input):
    value = int(user_input)
    print(f"Integer: {value}")
elif is_float(user_input):
    value = float(user_input)
    print(f"Float: {value}")
else:
    print("Not a valid number")
```

### validate_range

Validate if a number is within a specified range.

```python
from examples.telemetry_utils_v5.validation_utils import validate_range

# Basic range validation
print(validate_range(5, min_value=0, max_value=10))   # True
print(validate_range(15, min_value=0, max_value=10))  # False

# Inclusive bounds (default)
print(validate_range(10, min_value=0, max_value=10))  # True

# Exclusive bounds
print(validate_range(10, min_value=0, max_value=10, inclusive=False))  # False

# Only minimum
print(validate_range(5, min_value=0))    # True
print(validate_range(-5, min_value=0))   # False

# Only maximum
print(validate_range(100, max_value=50))  # False

# No bounds
print(validate_range(5))  # True

# Age validation
age = 25
if validate_range(age, min_value=18, max_value=120):
    print("Valid age")
else:
    print("Invalid age")
```

---

## Date Utilities

Module: `date_utils.py`

### format_date

Format a date object to a string.

```python
from datetime import date
from examples.telemetry_utils_v5.date_utils import format_date

# Default format (YYYY-MM-DD)
dt = date(2023, 12, 25)
print(format_date(dt))  # '2023-12-25'

# Custom formats
print(format_date(dt, "%m/%d/%Y"))      # '12/25/2023'
print(format_date(dt, "%B %d, %Y"))     # 'December 25, 2023'
print(format_date(dt, "%d-%b-%Y"))      # '25-Dec-2023'
print(format_date(dt, "%Y"))            # '2023'

# Display dates
today = date.today()
print(f"Today: {format_date(today, '%A, %B %d, %Y')}")
```

### parse_date

Parse a string to a date object.

```python
from examples.telemetry_utils_v5.date_utils import parse_date

# Default format (YYYY-MM-DD)
dt = parse_date("2023-12-25")
print(dt)  # date(2023, 12, 25)

# Custom formats
dt = parse_date("12/25/2023", "%m/%d/%Y")
print(dt)  # date(2023, 12, 25)

dt = parse_date("25-Dec-2023", "%d-%b-%Y")
print(dt)  # date(2023, 12, 25)

# Parse user input
date_str = input("Enter date (YYYY-MM-DD): ")
try:
    dt = parse_date(date_str)
    print(f"Parsed: {dt}")
except ValueError:
    print("Invalid date format")
```

### add_days

Add a specified number of days to a date.

```python
from datetime import date
from examples.telemetry_utils_v5.date_utils import add_days

# Add days
dt = date(2023, 12, 25)
future = add_days(dt, 7)
print(future)  # date(2024, 1, 1)

# Subtract days
past = add_days(dt, -5)
print(past)  # date(2023, 12, 20)

# No change
same = add_days(dt, 0)
print(same)  # date(2023, 12, 25)

# Calculate due date
today = date.today()
due_date = add_days(today, 30)
print(f"Due in 30 days: {due_date}")
```

### diff_days

Calculate the difference in days between two dates.

```python
from datetime import date
from examples.telemetry_utils_v5.date_utils import diff_days

# Basic difference
dt1 = date(2023, 12, 25)
dt2 = date(2024, 1, 1)
print(diff_days(dt1, dt2))  # 7

# Negative difference
print(diff_days(dt2, dt1))  # -7

# Same date
print(diff_days(dt1, dt1))  # 0

# Calculate age in days
birth_date = date(1990, 1, 1)
today = date.today()
age_days = diff_days(birth_date, today)
print(f"Age in days: {age_days}")
```

### is_weekend

Check if a date falls on a weekend.

```python
from datetime import date
from examples.telemetry_utils_v5.date_utils import is_weekend

# Saturday
dt = date(2023, 12, 23)
print(is_weekend(dt))  # True

# Sunday
dt = date(2023, 12, 24)
print(is_weekend(dt))  # True

# Monday
dt = date(2023, 12, 25)
print(is_weekend(dt))  # False

# Check if today is weekend
today = date.today()
if is_weekend(today):
    print("It's the weekend!")
else:
    print("It's a weekday")
```

---

## Path Utilities

Module: `path_utils.py`

### join_paths

Join multiple path components into a single path.

```python
from examples.telemetry_utils_v5.path_utils import join_paths

# Basic joining
path = join_paths('home', 'user', 'documents')
print(path)  # PosixPath('home/user/documents')

# Absolute path
path = join_paths('/var', 'log', 'app.log')
print(path)  # PosixPath('/var/log/app.log')

# Single component
path = join_paths('data')
print(path)  # PosixPath('data')

# Build file paths
base_dir = 'project'
data_dir = join_paths(base_dir, 'data')
file_path = join_paths(data_dir, 'output.txt')
print(file_path)  # PosixPath('project/data/output.txt')
```

### get_extension

Get the file extension from a path.

```python
from examples.telemetry_utils_v5.path_utils import get_extension

# Basic usage
print(get_extension('document.txt'))      # '.txt'
print(get_extension('archive.tar.gz'))    # '.gz'
print(get_extension('/path/to/file.py'))  # '.py'

# No extension
print(get_extension('README'))            # ''
print(get_extension('.hidden'))           # ''

# Check file type
filename = 'data.json'
if get_extension(filename) == '.json':
    print("JSON file detected")
```

### change_extension

Change the file extension of a path.

```python
from examples.telemetry_utils_v5.path_utils import change_extension

# Basic usage
path = change_extension('document.txt', '.md')
print(path)  # PosixPath('document.md')

# Without leading dot
path = change_extension('file.old', 'new')
print(path)  # PosixPath('file.new')

# Add extension
path = change_extension('README', '.txt')
print(path)  # PosixPath('README.txt')

# Convert file format
input_file = 'data.json'
output_file = change_extension(input_file, '.xml')
print(f"Converting {input_file} to {output_file}")
```

### is_subpath

Check if one path is a subpath of another.

```python
from examples.telemetry_utils_v5.path_utils import is_subpath

# Basic usage
print(is_subpath('/home/user/docs/file.txt', '/home/user'))  # True
print(is_subpath('/home/user/file.txt', '/home/other'))      # False

# Relative paths
print(is_subpath('data/subfolder/file.txt', 'data'))  # True

# Same path
print(is_subpath('/var/log', '/var/log'))  # True

# Security check
base_dir = '/var/www/uploads'
user_path = '/var/www/uploads/user123/file.txt'
if is_subpath(user_path, base_dir):
    print("Path is within allowed directory")
else:
    print("Access denied: path outside allowed directory")
```

---

## File I/O Utilities

Module: `io_utils.py`

### read_file

Read entire file content as a string.

```python
from examples.telemetry_utils_v5.io_utils import read_file

# Basic usage
content = read_file('config.txt')
print(content)

# With Path object
from pathlib import Path
content = read_file(Path('data/input.txt'))

# Custom encoding
content = read_file('file.txt', encoding='latin-1')

# Error handling
try:
    content = read_file('missing.txt')
except FileNotFoundError:
    print("File not found")
except IOError as e:
    print(f"Error reading file: {e}")
```

### write_file

Write string content to a file.

```python
from examples.telemetry_utils_v5.io_utils import write_file

# Basic usage
write_file('output.txt', 'Hello, World!')

# Append to file
write_file('log.txt', 'New entry\n', append=True)

# Create directories
write_file('data/output/result.txt', 'Data', create_dirs=True)

# Custom encoding
write_file('file.txt', 'Héllo', encoding='utf-8')

# Save generated content
report = "Report\n" + "=" * 50 + "\n" + "Content here"
write_file('report.txt', report)
```

### read_lines

Read file content as a list of lines.

```python
from examples.telemetry_utils_v5.io_utils import read_lines

# Basic usage
lines = read_lines('data.txt')
for line in lines:
    print(line)

# Preserve newlines
lines = read_lines('file.txt', strip_newlines=False)

# Skip empty lines
lines = read_lines('file.txt', skip_empty=True)

# Process line by line
lines = read_lines('config.txt')
for i, line in enumerate(lines, 1):
    print(f"Line {i}: {line}")
```

### write_lines

Write a list of lines to a file.

```python
from examples.telemetry_utils_v5.io_utils import write_lines

# Basic usage
lines = ['Line 1', 'Line 2', 'Line 3']
write_lines('output.txt', lines)

# Without newlines
write_lines('file.txt', ['A', 'B', 'C'], add_newlines=False)

# Append lines
write_lines('log.txt', ['Entry 1', 'Entry 2'], append=True)

# Create directories
write_lines('logs/app.log', ['Log entry'], create_dirs=True)

# Save list data
data = ['Item 1', 'Item 2', 'Item 3']
write_lines('items.txt', data)
```

---

## JSON Utilities

Module: `json_utils.py`

### load_json

Load JSON data from a file.

```python
from examples.telemetry_utils_v5.json_utils import load_json

# Basic usage
data = load_json('config.json')
print(data)

# With Path object
from pathlib import Path
data = load_json(Path('data.json'))

# Custom encoding
data = load_json('file.json', encoding='utf-8')

# Error handling
try:
    data = load_json('config.json')
    print(f"Loaded: {data}")
except FileNotFoundError:
    print("File not found")
except json.JSONDecodeError:
    print("Invalid JSON")
```

### save_json

Save data to a JSON file.

```python
from examples.telemetry_utils_v5.json_utils import save_json

# Basic usage
data = {'name': 'Alice', 'age': 30}
save_json('output.json', data)

# Compact format
save_json('data.json', data, indent=None)

# Sorted keys
save_json('sorted.json', data, sort_keys=True)

# Create directories
save_json('output/data.json', data, create_dirs=True)

# Save configuration
config = {
    'database': {'host': 'localhost', 'port': 5432},
    'logging': {'level': 'INFO'}
}
save_json('config.json', config, indent=2)
```

### pretty_print

Format JSON data as a pretty-printed string.

```python
from examples.telemetry_utils_v5.json_utils import pretty_print

# Basic usage
data = {'name': 'Bob', 'age': 35}
formatted = pretty_print(data)
print(formatted)

# Custom indentation
formatted = pretty_print(data, indent=4)

# Sorted keys
data = {'z': 1, 'a': 2, 'm': 3}
formatted = pretty_print(data, sort_keys=True)
print(formatted)

# Display API response
api_response = {'status': 'success', 'data': {'id': 123}}
print("Response:")
print(pretty_print(api_response))
```

### validate_json

Validate if a string is valid JSON.

```python
from examples.telemetry_utils_v5.json_utils import validate_json

# Valid JSON
print(validate_json('{"name": "Charlie"}'))  # True
print(validate_json('[1, 2, 3]'))            # True
print(validate_json('"string"'))             # True
print(validate_json('123'))                  # True
print(validate_json('true'))                 # True

# Invalid JSON
print(validate_json('{invalid}'))            # False
print(validate_json(''))                     # False
print(validate_json('undefined'))            # False

# Validate user input
json_str = input("Enter JSON: ")
if validate_json(json_str):
    print("Valid JSON")
else:
    print("Invalid JSON")
```

---

## CSV Utilities

Module: `csv_utils.py`

### read_csv

Read CSV file and return rows as list of lists.

```python
from examples.telemetry_utils_v5.csv_utils import read_csv

# Basic usage
rows = read_csv('data.csv')
for row in rows:
    print(row)

# Skip header
rows = read_csv('data.csv', skip_header=True)

# Custom delimiter
rows = read_csv('data.tsv', delimiter='\t')

# Custom encoding
rows = read_csv('file.csv', encoding='latin-1')

# Process CSV data
rows = read_csv('sales.csv', skip_header=True)
for row in rows:
    product, quantity, price = row
    print(f"{product}: {quantity} @ ${price}")
```

### write_csv

Write rows to a CSV file.

```python
from examples.telemetry_utils_v5.csv_utils import write_csv

# Basic usage
rows = [['name', 'age'], ['Alice', 30], ['Bob', 25]]
write_csv('output.csv', rows)

# Custom delimiter
write_csv('data.tsv', rows, delimiter='\t')

# Create directories
write_csv('output/data.csv', rows, create_dirs=True)

# Generate CSV report
header = ['Product', 'Quantity', 'Price']
data = [
    ['Widget', '10', '9.99'],
    ['Gadget', '5', '19.99']
]
rows = [header] + data
write_csv('report.csv', rows)
```

### to_dicts

Convert CSV rows to list of dictionaries.

```python
from examples.telemetry_utils_v5.csv_utils import to_dicts

# With header in first row
rows = [['name', 'age'], ['Alice', '30'], ['Bob', '25']]
dicts = to_dicts(rows)
print(dicts)
# [{'name': 'Alice', 'age': '30'}, {'name': 'Bob', 'age': '25'}]

# With custom headers
rows = [['Alice', '30'], ['Bob', '25']]
dicts = to_dicts(rows, headers=['name', 'age'])
print(dicts)

# Process as dictionaries
for record in dicts:
    print(f"{record['name']} is {record['age']} years old")
```

### from_dicts

Convert list of dictionaries to CSV rows.

```python
from examples.telemetry_utils_v5.csv_utils import from_dicts

# Basic usage
dicts = [{'name': 'Alice', 'age': 30}, {'name': 'Bob', 'age': 25}]
rows = from_dicts(dicts)
print(rows)
# [['name', 'age'], ['Alice', '30'], ['Bob', '25']]

# Without header
rows = from_dicts(dicts, include_header=False)
print(rows)
# [['Alice', '30'], ['Bob', '25']]

# Custom column order
rows = from_dicts(dicts, headers=['age', 'name'])
print(rows)
# [['age', 'name'], ['30', 'Alice'], ['25', 'Bob']]

# Convert and save
from examples.telemetry_utils_v5.csv_utils import write_csv
data = [{'id': 1, 'name': 'Item1'}, {'id': 2, 'name': 'Item2'}]
rows = from_dicts(data)
write_csv('output.csv', rows)
```

---

## INI Utilities

Module: `ini_utils.py`

### read_ini

Read an INI file and return a ConfigParser object.

```python
from examples.telemetry_utils_v5.ini_utils import read_ini

# Basic usage
config = read_ini('config.ini')

# Access values
host = config.get('database', 'host')
port = config.getint('database', 'port')

# List sections
sections = config.sections()
print(f"Sections: {sections}")

# Check if section/option exists
if config.has_section('database'):
    if config.has_option('database', 'host'):
        print(f"Host: {config.get('database', 'host')}")
```

### write_ini

Write a ConfigParser object to an INI file.

```python
import configparser
from examples.telemetry_utils_v5.ini_utils import write_ini

# Create configuration
config = configparser.ConfigParser()
config['database'] = {
    'host': 'localhost',
    'port': '5432',
    'name': 'mydb'
}
config['logging'] = {
    'level': 'INFO',
    'file': 'app.log'
}

# Write to file
write_ini('config.ini', config)

# Create directories
write_ini('configs/app.ini', config, create_dirs=True)
```

### get_value

Get a value from an INI file.

```python
from examples.telemetry_utils_v5.ini_utils import get_value

# Basic usage
host = get_value('config.ini', 'database', 'host')
print(f"Host: {host}")

# With default value
user = get_value('config.ini', 'database', 'user', default='admin')
print(f"User: {user}")

# Quick config access
timeout = get_value('settings.ini', 'app', 'timeout', default='30')
timeout = int(timeout)
```

### set_value

Set a value in an INI file.

```python
from examples.telemetry_utils_v5.ini_utils import set_value

# Basic usage
set_value('config.ini', 'database', 'host', 'localhost')
set_value('config.ini', 'database', 'port', 5432)

# Create new file
set_value('new.ini', 'app', 'name', 'MyApp')

# Create directories
set_value('configs/app.ini', 'settings', 'debug', 'true', create_dirs=True)

# Update configuration
set_value('config.ini', 'logging', 'level', 'DEBUG')
```

---

## Logging Utilities

Module: `logging_utils.py`

### setup_logger

Configure and return a logger with specified settings.

```python
from examples.telemetry_utils_v5.logging_utils import setup_logger
import logging

# Basic usage
logger = setup_logger('my_app')
logger.info('Application started')
logger.warning('This is a warning')
logger.error('An error occurred')

# Custom log level
logger = setup_logger('debug_logger', level=logging.DEBUG)
logger.debug('Debug message')

# String level
logger = setup_logger('app', level='WARNING')

# Custom format
logger = setup_logger(
    'custom',
    format_string='%(levelname)s: %(message)s'
)

# Application logging
logger = setup_logger('myapp', level=logging.INFO)
logger.info('Starting application')
try:
    # Application code
    pass
except Exception as e:
    logger.error(f'Error: {e}')
```

### log_to_file

Configure file-based logging for a logger.

```python
from examples.telemetry_utils_v5.logging_utils import setup_logger, log_to_file
import logging

# Setup logger and add file handler
logger = setup_logger('my_app')
log_to_file(logger, 'logs/app.log')

logger.info('This goes to console and file')

# Create directories
log_to_file(logger, 'logs/debug.log', create_dirs=True)

# Different level for file
log_to_file(logger, 'logs/errors.log', level=logging.ERROR)

# Overwrite mode
log_to_file(logger, 'logs/app.log', mode='w')

# Application with file logging
logger = setup_logger('app', level=logging.INFO)
log_to_file(logger, 'logs/app.log', create_dirs=True)

logger.info('Application started')
logger.error('Error occurred')
```

### get_logger

Get or create a logger instance by name.

```python
from examples.telemetry_utils_v5.logging_utils import get_logger
import logging

# Get logger (creates if new)
logger = get_logger('my_app')
logger.info('Hello, World!')

# Get same logger again
logger2 = get_logger('my_app')
logger2.info('Same logger')  # Uses same logger instance

# Custom level
logger = get_logger('debug', level=logging.DEBUG)

# Without auto-setup
logger = get_logger('raw', setup_if_new=False)

# Module-level logging
# In module1.py
logger = get_logger('app.module1')
logger.info('Module 1 message')

# In module2.py
logger = get_logger('app.module2')
logger.info('Module 2 message')
```

---

## Retry Utilities

Module: `retry_utils.py`

### retry_on_exception

Decorator to retry a function on exception with exponential backoff.

```python
from examples.telemetry_utils_v5.retry_utils import retry_on_exception
import random

# Basic usage
@retry_on_exception(max_attempts=3, base_delay=0.1)
def flaky_function():
    if random.random() < 0.7:
        raise ValueError("Random failure")
    return "success"

result = flaky_function()
print(result)

# Specific exceptions
@retry_on_exception(max_attempts=3, exceptions=(IOError, OSError))
def read_file(path):
    with open(path, 'r') as f:
        return f.read()

# With retry callback
def log_retry(exc, attempt, delay):
    print(f"Retry {attempt} after {delay:.2f}s due to {exc}")

@retry_on_exception(max_attempts=3, on_retry=log_retry)
def api_call():
    # Simulated API call
    if random.random() < 0.5:
        raise ConnectionError("API unavailable")
    return {"status": "ok"}

# Network request with retry
@retry_on_exception(
    max_attempts=5,
    base_delay=1.0,
    max_delay=30.0,
    exceptions=(ConnectionError, TimeoutError)
)
def fetch_data(url):
    # Fetch data from URL
    pass
```

### exponential_backoff

Calculate exponential backoff delay.

```python
from examples.telemetry_utils_v5.retry_utils import exponential_backoff

# Basic usage
for attempt in range(5):
    delay = exponential_backoff(attempt, base_delay=1.0, jitter=False)
    print(f"Attempt {attempt}: delay {delay}s")
# Output:
# Attempt 0: delay 1.0s
# Attempt 1: delay 2.0s
# Attempt 2: delay 4.0s
# Attempt 3: delay 8.0s
# Attempt 4: delay 16.0s

# With max delay
delay = exponential_backoff(10, base_delay=1.0, max_delay=60.0, jitter=False)
print(delay)  # 60.0 (capped)

# With jitter
delay = exponential_backoff(2, base_delay=1.0, jitter=True)
print(f"Delay with jitter: {delay:.2f}s")  # Random between 2.0 and 6.0

# Custom exponential base
delay = exponential_backoff(3, base_delay=0.5, exponential_base=3.0, jitter=False)
print(delay)  # 13.5 (0.5 * 3^3)
```

### RetryConfig

Configuration class for retry behavior.

```python
from examples.telemetry_utils_v5.retry_utils import RetryConfig, retry_with_config

# Create configuration
config = RetryConfig(
    max_attempts=5,
    base_delay=1.0,
    max_delay=60.0,
    exponential_base=2.0,
    jitter=True,
    exceptions=(ConnectionError, TimeoutError)
)

# Use with decorator
@retry_with_config(config)
def network_request():
    # Make network request
    pass

# Reusable configurations
aggressive_retry = RetryConfig(max_attempts=10, base_delay=0.5)
conservative_retry = RetryConfig(max_attempts=3, base_delay=2.0)

@retry_with_config(aggressive_retry)
def critical_operation():
    pass

@retry_with_config(conservative_retry)
def non_critical_operation():
    pass
```

---

## Text Wrapping Utilities

Module: `textwrap_utils.py`

### wrap_text

Wrap text to a specified width.

```python
from examples.telemetry_utils_v5.textwrap_utils import wrap_text

# Basic usage
text = "This is a long line of text that needs to be wrapped to fit within a certain width"
lines = wrap_text(text, width=40)
for line in lines:
    print(line)

# Custom width
lines = wrap_text(text, width=20)
print(lines)

# Don't break long words
text = "Supercalifragilisticexpialidocious is a long word"
lines = wrap_text(text, width=20, break_long_words=False)
print(lines)

# Format paragraph
paragraph = "Lorem ipsum dolor sit amet, consectetur adipiscing elit."
lines = wrap_text(paragraph, width=30)
for line in lines:
    print(line)
```

### indent_text

Add indentation to text lines.

```python
from examples.telemetry_utils_v5.textwrap_utils import indent_text

# Basic usage
text = "Line 1\nLine 2\nLine 3"
indented = indent_text(text)
print(indented)
# Output:
#     Line 1
#     Line 2
#     Line 3

# Custom prefix
indented = indent_text(text, prefix=">> ")
print(indented)
# Output:
# >> Line 1
# >> Line 2
# >> Line 3

# Conditional indentation
def should_indent(line):
    return not line.startswith('#')

text = "Normal line\n# Comment\nAnother line"
indented = indent_text(text, prefix="  ", predicate=should_indent)
print(indented)

# Format code block
code = "def hello():\n    print('Hello')\n    return True"
indented = indent_text(code, prefix="    ")
print(indented)
```

### dedent_text

Remove common leading whitespace from text.

```python
from examples.telemetry_utils_v5.textwrap_utils import dedent_text

# Basic usage
text = "    Line 1\n    Line 2\n    Line 3"
dedented = dedent_text(text)
print(dedented)
# Output:
# Line 1
# Line 2
# Line 3

# Preserve relative indentation
text = "  Hello\n    World\n  !"
dedented = dedent_text(text)
print(dedented)
# Output:
# Hello
#   World
# !

# Clean up docstring
def example():
    """
    This is a docstring
    with indentation
    """
    pass

doc = example.__doc__
cleaned = dedent_text(doc)
print(cleaned)
```

### fill_text

Wrap and join text into a single string.

```python
from examples.telemetry_utils_v5.textwrap_utils import fill_text

# Basic usage
text = "This is a long line of text that needs to be wrapped"
filled = fill_text(text, width=30)
print(filled)

# With initial indent
filled = fill_text(text, width=40, initial_indent="* ")
print(filled)
# Output:
# * This is a long line of text that
# needs to be wrapped

# With subsequent indent
filled = fill_text(
    text,
    width=40,
    initial_indent="> ",
    subsequent_indent="  "
)
print(filled)
# Output:
# > This is a long line of text that
#   needs to be wrapped

# Format bullet points
items = [
    "First item with a long description that needs wrapping",
    "Second item also with a long description"
]
for item in items:
    formatted = fill_text(
        item,
        width=50,
        initial_indent="• ",
        subsequent_indent="  "
    )
    print(formatted)
    print()
```

---

## Complete Example: Data Processing Pipeline

Here's a complete example combining multiple utilities:

```python
from examples.telemetry_utils_v5.csv_utils import read_csv, to_dicts, from_dicts, write_csv
from examples.telemetry_utils_v5.dict_utils import filter_keys, get_nested
from examples.telemetry_utils_v5.validation_utils import is_email, validate_range
from examples.telemetry_utils_v5.json_utils import save_json
from examples.telemetry_utils_v5.logging_utils import setup_logger, log_to_file
from examples.telemetry_utils_v5.date_utils import parse_date, format_date

# Setup logging
logger = setup_logger('data_pipeline', level='INFO')
log_to_file(logger, 'logs/pipeline.log', create_dirs=True)

logger.info('Starting data processing pipeline')

# Read CSV data
rows = read_csv('input.csv')
data = to_dicts(rows)
logger.info(f'Loaded {len(data)} records')

# Validate and filter data
valid_records = []
for record in data:
    # Validate email
    if not is_email(record.get('email', '')):
        logger.warning(f"Invalid email: {record.get('email')}")
        continue

    # Validate age range
    age = int(record.get('age', 0))
    if not validate_range(age, min_value=18, max_value=120):
        logger.warning(f"Invalid age: {age}")
        continue

    valid_records.append(record)

logger.info(f'Validated {len(valid_records)} records')

# Filter sensitive fields
safe_records = [filter_keys(r, ['password'], exclude=True) for r in valid_records]

# Save as JSON
save_json('output/data.json', safe_records, indent=2, create_dirs=True)
logger.info('Saved JSON output')

# Save as CSV
output_rows = from_dicts(safe_records)
write_csv('output/data.csv', output_rows, create_dirs=True)
logger.info('Saved CSV output')

logger.info('Pipeline completed successfully')
```

---

## Tips and Best Practices

### Error Handling

Always wrap file operations in try-except blocks:

```python
from examples.telemetry_utils_v5.io_utils import read_file

try:
    content = read_file('config.txt')
    # Process content
except FileNotFoundError:
    print("Configuration file not found")
except IOError as e:
    print(f"Error reading file: {e}")
```

### Type Hints

All functions include type hints for better IDE support:

```python
from examples.telemetry_utils_v5.string_utils import capitalize_words

# IDE will show: capitalize_words(text: str) -> str
result: str = capitalize_words("hello world")
```

### Chaining Operations

Combine utilities for complex operations:

```python
from examples.telemetry_utils_v5.list_utils import chunk, flatten, unique

data = [1, 2, 2, 3, [4, 5], [6, [7, 8]]]
flat = flatten(data)        # [1, 2, 2, 3, 4, 5, 6, 7, 8]
uniq = unique(flat)         # [1, 2, 3, 4, 5, 6, 7, 8]
chunks = chunk(uniq, 3)     # [[1, 2, 3], [4, 5, 6], [7, 8]]
```

### Path Handling

Use Path objects for cross-platform compatibility:

```python
from pathlib import Path
from examples.telemetry_utils_v5.io_utils import read_file

base_dir = Path('data')
file_path = base_dir / 'input.txt'
content = read_file(file_path)
```

---

For more information, see the [README.md](README.md) file.
