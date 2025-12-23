# BUILD-132: Coverage Delta Integration for Quality Gate

**Status**: PLANNED
**Priority**: MEDIUM (Short-term, next 2 weeks)
**Estimated Time**: 2-3 hours
**Created**: 2025-12-23
**Prerequisite**: BUILD-127 Phase 3 (Quality Gate) - ✅ COMPLETE

## Executive Summary

Currently, `coverage_delta` is hardcoded to `0.0` in all Quality Gate calls. This BUILD implements actual coverage delta calculation to enhance Quality Gate decision-making with test coverage metrics.

### Current State
```python
# autonomous_executor.py:4536, 4556, 5167, 5179, 5716, 5728, 6055, 6067
coverage_delta=0.0,  # TODO: Calculate actual coverage delta
```

### Target State
```python
coverage_delta=calculate_coverage_delta(
    baseline_coverage=run_config.get("baseline_coverage", 0.0),
    current_coverage=extract_coverage_from_test_results(ci_result)
)
```

## Problem Statement

The Quality Gate currently checks coverage_delta:
```python
# quality_gate.py:463-464
if coverage_delta < -5.0:
    issues.append(f"Code coverage decreased by {abs(coverage_delta):.1f}%")
```

However, this check never triggers because coverage_delta is always 0.0. This means:
- Quality Gate cannot detect coverage regressions
- Missing signal for assessing change quality
- Unable to enforce coverage thresholds

## Technical Investigation

### 1. pytest-cov Status
✅ **INSTALLED**: pytest-cov 7.0.0 is available

### 2. Current pytest Configuration
**File**: `pytest.ini`
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

**Status**: No coverage collection configured

### 3. Usage Sites
coverage_delta is passed to Quality Gate in:
- `autonomous_executor.py`: 8 call sites across batching functions
- `llm_service.py`: Passed through to quality_gate
- `quality_gate.py`: Used in validation logic

## Implementation Plan

### Phase 1: Enable Coverage Collection (30 min)

**1.1 Update pytest.ini**
```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --cov=src/autopack
    --cov-report=term-missing:skip-covered
    --cov-report=json:.coverage.json
    --cov-branch
asyncio_mode = auto
asyncio_default_fixture_loop_scope = function
```

**Rationale**:
- `--cov=src/autopack`: Measure coverage for main codebase
- `--cov-report=json:.coverage.json`: Machine-readable output for parsing
- `--cov-branch`: Include branch coverage (more accurate)
- `term-missing:skip-covered`: Human-readable output showing uncovered lines

**1.2 Establish T0 Baseline**
```bash
# Run tests to generate baseline
PYTHONPATH=src pytest tests/ -v

# Save baseline coverage
cp .coverage.json .coverage_baseline.json

# Store in run config
echo '{"baseline_coverage": <extracted_percentage>}' > .autopack_baseline.json
```

### Phase 2: Coverage Extraction (45 min)

**2.1 Create Coverage Helper Module**
**File**: `src/autopack/coverage_tracker.py`

```python
"""Coverage delta calculation for Quality Gate.

Tracks test coverage changes relative to baseline for quality assessment.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

logger = logging.getLogger(__name__)


class CoverageTracker:
    """Calculate coverage delta for Quality Gate."""

    def __init__(self, workspace_root: Path):
        self.workspace_root = workspace_root
        self.baseline_path = workspace_root / ".coverage_baseline.json"
        self.current_path = workspace_root / ".coverage.json"

    def get_baseline_coverage(self) -> Optional[float]:
        """Load baseline coverage from T0 snapshot.

        Returns:
            Baseline coverage percentage, or None if not found
        """
        if not self.baseline_path.exists():
            logger.warning(
                f"[CoverageTracker] Baseline not found at {self.baseline_path}. "
                f"Run 'pytest --cov' and save .coverage.json as .coverage_baseline.json"
            )
            return None

        try:
            data = json.loads(self.baseline_path.read_text())
            return self._extract_coverage_percentage(data)
        except Exception as e:
            logger.error(f"[CoverageTracker] Failed to load baseline: {e}")
            return None

    def get_current_coverage(self) -> Optional[float]:
        """Extract coverage from most recent test run.

        Returns:
            Current coverage percentage, or None if not found
        """
        if not self.current_path.exists():
            logger.debug(
                f"[CoverageTracker] No coverage data at {self.current_path}. "
                f"Tests may not have run with --cov flag."
            )
            return None

        try:
            data = json.loads(self.current_path.read_text())
            return self._extract_coverage_percentage(data)
        except Exception as e:
            logger.error(f"[CoverageTracker] Failed to load current coverage: {e}")
            return None

    def _extract_coverage_percentage(self, coverage_data: Dict) -> float:
        """Extract overall coverage percentage from pytest-cov JSON.

        Args:
            coverage_data: Parsed .coverage.json data

        Returns:
            Coverage percentage (0-100)
        """
        # pytest-cov JSON format:
        # {
        #   "totals": {
        #     "percent_covered": 85.5,
        #     "num_statements": 1000,
        #     "missing_lines": 145,
        #     ...
        #   }
        # }
        totals = coverage_data.get("totals", {})
        return totals.get("percent_covered", 0.0)

    def calculate_delta(self) -> Tuple[float, Dict[str, Optional[float]]]:
        """Calculate coverage delta (current - baseline).

        Returns:
            Tuple of:
            - delta: Coverage change in percentage points
            - metadata: Dict with baseline, current, delta
        """
        baseline = self.get_baseline_coverage()
        current = self.get_current_coverage()

        if baseline is None or current is None:
            logger.warning(
                f"[CoverageTracker] Cannot calculate delta: "
                f"baseline={baseline}, current={current}"
            )
            return 0.0, {
                "baseline": baseline,
                "current": current,
                "delta": 0.0,
                "error": "Missing baseline or current coverage data"
            }

        delta = current - baseline

        logger.info(
            f"[CoverageTracker] Coverage delta: {delta:+.1f}% "
            f"(baseline={baseline:.1f}%, current={current:.1f}%)"
        )

        return delta, {
            "baseline": baseline,
            "current": current,
            "delta": delta
        }


def calculate_coverage_delta(workspace_root: Path) -> float:
    """Convenience function to calculate coverage delta.

    Args:
        workspace_root: Project root directory

    Returns:
        Coverage delta in percentage points (e.g., +5.0, -2.5)
    """
    tracker = CoverageTracker(workspace_root)
    delta, metadata = tracker.calculate_delta()
    return delta
```

**2.2 Unit Tests**
**File**: `tests/test_coverage_tracker.py`

```python
"""Unit tests for coverage delta calculation."""

import pytest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

from autopack.coverage_tracker import CoverageTracker, calculate_coverage_delta


class TestCoverageTracker:
    """Test coverage delta calculation."""

    def test_calculate_delta_success(self):
        """Test successful delta calculation."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Create baseline coverage (80%)
            baseline_data = {
                "totals": {"percent_covered": 80.0}
            }
            (workspace / ".coverage_baseline.json").write_text(json.dumps(baseline_data))

            # Create current coverage (85%)
            current_data = {
                "totals": {"percent_covered": 85.0}
            }
            (workspace / ".coverage.json").write_text(json.dumps(current_data))

            tracker = CoverageTracker(workspace)
            delta, metadata = tracker.calculate_delta()

            assert delta == 5.0
            assert metadata["baseline"] == 80.0
            assert metadata["current"] == 85.0
            assert metadata["delta"] == 5.0

    def test_calculate_delta_regression(self):
        """Test coverage regression (negative delta)."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Baseline: 90%
            baseline_data = {"totals": {"percent_covered": 90.0}}
            (workspace / ".coverage_baseline.json").write_text(json.dumps(baseline_data))

            # Current: 75% (regression)
            current_data = {"totals": {"percent_covered": 75.0}}
            (workspace / ".coverage.json").write_text(json.dumps(current_data))

            delta, metadata = tracker = CoverageTracker(workspace).calculate_delta()

            assert delta == -15.0
            assert metadata["delta"] == -15.0

    def test_missing_baseline(self):
        """Test when baseline doesn't exist."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            # Only current, no baseline
            current_data = {"totals": {"percent_covered": 80.0}}
            (workspace / ".coverage.json").write_text(json.dumps(current_data))

            tracker = CoverageTracker(workspace)
            delta, metadata = tracker.calculate_delta()

            assert delta == 0.0  # Fallback to 0
            assert "error" in metadata

    def test_convenience_function(self):
        """Test calculate_coverage_delta convenience function."""
        with TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)

            baseline_data = {"totals": {"percent_covered": 70.0}}
            current_data = {"totals": {"percent_covered": 75.0}}

            (workspace / ".coverage_baseline.json").write_text(json.dumps(baseline_data))
            (workspace / ".coverage.json").write_text(json.dumps(current_data))

            delta = calculate_coverage_delta(workspace)
            assert delta == 5.0
```

### Phase 3: Integration with Executor (30 min)

**3.1 Update autonomous_executor.py**

Replace all 8 instances of:
```python
coverage_delta=0.0,  # TODO: Calculate actual coverage delta
```

With:
```python
coverage_delta=calculate_coverage_delta(self.workspace_root),
```

**Import addition** (top of file):
```python
from .coverage_tracker import calculate_coverage_delta
```

**Call sites**:
- Line 4536 (execute_phase_with_autonomous_recovery)
- Line 4556 (execute_phase_with_autonomous_recovery - journal logging)
- Line 5167 (_execute_phase_with_batching)
- Line 5179 (_execute_phase_with_batching - journal logging)
- Line 5716 (_execute_deliverables_batching_v2)
- Line 5728 (_execute_deliverables_batching_v2 - journal logging)
- Line 6055 (_execute_deliverables_batching_old)
- Line 6067 (_execute_deliverables_batching_old - journal logging)

**3.2 Error Handling**

The `calculate_coverage_delta()` function already handles missing data gracefully:
- Returns 0.0 if baseline or current coverage missing
- Logs warnings for debugging
- Non-blocking: won't crash execution

### Phase 4: Documentation and Baseline Setup (30 min)

**4.1 Update README.md**

Add coverage section:
```markdown
## Test Coverage

Autopack tracks test coverage to monitor code quality:

### Initial Setup (One-time)
```bash
# Generate baseline coverage
PYTHONPATH=src pytest tests/ --cov=src/autopack --cov-report=json:.coverage.json

# Save as baseline
cp .coverage.json .coverage_baseline.json
```

### During Development
Coverage is automatically calculated during autonomous runs. The Quality Gate will:
- ✅ Pass if coverage increases or stays stable
- ⚠️  Warn if coverage decreases by >5%
- Track delta relative to baseline

### Manual Coverage Check
```bash
# Run tests with coverage
PYTHONPATH=src pytest tests/ --cov=src/autopack --cov-report=term-missing

# View detailed coverage
PYTHONPATH=src pytest tests/ --cov=src/autopack --cov-report=html
open htmlcov/index.html
```

**4.2 Add to .gitignore**
```gitignore
.coverage
.coverage.*
!.coverage_baseline.json
htmlcov/
.pytest_cache/
```

## Testing Plan

### 1. Unit Tests
```bash
PYTHONPATH=src pytest tests/test_coverage_tracker.py -v
```
Expected: All tests pass

### 2. Integration Test
```bash
# Generate baseline
PYTHONPATH=src pytest tests/ --cov=src/autopack --cov-report=json:.coverage.json
cp .coverage.json .coverage_baseline.json

# Run with slightly different coverage (modify a test)
PYTHONPATH=src pytest tests/test_autonomous_executor.py --cov=src/autopack --cov-report=json:.coverage.json

# Check logs for coverage delta
grep "CoverageTracker" backend.log
```
Expected: Log shows coverage delta calculation

### 3. Quality Gate Test
```bash
# Create a test run with coverage delta
python scripts/test_coverage_integration.py
```
Expected: Quality Gate receives non-zero coverage_delta

## Rollout Plan

### Step 1: Implement (60 min)
1. Update pytest.ini with coverage flags
2. Create coverage_tracker.py module
3. Write unit tests
4. Update autonomous_executor.py imports and calls

### Step 2: Establish Baseline (15 min)
1. Run full test suite with coverage
2. Save baseline
3. Document in README.md

### Step 3: Validate (30 min)
1. Run unit tests
2. Run integration test
3. Verify Quality Gate receives coverage data
4. Check logs for coverage delta logging

### Step 4: Monitor (Ongoing)
1. Track coverage delta in runs
2. Tune threshold if needed (currently -5% triggers warning)
3. Consider stricter thresholds for critical paths

## Success Criteria

- [  ] pytest-cov configured in pytest.ini
- [  ] CoverageTracker module implemented and tested
- [  ] Baseline coverage established
- [  ] All 8 executor call sites updated
- [  ] Integration test passes
- [  ] Quality Gate logs show coverage delta
- [  ] Documentation updated
- [  ] No regressions in existing tests

## Future Enhancements (Post-BUILD-132)

### 1. Per-Module Coverage Tracking
Track coverage by module to identify under-tested areas

### 2. Coverage Trends
Store coverage history to visualize trends over time

### 3. Stricter Thresholds
Enforce minimum coverage requirements for new code

### 4. Branch Coverage Analysis
Deep-dive into branch coverage for critical paths

## References

- Quality Gate Implementation: [quality_gate.py:463-464](../src/autopack/quality_gate.py#L463-L464)
- Current TODO Sites: [autonomous_executor.py:4536](../src/autopack/autonomous_executor.py#L4536)
- pytest-cov Documentation: https://pytest-cov.readthedocs.io/
- BUILD-127 Phase 3: Quality Gate with structured deliverables validation

## Risk Assessment

**Risk**: Low
**Why**:
- pytest-cov already installed
- Non-breaking change (fallback to 0.0 on errors)
- Quality Gate already designed for coverage_delta
- No changes to existing test logic

**Mitigation**:
- Comprehensive unit tests
- Graceful error handling
- Baseline can be regenerated if lost
- Documented rollback (remove coverage flags from pytest.ini)
