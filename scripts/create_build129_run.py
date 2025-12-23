"""
Create BUILD-129 autonomous run: Token Budget Intelligence (Self-Improvement)

Implements GPT-5.2's 4-layer token budget policy to reduce truncation failures.
"""

import requests
import sys

API_URL = "http://localhost:8000"

# BUILD-129 Plan: Token Budget Intelligence (3 phases)
BUILD_129_PLAN = {
    "run_id": "build129-token-budget-intelligence",
    "display_name": "BUILD-129: Token Budget Intelligence (Self-Improvement)",
    "goal": (
        "Implement GPT-5.2's 4-layer token budget policy to reduce truncation failures from 50% to 10% for multi-file phases. "
        "Reference: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md. "
        "This is a self-improvement build - Autopack implementing Autopack improvements (similar to BUILD-126 quality_gate.py). "
        "Key improvements: (1) Output-size predictor replacing file-count heuristic, "
        "(2) Continuation-based recovery to avoid wasted work on truncation, "
        "(3) NDJSON structured-edit format for truncation tolerance. "
        "Monitor BUILD-112/113/114 stability after each phase."
    ),
    "phases": [
        {
            "phase_id": "build129-phase1-output-size-predictor",
            "display_name": "Phase 1: Output-Size Predictor (Layer 1)",
            "goal": (
                "Replace file-count heuristic with deliverable-based token estimation. "
                "Create token_estimator.py module with estimate_output_tokens() function that predicts required tokens based on deliverable types: "
                "new files (~800 tokens), modifications (~300), tests (~600), docs (~200), config (~400). "
                "Integrate into anthropic_clients.py (line 160) and manifest_generator.py (_enhance_phase method). "
                "Reference implementation: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md Section 'Layer 1: Preflight Token Budget Selection'. "
                "Success criteria: BUILD-127 scenario estimated at 18k-22k tokens (vs 16k fixed before), all tests pass, no BUILD-112/113/114 regressions."
            ),
            "complexity": "medium",
            "task_category": "backend",
            "scope": {
                "deliverables": [
                    "src/autopack/token_estimator.py",
                    "src/autopack/anthropic_clients.py modifications",
                    "src/autopack/manifest_generator.py modifications",
                    "tests/test_token_estimator.py",
                    "docs/BUILD-129_PHASE1_OUTPUT_SIZE_PREDICTOR.md"
                ],
                "protected_paths": [
                    "src/autopack/autonomous_executor.py",
                    "src/autopack/models.py",
                    "src/frontend/"
                ],
                "read_only_context": [
                    "docs/TOKEN_BUDGET_ANALYSIS_REVISED.md",
                    "docs/BUILD-129_SELF_IMPROVEMENT_PLAN.md",
                    "src/autopack/deliverables_validator.py"
                ]
            }
        },
        {
            "phase_id": "build129-phase2-continuation-recovery",
            "display_name": "Phase 2: Continuation Recovery (Layer 2) - HIGHEST PRIORITY",
            "goal": (
                "Implement continuation-based truncation recovery to avoid wasted work. "
                "When truncation occurs at 95% completion, continue from last completed marker instead of regenerating everything. "
                "Create continuation_handler.py with handle_truncation_with_continuation() that: "
                "(1) Parses partial output to find last completed file/operation, "
                "(2) Generates continuation prompt with remaining deliverables, "
                "(3) Retries with reduced token budget (only for remaining work). "
                "Support both diff format (find last 'diff --git' block) and JSON format (parse partial operations). "
                "Integrate into autonomous_executor.py retry logic (around line 3800). "
                "Reference: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md Section 'Layer 2: Continuation-Based Recovery'. "
                "Success criteria: Truncation at 95% triggers continuation (not regeneration), BUILD-127 completes after continuation, no full regeneration in logs."
            ),
            "complexity": "high",
            "task_category": "backend",
            "dependencies": ["build129-phase1-output-size-predictor"],
            "scope": {
                "deliverables": [
                    "src/autopack/continuation_handler.py",
                    "src/autopack/autonomous_executor.py modifications",
                    "src/autopack/anthropic_clients.py modifications",
                    "tests/test_continuation_recovery.py",
                    "docs/BUILD-129_PHASE2_CONTINUATION_RECOVERY.md"
                ],
                "protected_paths": [
                    "src/autopack/models.py",
                    "src/frontend/"
                ],
                "read_only_context": [
                    "docs/TOKEN_BUDGET_ANALYSIS_REVISED.md",
                    "docs/BUILD-129_SELF_IMPROVEMENT_PLAN.md",
                    "src/autopack/token_estimator.py"
                ]
            }
        },
        {
            "phase_id": "build129-phase3-ndjson-format",
            "display_name": "Phase 3: NDJSON Structured-Edit Format (Layer 3)",
            "goal": (
                "Replace monolithic JSON with NDJSON (newline-delimited JSON) for truncation tolerance. "
                "Current structured-edit uses single JSON object - one truncation ruins entire output. "
                "NDJSON format: one operation per line, so partial output is parseable (only last line lost). "
                "Create ndjson_handler.py with parse_ndjson_structured_edit() and apply_ndjson_operations(). "
                "Format: First line is meta {\"type\": \"meta\", \"total_operations\": N}, then one operation per line. "
                "Update anthropic_clients.py to request NDJSON for multi-file scopes (≥5 deliverables). "
                "Update apply_handler.py to apply NDJSON operations incrementally. "
                "Reference: docs/TOKEN_BUDGET_ANALYSIS_REVISED.md Section 'Layer 3: Truncation-Tolerant Output Formats'. "
                "Success criteria: Truncation at operation 8/12 allows parsing operations 1-7, continuation from operation 8, zero JSON repair failures."
            ),
            "complexity": "high",
            "task_category": "backend",
            "dependencies": ["build129-phase2-continuation-recovery"],
            "scope": {
                "deliverables": [
                    "src/autopack/ndjson_handler.py",
                    "src/autopack/anthropic_clients.py modifications",
                    "src/autopack/apply_handler.py modifications",
                    "src/autopack/autonomous_executor.py modifications",
                    "tests/test_ndjson_structured_edit.py",
                    "docs/BUILD-129_PHASE3_NDJSON_FORMAT.md"
                ],
                "protected_paths": [
                    "src/autopack/models.py",
                    "src/frontend/"
                ],
                "read_only_context": [
                    "docs/TOKEN_BUDGET_ANALYSIS_REVISED.md",
                    "docs/BUILD-129_SELF_IMPROVEMENT_PLAN.md",
                    "src/autopack/continuation_handler.py",
                    "src/autopack/token_estimator.py"
                ]
            }
        }
    ],
    "model_overrides": {
        "builder": {
            "backend:high": "claude-sonnet-4-5"
        }
    },
    "auto_approve": False  # Human review after each phase to check BUILD-112/113/114 stability
}


def main():
    """Create BUILD-129 run for token budget intelligence."""
    print("Creating BUILD-129: Token Budget Intelligence (Self-Improvement)")
    print("=" * 80)
    print(f"Goal: {BUILD_129_PLAN['goal']}")
    print(f"Phases: {len(BUILD_129_PLAN['phases'])}")
    print()

    for i, phase in enumerate(BUILD_129_PLAN['phases'], 1):
        print(f"Phase {i}: {phase['display_name']}")
        print(f"  Complexity: {phase['complexity']}")
        print(f"  Deliverables: {len(phase['scope']['deliverables'])}")
        if 'dependencies' in phase:
            print(f"  Dependencies: {phase['dependencies']}")
        print()

    print("Creating run via API...")
    try:
        response = requests.post(
            f"{API_URL}/run/create",
            json=BUILD_129_PLAN,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        run_id = result.get("run_id")

        print(f"✅ BUILD-129 run created: {run_id}")
        print()
        print("Next steps:")
        print("1. Start autonomous executor for BUILD-129")
        print("2. Monitor BUILD-112/113/114 stability after each phase")
        print("3. Review phase outputs before approving next phase")
        print()
        print("Run command:")
        print(f"  PYTHONUTF8=1 PYTHONPATH=src DATABASE_URL='sqlite:///autopack.db' python -m autopack.autonomous_executor {run_id}")

        return run_id

    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating run: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response: {e.response.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
