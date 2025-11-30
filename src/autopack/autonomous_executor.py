"""Autonomous Executor - Orchestration Loop for Autopack

Wires together Builder/Auditor clients to autonomously execute Autopack runs.

Architecture:
- Polls Autopack API for QUEUED phases
- Executes phases using BuilderClient implementations
- Reviews results using AuditorClient implementations
- Applies QualityGate checks for risk-based enforcement
- Updates phase status via API
- Supports dual auditor mode for high-risk categories

Usage:
    python autonomous_executor.py --run-id my-run

Environment Variables:
    OPENAI_API_KEY: OpenAI API key (required if using OpenAI)
    ANTHROPIC_API_KEY: Anthropic API key (required if using Anthropic)
    AUTOPACK_API_KEY: Autopack API key (optional)
    AUTOPACK_API_URL: Autopack API URL (default: http://localhost:8000)
"""

import os
import sys
import time
import json
import argparse
import logging
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.quality_gate import QualityGate
from autopack.llm_client import BuilderResult, AuditorResult
from autopack.error_recovery import ErrorRecoverySystem, get_error_recovery, safe_execute
from autopack.llm_service import LlmService
from autopack.debug_journal import log_error, log_fix, mark_resolved
from autopack.archive_consolidator import log_build_event, log_feature
from autopack.learned_rules import (
    load_project_learned_rules,
    get_relevant_rules_for_phase,
    get_relevant_hints_for_phase,
    promote_hints_to_rules,
    save_run_hint,
)
from autopack.journal_reader import get_recent_prevention_rules


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class AutonomousExecutor:
    """Autonomous executor for Autopack runs

    Orchestrates Builder -> Auditor -> QualityGate pipeline for each phase.
    """

    def __init__(
        self,
        run_id: str,
        api_url: str,
        api_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        workspace: Path = Path("."),
        use_dual_auditor: bool = True,
    ):
        """Initialize autonomous executor

        Args:
            run_id: Autopack run ID to execute
            api_url: Autopack API base URL
            api_key: Autopack API key (optional)
            openai_key: OpenAI API key (optional)
            anthropic_key: Anthropic API key (optional)
            workspace: Workspace root directory
            use_dual_auditor: Use dual auditor mode (requires both API keys)
        """
        self.run_id = run_id
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.workspace = workspace
        self.use_dual_auditor = use_dual_auditor

        # Store API keys
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")

        # Validate at least one API key is available
        if not self.openai_key and not self.anthropic_key:
            raise ValueError(
                "At least one LLM API key required: OPENAI_API_KEY or ANTHROPIC_API_KEY"
            )

        # Initialize error recovery system
        self.error_recovery = ErrorRecoverySystem()

        # Apply encoding fix immediately to prevent Unicode crashes
        # Create a dummy error context for encoding fix
        from autopack.error_recovery import ErrorContext, ErrorCategory, ErrorSeverity
        dummy_ctx = ErrorContext(
            error=Exception("Pre-emptive encoding fix"),
            error_type="UnicodeEncodeError",
            error_message="Pre-emptive encoding fix",
            traceback_str="",
            category=ErrorCategory.ENCODING,
            severity=ErrorSeverity.RECOVERABLE
        )
        logger.info("Applying pre-emptive encoding fix...")
        self.error_recovery._fix_encoding_error(dummy_ctx)

        # Initialize database for usage tracking
        db_url = os.getenv("AUTOPACK_DB_URL", "sqlite:///autopack.db")
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()

        # Initialize database tables (creates llm_usage_events table)
        # Import Base and models to register them with metadata
        from autopack.database import Base
        from autopack import models  # noqa: F401
        from autopack.usage_recorder import LlmUsageEvent  # noqa: F401

        # Create all tables using the same engine as the session
        Base.metadata.create_all(bind=engine)
        logger.info("Database tables initialized")

        # Initialize LlmService (replaces direct client instantiation)
        self.llm_service = None  # Will be set in _init_infrastructure

        # Initialize quality gate (will be set in _init_infrastructure)
        self.quality_gate = None

        logger.info(f"Initialized autonomous executor for run: {run_id}")
        logger.info(f"API URL: {api_url}")
        logger.info(f"Workspace: {workspace}")

        # [Self-Troubleshoot] Phase failure tracking for escalation
        self._phase_failure_counts: Dict[str, int] = {}  # phase_id -> consecutive failure count
        self._skipped_phases: set = set()  # Phases skipped due to escalation
        self.MAX_PHASE_FAILURES = 3  # Escalate after this many consecutive failures

        # [Mid-Run Re-Planning] Track failure patterns to detect approach flaws
        self._phase_error_history: Dict[str, List[Dict]] = {}  # phase_id -> list of error records
        self._phase_revised_specs: Dict[str, Dict] = {}  # phase_id -> revised phase spec
        self.REPLAN_TRIGGER_THRESHOLD = 2  # Trigger re-planning after this many same-type failures
        self.MAX_REPLANS_PER_PHASE = 1  # Maximum re-planning attempts per phase

        # Phase 1.4-1.5: Run proactive startup checks (from DEBUG_JOURNAL.md)
        self._run_startup_checks()

        # Learning Pipeline: Load project learned rules (Stage 0B)
        self._load_project_learning_context()

    def _run_startup_checks(self):
        """
        Phase 1.4-1.5: Run proactive startup checks from DEBUG_JOURNAL.md

        This implements the prevention system from ref5.md by applying
        learned fixes BEFORE errors occur (proactive vs reactive).
        """
        from autopack.journal_reader import get_startup_checks

        logger.info("Running proactive startup checks from DEBUG_JOURNAL.md...")

        try:
            checks = get_startup_checks()

            for check_config in checks:
                check_name = check_config.get("name")
                check_fn = check_config.get("check")
                fix_fn = check_config.get("fix")
                priority = check_config.get("priority", "MEDIUM")
                reason = check_config.get("reason", "")

                # Skip placeholder checks (implemented elsewhere)
                if check_fn == "implemented_in_executor":
                    continue

                logger.info(f"[{priority}] Checking: {check_name}")
                logger.info(f"  Reason: {reason}")

                try:
                    # Run the check
                    if callable(check_fn):
                        passed = check_fn()
                    else:
                        # Skip non-callable checks
                        continue

                    if not passed:
                        logger.warning(f"  Check FAILED - applying proactive fix...")
                        if callable(fix_fn):
                            fix_fn()
                            logger.info(f"  Fix applied successfully")
                        else:
                            logger.warning(f"  No fix function available")
                    else:
                        logger.info(f"  Check PASSED")

                except Exception as e:
                    logger.warning(f"  Startup check failed with error: {e}")
                    # Continue with other checks even if one fails

        except Exception as e:
            # Gracefully continue if startup checks system fails
            logger.warning(f"Startup checks system unavailable: {e}")

        logger.info("Startup checks complete")

    def _load_project_learning_context(self):
        """
        Learning Pipeline: Load project learned rules.

        This implements Stage 0B from LEARNED_RULES_README.md:
        - Loads persistent project rules from project_learned_rules.json
        - Rules are promoted from hints recorded during troubleshooting
        - These will be passed to Builder/Auditor for context-aware generation
        """
        project_id = self._get_project_slug()
        logger.info(f"Loading learning context for project: {project_id}")

        # Stage 0B: Load persistent project rules (promoted from hints)
        try:
            self.project_rules = load_project_learned_rules(project_id)
            if self.project_rules:
                logger.info(f"  Loaded {len(self.project_rules)} persistent project rules")
                for rule in self.project_rules[:3]:  # Show first 3
                    logger.info(f"    - {rule.constraint[:50]}...")
            else:
                logger.info("  No persistent project rules found (will learn from this run)")
        except Exception as e:
            logger.warning(f"  Failed to load project rules: {e}")
            self.project_rules = []

        logger.info("Learning context loaded successfully")

    def _get_learning_context_for_phase(self, phase: Dict) -> Dict:
        """
        Get relevant learning context for a specific phase.

        Filters project rules and run hints relevant to this phase's
        task category for injection into Builder/Auditor prompts.

        Args:
            phase: Phase specification dict

        Returns:
            Dict with 'project_rules' and 'run_hints' keys
        """
        # Get relevant project rules (Stage 0B - cross-run persistent rules)
        relevant_rules = get_relevant_rules_for_phase(
            self.project_rules if hasattr(self, 'project_rules') else [],
            phase  # Correct signature: pass phase dict
        )

        # Get run-local hints from earlier phases (Stage 0A - within-run hints)
        relevant_hints = get_relevant_hints_for_phase(
            self.run_id,
            phase,
            max_hints=5
        )

        if relevant_rules:
            logger.debug(f"  Found {len(relevant_rules)} relevant project rules for phase")
        if relevant_hints:
            logger.debug(f"  Found {len(relevant_hints)} hints from earlier phases")

        return {
            "project_rules": relevant_rules,
            "run_hints": relevant_hints,
        }

    def _mark_rules_updated(self, project_id: str, promoted_count: int):
        """
        Mark that project rules have been updated.

        This creates/updates a marker file that future planning agents can detect
        to know when rules have changed since the last plan was generated.

        The marker file contains:
        - Last update timestamp
        - Run ID that triggered the update
        - Number of new rules promoted
        - Total rule count

        Future planning can check this against plan generation time to determine
        if re-planning is needed based on newly learned rules.
        """
        try:
            from datetime import datetime

            marker_path = Path(".autonomous_runs") / project_id / "rules_updated.json"
            marker_path.parent.mkdir(parents=True, exist_ok=True)

            # Load existing marker or create new
            existing = {}
            if marker_path.exists():
                try:
                    with open(marker_path, 'r') as f:
                        existing = json.load(f)
                except (json.JSONDecodeError, IOError):
                    pass

            # Load current rules for total count
            rules = load_project_learned_rules(project_id)

            # Update marker
            marker = {
                "last_updated": datetime.utcnow().isoformat(),
                "last_run_id": self.run_id,
                "promoted_this_run": promoted_count,
                "total_rules": len(rules),
                "update_history": existing.get("update_history", [])[-9:] + [
                    {
                        "run_id": self.run_id,
                        "promoted": promoted_count,
                        "timestamp": datetime.utcnow().isoformat()
                    }
                ]
            }

            with open(marker_path, 'w') as f:
                json.dump(marker, f, indent=2)

            logger.info(f"Learning Pipeline: Marked rules updated (total: {len(rules)} rules)")

            # Log to console for visibility - future plans should incorporate these rules
            logger.info(
                f"[PLANNING NOTICE] {promoted_count} new rules promoted. "
                f"Future planning should incorporate {len(rules)} total project rules."
            )

        except Exception as e:
            logger.warning(f"Failed to mark rules updated: {e}")

    def _init_infrastructure(self):
        """Initialize LlmService and Quality Gate with error recovery.

        All LLM calls now go through LlmService which handles:
        - Model routing via ModelRouter
        - Multi-provider support (OpenAI, Anthropic)
        - Usage tracking and recording
        - Escalation logic
        """
        def _do_init():
            logger.info("Initializing infrastructure...")

            # Initialize LlmService (handles model routing, usage tracking, quality gate)
            self.llm_service = LlmService(
                db=self.db_session,
                config_path="config/models.yaml",
                repo_root=self.workspace
            )
            logger.info("LlmService: Initialized with ModelRouter and UsageRecorder")

            # Initialize Quality Gate
            self.quality_gate = QualityGate(repo_root=self.workspace)
            logger.info("Quality Gate: Initialized")

        # Wrap initialization with error recovery
        self.error_recovery.execute_with_retry(
            func=_do_init,
            operation_name="Infrastructure initialization",
            max_retries=3
        )

    def get_run_status(self) -> Dict:
        """Fetch run status from Autopack API with error recovery

        Returns:
            Run data with phases and status
        """
        def _fetch_status():
            url = f"{self.api_url}/runs/{self.run_id}"
            headers = {}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()

        return self.error_recovery.execute_with_retry(
            func=_fetch_status,
            operation_name="Fetch run status from API",
            max_retries=3
        )

    def _detect_and_reset_stale_phases(self, run_data: Dict):
        """
        Phase 1.6-1.7: Detect and auto-reset stale EXECUTING phases

        Identifies phases stuck in EXECUTING state for >10 minutes
        and automatically resets them to QUEUED for retry.

        This prevents the system from getting permanently stuck on
        failed infrastructure issues (network timeouts, API errors, etc.)
        """
        from datetime import datetime, timedelta
        import requests

        tiers = run_data.get("tiers", [])
        stale_threshold = timedelta(minutes=10)
        now = datetime.now()

        for tier in tiers:
            phases = tier.get("phases", [])

            for phase in phases:
                if phase.get("state") != "EXECUTING":
                    continue

                phase_id = phase.get("phase_id")

                # Check if phase has a last_updated timestamp
                last_updated_str = phase.get("updated_at") or phase.get("last_updated")

                if not last_updated_str:
                    logger.warning(f"[{phase_id}] EXECUTING phase has no timestamp - assuming stale and resetting")
                    self._update_phase_status(phase_id, "QUEUED")
                    continue

                try:
                    # Parse timestamp (assuming ISO format)
                    last_updated = datetime.fromisoformat(last_updated_str.replace('Z', '+00:00'))

                    # Make timezone-naive for comparison (assuming UTC)
                    if last_updated.tzinfo:
                        last_updated = last_updated.replace(tzinfo=None)

                    time_stale = now - last_updated

                    if time_stale > stale_threshold:
                        logger.warning(f"[{phase_id}] STALE PHASE DETECTED")
                        logger.warning(f"  State: EXECUTING")
                        logger.warning(f"  Last Updated: {last_updated_str}")
                        logger.warning(f"  Time Stale: {time_stale.total_seconds():.0f} seconds")
                        logger.warning(f"  Auto-resetting to QUEUED...")

                        # Phase 1.7: Auto-reset EXECUTING → QUEUED
                        try:
                            self._update_phase_status(phase_id, "QUEUED")
                            logger.info(f"[{phase_id}] Successfully reset to QUEUED")

                            # Log to DEBUG_JOURNAL.md for tracking
                            from autopack.debug_journal import log_fix
                            log_fix(
                                error_signature=f"Stale Phase Auto-Reset: {phase_id}",
                                fix_description=f"Automatically reset phase from EXECUTING to QUEUED after {time_stale.total_seconds():.0f}s of inactivity",
                                files_changed=["autonomous_executor.py"],
                                test_run_id=self.run_id,
                                result="success"
                            )

                        except Exception as e:
                            logger.error(f"[{phase_id}] Failed to reset stale phase: {e}")

                            # Log stale phase reset failure
                            log_error(
                                error_signature="Stale phase reset failure",
                                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                                run_id=self.run_id,
                                phase_id=phase_id,
                                suspected_cause="Failed to call API to reset stuck phase",
                                priority="HIGH"
                            )

                except Exception as e:
                    logger.warning(f"[{phase_id}] Failed to parse timestamp '{last_updated_str}': {e}")

    def get_next_queued_phase(self, run_data: Dict) -> Optional[Dict]:
        """Find next QUEUED phase in tier/index order

        Args:
            run_data: Run data from API

        Returns:
            Phase dict if found, None otherwise
        """
        tiers = run_data.get("tiers", [])

        # Sort tiers by tier_index
        sorted_tiers = sorted(tiers, key=lambda t: t.get("tier_index", 0))

        # Find first QUEUED phase across all tiers
        for tier in sorted_tiers:
            phases = tier.get("phases", [])
            # Sort phases within tier
            sorted_phases = sorted(phases, key=lambda p: p.get("phase_index", 0))

            for phase in sorted_phases:
                if phase.get("state") == "QUEUED":  # Note: API uses "state" not "status"
                    return phase

        return None

    def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
        """Execute Builder -> Auditor -> QualityGate pipeline for a phase with model escalation

        This method implements a retry loop with model escalation:
        - Attempts 0-1: Use cheapest model in escalation chain
        - Attempts 2-3: Use middle model in escalation chain
        - Attempts 4+: Use strongest model in escalation chain
        - After max_attempts failures: Mark phase as FAILED and skip

        Args:
            phase: Phase data from API

        Returns:
            Tuple of (success: bool, status: str)
            status can be: "COMPLETE", "FAILED", "BLOCKED"
        """
        phase_id = phase.get("phase_id")
        logger.info(f"Executing phase: {phase_id}")

        # Get max attempts from LlmService (reads from config)
        max_attempts = self.llm_service.get_max_attempts() if self.llm_service else 5

        # Track attempt index for this phase
        attempt_key = f"_attempt_index_{phase_id}"
        attempt_index = getattr(self, attempt_key, 0)

        # Retry loop with model escalation
        while attempt_index < max_attempts:
            logger.info(f"[{phase_id}] Attempt {attempt_index + 1}/{max_attempts} (model escalation enabled)")

            # Store current attempt for inner method
            setattr(self, attempt_key, attempt_index)

            # Wrap phase execution with error recovery
            def _execute_phase_inner():
                return self._execute_phase_with_recovery(phase, attempt_index=attempt_index)

            try:
                success, status = self.error_recovery.execute_with_retry(
                    func=_execute_phase_inner,
                    operation_name=f"Phase execution: {phase_id}",
                    max_retries=1  # Only 1 retry for transient errors within an attempt
                )

                if success:
                    # Record success for escalation tracking
                    if self.llm_service:
                        self.llm_service.record_attempt_outcome(
                            phase_id=phase_id,
                            model="unknown",  # Model info is in LlmService
                            outcome="success"
                        )

                    # Learning Pipeline: Record hint if succeeded after retries
                    # This means we learned something worth sharing with future phases
                    if attempt_index > 0:
                        self._record_learning_hint(
                            phase=phase,
                            hint_type="success_after_retry",
                            details=f"Succeeded on attempt {attempt_index + 1} after {attempt_index} failed attempts"
                        )

                    return success, status

                # Record failure and determine if we should retry
                failure_outcome = self._status_to_outcome(status)
                if self.llm_service:
                    self.llm_service.record_attempt_outcome(
                        phase_id=phase_id,
                        model="unknown",
                        outcome=failure_outcome,
                        details=f"Attempt {attempt_index + 1} failed with status {status}"
                    )

                # Learning Pipeline: Record hint about what went wrong
                # These hints help future phases avoid same mistakes
                self._record_learning_hint(
                    phase=phase,
                    hint_type=failure_outcome,
                    details=f"Failed with {status} on attempt {attempt_index + 1}"
                )

                # Mid-Run Re-Planning: Record error for approach flaw detection
                self._record_phase_error(
                    phase=phase,
                    error_type=failure_outcome,
                    error_details=f"Status: {status}",
                    attempt_index=attempt_index
                )

                # Check if we should trigger re-planning before next retry
                should_replan, flaw_type = self._should_trigger_replan(phase)
                if should_replan:
                    logger.info(f"[{phase_id}] Triggering mid-run re-planning due to {flaw_type}")

                    # Get error history for context
                    error_history = self._phase_error_history.get(phase_id, [])

                    # Invoke re-planner
                    revised_phase = self._revise_phase_approach(phase, flaw_type, error_history)

                    if revised_phase:
                        # Switch to revised approach and reset attempts
                        phase = revised_phase
                        attempt_index = 0
                        setattr(self, attempt_key, 0)
                        logger.info(f"[{phase_id}] Re-planning successful. Restarting with revised approach.")
                        continue
                    else:
                        logger.warning(f"[{phase_id}] Re-planning failed, continuing with original approach")

                # Increment attempt and continue loop
                attempt_index += 1
                setattr(self, attempt_key, attempt_index)

                if attempt_index < max_attempts:
                    logger.warning(f"[{phase_id}] Attempt {attempt_index} failed, escalating model for retry...")
                continue

            except Exception as e:
                logger.error(f"[{phase_id}] Attempt {attempt_index + 1} raised exception: {e}")
                # Record infrastructure error
                if self.llm_service:
                    self.llm_service.record_attempt_outcome(
                        phase_id=phase_id,
                        model="unknown",
                        outcome="infra_error",
                        details=str(e)
                    )

                # Mid-Run Re-Planning: Record error for approach flaw detection
                self._record_phase_error(
                    phase=phase,
                    error_type="infra_error",
                    error_details=str(e),
                    attempt_index=attempt_index
                )

                # Check if we should trigger re-planning before next retry
                should_replan, flaw_type = self._should_trigger_replan(phase)
                if should_replan:
                    logger.info(f"[{phase_id}] Triggering mid-run re-planning due to {flaw_type}")
                    error_history = self._phase_error_history.get(phase_id, [])
                    revised_phase = self._revise_phase_approach(phase, flaw_type, error_history)
                    if revised_phase:
                        phase = revised_phase
                        attempt_index = 0
                        setattr(self, attempt_key, 0)
                        logger.info(f"[{phase_id}] Re-planning successful. Restarting with revised approach.")
                        continue

                attempt_index += 1
                setattr(self, attempt_key, attempt_index)
                if attempt_index >= max_attempts:
                    break
                continue

        # All attempts exhausted - mark phase as FAILED
        logger.error(f"[{phase_id}] All {max_attempts} attempts exhausted. Marking phase as FAILED.")

        # Log to debug journal for persistent tracking
        log_error(
            error_signature=f"Phase {phase_id} max attempts exhausted",
            symptom=f"Phase failed after {max_attempts} attempts with model escalation",
            run_id=self.run_id,
            phase_id=phase_id,
            suspected_cause="Task complexity exceeds model capabilities or task is impossible",
            priority="HIGH"
        )

        self._update_phase_status(phase_id, "FAILED")
        return False, "FAILED"

    def _status_to_outcome(self, status: str) -> str:
        """Map phase status to outcome for escalation tracking."""
        outcome_map = {
            "FAILED": "auditor_reject",
            "PATCH_FAILED": "patch_apply_error",
            "BLOCKED": "auditor_reject",
            "CI_FAILED": "ci_fail",
        }
        return outcome_map.get(status, "auditor_reject")

    def _record_learning_hint(self, phase: Dict, hint_type: str, details: str):
        """
        Learning Pipeline: Record a hint for this run.

        Hints are lessons learned during troubleshooting that can help:
        1. Later phases in the same run (Stage 0A)
        2. Future runs after promotion (Stage 0B)

        Args:
            phase: Phase specification dict
            hint_type: Type of hint (e.g., auditor_reject, ci_fail, success_after_retry)
            details: Human-readable details about what was learned
        """
        try:
            phase_id = phase.get("phase_id", "unknown")
            task_category = phase.get("task_category", "general")
            phase_name = phase.get("name", phase_id)

            # Generate descriptive hint text based on type
            hint_templates = {
                "auditor_reject": f"Phase '{phase_name}' was rejected by auditor - ensure code quality and completeness",
                "ci_fail": f"Phase '{phase_name}' failed CI tests - verify tests pass before submitting",
                "patch_apply_error": f"Phase '{phase_name}' generated invalid patch - ensure proper diff format",
                "infra_error": f"Phase '{phase_name}' hit infrastructure error - check API connectivity",
                "success_after_retry": f"Phase '{phase_name}' succeeded after retries - model escalation was needed",
            }

            hint_text = hint_templates.get(hint_type, f"Phase '{phase_name}': {hint_type}")
            hint_text = f"{hint_text}. Details: {details}"

            # Save the hint
            save_run_hint(
                run_id=self.run_id,
                phase=phase,
                hint_text=hint_text,
                source_issue_keys=[f"{hint_type}_{phase_id}"]
            )

            logger.debug(f"[Learning] Recorded hint for {phase_id}: {hint_type}")

        except Exception as e:
            # Don't let hint recording break phase execution
            logger.warning(f"Failed to record learning hint: {e}")

    # =========================================================================
    # Mid-Run Re-Planning System
    # =========================================================================

    def _record_phase_error(self, phase: Dict, error_type: str, error_details: str, attempt_index: int):
        """
        Record an error for approach flaw detection.

        Tracks error patterns to distinguish 'approach flaw' from 'transient failure'.
        An approach flaw is detected when the same error type occurs repeatedly,
        indicating the underlying implementation approach is wrong.

        Args:
            phase: Phase specification
            error_type: Category of error (e.g., 'auditor_reject', 'ci_fail', 'patch_error')
            error_details: Detailed error message
            attempt_index: Current attempt number
        """
        phase_id = phase.get("phase_id")

        if phase_id not in self._phase_error_history:
            self._phase_error_history[phase_id] = []

        error_record = {
            "attempt": attempt_index,
            "error_type": error_type,
            "error_details": error_details,
            "timestamp": time.time(),
        }

        self._phase_error_history[phase_id].append(error_record)
        logger.debug(f"[Re-Plan] Recorded error for {phase_id}: {error_type}")

    def _normalize_error_message(self, message: str) -> str:
        """
        Normalize error message for similarity comparison.

        Strips:
        - Absolute/relative paths
        - Line numbers
        - Run IDs / UUIDs
        - Timestamps
        - Stack trace lines
        - Collapses whitespace
        """
        import re

        if not message:
            return ""

        normalized = message.lower()

        # Strip file paths (Unix and Windows)
        normalized = re.sub(r'[/\\][\w\-./\\]+\.(py|js|ts|json|yaml|yml|md)', '[PATH]', normalized)
        normalized = re.sub(r'[a-z]:\\[\w\-\\]+', '[PATH]', normalized, flags=re.IGNORECASE)

        # Strip line numbers (e.g., "line 42", ":42:", "L42")
        normalized = re.sub(r'\bline\s*\d+\b', 'line [N]', normalized)
        normalized = re.sub(r':\d+:', ':[N]:', normalized)
        normalized = re.sub(r'\bL\d+\b', 'L[N]', normalized)

        # Strip UUIDs
        normalized = re.sub(r'[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}', '[UUID]', normalized)

        # Strip run IDs (common patterns)
        normalized = re.sub(r'\b[a-z]+-\d{8}(-\d+)?\b', '[RUN_ID]', normalized)

        # Strip timestamps (ISO format and common patterns)
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}', '[TIMESTAMP]', normalized)
        normalized = re.sub(r'\d{2}:\d{2}:\d{2}', '[TIME]', normalized)

        # Strip stack trace lines
        normalized = re.sub(r'file "[^"]+", line \[n\]', 'file [PATH], line [N]', normalized)
        normalized = re.sub(r'traceback \(most recent call last\):', '[TRACEBACK]', normalized)

        # Collapse whitespace
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def _calculate_message_similarity(self, msg1: str, msg2: str) -> float:
        """
        Calculate similarity between two error messages using difflib.

        Returns:
            Float between 0.0 and 1.0 (1.0 = identical)
        """
        from difflib import SequenceMatcher

        if not msg1 or not msg2:
            return 0.0

        norm1 = self._normalize_error_message(msg1)
        norm2 = self._normalize_error_message(msg2)

        return SequenceMatcher(None, norm1, norm2).ratio()

    def _detect_approach_flaw(self, phase: Dict) -> Optional[str]:
        """
        Analyze error history to detect fundamental approach flaws.

        Enhanced with message similarity checking per GPT recommendation:
        - Checks consecutive same-type failures (not just total count)
        - Verifies message similarity >= threshold
        - Supports fatal error types that trigger immediately

        Returns:
            Error type if approach flaw detected, None otherwise
        """
        phase_id = phase.get("phase_id")
        errors = self._phase_error_history.get(phase_id, [])

        # Load replan config from models.yaml
        import yaml
        try:
            with open("config/models.yaml") as f:
                config = yaml.safe_load(f)
            replan_config = config.get("replan", {})
        except Exception:
            replan_config = {}

        trigger_threshold = replan_config.get("trigger_threshold", self.REPLAN_TRIGGER_THRESHOLD)
        similarity_enabled = replan_config.get("message_similarity_enabled", True)
        similarity_threshold = replan_config.get("similarity_threshold", 0.8)
        min_message_length = replan_config.get("min_message_length", 30)
        fatal_error_types = replan_config.get("fatal_error_types", [])

        if len(errors) == 0:
            return None

        # Check for fatal error types (immediate trigger on first occurrence)
        latest_error = errors[-1]
        if latest_error["error_type"] in fatal_error_types:
            logger.info(f"[Re-Plan] Fatal error type detected for {phase_id}: {latest_error['error_type']}")
            return latest_error["error_type"]

        if len(errors) < trigger_threshold:
            return None

        # Check consecutive same-type failures with message similarity
        # Look at the last N errors (where N = trigger_threshold)
        recent_errors = errors[-trigger_threshold:]

        # Group by error type
        error_types = [e["error_type"] for e in recent_errors]
        if len(set(error_types)) != 1:
            # Different error types in recent errors - not a repeated pattern
            return None

        error_type = error_types[0]

        # If similarity checking is disabled, trigger on same type alone
        if not similarity_enabled:
            logger.info(f"[Re-Plan] Approach flaw detected for {phase_id}: {error_type} occurred {trigger_threshold} times consecutively")
            return error_type

        # Check message similarity between consecutive errors
        messages = [e.get("error_details", "") for e in recent_errors]

        # Skip if messages are too short
        if all(len(m) < min_message_length for m in messages):
            logger.debug(f"[Re-Plan] Messages too short for similarity check ({phase_id})")
            # Fall back to type-only check
            logger.info(f"[Re-Plan] Approach flaw detected for {phase_id}: {error_type} occurred {trigger_threshold} times (short messages)")
            return error_type

        # Check pairwise similarity between consecutive errors
        all_similar = True
        for i in range(len(messages) - 1):
            similarity = self._calculate_message_similarity(messages[i], messages[i + 1])
            logger.debug(f"[Re-Plan] Message similarity [{i}]->[{i+1}]: {similarity:.2f}")
            if similarity < similarity_threshold:
                all_similar = False
                break

        if all_similar:
            logger.info(
                f"[Re-Plan] Approach flaw detected for {phase_id}: {error_type} occurred {trigger_threshold} times "
                f"with similar messages (similarity >= {similarity_threshold})"
            )
            return error_type

        logger.debug(f"[Re-Plan] No approach flaw for {phase_id}: messages not similar enough")
        return None

    def _get_replan_count(self, phase_id: str) -> int:
        """Get how many times a phase has been re-planned."""
        return self._phase_revised_specs.get(f"_replan_count_{phase_id}", 0)

    def _should_trigger_replan(self, phase: Dict) -> Tuple[bool, Optional[str]]:
        """
        Determine if re-planning should be triggered for a phase.

        Returns:
            Tuple of (should_replan: bool, detected_flaw_type: str or None)
        """
        phase_id = phase.get("phase_id")

        # Check if we've exceeded max replans
        replan_count = self._get_replan_count(phase_id)
        if replan_count >= self.MAX_REPLANS_PER_PHASE:
            logger.info(f"[Re-Plan] Max replans ({self.MAX_REPLANS_PER_PHASE}) reached for {phase_id}")
            return False, None

        # Detect approach flaw
        flaw_type = self._detect_approach_flaw(phase)
        if flaw_type:
            return True, flaw_type

        return False, None

    def _revise_phase_approach(self, phase: Dict, flaw_type: str, error_history: List[Dict]) -> Optional[Dict]:
        """
        Invoke LLM to revise the phase approach based on failure context.

        This is the core of mid-run re-planning: we ask the LLM to analyze
        what went wrong and provide a revised implementation approach.

        Args:
            phase: Original phase specification
            flaw_type: Detected flaw type
            error_history: History of errors for this phase

        Returns:
            Revised phase specification dict, or None if revision failed
        """
        phase_id = phase.get("phase_id")
        phase_name = phase.get("name", phase_id)
        original_description = phase.get("description", "")

        logger.info(f"[Re-Plan] Revising approach for {phase_id} due to {flaw_type}")

        # Build context from error history
        error_summary = "\n".join([
            f"- Attempt {e['attempt'] + 1}: {e['error_type']} - {e['error_details'][:200]}"
            for e in error_history[-5:]  # Last 5 errors
        ])

        # Get any run hints that might help
        learning_context = self._get_learning_context_for_phase(phase)
        hints_summary = "\n".join([
            f"- {hint}" for hint in learning_context.get("run_hints", [])[:3]
        ])

        replan_prompt = f"""You are a senior software architect. A phase in our automated build system has failed repeatedly with the same error pattern. Your task is to analyze the failures and provide a revised implementation approach.

## Original Phase Specification
**Phase**: {phase_name}
**Description**: {original_description}
**Category**: {phase.get('task_category', 'general')}
**Complexity**: {phase.get('complexity', 'medium')}

## Error Pattern Detected
**Flaw Type**: {flaw_type}
**Recent Errors**:
{error_summary}

## Learning Hints from Earlier Phases
{hints_summary if hints_summary else "(No hints available)"}

## Your Task
Analyze why the original approach kept failing and provide a REVISED description that:
1. Addresses the root cause of the repeated failures
2. Uses a different implementation strategy if needed
3. Includes specific guidance to avoid the detected error pattern
4. Keeps the same overall goal but changes HOW to achieve it

## Output Format
Provide ONLY the revised description text. Do not include JSON, markdown headers, or explanations.
Just the new description that should replace the original.
"""

        try:
            # Use LlmService to invoke planner (use strongest model for replanning)
            if not self.llm_service:
                logger.error("[Re-Plan] LlmService not initialized")
                return None

            # Get the anthropic client directly for re-planning
            import os

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("[Re-Plan] ANTHROPIC_API_KEY not set for re-planning")
                return None

            # Use Claude for re-planning (strongest model)
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",  # Use strong model for re-planning
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": replan_prompt}
                ]
            )

            revised_description = response.content[0].text.strip()

            if not revised_description or len(revised_description) < 20:
                logger.error("[Re-Plan] LLM returned empty or too-short revision")
                return None

            # Create revised phase spec
            revised_phase = phase.copy()
            revised_phase["description"] = revised_description
            revised_phase["_original_description"] = original_description
            revised_phase["_revision_reason"] = f"Approach flaw: {flaw_type}"
            revised_phase["_revision_timestamp"] = time.time()

            logger.info(f"[Re-Plan] Successfully revised phase {phase_id}")
            logger.info(f"[Re-Plan] Original: {original_description[:100]}...")
            logger.info(f"[Re-Plan] Revised: {revised_description[:100]}...")

            # Store and track
            self._phase_revised_specs[phase_id] = revised_phase
            self._phase_revised_specs[f"_replan_count_{phase_id}"] = self._get_replan_count(phase_id) + 1

            # Clear error history for fresh start with new approach
            self._phase_error_history[phase_id] = []

            # Record this re-planning event
            log_build_event(
                event_type="PHASE_REPLANNED",
                description=f"Phase {phase_id} replanned due to {flaw_type}. Original: '{original_description[:50]}...' -> Revised approach applied.",
                deliverables=[f"Run: {self.run_id}", f"Phase: {phase_id}", f"Flaw: {flaw_type}"],
                project_slug=self._get_project_slug()
            )

            return revised_phase

        except Exception as e:
            logger.error(f"[Re-Plan] Failed to revise phase: {e}")
            return None

    def _get_phase_spec_for_execution(self, phase: Dict) -> Dict:
        """
        Get the phase specification to use for execution.

        Returns the revised spec if one exists, otherwise the original.
        """
        phase_id = phase.get("phase_id")
        if phase_id in self._phase_revised_specs:
            logger.info(f"[Re-Plan] Using revised spec for {phase_id}")
            return self._phase_revised_specs[phase_id]
        return phase

    def _execute_phase_with_recovery(self, phase: Dict, attempt_index: int = 0) -> Tuple[bool, str]:
        """Inner phase execution with error handling and model escalation support"""
        phase_id = phase.get("phase_id")

        try:
            # Step 1: Execute with Builder using LlmService
            logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...")

            # Load repository context for Builder
            file_context = self._load_repository_context(phase)
            logger.info(f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context")

            # Load learning context (Stage 0A hints + Stage 0B rules)
            learning_context = self._get_learning_context_for_phase(phase)
            project_rules = learning_context.get("project_rules", [])
            run_hints = learning_context.get("run_hints", [])

            if project_rules or run_hints:
                logger.info(f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints")

            # Use LlmService for complexity-based model selection with escalation
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase,
                file_context=file_context,
                max_tokens=None,  # Let ModelRouter decide based on phase config
                project_rules=project_rules,  # Stage 0B: Persistent project rules
                run_hints=run_hints,  # Stage 0A: Within-run hints from earlier phases
                run_id=self.run_id,
                phase_id=phase_id,
                run_context={},  # TODO: Pass model_overrides if specified in run config
                attempt_index=attempt_index,  # Pass attempt for model escalation
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")
                self._post_builder_result(phase_id, builder_result)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # Post builder result to API
            self._post_builder_result(phase_id, builder_result)

            # Step 2: Apply patch first (so we can run CI on it)
            logger.info(f"[{phase_id}] Step 2/5: Applying patch...")

            # Import and use GovernedApplyPath for actual patch application
            from pathlib import Path
            from autopack.governed_apply import GovernedApplyPath

            governed_apply = GovernedApplyPath(workspace=Path(self.workspace))
            patch_success, error_msg = governed_apply.apply_patch(builder_result.patch_content)

            if not patch_success:
                logger.error(f"[{phase_id}] Failed to apply patch to filesystem: {error_msg}")
                self._update_phase_status(phase_id, "FAILED")
                return False, "PATCH_FAILED"

            logger.info(f"[{phase_id}] Patch applied successfully to filesystem")

            # Step 3: Run CI checks on the applied code
            logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
            ci_result = self._run_ci_checks(phase_id, phase)

            # Step 4: Review with Auditor using LlmService (with real CI results)
            logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")

            # Use LlmService for complexity-based model selection with escalation, usage tracking, and quality gate
            # Note: project_rules and run_hints were already loaded for Builder above
            auditor_result = self.llm_service.execute_auditor_review(
                patch_content=builder_result.patch_content,
                phase_spec=phase,
                max_tokens=None,  # Let ModelRouter decide
                project_rules=project_rules,  # Stage 0B: Persistent project rules
                run_hints=run_hints,  # Stage 0A: Within-run hints from earlier phases
                run_id=self.run_id,
                phase_id=phase_id,
                run_context={},  # TODO: Pass model_overrides if specified
                ci_result=ci_result,  # Now passing real CI results!
                coverage_delta=0.0,  # TODO: Calculate actual coverage delta
                attempt_index=attempt_index,  # Pass attempt for model escalation
            )

            logger.info(f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, "
                       f"issues={len(auditor_result.issues_found)}")

            # Post auditor result to API
            self._post_auditor_result(phase_id, auditor_result)

            # Step 5: Apply Quality Gate (with real CI results)
            logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
            quality_report = self.quality_gate.assess_phase(
                phase_id=phase_id,
                phase_spec=phase,
                auditor_result={
                    "approved": auditor_result.approved,
                    "issues_found": auditor_result.issues_found,
                },
                ci_result=ci_result,  # Now passing real CI results!
                coverage_delta=0.0,  # TODO: Calculate actual coverage delta
                patch_content=builder_result.patch_content,
                files_changed=None,  # TODO: Extract from builder result
            )

            logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")

            # Check if blocked (due to CI failure or other issues)
            if quality_report.is_blocked():
                logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
                for issue in quality_report.issues:
                    logger.warning(f"  - {issue}")
                # Note: Patch is already applied - in future we could rollback here
                # For now, mark as blocked but leave changes (human review needed)
                self._update_phase_status(phase_id, "BLOCKED")
                return False, "BLOCKED"

            # Update phase status to COMPLETE
            self._update_phase_status(phase_id, "COMPLETE")
            logger.info(f"[{phase_id}] Phase completed successfully")

            # Log build event to CONSOLIDATED_BUILD.md
            try:
                phase_name = phase.get("name", phase_id)
                builder_tokens = getattr(builder_result, 'tokens_used', 0)
                log_build_event(
                    event_type="PHASE_COMPLETE",
                    description=f"Phase {phase_id} ({phase_name}) completed. Builder: {builder_tokens} tokens. Auditor: {'approved' if auditor_result.approved else 'rejected'} ({len(auditor_result.issues_found)} issues). Quality: {quality_report.quality_level}",
                    deliverables=[f"Run: {self.run_id}", f"Phase: {phase_id}"],
                    token_usage={"builder": builder_tokens},
                    project_slug=self._get_project_slug()
                )
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to log build event: {e}")

            return True, "COMPLETE"

        except Exception as e:
            logger.error(f"[{phase_id}] Execution failed: {e}")

            # Log ALL exceptions to debug journal for tracking
            log_error(
                error_signature=f"Phase {phase_id} inner execution failure",
                symptom=f"{type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Unhandled exception in _execute_phase_with_recovery",
                priority="HIGH"
            )

            self._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

    def _load_repository_context(self, phase: Dict) -> Dict:
        """Load repository files for Claude Builder context

        Simple heuristic-based file loading:
        - Load key configuration files (package.json, setup.py, etc.)
        - Load Python files from src/backend directories
        - Load recently changed files
        - Limit total file count to avoid context bloat

        Args:
            phase: Phase specification

        Returns:
            Dict with 'files' key containing list of {path, content} dicts
        """
        workspace = Path(self.workspace)
        files_to_load = []
        max_files = 30  # Limit context size

        # Priority 1: Key config files (always include if they exist)
        priority_files = [
            "package.json",
            "setup.py",
            "requirements.txt",
            "pyproject.toml",
            "README.md",
            ".gitignore"
        ]

        for filename in priority_files:
            filepath = workspace / filename
            if filepath.exists() and filepath.is_file():
                try:
                    content = filepath.read_text(encoding='utf-8', errors='ignore')
                    files_to_load.append({
                        "path": str(filepath.relative_to(workspace)),
                        "content": content[:10000]  # Limit file size
                    })
                except Exception as e:
                    logger.warning(f"Failed to read {filepath}: {e}")

        # Priority 2: Source files from common directories
        source_dirs = ["src", "backend", "app", "lib"]
        for source_dir in source_dirs:
            dir_path = workspace / source_dir
            if not dir_path.exists():
                continue

            # Load Python files
            for py_file in dir_path.rglob("*.py"):
                if len(files_to_load) >= max_files:
                    break
                if py_file.is_file() and "__pycache__" not in str(py_file):
                    try:
                        content = py_file.read_text(encoding='utf-8', errors='ignore')
                        files_to_load.append({
                            "path": str(py_file.relative_to(workspace)),
                            "content": content[:10000]
                        })
                    except Exception as e:
                        logger.warning(f"Failed to read {py_file}: {e}")

        logger.debug(f"Loaded {len(files_to_load)} repository files for context")

        # Transform to OpenAI Builder format: {"existing_files": {path: content}}
        existing_files = {}
        for file_dict in files_to_load:
            existing_files[file_dict["path"]] = file_dict["content"]

        return {"existing_files": existing_files}

    def _post_builder_result(self, phase_id: str, result: BuilderResult):
        """POST builder result to Autopack API

        Args:
            phase_id: Phase ID
            result: Builder result from llm_client.BuilderResult dataclass
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/builder_result"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Map llm_client.BuilderResult to builder_schemas.BuilderResult
        # Parse patch statistics using GovernedApplyPath
        from pathlib import Path
        from autopack.governed_apply import GovernedApplyPath

        governed_apply = GovernedApplyPath(workspace=Path(self.workspace))
        files_changed, lines_added, lines_removed = governed_apply.parse_patch_stats(result.patch_content or "")

        payload = {
            "phase_id": phase_id,
            "run_id": self.run_id,
            "patch_content": result.patch_content,
            "files_changed": files_changed,
            "lines_added": lines_added,
            "lines_removed": lines_removed,
            "builder_attempts": 1,
            "tokens_used": result.tokens_used,
            "duration_minutes": 0.0,  # TODO: Track actual duration
            "probe_results": [],  # TODO: Integrate with governed_apply probe system
            "suggested_issues": [],  # TODO: Parse from builder_messages
            "status": "success" if result.success else "failed",
            "notes": "\n".join(result.builder_messages) if result.builder_messages else (result.error or ""),
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)

            # Phase 2.3: Handle 422 validation errors separately
            if response.status_code == 422:
                error_detail = response.json().get("detail", "Patch validation failed")
                logger.error(f"[{phase_id}] Patch validation failed (422): {error_detail}")
                logger.info(f"[{phase_id}] Phase 2.3: Validation errors indicate malformed patch - LLM should regenerate")

                # Log validation failures to debug journal
                log_error(
                    error_signature=f"Patch validation failure (422)",
                    symptom=f"Phase {phase_id}: {error_detail}",
                    run_id=self.run_id,
                    phase_id=phase_id,
                    suspected_cause="LLM generated malformed patch - needs regeneration",
                    priority="MEDIUM"
                )

                # TODO: Implement automatic retry with LLM correction
                raise requests.exceptions.HTTPError(f"Patch validation failed: {error_detail}", response=response)

            response.raise_for_status()
            logger.debug(f"Posted builder result for phase {phase_id}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to post builder result: {e}")

            # Log API failures to debug journal
            log_error(
                error_signature="API failure: POST builder_result",
                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM"
            )

    def _post_auditor_result(self, phase_id: str, result: AuditorResult):
        """POST auditor result to Autopack API

        Args:
            phase_id: Phase ID
            result: Auditor result from llm_client.AuditorResult dataclass
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/auditor_result"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Map llm_client.AuditorResult to builder_schemas.AuditorResult
        # Convert issues_found from List[Dict] to List[BuilderSuggestedIssue]
        formatted_issues = []
        for issue in result.issues_found:
            formatted_issues.append({
                "issue_key": issue.get("issue_key", "unknown"),
                "severity": issue.get("severity", "medium"),
                "source": issue.get("source", "auditor"),
                "category": issue.get("category", "general"),
                "evidence_refs": issue.get("evidence_refs", []),
                "description": issue.get("description", ""),
            })

        payload = {
            "phase_id": phase_id,
            "run_id": self.run_id,
            "review_notes": "\n".join(result.auditor_messages) if result.auditor_messages else (result.error or ""),
            "issues_found": formatted_issues,
            "suggested_patches": [],  # TODO: Parse from auditor_messages if available
            "auditor_attempts": 1,
            "tokens_used": result.tokens_used,
            "recommendation": "approve" if result.approved else "revise",
            "confidence": "medium",  # TODO: Parse confidence if available
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug(f"Posted auditor result for phase {phase_id}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to post auditor result: {e}")

            # Log API failures to debug journal
            log_error(
                error_signature="API failure: POST auditor_result",
                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM"
            )

    def _get_project_slug(self) -> str:
        """Extract project slug from run_id or workspace

        Returns:
            Project slug for archive_consolidator (e.g., 'file-organizer-app-v1')
        """
        # Try to extract from run_id (format: projectname-phase2-xxx or fileorg-xxx)
        if "fileorg" in self.run_id.lower() or "file-organizer" in self.run_id.lower():
            return "file-organizer-app-v1"

        # Default to Autopack framework
        return "autopack"

    def _run_ci_checks(self, phase_id: str, phase: Dict) -> Dict[str, Any]:
        """Run CI checks (pytest) after patch application

        Executes pytest on the workspace and returns structured results.

        Args:
            phase_id: Phase ID for logging
            phase: Phase specification

        Returns:
            Dict with CI results:
            {
                "passed": bool,
                "tests_run": int,
                "tests_passed": int,
                "tests_failed": int,
                "tests_error": int,
                "duration_seconds": float,
                "output": str (truncated),
                "error": str (if any)
            }
        """
        logger.info(f"[{phase_id}] Running CI checks (pytest)...")

        # Determine test directory based on project
        project_slug = self._get_project_slug()
        if project_slug == "file-organizer-app-v1":
            # FileOrganizer has tests in src/backend/tests/
            test_paths = ["src/backend/tests/", "tests/backend/"]
        else:
            # Autopack framework tests
            test_paths = ["tests/"]

        # Find first existing test path
        test_dir = None
        for path in test_paths:
            full_path = Path(self.workspace) / path
            if full_path.exists():
                test_dir = path
                break

        if not test_dir:
            logger.warning(f"[{phase_id}] No test directory found, skipping CI checks")
            return {
                "passed": True,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": 0.0,
                "output": "No test directory found",
                "error": None,
                "skipped": True
            }

        # Build pytest command
        # Use JSON output for easier parsing
        cmd = [
            sys.executable, "-m", "pytest",
            test_dir,
            "-v",
            "--tb=line",
            "-q",
            "--no-header",
            f"--timeout=60",  # Per-test timeout
        ]

        # Set environment for subprocess
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(self.workspace) / "src")
        env["TESTING"] = "1"
        env["PYTHONUTF8"] = "1"

        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute total timeout
                env=env
            )
            duration = time.time() - start_time

            output = result.stdout + result.stderr
            # Truncate output to prevent memory issues
            if len(output) > 10000:
                output = output[:5000] + "\n\n... (truncated) ...\n\n" + output[-5000:]

            # Parse pytest output to extract counts
            tests_run = 0
            tests_passed = 0
            tests_failed = 0
            tests_error = 0
            import re

            # Look for summary line like "5 passed, 2 failed, 1 error in 1.23s"
            # Also handle "X tests collected, Y errors" for collection errors
            for line in output.split("\n"):
                line_lower = line.lower()

                # Check for collection errors first (e.g., "4 errors during collection")
                collection_error_match = re.search(r"(\d+)\s+errors?\s+during\s+collection", line_lower)
                if collection_error_match:
                    tests_error = int(collection_error_match.group(1))
                    continue

                # Check for "X tests collected" to get baseline
                collected_match = re.search(r"(\d+)\s+tests?\s+collected", line_lower)
                if collected_match:
                    tests_run = int(collected_match.group(1))
                    continue

                # Standard summary line parsing
                if "passed" in line_lower or "failed" in line_lower or ("error" in line_lower and "during collection" not in line_lower):
                    # Extract numbers from summary line
                    passed_match = re.search(r"(\d+)\s+passed", line_lower)
                    failed_match = re.search(r"(\d+)\s+failed", line_lower)
                    error_match = re.search(r"(\d+)\s+errors?(?!\s+during)", line_lower)

                    if passed_match:
                        tests_passed = int(passed_match.group(1))
                    if failed_match:
                        tests_failed = int(failed_match.group(1))
                    if error_match:
                        tests_error = int(error_match.group(1))

            tests_run = tests_passed + tests_failed + tests_error
            passed = result.returncode == 0

            # [Self-Troubleshoot] Detect suspicious 0/0/0 as potential collection error
            # If pytest runs but reports 0 tests, something is likely wrong
            no_tests_detected = (tests_run == 0 and tests_passed == 0 and
                                tests_failed == 0 and tests_error == 0)

            if no_tests_detected and result.returncode != 0:
                # Pytest failed but we couldn't parse any test counts
                # This usually indicates a collection error or import failure
                logger.warning(f"[{phase_id}] CI detected possible collection error - "
                             f"pytest failed (code {result.returncode}) but no test counts found")
                # Mark as failed even if return code was 0, and add specific error
                passed = False
                error_msg = "Possible test collection error - no tests were detected"

                # Try to extract actual error from output
                if "ImportError" in output or "ModuleNotFoundError" in output:
                    error_msg = "Import error during test collection"
                elif "SyntaxError" in output:
                    error_msg = "Syntax error during test collection"
                elif "no tests ran" in output.lower():
                    error_msg = "No tests ran - check test discovery configuration"

            elif no_tests_detected and passed:
                # Pytest "passed" but found no tests - this is suspicious
                logger.warning(f"[{phase_id}] CI suspicious result - pytest passed but 0 tests detected")
                # Don't fail, but flag it in the result
                error_msg = "Warning: pytest reported success but no tests were executed"
            else:
                error_msg = None if passed else f"pytest exited with code {result.returncode}"

            ci_result = {
                "passed": passed,
                "tests_run": tests_run,
                "tests_passed": tests_passed,
                "tests_failed": tests_failed,
                "tests_error": tests_error,
                "duration_seconds": round(duration, 2),
                "output": output,
                "error": error_msg,
                "skipped": False,
                "suspicious_zero_tests": no_tests_detected  # New flag for visibility
            }

            if passed:
                logger.info(f"[{phase_id}] CI checks PASSED: {tests_passed}/{tests_run} tests passed in {duration:.1f}s")
            else:
                logger.warning(f"[{phase_id}] CI checks FAILED: {tests_passed}/{tests_run} passed, {tests_failed} failed, {tests_error} errors")

            return ci_result

        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"[{phase_id}] CI checks TIMEOUT after {duration:.1f}s")
            return {
                "passed": False,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": round(duration, 2),
                "output": "",
                "error": "pytest timed out after 300 seconds",
                "skipped": False
            }
        except Exception as e:
            duration = time.time() - start_time
            logger.error(f"[{phase_id}] CI checks ERROR: {e}")
            return {
                "passed": False,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": round(duration, 2),
                "output": "",
                "error": str(e),
                "skipped": False
            }

    def _update_phase_status(self, phase_id: str, status: str):
        """Update phase status via API

        Uses the /runs/{run_id}/phases/{phase_id}/update_status endpoint.

        Args:
            phase_id: Phase ID
            status: New status (QUEUED, EXECUTING, COMPLETE, FAILED, BLOCKED)
        """
        try:
            url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/update_status"
            response = requests.post(
                url,
                json={"state": status},
                headers={"Content-Type": "application/json"},
                timeout=30
            )
            response.raise_for_status()
            logger.info(f"Updated phase {phase_id} status to {status}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to update phase {phase_id} status: {e}")

    def _force_mark_phase_failed(self, phase_id: str) -> bool:
        """
        [Self-Troubleshoot] Force mark a phase as FAILED directly in database.

        This bypasses the API when it's returning errors, ensuring we can
        progress past stuck phases.

        Returns:
            bool: True if successfully updated, False otherwise
        """
        # Try direct database update first (more reliable than API)
        try:
            from autopack.models import Phase, PhaseState

            # Expire all cached objects to get fresh data
            self.db_session.expire_all()

            phase = self.db_session.query(Phase).filter(
                Phase.phase_id == phase_id,
                Phase.run_id == self.run_id
            ).first()

            if phase:
                phase.state = PhaseState.FAILED
                self.db_session.commit()
                # Force flush to ensure write is complete
                self.db_session.flush()
                logger.info(f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED in database")
                return True
            else:
                logger.warning(f"[Self-Troubleshoot] Phase {phase_id} not found in database")
        except Exception as e:
            logger.error(f"[Self-Troubleshoot] Failed to force-mark phase in database: {e}")
            self.db_session.rollback()

        # Try API as fallback (with retries)
        for attempt in range(3):
            try:
                self._update_phase_status(phase_id, "FAILED")
                logger.info(f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED via API (attempt {attempt + 1})")
                return True
            except Exception as e:
                logger.warning(f"[Self-Troubleshoot] API update attempt {attempt + 1} failed: {e}")
                time.sleep(1)

        logger.error(f"[Self-Troubleshoot] All attempts to mark phase {phase_id} as FAILED have failed")
        return False

    def run_autonomous_loop(
        self,
        poll_interval: int = 10,
        max_iterations: Optional[int] = None
    ):
        """Main autonomous execution loop

        Args:
            poll_interval: Seconds to wait between polling for next phase
            max_iterations: Maximum number of phases to execute (None = unlimited)
        """
        logger.info("Starting autonomous execution loop...")
        logger.info(f"Poll interval: {poll_interval}s")
        if max_iterations:
            logger.info(f"Max iterations: {max_iterations}")

        # Initialize infrastructure
        self._init_infrastructure()

        iteration = 0
        phases_executed = 0
        phases_failed = 0
        while True:
            # Check iteration limit
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations}), stopping")
                break

            iteration += 1

            # Fetch run status
            logger.info(f"Iteration {iteration}: Fetching run status...")
            try:
                run_data = self.get_run_status()
            except Exception as e:
                logger.error(f"Failed to fetch run status: {e}")
                logger.info(f"Waiting {poll_interval}s before retry...")
                time.sleep(poll_interval)
                continue

            # Phase 1.6-1.7: Detect and reset stale EXECUTING phases
            try:
                self._detect_and_reset_stale_phases(run_data)
            except Exception as e:
                logger.warning(f"Stale phase detection failed: {e}")
                # Continue even if stale detection fails

            # Get next queued phase
            next_phase = self.get_next_queued_phase(run_data)

            if not next_phase:
                logger.info("No more QUEUED phases, execution complete")
                break

            phase_id = next_phase.get("phase_id")
            logger.info(f"Next phase: {phase_id}")

            # [Self-Troubleshoot] Check if phase was escalated/skipped
            if phase_id in self._skipped_phases:
                # Track skip attempts to prevent infinite loops
                skip_attempts_key = f"_skip_attempts_{phase_id}"
                skip_attempts = getattr(self, skip_attempts_key, 0) + 1
                setattr(self, skip_attempts_key, skip_attempts)

                if skip_attempts > 10:
                    logger.error(f"[FATAL] Phase {phase_id} stuck after 10 skip attempts. Aborting run.")
                    break

                logger.warning(f"[Escalation] Skipping phase {phase_id} - previously escalated (attempt {skip_attempts})")
                # Force update phase status to FAILED in database directly
                if self._force_mark_phase_failed(phase_id):
                    # Success - wait for database sync
                    time.sleep(2)
                else:
                    logger.error(f"[Escalation] Could not mark {phase_id} as FAILED, waiting 5s before retry")
                    time.sleep(5)
                phases_failed += 1
                continue

            # Execute phase
            success, status = self.execute_phase(next_phase)

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
                phases_executed += 1
                # Reset failure count on success
                self._phase_failure_counts[phase_id] = 0
            else:
                logger.warning(f"Phase {phase_id} finished with status: {status}")
                phases_failed += 1

                # [Self-Troubleshoot] Track consecutive failures and escalate
                self._phase_failure_counts[phase_id] = self._phase_failure_counts.get(phase_id, 0) + 1
                failure_count = self._phase_failure_counts[phase_id]

                if failure_count >= self.MAX_PHASE_FAILURES:
                    logger.critical(
                        f"[ESCALATION] Phase {phase_id} failed {failure_count} times consecutively. "
                        f"Skipping phase and continuing to next. Manual intervention required."
                    )
                    self._skipped_phases.add(phase_id)

                    # Log escalation to debug journal
                    from autopack.debug_journal import log_escalation
                    try:
                        log_escalation(
                            error_category="PHASE_FAILURE",
                            error_count=failure_count,
                            threshold=self.MAX_PHASE_FAILURES,
                            reason=f"Phase '{phase_id}' failed {failure_count} consecutive times with status '{status}'",
                            run_id=self.run_id,
                            phase_id=phase_id
                        )
                    except Exception as e:
                        logger.warning(f"Failed to log escalation: {e}")

                    # Force mark phase as failed
                    self._force_mark_phase_failed(phase_id)

            # Wait before next iteration
            if max_iterations is None or iteration < max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                time.sleep(poll_interval)

        logger.info("Autonomous execution loop finished")

        # Log run completion summary to CONSOLIDATED_BUILD.md
        try:
            log_build_event(
                event_type="RUN_COMPLETE",
                description=f"Run {self.run_id} completed. Phases: {phases_executed} successful, {phases_failed} failed. Total iterations: {iteration}",
                deliverables=[f"Run ID: {self.run_id}", f"Successful: {phases_executed}", f"Failed: {phases_failed}"],
                project_slug=self._get_project_slug()
            )
        except Exception as e:
            logger.warning(f"Failed to log run completion: {e}")

        # Learning Pipeline: Promote hints to persistent rules (Stage 0B)
        try:
            project_id = self._get_project_slug()
            promoted_count = promote_hints_to_rules(self.run_id, project_id)
            if promoted_count > 0:
                logger.info(f"Learning Pipeline: Promoted {promoted_count} hints to persistent project rules")
                # Mark that rules have changed for future planning updates
                self._mark_rules_updated(project_id, promoted_count)
            else:
                logger.info("Learning Pipeline: No hints qualified for promotion (need 2+ occurrences)")
        except Exception as e:
            logger.warning(f"Failed to promote hints to rules: {e}")


def main():
    """Main entry point with CLI argument parsing"""
    parser = argparse.ArgumentParser(
        description="Autonomous executor for Autopack runs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Execute an existing run
  python autonomous_executor.py --run-id fileorg-phase2-beta

  # With custom API URL
  python autonomous_executor.py --run-id my-run --api-url http://localhost:8000

  # Limit to 3 phases
  python autonomous_executor.py --run-id my-run --max-iterations 3

  # Disable dual auditor
  python autonomous_executor.py --run-id my-run --no-dual-auditor

Environment Variables:
  OPENAI_API_KEY       OpenAI API key (required if using OpenAI)
  ANTHROPIC_API_KEY    Anthropic API key (required if using Anthropic)
  AUTOPACK_API_KEY     Autopack API key (optional)
  AUTOPACK_API_URL     Autopack API URL (default: http://localhost:8000)
        """
    )

    # Required arguments
    parser.add_argument(
        "--run-id",
        required=True,
        help="Autopack run ID to execute"
    )

    # Optional arguments
    parser.add_argument(
        "--api-url",
        default=os.getenv("AUTOPACK_API_URL", "http://localhost:8000"),
        help="Autopack API URL (default: http://localhost:8000)"
    )

    parser.add_argument(
        "--api-key",
        default=os.getenv("AUTOPACK_API_KEY"),
        help="Autopack API key (default: $AUTOPACK_API_KEY)"
    )

    parser.add_argument(
        "--openai-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key (default: $OPENAI_API_KEY)"
    )

    parser.add_argument(
        "--anthropic-key",
        default=os.getenv("ANTHROPIC_API_KEY"),
        help="Anthropic API key (default: $ANTHROPIC_API_KEY)"
    )

    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Workspace root directory (default: current directory)"
    )

    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between polling for next phase (default: 10)"
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of phases to execute (default: unlimited)"
    )

    parser.add_argument(
        "--no-dual-auditor",
        action="store_true",
        help="Disable dual auditor mode (use single auditor)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create executor
    try:
        executor = AutonomousExecutor(
            run_id=args.run_id,
            api_url=args.api_url,
            api_key=args.api_key,
            openai_key=args.openai_key,
            anthropic_key=args.anthropic_key,
            workspace=args.workspace,
            use_dual_auditor=not args.no_dual_auditor,
        )
    except ValueError as e:
        logger.error(f"Failed to initialize executor: {e}")
        sys.exit(1)

    # Run autonomous loop
    try:
        executor.run_autonomous_loop(
            poll_interval=args.poll_interval,
            max_iterations=args.max_iterations
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
