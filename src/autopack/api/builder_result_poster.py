"""Builder result posting to API server.

Extracted from autonomous_executor.py as part of PR-EXE-12.
Handles posting Builder execution results to the Autopack API.
"""

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

from autopack.debug_journal import log_error
from autopack.governed_apply import GovernedApplyPath
from autopack.llm_client import BuilderResult

if TYPE_CHECKING:
    from autopack.autonomous_executor import AutonomousExecutor

logger = logging.getLogger(__name__)


class BuilderResultPoster:
    """Posts Builder execution results to API server.

    Responsibilities:
    1. Format Builder results for API
    2. Post to API endpoints
    3. Handle API errors
    4. Retry on transient failures
    """

    def __init__(self, executor: "AutonomousExecutor"):
        self.executor = executor

    async def post_result(
        self, phase_id: str, result: BuilderResult, allowed_paths: Optional[List[str]] = None
    ):
        """Post Builder result to API server.

        Args:
            phase_id: Phase ID
            result: Builder result from llm_client.BuilderResult dataclass
            allowed_paths: Optional list of allowed paths for patching

        Raises:
            SupervisorApiHttpError: On API communication failure
        """
        from autopack.supervisor.api_client import SupervisorApiHttpError

        # Map llm_client.BuilderResult to builder_schemas.BuilderResult
        # Parse patch statistics using GovernedApplyPath
        # Enable internal mode for maintenance run types (for consistency)
        is_maintenance_run = self.executor.run_type in [
            "autopack_maintenance",
            "autopack_upgrade",
            "self_repair",
        ]
        governed_apply = GovernedApplyPath(
            workspace=Path(self.executor.workspace),
            run_type=self.executor.run_type,
            autopack_internal_mode=is_maintenance_run,
        )
        files_changed, lines_added, lines_removed = governed_apply.parse_patch_stats(
            result.patch_content or ""
        )

        # P1.2: Emit canonical BuilderResult payload matching builder_schemas.py
        # Use lowercase status vocabulary and top-level fields (no metadata wrapper)
        payload = {
            "phase_id": phase_id,
            "run_id": self.executor.run_id,
            "run_type": self.executor.run_type,
            "allowed_paths": allowed_paths or [],
            # Patch/diff information
            "patch_content": result.patch_content,  # Canonical field name
            "files_changed": files_changed,  # Canonical field name
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            # Execution details (top-level, not in metadata)
            "builder_attempts": 1,
            "tokens_used": result.tokens_used,
            "duration_minutes": 0.0,
            "probe_results": [],
            "suggested_issues": [],
            # Status (lowercase canonical vocabulary)
            "status": "success" if result.success else "failed",
            "notes": (
                "\n".join(result.builder_messages)
                if result.builder_messages
                else (result.error or "")
            ),
        }

        try:
            for attempt in range(3):
                try:
                    self.executor.api_client.submit_builder_result(
                        self.executor.run_id, phase_id, payload, timeout=10
                    )
                    logger.debug(f"Posted builder result for phase {phase_id}")
                    break
                except SupervisorApiHttpError as e:
                    # BUILD-195: Handle 422 payload schema validation errors
                    # These are schema errors (missing fields, wrong types, extra keys),
                    # NOT patch format errors. Use PayloadCorrectionTracker for one-shot.
                    if e.status_code == 422:
                        import json

                        error_detail = []
                        if e.response_body:
                            try:
                                error_detail = json.loads(e.response_body).get("detail", [])
                            except Exception:
                                pass
                        logger.error(
                            f"[{phase_id}] Payload schema validation failed (422): {error_detail}"
                        )

                        # Log validation failures to debug journal
                        log_error(
                            error_signature="Payload schema validation failure (422)",
                            symptom=f"Phase {phase_id}: {error_detail}",
                            run_id=self.executor.run_id,
                            phase_id=phase_id,
                            suspected_cause="BuilderResult payload has schema drift",
                            priority="MEDIUM",
                        )

                        # BUILD-195: One-shot payload correction via tracker
                        from autopack.executor.payload_correction import \
                            should_attempt_payload_correction

                        # Check budget and attempt correction (one-shot via tracker)
                        budget_remaining = 1.0 - (attempt / 3.0)
                        if should_attempt_payload_correction(error_detail, budget_remaining):
                            # Generate stable event_id for one-shot enforcement
                            event_id = f"{self.executor.run_id}:{phase_id}:422:{attempt}"
                            correction_result = (
                                self.executor._payload_correction_tracker.attempt_correction(
                                    original_payload=payload,
                                    validator_error_detail=error_detail,
                                    context={
                                        "run_id": self.executor.run_id,
                                        "phase_id": phase_id,
                                        "attempt": attempt,
                                        "event_id": event_id,
                                    },
                                )
                            )

                            if (
                                correction_result.correction_successful
                                and correction_result.corrected_payload
                            ):
                                logger.info(
                                    f"[{phase_id}] Payload correction successful "
                                    f"(method: {correction_result.evidence.get('correction_method', 'unknown')}, "
                                    f"fixes: {correction_result.evidence.get('corrections_made', [])}), "
                                    f"retrying POST"
                                )
                                # Replace payload with corrected version
                                payload = correction_result.corrected_payload
                                continue  # Retry with corrected payload
                            elif correction_result.blocked_reason:
                                logger.warning(
                                    f"[{phase_id}] Payload correction blocked: {correction_result.blocked_reason}"
                                )
                            else:
                                logger.warning(
                                    f"[{phase_id}] Payload correction failed, raising error"
                                )

                        raise  # Re-raise the 422 error

                    # Handle HTTP 5xx errors with retry logic
                    status_code = e.status_code
                    if status_code and status_code >= 500:
                        self.executor._run_http_500_count += 1
                        logger.warning(
                            f"[{phase_id}] HTTP 500 count this run: {self.executor._run_http_500_count}/{self.executor.MAX_HTTP_500_PER_RUN}"
                        )
                        if attempt < 2:
                            backoff = 1 * (2**attempt)
                            logger.info(
                                f"[{phase_id}] Retrying builder_result POST after {backoff}s (attempt {attempt + 2}/3)"
                            )
                            await asyncio.sleep(backoff)
                            continue
                        if self.executor._run_http_500_count >= self.executor.MAX_HTTP_500_PER_RUN:
                            logger.error(
                                f"[{phase_id}] HTTP 500 budget exceeded for run {self.executor.run_id}; consider aborting run."
                            )
                    # Non-retryable or retries exhausted
                    raise
        except SupervisorApiHttpError as e:
            status_code = e.status_code
            if status_code and status_code >= 500:
                self.executor._run_http_500_count += 1
                logger.warning(
                    f"[{phase_id}] HTTP 500 count this run: {self.executor._run_http_500_count}/{self.executor.MAX_HTTP_500_PER_RUN}"
                )
            if (
                status_code
                and status_code >= 500
                and self.executor._run_http_500_count >= self.executor.MAX_HTTP_500_PER_RUN
            ):
                logger.error(
                    f"[{phase_id}] HTTP 500 budget exceeded for run {self.executor.run_id}; consider aborting run."
                )
            logger.warning(f"Failed to post builder result: {e}")

            # Log API failures to debug journal
            log_error(
                error_signature="API failure: POST builder_result",
                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                run_id=self.executor.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM",
            )
