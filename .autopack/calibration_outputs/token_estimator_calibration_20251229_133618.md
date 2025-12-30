# Token Estimator Calibration Report

Generated: 2025-12-29T13:36:18.839363+00:00

## Summary

- Total samples analyzed: 36
- Total groups: 4
- High-confidence groups (≥70%): 3

## Recommendations

Groups with sufficient confidence for coefficient adjustments:

### implementation / low

- **Samples**: 8
- **Confidence**: 77.1%
- **Current avg estimate**: 5200 tokens
- **Actual avg**: 1675 tokens
- **Median ratio** (actual/estimated): 0.32x
- **Proposed multiplier**: 0.32x
- **Action**: Decrease coefficients by 68%

### docs / low

- **Samples**: 13
- **Confidence**: 77.0%
- **Current avg estimate**: 2551 tokens
- **Actual avg**: 4152 tokens
- **Median ratio** (actual/estimated): 1.34x
- **Proposed multiplier**: 1.34x
- **Action**: Increase coefficients by 34%

### implementation / medium

- **Samples**: 9
- **Confidence**: 72.8%
- **Current avg estimate**: 6704 tokens
- **Actual avg**: 4124 tokens
- **Median ratio** (actual/estimated): 0.40x
- **Proposed multiplier**: 0.40x
- **Action**: Decrease coefficients by 60%

## Detailed Results

All calibration groups (including low-confidence):

| Category | Complexity | Samples | Avg Actual | Avg Est | Median Ratio | Confidence | Proposed Mult |
|----------|------------|---------|------------|---------|--------------|------------|---------------|
| docs | low | 13 | 4152 | 2551 | 1.34x | 77.0% | 1.34x |
| implementation | medium | 9 | 4124 | 6704 | 0.40x | 72.8% | 0.40x |
| implementation | low | 8 | 1675 | 5200 | 0.32x | 77.1% | 0.32x |
| testing | medium | 6 | 4615 | 5070 | 0.89x | 64.8% | 0.89x |

## Notes

- **Median ratio > 1.0**: Underestimating (need to increase coefficients)
- **Median ratio < 1.0**: Overestimating (need to decrease coefficients)
- **Confidence**: Based on sample count and ratio variance
- **Proposed multiplier**: Apply to current PHASE_OVERHEAD or TOKEN_WEIGHTS

