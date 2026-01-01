"""Pytest tests for date_utils module.

This module contains comprehensive tests for all date utility functions
including format_date, parse_date, add_days, diff_days, and is_weekend.
"""

import pytest
from datetime import date, datetime
from examples.telemetry_utils_v5.date_utils import (
    format_date,
    parse_date,
    add_days,
    diff_days,
    is_weekend,
)


class TestFormatDate:
    """Tests for format_date function."""
    
    def test_format_date_default(self):
        """Test formatting with default format string."""
        dt = date(2023, 12, 25)
        assert format_date(dt) == '2023-12-25'
    
    def test_format_date_custom_format(self):
        """Test formatting with custom format string."""
        dt = date(2023, 12, 25)
        assert format_date(dt, "%m/%d/%Y") == '12/25/2023'
    
    def test_format_date_long_format(self):
        """Test formatting with long date format."""
        dt = date(2023, 1, 5)
        assert format_date(dt, "%B %d, %Y") == 'January 05, 2023'
    
    def test_format_date_with_datetime(self):
        """Test formatting with datetime object."""
        dt = datetime(2023, 12, 25, 10, 30, 0)
        assert format_date(dt) == '2023-12-25'
    
    def test_format_date_year_only(self):
        """Test formatting to show year only."""
        dt = date(2023, 6, 15)
        assert format_date(dt, "%Y") == '2023'


class TestParseDate:
    """Tests for parse_date function."""
    
    def test_parse_date_default_format(self):
        """Test parsing with default format string."""
        result = parse_date("2023-12-25")
        assert result == date(2023, 12, 25)
    
    def test_parse_date_custom_format(self):
        """Test parsing with custom format string."""
        result = parse_date("12/25/2023", "%m/%d/%Y")
        assert result == date(2023, 12, 25)
    
    def test_parse_date_single_digit_month(self):
        """Test parsing date with single digit month."""
        result = parse_date("2023-01-15")
        assert result == date(2023, 1, 15)
    
    def test_parse_date_invalid_format_raises_error(self):
        """Test that invalid date format raises ValueError."""
        with pytest.raises(ValueError):
            parse_date("25-12-2023")  # Wrong format for default
    
    def test_parse_date_invalid_date_raises_error(self):
        """Test that invalid date raises ValueError."""
        with pytest.raises(ValueError):
            parse_date("2023-13-01")  # Month 13 doesn't exist


class TestAddDays:
    """Tests for add_days function."""
    
    def test_add_days_positive(self):
        """Test adding positive number of days."""
        dt = date(2023, 12, 25)
        result = add_days(dt, 7)
        assert result == date(2024, 1, 1)
    
    def test_add_days_negative(self):
        """Test subtracting days with negative number."""
        dt = date(2023, 12, 25)
        result = add_days(dt, -5)
        assert result == date(2023, 12, 20)
    
    def test_add_days_zero(self):
        """Test adding zero days returns same date."""
        dt = date(2023, 12, 25)
        result = add_days(dt, 0)
        assert result == date(2023, 12, 25)
    
    def test_add_days_month_boundary(self):
        """Test adding days across month boundary."""
        dt = date(2023, 1, 31)
        result = add_days(dt, 1)
        assert result == date(2023, 2, 1)
    
    def test_add_days_with_datetime(self):
        """Test adding days to datetime object."""
        dt = datetime(2023, 12, 25, 10, 30, 0)
        result = add_days(dt, 7)
        assert result == date(2024, 1, 1)
    
    def test_add_days_leap_year(self):
        """Test adding days in leap year."""
        dt = date(2024, 2, 28)
        result = add_days(dt, 1)
        assert result == date(2024, 2, 29)


class TestDiffDays:
    """Tests for diff_days function."""
    
    def test_diff_days_positive(self):
        """Test difference with later date."""
        dt1 = date(2023, 12, 25)
        dt2 = date(2024, 1, 1)
        assert diff_days(dt1, dt2) == 7
    
    def test_diff_days_negative(self):
        """Test difference with earlier date."""
        dt1 = date(2024, 1, 1)
        dt2 = date(2023, 12, 25)
        assert diff_days(dt1, dt2) == -7
    
    def test_diff_days_same_date(self):
        """Test difference between same dates."""
        dt = date(2023, 12, 25)
        assert diff_days(dt, dt) == 0
    
    def test_diff_days_year_span(self):
        """Test difference spanning a full year."""
        dt1 = date(2023, 1, 1)
        dt2 = date(2023, 12, 31)
        assert diff_days(dt1, dt2) == 364
    
    def test_diff_days_with_datetime(self):
        """Test difference with datetime objects."""
        dt1 = datetime(2023, 12, 25, 10, 30, 0)
        dt2 = datetime(2024, 1, 1, 15, 45, 0)
        assert diff_days(dt1, dt2) == 7


class TestIsWeekend:
    """Tests for is_weekend function."""
    
    def test_is_weekend_saturday(self):
        """Test that Saturday is detected as weekend."""
        dt = date(2023, 12, 23)  # Saturday
        assert is_weekend(dt) is True
    
    def test_is_weekend_sunday(self):
        """Test that Sunday is detected as weekend."""
        dt = date(2023, 12, 24)  # Sunday
        assert is_weekend(dt) is True
    
    def test_is_weekend_monday(self):
        """Test that Monday is not weekend."""
        dt = date(2023, 12, 25)  # Monday
        assert is_weekend(dt) is False
    
    def test_is_weekend_friday(self):
        """Test that Friday is not weekend."""
        dt = date(2023, 12, 22)  # Friday
        assert is_weekend(dt) is False
    
    def test_is_weekend_wednesday(self):
        """Test that Wednesday is not weekend."""
        dt = date(2023, 12, 20)  # Wednesday
        assert is_weekend(dt) is False
    
    def test_is_weekend_with_datetime(self):
        """Test weekend detection with datetime object."""
        dt = datetime(2023, 12, 23, 10, 30, 0)  # Saturday
        assert is_weekend(dt) is True
