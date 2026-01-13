# Universal Comprehensive Scan Prompt - CI-Efficient

**Version**: 1.0.0 | **Date**: 2026-01-13 | **Part of**: PR-INFRA-3

**Copy-paste this prompt to run a CI-efficient comprehensive scan:**

---

Given the current state of Autopack (based on recent PRs and README.md ideal state):

Perform a **COMPREHENSIVE SCAN** for improvement opportunities and categorize by **CI IMPACT**.

## Categorization Rules

**Category A - Docs Only** (No backend tests)
- Files: `docs/**`, `README.md`, `*.md`
- CI Impact: ~5-10 min (docs-sot-integrity job only)
- Path filter: Triggers `docs` but not `backend`

**Category B - Frontend Only** (No backend tests)
- Files: `*.tsx`, `*.ts` (frontend), `*.css`, `vite.config.ts`, `package.json`
- CI Impact: ~10-15 min (frontend-ci job only)
- Path filter: Triggers `frontend` but not `backend`

**Category C - Backend Non-Critical** (Partial tests)
- Files: `src/autopack/research/**`, `src/autopack/storage_optimizer/**`, `src/autopack/diagnostics/**`
- CI Impact: ~15-25 min (subset of 4,901 core tests)
- Test markers: Often marked `@pytest.mark.research` (549 tests)

**Category D - Backend Core** (Full test suite)
- Files: `src/autopack/autonomous_executor.py`, `src/autopack/llm_service.py`, `src/autopack/anthropic_clients.py`, core modules
- CI Impact: ~30-45 min (all 4,901 core tests)
- Test markers: Core tests (no markers, blocking)

**Category E - Infrastructure/Tooling** (Parallel-safe)
- Files: `scripts/**`, `.github/workflows/**`, `pyproject.toml`, `requirements*.txt`
- CI Impact: Variable (15-45 min, but can run parallel with other work)
- Examples: CI improvements, testing tools, build configs

## Output Format

For **EACH** improvement opportunity, provide:

```json
{
  "id": "IMP-001",
  "category": "A|B|C|D|E",
  "title": "Brief title",
  "description": "1-2 sentence description",
  "files_affected": ["list", "of", "files"],
  "effort": "S|M|L|XL",
  "priority": "Critical|High|Medium|Low",
  "dependencies": ["IMP-002", "IMP-003"],
  "parallel_safe": true|false,
  "test_impact": {
    "test_files": ["tests/path/to/test.py"],
    "test_count_estimate": 100,
    "can_mark_aspirational": true|false
  },
  "pr_suggestion": "PR-XXX-N: Brief PR title",
  "estimated_ci_time": "10 min"
}
```

## Execution Plan Output

After listing all improvements, generate:

```json
{
  "scan_metadata": {
    "scan_date": "YYYY-MM-DD",
    "total_opportunities": 42,
    "by_category": {
      "A": 8, "B": 5, "C": 7, "D": 15, "E": 7
    }
  },
  "execution_plan": {
    "wave_1_parallel": {
      "description": "Zero backend impact - can merge all PRs in parallel",
      "improvements": ["IMP-001", "IMP-002", "..."],
      "categories": ["A", "B", "E"],
      "estimated_prs": 5,
      "estimated_ci_time_parallel": "15 min wall-clock",
      "merge_strategy": "All can merge independently"
    },
    "wave_2_parallel": {
      "description": "Low backend impact - parallel non-critical improvements",
      "improvements": ["IMP-015", "IMP-016", "..."],
      "categories": ["C", "E"],
      "estimated_prs": 3,
      "estimated_ci_time_parallel": "25 min wall-clock",
      "merge_strategy": "All can merge independently"
    },
    "wave_3_sequential": {
      "description": "High backend impact - batched core improvements",
      "batches": [
        {
          "batch_id": "CORE-BATCH-1",
          "description": "Executor improvements",
          "improvements": ["IMP-020", "IMP-021", "..."],
          "estimated_ci_time": "45 min",
          "merge_strategy": "Sequential (one PR)"
        },
        {
          "batch_id": "CORE-BATCH-2",
          "description": "LLM service improvements",
          "improvements": ["IMP-025", "IMP-026", "..."],
          "estimated_ci_time": "45 min",
          "merge_strategy": "Sequential (one PR)"
        }
      ]
    }
  },
  "summary": {
    "without_batching": "450 min (10 PRs × 45 min each)",
    "with_batching": "125 min wall-clock (Wave1: 15 min + Wave2: 25 min + Wave3: 90 min)",
    "time_saved": "325 min (72% reduction)",
    "with_pytest_xdist": "60 min wall-clock (87% reduction - if PR-INFRA-1 merged)"
  }
}
```

## Scope Guidelines

Scan these areas comprehensively:

1. **Code Quality**: Refactoring, complexity reduction, pattern improvements
2. **Testing**: Coverage gaps, flaky tests, test organization
3. **Documentation**: Outdated docs, missing guides, SOT improvements
4. **Performance**: Bottlenecks, optimization opportunities
5. **Architecture**: Design debt, coupling issues, modularity
6. **Security**: Vulnerabilities, best practices, hardening
7. **Developer Experience**: Tooling, CI/CD, local development
8. **Feature Completeness**: README ideal state gaps, roadmap items

## Context Handling

If context limits are reached:
1. Output partial results in JSON format
2. Mark as: `"status": "partial", "continue_from": "wave_3_sequential"`
3. I'll respond with "continue" to resume

---

**Important**: Focus on **actionable, concrete improvements** with clear file paths and PR structures. Avoid vague suggestions.

**Goal**: Generate a complete, executable improvement plan that minimizes total CI time through smart categorization and parallel execution.
