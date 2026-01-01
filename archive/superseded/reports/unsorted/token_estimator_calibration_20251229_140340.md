# Token Estimator Calibration Report

Generated: 2025-12-29T14:03:40.558315+00:00

## Summary

- Total samples analyzed: 6
- Total groups: 4
- High-confidence groups (≥70%): 0

## Recommendations

No groups met the confidence threshold for recommendations.
Increase sample size or lower confidence threshold.

## Detailed Results

All calibration groups (including low-confidence):

| Category | Complexity | Samples | Avg Actual | Avg Est | Median Ratio | Confidence | Proposed Mult |
|----------|------------|---------|------------|---------|--------------|------------|---------------|
| docs | medium | 2 | 5000 | 3900 | 1.47x | 43.6% | 1.47x |
| tests | medium | 2 | 3380 | 4420 | 0.81x | 48.2% | 0.81x |
| doc_synthesis | medium | 1 | 3638 | 7085 | 0.51x | 45.0% | 0.51x |
| tests | low | 1 | 1424 | 4420 | 0.32x | 45.0% | 0.32x |

## Notes

- **Median ratio > 1.0**: Underestimating (need to increase coefficients)
- **Median ratio < 1.0**: Overestimating (need to decrease coefficients)
- **Confidence**: Based on sample count and ratio variance
- **Proposed multiplier**: Apply to current PHASE_OVERHEAD or TOKEN_WEIGHTS

