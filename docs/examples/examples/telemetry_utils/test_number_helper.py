"""Comprehensive tests for number_helper module.

This module provides comprehensive test coverage for the number_helper module,
including tests for is_even, is_prime, and factorial functions.
"""

import pytest
from examples.telemetry_utils.number_helper import is_even, is_prime, factorial


class TestIsEven:
    """Test suite for is_even function."""

    def test_even_positive_numbers(self):
        """Test even positive numbers."""
        assert is_even(0) is True
        assert is_even(2) is True
        assert is_even(4) is True
        assert is_even(10) is True
        assert is_even(100) is True
        assert is_even(1000) is True

    def test_odd_positive_numbers(self):
        """Test odd positive numbers."""
        assert is_even(1) is False
        assert is_even(3) is False
        assert is_even(7) is False
        assert is_even(15) is False
        assert is_even(99) is False
        assert is_even(1001) is False

    def test_even_negative_numbers(self):
        """Test even negative numbers."""
        assert is_even(-2) is True
        assert is_even(-4) is True
        assert is_even(-10) is True
        assert is_even(-100) is True

    def test_odd_negative_numbers(self):
        """Test odd negative numbers."""
        assert is_even(-1) is False
        assert is_even(-3) is False
        assert is_even(-7) is False
        assert is_even(-99) is False

    def test_zero(self):
        """Test that zero is even."""
        assert is_even(0) is True

    def test_large_numbers(self):
        """Test with very large numbers."""
        assert is_even(1000000) is True
        assert is_even(1000001) is False
        assert is_even(-1000000) is True
        assert is_even(-1000001) is False


class TestIsPrime:
    """Test suite for is_prime function."""

    def test_small_primes(self):
        """Test small prime numbers."""
        assert is_prime(2) is True
        assert is_prime(3) is True
        assert is_prime(5) is True
        assert is_prime(7) is True
        assert is_prime(11) is True
        assert is_prime(13) is True

    def test_larger_primes(self):
        """Test larger prime numbers."""
        assert is_prime(17) is True
        assert is_prime(19) is True
        assert is_prime(23) is True
        assert is_prime(29) is True
        assert is_prime(31) is True
        assert is_prime(97) is True

    def test_composite_numbers(self):
        """Test composite (non-prime) numbers."""
        assert is_prime(4) is False
        assert is_prime(6) is False
        assert is_prime(8) is False
        assert is_prime(9) is False
        assert is_prime(10) is False
        assert is_prime(15) is False
        assert is_prime(20) is False
        assert is_prime(100) is False

    def test_edge_cases(self):
        """Test edge cases for prime checking."""
        assert is_prime(0) is False
        assert is_prime(1) is False
        assert is_prime(2) is True  # Smallest prime

    def test_negative_numbers(self):
        """Test that negative numbers are not prime."""
        assert is_prime(-1) is False
        assert is_prime(-2) is False
        assert is_prime(-5) is False
        assert is_prime(-7) is False
        assert is_prime(-11) is False

    def test_perfect_squares(self):
        """Test perfect squares (all composite)."""
        assert is_prime(4) is False  # 2^2
        assert is_prime(9) is False  # 3^2
        assert is_prime(16) is False  # 4^2
        assert is_prime(25) is False  # 5^2
        assert is_prime(49) is False  # 7^2
        assert is_prime(121) is False  # 11^2

    def test_large_primes(self):
        """Test larger prime numbers."""
        assert is_prime(101) is True
        assert is_prime(103) is True
        assert is_prime(107) is True
        assert is_prime(109) is True

    def test_large_composites(self):
        """Test larger composite numbers."""
        assert is_prime(100) is False
        assert is_prime(102) is False
        assert is_prime(104) is False
        assert is_prime(105) is False


class TestFactorial:
    """Test suite for factorial function."""

    def test_factorial_zero(self):
        """Test factorial of zero."""
        assert factorial(0) == 1

    def test_factorial_one(self):
        """Test factorial of one."""
        assert factorial(1) == 1

    def test_factorial_small_numbers(self):
        """Test factorial of small numbers."""
        assert factorial(2) == 2
        assert factorial(3) == 6
        assert factorial(4) == 24
        assert factorial(5) == 120
        assert factorial(6) == 720

    def test_factorial_medium_numbers(self):
        """Test factorial of medium numbers."""
        assert factorial(7) == 5040
        assert factorial(8) == 40320
        assert factorial(9) == 362880
        assert factorial(10) == 3628800

    def test_factorial_negative_raises_error(self):
        """Test that factorial of negative number raises ValueError."""
        with pytest.raises(ValueError, match="Factorial is not defined for negative numbers"):
            factorial(-1)

        with pytest.raises(ValueError, match="Factorial is not defined for negative numbers"):
            factorial(-5)

        with pytest.raises(ValueError, match="Factorial is not defined for negative numbers"):
            factorial(-100)

    def test_factorial_larger_numbers(self):
        """Test factorial of larger numbers."""
        assert factorial(11) == 39916800
        assert factorial(12) == 479001600

    def test_factorial_growth(self):
        """Test that factorial grows rapidly."""
        # Each factorial should be n times the previous
        for n in range(2, 10):
            assert factorial(n) == n * factorial(n - 1)

    def test_factorial_type(self):
        """Test that factorial returns an integer."""
        assert isinstance(factorial(0), int)
        assert isinstance(factorial(5), int)
        assert isinstance(factorial(10), int)


class TestIntegration:
    """Integration tests combining multiple functions."""

    def test_even_primes(self):
        """Test that 2 is the only even prime."""
        # 2 is the only even prime
        assert is_even(2) is True
        assert is_prime(2) is True

        # All other even numbers are not prime
        for n in [4, 6, 8, 10, 12, 14, 16, 18, 20]:
            assert is_even(n) is True
            assert is_prime(n) is False

    def test_odd_primes(self):
        """Test that all primes except 2 are odd."""
        odd_primes = [3, 5, 7, 11, 13, 17, 19, 23, 29, 31]
        for p in odd_primes:
            assert is_even(p) is False
            assert is_prime(p) is True

    def test_factorial_of_primes(self):
        """Test factorial of prime numbers."""
        assert factorial(2) == 2
        assert factorial(3) == 6
        assert factorial(5) == 120
        assert factorial(7) == 5040

    def test_factorial_of_even_numbers(self):
        """Test factorial of even numbers."""
        for n in [2, 4, 6, 8, 10]:
            assert is_even(n) is True
            result = factorial(n)
            assert isinstance(result, int)
            assert result > 0

    def test_prime_factorials_divisibility(self):
        """Test that factorial(n) is divisible by all numbers <= n."""
        for n in [5, 6, 7]:
            fact_n = factorial(n)
            for i in range(1, n + 1):
                assert fact_n % i == 0

    def test_combined_properties(self):
        """Test combined properties of numbers."""
        # Test numbers 0-20
        for n in range(21):
            # Check even/odd property
            even = is_even(n)

            # Check prime property
            prime = is_prime(n)

            # If prime and greater than 2, must be odd
            if prime and n > 2:
                assert even is False

            # Calculate factorial if non-negative
            if n >= 0:
                fact = factorial(n)
                assert fact >= 1
                assert isinstance(fact, int)


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_boundary_values(self):
        """Test boundary values for all functions."""
        # is_even boundaries
        assert is_even(0) is True
        assert is_even(-1) is False
        assert is_even(1) is False

        # is_prime boundaries
        assert is_prime(0) is False
        assert is_prime(1) is False
        assert is_prime(2) is True

        # factorial boundaries
        assert factorial(0) == 1
        assert factorial(1) == 1

    def test_consecutive_numbers(self):
        """Test consecutive numbers for pattern consistency."""
        # Consecutive numbers alternate even/odd
        for n in range(-10, 10):
            assert is_even(n) != is_even(n + 1)

    def test_twin_primes(self):
        """Test twin primes (primes that differ by 2)."""
        twin_prime_pairs = [(3, 5), (5, 7), (11, 13), (17, 19), (29, 31)]
        for p1, p2 in twin_prime_pairs:
            assert is_prime(p1) is True
            assert is_prime(p2) is True
            assert p2 - p1 == 2

    def test_factorial_monotonic_growth(self):
        """Test that factorial grows monotonically."""
        # factorial(n+1) > factorial(n) for all n >= 1
        for n in range(1, 10):
            assert factorial(n + 1) > factorial(n)

    def test_special_number_properties(self):
        """Test special number properties."""
        # 1 is neither prime nor composite
        assert is_prime(1) is False

        # 0 is even
        assert is_even(0) is True

        # 0! = 1 by definition
        assert factorial(0) == 1

        # 2 is the only even prime
        assert is_even(2) is True
        assert is_prime(2) is True


class TestPerformance:
    """Test performance with larger inputs."""

    @pytest.mark.slow
    def test_large_prime_check(self):
        """Test prime checking with larger numbers."""
        # Test some known large primes
        assert is_prime(997) is True
        assert is_prime(1009) is True

        # Test some large composites
        assert is_prime(1000) is False
        assert is_prime(1001) is False

    @pytest.mark.slow
    def test_large_factorial(self):
        """Test factorial with larger numbers."""
        # Test that we can compute larger factorials
        result = factorial(20)
        assert result == 2432902008176640000

        # Verify it's a very large number
        assert result > 10**18

    def test_even_check_performance(self):
        """Test that even check is fast for large numbers."""
        # Should be O(1) regardless of size
        large_even = 10**100
        large_odd = 10**100 + 1

        assert is_even(large_even) is True
        assert is_even(large_odd) is False
