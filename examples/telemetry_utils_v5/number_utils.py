"""Number utility functions for mathematical operations.

This module provides common number manipulation utilities including:
- is_even: Check if a number is even
- is_prime: Check if a number is prime
- gcd: Calculate the greatest common divisor of two numbers
- lcm: Calculate the least common multiple of two numbers
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


def gcd(a: int, b: int) -> int:
    """Calculate the greatest common divisor of two numbers.
    
    Uses the Euclidean algorithm to find the largest positive integer that
    divides both numbers without a remainder.
    
    Args:
        a: First integer
        b: Second integer
        
    Returns:
        The greatest common divisor of a and b
        
    Examples:
        >>> gcd(48, 18)
        6
        >>> gcd(100, 50)
        50
        >>> gcd(17, 19)
        1
        >>> gcd(0, 5)
        5
    """
    a = abs(a)
    b = abs(b)
    
    while b != 0:
        a, b = b, a % b
    
    return a


def lcm(a: int, b: int) -> int:
    """Calculate the least common multiple of two numbers.
    
    The least common multiple is the smallest positive integer that is
    divisible by both numbers.
    
    Args:
        a: First integer
        b: Second integer
        
    Returns:
        The least common multiple of a and b
        
    Raises:
        ValueError: If both a and b are zero
        
    Examples:
        >>> lcm(4, 6)
        12
        >>> lcm(21, 6)
        42
        >>> lcm(5, 7)
        35
        >>> lcm(10, 10)
        10
    """
    a = abs(a)
    b = abs(b)
    
    if a == 0 and b == 0:
        raise ValueError("LCM is undefined for both arguments being zero")
    
    if a == 0 or b == 0:
        return 0
    
    return abs(a * b) // gcd(a, b)
