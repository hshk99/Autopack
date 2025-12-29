"""Pytest tests for number_utils module.

This module contains comprehensive tests for all number utility functions
including is_even, is_prime, gcd, and lcm.
"""

import pytest
from examples.telemetry_utils_v5.number_utils import (
    is_even,
    is_prime,
    gcd,
    lcm,
)


class TestIsEven:
    """Tests for is_even function."""
    
    def test_even_positive_number(self):
        """Test that positive even numbers return True."""
        assert is_even(4) is True
        assert is_even(100) is True
    
    def test_odd_positive_number(self):
        """Test that positive odd numbers return False."""
        assert is_even(7) is False
        assert is_even(99) is False
    
    def test_zero(self):
        """Test that zero is considered even."""
        assert is_even(0) is True
    
    def test_negative_even_number(self):
        """Test that negative even numbers return True."""
        assert is_even(-2) is True
        assert is_even(-100) is True
    
    def test_negative_odd_number(self):
        """Test that negative odd numbers return False."""
        assert is_even(-3) is False
        assert is_even(-99) is False


class TestIsPrime:
    """Tests for is_prime function."""
    
    def test_small_primes(self):
        """Test small prime numbers."""
        assert is_prime(2) is True
        assert is_prime(3) is True
        assert is_prime(5) is True
        assert is_prime(7) is True
    
    def test_larger_primes(self):
        """Test larger prime numbers."""
        assert is_prime(17) is True
        assert is_prime(29) is True
        assert is_prime(97) is True
    
    def test_composite_numbers(self):
        """Test composite (non-prime) numbers."""
        assert is_prime(4) is False
        assert is_prime(9) is False
        assert is_prime(100) is False
    
    def test_one_and_below(self):
        """Test that 1 and numbers below 2 are not prime."""
        assert is_prime(1) is False
        assert is_prime(0) is False
        assert is_prime(-5) is False


class TestGcd:
    """Tests for gcd function."""
    
    def test_basic_gcd(self):
        """Test basic GCD calculations."""
        assert gcd(48, 18) == 6
        assert gcd(100, 50) == 50
    
    def test_coprime_numbers(self):
        """Test GCD of coprime numbers (GCD = 1)."""
        assert gcd(17, 19) == 1
        assert gcd(13, 7) == 1
    
    def test_with_zero(self):
        """Test GCD when one number is zero."""
        assert gcd(0, 5) == 5
        assert gcd(10, 0) == 10
    
    def test_negative_numbers(self):
        """Test GCD with negative numbers."""
        assert gcd(-48, 18) == 6
        assert gcd(48, -18) == 6
        assert gcd(-48, -18) == 6
    
    def test_same_numbers(self):
        """Test GCD of identical numbers."""
        assert gcd(42, 42) == 42


class TestLcm:
    """Tests for lcm function."""
    
    def test_basic_lcm(self):
        """Test basic LCM calculations."""
        assert lcm(4, 6) == 12
        assert lcm(21, 6) == 42
    
    def test_coprime_numbers(self):
        """Test LCM of coprime numbers (product of the numbers)."""
        assert lcm(5, 7) == 35
        assert lcm(13, 17) == 221
    
    def test_same_numbers(self):
        """Test LCM of identical numbers."""
        assert lcm(10, 10) == 10
        assert lcm(7, 7) == 7
    
    def test_with_one(self):
        """Test LCM with one as an argument."""
        assert lcm(1, 5) == 5
        assert lcm(10, 1) == 10
    
    def test_with_zero(self):
        """Test LCM when one number is zero."""
        assert lcm(0, 5) == 0
        assert lcm(10, 0) == 0
    
    def test_both_zero_raises_error(self):
        """Test that LCM of (0, 0) raises ValueError."""
        with pytest.raises(ValueError, match="LCM is undefined for both arguments being zero"):
            lcm(0, 0)
    
    def test_negative_numbers(self):
        """Test LCM with negative numbers."""
        assert lcm(-4, 6) == 12
        assert lcm(4, -6) == 12
        assert lcm(-4, -6) == 12
