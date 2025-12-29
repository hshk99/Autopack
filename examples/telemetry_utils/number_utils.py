"""Number utility functions for mathematical operations.

This module provides common number utilities including even/odd checking,
prime number detection, and factorial calculation.
"""

from typing import Union


def is_even(n: int) -> bool:
    """Check if a number is even.
    
    Args:
        n: The integer to check
    
    Returns:
        True if the number is even, False otherwise
    
    Examples:
        >>> is_even(4)
        True
        >>> is_even(7)
        False
        >>> is_even(0)
        True
        >>> is_even(-2)
        True
    """
    return n % 2 == 0


def is_prime(n: int) -> bool:
    """Check if a number is prime.
    
    A prime number is a natural number greater than 1 that has no positive
    divisors other than 1 and itself.
    
    Args:
        n: The integer to check
    
    Returns:
        True if the number is prime, False otherwise
    
    Examples:
        >>> is_prime(2)
        True
        >>> is_prime(17)
        True
        >>> is_prime(4)
        False
        >>> is_prime(1)
        False
        >>> is_prime(0)
        False
        >>> is_prime(-5)
        False
    """
    if n < 2:
        return False
    
    if n == 2:
        return True
    
    if n % 2 == 0:
        return False
    
    # Check odd divisors up to sqrt(n)
    i = 3
    while i * i <= n:
        if n % i == 0:
            return False
        i += 2
    
    return True


def factorial(n: int) -> int:
    """Calculate the factorial of a non-negative integer.
    
    The factorial of n (denoted n!) is the product of all positive integers
    less than or equal to n. By definition, 0! = 1.
    
    Args:
        n: A non-negative integer
    
    Returns:
        The factorial of n
    
    Raises:
        ValueError: If n is negative
    
    Examples:
        >>> factorial(0)
        1
        >>> factorial(1)
        1
        >>> factorial(5)
        120
        >>> factorial(10)
        3628800
    """
    if n < 0:
        raise ValueError("Factorial is not defined for negative numbers")
    
    if n == 0 or n == 1:
        return 1
    
    result = 1
    for i in range(2, n + 1):
        result *= i
    
    return result


if __name__ == "__main__":
    # Simple demonstration
    print("Number Utilities Demo")
    print("=" * 40)
    
    # Test is_even
    test_numbers = [0, 1, 2, 7, 10, 15, -4, -7]
    print("\nEven Number Check:")
    for num in test_numbers:
        result = is_even(num)
        print(f"  is_even({num}) = {result}")
    
    # Test is_prime
    prime_test = [0, 1, 2, 3, 4, 5, 11, 15, 17, 20, 29]
    print("\nPrime Number Check:")
    for num in prime_test:
        result = is_prime(num)
        print(f"  is_prime({num}) = {result}")
    
    # Test factorial
    factorial_test = [0, 1, 5, 10]
    print("\nFactorial Calculation:")
    for num in factorial_test:
        result = factorial(num)
        print(f"  factorial({num}) = {result}")
