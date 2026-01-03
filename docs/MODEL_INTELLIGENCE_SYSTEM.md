# Model Intelligence System - Implementation Guide

## Overview

The Model Intelligence System is a Postgres-backed model catalog and recommendation engine that eliminates manual model bump hunts and provides explainable, evidence-based upgrade recommendations.

**Key Features:**
- Single source of truth for model definitions and pricing
- Evidence-backed recommendations (pricing, benchmarks, telemetry, sentiment)
- No silent auto-upgrades (recommendations require explicit approval)
- Comprehensive tracking of model metadata, benchmarks, runtime performance, and community sentiment

## Architecture

### Database Schema

The system uses 6 PostgreSQL tables:

1. **`models_catalog`** - Model identity and metadata
2. **`model_pricing`** - Time-series pricing records (USD per 1K tokens)
3. **`model_benchmarks`** - Benchmark scores from official/third-party sources
4. **`model_runtime_stats`** - Aggregated telemetry from `llm_usage_events`
5. **`model_sentiment_signals`** - Community sentiment evidence (supporting, not primary)
6. **`model_recommendations`** - Recommendation objects with evidence references

### Module Structure

```
src/autopack/model_intelligence/
├── __init__.py              # Module exports
├── models.py                # SQLAlchemy models
├── db.py                    # Database session helpers
├── catalog_ingest.py        # Load models.yaml + pricing.yaml
├── runtime_stats.py         # Aggregate llm_usage_events
├── sentiment_ingest.py      # Capture community sentiment
├── recommender.py           # Generate recommendations
└── patcher.py               # Generate YAML patches
```

## Setup

### 1. Run Migration

Create the database tables:

```bash
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
python scripts/migrations/add_model_intelligence_tables_build146_p18.py upgrade
```

### 2. Ingest Initial Data

Load models and pricing from YAML configs:

```bash
DATABASE_URL="postgresql://autopack:autopack@localhost:5432/autopack" \
python scripts/model_intel.py ingest-catalog
```

Expected output:
```
✓ Catalog ingestion complete:
  - Models ingested: 8
  - Pricing records ingested: 8
```

## Usage

### CLI Commands

The `scripts/model_intel.py` CLI provides all operations:

#### 1. Ingest Catalog

Load models and pricing from config files:

```bash
python scripts/model_intel.py ingest-catalog
```

#### 2. Compute Runtime Stats

Aggregate telemetry into runtime stats (rolling window):

```bash
python scripts/model_intel.py compute-runtime-stats --window-days 30
```

#### 3. Ingest Sentiment Signals

Add community sentiment evidence:

```bash
python scripts/model_intel.py ingest-sentiment \
  --model glm-4.7 \
  --source reddit \
  --url "https://reddit.com/r/LocalLLaMA/..." \
  --snippet "GLM 4.7 shows significant improvements in code generation" \
  --sentiment positive \
  --title "GLM 4.7 Release Discussion"
```

#### 4. Generate Recommendations

Generate recommendations for a use case:

```bash
python scripts/model_intel.py recommend \
  --use-case tidy_semantic \
  --current-model glm-4.6 \
  --max-candidates 3 \
  --persist
```

Expected output:
```
✓ Found 3 recommendation(s):

[1] glm-4.7
    Provider: zhipu_glm
    Composite Score: 0.875
    Confidence: 90%
    Cost Delta: -15.2%
    Quality Delta: +12.5%

    ✓ Recommendation persisted (ID: 42)
```

#### 5. View Recommendations

Display latest recommendations:

```bash
python scripts/model_intel.py report --latest --use-case tidy_semantic
```

#### 6. Propose Patch

Generate YAML patch for approved recommendation:

```bash
python scripts/model_intel.py propose-patch \
  --recommendation-id 42 \
  --output /tmp/model_upgrade.patch
```

Expected output:
```
Model Recommendation Report (ID: 42)
======================================================================

Use Case:         tidy_semantic
Current Model:    glm-4.6
Recommended:      glm-4.7
Status:           proposed
Confidence:       90%

Reasoning:
  Recommended glm-4.7 for tidy_semantic. Composite score: 0.875.
  Evidence: pricing, benchmarks, runtime stats, sentiment.

Expected Cost Change:    -15.2%
Expected Quality Change: +12.5%

Evidence:
  - Pricing records: 2 references
  - Benchmark records: 4 references
  - Runtime stats: 2 references
  - Sentiment signals: 3 references

Proposed YAML Patch:
----------------------------------------------------------------------
# Recommendation ID: 42
# Use case: tidy_semantic
# Change: glm-4.6 → glm-4.7
# Reasoning: Recommended glm-4.7 for tidy_semantic. Composite score: 0.875.

tool_models:
  tidy_semantic: glm-4.7
----------------------------------------------------------------------

✓ Patch written to: /tmp/model_upgrade.patch
```

## Recommendation Scoring

The recommendation engine uses a weighted composite score:

```
score = 0.35 * price_score
      + 0.40 * benchmark_score
      + 0.20 * runtime_score
      + 0.05 * sentiment_score
```

### Scoring Components

1. **Price Score (35%)** - Objective cost comparison
   - 1.0 if cheaper
   - 0.75 if moderately more expensive (up to 50%)
   - 0.5 if up to 2x more expensive
   - 0.0 if >2x more expensive

2. **Benchmark Score (40%)** - Official/third-party benchmarks
   - 1.0 if 20%+ better
   - 0.75 if slightly better
   - 0.5 if similar
   - 0.0 if worse

3. **Runtime Score (20%)** - Real-world telemetry
   - Based on success rate and cost efficiency from actual usage
   - Falls back to neutral (0.5) if no telemetry available

4. **Sentiment Score (5%)** - Community feedback (supporting only)
   - Nudges score but never dominates
   - Based on aggregated positive/negative signals

### Confidence Calculation

- **0.9** if runtime telemetry is available
- **0.6** if relying only on pricing/benchmarks (no real-world data)

## Use Cases

The system supports these predefined use cases (expandable):

- `tidy_semantic` - Tidy tool semantic model
- `builder_low`, `builder_medium`, `builder_high` - Builder models by complexity
- `auditor_low`, `auditor_medium`, `auditor_high` - Auditor models by complexity
- `doctor_cheap`, `doctor_strong` - Doctor models

## Workflow Example

### Scenario: Upgrade GLM for Tidy Tool

1. **Ingest catalog and pricing:**
   ```bash
   python scripts/model_intel.py ingest-catalog
   ```

2. **Compute recent runtime stats:**
   ```bash
   python scripts/model_intel.py compute-runtime-stats --window-days 30
   ```

3. **Add sentiment signals (optional):**
   ```bash
   python scripts/model_intel.py ingest-sentiment \
     --model glm-4.7 \
     --source reddit \
     --url "https://reddit.com/..." \
     --snippet "Excellent coding improvements" \
     --sentiment positive
   ```

4. **Generate recommendations:**
   ```bash
   python scripts/model_intel.py recommend \
     --use-case tidy_semantic \
     --current-model glm-4.6 \
     --persist
   ```

5. **Review recommendation:**
   ```bash
   python scripts/model_intel.py report --latest
   ```

6. **Generate patch:**
   ```bash
   python scripts/model_intel.py propose-patch \
     --recommendation-id 42 \
     --output model_upgrade.patch
   ```

7. **Apply patch manually:**
   - Review `model_upgrade.patch`
   - Edit `config/models.yaml` to apply changes
   - Test the upgrade
   - Commit and deploy

## Production Safety

### Required Environment Variable

All mutation operations require explicit `DATABASE_URL`:

```bash
DATABASE_URL="postgresql://..." python scripts/model_intel.py ...
```

This prevents accidental writes to the wrong database.

### No Silent Upgrades

The system **never** automatically changes production config. All recommendations:
1. Are persisted to DB with status `proposed`
2. Require explicit human review
3. Must be manually applied to config files

### Evidence Traceability

Every recommendation stores evidence references:
- Pricing record IDs
- Benchmark record IDs
- Runtime stats record IDs
- Sentiment signal IDs

This ensures recommendations are always explainable and auditable.

## Testing

Run the test suite:

```bash
# All model intelligence tests
PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL="sqlite:///:memory:" \
pytest tests/test_model_intelligence_*.py -v

# Specific test modules
pytest tests/test_model_intelligence_catalog_ingest.py -v
pytest tests/test_model_intelligence_runtime_stats.py -v
pytest tests/test_model_intelligence_recommender.py -v
```

## Extending the System

### Adding New Benchmarks

```python
from autopack.model_intelligence.models import ModelBenchmark

benchmark = ModelBenchmark(
    model_id="glm-4.7",
    benchmark_name="SWE-bench Verified",
    score=48.5,
    unit="percent",
    task_type="code",
    dataset_version="2024-12",
    source="official",
    source_url="https://...",
)
session.add(benchmark)
session.commit()
```

### Adding New Use Cases

Edit `recommender.py` to add new use case patterns, or use the existing generic
recommendation flow with custom use case identifiers.

### Custom Sentiment Sources

Use the sentiment ingestion API to add custom sources beyond Reddit/HN:

```python
from autopack.model_intelligence.sentiment_ingest import ingest_sentiment_batch

signals = [
    {
        "model_id": "glm-4.7",
        "source": "blog",
        "source_url": "https://...",
        "snippet": "...",
        "sentiment": "positive",
        "title": "...",
        "tags": {"topic": "coding", "focus": "speed"},
    }
]

with get_model_intelligence_session() as session:
    results = ingest_sentiment_batch(session, signals)
```

## Troubleshooting

### Migration Fails

Ensure `DATABASE_URL` points to a PostgreSQL database (SQLite not supported for production):

```bash
DATABASE_URL="postgresql://user:pass@host:5432/dbname" \
python scripts/migrations/add_model_intelligence_tables_build146_p18.py upgrade
```

### No Recommendations Found

Check that:
1. Catalog is ingested: `python scripts/model_intel.py ingest-catalog`
2. Pricing is available for both current and candidate models
3. Models are not deprecated (`is_deprecated=False`)

### Low Confidence Scores

Confidence is reduced when runtime telemetry is unavailable. To improve:
1. Run `compute-runtime-stats` to aggregate recent telemetry
2. Ensure `llm_usage_events` table has data for the models in question

## References

- **Plan Document:** `archive/superseded/plans/MODEL_RECOMMENDER_SYSTEM_PLAN.md`
- **Migration Script:** `scripts/migrations/add_model_intelligence_tables_build146_p18.py`
- **CLI Tool:** `scripts/model_intel.py`
- **Module:** `src/autopack/model_intelligence/`
- **Tests:** `tests/test_model_intelligence_*.py`
