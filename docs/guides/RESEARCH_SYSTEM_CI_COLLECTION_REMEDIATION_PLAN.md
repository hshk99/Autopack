# Research System CI Collection Remediation Plan (Bring repo back to README “ideal state”)

## Goal

Restore the state claimed in `README.md` (2025-12-28 v0.4.10) where:

- **Zero test collection failures** (pytest collection must succeed)
- The **research system compatibility APIs** exist (so batch drain phases don’t fail at CI collection time)
- The repo can safely batch-drain research runs without deterministic CI import failures wasting tokens

This plan is written to address the **specific, reproduced failures** currently exhibited by `python -m pytest --collect-only -q`.

## Current observed failures (reproduced)

Running `python -m pytest --collect-only -q` currently produces **6 collection errors**:

1. `tests/autopack/cli/test_research_commands.py`
   - `ImportError: cannot import name 'list_phases' from 'autopack.cli.research_commands'`
2. `tests/autopack/integrations/test_build_history_integrator.py`
   - `ImportError: cannot import name 'BuildHistoryInsights' from 'autopack.integrations.build_history_integrator'`
3. `tests/autopack/phases/test_research_phase.py`
   - `ImportError: cannot import name 'ResearchPhaseExecutor' from 'autopack.phases.research_phase'`
4. `tests/autopack/workflow/test_research_review.py`
   - `ImportError: cannot import name 'ReviewResult' from 'autopack.workflow.research_review'`
5. `tests/research/frameworks/test_product_feasibility.py`
   - `ImportError: cannot import name 'TechnicalRequirement' from 'research.frameworks.product_feasibility'`
6. `tests/research/gatherers/test_reddit_gatherer.py`
   - `import file mismatch` because `test_reddit_gatherer.py` exists in two different paths and is imported as the same top-level module

Additionally, a repo-wide duplicate basename scan shows **5 duplicate test module basenames** that can trigger the same “import file mismatch” issue:

- `test_auth.py` (2 paths)
- `test_backlog_maintenance.py` (2 paths)
- `test_evidence_model.py` (2 paths)
- `test_orchestrator.py` (3 paths)
- `test_reddit_gatherer.py` (2 paths)

## Root causes

### Root cause A — Compatibility APIs referenced by tests do not exist (API drift)

Multiple test suites import symbols that are not present in the implementation modules:

- `autopack.cli.research_commands` exports `list_sessions`, but tests import `list_phases`.
- `autopack.integrations.build_history_integrator` defines `BuildHistoryInsight` (singular) but tests import `BuildHistoryInsights` (plural) and expect a different shape.
- `autopack.phases.research_phase` does not define `ResearchPhaseExecutor` and its data models don’t match test expectations.
- `autopack.workflow.research_review` does not define `ReviewResult` and its workflow API does not match test expectations.
- `research.frameworks.product_feasibility` defines `TechnicalRequirements` / `ResourceRequirements`, but tests import `TechnicalRequirement` / `ResourceRequirement` and expect different scoring methods.

This is consistent with the log theme: “CI collection/import errors” are the dominant deterministic failure cluster.

### Root cause B — Duplicate test module basenames + non-package test dirs

Pytest is importing some tests as **top-level modules** because the containing directories are not Python packages (missing `__init__.py`).

When two files share the same basename (e.g., `test_reddit_gatherer.py`) and are both imported as `test_reddit_gatherer`, pytest detects an “import file mismatch” and aborts collection.

### Root cause C — Dependency declaration drift (latent, but blocks “ideal state” reproducibility)

Even when the environment has the packages installed, the repo currently does not declare several runtime/test dependencies that the code imports (e.g., `click`, `requests`, and likely `rich` / `praw` depending on which modules are exercised).

This makes “ideal state” non-reproducible across fresh environments and CI runners.

## Target state / Acceptance criteria

### A. CI collection is clean

- `python -m pytest --collect-only -q` exits with code `0`
- No `ImportError` and no `import file mismatch`

### B. Compatibility APIs exist for research-system tests

At minimum, the following imports must work:

- `from autopack.cli.research_commands import list_phases`
- `from autopack.integrations.build_history_integrator import BuildHistoryInsights`
- `from autopack.phases.research_phase import ResearchPhaseExecutor`
- `from autopack.workflow.research_review import ReviewResult`
- `from research.frameworks.product_feasibility import TechnicalRequirement, ResourceRequirement`

### C. README claims are true again

`README.md` v0.4.10 claims:
- “CI Collection Blockers … compatibility API”
- “Zero test collection failures”

After implementing this plan, that claim should again be accurate.

## Implementation plan (concrete steps)

### 1) Eliminate “import file mismatch” errors (duplicate basenames)

**Approach:** Make the relevant `tests/**` subdirectories Python packages so pytest imports them with fully-qualified module names instead of as top-level modules.

Add empty `__init__.py` files to the following directories (minimum set to fix known duplicates):

- `tests/backend/api/`
- `tests/backlog/`
- `tests/research/unit/`
- `tests/research/tracer_bullet/`
- `tests/research/gatherers/`
- `tests/autopack/research/gatherers/`

Then re-run:

- `python -m pytest --collect-only -q`

If any additional “import file mismatch” appears, repeat:

- run the duplicate-basename scan (see Appendix A)
- add `__init__.py` to the colliding directories

### 2) Restore `autopack.cli.research_commands` compatibility exports + CLI contract

File: `src/autopack/cli/research_commands.py`

**Required changes:**

- **Export `list_phases`**: Provide `list_phases` as an alias to the existing click command `list_sessions` (or rename to `list_phases` and keep `list_sessions` as backward alias).
- **Match test CLI flags**:
  - Tests invoke `start_research` as a click command expecting:
    - a positional “description” argument
    - `-q/--query` repeated for multiple queries
    - `-c/--category` option (string)
    - `-o/--output` output path
  - Update `start_research` click signature to accept these without crashing.
- **Expose `ResearchPhaseExecutor` symbol for monkeypatching**:
  - Tests monkeypatch `autopack.cli.research_commands.ResearchPhaseExecutor`.
  - Ensure the module defines `ResearchPhaseExecutor` (import it from `autopack.phases.research_phase` and re-export it).

**Non-goals (for now):**

- Full persistence/backed “list” and “status” support. The tests allow “not found / not implemented” as long as it doesn’t crash.

### 3) Rebuild `autopack.phases.research_phase` to satisfy tests (and keep a sane API)

File: `src/autopack/phases/research_phase.py`

**Problem:** Current file is a placeholder-oriented API that does not match tests.

**Strategy:** Implement the “test contract API” directly in this module (keeping any existing helpers if still used elsewhere), and ensure the names imported by tests exist.

**Required public API (as used in tests):**

- `ResearchPhaseStatus` enum with at least: `PENDING`, `IN_PROGRESS`, `COMPLETED`, `FAILED`
  - Also keep `ResearchStatus` as an alias if other code uses it.
- `ResearchQuery` dataclass:
  - Fields used by tests: `query: str`, `priority: int = 1`, `required: bool = False`
  - Allow optional `context: dict = field(default_factory=dict)`
- `ResearchResult` dataclass:
  - Fields used by tests: `query: str`, `answer: str`, `confidence: float`
  - Optional: `sources: list[str] = field(default_factory=list)`, `metadata: dict = field(default_factory=dict)`
- `ResearchPhaseConfig` dataclass:
  - Fields used by tests: `queries: list[ResearchQuery] = field(default_factory=list)`
  - Optional config used by tests: `max_duration_minutes`, `save_to_history`, `auto_approve_threshold`
- `ResearchPhase` class:
  - `__init__(phase_id: str, description: str, config: ResearchPhaseConfig, status: ResearchPhaseStatus = PENDING)`
  - properties expected by tests: `phase_id`, `description`, `config`, `status`, `results`, `started_at`, `completed_at`, `error`
  - `to_dict()` used by tests
- `ResearchPhaseExecutor` class:
  - `__init__(research_system=None, build_history_path: Path | None = None)`
  - `execute(phase: ResearchPhase) -> ResearchPhase`
  - `should_auto_approve(phase: ResearchPhase) -> bool`
  - `_format_history_entry(phase: ResearchPhase) -> str`

**Execution behavior expected by tests:**

- When `research_system` is provided, call `research_system.query(query, context)` and map its response into `ResearchResult`.
- When `research_system` is `None`, still “succeed” with a placeholder `ResearchResult` with `confidence=0.0`.
- Respect `required=True`: if a required query returns very low confidence (e.g., `< 0.5`), mark the phase `FAILED` and set `phase.error`.
- Always set `started_at` and `completed_at`.

### 4) Rebuild `autopack.workflow.research_review` to satisfy tests

File: `src/autopack/workflow/research_review.py`

**Problem:** Current file implements a different review model than tests require.

**Required public API (as used in tests):**

- `ReviewDecision` enum with values:
  - `APPROVED`, `REJECTED`, `NEEDS_MORE_RESEARCH`
- `ReviewCriteria` dataclass with fields:
  - `auto_approve_confidence: float = 0.9`
  - `auto_reject_confidence: float = 0.3`
  - `require_human_review: bool = True`
  - `min_findings_required: int = 1`
  - `min_recommendations_required: int = 1`
- `ReviewResult` dataclass:
  - `decision`, `reviewer`, `confidence`, `comments`, `timestamp`
  - plus any extras referenced by tests (e.g., `approved_findings`)
- `ResearchReviewWorkflow` class:
  - internal storage `_pending_reviews: dict`
  - `submit_for_review(research_result) -> review_id`
  - `_can_auto_review(result) -> bool`
  - `_auto_review(result) -> ReviewResult`
  - `manual_review(review_id, decision, reviewer, comments=None) -> ReviewResult`
  - `get_review_status(review_id) -> dict`
  - `list_pending_reviews() -> list`
  - `export_review_to_build_history(review_id) -> str`

**Important:** `tests/autopack/workflow/test_research_review.py` currently expects a `ResearchPhaseResult` and `ResearchPhaseStatus` type from `autopack.phases.research_phase`. Ensure those exist (Step 3) or update the workflow to accept the `ResearchPhase`/result type you implement.

### 5) Restore BUILD_HISTORY integrator compatibility (`BuildHistoryInsights` + behaviors)

File: `src/autopack/integrations/build_history_integrator.py`

**Required public API (as used in tests):**

- `BuildHistoryInsights` dataclass with:
  - `total_phases: int`
  - `successful_phases: int`
  - `failed_phases: int`
  - `best_practices: list[str]`
  - `common_pitfalls: list[str]`
  - `patterns: list[HistoricalPattern]`
- `BuildHistoryIntegrator` methods:
  - `get_insights_for_task(task_desc, category=None) -> BuildHistoryInsights`
  - `should_trigger_research(task_desc, category=None, threshold=0.5) -> bool`
  - `format_insights_for_prompt(insights: BuildHistoryInsights) -> str`
  - `_merge_insights(ins1, ins2) -> BuildHistoryInsights`

**Parsing requirement:** The tests build a sample markdown using headings like:

- `## Phase 1: ...`
- `**Status**: ✓ SUCCESS` or `**Status**: ✗ FAILED`
- `**Category**: IMPLEMENT_FEATURE`

Implement a parser that extracts:

- phase count
- success/failure counts
- best practices (from “Lessons Learned” bullets)
- common pitfalls (from “Issues” bullets)
- patterns (can be simple: create a `HistoricalPattern` per category with frequency)

### 6) Restore `research.frameworks.product_feasibility` compatibility

File: `src/research/frameworks/product_feasibility.py`

**Problem:** Implementation exists, but names + scoring API do not match tests.

**Required public API (as used in tests):**

- `TechnicalRequirement` dataclass (singular) with:
  - `name`, `complexity`, `availability`, `maturity`
- `ResourceRequirement` dataclass (singular) with:
  - `team_size`, `required_skills`, `development_time_months`, `estimated_cost`
- `FeasibilityLevel` enum must include `VERY_HIGH_FEASIBILITY` (tests assert this exact value)
- `RiskLevel` enum should include at least `LOW`, `MEDIUM`, `HIGH`, `CRITICAL`
- `ProductFeasibility` class with methods:
  - `calculate_technical_score() -> float`
  - `calculate_resource_score() -> float`
  - `calculate_risk_score() -> float`
  - `get_feasibility_level() -> FeasibilityLevel`
  - `identify_critical_risks() -> list`
  - `generate_report() -> dict`

**Guidance:** You can keep the existing implementation as an internal engine, but you must expose the tested API and ensure score thresholds match:

- Mature/readily available/low complexity should yield **technical score ≥ 85**
- Unavailable/experimental/high complexity should yield **technical score < 40**
- Small team / short timeline / modest cost should yield **resource score ≥ 85**
- Large team / long timeline / high cost should yield **resource score < 40**
- No risks should yield **risk score ≥ 75**
- Critical/high risks should yield **risk score < 40**

### 7) Dependency declarations (make “ideal state” reproducible)

Update dependency declarations so a clean environment can run the above tests without “works on my machine” drift.

At minimum, add to the project dependencies (choose one source-of-truth and sync the other):

- `click` (required by CLI modules and tests)
- `requests` (used by research gatherers)
- `rich` (optional, but imported in CLI with a try/except; still recommended for full-feature usage)
- If `src/research/gatherers/reddit_gatherer.py` hard-imports `praw`, either:
  - declare `praw` as dependency, **or**
  - change that module to import `praw` lazily / safely so the module can import without it

### 8) Optional cleanup: reduce pytest collection warnings from `src/`

Pytest is currently discovering classes under `src/autopack/test_baseline_tracker.py` etc. This is not a hard failure, but it’s noisy and can hide real warnings.

Options:

- Rename modules under `src/autopack/` that start with `test_` to non-test names
- Or configure pytest to only collect tests under `tests/` and ignore `src/**/test_*.py`

## Validation checklist (must pass before declaring done)

Run locally:

1. `python -m pytest --collect-only -q`
2. `python -m pytest -q tests/autopack/cli/test_research_commands.py`
3. `python -m pytest -q tests/autopack/phases/test_research_phase.py`
4. `python -m pytest -q tests/autopack/workflow/test_research_review.py`
5. `python -m pytest -q tests/autopack/integrations/test_build_history_integrator.py`
6. `python -m pytest -q tests/research/frameworks/test_product_feasibility.py`
7. Re-run a full suite if time permits: `python -m pytest -q`

Success criteria:

- No collection errors
- These suites pass (or at minimum the repo returns to the README-claimed “targeted tests passing” for the research-system compatibility layer)

## Appendix A — Duplicate basename scan command

PowerShell-friendly command to scan for duplicate `test_*.py` basenames:

```powershell
python -c "import pathlib,collections; p=pathlib.Path('tests'); files=[f for f in p.rglob('test_*.py') if f.is_file()]; m=collections.defaultdict(list); [m[f.name].append(str(f)) for f in files]; d={k:v for k,v in m.items() if len(v)>1}; print('dup_basenames',len(d)); [print('\\n'+k+'\\n  '+'\\n  '.join(v)) for k,v in sorted(d.items())]"
```


