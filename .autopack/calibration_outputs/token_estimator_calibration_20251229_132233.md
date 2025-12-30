# Token Estimator Calibration Report

Generated: 2025-12-29T13:22:33.163952+00:00

## Summary

- Total samples analyzed: 36
- Total groups: 4
- High-confidence groups (≥70%): 0

## Recommendations

No groups met the confidence threshold for recommendations.
Increase sample size or lower confidence threshold.

## Detailed Results

All calibration groups (including low-confidence):

| Category | Complexity | Samples | Avg Actual | Avg Est | Median Ratio | Confidence | Proposed Mult |
|----------|------------|---------|------------|---------|--------------|------------|---------------|
| docs | low | 13 | 4152 | 2551 | 1.34x | 53.7% | 1.34x |
| implementation | medium | 9 | 4124 | 6704 | 0.40x | 57.3% | 0.40x |
| implementation | low | 8 | 1675 | 5200 | 0.32x | 66.3% | 0.32x |
| testing | medium | 6 | 4615 | 5070 | 0.89x | 58.5% | 0.89x |

## Notes

- **Median ratio > 1.0**: Underestimating (need to increase coefficients)
- **Median ratio < 1.0**: Overestimating (need to decrease coefficients)
- **Confidence**: Based on sample count and ratio variance
- **Proposed multiplier**: Apply to current PHASE_OVERHEAD or TOKEN_WEIGHTS

