#!/usr/bin/env python3
"""Command-line interface demo for telemetry_utils_v5 package.

This module provides a CLI demo showcasing the various utility functions
available in the telemetry_utils_v5 package.
"""

import argparse
import sys
from typing import List, Optional

# Import utility modules
from examples.telemetry_utils_v5.string_utils import (
    capitalize_words,
    reverse_string,
    snake_to_camel,
    truncate,
)
from examples.telemetry_utils_v5.number_utils import (
    is_even,
    is_prime,
    gcd,
    lcm,
)
from examples.telemetry_utils_v5.list_utils import (
    chunk,
    flatten,
    unique,
    rotate,
)
from examples.telemetry_utils_v5.dict_utils import (
    merge,
    get_nested,
    filter_keys,
    invert,
)
from examples.telemetry_utils_v5.validation_utils import (
    is_email,
    is_url,
    is_int,
    is_float,
    validate_range,
)


def demo_string_utils() -> None:
    """Demonstrate string utility functions."""
    print("\n=== String Utils Demo ===")

    text = "hello world from python"
    print(f"Original: {text}")
    print(f"Capitalized: {capitalize_words(text)}")
    print(f"Reversed: {reverse_string(text)}")

    snake = "my_variable_name"
    print(f"\nSnake case: {snake}")
    print(f"Camel case: {snake_to_camel(snake)}")
    print(f"Pascal case: {snake_to_camel(snake, upper_first=True)}")

    long_text = "This is a very long string that needs to be truncated"
    print(f"\nLong text: {long_text}")
    print(f"Truncated (20): {truncate(long_text, 20)}")


def demo_number_utils() -> None:
    """Demonstrate number utility functions."""
    print("\n=== Number Utils Demo ===")

    numbers = [4, 7, 17, 100]
    print("\nEven/Odd check:")
    for n in numbers:
        print(f"  {n} is {'even' if is_even(n) else 'odd'}")

    print("\nPrime check:")
    for n in numbers:
        print(f"  {n} is {'prime' if is_prime(n) else 'not prime'}")

    print("\nGCD and LCM:")
    pairs = [(48, 18), (100, 50), (17, 19)]
    for a, b in pairs:
        print(f"  gcd({a}, {b}) = {gcd(a, b)}, lcm({a}, {b}) = {lcm(a, b)}")


def demo_list_utils() -> None:
    """Demonstrate list utility functions."""
    print("\n=== List Utils Demo ===")

    lst = [1, 2, 3, 4, 5, 6, 7, 8, 9]
    print(f"\nOriginal list: {lst}")
    print(f"Chunked (size 3): {chunk(lst, 3)}")
    print(f"Rotated right by 2: {rotate(lst, 2)}")
    print(f"Rotated left by 2: {rotate(lst, -2)}")

    nested = [1, [2, 3], [4, [5, 6]], 7]
    print(f"\nNested list: {nested}")
    print(f"Flattened: {flatten(nested)}")

    duplicates = [1, 2, 2, 3, 1, 4, 3, 5]
    print(f"\nWith duplicates: {duplicates}")
    print(f"Unique: {unique(duplicates)}")


def demo_dict_utils() -> None:
    """Demonstrate dictionary utility functions."""
    print("\n=== Dict Utils Demo ===")

    dict1 = {"a": 1, "b": {"x": 10}}
    dict2 = {"b": {"y": 20}, "c": 3}
    print(f"\nDict 1: {dict1}")
    print(f"Dict 2: {dict2}")
    print(f"Merged (deep): {merge(dict1, dict2, deep=True)}")
    print(f"Merged (shallow): {merge(dict1, dict2, deep=False)}")

    nested_dict = {"user": {"profile": {"name": "John", "age": 30}}}
    print(f"\nNested dict: {nested_dict}")
    print(f"Get 'user.profile.name': {get_nested(nested_dict, 'user.profile.name')}")
    print(
        f"Get 'user.profile.email' (default): {get_nested(nested_dict, 'user.profile.email', default='N/A')}"
    )

    data = {"a": 1, "b": 2, "c": 3, "d": 4}
    print(f"\nOriginal: {data}")
    print(f"Filter keys ['a', 'c']: {filter_keys(data, ['a', 'c'])}")
    print(f"Exclude keys ['b', 'd']: {filter_keys(data, ['b', 'd'], exclude=True)}")

    simple = {"x": 1, "y": 2, "z": 3}
    print(f"\nOriginal: {simple}")
    print(f"Inverted: {invert(simple)}")


def demo_validation_utils() -> None:
    """Demonstrate validation utility functions."""
    print("\n=== Validation Utils Demo ===")

    emails = ["user@example.com", "invalid.email", "test@domain.co.uk", "@nodomain.com"]
    print("\nEmail validation:")
    for email in emails:
        print(f"  '{email}': {'valid' if is_email(email) else 'invalid'}")

    urls = ["https://www.example.com", "http://test.com/path", "www.example.com", "not a url"]
    print("\nURL validation:")
    for url in urls:
        print(f"  '{url}': {'valid' if is_url(url) else 'invalid'}")

    values = ["123", "-456", "12.34", "abc", "1e5"]
    print("\nInteger validation:")
    for val in values:
        print(f"  '{val}': {'is int' if is_int(val) else 'not int'}")

    print("\nFloat validation:")
    for val in values:
        print(f"  '{val}': {'is float' if is_float(val) else 'not float'}")

    print("\nRange validation (0-10, inclusive):")
    test_nums = [-5, 0, 5, 10, 15]
    for num in test_nums:
        print(f"  {num}: {'in range' if validate_range(num, 0, 10) else 'out of range'}")


def run_all_demos() -> None:
    """Run all demonstration functions."""
    print("\n" + "=" * 60)
    print("Telemetry Utils v5 - Complete Demo")
    print("=" * 60)

    demo_string_utils()
    demo_number_utils()
    demo_list_utils()
    demo_dict_utils()
    demo_validation_utils()

    print("\n" + "=" * 60)
    print("Demo complete!")
    print("=" * 60 + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the CLI.

    Args:
        argv: Command-line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, non-zero for error)
    """
    parser = argparse.ArgumentParser(
        description="Telemetry Utils v5 - CLI Demo",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all              Run all demos
  %(prog)s --string           Run string utils demo
  %(prog)s --number           Run number utils demo
  %(prog)s --list             Run list utils demo
  %(prog)s --dict             Run dict utils demo
  %(prog)s --validation       Run validation utils demo
  %(prog)s --string --number  Run multiple specific demos
        """,
    )

    parser.add_argument("--all", action="store_true", help="Run all demonstrations")
    parser.add_argument(
        "--string", action="store_true", help="Demonstrate string utility functions"
    )
    parser.add_argument(
        "--number", action="store_true", help="Demonstrate number utility functions"
    )
    parser.add_argument("--list", action="store_true", help="Demonstrate list utility functions")
    parser.add_argument(
        "--dict", action="store_true", help="Demonstrate dictionary utility functions"
    )
    parser.add_argument(
        "--validation", action="store_true", help="Demonstrate validation utility functions"
    )
    parser.add_argument("--version", action="version", version="%(prog)s 5.0.0")

    args = parser.parse_args(argv)

    # If no specific demo is selected, show help
    if not any([args.all, args.string, args.number, args.list, args.dict, args.validation]):
        parser.print_help()
        return 0

    try:
        # Run all demos if --all is specified
        if args.all:
            run_all_demos()
        else:
            # Run specific demos based on flags
            if args.string:
                demo_string_utils()
            if args.number:
                demo_number_utils()
            if args.list:
                demo_list_utils()
            if args.dict:
                demo_dict_utils()
            if args.validation:
                demo_validation_utils()

        return 0

    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
