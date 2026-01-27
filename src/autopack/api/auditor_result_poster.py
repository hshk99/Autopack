"""Auditor result posting to API server.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles posting Auditor review results to the Autopack API.
"""

import logging
from typing import TYPE_CHECKING

from autopack.debug_journal import log_error
from autopack.llm_client import AuditorResult

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class AuditorResultPoster:
    """Posts Auditor review results to API server.

    Responsibilities:
    1. Format Auditor results for API
    2. Post to API endpoints
    3. Handle API errors
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    def post_result(self, phase_id: str, result: AuditorResult):
        """Post Auditor result to API server.

        Args:
            phase_id: Phase ID
            result: Auditor result from llm_client.AuditorResult dataclass

        Raises:
            Exception: On API communication failure (logged but not propagated)
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
            "run_id": self.executor.run_id,
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
            self.executor.api_client.submit_auditor_result(
                self.executor.run_id, phase_id, payload, timeout=10
            )
            logger.debug(f"Posted auditor result for phase {phase_id}")
        except SupervisorApiHttpError as e:
            if e.status_code == 422:
                # Backwards compatibility: some backend deployments still (incorrectly) expect BuilderResultRequest
                # at the auditor_result endpoint, requiring a "success" field.
                #
                # If we see this schema-mismatch signature, retry with a minimal BuilderResultRequest wrapper.
                import json

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
                        f"[{phase_id}] auditor_result POST returned 422 missing success; retrying with "
                        f"BuilderResultRequest-compatible payload for backwards compatibility."
                    )
                    self.executor.api_client.submit_auditor_result(
                        self.executor.run_id, phase_id, fallback, timeout=10
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
                run_id=self.executor.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM",
            )
