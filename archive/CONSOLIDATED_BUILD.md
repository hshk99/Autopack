# Consolidated Build Reference

**Last Updated**: 2025-12-04
**Auto-generated** by scripts/consolidate_docs.py

## Contents

- [ARCH_BUILDER_AUDITOR_DISCOVERY](#arch-builder-auditor-discovery)
- [AUTO_DOCUMENTATION](#auto-documentation)
- [BUILD_PLAN_TASK_TRACKER](#build-plan-task-tracker)
- [RECENT_SCOPE_FIX](#recent-scope-fix)

---

## RECENT_SCOPE_FIX

**Date**: 2025-12-04  
**Status**: ✅ Implemented in `src/autopack/autonomous_executor.py` and `src/autopack/anthropic_clients.py`

- Builder prompts now strictly reflect `scope.paths` vs `read_only_context`. Missing scoped files are surfaced as “create this file” tasks, and read-only context no longer appears under “Files You May Modify.”
- `_load_scoped_context` returns metadata for every scoped path (including placeholders for files that do not yet exist) so the LLM can generate Docker assets or other new files without guessing.
- `_parse_full_file_output` now accepts the streamed JSON payloads the Builder actually returns (handles markdown fences, leading chatter, and newline repairs), eliminating the “expected JSON with ‘files’ array” false negatives seen during the Docker phase.

Result: the Docker phase can now receive the correct context, create new scoped files, and pass JSON validation without manual intervention.

---

## ARCH_BUILDER_AUDITOR_DISCOVERY

**Source**: [ARCH_BUILDER_AUDITOR_DISCOVERY.md](C:\dev\Autopack\archive\superseded\ARCH_BUILDER_AUDITOR_DISCOVERY.md)
**Last Modified**: 2025-11-28

# Builder and Auditor Component Discovery

**Date**: 2025-11-28
**Status**: ✅ **Existing components found - No new implementation needed**

---

## Summary

Autopack already has well-architected Builder and Auditor components with clean, reusable APIs. These components follow proper software engineering patterns (Protocol interfaces, multiple implementations, clear separation of concerns).

**Recommendation**: Use existing components as-is. No need to create new `builder_component.py` or `auditor_component.py` files.

---

## Builder Component (Chunk B)

### Existing Implementation

**Protocol Interface**: `src/autopack/llm_client.py`

```python
class BuilderClient(Protocol):
    """Protocol for Builder implementations

    Builder generates code patches from phase specifications.
    """

    def execute_phase(
        self,
        phase_spec: Dict,
        file_context: Optional[Dict] = None,
        max_tokens: Optional[int] = None
    ) -> BuilderResult:
        """Execute a phase and generate code patch"""
        ...
```

**Data Model**:
```python
@dataclass
class BuilderResult:
    success: bool
    patch_content: str
    builder_messages: List[str]
    tokens_used: int
    model_used: str
    error: Optional[str] = None
```

### Concrete Implementations

1. **OpenAI Implementation**: `src/autopack/openai_clients.py`
   - **Class**: `OpenAIBuilderClient`
   - **Line**: 18
   - **Method**: `execute_phase(phase_spec, file_context, max_tokens, model, project_rules, run_hints)`
   - **Integration**: Uses `ModelRouter` for model selection, `LlmService` for usage tracking

2. **Anthropic Implementation**: `src/autopack/anthropic_clients.py`
   - **Class**: `AnthropicBuilderClient`
   - **Line**: 25
   - **Method**: `execute_phase(phase_spec, file_context, max_tokens, model, project_rules, run_hints)`
   - **Integration**: Claude Code integration, uses learned rules and run hints

### API Schemas (Chunk D)

**File**: `src/autopack/builder_schemas.py`

Defines comprehensive Builder result schemas:
- `BuilderResult` - Complete builder result with patch, files changed, token usage
- `BuilderProbeResult` - Test/probe results (pytest, lint, etc.)
- `BuilderSuggestedIssue` - Issues detected during building

---

## Auditor Component (Chunk C)

### Existing Implementation

**Protocol Interface**: `src/autopack/llm_client.py`

```python
class AuditorClient(Protocol):
    """Protocol for Auditor implementations

    Auditor reviews code patches and finds issues.
    """

    def review_patch(
        self,
        patch_content: str,
        phase_spec: Dict,
        max_tokens: Optional[int] = None
    ) -> AuditorResult:
        """Review a patch and find issues"""
        ...
```

**Data Model**:
```python
@dataclass
class AuditorResult:
    approved: bool
    issues_found: List[Dict]  # List of IssueCreate dicts
    auditor_messages: List[str]
    tokens_used: int
    model_used: str
    error: Optional[str] = None
```

### Concrete Implementations

1. **OpenAI Implementation**: `src/autopack/openai_clients.py`
   - **Class**: `OpenAIAuditorClient`
   - **Line**: 188
   - **Method**: `review_patch(patch_content, phase_spec, max_tokens, model, project_rules, run_hints)`
   - **Integration**: Uses `ModelRouter`, `LlmService`, `LearnedRules`

2. **Anthropic Implementation**: `src/autopack/anthropic_clients.py`
   - **Class**: `AnthropicAuditorClient`
   - **Line**: 187
   - **Method**: `review_patch(patch_content, phase_spec, max_tokens, model, project_rules, run_hints)`
   - **Integration**: Claude-based code review with issue detection

3. **Dual Auditor** (Advanced): `src/autopack/dual_auditor.py`
   - **Class**: `DualAuditor`
   - **Purpose**: High-risk categories get reviewed by both OpenAI and Claude auditors
   - **Method**: `review_patch(...)` - Merges results from multiple auditors
   - **Features**:
     - Issue-based conflict resolution
     - Severity escalation (any "major" → effective_severity="major")
     - Automatic deduplication of duplicate issues
     - Disagreement tracking metrics

### API Schemas (Chunk D)

**File**: `src/autopack/builder_schemas.py`

Defines comprehensive Auditor request/result schemas:
- `AuditorRequest` - Request for auditor review with context
- `AuditorResult` - Complete auditor result with issues, recommendations
- `AuditorSuggestedPatch` - Minimal patch suggestions from auditor

---

## Quality Gate Integration

**File**: `src/autopack/quality_gate.py`

**Class**: `QualityGate`

**Purpose**: Thin quality enforcement layer for high-risk categories

**Key Features**:
- Integrates Auditor results with CI/coverage checks
- Risk-based gating: Strict for high-risk categories, lenient otherwise
- Uses `RiskScorer` for proactive risk assessment
- Returns `QualityReport` with quality levels: "ok" | "needs_review" | "blocked"

**High-Risk Categories** (strict enforcement):
- `external_feature_reuse`
- `security_auth_change`
- `schema_contract_change`

**Method**: `assess_phase(phase_id, phase_spec, auditor_result, ci_result, coverage_delta, patch_content, files_changed)`

**Integration Helper**: `integrate_with_auditor(auditor_result, quality_report)` - Merges quality gate results into auditor result

---

## Supporting Infrastructure

### 1. Model Router

**File**: `src/autopack/model_router.py`

- **Purpose**: Intelligent model selection based on task category and complexity
- **Integration**: Used by both Builder and Auditor clients
- **Features**: Budget tracking, quota management, learned model preferences

### 2. LLM Service

**File**: `src/autopack/llm_service.py`

- **Purpose**: Centralized LLM invocation with usage tracking
- **Integration**: All Builder/Auditor clients use this for actual API calls
- **Features**: Token tracking, cost calculation, logging

### 3. Learned Rules

**File**: `src/autopack/learned_rules.py`

- **Purpose**: Repository-specific rules learned from past runs
- **Integration**: Passed to both Builder and Auditor for context
- **Features**: Pattern matching, rule priority, category-specific rules

### 4. Usage Tracking

**File**: `src/autopack/usage_recorder.py`

- **Purpose**: Track and persist token usage, costs, model performance
- **Integration**: Automatic tracking through `LlmService`

---

## Current Wiring in Main Pipeline

The Builder and Auditor components are integrated into the main Autopack API:

**File**: `src/autopack/main.py`

### Builder Integration

**Endpoint**: `POST /runs/{run_id}/phases/{phase_id}/builder_result`
- **Line**: ~414
- **Purpose**: Accept Builder results after phase execution
- **Accepts**: `BuilderResult` schema
- **Actions**:
  - Updates phase status
  - Records token usage
  - Stores patch content
  - Creates suggested issues in database

### Auditor Integration

**Endpoint**: `POST /runs/{run_id}/phases/{phase_id}/auditor_request`
- **Line**: ~495
- **Purpose**: Request auditor review for a phase
- **Accepts**: `AuditorRequest` schema
- **Returns**: Stored request for async auditor processing

**Endpoint**: `POST /runs/{run_id}/phases/{phase_id}/auditor_result`
- **Line**: ~530
- **Purpose**: Accept Auditor results after review
- **Accepts**: `AuditorResult` schema
- **Actions**:
  - Updates phase quality labels
  - Records issues found
  - Updates phase state based on approval

---

## What's Missing (For Full End-to-End Execution)

While the Builder and Auditor **components** exist, they are not yet wired into an **autonomous execution loop**. Currently:

1. ✅ **Components exist**: `BuilderClient`, `AuditorClient` with multiple implementations
2. ✅ **API endpoints exist**: `/builder_result`, `/auditor_request`, `/auditor_result`
3. ❌ **Orchestration loop missing**: No code that:
   - Fetches next queued phase
   - Calls `BuilderClient.execute_phase()`
   - Applies resulting patch
   - Calls `AuditorClient.review_patch()`
   - Applies quality gating
   - Moves to next phase

This orchestration logic would typically live in:
- A background worker/daemon that polls for queued phases
- Or a script like `.autonomous_runs/file-organizer-app-v1/scripts/phase2_orchestrator.py` (project-specific)

---

## Recommended Next Steps

### Option A: Use Existing Components As-Is

**Recommended approach**: The existing architecture is clean and well-designed.

1. **No new files needed**: `builder_component.py` and `auditor_component.py` are redundant
2. **Direct usage**:
   ```python
   from src.autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient
   from src.autopack.anthropic_clients import AnthropicBuilderClient
   from src.autopack.dual_auditor import DualAuditor
   from src.autopack.quality_gate import QualityGate
   from src.autopack.model_router import ModelRouter
   from src.autopack.llm_service import LlmService

   # Initialize
   builder = OpenAIBuilderClient(api_key=..., model_router=...)
   primary_auditor = OpenAIAuditorClient(api_key=..., model_router=...)
   secondary_auditor = AnthropicBuilderClient(api_key=...)
   auditor = DualAuditor(primary_auditor, secondary_auditor)
   quality_gate = QualityGate(repo_root=Path("."))

   # Execute phase
   builder_result = builder.execute_phase(phase_spec={...})

   # Review phase
   auditor_result = auditor.review_patch(
       patch_content=builder_result.patch_content,
       phase_spec={...}
   )

   # Apply quality gate
   quality_report = quality_gate.assess_phase(
       phase_id="...",
       phase_spec={...},
       auditor_result=auditor_result.__dict__,
       ci_result={...},
       files_changed=[...]
   )
   ```

### Option B: Add Thin Facade Layer (If Desired)

If you want even simpler top-level API, create thin facades:

**`src/autopack/phase_executor.py`**: Combines Builder + Auditor + Quality Gate into single call

```python
class PhaseExecutor:
    """High-level phase execution combining Builder, Auditor, and Quality Gate"""

    def __init__(self, builder, auditor, quality_gate):
        self.builder = builder
        self.auditor = auditor
        self.quality_gate = quality_gate

    def execute_and_review(self, phase_spec, apply_patch=False):
        """Execute phase with builder, review with auditor, apply quality gate"""
        # Build
        builder_result = self.builder.execute_phase(phase_spec)

        # Review
        auditor_result = self.auditor.review_patch(
            builder_result.patch_content,
            phase_spec
        )

        # Quality gate
        quality_report = self.quality_gate.assess_phase(
            phase_spec=phase_spec,
            auditor_result=auditor_result.__dict__,
            ...
        )

        return {
            "builder": builder_result,
            "auditor": auditor_result,
            "quality": quality_report
        }
```

### Option C: Implement Autonomous Loop

Create orchestration script that:
1. Polls `/runs/{run_id}` for phases in `QUEUED` state
2. For each queued phase:
   - Execute with `BuilderClient`
   - Review with `AuditorClient`
   - Apply `QualityGate`
   - POST results back to Autopack API
   - Update phase state to `COMPLETE` or `FAILED`
3. Repeat until all phases complete

---

## Conclusion

**Status**: ✅ **Existing components fully satisfy requirements**

Autopack has mature, well-designed Builder and Auditor components that:
- Follow clean architecture (Protocol interfaces, multiple implementations)
- Integrate with existing infrastructure (ModelRouter, LlmService, LearnedRules)
- Support advanced features (Dual Auditor, Quality Gate, Risk Scoring)
- Have comprehensive API schemas (Chunk D)

**No new implementation needed** - just wire existing components into an orchestration loop for full autonomous execution.

---

**Next Action**: Implement orchestration loop or update project-specific scripts (like `phase2_orchestrator.py`) to use these existing components.


---

## AUTO_DOCUMENTATION

**Source**: [AUTO_DOCUMENTATION.md](C:\dev\Autopack\archive\superseded\AUTO_DOCUMENTATION.md)
**Last Modified**: 2025-11-28

# Auto-Documentation System

**Zero-token documentation updates using Python AST + git diff analysis**

## Overview

Autopack automatically keeps documentation in sync with code changes without using LLMs. The system has two modes:

1. **Quick Mode** (default): Fast endpoint count updates for git pre-commit hook
2. **Full Analysis Mode** (`--analyze`): Deep structural change detection for CI flow

## What Gets Detected

### Structural Changes (Full Analysis Only)

- **New Modules**: Python files added to `src/autopack/`
- **New Classes**: Classes defined in new modules (via AST parsing)
- **API Changes**: New endpoint groups (e.g., `/dashboard/*`)
- **Dependencies**: Changes to `requirements.txt` or `package.json`

### Statistics (Both Modes)

- API endpoint count in `main.py`
- Dashboard build status
- Documentation file count

## Usage

### Quick Mode (Pre-Commit Hook)

```bash
# Fast update (< 0.5 seconds)
python scripts/update_docs.py

# Preview changes
python scripts/update_docs.py --dry-run

# Check if updates needed
python scripts/update_docs.py --check
```

This runs automatically on every commit via `.git/hooks/pre-commit`.

### Full Analysis Mode (CI Flow)

```bash
# Full structural analysis (1-2 seconds)
python scripts/update_docs.py --analyze

# Preview what would be documented
python scripts/update_docs.py --analyze --dry-run

# Run via CI script
bash scripts/ci_update_docs.sh
```

Use this during CI flow to detect and document major structural changes.

## What Gets Updated

### README.md

- API endpoint count in technology stack section
- Validates dashboard section exists
- Validates architecture diagram includes new components

### CHANGELOG.md

When `--analyze` detects structural changes, creates a new entry:

```markdown
## [2025-11-25] - Structural Updates

### New Modules
- New module: llm_service (`src/autopack/llm_service.py`)
- New module: model_router (`src/autopack/model_router.py`)

### New Classes
- New classes: LlmService (`src/autopack/llm_service.py`)
- New classes: ModelRouter (`src/autopack/model_router.py`)

### API Changes
- Dashboard API endpoints added (`main.py::/dashboard/*`)
```

## Integration Points

### Git Pre-Commit Hook

Location: `.git/hooks/pre-commit`

```bash
if [ -f "scripts/update_docs.py" ]; then
    python scripts/update_docs.py --check

    if [ $? -ne 0 ]; then
        echo "⚠️  Documentation may need updating. Run: python scripts/update_docs.py"
        echo "Continuing with commit..."
    fi
fi
```

**Non-blocking**: Prints warning but allows commit to proceed.

### CI Flow Integration

Add to your CI probe script:

```bash
# After tests pass, update documentation
if [ $all_tests_passed ]; then
    bash scripts/ci_update_docs.sh

    # Commit documentation updates
    git add CHANGELOG.md README.md
    git commit -m "docs: auto-update from CI flow"
fi
```

## Technical Details

### AST Parsing

Uses Python's `ast` module to parse source code and extract:
- Class definitions (`ast.ClassDef`)
- Function definitions (`ast.FunctionDef`)
- Module-level constants

### Git Diff Analysis

Uses `git diff --name-status` to detect:
- New files (`A` status)
- Modified files (`M` status)
- Deleted files (`D` status)

Looks back 5 commits by default:
```python
git diff --name-status HEAD~5 HEAD
```

### Pattern Matching

Uses regex to detect:
- FastAPI endpoint decorators: `@app.(get|post|put|delete|patch)`
- Dependency declarations: Package names in `requirements.txt`

## Cost Analysis

- **Token usage**: 0 (uses only Python stdlib + git)
- **Execution time**:
  - Quick mode: < 0.5 seconds
  - Full analysis: 1-2 seconds
- **Dependencies**: None (uses `ast`, `re`, `subprocess`, `pathlib`)

## Examples

### Example 1: Quick Update

```bash
$ python scripts/update_docs.py
[*] Scanning codebase for documentation updates...
[Mode] Quick update (endpoint counts only)

[OK] Documentation is up to date!
```

### Example 2: Full Analysis with Changes

```bash
$ python scripts/update_docs.py --analyze
[*] Scanning codebase for documentation updates...
[Mode] Full structural analysis (detecting major changes)

[Status] Current State:
  API Endpoints: 22
  New Modules: 7
  Dashboard Built: YES
  Doc Files: 4

[*] Analyzing structural changes (AST + git diff)...

[Detected] 8 major structural changes:
  [MODULE] New module: llm_service
      Location: src/autopack/llm_service.py
  [CLASS] New classes: LlmService
      Location: src/autopack/llm_service.py
  [API] Dashboard API endpoints added
      Location: main.py::/dashboard/*

[OK] Updated CHANGELOG.md with 8 structural changes
[OK] All updates applied
```

### Example 3: Preview Mode

```bash
$ python scripts/update_docs.py --analyze --dry-run
[*] Scanning codebase for documentation updates...
[Mode] Full structural analysis (detecting major changes)

[Detected] 3 major structural changes:
  [MODULE] New module: feature_x
  [CLASS] New classes: FeatureX, FeatureXService
  [API] New /features/* endpoints

[DRY RUN] Would add to CHANGELOG.md:

## [2025-11-25] - Structural Updates

### New Modules
- New module: feature_x (`src/autopack/feature_x.py`)

[DRY RUN] No files modified
```

## Troubleshooting

### "Documentation may need updating" warning

**Cause**: Structural changes detected but not yet documented.

**Solution**: Run `python scripts/update_docs.py` to apply updates.

### No structural changes detected

**Cause**:
- Changes are within existing files (not new modules)
- Changes are in last 5 commits already documented
- Changes are in non-tracked directories

**Solution**: This is expected for minor updates. Only major structural changes trigger updates.

### Git command fails

**Cause**: Not in a git repository or git not installed.

**Solution**: Ensure you're in the Autopack root directory with `.git/` folder present.

## Future Enhancements

Potential additions (still token-free):

1. **Diff-based detection**: Detect significant function signature changes
2. **Import analysis**: Track new external library imports
3. **Test coverage**: Count test files per module
4. **Architecture validation**: Ensure layer boundaries are maintained
5. **Breaking change detection**: Detect removed public APIs

## Configuration

### Adjust lookback range

In `scripts/update_docs.py`:

```python
def detect_new_modules_since_commit(self, since_commit: str = "HEAD~5"):
    # Change HEAD~5 to HEAD~10 to look back 10 commits
```

### Customize module detection

In `scripts/update_docs.py`:

```python
if "src/autopack/" in file_path and not file_path.endswith("__init__.py"):
    # Add additional filters here
```

### Add new detection categories

Extend `StructuralChange` categories:

```python
class StructuralChange:
    def __init__(self, category: str, description: str, location: str):
        # Valid categories: "module", "class", "api", "dependency", "config", "test", "breaking"
        self.category = category
```

## Comparison to LLM-Based Approach

| Feature | Auto-Documentation | LLM Approach |
|---------|-------------------|--------------|
| Token cost | $0 | $0.01-0.10 per run |
| Speed | < 2 seconds | 5-30 seconds |
| Accuracy | Deterministic | 95%+ |
| Semantic understanding | No | Yes |
| Offline capable | Yes | No |
| False positives | Low | Medium |

**When to use each**:
- **Auto-Documentation**: Structural changes, statistics, CI flow
- **LLM Approach**: Semantic summaries, release notes, user-facing docs


---

## BUILD_PLAN_TASK_TRACKER

**Source**: [BUILD_PLAN_TASK_TRACKER.md](C:\dev\Autopack\archive\superseded\BUILD_PLAN_TASK_TRACKER.md)
**Last Modified**: 2025-11-28

# Build Plan: Task Tracker Application

**Project ID**: task-tracker-v1
**Build Date**: 2025-11-26
**Strategy**: Manual supervised build (first application)
**Goal**: Validate Phase 1b implementation with a complete 20-50 phase build

---

## Executive Summary

This is our **first production build** using Autopack Phase 1b. We're building a simple task tracker to validate:

1. **Model routing** (8 fine-grained categories)
2. **Budget warnings** (alert-based system)
3. **Context ranking** (JIT loading for 30-50% token savings)
4. **Risk scoring** (LOC delta, critical paths, test coverage)
5. **Learned rules** (accumulation across phases)
6. **Dual auditing** (security-critical categories only)

---

## Tech Stack

- **Backend**: FastAPI + PostgreSQL + SQLAlchemy + Alembic
- **Frontend**: React + Vite + TailwindCSS
- **Testing**: pytest + React Testing Library
- **Deployment**: Docker Compose (already configured)

---

## Build Tiers and Phases

### **Tier 1: Database and Backend Foundation** (8 phases)

#### Phase 1.1: Database Schema - Task Model
- **Category**: `schema_contract_change_additive`
- **Complexity**: medium
- **Description**: Create Task model with id, title, description, completed, created_at, updated_at
- **Acceptance Criteria**:
  - SQLAlchemy model defined in `src/autopack/models/task.py`
  - Alembic migration generated
  - Schema includes proper indexes (id primary key, created_at for sorting)
  - Type hints on all fields
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (schema change + 50 LOC)

#### Phase 1.2: Run Alembic Migration
- **Category**: `schema_contract_change_additive`
- **Complexity**: low
- **Description**: Apply migration to create tasks table
- **Acceptance Criteria**:
  - Migration applied successfully
  - `tasks` table exists in database
  - Schema matches model definition
- **Expected Model**: gpt-4o-mini (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~30 (destructive operation)

#### Phase 1.3: CRUD API Endpoints - Create Task
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: POST /api/tasks endpoint to create new tasks
- **Acceptance Criteria**:
  - Endpoint defined in `src/autopack/routers/tasks.py`
  - Pydantic request/response models
  - Input validation (title required, 1-200 chars)
  - Returns 201 with created task
  - Type hints on all functions
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~50 (critical path + 80 LOC)

#### Phase 1.4: CRUD API Endpoints - List Tasks
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: GET /api/tasks endpoint to list all tasks
- **Acceptance Criteria**:
  - Supports pagination (offset, limit query params)
  - Supports filtering by completed status
  - Sorted by created_at descending
  - Returns 200 with task array
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (critical path + 60 LOC)

#### Phase 1.5: CRUD API Endpoints - Update Task
- **Category**: `core_backend_high`
- **Complexity**: medium
- **Description**: PUT /api/tasks/{task_id} endpoint to update tasks
- **Acceptance Criteria**:
  - Supports partial updates (title, description, completed)
  - Returns 404 if task not found
  - Returns 200 with updated task
  - Updates updated_at timestamp
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~50 (critical path + 70 LOC)

#### Phase 1.6: CRUD API Endpoints - Delete Task
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: DELETE /api/tasks/{task_id} endpoint
- **Acceptance Criteria**:
  - Soft delete (sets deleted_at timestamp)
  - Returns 404 if task not found
  - Returns 204 on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (critical path + 30 LOC)

#### Phase 1.7: Backend Unit Tests - CRUD Operations
- **Category**: `tests`
- **Complexity**: medium
- **Description**: pytest tests for all CRUD endpoints
- **Acceptance Criteria**:
  - Test file: `tests/test_tasks_api.py`
  - Tests for create, list, update, delete
  - Tests for validation errors
  - Tests for 404 cases
  - Coverage >80% for tasks router
- **Expected Model**: gpt-4o-mini (builder - cheap_first), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~25 (tests + 150 LOC)

#### Phase 1.8: API Documentation - OpenAPI Spec
- **Category**: `docs`
- **Complexity**: low
- **Description**: Ensure FastAPI auto-generated docs are complete
- **Acceptance Criteria**:
  - All endpoints have docstrings
  - Request/response models documented
  - Example values provided
  - /docs endpoint renders correctly
- **Expected Model**: gpt-4o-mini (builder - cheap_first), gpt-4o-mini (auditor - cheap_first)
- **Risk Score**: ~15 (docs + 40 LOC)

---

### **Tier 2: Frontend Foundation** (7 phases)

#### Phase 2.1: Vite + React Setup
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Initialize Vite React app in `frontend/` directory
- **Acceptance Criteria**:
  - Vite config with HMR
  - TailwindCSS configured
  - ESLint + Prettier setup
  - Dev server runs on port 5173
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~35 (new frontend + 100 LOC)

#### Phase 2.2: API Client - Fetch Wrapper
- **Category**: `external_feature_reuse_remote`
- **Complexity**: low
- **Description**: Create typed API client for backend
- **Acceptance Criteria**:
  - File: `frontend/src/api/client.ts`
  - TypeScript types for Task
  - Fetch wrapper with error handling
  - Base URL from environment variable
- **Expected Model**: gpt-5 (builder - best_first for external integration), claude-opus-4-5 (auditor - best_first)
- **Risk Score**: ~55 (external dependency + 80 LOC)

#### Phase 2.3: Task List Component
- **Category**: `core_frontend_medium`
- **Complexity**: medium
- **Description**: React component to display task list
- **Acceptance Criteria**:
  - File: `frontend/src/components/TaskList.tsx`
  - Fetches tasks on mount
  - Displays loading state
  - Displays error state
  - Renders task cards with title, description, status
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (UI component + 120 LOC)

#### Phase 2.4: Task Create Form
- **Category**: `core_frontend_medium`
- **Complexity**: medium
- **Description**: Form component to create new tasks
- **Acceptance Criteria**:
  - File: `frontend/src/components/TaskForm.tsx`
  - Controlled inputs for title, description
  - Client-side validation
  - Calls POST /api/tasks
  - Clears form on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~45 (form validation + 100 LOC)

#### Phase 2.5: Task Update - Toggle Complete
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Checkbox to toggle task completion
- **Acceptance Criteria**:
  - Checkbox in TaskList component
  - Calls PUT /api/tasks/{id} on change
  - Optimistic UI update
  - Reverts on error
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (state management + 60 LOC)

#### Phase 2.6: Task Delete Button
- **Category**: `core_frontend_medium`
- **Complexity**: low
- **Description**: Delete button for each task
- **Acceptance Criteria**:
  - Confirmation dialog
  - Calls DELETE /api/tasks/{id}
  - Removes from UI on success
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~35 (UI action + 50 LOC)

#### Phase 2.7: Frontend Tests - Components
- **Category**: `tests`
- **Complexity**: medium
- **Description**: React Testing Library tests for components
- **Acceptance Criteria**:
  - Tests for TaskList, TaskForm
  - Mocked API calls
  - Tests for loading/error states
  - Coverage >70% for components
- **Expected Model**: gpt-4o-mini (builder - cheap_first), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~25 (tests + 130 LOC)

---

### **Tier 3: Integration and Polish** (6 phases)

#### Phase 3.1: CORS Configuration
- **Category**: `security_auth_change`
- **Complexity**: low
- **Description**: Configure CORS for frontend-backend communication
- **Acceptance Criteria**:
  - FastAPI CORS middleware
  - Allow origins: http://localhost:5173
  - Allow credentials: true
  - Allow methods: GET, POST, PUT, DELETE
- **Expected Model**: gpt-5 (builder - best_first for security), claude-opus-4-5 (auditor - dual auditing)
- **Risk Score**: ~65 (security config + 30 LOC)

#### Phase 3.2: Environment Variables
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: Externalize configuration to .env
- **Acceptance Criteria**:
  - Backend: DATABASE_URL, CORS_ORIGINS
  - Frontend: VITE_API_URL
  - Example .env.example files
  - pydantic-settings for backend config
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~30 (config + 40 LOC)

#### Phase 3.3: Error Handling - 500 Responses
- **Category**: `core_backend_high`
- **Complexity**: low
- **Description**: Global error handler for uncaught exceptions
- **Acceptance Criteria**:
  - FastAPI exception handler
  - Logs errors to console
  - Returns 500 with safe error message
  - Doesn't leak stack traces
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~40 (error handling + 50 LOC)

#### Phase 3.4: Integration Tests - E2E Scenarios
- **Category**: `tests`
- **Complexity**: high
- **Description**: End-to-end tests for full workflows
- **Acceptance Criteria**:
  - Test file: `tests/test_integration.py`
  - Create → List → Update → Delete flow
  - Tests with real database (test container)
  - Cleanup between tests
- **Expected Model**: gpt-4o (builder), claude-sonnet-4-5 (auditor)
- **Risk Score**: ~55 (complex tests + 180 LOC)

#### Phase 3.5: Docker Compose - Frontend Service
- **Category**: `external_feature_reuse_remote`
- **Complexity**: low
- **Description**: Add frontend service to docker-compose.yml
- **Acceptance Criteria**:
  - Service name: task-tracker-frontend
  - Builds from frontend/Dockerfile
  - Exposed on port 5173
  - Depends on backend API
- **Expected Model**: gpt-5 (builder - best_first for docker integration), claude-opus-4-5 (auditor)
- **Risk Score**: ~50 (docker config + 40 LOC)

#### Phase 3.6: README and Deployment Docs
- **Category**: `docs`
- **Complexity**: low
- **Description**: Complete README for task tracker
- **Acceptance Criteria**:
  - Installation steps
  - Running with docker-compose
  - API endpoints documentation
  - Frontend usage guide
- **Expected Model**: gpt-4o-mini (builder - cheap_first), gpt-4o-mini (auditor - cheap_first)
- **Risk Score**: ~15 (docs + 80 LOC)

---

## Summary Stats (Estimated)

- **Total Phases**: 21
- **Total LOC**: ~1,700 (estimated)
- **Category Distribution**:
  - schema_contract_change_additive: 2 (9.5%)
  - core_backend_high: 6 (28.6%)
  - core_frontend_medium: 5 (23.8%)
  - external_feature_reuse_remote: 2 (9.5%)
  - security_auth_change: 1 (4.8%)
  - tests: 4 (19.0%)
  - docs: 2 (9.5%)
  - general: 0 (0%)

- **Strategy Distribution**:
  - best_first: 4 phases (security + external integration)
  - progressive: 14 phases (core backend/frontend)
  - cheap_first: 3 phases (docs + tests)

- **Token Budget Estimate** (rough):
  - Best-first phases: 4 × 15k = 60k tokens
  - Progressive phases: 14 × 10k = 140k tokens
  - Cheap-first phases: 3 × 5k = 15k tokens
  - **Total**: ~215k tokens (well under 50M quota)

- **Risk Score Distribution**:
  - High (>60): 2 phases (CORS, Docker)
  - Medium (40-60): 11 phases
  - Low (<40): 8 phases

---

## Manual Tracking Plan

We'll track these metrics manually during the build:

### 1. Category Accuracy
- Does `schema_contract_change_additive` correctly trigger for migrations?
- Does `security_auth_change` correctly trigger dual auditing for CORS?
- Does `external_feature_reuse_remote` correctly escalate to best_first for Docker/API client?

### 2. Escalation Frequency
- How often does progressive strategy escalate from gpt-4o to gpt-5?
- After how many failed attempts?
- Were escalations necessary?

### 3. Token Savings (Context Ranking)
- Estimate tokens without context ranking (all files loaded)
- Actual tokens used (with JIT loading)
- Calculate % savings

### 4. Risk Scorer Calibration
- Which phases had high risk scores?
- Did high-risk phases actually have more issues?
- Correlation between risk score and audit failures?

### 5. Budget Warnings
- Did we hit any 80% soft limit warnings?
- Were warnings helpful?
- Did alert-based system work better than hard blocks?

### 6. Learned Rules Effectiveness
- How many rules were recorded?
- Were rules applied in later phases?
- Did rules reduce audit failures over time?

---

## Execution Approach

Since this is our first build, we'll use a **manual supervised approach**:

1. **Execute phases sequentially** (one at a time)
2. **Review each Builder output** before auditing
3. **Manually call Auditor** after each Builder output
4. **Record observations** in manual tracking file
5. **Update todo list** as we complete phases
6. **Commit changes** after each successful phase

This approach lets us observe the system in action and validate Phase 1b implementation.

---

## Success Criteria

This build is successful if:

1. ✅ All 21 phases complete with working code
2. ✅ No quota exhaustion (under 50M OpenAI tokens)
3. ✅ At least 5 learned rules recorded
4. ✅ Security phases use dual auditing (CORS phase)
5. ✅ Context ranking works (no file-not-found errors)
6. ✅ Risk scorer provides useful signals
7. ✅ Manual tracking reveals actionable insights for tuning

---

## Next Steps

1. Create `.autonomous_runs/task-tracker-v1/` directory
2. Create `MANUAL_TRACKING.md` file
3. Execute Phase 1.1 (Database Schema)
4. Record observations after each phase
5. Review data after 10 phases (mid-point check)
6. Complete all 21 phases
7. Analyze final results and decide on Phase 2 implementation

---

**Ready to Start?** Let's build! 🚀


---

