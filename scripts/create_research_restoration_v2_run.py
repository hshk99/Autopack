"""
Create research citation fix restoration run v2.2

Restores research system components and runs evaluation after Phase 1 fix.
BUILD-039 JSON repair is now active to handle malformed JSON autonomously.
"""

import os
import sys
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# API configuration
API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8000")
API_KEY = os.getenv("AUTOPACK_API_KEY")

RUN_ID = "research-system-restore-and-evaluate-v2"

PHASES = [
    {
        "phase_id": "restore_github_gatherer_v2",
        "phase_index": 0,
        "tier_id": "tier-restoration",
        "name": "Restore GitHub Gatherer",
        "description": "Create src/autopack/research/gatherers/github_gatherer.py with GitHub API integration, README fetching, and LLM-based finding extraction.",
        "instructions": """Create src/autopack/research/gatherers/github_gatherer.py with the following components:

1. GitHubGatherer class with:
   - __init__(self, github_token: str = None)
   - discover_repositories(self, topic: str, max_repos: int = 10) -> List[Dict]
   - fetch_readme(self, repo_full_name: str) -> str
   - extract_findings(self, readme_content: str, topic: str, max_findings: int = 5) -> List[Finding]

2. Key implementation details:
   - Use GitHub API (requests library) for repository search: https://api.github.com/search/repositories
   - Fetch README via API: https://api.github.com/repos/{owner}/{repo}/readme
   - Use anthropic client (claude-sonnet-4-5) for finding extraction
   - Parse LLM JSON response, handle markdown code blocks with regex
   - Import Finding from src.autopack.research.models.validators
   - Return Finding objects with: title, content, extraction_span, category, relevance_score, source_hash

3. Finding extraction prompt MUST emphasize:
   - extraction_span should be CHARACTER-FOR-CHARACTER quote from README (minimum 20 characters)
   - Explain that extraction_span is direct quote, content is LLM's interpretation
   - Provide examples: Good extraction_span quotes exact text, Bad extraction_span paraphrases
   - Categories: market_intelligence, competitive_analysis, technical_analysis
   - For market_intelligence/competitive_analysis: extraction_span MUST contain numbers

4. JSON parsing:
   - Try direct json.loads()
   - If fails, extract from markdown: ```json\\n(.+?)\\n``` (regex DOTALL mode)
   - Return list of Finding objects

5. Error handling:
   - Handle API rate limits gracefully
   - Log warnings for parsing failures
   - Return empty list if no findings

Reference: archive/research/active/CITATION_VALIDITY_IMPROVEMENT_PLAN.md lines 96-164

IMPORTANT: This is standalone file creation. Do NOT run pytest. File should import successfully with no syntax errors.""",
        "task_category": "restoration",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
        "scope": {
            "paths": [
                "src/autopack/research/gatherers/github_gatherer.py",
                "src/autopack/research/gatherers/__init__.py",
            ],
            "read_only_context": [
                "src/autopack/research/models/validators.py",
                "archive/research/active/CITATION_VALIDITY_IMPROVEMENT_PLAN.md",
            ],
        },
    },
    {
        "phase_id": "restore_evaluation_module_v2",
        "phase_index": 1,
        "tier_id": "tier-restoration",
        "name": "Restore Evaluation Module",
        "description": "Create src/autopack/research/evaluation/ module with CitationValidityEvaluator class.",
        "instructions": """Create src/autopack/research/evaluation/ module with CitationValidityEvaluator:

1. Create directory structure:
   - src/autopack/research/evaluation/__init__.py (can be empty or export CitationValidityEvaluator)
   - src/autopack/research/evaluation/citation_validator.py

2. CitationValidityEvaluator class in citation_validator.py:
   - Import: from src.autopack.research.models.validators import CitationValidator, Finding
   - Class with evaluate_summary(findings: List[Finding], source_content_map: Dict[str, str]) -> Dict method

3. evaluate_summary() implementation:
   - Create CitationValidator instance
   - For each finding:
     * Get source_text from source_content_map using finding metadata (repo name or source_hash)
     * Call validator.verify(finding, source_text, source_hash)
     * Track valid/invalid counts
     * Record failure reasons from VerificationResult.reason
   - Return Dict with:
     * total_findings: int
     * valid_citations: int
     * invalid_citations: int
     * validity_percentage: float (valid/total * 100)
     * failure_breakdown: Dict[str, int] (reason -> count)

4. Example usage:
```python
evaluator = CitationValidityEvaluator()
results = evaluator.evaluate_summary(findings, source_map)
print(f"Citation validity: {results['validity_percentage']:.1f}%")
```

Reference: archive/research/active/PHASE_0_STATUS_SUMMARY.md lines 152-165

IMPORTANT: Do NOT run pytest. This is file creation only.""",
        "task_category": "restoration",
        "complexity": "medium",
        "builder_mode": "scaffolding_heavy",
        "scope": {
            "paths": [
                "src/autopack/research/evaluation/citation_validator.py",
                "src/autopack/research/evaluation/__init__.py",
            ],
            "read_only_context": [
                "src/autopack/research/models/validators.py",
                "archive/research/active/PHASE_0_STATUS_SUMMARY.md",
            ],
        },
    },
    {
        "phase_id": "run_phase1_evaluation_v2",
        "phase_index": 2,
        "tier_id": "tier-evaluation",
        "name": "Run Phase 1 Evaluation",
        "description": "Execute evaluation to measure Phase 1 citation validity improvement (target: 74-79%).",
        "instructions": """Update and execute scripts/run_phase0_evaluation.py to measure citation validity:

1. Update script imports:
```python
from src.autopack.research.gatherers.github_gatherer import GitHubGatherer
from src.autopack.research.evaluation.citation_validator import CitationValidityEvaluator
```

2. Test on 3-5 sample repositories:
   - Use GitHub search: 'machine learning' OR 'data science' OR 'web framework'
   - Limit to repos with good README content (stars > 1000)
   - Extract findings from each README

3. For each repository:
   - gatherer = GitHubGatherer()
   - repos = gatherer.discover_repositories(topic, max_repos=5)
   - For each repo: readme = gatherer.fetch_readme(repo['full_name'])
   - findings = gatherer.extract_findings(readme, topic, max_findings=5)
   - Track source_content_map[repo_name] = readme

4. Run evaluation:
   - evaluator = CitationValidityEvaluator()
   - results = evaluator.evaluate_summary(all_findings, source_content_map)

5. Generate JSON report at .autonomous_runs/research-citation-fix/phase1_evaluation_results.json with baseline comparison and decision.

6. Expected results:
   - Baseline (Phase 0): 59.3%
   - After Phase 1 fix: 74-79% (target)
   - If ≥80%: Output "Phase 1 SUCCESS"
   - If <80%: Output "Phase 1 improvement confirmed, proceeding to Phase 2"

IMPORTANT: Run pytest tests/test_research_validators.py to verify Phase 1 fix.""",
        "task_category": "test",
        "complexity": "low",
        "builder_mode": "tweak_light",
        "scope": {
            "paths": [
                "scripts/run_phase0_evaluation.py",
                ".autonomous_runs/research-citation-fix/phase1_evaluation_results.json",
            ],
            "read_only_context": [
                "src/autopack/research/gatherers/github_gatherer.py",
                "src/autopack/research/evaluation/citation_validator.py",
                "src/autopack/research/models/validators.py",
            ],
        },
    },
]

TIERS = [
    {
        "tier_id": "tier-restoration",
        "tier_index": 0,
        "name": "Research System Restoration",
        "description": "Restore github_gatherer and evaluation modules with BUILD-039 JSON repair active",
    },
    {
        "tier_id": "tier-evaluation",
        "tier_index": 1,
        "name": "Phase 1 Evaluation",
        "description": "Run evaluation to measure Phase 1 citation validity improvement",
    },
]


def create_run():
    """Create run via API"""
    headers = {"Content-Type": "application/json"}
    if API_KEY:
        headers["Authorization"] = f"Bearer {API_KEY}"

    payload = {
        "run_id": RUN_ID,
        "tiers": TIERS,
        "phases": PHASES,
    }

    response = requests.post(f"{API_URL}/runs", json=payload, headers=headers)
    if response.status_code == 200:
        print(f"✅ Created run: {RUN_ID}")
        return True
    else:
        print(f"❌ Failed to create run: {response.status_code}")
        print(response.text)
        return False


if __name__ == "__main__":
    if create_run():
        print("\n🚀 Run created successfully!")
        print(f"\n📝 Monitor run at: {API_URL}/runs/{RUN_ID}")
        print("\n▶️  Start execution with:")
        print("   cd c:/dev/Autopack")
        print("   PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\" \\")
        print("   QDRANT_HOST=\"http://localhost:6333\" python -m autopack.autonomous_executor \\")
        print(f"   --run-id {RUN_ID} --api-url {API_URL} --poll-interval 15 --run-type autopack_maintenance")
        sys.exit(0)
    else:
        sys.exit(1)
