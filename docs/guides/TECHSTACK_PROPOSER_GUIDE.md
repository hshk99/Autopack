# TechStackProposer Guide

The **TechStackProposer** is a research module that provides **advisory recommendations** for technology choices during project planning. It analyzes project requirements and proposes multiple technology stack options with detailed pros/cons analysis, cost estimates, and risk assessments.

**Status**: ✅ Full implementation complete with comprehensive testing
**Module Location**: `src/autopack/research/tech_stack_proposer.py`
**Schema Location**: `src/autopack/schemas/tech_stack_proposal.schema.json`

---

## Overview

The TechStackProposer helps teams make informed technology decisions by:

1. **Proposing 2+ options** for each project type with evaluated trade-offs
2. **Estimating costs** with tiered classifications (free, low, medium, high, variable)
3. **Identifying risks** including Terms of Service restrictions and legal concerns
4. **Checking MCP availability** to show which options have Model Context Protocol support
5. **Scoring and ranking** options based on project requirements
6. **Providing recommendations** with confidence scores and reasoning

---

## Quick Start

### Basic Usage

```python
from autopack.research.tech_stack_proposer import TechStackProposer
from autopack.research.idea_parser import ProjectType

# Create a proposer
proposer = TechStackProposer(include_mcp_options=True)

# Get recommendations for an e-commerce project
proposal = proposer.propose(
    project_type=ProjectType.ECOMMERCE,
    requirements=["fast-checkout", "multi-vendor", "inventory-management"]
)

# Access results
print(f"Project Type: {proposal.project_type.value}")
print(f"Recommendation: {proposal.recommendation}")
print(f"Confidence Score: {proposal.confidence_score}")

# Examine options
for option in proposal.options:
    print(f"\n{option.name}")
    print(f"  Cost: {option.estimated_cost}")
    print(f"  Setup: {option.setup_complexity}")
    print(f"  MCP Available: {option.mcp_available}")
```

### Project Types

The proposer supports five project type categories:

| Type | Description | Common Stack Options |
|------|-------------|----------------------|
| **ECOMMERCE** | Online retail and e-shop platforms | Shopify, Next.js+Stripe+Supabase, WooCommerce |
| **TRADING** | Algorithmic or automated trading systems | Python+CCXT, Alpaca API+FastAPI |
| **CONTENT** | Content publishing and management platforms | Next.js+Sanity, Headless WordPress, Ghost |
| **AUTOMATION** | Workflow and process automation tools | Zapier, n8n, Make.com |
| **OTHER** | General-purpose applications | Next.js+Supabase, Django+PostgreSQL+Redis |

---

## API Reference

### TechStackProposer Class

```python
class TechStackProposer:
    """Proposes technology stack recommendations."""

    def __init__(self, include_mcp_options: bool = True):
        """Initialize the proposer.

        Args:
            include_mcp_options: Whether to prioritize options with MCP servers available
        """
```

#### `propose()` Method

**Signature**:
```python
def propose(
    project_type: ProjectType,
    requirements: list[str] | None = None,
) -> TechStackProposal:
```

**Parameters**:
- `project_type` (ProjectType): The category of project (ECOMMERCE, TRADING, CONTENT, AUTOMATION, OTHER)
- `requirements` (Optional[List[str]]): Specific requirements to consider (e.g., ["real-time-updates", "AI-integration"])

**Returns**:
- `TechStackProposal`: A proposal containing 2-3 ranked technology options with analysis

**Example**:
```python
proposal = proposer.propose(
    project_type=ProjectType.CONTENT,
    requirements=["SEO-optimization", "multi-language", "developer-friendly-cms"]
)
```

#### `get_all_options_for_type()` Method

**Signature**:
```python
def get_all_options_for_type(project_type: ProjectType) -> list[TechStackOption]:
```

**Returns**: All available technology stack options for a given project type

**Example**:
```python
all_ecommerce_options = proposer.get_all_options_for_type(ProjectType.ECOMMERCE)
print(f"Total e-commerce options: {len(all_ecommerce_options)}")
```

#### `get_mcp_enabled_options()` Method

**Signature**:
```python
def get_mcp_enabled_options(project_type: ProjectType) -> list[TechStackOption]:
```

**Returns**: Only technology options that have available MCP (Model Context Protocol) servers

**Example**:
```python
mcp_options = proposer.get_mcp_enabled_options(ProjectType.AUTOMATION)
# These options have MCP servers available for better AI integration
```

#### `check_tos_risks()` Method

**Signature**:
```python
def check_tos_risks(project_type: ProjectType) -> dict[str, list[TosRisk]]:
```

**Returns**: A dictionary mapping technology names to their associated ToS/legal risks

**Example**:
```python
risks = proposer.check_tos_risks(ProjectType.TRADING)
for tech_name, risk_list in risks.items():
    for risk in risk_list:
        if risk.level == TosRiskLevel.CRITICAL:
            print(f"⚠️ {tech_name}: {risk.description}")
```

---

## Data Models

### TechStackProposal

The main output object containing technology recommendations.

```python
class TechStackProposal(BaseModel):
    project_type: ProjectType           # The project category
    requirements: list[str]             # Input requirements
    options: list[TechStackOption]      # 2-3 recommended stacks
    recommendation: Optional[str]       # Recommended option name (if clear winner)
    recommendation_reasoning: Optional[str]  # Why this option is recommended
    confidence_score: float             # Confidence (0.0-1.0)
```

### TechStackOption

A single technology stack option with complete analysis.

```python
class TechStackOption(BaseModel):
    name: str                           # e.g., "Next.js + Stripe + Supabase"
    category: str                       # e.g., "Custom Stack"
    description: str                    # Brief overview
    pros: list[str]                     # Advantages (3-5 items)
    cons: list[str]                     # Disadvantages (3-5 items)
    estimated_cost: CostEstimate        # Cost analysis
    mcp_available: bool                 # MCP server available?
    mcp_server_name: Optional[str]      # Name of MCP server
    tos_risks: list[TosRisk]            # Legal/ToS risks
    setup_complexity: str               # "low", "medium", or "high"
    documentation_url: Optional[str]    # Link to official docs
    recommended_for: list[str]          # Scenarios this fits best
```

### CostEstimate

Detailed cost breakdown for a technology option.

```python
class CostEstimate(BaseModel):
    monthly_min: float                  # Minimum monthly cost (USD)
    monthly_max: float                  # Maximum monthly cost (USD)
    currency: str                       # Currency code (default: "USD")
    tier: CostTier                      # Classification: FREE, LOW, MEDIUM, HIGH, VARIABLE
    notes: str                          # Additional notes (scaling, hidden fees, etc.)
```

**Cost Tiers**:
- `FREE`: $0/month
- `LOW`: $0-50/month
- `MEDIUM`: $50-500/month
- `HIGH`: $500+/month
- `VARIABLE`: Usage-based pricing

### TosRisk

Terms of Service or legal risks associated with a technology.

```python
class TosRisk(BaseModel):
    description: str                    # What the risk is
    level: TosRiskLevel                 # NONE, LOW, MEDIUM, HIGH, CRITICAL
    mitigation: Optional[str]           # How to mitigate
```

**Risk Levels**:
- `NONE`: No significant risk
- `LOW`: Minor considerations
- `MEDIUM`: Important to review
- `HIGH`: Significant risk requiring careful planning
- `CRITICAL`: May result in account termination or legal issues

---

## Complete Example

### Scenario: Building an E-Commerce Platform

```python
from autopack.research.tech_stack_proposer import TechStackProposer, TosRiskLevel
from autopack.research.idea_parser import ProjectType

# Initialize proposer
proposer = TechStackProposer(include_mcp_options=True)

# Define project requirements
requirements = [
    "Global payment processing",
    "Scalable to 10k+ daily users",
    "Mobile-friendly",
    "Customizable product catalog"
]

# Get proposal
proposal = proposer.propose(ProjectType.ECOMMERCE, requirements)

# Display results
print(f"=== E-Commerce Tech Stack Proposal ===")
print(f"Top Recommendation: {proposal.recommendation}")
print(f"Confidence Score: {proposal.confidence_score * 100:.0f}%")
print(f"\nEvaluated {len(proposal.options)} options:\n")

for i, option in enumerate(proposal.options, 1):
    print(f"{i}. {option.name} ({option.category})")
    print(f"   Description: {option.description}")
    print(f"   Cost: {option.estimated_cost}")
    print(f"   Setup Complexity: {option.setup_complexity}")

    if option.mcp_available:
        print(f"   ✓ MCP Available: {option.mcp_server_name}")

    # Show critical risks
    critical_risks = [r for r in option.tos_risks if r.level == TosRiskLevel.CRITICAL]
    if critical_risks:
        print(f"   ⚠️  Critical Risks:")
        for risk in critical_risks:
            print(f"      - {risk.description}")
            if risk.mitigation:
                print(f"        → {risk.mitigation}")

    print(f"   Recommended For: {', '.join(option.recommended_for)}")
    print()
```

---

## Technology Stack Inventory

### E-Commerce Options

1. **Shopify + Custom App**
   - Best for rapid setup, non-technical founders
   - Cost: $29-299/month (medium tier)
   - Setup: Low complexity
   - MCP: Not available
   - Key Risk: Product category restrictions

2. **Next.js + Stripe + Supabase**
   - Best for custom requirements, developer-led teams
   - Cost: Free-$100/month (low tier)
   - Setup: High complexity
   - MCP: Supabase available
   - Key Risk: You manage PCI scope

3. **WooCommerce + WordPress**
   - Best for content-heavy stores
   - Cost: $10-50/month (low tier)
   - Setup: Medium complexity
   - MCP: Not available
   - Key Risk: Security updates responsibility

### Trading Options

1. **Python + CCXT + PostgreSQL**
   - Best for crypto trading, backtesting
   - Cost: Free-$50/month (low tier)
   - Setup: Medium complexity
   - MCP: PostgreSQL available
   - Key Risks: Exchange API ToS vary, regulatory compliance critical

2. **Alpaca API + FastAPI**
   - Best for US stock trading, beginners
   - Cost: Free-$99/month (low tier)
   - Setup: Low complexity
   - MCP: Not available
   - Key Risk: Pattern day trader rules (FINRA)

### Content Options

1. **Next.js + Sanity CMS**
   - Best for modern content management
   - Cost: Free-$99/month (variable tier)
   - Setup: Medium complexity
   - MCP: Available
   - Key Risk: Learning curve for content modeling

2. **Headless WordPress**
   - Best for existing WordPress users
   - Cost: $10-100/month (low-medium tier)
   - Setup: Medium complexity
   - MCP: Not available
   - Key Risk: WordPress plugin ecosystem quality varies

3. **Ghost**
   - Best for newsletter/publication focused
   - Cost: $29-199/month (medium tier)
   - Setup: Low complexity
   - MCP: Not available
   - Key Risk: Limited e-commerce capabilities

### Automation Options

1. **n8n**
   - Best for self-hosted workflows
   - Cost: Free-$35/month (low tier)
   - Setup: Low complexity
   - MCP: Not available
   - Key Risk: Limited free tier for complex workflows

2. **Zapier**
   - Best for quick prototypes, non-technical users
   - Cost: Free-$99/month (variable tier)
   - Setup: Low complexity
   - MCP: Not available
   - Key Risk: Task limits can be unexpectedly exceeded

### General Purpose Options

1. **Next.js + Supabase**
   - Best for MVPs, real-time apps
   - Cost: Free-$25/month (low tier)
   - Setup: Low complexity
   - MCP: Supabase available
   - Key Risk: Supabase still maturing vs Firebase

2. **Django + PostgreSQL + Redis**
   - Best for data-heavy apps, Python teams
   - Cost: $5-100/month (low tier)
   - Setup: Medium complexity
   - MCP: PostgreSQL available
   - Key Risk: Monolithic architecture may not suit all projects

---

## Integration with Autopack

### Research-to-Anchor Pipeline

TechStackProposer is **Deliverable 3** in the Research-to-Anchor pipeline:

1. **Market Analyzer** - Validates market opportunity
2. **Competitive Intelligence** - Analyzes competitors
3. **Tech Stack Proposer** ← You are here
4. **Gap Scanner** - Identifies missing requirements
5. **Plan Proposer** - Generates implementation plan
6. **Anchor Generator** - Creates intention anchors

### Usage in Project Bootstrap

When creating a new project with Autopack:

```
1. Parse project idea
2. Run market research
3. Get TechStackProposal
4. Incorporate recommendations into intention anchor
5. Execute build plan
```

### MCP Registry Integration

If `include_mcp_options=True`, the proposer prioritizes options with available MCP (Model Context Protocol) servers:

- `supabase-mcp` - For Supabase-based stacks
- `postgres-mcp` - For PostgreSQL databases
- More MCP servers added as ecosystem grows

---

## Best Practices

### 1. Always Provide Requirements

While the `requirements` parameter is optional, providing specific requirements improves recommendation accuracy:

```python
# ✓ Good: Specific requirements
proposal = proposer.propose(
    ProjectType.ECOMMERCE,
    requirements=["global-payments", "high-volume", "mobile-first", "third-party-integrations"]
)

# ✗ Weak: Generic proposal without context
proposal = proposer.propose(ProjectType.ECOMMERCE)
```

### 2. Review All Risk Levels

Always examine the `tos_risks` list, especially CRITICAL and HIGH-level risks:

```python
for option in proposal.options:
    high_risks = [r for r in option.tos_risks if r.level in [TosRiskLevel.HIGH, TosRiskLevel.CRITICAL]]
    if high_risks:
        # Flag for legal/compliance review
        print(f"⚠️ {option.name} requires review")
```

### 3. Filter by MCP Availability

If your project will use Claude agents with MCP support, prioritize MCP-enabled options:

```python
# Get only options with MCP support
mcp_options = proposer.get_mcp_enabled_options(ProjectType.AUTOMATION)

# Propose including MCP preferences
proposal = proposer.propose(
    ProjectType.AUTOMATION,
    requirements=["mcp-integration"]  # Hint to prioritize MCP options
)
```

### 4. Cost Estimation Context

Cost estimates are ranges. Consider:
- Early stage: Use `monthly_min`
- Growth stage: Use `monthly_max`
- Read the `notes` field for hidden costs (transaction fees, scaling charges, etc.)

```python
for option in proposal.options:
    print(f"{option.name}:")
    print(f"  Startup Cost: ${option.estimated_cost.monthly_min}")
    print(f"  Peak Cost: ${option.estimated_cost.monthly_max}")
    print(f"  Notes: {option.estimated_cost.notes}")
```

### 5. Setup Complexity Affects Timeline

Factor setup complexity into your planning:

```python
# "low" = 1-2 hours to get started
# "medium" = 1-3 days to set up properly
# "high" = 1-2 weeks for full setup + learning

for option in proposal.options:
    if option.setup_complexity == "high":
        # Plan for longer setup phase
        pass
```

---

## Testing

The TechStackProposer has comprehensive test coverage:

**Test Files**:
- `tests/research/test_tech_stack_proposer.py` - Core proposal generation
- `tests/research/test_tech_stack_proposal_validation.py` - Schema validation

**Run Tests**:
```bash
pytest tests/research/test_tech_stack_proposer.py -v
pytest tests/research/test_tech_stack_proposal_validation.py -v
```

---

## Schema Validation

Technology proposals are validated against the JSON Schema:

**Location**: `src/autopack/schemas/tech_stack_proposal.schema.json`

**Use in code**:
```python
import json
from jsonschema import validate

# Validate a proposal
proposal_dict = proposal.model_dump()
with open("src/autopack/schemas/tech_stack_proposal.schema.json") as f:
    schema = json.load(f)
    validate(instance=proposal_dict, schema=schema)
    print("✓ Proposal is valid")
```

---

## Related Documentation

- **Research-to-Anchor Pipeline**: `docs/IMPLEMENTATION_PLAN_RESEARCH_TO_ANCHOR_PIPELINE.md`
- **Claude Agents Research Bridge**: `docs/IMPLEMENTATION_PLAN_CLAUDE_AGENTS_RESEARCH_BRIDGE.md`
- **Project Type Parser**: `src/autopack/research/idea_parser.py`
- **Stack Evaluator Agent**: `.claude/agents/research-sub/stack-evaluator.md` (if available)

---

## Troubleshooting

### Q: How do I filter options by cost?

```python
proposal = proposer.propose(ProjectType.ECOMMERCE)

# Get only free/low-cost options
budget_options = [
    opt for opt in proposal.options
    if opt.estimated_cost.tier in ["free", "low"]
]
```

### Q: How do I find options suitable for beginners?

```python
proposal = proposer.propose(ProjectType.ECOMMERCE)

# Filter by setup complexity and documentation
beginner_options = [
    opt for opt in proposal.options
    if opt.setup_complexity == "low" and "non-technical" in opt.recommended_for
]
```

### Q: Can I get all options, not just the top 3?

```python
# Yes, use get_all_options_for_type()
all_options = proposer.get_all_options_for_type(ProjectType.ECOMMERCE)

# Then score/filter them manually as needed
```

### Q: What if I need a tech stack not in the predefined options?

The TechStackProposer provides **advisory recommendations** for common project types. For highly specialized stacks, the proposal includes reasoning that can be extended with domain-specific analysis.

---

## Contributing

To add new technology options or update existing ones:

1. Edit `src/autopack/research/tech_stack_proposer.py`
2. Add/update the relevant `_*_STACKS` list
3. Update the schema if new fields are needed
4. Add test cases to `tests/research/test_tech_stack_proposer.py`
5. Verify schema validation passes

---

## Version History

- **v1.0** (Commit ac4ad764, BUILD-170+): Full implementation with 5 project types, 14 technology options, comprehensive schema validation
