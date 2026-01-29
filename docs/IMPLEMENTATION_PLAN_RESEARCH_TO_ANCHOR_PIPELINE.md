# Implementation Plan: Research → Intention Anchor Pipeline (Project Bootstrap)

**Audience**: Implementation cursor / engineering agent
**Status**: Plan only (do not implement in this doc)
**Aligned to README "ideal state"**: Transform rough project ideas into production-ready applications autonomously

---

## Executive Summary

This plan bridges the gap between Autopack's existing research infrastructure and the IntentionAnchorV2 system. Currently, research capabilities exist but are isolated; this plan wires them into a cohesive pipeline that can bootstrap new projects from rough ideas.

**Goal**: `rough_idea.md` → Research → Questions → IntentionAnchorV2 → Gap Scanner → Plan Proposer → Build

---

## Current State Analysis

### What Exists (✅)

| Component | Location | Status |
|-----------|----------|--------|
| ResearchOrchestrator | `src/autopack/research/orchestrator.py` | Session management works |
| IntentClarificationAgent | `src/autopack/research/intent_clarification.py` | Extracts concepts, generates questions |
| AnalysisAgent | `src/autopack/research/agents/analysis_agent.py` | Aggregates findings, identifies gaps |
| WebDiscovery | `src/autopack/research/discovery/` | Google search integration |
| GitHubDiscovery | `src/autopack/research/discovery/` | Repository/code search |
| RedditDiscovery | `src/autopack/research/discovery/` | Community sentiment |
| MarketAttractiveness Framework | `src/autopack/research/frameworks/` | Market evaluation |
| CompetitiveIntensity Framework | `src/autopack/research/frameworks/` | Competitor analysis |
| ProductFeasibility Framework | `src/autopack/research/frameworks/` | Technical feasibility |
| IntentionAnchorV2 | `src/autopack/intention_anchor/v2.py` | 8 pivot intentions defined |
| `validate_pivot_completeness()` | `src/autopack/intention_anchor/v2.py:358` | Generates clarifying questions |
| Research API | `src/autopack/research/api/router.py` | **Quarantined (disabled)** |

### What's Missing (❌)

| Gap | Impact |
|-----|--------|
| **IdeaParser** | Cannot extract distinct projects from rough idea documents |
| **ResearchToAnchorMapper** | Research findings don't auto-populate intention anchors |
| **TechStackProposer** | No mechanism to propose APIs/MCPs/frameworks with pros/cons |
| **Interactive Q&A Loop** | `validate_pivot_completeness()` exists but not wired to user interaction |
| **Research API Activation** | API is quarantined; cannot bootstrap externally |
| **Project Bootstrap Command** | No `autopack bootstrap` CLI entry point |

---

## Direction (Explicit, No Ambiguity)

1. **Research informs, humans approve** — Research proposes, never auto-creates intentions without approval
2. **Tech stack proposals are advisory** — Present options with pros/cons; human selects
3. **Questions are targeted** — Max 8 clarifying questions per project (per existing contract)
4. **Default-deny for high-risk projects** — Financial, trading, and external API projects require explicit approval
5. **Research API remains gated** — Enable for bootstrap workflow only, not general-purpose

---

## Key Concepts: Research → Anchor Mapping

### Mapping Research Findings to 8 Pivot Intentions

| Research Output | Maps To Pivot | How |
|-----------------|---------------|-----|
| Market size, trends, demand signals | **NorthStar** | Desired outcomes, success metrics |
| Competitor analysis, differentiation | **NorthStar** | Non-goals (what not to build) |
| API rate limits, ToS restrictions | **SafetyRisk** | Never-allow operations |
| Legal/regulatory findings | **SafetyRisk** | Approval requirements |
| Technical feasibility, dependencies | **EvidenceVerification** | Hard blocks, required checks |
| Platform policies (Etsy, YouTube, etc.) | **ScopeBoundaries** | Network allowlist, protected paths |
| Cost estimates (APIs, hosting, tokens) | **BudgetCost** | Token/time caps, cost escalation |
| Data retention requirements | **MemoryContinuity** | What persists, retention rules |
| Approval workflows needed | **GovernanceReview** | Default-deny rules, approval channels |
| Parallelism feasibility | **ParallelismIsolation** | Isolation model requirements |

### Tech Stack Proposal Format

```yaml
tech_stack_proposal:
  project_type: "etsy_automation"

  options:
    - name: "Option A: Python + Selenium + Etsy API"
      pros:
        - "Direct Etsy API access for official operations"
        - "Well-documented Python ecosystem"
        - "Low cost (self-hosted)"
      cons:
        - "Etsy API has rate limits (10,000 requests/day)"
        - "Selenium is fragile for long-term automation"
        - "Requires maintaining browser drivers"
      risk_level: "medium"
      estimated_cost: "$20-50/month (hosting)"

    - name: "Option B: Node.js + Puppeteer + Third-party Integration"
      pros:
        - "Faster execution than Selenium"
        - "Better async handling"
        - "More stable for headless operations"
      cons:
        - "Third-party integrations may violate ToS"
        - "Higher memory usage"
        - "Less mature AI/ML ecosystem"
      risk_level: "medium-high"
      estimated_cost: "$30-80/month (hosting)"

  recommended: "Option A"
  recommendation_rationale: "Official API compliance reduces legal risk; Python ecosystem better for AI image processing"

  mcp_integrations:
    - name: "etsy-mcp"
      purpose: "Etsy API operations"
      availability: "community"

    - name: "image-processing-mcp"
      purpose: "Background removal, image optimization"
      availability: "to be built"
```

---

## Deliverable Set

### Deliverable 1: IdeaParser (Extract Projects from Documents)

**Purpose**: Parse rough idea documents and extract distinct project specifications.

**Location**: `src/autopack/research/idea_parser.py`

**Interface**:
```python
@dataclass
class ParsedIdea:
    id: str
    title: str
    description: str
    raw_requirements: List[str]
    detected_project_type: str  # e-commerce, trading, content, automation
    risk_profile: str  # low, medium, high, critical
    dependencies: List[str]  # mentions of other projects or prerequisites

class IdeaParser:
    def parse_document(self, file_path: str) -> List[ParsedIdea]:
        """Extract distinct project ideas from a markdown document."""

    def classify_project_type(self, idea: ParsedIdea) -> str:
        """Classify project into category for research routing."""
```

**Design Rules**:
- Deterministic parsing (regex + heuristics first, LLM fallback only for ambiguous cases)
- Each numbered section becomes a distinct project
- Risk profile derived from keywords (financial, trading, API, scraping → higher risk)

---

### Deliverable 2: ResearchToAnchorMapper (Core Pipeline)

**Purpose**: Map research findings to IntentionAnchorV2 structure.

**Location**: `src/autopack/research/anchor_mapper.py`

**Interface**:
```python
@dataclass
class ResearchFindings:
    market_analysis: MarketAnalysisReport
    competitive_analysis: CompetitiveAnalysisReport
    technical_feasibility: TechnicalFeasibilityReport
    legal_compliance: LegalComplianceReport
    cost_estimates: CostEstimateReport

@dataclass
class AnchorDraft:
    anchor: IntentionAnchorV2
    confidence_scores: Dict[str, float]  # per pivot
    missing_pivots: List[str]
    clarifying_questions: List[str]
    tech_stack_proposal: TechStackProposal

class ResearchToAnchorMapper:
    def map_findings_to_anchor(
        self,
        idea: ParsedIdea,
        findings: ResearchFindings
    ) -> AnchorDraft:
        """Map research findings to draft IntentionAnchorV2."""

    def generate_clarifying_questions(
        self,
        draft: AnchorDraft
    ) -> List[ClarifyingQuestion]:
        """Generate targeted questions for missing/low-confidence pivots."""

    def apply_user_answers(
        self,
        draft: AnchorDraft,
        answers: Dict[str, str]
    ) -> IntentionAnchorV2:
        """Apply user answers to finalize anchor."""
```

**Design Rules**:
- Confidence threshold: 0.7 (below → requires clarification)
- Max 8 clarifying questions (per existing contract)
- Never auto-populate SafetyRisk.never_allow without explicit confirmation

---

### Deliverable 3: TechStackProposer (Advisory Recommendations)

**Purpose**: Propose technology choices with pros/cons analysis.

**Location**: `src/autopack/research/tech_stack_proposer.py`

**Interface**:
```python
@dataclass
class TechStackOption:
    name: str
    components: List[str]  # frameworks, libraries, APIs
    pros: List[str]
    cons: List[str]
    risk_level: str
    estimated_monthly_cost: str
    mcp_integrations: List[MCPIntegration]

@dataclass
class TechStackProposal:
    project_type: str
    options: List[TechStackOption]
    recommended: str
    recommendation_rationale: str

class TechStackProposer:
    def propose_stack(
        self,
        idea: ParsedIdea,
        findings: ResearchFindings
    ) -> TechStackProposal:
        """Propose tech stack options based on research."""

    def evaluate_mcp_availability(
        self,
        required_capabilities: List[str]
    ) -> List[MCPIntegration]:
        """Check which MCPs exist vs. need to be built."""
```

**Design Rules**:
- Always provide at least 2 options
- Include cost estimates (hosting, API fees, token usage)
- Flag ToS/legal risks prominently
- Check MCP registry for existing integrations

---

### Deliverable 4: Interactive Q&A Controller

**Purpose**: Wire `validate_pivot_completeness()` to interactive user flow.

**Location**: `src/autopack/research/qa_controller.py`

**Interface**:
```python
@dataclass
class ClarifyingQuestion:
    pivot_type: str  # which pivot this clarifies
    question: str
    options: Optional[List[str]]  # predefined options if applicable
    default: Optional[str]
    importance: str  # critical, important, optional

class QAController:
    def collect_answers_cli(
        self,
        questions: List[ClarifyingQuestion]
    ) -> Dict[str, str]:
        """Interactive CLI Q&A session."""

    def collect_answers_file(
        self,
        questions: List[ClarifyingQuestion],
        answers_file: str
    ) -> Dict[str, str]:
        """Load answers from YAML file (for automation)."""

    def generate_defaults(
        self,
        questions: List[ClarifyingQuestion],
        project_type: str
    ) -> Dict[str, str]:
        """Generate sensible defaults based on project type."""
```

**Design Rules**:
- Critical questions block progress until answered
- Important questions have defaults but prompt for review
- Optional questions auto-default if not answered within timeout

---

### Deliverable 5: Research API Un-quarantine (Gated)

**Purpose**: Enable Research API for bootstrap workflow.

**Location**: Modify `src/autopack/research/api/router.py`

**Changes**:
```python
# Current (quarantined):
RESEARCH_API_ENABLED = os.getenv("RESEARCH_API_ENABLED", "false").lower() == "true"

# New (gated by mode):
RESEARCH_API_MODE = os.getenv("RESEARCH_API_MODE", "disabled")
# Options: "disabled", "bootstrap_only", "full"

# Bootstrap mode only allows:
# - POST /research/bootstrap (new endpoint)
# - GET /research/bootstrap/{id}/status
# - GET /research/bootstrap/{id}/draft_anchor

# Full mode (dev only) allows all existing endpoints
```

**Design Rules**:
- Production default: "disabled"
- Bootstrap mode: limited to project initialization workflow
- Full mode: dev/local only

---

### Deliverable 6: Bootstrap CLI Command

**Purpose**: Single command to start project from idea.

**Location**: `src/autopack/cli/commands/bootstrap.py`

**Interface**:
```bash
# Basic usage
autopack bootstrap --idea "Automated Etsy image upload with AI generation"

# From file
autopack bootstrap --idea-file /path/to/lucrative_project_ideas.md --project 1

# With pre-answers
autopack bootstrap --idea "..." --answers-file /path/to/answers.yaml

# Skip research (use cached/provided)
autopack bootstrap --idea "..." --skip-research --research-file /path/to/research.json

# Full autonomous (use defaults, no prompts)
autopack bootstrap --idea "..." --autonomous --risk-tolerance medium
```

**Workflow**:
```
1. Parse idea → ParsedIdea
2. Classify risk profile
3. Execute research phase:
   - Market analysis
   - Competitive analysis
   - Technical feasibility
   - Legal/policy compliance
4. Map findings → AnchorDraft
5. Propose tech stack
6. Generate clarifying questions
7. Collect answers (CLI/file/defaults)
8. Finalize IntentionAnchorV2
9. Create project directory structure
10. Write READY_FOR_BUILD marker
```

---

## Phase Plan (Implementation Steps)

### Phase 0 — IdeaParser (Foundation)

**Goal**: Parse rough idea documents reliably.

**Work**:
- Create `src/autopack/research/idea_parser.py`
- Add regex patterns for common idea formats (numbered lists, headers, bullet points)
- Add project type classification heuristics
- Add risk profile detection

**Acceptance Criteria**:
- Can parse `lucrative_project_ideas.md` into 8+ distinct projects
- Each project has title, description, raw requirements
- Risk profiles assigned correctly (trading → high, content → medium)

**Tests**:
- `tests/research/test_idea_parser.py`

---

### Phase 1 — Research Orchestration Enhancement

**Goal**: Extend ResearchOrchestrator for project bootstrap workflow.

**Work**:
- Add `start_bootstrap_session()` method
- Add research phase routing by project type
- Add parallel research execution for independent phases
- Add research caching (avoid redundant queries)

**Acceptance Criteria**:
- Single session can coordinate market + competitive + technical research
- Results cached for 24 hours
- Parallel execution reduces total time by 50%

**Tests**:
- `tests/research/test_bootstrap_orchestration.py`

---

### Phase 2 — ResearchToAnchorMapper

**Goal**: Map research findings to anchor structure.

**Work**:
- Create `src/autopack/research/anchor_mapper.py`
- Implement mapping rules (see table above)
- Add confidence scoring per pivot
- Add missing pivot detection
- Integrate with `validate_pivot_completeness()`

**Acceptance Criteria**:
- Research findings map to correct pivots
- Low-confidence pivots generate questions
- SafetyRisk never auto-populated without confirmation

**Tests**:
- `tests/research/test_anchor_mapper.py`
- `tests/research/test_anchor_mapper_safety.py` (security-focused)

---

### Phase 3 — TechStackProposer

**Goal**: Propose technology choices with analysis.

**Work**:
- Create `src/autopack/research/tech_stack_proposer.py`
- Add project type → stack templates mapping
- Add MCP registry integration
- Add cost estimation logic

**Acceptance Criteria**:
- Each project type has at least 2 stack options
- Cost estimates within 50% accuracy
- MCP availability correctly detected

**Tests**:
- `tests/research/test_tech_stack_proposer.py`

---

### Phase 4 — Interactive Q&A Controller

**Goal**: Wire clarifying questions to user interaction.

**Work**:
- Create `src/autopack/research/qa_controller.py`
- Implement CLI Q&A (with rich/prompt_toolkit)
- Implement file-based answers
- Implement default generation

**Acceptance Criteria**:
- CLI Q&A works interactively
- File-based answers work for automation
- Defaults are sensible per project type

**Tests**:
- `tests/research/test_qa_controller.py`

---

### Phase 5 — Bootstrap CLI and API

**Goal**: Unified entry point for project bootstrap.

**Work**:
- Create `src/autopack/cli/commands/bootstrap.py`
- Un-quarantine Research API (gated mode)
- Add bootstrap-specific endpoints
- Integrate all components into pipeline

**Acceptance Criteria**:
- `autopack bootstrap --idea "..."` works end-to-end
- Creates project directory with valid IntentionAnchorV2
- Writes READY_FOR_BUILD marker

**Tests**:
- `tests/cli/test_bootstrap_command.py`
- `tests/integration/test_bootstrap_pipeline.py`

---

### Phase 6 — Integration with Existing Pipeline

**Goal**: Connect bootstrap output to Gap Scanner → Plan Proposer → Execution.

**Work**:
- Ensure IntentionAnchorV2 from bootstrap loads correctly
- Add automatic Gap Scanner trigger after bootstrap
- Add automatic Plan Proposer trigger after gap scan
- Add approval gate before execution

**Acceptance Criteria**:
- Full pipeline: idea → research → anchor → gaps → plan → (approval) → build
- Human approval required before first build of any project
- Subsequent builds can be auto-approved per governance rules

**Tests**:
- `tests/integration/test_full_bootstrap_pipeline.py`

---

## Skeleton Structure (Files to Create/Modify)

### New Files
```
src/autopack/research/idea_parser.py
src/autopack/research/anchor_mapper.py
src/autopack/research/tech_stack_proposer.py
src/autopack/research/qa_controller.py
src/autopack/cli/commands/bootstrap.py
docs/schemas/tech_stack_proposal.schema.json
docs/schemas/parsed_idea.schema.json
tests/research/test_idea_parser.py
tests/research/test_anchor_mapper.py
tests/research/test_tech_stack_proposer.py
tests/research/test_qa_controller.py
tests/cli/test_bootstrap_command.py
tests/integration/test_bootstrap_pipeline.py
tests/integration/test_full_bootstrap_pipeline.py
```

### Modified Files
```
src/autopack/research/orchestrator.py (add bootstrap session)
src/autopack/research/api/router.py (un-quarantine with gating)
src/autopack/intention_anchor/v2.py (add from_research_findings factory)
src/autopack/cli/main.py (register bootstrap command)
```

---

## Mechanical Policies (Must Be Enforced)

1. **No auto-execution of first build** — Always require human approval for first build of new project
2. **Research caching** — Cache research results for 24 hours to avoid redundant API calls
3. **Cost tracking** — Record all API costs (search, LLM tokens) in telemetry
4. **Audit trail** — Every anchor must trace back to research session ID
5. **Sensitive data filtering** — Strip API keys, tokens from all research artifacts
6. **Rate limiting** — Respect all external API rate limits (Google, GitHub, Reddit)

---

## Known Ambiguities (Resolved Here)

1. **Can Autopack auto-select tech stack?**
   **No.** It proposes options; human selects.

2. **Can Autopack skip research for known project types?**
   **Yes, if cached** — Research results cached for 24 hours. Can also use `--skip-research` with provided research file.

3. **What if research finds legal/ToS blockers?**
   **Block and report.** Flag as critical SafetyRisk issue; require explicit acknowledgment to proceed.

4. **Can Autopack create multiple projects in parallel?**
   **Yes.** Use separate bootstrap sessions; parallelism rules apply per existing contracts.

---

## Validation Commands

```bash
# Unit tests
pytest -q tests/research/test_idea_parser.py
pytest -q tests/research/test_anchor_mapper.py
pytest -q tests/research/test_tech_stack_proposer.py

# Integration tests
pytest -q tests/integration/test_bootstrap_pipeline.py

# End-to-end test
autopack bootstrap --idea "Test project" --autonomous --dry-run
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Time from idea to buildable anchor | < 10 minutes (with cached research) |
| Research coverage per project | 100% of required frameworks executed |
| Question reduction via research | 50% fewer questions than without research |
| First-build approval rate | 100% (all first builds require approval) |
| Anchor completeness score | > 0.8 for all pivots |
