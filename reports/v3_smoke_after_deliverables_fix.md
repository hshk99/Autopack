# Token Estimation Telemetry Analysis V3
Generated: 2025-12-23T21:24:12.740706

## Analysis Configuration
- **Filter**: ALL SAMPLES (includes failures)
- **Total Records**: 5
- **Analysis Records**: 5
- **V2 Records**: 0
- **Underestimation tolerance**: actual > predicted * 1.00

---

## 🎯 TIER 1: RISK METRICS (Primary Tuning Gates)

### Truncation Prevention
- **Underestimation Rate**: 0.0% (0 samples)
  - **Target**: ≤ 5%
  - **Status**: ✅ WITHIN TARGET

- **Truncation Rate** (V2 only): 0.0% (0 samples)
  - **Target**: ≤ 2%
  - **Status**: ✅ WITHIN TARGET

### Quality
- **Success Rate** (V2 only): 0.0% (0 samples)

---

## 💰 TIER 2: COST METRICS (Secondary Optimization)

### Budget Waste (predicted/actual ratio)
- **Median**: 6.20x
- **P90**: 15.50x
- **Mean**: 7.82x

**Interpretation**:
- 1.0x = perfect prediction
- >1.0x = overestimation (budget waste)
- <1.0x = underestimation (truncation risk)

---

## 📊 DIAGNOSTIC METRICS (SMAPE - for reference only)

### SMAPE (Symmetric Mean Absolute Percentage Error)
- **Mean**: 79.4%
- **Median**: 83.9%
- **Range**: 57.3% - 93.5%

### Token Distribution
- **Predicted**: mean=1000, median=800
- **Actual**: mean=126, median=129

---

## 🚦 TUNING DECISION: ✅ WITHIN TARGETS

### ✅ No Tuning Needed

Tier 1 metrics are within targets. Monitor for drift, but coefficient changes are not required.

Consider cost optimization (Tier 2) if waste ratio P90 > 3x, but this is secondary to truncation prevention.


---

## 📋 Next Steps

1. ⚠️ **Re-run with --success-only flag** for tuning decisions
2. Current analysis includes failure-mode samples (not representative)
3. Only use Tier 1 metrics from successful phases for tuning
4. Keep this "all samples" view for monitoring overall behavior

---

## Data Sources

Total files analyzed: 1

- `telemetry_collection.log`: 5 records
