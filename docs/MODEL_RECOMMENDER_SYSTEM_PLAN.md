# Model Catalog + Recommendation System (Postgres-backed)

Audience: **you** (the implementer).

This plan creates a repeatable system so model upgrades (e.g., `glm-4.6 → glm-4.7`) are **not** done by manual codebase hunting and ad-hoc prompts. It also adds a **recommendation engine** that uses:

- **Official pricing/specs**
- **Benchmarks** (official + reputable third parties)
- **Real Autopack telemetry** (actual cost + success/failure outcomes)
- **Community sentiment** (e.g., Reddit threads) as supporting evidence

The system persists **recommendations + evidence** in **PostgreSQL**, and can optionally generate a PR/config patch.

---

## 0) Core intention (do not stray)

1. **Single source of truth** for model definitions, roles, and defaults.
2. **No stale hardcoded model strings** left behind after upgrades (enforced by audit).
3. **Postgres-backed evidence** so recommendations are explainable and reproducible.
4. **No silent auto-upgrades**. The system recommends + produces a proposed change, but upgrades require explicit approval (config change / PR).
5. The recommendation logic must consider:
   - objective metrics (price, benchmarks)
   - **real-world** outcomes (Autopack telemetry)
   - user sentiment signals (Reddit/HN) **as supporting evidence**, not as the sole driver.

---

## 1) Scope (what you will build)

### In scope
- A model catalog persisted in Postgres (`models_catalog`, `model_pricing`, `model_benchmarks`).
- A telemetry-derived performance table (`model_runtime_stats`) aggregated from existing telemetry DB tables.
- A sentiment capture table (`model_sentiment_signals`) with sources/quotes/URLs.
- A recommendation table (`model_recommendations`) with:
  - current model per use-case
  - candidate replacement
  - expected tradeoffs + confidence score
  - evidence references
- A CLI workflow:
  1) ingest/update catalog (pricing/benchmarks)
  2) compute runtime stats from telemetry
  3) ingest sentiment signals (optional, but supported)
  4) generate recommendations and persist to DB
  5) print a human-readable report + optionally write a patch for `config/models.yaml`

### Explicitly out of scope (for v1)
- Automatically changing production config without approval.
- Running a live benchmarking harness on your own workloads (A/B can come later; you already have A/B scaffolding in other areas).
- Building a full UI; CLI + DB + docs are enough.

---

## 2) Where “model usage” is defined (SOT)

### Canonical config inputs
- `config/models.yaml`: routing, defaults, tool models, aliases.
- `config/pricing.yaml`: base pricing (will be kept, but also loaded into Postgres).

### Canonical runtime truth
- Telemetry DB tables (already exist):
  - `llm_usage_events` (provider, model, tokens)
  - `runs` / `phases` tables (outcomes) (depending on schema)

---

## 3) Postgres schema (new tables)

Create a dedicated “model intelligence” schema in Postgres (either separate tables or a prefix).

### 3.1 `models_catalog`
Stores identity + metadata.
- `model_id` (PK, text) — canonical key (e.g., `claude-sonnet-4-5`, `glm-4.7`)
- `provider` (text) — `anthropic`, `openai`, `google`, `zhipu_glm`
- `family` (text) — `claude`, `gpt`, `gemini`, `glm`
- `display_name` (text)
- `context_window_tokens` (int, nullable)
- `notes` (text, nullable)
- `released_at` (timestamptz, nullable)
- `is_deprecated` (bool, default false)
- `created_at`, `updated_at`

### 3.2 `model_pricing`
Stores pricing history (time series).
- `id` (PK)
- `model_id` (FK models_catalog)
- `input_per_1k` (numeric)
- `output_per_1k` (numeric)
- `currency` (text, default `USD`)
- `effective_at` (timestamptz)
- `source` (text) — e.g., `anthropic_pricing_page`, `openai_pricing_page`
- `source_url` (text)
- `retrieved_at` (timestamptz)
- Unique: `(model_id, effective_at, source)`

### 3.3 `model_benchmarks`
Stores benchmark records (time series, multiple sources).
- `id` (PK)
- `model_id` (FK)
- `benchmark_name` (text) — e.g., `SWE-bench Verified`, `MMLU`, `HumanEval`
- `score` (numeric)
- `unit` (text) — `percent`, `pass@1`, etc.
- `task_type` (text) — `code`, `reasoning`, `math`, `multimodal`, etc.
- `dataset_version` (text, nullable)
- `source` (text) — `official`, `lmsys`, `third_party`
- `source_url` (text)
- `retrieved_at` (timestamptz)
- Unique: `(model_id, benchmark_name, dataset_version, source_url)`

### 3.4 `model_runtime_stats`
Aggregated from your real telemetry (rolling window).
- `id` (PK)
- `window_start`, `window_end` (timestamptz)
- `provider` (text)
- `model` (text)
- `role` (text) — builder/auditor/doctor/agent:planner etc.
- `calls` (int)
- `total_tokens` (bigint)
- `prompt_tokens` (bigint, nullable)
- `completion_tokens` (bigint, nullable)
- `est_cost_usd` (numeric, nullable) — computed using pricing table
- `success_rate` (numeric, nullable) — if you can infer success (else leave null for v1)
- `p50_tokens`, `p90_tokens` (bigint, nullable)
- `notes` (text, nullable)
- Unique: `(window_start, window_end, provider, model, role)`

### 3.5 `model_sentiment_signals`
Stores community “experience” evidence (supporting, not primary).
- `id` (PK)
- `model_id` (FK)
- `source` (text) — `reddit`, `hn`, `twitter`, `blog`
- `source_url` (text)
- `title` (text, nullable)
- `snippet` (text) — short quote or extracted summary
- `sentiment` (text) — `positive|neutral|negative|mixed`
- `tags` (jsonb) — e.g., `{ "topic": "coding", "issue": "hallucination" }`
- `retrieved_at` (timestamptz)
- Unique: `(model_id, source_url)`

### 3.6 `model_recommendations`
Stores the actual recommendation objects.
- `id` (PK)
- `created_at` (timestamptz)
- `status` (text) — `proposed|accepted|rejected|implemented`
- `use_case` (text) — e.g., `tidy_semantic`, `builder_low`, `doctor_cheap`
- `current_model` (text)
- `recommended_model` (text)
- `reasoning` (text) — concise human-readable rationale
- `expected_cost_delta_pct` (numeric, nullable)
- `expected_quality_delta` (numeric, nullable) — normalized 0..1 if possible
- `confidence` (numeric) — 0..1
- `evidence` (jsonb) — IDs/refs to pricing/benchmarks/runtime_stats/sentiment
- `proposed_patch` (text, nullable) — optional YAML patch or diff excerpt
- Unique: `(use_case, current_model, recommended_model, created_at)` (or a dedupe hash)

---

## 4) Recommendation logic (v1)

### 4.1 Define “use cases”
Start with a small fixed set (expand later):
- `tidy_semantic` (from `config/models.yaml tool_models.tidy_semantic`)
- `builder_default_low|medium|high` (from `complexity_models`)
- `auditor_default_low|medium|high`
- `doctor_cheap`, `doctor_strong`

### 4.2 Candidate generation
For each use case:
- Prefer same provider family upgrades first (e.g., `glm-4.6 → glm-4.7`).
- Also consider cross-provider candidates **only** if:
  - pricing is competitive AND
  - benchmark score is better AND
  - runtime stats don’t show clear regressions (or are missing and confidence is lowered).

### 4.3 Scoring (simple, explainable)
Compute a composite score:
\[
score = w_p \cdot price\_score + w_b \cdot benchmark\_score + w_r \cdot runtime\_score + w_s \cdot sentiment\_score
\]

Guidelines:
- Set **sentiment weight low** (e.g., \(w_s = 0.05\)) so it nudges but doesn’t dominate.
- Runtime score should be based on your own telemetry:
  - cost per successful phase (if available)
  - retries / failure patterns (if available)
- If runtime stats unavailable, reduce confidence and rely on price/benchmarks.

### 4.4 Output
Store top 1–3 candidates per use case with evidence pointers.

---

## 5) Implementation skeleton (files)

### 5.1 New module: `src/autopack/model_intelligence/`
Create:
- `src/autopack/model_intelligence/__init__.py`
- `src/autopack/model_intelligence/models.py`  
  SQLAlchemy models for tables above (or raw SQL if preferred, but ORM is recommended for consistency).
- `src/autopack/model_intelligence/db.py`  
  session helpers / migrations helper (require explicit `DATABASE_URL`).
- `src/autopack/model_intelligence/catalog_ingest.py`  
  load `config/models.yaml` + `config/pricing.yaml` into DB.
- `src/autopack/model_intelligence/runtime_stats.py`  
  aggregate `llm_usage_events` → `model_runtime_stats` and estimate cost via pricing.
- `src/autopack/model_intelligence/sentiment_ingest.py`  
  fetch/summarize sentiment signals (see below).
- `src/autopack/model_intelligence/recommender.py`  
  candidate generation + scoring + DB writes.
- `src/autopack/model_intelligence/patcher.py`  
  generate proposed patch for `config/models.yaml` for selected recommendations.

### 5.2 New scripts
Add:
- `scripts/model_intel.py` (CLI entrypoint)

Commands:
- `python scripts/model_intel.py ingest-catalog`
- `python scripts/model_intel.py compute-runtime-stats --window-days 30`
- `python scripts/model_intel.py ingest-sentiment --model glm-4.7 --source reddit --limit 20`
- `python scripts/model_intel.py recommend --use-case tidy_semantic`
- `python scripts/model_intel.py report --latest`
- `python scripts/model_intel.py propose-patch --recommendation-id <id>`

### 5.3 Migrations
Create a migration script:
- `scripts/migrations/add_model_intelligence_tables_build146_pXX.py`

Requirement: fail if `DATABASE_URL` not set (production safety pattern).

### 5.4 Tests
Add:
- `tests/test_model_intelligence_recommender.py`
- `tests/test_model_intelligence_runtime_stats.py`
- `tests/test_model_intelligence_catalog_ingest.py`

Use SQLite in-memory for unit tests where possible (consistent with your existing testing approach), but ensure Postgres SQL compatibility if using Postgres-only types.

---

## 6) Sentiment ingestion (Reddit etc.)

### Approach (v1)
- Do not try to scrape at scale.
- Use a small number of “high-signal” sources:
  - specific subreddit threads (`r/LocalLLaMA`, `r/OpenAI`, `r/ClaudeAI`) and/or
  - curated links provided by you
- Store:
  - URL
  - extracted snippet(s)
  - sentiment label
  - tags (`coding`, `reasoning`, `speed`, `hallucination`, `tool_use`, etc.)

### Tooling
If you have a web search function available in your environment:
- Use it to collect candidate URLs.
If not:
- Make `ingest-sentiment` accept URLs explicitly as input.

**Important**: sentiment is supporting evidence; it should never silently override pricing/telemetry.

---

## 7) “No outdated model left behind” policy

Keep using `scripts/model_audit.py` as a guardrail:
- Add a CI step later (optional) to run:
  - `python scripts/model_audit.py --glob "*.py" --fail-on "glm-4.6"`
…once you confirm `glm-4.6` is truly deprecated for active paths.

For now, treat old model strings in comments/docs as acceptable; the audit script supports filtering/targeting.

---

## 8) Reusable prompt (copy/paste)

Use this prompt to implement the system without drift:

> Implement the Postgres-backed model catalog + recommendation system described in `docs/MODEL_RECOMMENDER_SYSTEM_PLAN.md`.  
> Intention: eliminate manual model bump hunts; persist explainable recommendations + evidence; no information loss; no silent auto-upgrades.  
> Deliverables: new Postgres tables + migration, `scripts/model_intel.py` CLI, catalog ingestion (models.yaml + pricing.yaml), runtime stats aggregation from telemetry, sentiment ingestion (URLs + snippets), recommendation engine with scoring + DB persistence, and tests.  
> Constraints: safe defaults, explicit `DATABASE_URL` required for mutations, bounded outputs, and recommendations must cite evidence (pricing/benchmarks/telemetry/sentiment) in DB.


