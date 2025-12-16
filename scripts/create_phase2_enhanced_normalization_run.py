#!/usr/bin/env python3
"""
Create Autopack run for Phase 2: Enhanced Text Normalization

This script creates an Autopack autonomous run to integrate text_normalization.py
into validators.py to improve citation validity from 72.2% to ≥80%.
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

RUN_ID = "research-phase2-enhanced-normalization"


def main():
    if not API_KEY:
        print("Error: AUTOPACK_API_KEY not set in environment")
        return 1

    headers = {"X-API-Key": API_KEY}

    # Create run
    run_payload = {
        "run_id": RUN_ID,
        "goal": "Phase 2: Integrate enhanced text normalization into validators.py to achieve ≥80% citation validity",
        "context": {
            "project": "research_citation_fix",
            "phase": "phase_2_enhanced_normalization",
            "version": "2.3",
            "current_validity": "72.2%",
            "target_validity": "80.0%",
            "phase1_improvement": "+12.9%",
            "remaining_gap": "7.8%",
            "primary_failures": "3/5 failures are 'extraction_span not found in source' (text normalization issue)"
        }
    }

    response = requests.post(f"{API_URL}/runs", json=run_payload, headers=headers)
    if response.status_code != 200:
        print(f"Error creating run: {response.status_code} - {response.text}")
        return 1

    print(f"✅ Created run: {RUN_ID}")

    # Define phases
    phases = [
        {
            "phase_id": "integrate_text_normalization",
            "phase_index": 0,
            "tier_id": "tier-implementation",
            "name": "Integrate Text Normalization",
            "description": """Integrate text_normalization.normalize_text() into validators.py _normalize_text() method.

CONTEXT:
- Phase 1 evaluation achieved 72.2% citation validity (up from 59.3%)
- Target is ≥80% validity
- Primary failure reason: 3/5 failures are "extraction_span not found in source" (text normalization issue)
- Enhanced normalization should fix these by handling HTML entities, Unicode, markdown artifacts

TASK:
Modify src/autopack/research/models/validators.py:

1. Add import at top of file:
   from autopack.text_normalization import normalize_text

2. Replace the _normalize_text() method (lines ~100-124) with enhanced version:
   def _normalize_text(self, text: str) -> str:
       \"\"\"Normalize text for matching using enhanced normalization.

       PHASE 2 ENHANCEMENT (2025-12-16):
       - Uses text_normalization.normalize_text() for comprehensive normalization
       - Handles HTML entities (e.g., &nbsp;, &#x27;)
       - Unicode normalization (NFC)
       - Markdown artifact stripping ([links], **bold**, etc.)
       - Whitespace normalization

       Args:
           text: Text to normalize

       Returns:
           Normalized text
       \"\"\"
       if not text:
           return ""

       # Use comprehensive normalization from text_normalization module
       return normalize_text(text, strip_markdown=True)

ACCEPTANCE CRITERIA:
- Import added correctly
- _normalize_text() method replaced with enhanced version
- Comment updated to reflect Phase 2 enhancement
- File still imports successfully (no syntax errors)

REFERENCE FILES:
- Source file: src/autopack/research/models/validators.py
- Normalization module: src/autopack/text_normalization.py (already exists with normalize_text function)
- Tests: tests/test_research_validators.py (should still pass 20/20)

DO NOT:
- Modify any other methods in validators.py
- Change the method signature of _normalize_text()
- Add any other functionality beyond text normalization integration
""",
            "category": "feature",
            "status": "QUEUED",
            "retry_count": 0,
            "max_retries": 3,
            "metadata": {
                "complexity": "low",
                "estimated_tokens": 3000,
                "files_to_modify": ["src/autopack/research/models/validators.py"],
                "reference_files": ["src/autopack/text_normalization.py"],
                "expected_impact": "+5-10% citation validity"
            },
            "status": "PENDING",
            "category": "feature",
            "estimated_token_budget": 3000
        },
        {
            "phase_id": "run_phase2_evaluation",
            "phase_index": 1,
            "tier_id": "tier-testing",
            "name": "Run Phase 2 Evaluation",
            "description": """Run Phase 2 evaluation to measure citation validity after enhanced normalization.

CONTEXT:
- Phase 1 evaluation: 72.2% validity
- Phase 2 integration: Enhanced text normalization applied
- Target: ≥80% validity

TASK:
Execute the existing Phase 1 evaluation script on the same test repositories to measure improvement after Phase 2 fix.

RUN COMMAND:
cd /c/dev/Autopack && PYTHONUTF8=1 PYTHONPATH=src python scripts/run_phase1_evaluation.py

This will:
1. Test on same 6 repositories (tensorflow, transformers, bootstrap, fastapi, d3, grafana)
2. Extract 18 findings (3 per repository)
3. Use CitationValidator with Phase 2 enhanced normalization
4. Save results to .autonomous_runs/research-citation-fix/phase1_evaluation_results.json
5. Compare to Phase 1 baseline (72.2%)

ACCEPTANCE CRITERIA:
- Evaluation script runs successfully
- Results show citation validity percentage
- Comparison to 72.2% baseline documented
- Decision: If ≥80%, Phase 2 SUCCESS. If <80%, document remaining issues.

EXPECTED OUTCOME:
- Citation validity: 80-85% (Phase 1: 72.2% + Phase 2: +7-13%)
- Primary improvement: Fix "extraction_span not found" failures (3/5 invalid citations)
- Remaining failures: Likely numeric edge cases (2/5 invalid citations)

OUTPUT:
Save evaluation report and document results in phase completion notes.
""",
            "status": "PENDING",
            "category": "test",
            "estimated_token_budget": 2000
        },
        {
            "phase_id": "update_documentation_phase2",
            "phase_index": 2,
            "tier_id": "tier-documentation",
            "name": "Update Documentation",
            "description": """Update RESEARCH_CITATION_FIX_PLAN.md and FUTURE_PLAN.md with Phase 2 results.

CONTEXT:
- Phase 2 enhanced normalization has been applied
- Evaluation results available
- Need to document outcomes and next steps

TASK:
Update documentation files based on Phase 2 evaluation results.

1. Update RESEARCH_CITATION_FIX_PLAN.md:
   - Add "## Phase 2: Enhanced Text Normalization" section after Phase 1 Evaluation
   - Include implementation details (integrate text_normalization.py)
   - Add Phase 2 evaluation results (validity percentage, comparison to Phase 1)
   - Document success/failure and next steps
   - Update header status line

2. Update FUTURE_PLAN.md:
   - Mark Task R4 as COMPLETE with actual results
   - Update "Current Status" line with Phase 2 results
   - Update "Citation Validity" percentage
   - If ≥80%: Mark project as SUCCESS
   - If <80%: Document remaining issues and potential Phase 3

ACCEPTANCE CRITERIA:
- Both documentation files updated with Phase 2 results
- Evaluation metrics documented (validity %, improvement, failure analysis)
- Next steps clearly stated
- Status lines reflect Phase 2 completion

REFERENCE:
- Phase 1 evaluation section in RESEARCH_CITATION_FIX_PLAN.md (lines 125-172)
- Task R3 completion pattern in FUTURE_PLAN.md (lines 80-101)
""",
            "status": "PENDING",
            "category": "documentation",
            "estimated_token_budget": 4000
        }
    ]

    # Create phases
    for phase in phases:
        response = requests.post(f"{API_URL}/runs/{RUN_ID}/phases", json=phase, headers=headers)
        if response.status_code != 200:
            print(f"Error creating phase {phase['phase_id']}: {response.status_code} - {response.text}")
            return 1
        print(f"  ✅ Created phase: {phase['phase_id']}")

    print(f"\n🚀 Run created successfully!")
    print(f"   Run ID: {RUN_ID}")
    print(f"   Phases: {len(phases)}")
    print(f"\nTo execute:")
    print(f"  cd c:/dev/Autopack && PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL=\"postgresql://autopack:autopack@localhost:5432/autopack\" QDRANT_HOST=\"http://localhost:6333\" python -m autopack.autonomous_executor --run-id {RUN_ID} --poll-interval 15 --run-type autopack_maintenance")

    return 0


if __name__ == "__main__":
    sys.exit(main())
