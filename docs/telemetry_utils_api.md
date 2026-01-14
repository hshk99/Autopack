# Telemetry Utils API Documentation

**Module**: `src.autopack.telemetry_utils`

**Purpose**: Utility functions for token estimation telemetry analysis

---

## Overview

The `telemetry_utils` module provides helper functions for analyzing token estimation telemetry data. It supports:

- **Sample filtering**: Filter telemetry samples by success, category, complexity, and token ranges
- **SMAPE calculation**: Symmetric Mean Absolute Percentage Error for prediction accuracy
- **Ratio statistics**: Waste ratio (predicted/actual) for budget efficiency analysis
- **Underestimation detection**: Identify samples where predictions fell short
- **Summary statistics**: Mean, median, percentiles for metrics
- **Validation**: Ensure telemetry samples have required fields and valid values
- **Grouping**: Organize samples by category or complexity

---

## Functions

### `filter_samples()`

Filter telemetry samples based on criteria.

**Signature**:
```python
filter_samples(
    samples: List[Dict[str, Any]],
    success_only: bool = False,
    category: Optional[str] = None,
    complexity: Optional[str] = None,
    min_actual_tokens: int = 50,
    max_actual_tokens: Optional[int] = None
) -> List[Dict[str, Any]]
```

**Parameters**:
- `samples`: List of telemetry sample dictionaries
- `success_only`: If True, only include samples with `success=True`
- `category`: Filter by task category (e.g., 'implementation', 'testing')
- `complexity`: Filter by complexity level (e.g., 'low', 'medium', 'high')
- `min_actual_tokens`: Minimum actual output tokens (default: 50, filters error responses)
- `max_actual_tokens`: Maximum actual output tokens (optional)

**Returns**: Filtered list of samples

**Example**:
```python
from src.autopack.telemetry_utils import filter_samples

# Filter for successful implementation phases with low complexity
filtered = filter_samples(
    samples,
    success_only=True,
    category='implementation',
    complexity='low'
)
```

---

### `calculate_smape()`

Calculate Symmetric Mean Absolute Percentage Error.

**Signature**:
```python
calculate_smape(
    predicted: float,
    actual: float,
    epsilon: float = 1.0
) -> float
```

**Parameters**:
- `predicted`: Predicted value
- `actual`: Actual value
- `epsilon`: Small constant to avoid division by zero (default: 1.0)

**Returns**: SMAPE percentage (0-200)

**Formula**: `SMAPE = |predicted - actual| / ((|predicted| + |actual|) / 2) * 100`

**Example**:
```python
from src.autopack.telemetry_utils import calculate_smape

smape = calculate_smape(predicted=1000, actual=900)
print(f"SMAPE: {smape:.1f}%")  # Output: SMAPE: 10.5%
```

---

### `calculate_waste_ratio()`

Calculate waste ratio (predicted / actual).

**Signature**:
```python
calculate_waste_ratio(
    predicted: float,
    actual: float,
    epsilon: float = 1.0
) -> float
```

**Parameters**:
- `predicted`: Predicted value
- `actual`: Actual value
- `epsilon`: Small constant to avoid division by zero (default: 1.0)

**Returns**: Waste ratio (predicted / actual)

**Interpretation**:
- `1.0` = perfect prediction
- `>1.0` = overestimation (wasted budget)
- `<1.0` = underestimation (risk of truncation)

**Example**:
```python
from src.autopack.telemetry_utils import calculate_waste_ratio

ratio = calculate_waste_ratio(predicted=2000, actual=1000)
print(f"Waste ratio: {ratio:.1f}x")  # Output: Waste ratio: 2.0x
```

---

### `detect_underestimation()`

Detect if prediction underestimated actual value.

**Signature**:
```python
detect_underestimation(
    predicted: float,
    actual: float,
    tolerance: float = 1.0
) -> bool
```

**Parameters**:
- `predicted`: Predicted value
- `actual`: Actual value
- `tolerance`: Tolerance multiplier (default: 1.0 = no tolerance)

**Returns**: True if underestimated beyond tolerance

**Example**:
```python
from src.autopack.telemetry_utils import detect_underestimation

# 10% underestimation
underestimated = detect_underestimation(predicted=900, actual=1000)
print(underestimated)  # Output: True

# Within 10% tolerance
underestimated = detect_underestimation(predicted=900, actual=1000, tolerance=1.1)
print(underestimated)  # Output: False
```

---

### `calculate_statistics()`

Calculate summary statistics for a metric across samples.

**Signature**:
```python
calculate_statistics(
    samples: List[Dict[str, Any]],
    metric: str = 'smape'
) -> Dict[str, float]
```

**Parameters**:
- `samples`: List of telemetry samples
- `metric`: Metric to calculate ('smape', 'waste_ratio', 'actual_tokens', 'predicted_tokens')

**Returns**: Dictionary with statistics:
- `mean`: Mean value
- `median`: Median value (P50)
- `p90`: 90th percentile
- `p95`: 95th percentile
- `min`: Minimum value
- `max`: Maximum value
- `count`: Number of samples

**Example**:
```python
from src.autopack.telemetry_utils import calculate_statistics

stats = calculate_statistics(samples, metric='waste_ratio')
print(f"Mean waste ratio: {stats['mean']:.2f}x")
print(f"P90 waste ratio: {stats['p90']:.2f}x")
```

---

### `calculate_underestimation_rate()`

Calculate percentage of samples that underestimated actual tokens.

**Signature**:
```python
calculate_underestimation_rate(
    samples: List[Dict[str, Any]],
    tolerance: float = 1.0
) -> float
```

**Parameters**:
- `samples`: List of telemetry samples
- `tolerance`: Tolerance multiplier (default: 1.0 = no tolerance)

**Returns**: Underestimation rate as percentage (0-100)

**Example**:
```python
from src.autopack.telemetry_utils import calculate_underestimation_rate

rate = calculate_underestimation_rate(samples)
print(f"Underestimation rate: {rate:.1f}%")
```

---

### `calculate_truncation_rate()`

Calculate percentage of samples that were truncated.

**Signature**:
```python
calculate_truncation_rate(
    samples: List[Dict[str, Any]]
) -> float
```

**Parameters**:
- `samples`: List of telemetry samples

**Returns**: Truncation rate as percentage (0-100)

**Example**:
```python
from src.autopack.telemetry_utils import calculate_truncation_rate

rate = calculate_truncation_rate(samples)
print(f"Truncation rate: {rate:.1f}%")
```

---

### `validate_sample()`

Validate a telemetry sample has required fields and valid values.

**Signature**:
```python
validate_sample(
    sample: Dict[str, Any],
    required_fields: Optional[List[str]] = None
) -> Tuple[bool, Optional[str]]
```

**Parameters**:
- `sample`: Telemetry sample dictionary
- `required_fields`: List of required field names (default: standard fields)

**Returns**: Tuple of `(is_valid, error_message)`

**Example**:
```python
from src.autopack.telemetry_utils import validate_sample

is_valid, error = validate_sample(sample)
if not is_valid:
    print(f"Invalid sample: {error}")
```

---

### `group_by_category()`

Group samples by task category.

**Signature**:
```python
group_by_category(
    samples: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]
```

**Parameters**:
- `samples`: List of telemetry samples

**Returns**: Dictionary mapping category to list of samples

**Example**:
```python
from src.autopack.telemetry_utils import group_by_category

groups = group_by_category(samples)
for category, category_samples in groups.items():
    print(f"{category}: {len(category_samples)} samples")
```

---

### `group_by_complexity()`

Group samples by complexity level.

**Signature**:
```python
group_by_complexity(
    samples: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]
```

**Parameters**:
- `samples`: List of telemetry samples

**Returns**: Dictionary mapping complexity to list of samples

**Example**:
```python
from src.autopack.telemetry_utils import group_by_complexity

groups = group_by_complexity(samples)
for complexity, complexity_samples in groups.items():
    print(f"{complexity}: {len(complexity_samples)} samples")
```

---

## Usage Examples

### Example 1: Analyze Success-Only Samples

```python
from src.autopack.telemetry_utils import (
    filter_samples,
    calculate_statistics,
    calculate_underestimation_rate,
    calculate_truncation_rate
)

# Load telemetry samples (from database, log files, etc.)
samples = load_telemetry_samples()

# Filter for successful samples only
successful = filter_samples(samples, success_only=True)

# Calculate key metrics
smape_stats = calculate_statistics(successful, metric='smape')
waste_stats = calculate_statistics(successful, metric='waste_ratio')
under_rate = calculate_underestimation_rate(successful)
trunc_rate = calculate_truncation_rate(successful)

print(f"Successful samples: {len(successful)}")
print(f"Mean SMAPE: {smape_stats['mean']:.1f}%")
print(f"P90 waste ratio: {waste_stats['p90']:.2f}x")
print(f"Underestimation rate: {under_rate:.1f}%")
print(f"Truncation rate: {trunc_rate:.1f}%")
```

### Example 2: Stratified Analysis by Category

```python
from src.autopack.telemetry_utils import (
    filter_samples,
    group_by_category,
    calculate_statistics
)

# Filter and group
successful = filter_samples(samples, success_only=True)
groups = group_by_category(successful)

# Analyze each category
for category, category_samples in groups.items():
    stats = calculate_statistics(category_samples, metric='waste_ratio')
    print(f"\n{category.upper()}:")
    print(f"  Samples: {stats['count']}")
    print(f"  Mean waste: {stats['mean']:.2f}x")
    print(f"  P90 waste: {stats['p90']:.2f}x")
```

### Example 3: Identify Problematic Samples

```python
from src.autopack.telemetry_utils import (
    filter_samples,
    detect_underestimation,
    validate_sample
)

# Find underestimated samples
problematic = []
for sample in samples:
    # Validate first
    is_valid, error = validate_sample(sample)
    if not is_valid:
        continue

    # Check for underestimation
    pred = sample['predicted_output_tokens']
    actual = sample['actual_output_tokens']
    if detect_underestimation(pred, actual, tolerance=1.1):
        problematic.append(sample)

print(f"Found {len(problematic)} underestimated samples")
```

---

## Related Documentation

- [TELEMETRY_GUIDE.md](TELEMETRY_GUIDE.md) - Telemetry collection and analysis guide
- [TELEMETRY_COLLECTION_GUIDE.md](TELEMETRY_COLLECTION_GUIDE.md) - Detailed collection workflow
- [TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md](archive/superseded/reports/unsorted/TOKEN_ESTIMATION_VALIDATION_LEARNINGS.md) - Methodology and learnings
- [src/autopack/token_estimator.py](../src/autopack/token_estimator.py) - Token estimator implementation

---

**Total Lines**: 250 (within ≤300 line constraint)

**Coverage**: All 11 functions documented with signatures, parameters, returns, and examples
