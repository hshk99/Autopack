# Token Estimation Telemetry Analysis
Generated: 2025-12-23T19:48:48.706768

## Summary

**Total Records Analyzed:** 11
**Formats:** v2=5 v1=6
**Mean Error Rate:** 96.7%
**Target (<30% error):** ❌ NO
**Under-estimation rate:** 0.0% (risk for truncation)
**Over-estimation rate:** 100.0%
**V2 truncation rate:** 0.0% (only where V2 telemetry present)
**V2 success rate:** 0.0% (only where V2 telemetry present)

## Error Rate Statistics

- **Mean:** 96.7%
- **Median:** 93.5%
- **Min:** 57.3%
- **Max:** 145.7%
- **Std Dev:** 23.2%

## Token Predictions

### Predicted Tokens
- **Mean:** 731
- **Median:** 448
- **Range:** 300 - 2000

### Actual Tokens
- **Mean:** 124
- **Median:** 128
- **Range:** 104 - 129

### Absolute Error
- **Mean:** 607 tokens
- **Median:** 324 tokens

## Estimation Direction (Risk)

- **Over-estimated:** 11 records (100.0%)
- **Under-estimated:** 0 records (0.0%)

## Recommendations

### 🔴 Critical: High Error Rate (≥50%)

1. **Immediate Action Required:**
   - Review TokenEstimator coefficients in `src/autopack/token_estimator.py`
   - Check if deliverable type categorization is accurate
   - Verify base estimates for different file types

2. **Investigation Areas:**
   - Are actual file sizes much different from estimated averages?
   - Are there specific deliverable categories with consistently high errors?
   - Is the context size calculation accurate?


### Bias: Consistent Over-Estimation

The estimator is over-predicting by a large margin. Consider:
- Reducing base estimates for common file types
- Lowering safety buffers
- Reviewing context size multipliers

## Next Steps

1. **Prioritize V2 telemetry:** Ensure logs include `[TokenEstimationV2]` so we measure the real TokenEstimator.
2. **Collect representative runs:** Prefer successful phases; failure-mode outputs skew token counts downwards.
3. **Tune for truncation risk:** Track under-estimation rate + truncation rate alongside error.
4. **Stratify:** Break down by category/deliverable count once you have enough V2 records.

## Data Sources

- `telemetry_collection.log`: 5 records
- `telemetry_collection_v2.log`: 5 records
- `test_telemetry_output.log`: 1 records
