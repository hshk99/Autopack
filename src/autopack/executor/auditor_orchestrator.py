"""Auditor orchestration for phase execution.

Extracted from autonomous_executor.py as part of PR-EXE-11.
Handles Auditor LLM invocation, result parsing, and API posting.
"""

import json
import logging
from typing import Any, Dict, List, Optional

from autopack.debug_journal import log_error

logger = logging.getLogger(__name__)


class AuditorOrchestrator:
    """Orchestrates Auditor review for phase validation.

    Responsibilities:
    1. Execute Auditor LLM review with CI results and coverage
    2. Parse Auditor response for structured fields
    3. Format and post Auditor results to API
    4. Handle backwards compatibility for API schema mismatches
    """

    def __init__(self, executor: "AutonomousExecutor"):
        """Initialize with reference to parent executor.

        Args:
            executor: Parent AutonomousExecutor instance for accessing:
                - llm_service: LLM service for Auditor invocation
                - api_client: API client for posting results
                - run_id: Run identifier
                - _build_run_context(): Model override builder
                - _compute_coverage_delta(): Coverage computation
        """
        self.executor = executor
        self.llm_service = executor.llm_service
        self.api_client = executor.api_client
        self.run_id = executor.run_id

    def execute_auditor_review(
        self,
        phase_id: str,
        phase: Dict,
        builder_result: "BuilderResult",
        ci_result: Optional[Dict[str, Any]],
        project_rules: List[str],
        run_hints: List[str],
        attempt_index: int = 0,
    ) -> "AuditorResult":
        """Execute Auditor review via LlmService.

        Main entry point for Auditor orchestration. Invokes Auditor LLM,
        parses response, and posts results to API.

        Args:
            phase_id: Unique phase identifier
            phase: Phase specification dict
            builder_result: BuilderResult with patch to review
            ci_result: CI test results (with coverage if available)
            project_rules: Stage 0B persistent project rules
            run_hints: Stage 0A within-run hints from earlier phases
            attempt_index: Current attempt number for model escalation

        Returns:
            AuditorResult with approval status, issues, and suggested patches
        """
        logger.info(
            f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)..."
        )

        # Compute coverage delta from CI results
        coverage_delta = self._compute_coverage_delta(ci_result)

        # Use LlmService for complexity-based model selection with escalation
        auditor_result = self.llm_service.execute_auditor_review(
            patch_content=builder_result.patch_content,
            phase_spec=phase,
            max_tokens=None,  # Let ModelRouter decide
            project_rules=project_rules,  # Stage 0B: Persistent project rules
            run_hints=run_hints,  # Stage 0A: Within-run hints from earlier phases
            run_id=self.run_id,
            phase_id=phase_id,
            run_context=self._build_run_context(),  # Include model overrides if specified
            ci_result=ci_result,  # Real CI results
            coverage_delta=coverage_delta,  # Coverage delta computation
            attempt_index=attempt_index,  # Pass attempt for model escalation
        )

        logger.info(
            f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, "
            f"issues={len(auditor_result.issues_found)}"
        )

        # Post auditor result to API
        self.post_auditor_result(phase_id, auditor_result)

        return auditor_result

    def post_auditor_result(self, phase_id: str, result: "AuditorResult"):
        """POST auditor result to Autopack API.

        Formats Auditor result, parses structured fields, and posts to API
        with backwards compatibility handling.

        Args:
            phase_id: Phase ID
            result: Auditor result from llm_client.AuditorResult dataclass
        """
        from autopack.supervisor.api_client import SupervisorApiHttpError

        # Map llm_client.AuditorResult to builder_schemas.AuditorResult
        # Convert issues_found from List[Dict] to List[BuilderSuggestedIssue]
        formatted_issues = []
        for issue in result.issues_found:
            formatted_issues.append(
                {
                    "issue_key": issue.get("issue_key", "unknown"),
                    "severity": issue.get("severity", "medium"),
                    "source": issue.get("source", "auditor"),
                    "category": issue.get("category", "general"),
                    "evidence_refs": issue.get("evidence_refs", []),
                    "description": issue.get("description", ""),
                }
            )

        # BUILD-190: Use deterministic auditor parsing for structured fields
        from autopack.executor.auditor_parsing import parse_auditor_result

        parsed_result = parse_auditor_result(
            auditor_messages=result.auditor_messages or [],
            approved=result.approved,
            issues_found=result.issues_found,
        )

        # Extract suggested patches from parsed result
        suggested_patches = [p.to_dict() for p in parsed_result.suggested_patches]

        payload = {
            "phase_id": phase_id,
            "run_id": self.run_id,
            "review_notes": (
                "\n".join(result.auditor_messages)
                if result.auditor_messages
                else (result.error or "")
            ),
            "issues_found": formatted_issues,
            "suggested_patches": suggested_patches,
            "auditor_attempts": 1,
            "tokens_used": result.tokens_used,
            "recommendation": parsed_result.recommendation,
            "confidence": parsed_result.confidence_overall,
        }

        try:
            self.api_client.submit_auditor_result(self.run_id, phase_id, payload, timeout=10)
            logger.debug(f"Posted auditor result for phase {phase_id}")
        except SupervisorApiHttpError as e:
            if e.status_code == 422:
                # Backwards compatibility: some backend deployments still (incorrectly) expect
                # BuilderResultRequest at the auditor_result endpoint, requiring a "success" field.
                #
                # If we see this schema-mismatch signature, retry with a minimal BuilderResultRequest wrapper.
                detail = None
                if e.response_body:
                    try:
                        detail = json.loads(e.response_body).get("detail")
                    except Exception:
                        pass

                is_missing_success = False
                if isinstance(detail, list):
                    for item in detail:
                        loc = item.get("loc") if isinstance(item, dict) else None
                        msg = item.get("msg") if isinstance(item, dict) else ""
                        if loc == ["body", "success"] and "Field required" in str(msg):
                            is_missing_success = True
                            break

                if is_missing_success:
                    fallback = {
                        "success": bool(result.approved),
                        "output": payload.get("review_notes") or "",
                        "files_modified": [],
                        "metadata": payload,
                    }
                    logger.warning(
                        f"[{phase_id}] auditor_result POST returned 422 missing success; "
                        f"retrying with BuilderResultRequest-compatible payload for backwards compatibility."
                    )
                    self.api_client.submit_auditor_result(
                        self.run_id, phase_id, fallback, timeout=10
                    )
                    logger.debug(f"Posted auditor result for phase {phase_id} (compat retry)")
                    return

            # Re-raise if not handled
            raise
        except Exception as e:
            logger.warning(f"Failed to post auditor result: {e}")

            # Log API failures to debug journal
            log_error(
                error_signature="API failure: POST auditor_result",
                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM",
            )

    def _compute_coverage_delta(self, ci_result: Optional[Dict[str, Any]]) -> Optional[float]:
        """Compute coverage delta from CI results.

        BUILD-190: Uses coverage_metrics module for deterministic handling.
        Returns None when coverage data unavailable (not 0.0 placeholder).

        Args:
            ci_result: CI test results (may contain coverage data)

        Returns:
            Coverage delta as float (e.g., +5.2 for 5.2% increase),
            or None if coverage data unavailable
        """
        from autopack.executor.coverage_metrics import compute_coverage_delta

        return compute_coverage_delta(ci_result)

    def _build_run_context(self) -> Dict[str, Any]:
        """Build run context for Auditor with model overrides.

        Delegates to executor's _build_run_context() method.

        Returns:
            Run context dict with model overrides if specified
        """
        return self.executor._build_run_context()
