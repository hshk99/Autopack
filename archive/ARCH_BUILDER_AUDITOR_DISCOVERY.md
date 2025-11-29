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
