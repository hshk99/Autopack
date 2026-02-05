# TechStackProposer API Reference

**Quick Reference** for the TechStackProposer class API.

**Module**: `autopack.research.tech_stack_proposer`
**Full Guide**: `docs/guides/TECHSTACK_PROPOSER_GUIDE.md`

---

## Quick Start

```python
from autopack.research.tech_stack_proposer import TechStackProposer
from autopack.research.idea_parser import ProjectType

proposer = TechStackProposer(include_mcp_options=True)
proposal = proposer.propose(ProjectType.ECOMMERCE, ["multi-vendor", "global-payments"])
print(proposal.recommendation)
```

---

## Class Methods

### `__init__(include_mcp_options: bool = True)`
Initialize proposer.

**Args**:
- `include_mcp_options` (bool): Prioritize options with MCP servers available

---

### `propose(project_type: ProjectType, requirements: list[str] | None = None) -> TechStackProposal`

Generate technology stack recommendations.

**Args**:
- `project_type` (ProjectType): Project category (ECOMMERCE, TRADING, CONTENT, AUTOMATION, OTHER)
- `requirements` (Optional[List[str]]): Specific project requirements

**Returns**:
- `TechStackProposal`: Proposal with 2-3 recommended options

**Example**:
```python
proposal = proposer.propose(
    ProjectType.CONTENT,
    ["multi-language", "headless-cms", "real-time-updates"]
)
```

---

### `get_all_options_for_type(project_type: ProjectType) -> list[TechStackOption]`

Get all available technology options for a project type.

**Args**:
- `project_type` (ProjectType): Project category

**Returns**:
- List of all TechStackOption objects

---

### `get_mcp_enabled_options(project_type: ProjectType) -> list[TechStackOption]`

Get only options with MCP (Model Context Protocol) server support.

**Args**:
- `project_type` (ProjectType): Project category

**Returns**:
- Filtered list of TechStackOption objects with MCP available

---

### `check_tos_risks(project_type: ProjectType) -> dict[str, list[TosRisk]]`

Check Terms of Service and legal risks by technology.

**Args**:
- `project_type` (ProjectType): Project category

**Returns**:
- Dictionary mapping technology names to their TosRisk list

---

## Data Classes

### TechStackProposal

```python
@dataclass
class TechStackProposal:
    project_type: ProjectType
    requirements: list[str]
    options: list[TechStackOption]  # 2-3 recommended
    recommendation: Optional[str]
    recommendation_reasoning: Optional[str]
    confidence_score: float  # 0.0-1.0
```

---

### TechStackOption

```python
@dataclass
class TechStackOption:
    name: str
    category: str
    description: str
    pros: list[str]
    cons: list[str]
    estimated_cost: CostEstimate
    mcp_available: bool
    mcp_server_name: Optional[str]
    tos_risks: list[TosRisk]
    setup_complexity: str  # "low", "medium", "high"
    documentation_url: Optional[str]
    recommended_for: list[str]
```

---

### CostEstimate

```python
@dataclass
class CostEstimate:
    monthly_min: float        # USD
    monthly_max: float        # USD
    currency: str             # "USD"
    tier: CostTier            # FREE, LOW, MEDIUM, HIGH, VARIABLE
    notes: str                # Scaling, hidden fees, etc.
```

**Cost Tiers**:
- `FREE` → $0/month
- `LOW` → $0-50/month
- `MEDIUM` → $50-500/month
- `HIGH` → $500+/month
- `VARIABLE` → Usage-based

---

### TosRisk

```python
@dataclass
class TosRisk:
    description: str
    level: TosRiskLevel     # NONE, LOW, MEDIUM, HIGH, CRITICAL
    mitigation: Optional[str]
```

---

### Enums

```python
class ProjectType(str, Enum):
    ECOMMERCE = "ecommerce"
    TRADING = "trading"
    CONTENT = "content"
    AUTOMATION = "automation"
    OTHER = "other"

class CostTier(str, Enum):
    FREE = "free"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VARIABLE = "variable"

class TosRiskLevel(str, Enum):
    NONE = "none"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

---

## Common Patterns

### Filter by Cost Tier

```python
proposal = proposer.propose(ProjectType.ECOMMERCE)
budget_options = [o for o in proposal.options if o.estimated_cost.tier in ["free", "low"]]
```

### Check for MCP Availability

```python
for option in proposal.options:
    if option.mcp_available:
        print(f"✓ {option.name} ({option.mcp_server_name})")
```

### Review Risks

```python
for option in proposal.options:
    critical = [r for r in option.tos_risks if r.level == TosRiskLevel.CRITICAL]
    if critical:
        print(f"⚠️ {option.name}:")
        for risk in critical:
            print(f"   {risk.description}")
```

### Filter by Setup Complexity

```python
easy_options = [o for o in proposal.options if o.setup_complexity == "low"]
```

---

## Testing

```bash
# Run all TechStackProposer tests
pytest tests/research/test_tech_stack_proposer.py -v
pytest tests/research/test_tech_stack_proposal_validation.py -v
```

---

## See Also

- Full guide: `docs/guides/TECHSTACK_PROPOSER_GUIDE.md`
- Implementation plan: `docs/IMPLEMENTATION_PLAN_RESEARCH_TO_ANCHOR_PIPELINE.md`
- Source code: `src/autopack/research/tech_stack_proposer.py`
- Schema: `src/autopack/schemas/tech_stack_proposal.schema.json`
