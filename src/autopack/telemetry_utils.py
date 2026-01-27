"""Telemetry utility functions for token estimation analysis.

Provides helpers for:
- Sample filtering (success-only, category/complexity filters)
- SMAPE (Symmetric Mean Absolute Percentage Error) calculation
- Ratio statistics (waste ratio, underestimation detection)
- Data validation and cleaning

Used by token estimation calibration and analysis scripts.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


def filter_samples(
    samples: List[Dict[str, Any]],
    success_only: bool = False,
    category: Optional[str] = None,
    complexity: Optional[str] = None,
    min_actual_tokens: int = 50,
    max_actual_tokens: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Filter telemetry samples based on criteria.

    Args:
        samples: List of telemetry sample dictionaries
        success_only: If True, only include samples with success=True
        category: Filter by task category (e.g., 'implementation', 'testing')
        complexity: Filter by complexity level (e.g., 'low', 'medium', 'high')
        min_actual_tokens: Minimum actual output tokens (default: 50, filters error responses)
        max_actual_tokens: Maximum actual output tokens (optional)

    Returns:
        Filtered list of samples
    """
    filtered = []

    for sample in samples:
        # Success filter
        if success_only and not sample.get("success", False):
            continue

        # Category filter
        if category and sample.get("category", "").lower() != category.lower():
            continue

        # Complexity filter
        if complexity and sample.get("complexity", "").lower() != complexity.lower():
            continue

        # Token range filters
        actual = sample.get("actual_output_tokens", 0)
        if actual < min_actual_tokens:
            continue
        if max_actual_tokens and actual > max_actual_tokens:
            continue

        filtered.append(sample)

    return filtered


def calculate_smape(predicted: float, actual: float, epsilon: float = 1.0) -> float:
    """Calculate Symmetric Mean Absolute Percentage Error.

    SMAPE is a percentage error metric that treats over- and under-estimation
    symmetrically. Range: 0% (perfect) to 200% (maximum error).

    Formula: SMAPE = |predicted - actual| / ((|predicted| + |actual|) / 2) * 100

    Args:
        predicted: Predicted value
        actual: Actual value
        epsilon: Small constant to avoid division by zero (default: 1.0)

    Returns:
        SMAPE percentage (0-200)

    Examples:
        >>> calculate_smape(100, 100)  # Perfect prediction
        0.0
        >>> calculate_smape(100, 50)   # 50% underestimation
        66.67
        >>> calculate_smape(50, 100)   # 50% overestimation
        66.67
    """
    if predicted < 0 or actual < 0:
        raise ValueError("SMAPE requires non-negative values")

    numerator = abs(predicted - actual)
    denominator = (abs(predicted) + abs(actual)) / 2.0

    # Avoid division by zero
    if denominator < epsilon:
        denominator = epsilon

    return (numerator / denominator) * 100.0


def calculate_waste_ratio(predicted: float, actual: float, epsilon: float = 1.0) -> float:
    """Calculate waste ratio (predicted / actual).

    Waste ratio measures token budget efficiency:
    - 1.0 = perfect prediction
    - >1.0 = overestimation (wasted budget)
    - <1.0 = underestimation (risk of truncation)

    Args:
        predicted: Predicted value
        actual: Actual value
        epsilon: Small constant to avoid division by zero (default: 1.0)

    Returns:
        Waste ratio (predicted / actual)

    Examples:
        >>> calculate_waste_ratio(100, 100)  # Perfect
        1.0
        >>> calculate_waste_ratio(200, 100)  # 2x waste
        2.0
        >>> calculate_waste_ratio(50, 100)   # Underestimated
        0.5
    """
    if predicted < 0 or actual < 0:
        raise ValueError("Waste ratio requires non-negative values")

    if actual < epsilon:
        actual = epsilon

    return predicted / actual


def detect_underestimation(predicted: float, actual: float, tolerance: float = 1.0) -> bool:
    """Detect if prediction underestimated actual value.

    Args:
        predicted: Predicted value
        actual: Actual value
        tolerance: Tolerance multiplier (default: 1.0 = no tolerance)
                   Use >1.0 to allow some underestimation (e.g., 1.1 = 10% tolerance)

    Returns:
        True if underestimated beyond tolerance

    Examples:
        >>> detect_underestimation(100, 100)  # Perfect
        False
        >>> detect_underestimation(90, 100)   # 10% under
        True
        >>> detect_underestimation(91, 100, tolerance=1.1)  # Within 10% tolerance
        False
    """
    if tolerance < 1.0:
        raise ValueError("Tolerance must be >= 1.0")

    return actual > (predicted * tolerance)


def calculate_statistics(samples: List[Dict[str, Any]], metric: str = "smape") -> Dict[str, float]:
    """Calculate summary statistics for a metric across samples.

    Args:
        samples: List of telemetry samples
        metric: Metric to calculate ('smape', 'waste_ratio', 'actual_tokens', 'predicted_tokens')

    Returns:
        Dictionary with statistics:
        - mean: Mean value
        - median: Median value (P50)
        - p90: 90th percentile
        - p95: 95th percentile
        - min: Minimum value
        - max: Maximum value
        - count: Number of samples
    """
    if not samples:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "min": 0.0,
            "max": 0.0,
            "count": 0,
        }

    # Extract values based on metric
    values = []
    for sample in samples:
        if metric == "smape":
            pred = sample.get("predicted_output_tokens", 0)
            actual = sample.get("actual_output_tokens", 0)
            if pred > 0 and actual > 0:
                values.append(calculate_smape(pred, actual))
        elif metric == "waste_ratio":
            pred = sample.get("predicted_output_tokens", 0)
            actual = sample.get("actual_output_tokens", 0)
            if pred > 0 and actual > 0:
                values.append(calculate_waste_ratio(pred, actual))
        elif metric == "actual_tokens":
            actual = sample.get("actual_output_tokens", 0)
            if actual > 0:
                values.append(actual)
        elif metric == "predicted_tokens":
            pred = sample.get("predicted_output_tokens", 0)
            if pred > 0:
                values.append(pred)
        else:
            raise ValueError(f"Unknown metric: {metric}")

    if not values:
        return {
            "mean": 0.0,
            "median": 0.0,
            "p90": 0.0,
            "p95": 0.0,
            "min": 0.0,
            "max": 0.0,
            "count": 0,
        }

    # Sort for percentile calculations
    values_sorted = sorted(values)
    n = len(values_sorted)

    # Calculate percentiles
    def percentile(data: List[float], p: float) -> float:
        """Calculate percentile using linear interpolation."""
        if not data:
            return 0.0
        k = (len(data) - 1) * (p / 100.0)
        f = int(k)
        c = k - f
        if f + 1 < len(data):
            return data[f] + c * (data[f + 1] - data[f])
        return data[f]

    return {
        "mean": sum(values) / n,
        "median": percentile(values_sorted, 50),
        "p90": percentile(values_sorted, 90),
        "p95": percentile(values_sorted, 95),
        "min": values_sorted[0],
        "max": values_sorted[-1],
        "count": n,
    }


def calculate_underestimation_rate(samples: List[Dict[str, Any]], tolerance: float = 1.0) -> float:
    """Calculate percentage of samples that underestimated actual tokens.

    Args:
        samples: List of telemetry samples
        tolerance: Tolerance multiplier (default: 1.0 = no tolerance)

    Returns:
        Underestimation rate as percentage (0-100)
    """
    if not samples:
        return 0.0

    underestimated = 0
    total = 0

    for sample in samples:
        pred = sample.get("predicted_output_tokens", 0)
        actual = sample.get("actual_output_tokens", 0)

        if pred > 0 and actual > 0:
            total += 1
            if detect_underestimation(pred, actual, tolerance):
                underestimated += 1

    if total == 0:
        return 0.0

    return (underestimated / total) * 100.0


def calculate_truncation_rate(samples: List[Dict[str, Any]]) -> float:
    """Calculate percentage of samples that were truncated.

    Args:
        samples: List of telemetry samples

    Returns:
        Truncation rate as percentage (0-100)
    """
    if not samples:
        return 0.0

    truncated = sum(1 for s in samples if s.get("truncated", False))
    return (truncated / len(samples)) * 100.0


def validate_sample(
    sample: Dict[str, Any], required_fields: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]:
    """Validate a telemetry sample has required fields and valid values.

    Args:
        sample: Telemetry sample dictionary
        required_fields: List of required field names (default: standard fields)

    Returns:
        Tuple of (is_valid, error_message)
    """
    if required_fields is None:
        required_fields = [
            "predicted_output_tokens",
            "actual_output_tokens",
            "category",
            "complexity",
        ]

    # Check required fields
    for field in required_fields:
        if field not in sample:
            return False, f"Missing required field: {field}"

    # Validate token values
    pred = sample.get("predicted_output_tokens")
    actual = sample.get("actual_output_tokens")

    if not isinstance(pred, (int, float)) or pred < 0:
        return False, f"Invalid predicted_output_tokens: {pred}"

    if not isinstance(actual, (int, float)) or actual < 0:
        return False, f"Invalid actual_output_tokens: {actual}"

    # Validate category and complexity
    category = sample.get("category", "")
    complexity = sample.get("complexity", "")

    if not isinstance(category, str) or not category:
        return False, f"Invalid category: {category}"

    if not isinstance(complexity, str) or not complexity:
        return False, f"Invalid complexity: {complexity}"

    return True, None


def group_by_category(samples: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group samples by task category.

    Args:
        samples: List of telemetry samples

    Returns:
        Dictionary mapping category to list of samples
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for sample in samples:
        category = sample.get("category", "unknown").lower()
        if category not in groups:
            groups[category] = []
        groups[category].append(sample)

    return groups


def group_by_complexity(samples: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group samples by complexity level.

    Args:
        samples: List of telemetry samples

    Returns:
        Dictionary mapping complexity to list of samples
    """
    groups: Dict[str, List[Dict[str, Any]]] = {}

    for sample in samples:
        complexity = sample.get("complexity", "unknown").lower()
        if complexity not in groups:
            groups[complexity] = []
        groups[complexity].append(sample)

    return groups
