# Research Analysis Framework Architecture

## Overview

The Research Analysis Framework is a comprehensive system for analyzing, evaluating, and continuously improving research outcomes in the Autopack project. It integrates multiple specialized analyzers to provide cost-effectiveness analysis, state tracking, adaptive research triggering, and build-vs-buy decision support.

**Key Components:**
- **CostEffectivenessAnalyzer**: Aggregates component decisions and projects total cost of ownership
- **ResearchStateTracker**: Tracks research progress, identifies gaps, and enables resumable sessions
- **FollowupResearchTrigger**: Analyzes findings to detect gaps and trigger automated follow-up research
- **BuildVsBuyAnalyzer**: Evaluates build vs. buy decisions for project components

---

## Architecture Overview

### Component Relationships

```
Research Pipeline
    ↓
[Analysis Results] → ResearchStateTracker ← [State Recovery/Checkpoints]
    ↓
[Gaps Detected] → FollowupResearchTrigger → [Research Callbacks]
    ↓
[Build-vs-Buy Data] → BuildVsBuyAnalyzer → [Component Decisions]
    ↓
[Component Costs] → CostEffectivenessAnalyzer → [Total Cost Projection]
    ↓
[Project Brief] with Budget, Risk Assessment, and Recommendations
```

### Data Flow

1. **Research Gathering**: Raw research data flows from research agents
2. **State Tracking**: Progress and completeness tracked in ResearchStateTracker
3. **Gap Detection**: Gaps identified and prioritized
4. **Trigger Analysis**: FollowupResearchTrigger analyzes findings for missing information
5. **Component Evaluation**: BuildVsBuyAnalyzer evaluates make/buy/integrate decisions
6. **Cost Analysis**: CostEffectivenessAnalyzer projects long-term costs
7. **Deliverable**: Complete project brief with business and technical recommendations

---

## Component Details

### 1. ResearchStateTracker

**Purpose**: Tracks research progress, identifies gaps, and enables resumable research sessions.

**Location**: `src/autopack/research/analysis/research_state.py`

#### Key Classes

**ResearchState** - Main state container
- `project_id`: Unique project identifier
- `coverage`: Coverage metrics by category
- `completed_queries`: Record of executed research queries
- `discovered_sources`: Indexed sources for deduplication
- `identified_gaps`: Research gaps requiring attention
- `entities_researched`: Entities analyzed so far
- `research_depth`: Depth level (shallow/medium/deep) by topic

**ResearchGap** - An identified gap
```python
@dataclass
class ResearchGap:
    gap_id: str              # Unique identifier
    gap_type: GapType        # coverage, entity, depth, recency, validation
    category: str            # Domain category
    description: str         # Human-readable description
    priority: GapPriority    # critical, high, medium, low
    suggested_queries: List[str]  # Recommended research queries
    status: str              # pending, addressed
```

**GapType Enumeration**
- `COVERAGE`: Insufficient research in a domain
- `ENTITY`: Specific entities not yet researched
- `DEPTH`: Shallow coverage needing deeper analysis
- `RECENCY`: Outdated information requiring refresh
- `VALIDATION`: Claims requiring verification

#### Edge Case Handling

The ResearchStateTracker includes robust recovery mechanisms:

**Checkpoints**: Create savepoints at research phase boundaries
```python
checkpoint = tracker.create_checkpoint(phase="market_analysis")
# Later, recover from interruption
recovered, checkpoint = tracker.handle_interrupted_research(project_id)
```

**Partial Results**: Store and process incomplete research
```python
tracker.handle_partial_results(
    phase="competitive_analysis",
    results={"competitors": ["Competitor A", "Competitor B"]}
)
```

**Async Failures**: Track and recover from failed tasks
```python
tracker.handle_async_failure(
    task_id="task_001",
    error="API timeout",
    fallback_action="retry with different strategy"
)
```

**State Validation**: Detect and repair corruptions
```python
errors = tracker.validate_state_consistency()
if errors:
    repair_result = tracker.repair_state()
```

#### Usage Example

```python
from pathlib import Path
from autopack.research.analysis.research_state import (
    ResearchStateTracker, ResearchRequirements, ResearchDepth
)

# Initialize tracker
requirements = ResearchRequirements(
    min_coverage={
        "market_research": 70,
        "competitive_analysis": 70,
        "technical_feasibility": 60,
        "legal_policy": 80,
    }
)
tracker = ResearchStateTracker(Path("."), requirements)

# Load or create state
state = tracker.load_or_create_state("project-123")

# Track research progress
tracker.update_coverage("market_research", 45.0)
tracker.record_completed_query(
    query="market size projections 2024",
    agent="market-research-agent",
    sources_found=3,
    quality_score=0.8,
    findings={"market_size": "$50B", "growth": "15% CAGR"}
)

# Detect gaps
gaps = tracker.detect_gaps()
for gap in gaps:
    print(f"Gap {gap.gap_id}: {gap.description}")
    print(f"Suggested queries: {gap.suggested_queries}")

# Create checkpoint for recovery
checkpoint = tracker.create_checkpoint(phase="market_research")

# Save state
tracker.save_state()
```

---

### 2. FollowupResearchTrigger

**Purpose**: Analyzes research findings to identify gaps and trigger automated follow-up research with callback execution.

**Location**: `src/autopack/research/analysis/followup_trigger.py`

#### Key Classes

**FollowupTrigger** - A research trigger
```python
@dataclass
class FollowupTrigger:
    trigger_id: str              # Unique ID
    trigger_type: TriggerType    # uncertainty, gap, depth, validation, emerging
    priority: TriggerPriority    # critical, high, medium, low
    reason: str                  # Why this trigger exists
    source_finding: str          # What finding triggered it
    research_plan: ResearchPlan  # How to address it
    callback_results: List[CallbackResult]  # Execution results
```

**TriggerType Enumeration**
- `UNCERTAINTY`: Low confidence findings requiring verification
- `GAP`: Missing information in research
- `DEPTH`: Topics requiring deeper investigation
- `VALIDATION`: Claims needing primary source verification
- `EMERGING`: New relevant topics discovered

**TriggerAnalysisResult** - Analysis output
```python
@dataclass
class TriggerAnalysisResult:
    triggers_detected: int              # Total triggers found
    triggers_selected: int              # Selected for execution
    trigger_summary: Dict[str, int]     # Count by trigger type
    selected_triggers: List[FollowupTrigger]  # Selected triggers
    should_research: bool               # Whether to perform follow-up
    execution_plan: Dict[str, Any]      # Parallel execution plan
    execution_result: Optional[TriggerExecutionResult]  # Results from callbacks
```

#### Callback Execution (IMP-HIGH-005)

The framework supports mid-execution research triggering through callbacks:

**Register Callbacks**:
```python
def handle_research(trigger: FollowupTrigger) -> Optional[Dict]:
    # Perform research based on trigger.research_plan
    queries = trigger.research_plan.queries
    agent = trigger.research_plan.target_agent
    # Execute research and return findings
    return {"findings": [...], "confidence": 0.8}

trigger_analyzer = FollowupResearchTrigger()
trigger_analyzer.register_callback(handle_research)
```

**Execute Callbacks**:
```python
# Analyze findings
result = trigger_analyzer.analyze(analysis_results)

# Execute registered callbacks for selected triggers
if result.should_research:
    exec_result = trigger_analyzer.execute_triggers(
        result.selected_triggers,
        stop_on_failure=False
    )
    print(f"Executed {exec_result.successful_executions} triggers")
    print(f"Failures: {exec_result.failed_executions}")
```

**Async Execution**:
```python
# Register async callback
async def handle_research_async(trigger: FollowupTrigger) -> Optional[Dict]:
    result = await research_orchestrator.execute(trigger.research_plan)
    return {"findings": result.findings}

trigger_analyzer.register_async_callback(handle_research_async)

# Execute asynchronously
exec_result = await trigger_analyzer.execute_triggers_async(
    result.selected_triggers,
    max_concurrent=5
)
```

#### Trigger Detection Methods

The analyzer automatically detects various trigger types:

1. **Uncertainty Triggers**: From low confidence findings
   - Triggered when confidence < 0.7
   - Priority scales with severity of uncertainty

2. **Gap Triggers**: From identified coverage gaps
   - Triggered by ResearchStateTracker
   - Recommended queries provided

3. **Depth Triggers**: From shallow coverage on critical topics
   - Critical topics: api_integration, pricing, compliance, security, etc.
   - Suggest deep-dive queries

4. **Validation Triggers**: From failed validations
   - Claims that didn't verify
   - Resolution queries generated

5. **Emerging Triggers**: From newly mentioned but unresearched entities
   - Discovered entities not in researched list
   - Basic understanding queries generated

6. **Conflict Triggers**: From cross-reference conflicts
   - Conflicting information found
   - Resolution queries suggested

#### Usage Example

```python
from autopack.research.analysis.followup_trigger import FollowupResearchTrigger

trigger_analyzer = FollowupResearchTrigger()

# Register callback for autonomous research
def autonomous_research(trigger: FollowupTrigger) -> Optional[Dict]:
    # Execute research based on trigger plan
    queries = trigger.research_plan.queries
    agent = trigger.research_plan.target_agent

    # Call research agents
    findings = research_executor.run_queries(queries, agent=agent)
    return findings

trigger_analyzer.register_callback(autonomous_research)

# Analyze and trigger research
result = trigger_analyzer.analyze_and_execute(
    analysis_results=previous_results,
    validation_results=validation_outcomes
)

print(f"Detected {result.triggers_detected} triggers")
print(f"Selected {result.triggers_selected} for research")
print(f"Execution: {result.execution_result.successful_executions} succeeded")

# Continue research if gaps remain
if trigger_analyzer.should_continue_followup(
    iteration=0,
    prev_results=previous_results,
    new_results=result.execution_result.integrated_findings
):
    # Perform another iteration
    pass
```

---

### 3. BuildVsBuyAnalyzer

**Purpose**: Evaluates build vs. buy decisions for project components through cost, risk, and strategic analysis.

**Location**: `src/autopack/research/analysis/build_vs_buy_analyzer.py`

#### Key Classes

**BuildVsBuyAnalysis** - Analysis result
```python
@dataclass
class BuildVsBuyAnalysis:
    component: str                      # Component name
    recommendation: DecisionRecommendation  # BUILD, BUY, or HYBRID
    confidence: float                   # 0.0 to 1.0
    build_cost: CostEstimate           # Build option costs
    buy_cost: CostEstimate             # Buy option costs
    build_time_weeks: float            # Development time
    buy_integration_time_weeks: float  # Integration time
    risks: List[RiskAssessment]        # Identified risks
    rationale: str                     # Decision rationale
    strategic_importance: StrategicImportance
    build_score: float                 # 0-100
    buy_score: float                   # 0-100
```

**DecisionRecommendation**
- `BUILD`: Develop in-house
- `BUY`: Purchase/integrate external solution
- `HYBRID`: Combination of build and buy

**StrategicImportance**
- `CORE_DIFFERENTIATOR`: Strategic advantage
- `SUPPORTING`: Important but not differentiating
- `COMMODITY`: Non-core, readily available

#### Scoring System

The analyzer uses weighted scoring across multiple dimensions:

**Weights:**
- Cost: 25%
- Time: 20%
- Risk: 20%
- Feature Fit: 15%
- Strategic Importance: 20%

**Build Score Factors:**
- Low cost development → +10 points
- Acceptable timeline → +15 points
- Core differentiator → +20 points
- High team expertise → +10 points
- Risk penalties: -3 points per risk severity level

**Buy Score Factors:**
- Low subscription cost → +15 points
- Fast integration → +20 points
- Commodity component → +15 points
- Vendor quality → +5 points per quality indicator
- Lock-in risk penalties: -3 points per risk severity level

#### Risk Assessment Categories

- `VENDOR_LOCK_IN`: Difficulty switching vendors
- `TECHNICAL_DEBT`: Code quality and maintenance concerns
- `MAINTENANCE_BURDEN`: Ongoing support requirements
- `SECURITY`: Security implementation and updates
- `COMPLIANCE`: Regulatory compliance requirements
- `SCALABILITY`: Growth capacity limitations
- `INTEGRATION`: Difficulty integrating with existing systems
- `COST_OVERRUN`: Risk of cost escalation
- `TIME_TO_MARKET`: Impact on launch timeline
- `FEATURE_FIT`: Whether solution matches requirements

#### Usage Example

```python
from autopack.research.analysis.build_vs_buy_analyzer import (
    BuildVsBuyAnalyzer, ComponentRequirements, VendorOption,
    StrategicImportance
)

analyzer = BuildVsBuyAnalyzer(hourly_rate=75.0)

# Define component requirements
requirements = ComponentRequirements(
    component_name="User Authentication",
    description="SSO with 2FA support",
    required_features=[
        "SAML/OIDC support",
        "Multi-factor authentication",
        "Session management",
        "API access"
    ],
    security_requirements=[
        "Zero-trust architecture",
        "Audit logging",
        "Encryption at rest"
    ],
    compliance_requirements=[
        "SOC 2 Type II",
        "GDPR compliance"
    ],
    team_expertise_level="medium",
    time_constraint_weeks=8,
    strategic_importance=StrategicImportance.SUPPORTING
)

# Define vendor options
vendors = [
    VendorOption(
        name="Auth0",
        pricing_model="subscription",
        monthly_cost=500,
        features=["SAML", "2FA", "SSO", "MFA"],
        lock_in_risk="medium",
        integration_complexity="low",
        support_quality="high",
        documentation_quality="high"
    ),
    VendorOption(
        name="Okta",
        pricing_model="subscription",
        monthly_cost=1200,
        features=["SAML", "OIDC", "2FA", "MFA"],
        lock_in_risk="high",
        integration_complexity="medium",
        support_quality="high"
    )
]

# Analyze
analysis = analyzer.analyze(requirements, vendors)

print(f"Recommendation: {analysis.recommendation.value}")
print(f"Confidence: {analysis.confidence:.0%}")
print(f"Build: {analysis.build_score:.0f}/100")
print(f"Buy: {analysis.buy_score:.0f}/100")
print(f"Rationale: {analysis.rationale}")

# Cost comparison
comparison = analyzer.cost_comparison(requirements, vendors)
print(f"\nBreak-even: {comparison['cost_comparison']['analysis']['break_even_months']} months")
print(f"Year 5 cost (build): ${comparison['cost_comparison']['build']['year_5']:,.0f}")
print(f"Year 5 cost (buy): ${comparison['cost_comparison']['buy']['year_5']:,.0f}")
```

---

### 4. CostEffectivenessAnalyzer

**Purpose**: Aggregates component-level build/buy decisions and projects comprehensive cost-effectiveness metrics for the entire project.

**Location**: `src/autopack/research/analysis/cost_effectiveness.py`

#### Key Classes

**ProjectCostProjection** - Complete cost model
```python
@dataclass
class ProjectCostProjection:
    project_name: str
    components: List[ComponentCostData]  # Component costs
    ai_features: List[AITokenCostProjection]  # AI/LLM costs
    year_1_users: int = 1000
    year_3_users: int = 10000
    year_5_users: int = 50000
    mvp_dev_hours: int = 400
    hourly_rate: float = 75.0
    hosting_monthly: float = 100.0
    database_monthly: float = 50.0
    monitoring_monthly: float = 50.0
    optimizations: List[CostOptimizationStrategy]
```

**ComponentCostData** - Per-component cost model
```python
@dataclass
class ComponentCostData:
    component: str
    decision: DecisionType  # build, buy, integrate, outsource
    service_name: Optional[str]
    initial_cost: float
    monthly_ongoing: float
    scaling_model: ScalingModel  # flat, linear, step_function, logarithmic
    scaling_factor: float
    year_1_total: float
    year_3_total: float
    year_5_total: float
    vendor_lock_in_level: VendorLockInLevel
    migration_cost: float
    is_core_differentiator: bool
```

**ScalingModel** - How costs scale with growth
- `FLAT`: Fixed cost regardless of users
- `LINEAR`: Cost grows linearly with users
- `STEP_FUNCTION`: Cost jumps at usage thresholds
- `LOGARITHMIC`: Logarithmic growth (cost efficiency)
- `EXPONENTIAL`: Rapid cost growth (avoid)

**AITokenCostProjection** - AI/LLM token costs
```python
@dataclass
class AITokenCostProjection:
    feature: str
    model: str
    avg_input_tokens: int
    avg_output_tokens: int
    requests_per_user_monthly: int
    input_price_per_million: float = 3.0   # Default Claude Sonnet
    output_price_per_million: float = 15.0

    # Methods
    def cost_per_request(self) -> float: ...
    def monthly_cost_for_users(self, users: int) -> float: ...
```

#### Cost Analysis Components

The analyzer calculates:

1. **Executive Summary**
   - Year 1, 3, 5 total costs
   - Primary cost drivers
   - Key recommendations

2. **Component Analysis**
   - Per-component costs
   - Build vs. buy savings
   - Strategic importance

3. **AI/Token Costs**
   - Model pricing
   - Request volume projections
   - Optimization opportunities

4. **Infrastructure Costs**
   - Hosting, database, monitoring
   - Scaling projections
   - Year-by-year trends

5. **Development Costs**
   - MVP development hours
   - Ongoing maintenance
   - Team capacity planning

6. **Total Cost of Ownership (TCO)**
   - 5-year projection
   - Cost breakdown by category
   - Risk-adjusted scenarios

7. **Cost Optimization Roadmap**
   - MVP phase (Month 1-4): Speed over cost
   - Growth phase (Month 5-12): Unit economics
   - Scale phase (Year 2+): Efficiency

8. **Break-even Analysis**
   - Required MRR to cover costs
   - Users needed at specific price points
   - Profitability timeline

9. **Vendor Lock-in Assessment**
   - Lock-in risks by component
   - Migration costs
   - Alternative options

#### Usage Example

```python
from autopack.research.analysis.cost_effectiveness import (
    CostEffectivenessAnalyzer,
    ComponentCostData,
    AITokenCostProjection,
    DecisionType,
    ScalingModel
)

analyzer = CostEffectivenessAnalyzer()

# Prepare build-vs-buy results from BuildVsBuyAnalyzer
build_vs_buy_results = [
    {
        "component": "Authentication",
        "decision": "buy",
        "service_name": "Auth0",
        "cost_data": {
            "initial_cost": 0,
            "monthly_ongoing": 500,
            "scaling_model": "flat"
        },
        "is_core": False
    },
    # ... more components
]

# Define AI features using tokens
ai_features = [
    {
        "feature": "AI Analysis Engine",
        "model": "claude-sonnet",
        "avg_input_tokens": 2000,
        "avg_output_tokens": 1000,
        "requests_per_user_monthly": 10
    },
    {
        "feature": "Research Report Generation",
        "model": "claude-sonnet",
        "avg_input_tokens": 5000,
        "avg_output_tokens": 2000,
        "requests_per_user_monthly": 2
    }
]

# User projections
user_projections = {
    "year_1": 500,
    "year_3": 5000,
    "year_5": 25000
}

# Run analysis
analysis = analyzer.analyze(
    project_name="Autopack SaaS",
    build_vs_buy_results=build_vs_buy_results,
    ai_features=ai_features,
    user_projections=user_projections
)

# Review results
print("Year 1 Cost Projection:")
print(f"  Development: ${analysis['total_cost_of_ownership']['year_1']['development']:,.0f}")
print(f"  Infrastructure: ${analysis['total_cost_of_ownership']['year_1']['infrastructure']:,.0f}")
print(f"  AI APIs: ${analysis['total_cost_of_ownership']['year_1']['ai_apis']:,.0f}")
print(f"  Total: ${analysis['total_cost_of_ownership']['year_1']['total']:,.0f}")

print("\nCost Drivers:")
for driver in analysis['executive_summary']['primary_cost_drivers']:
    print(f"  - {driver}")

print("\nBreak-even Analysis:")
be = analysis['break_even_analysis']
print(f"  Year 1 MRR needed: ${be['required_mrr_to_cover_costs']['year_1']:,.0f}")
print(f"  At $29/mo: {be['users_needed_at_29_mo']['year_1']:,} users needed")

# Save to JSON
analyzer.to_json("project_cost_analysis.json")

# Generate budget anchor for Autopack
budget_anchor = analyzer.generate_budget_anchor()
```

---

## Integration Points

### Research Pipeline Integration

```
[Research Agents]
    ↓
[Research Orchestrator]
    ↓
[Analysis Results]
    ↓
┌─────────────────────────────────────┐
│  ResearchStateTracker              │
│  - Tracks progress                 │
│  - Identifies gaps                 │
│  - Creates checkpoints             │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  FollowupResearchTrigger          │
│  - Detects gaps                   │
│  - Executes callbacks             │
│  - Drives autonomous research     │
└─────────────────────────────────────┘
    ↓
[Gap-filling Research Results]
    ↓
┌─────────────────────────────────────┐
│  BuildVsBuyAnalyzer               │
│  - Evaluates components           │
│  - Makes recommendations          │
│  - Assesses risks                 │
└─────────────────────────────────────┘
    ↓
┌─────────────────────────────────────┐
│  CostEffectivenessAnalyzer        │
│  - Aggregates costs               │
│  - Projects TCO                   │
│  - Generates budgets              │
└─────────────────────────────────────┘
    ↓
[Project Brief with Recommendations]
```

### API Contract

**ResearchStateTracker API**:
```python
class ResearchStateTracker:
    def load_or_create_state(project_id: str) -> ResearchState
    def detect_gaps() -> List[ResearchGap]
    def record_completed_query(query, agent, sources_found, quality_score, findings)
    def update_coverage(category: str, new_coverage: float)
    def create_checkpoint(phase: str) -> ResearchCheckpoint
    def handle_interrupted_research(project_id) -> (bool, Optional[ResearchCheckpoint])
```

**FollowupResearchTrigger API**:
```python
class FollowupResearchTrigger:
    def analyze(analysis_results) -> TriggerAnalysisResult
    def register_callback(callback: TriggerCallback)
    def execute_triggers(triggers) -> TriggerExecutionResult
    def execute_triggers_async(triggers, max_concurrent) -> TriggerExecutionResult
    def analyze_and_execute(analysis_results) -> TriggerAnalysisResult
```

**BuildVsBuyAnalyzer API**:
```python
class BuildVsBuyAnalyzer:
    def analyze(requirements, vendor_options) -> BuildVsBuyAnalysis
    def cost_comparison(requirements, vendor_options, years=5)
    def risk_assessment(requirements, vendor_options)
    def analyze_multiple(components, vendor_options_map)
```

**CostEffectivenessAnalyzer API**:
```python
class CostEffectivenessAnalyzer:
    def analyze(project_name, build_vs_buy_results, ai_features, user_projections)
    def to_json(filepath: str)
    def generate_budget_anchor()
```

---

## Extension Points

### Adding New Analyzers

To add a new analyzer to the framework:

1. **Create analyzer class** in `src/autopack/research/analysis/`
2. **Implement standard interface**:
   ```python
   class MyAnalyzer:
       def analyze(self, input_data: Dict) -> Dict[str, Any]:
           # Core analysis logic
           pass

       def to_dict(self) -> Dict[str, Any]:
           # Serialization
           pass
   ```

3. **Register with orchestrator** (if needed)
4. **Add tests** in `tests/research/analysis/`
5. **Document API contract** in this file

### Adding New Gap Types

Extend `GapType` enum and add detection logic to `ResearchStateTracker`:

```python
class GapType(Enum):
    # ... existing types ...
    CUSTOM_GAP = "custom_gap"

# Add detection method
def _detect_custom_gaps(self) -> List[ResearchGap]:
    # Detection logic
    pass

# Call from detect_gaps()
```

### Adding New Trigger Types

Extend `TriggerType` and add detection to `FollowupResearchTrigger`:

```python
class TriggerType(Enum):
    # ... existing types ...
    CUSTOM_TRIGGER = "custom_trigger"

# Add detection method
def _detect_custom_triggers(self, analysis_results) -> List[FollowupTrigger]:
    # Detection logic
    pass

# Call from analyze()
```

### Custom Callbacks

Implement the `TriggerCallback` interface:

```python
from autopack.research.analysis.followup_trigger import FollowupTrigger

def my_custom_callback(trigger: FollowupTrigger) -> Optional[Dict]:
    """Custom research callback.

    Args:
        trigger: The trigger to handle

    Returns:
        Optional dict with research findings
    """
    # Implement custom research logic
    return {"findings": [...]}

# Register with analyzer
trigger_analyzer.register_callback(my_custom_callback)
```

---

## Testing Approach

### Unit Tests

Test individual components in isolation:

```bash
pytest tests/research/analysis/test_research_state.py
pytest tests/research/analysis/test_followup_trigger.py
pytest tests/research/analysis/test_build_vs_buy.py
pytest tests/research/analysis/test_cost_effectiveness.py
```

### Integration Tests

Test component interactions:

```python
def test_gap_detection_triggers_research():
    """Verify gaps trigger follow-up research."""
    # Create state with gaps
    # Verify FollowupResearchTrigger detects them
    # Verify callbacks can be executed
    pass

def test_build_vs_buy_feeds_cost_analyzer():
    """Verify build/buy decisions feed cost analysis."""
    # Run BuildVsBuyAnalyzer
    # Feed results to CostEffectivenessAnalyzer
    # Verify cost calculations are correct
    pass
```

### Edge Case Tests

Test recovery and error handling:

```python
def test_checkpoint_recovery():
    """Verify interrupted research can resume."""
    pass

def test_corrupted_state_repair():
    """Verify corrupted state can be repaired."""
    pass

def test_callback_failure_handling():
    """Verify callback failures are handled gracefully."""
    pass
```

---

## Best Practices

1. **Regular Gap Analysis**: Run `detect_gaps()` frequently to identify missing research
2. **Callback Error Handling**: Always wrap callbacks with try/catch for robustness
3. **Cost Projections**: Update user projections quarterly as business evolves
4. **Vendor Lock-in**: Monitor and mitigate high lock-in components
5. **Async Execution**: Use async callbacks for long-running research tasks
6. **Checkpoints**: Create checkpoints at major research milestones
7. **Documentation**: Keep analyzer documentation updated as components change

---

## Related Documentation

- [Research Pipeline Architecture](./ARCHITECTURE.md#research-phase)
- [Phase Lifecycle](./PHASE_LIFECYCLE.md)
- [Model Intelligence System](./MODEL_INTELLIGENCE_SYSTEM.md)
- [Cost Optimization Guide](./CONFIG_GUIDE.md)

