# Autopack Framework

**Autonomous AI Code Generation Framework**

Autopack is a framework for orchestrating autonomous AI agents (Builder and Auditor) to plan, build, and verify software projects. It uses a structured approach with phased execution, quality gates, and self-healing capabilities.

---

## Recent Updates (v0.3.0 - Phase 2 Complete)

### Autopack Doctor (NEW)
LLM-based diagnostic system for intelligent failure recovery:
- **Failure Diagnosis**: Analyzes phase failures and recommends recovery actions
- **Model Routing**: Uses cheap model (glm-4.6) for routine failures, strong model (claude-sonnet-4-5) for complex ones
- **Actions**: `retry_with_fix` (with hint), `replan`, `skip_phase`, `mark_fatal`, `rollback_run`
- **Budgets**: Per-phase limit (2 calls) and run-level limit (10 calls) to prevent loops
- **Confidence Escalation**: Upgrades to strong model if confidence < 0.7

**Configuration** (`config/models.yaml`):
```yaml
doctor_models:
  cheap: glm-4.6
  strong: claude-sonnet-4-5
  min_confidence_for_cheap: 0.7
  health_budget_near_limit_ratio: 0.8
  high_risk_categories: [import, logic]
```

### Model Escalation System
Automatically escalates to more powerful models when phases fail repeatedly:
- **Intra-tier escalation**: Within complexity level (e.g., glm-4.6 -> claude-sonnet-4-5)
- **Cross-tier escalation**: Bump complexity level after N failures (low -> medium -> high)
- **Configurable thresholds**: `config/models.yaml` defines `complexity_escalation` settings

### Mid-Run Re-Planning with Message Similarity
Detects "approach flaws" vs transient failures using error message similarity:
- `_normalize_error_message()` - Strips variable content (paths, UUIDs, timestamps, line numbers)
- `_calculate_message_similarity()` - Uses `difflib.SequenceMatcher` with 0.8 threshold
- `_detect_approach_flaw()` - Triggers re-planning after consecutive same-type failures with similar messages

**Configuration** (`config/models.yaml`):
```yaml
replan:
  trigger_threshold: 2
  message_similarity_enabled: true
  similarity_threshold: 0.8
  fatal_error_types: [wrong_tech_stack, schema_mismatch, api_contract_wrong]
```

### Run-Level Health Budget
Prevents infinite retry loops by tracking failures across the run:
- `MAX_HTTP_500_PER_RUN`: 10 (stop after too many server errors)
- `MAX_PATCH_FAILURES_PER_RUN`: 15 (stop after too many patch failures)
- `MAX_TOTAL_FAILURES_PER_RUN`: 25 (hard cap on total failures)

### LLM Multi-Provider Routing
- Routes to GLM (Zhipu), Anthropic, or OpenAI based on model name
- **Provider tier strategy**:
  - Low complexity: GLM (`glm-4.6`) - cheapest
  - Medium complexity: Anthropic (`claude-sonnet-4-5`) - excellent cost/quality balance
  - High complexity: Anthropic (`claude-sonnet-4-5`) - premium quality
- Automatic fallback chain: GLM -> Anthropic -> OpenAI
- Per-category routing policies (BEST_FIRST, PROGRESSIVE, CHEAP_FIRST)

**Environment Variables**:
```bash
# Required for each provider you want to use
GLM_API_KEY=your-zhipu-api-key        # Zhipu AI (GLM) - low complexity
ANTHROPIC_API_KEY=your-anthropic-key   # Anthropic - medium/high complexity
OPENAI_API_KEY=your-openai-key         # OpenAI - optional fallback
```

### Hardening: Syntax + Unicode + Incident Fatigue
- Pre-emptive encoding fix at startup
- `PYTHONUTF8=1` environment variable for all subprocesses
- UTF-8 encoding on all file reads
- SyntaxError detection in CI checks

---

## Phase 3 Preview: Direct Fix Execution

### Doctor `execute_fix` Action (Coming Soon)
Enables Doctor to execute infrastructure-level fixes directly without going through Builder:
- **Problem Solved**: Merge conflicts, missing files, Docker issues currently require manual intervention
- **Solution**: Doctor emits shell commands (`git checkout`, `docker restart`, etc.) executed directly
- **Safety**: Strict whitelist, workspace-only paths, opt-in via config, no sudo/admin

**Planned Configuration** (`config/models.yaml`):
```yaml
doctor:
  allow_execute_fix_global: false   # Opt-in required
  max_execute_fix_per_phase: 1      # One attempt per phase
  allowed_fix_types: ["git", "file"] # Typed categories
```

**Supported Fix Types** (v1):
- `git`: `checkout`, `reset`, `stash`, `clean`, `merge --abort`
- `file`: `rm`, `mkdir`, `cp`, `mv` (workspace only)
- `python`: `pip install`, `pytest` (planned)

See [IMPLEMENTATION_PLAN.md](archive/IMPLEMENTATION_PLAN.md) for full design details.

---

## Documentation

Detailed documentation is available in the `archive/` directory:

- **[Archive Index](archive/ARCHIVE_INDEX.md)**: Master index of all documentation.
- **[Implementation Plan](archive/IMPLEMENTATION_PLAN.md)**: Current roadmap and Phase 3+ planning.
- **[Autonomous Executor](archive/CONSOLIDATED_REFERENCE.md#autonomous-executor-readme)**: Guide to the orchestration system.
- **[Learned Rules](LEARNED_RULES_README.md)**: System for preventing recurring errors.
- **[GPT/Claude Dialog](archive/)**: GPT_RESPONSE4-8.md and CLAUDE_RESPONSE*_TO_GPT.md for design decisions.

## Project Structure

```
C:/dev/Autopack/
├── .autonomous_runs/         # Runtime data and project-specific archives
│   ├── file-organizer-app-v1/# Example Project: File Organizer
│   └── ...
├── archive/                  # Framework documentation archive
├── config/
│   └── models.yaml           # Model configuration, escalation, routing policies
├── logs/
│   └── archived_runs/        # Archived log files from previous runs
├── src/
│   └── autopack/             # Core framework code
│       ├── autonomous_executor.py  # Main orchestration loop
│       ├── llm_service.py          # Multi-provider LLM abstraction
│       ├── model_router.py         # Model selection with quota awareness
│       ├── model_selection.py      # Escalation chains and routing policies
│       ├── error_recovery.py       # Error categorization and recovery
│       ├── archive_consolidator.py # Documentation management
│       ├── debug_journal.py        # Self-healing system wrapper
│       └── ...
├── scripts/                  # Utility scripts
│   └── consolidate_docs.py   # Documentation consolidation
└── tests/                    # Framework tests
```

## Key Features

- **Autonomous Orchestration**: Wires Builder and Auditor agents to execute phases automatically.
- **Model Escalation**: Automatically escalates to more powerful models after failures.
- **Mid-Run Re-Planning**: Detects approach flaws and revises phase strategy.
- **Self-Healing**: Automatically logs errors, fixes, and extracts prevention rules.
- **Quality Gates**: Enforces risk-based checks before code application.
- **Multi-Provider LLM**: Routes to Gemini, GLM, Anthropic, or OpenAI with automatic fallback.
- **Project Separation**: Strictly separates runtime data and docs for different projects.

## Usage

### Running an Autonomous Build

```bash
python src/autopack/autonomous_executor.py --run-id my-new-run
```

### Consolidating Documentation

To tidy up and consolidate documentation across projects:

```bash
python scripts/consolidate_docs.py
```

This will:
1. Scan all documentation files.
2. Sort them into project-specific archives (`archive/` vs `.autonomous_runs/<project>/archive/`).
3. Create consolidated reference files (`CONSOLIDATED_DEBUG.md`, etc.).
4. Move processed files to `superseded/`.

---

## Configuration

### Model Escalation (`config/models.yaml`)

```yaml
complexity_escalation:
  enabled: true
  thresholds:
    low_to_medium: 2    # Escalate after 2 failures at low complexity
    medium_to_high: 2   # Escalate after 2 failures at medium complexity
  max_attempts_per_phase: 5
  failure_types:
    - auditor_reject
    - ci_fail
    - patch_apply_error

escalation_chains:
  builder:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro, claude-sonnet-4-5]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5, gpt-5]
    high:
      models: [claude-sonnet-4-5, gpt-5]
  auditor:
    low:
      models: [glm-4.5-20250101, gemini-2.5-pro]
    medium:
      models: [gemini-2.5-pro, claude-sonnet-4-5]
    high:
      models: [claude-sonnet-4-5, claude-opus-4-5]
```

### Re-Planning (`config/models.yaml`)

```yaml
replan:
  trigger_threshold: 2          # Consecutive same-type failures before re-plan
  message_similarity_enabled: true
  similarity_threshold: 0.8     # How similar messages must be (0.0-1.0)
  min_message_length: 30        # Skip similarity check for short messages
  max_replans_per_phase: 1      # Prevent infinite re-planning loops
  fatal_error_types:            # Immediate re-plan triggers
    - wrong_tech_stack
    - schema_mismatch
    - api_contract_wrong
```

---

**Version**: 0.3.0 (Phase 2 Complete)
**License**: MIT
**Last Updated**: 2025-12-01
