"""Python-based calculators for data processing and analysis.

This module provides safe calculation functions that:
- Perform mathematical operations on extracted data
- Validate inputs and outputs
- Handle edge cases gracefully
- Support common research metrics
"""

import logging
import math
from typing import List, Dict, Any, Optional, Union

logger = logging.getLogger(__name__)


class Calculator:
    """Safe calculator for research data processing."""

    @staticmethod
    def safe_divide(numerator: float, denominator: float, default: float = 0.0) -> float:
        """Safely divide two numbers.

        Args:
            numerator: Numerator
            denominator: Denominator
            default: Default value if division fails

        Returns:
            Result of division or default
        """
        try:
            if denominator == 0:
                logger.warning("Division by zero, returning default")
                return default
            return numerator / denominator
        except (TypeError, ValueError) as e:
            logger.error(f"Division failed: {e}")
            return default

    @staticmethod
    def percentage(part: float, total: float) -> float:
        """Calculate percentage.

        Args:
            part: Part value
            total: Total value

        Returns:
            Percentage (0-100)
        """
        if total == 0:
            return 0.0
        return (part / total) * 100

    @staticmethod
    def average(values: List[Union[int, float]]) -> float:
        """Calculate average of values.

        Args:
            values: List of numeric values

        Returns:
            Average value
        """
        if not values:
            return 0.0

        try:
            numeric_values = [float(v) for v in values if v is not None]
            if not numeric_values:
                return 0.0
            return sum(numeric_values) / len(numeric_values)
        except (TypeError, ValueError) as e:
            logger.error(f"Average calculation failed: {e}")
            return 0.0

    @staticmethod
    def median(values: List[Union[int, float]]) -> float:
        """Calculate median of values.

        Args:
            values: List of numeric values

        Returns:
            Median value
        """
        if not values:
            return 0.0

        try:
            numeric_values = sorted([float(v) for v in values if v is not None])
            if not numeric_values:
                return 0.0

            n = len(numeric_values)
            if n % 2 == 0:
                return (numeric_values[n // 2 - 1] + numeric_values[n // 2]) / 2
            else:
                return numeric_values[n // 2]
        except (TypeError, ValueError) as e:
            logger.error(f"Median calculation failed: {e}")
            return 0.0

    @staticmethod
    def standard_deviation(values: List[Union[int, float]]) -> float:
        """Calculate standard deviation.

        Args:
            values: List of numeric values

        Returns:
            Standard deviation
        """
        if not values or len(values) < 2:
            return 0.0

        try:
            numeric_values = [float(v) for v in values if v is not None]
            if len(numeric_values) < 2:
                return 0.0

            mean = sum(numeric_values) / len(numeric_values)
            variance = sum((x - mean) ** 2 for x in numeric_values) / len(numeric_values)
            return math.sqrt(variance)
        except (TypeError, ValueError) as e:
            logger.error(f"Standard deviation calculation failed: {e}")
            return 0.0

    @staticmethod
    def growth_rate(old_value: float, new_value: float) -> float:
        """Calculate growth rate percentage.

        Args:
            old_value: Original value
            new_value: New value

        Returns:
            Growth rate as percentage
        """
        if old_value == 0:
            return 0.0 if new_value == 0 else 100.0

        return ((new_value - old_value) / old_value) * 100

    @staticmethod
    def aggregate_metrics(data: List[Dict[str, Any]], metric_key: str) -> Dict[str, float]:
        """Aggregate metrics from list of data dictionaries.

        Args:
            data: List of dictionaries containing metrics
            metric_key: Key to extract metric values

        Returns:
            Dictionary with aggregated statistics (mean, median, min, max, std)
        """
        if not data:
            return {
                "mean": 0.0,
                "median": 0.0,
                "min": 0.0,
                "max": 0.0,
                "std": 0.0,
                "count": 0,
            }

        values = []
        for item in data:
            if isinstance(item, dict) and metric_key in item:
                try:
                    values.append(float(item[metric_key]))
                except (TypeError, ValueError):
                    continue

        if not values:
            return {
                "mean": 0.0,
                "median": 0.0,
                "min": 0.0,
                "max": 0.0,
                "std": 0.0,
                "count": 0,
            }

        calc = Calculator()
        return {
            "mean": calc.average(values),
            "median": calc.median(values),
            "min": min(values),
            "max": max(values),
            "std": calc.standard_deviation(values),
            "count": len(values),
        }

    @staticmethod
    def validate_numeric(value: Any, min_value: Optional[float] = None, max_value: Optional[float] = None) -> bool:
        """Validate numeric value is within bounds.

        Args:
            value: Value to validate
            min_value: Minimum allowed value (optional)
            max_value: Maximum allowed value (optional)

        Returns:
            True if valid, False otherwise
        """
        try:
            num = float(value)

            if min_value is not None and num < min_value:
                logger.warning(f"Value {num} below minimum {min_value}")
                return False

            if max_value is not None and num > max_value:
                logger.warning(f"Value {num} above maximum {max_value}")
                return False

            return True
        except (TypeError, ValueError):
            logger.error(f"Invalid numeric value: {value}")
            return False
