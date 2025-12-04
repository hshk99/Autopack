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
    GLM_API_KEY: GLM (Zhipu AI) API key (primary provider)
    GLM_API_BASE: GLM API base URL (optional, defaults to https://open.bigmodel.cn/api/paas/v4)
    ANTHROPIC_API_KEY: Anthropic API key (for Claude models)
    OPENAI_API_KEY: OpenAI API key (fallback for gpt-* models)
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
import shlex
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.quality_gate import QualityGate
from autopack.config import settings
from autopack.llm_client import BuilderResult, AuditorResult
from autopack.error_recovery import (
    ErrorRecoverySystem, get_error_recovery, safe_execute,
    DoctorRequest, DoctorResponse, DoctorContextSummary,
    DOCTOR_MIN_BUILDER_ATTEMPTS, DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO,
)
from autopack.llm_service import LlmService
from autopack.debug_journal import log_error, log_fix, mark_resolved
from autopack.archive_consolidator import log_build_event, log_feature
from autopack.learned_rules import (
    load_project_rules,
    get_active_rules_for_phase,
    get_relevant_hints_for_phase,
    promote_hints_to_rules,
    save_run_hint,
)
from autopack.journal_reader import get_recent_prevention_rules
from autopack.health_checks import run_health_checks, HealthCheckResult


# Configure logging
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


# =============================================================================
# EXECUTE_FIX CONSTANTS (Phase 3 - GPT_RESPONSE9)
# =============================================================================
# Configuration for Doctor's execute_fix action - direct infrastructure fixes.
# Disabled by default (user opt-in via models.yaml).

MAX_EXECUTE_FIX_PER_PHASE = 1  # Maximum execute_fix attempts per phase

# Allowed fix types (v1: git, file, python; later: docker, shell)
ALLOWED_FIX_TYPES = {"git", "file", "python"}

# Command whitelists by fix_type (regex patterns)
ALLOWED_FIX_COMMANDS = {
    "git": [
        r"^git\s+checkout\s+",           # git checkout <file>/<branch>
        r"^git\s+reset\s+--hard\s+HEAD", # git reset --hard HEAD
        r"^git\s+stash\s*$",             # git stash
        r"^git\s+stash\s+pop$",          # git stash pop
        r"^git\s+clean\s+-fd$",          # git clean -fd
        r"^git\s+merge\s+--abort$",      # git merge --abort
        r"^git\s+rebase\s+--abort$",     # git rebase --abort
    ],
    "file": [
        r"^rm\s+-f\s+",                  # rm -f <file> (single file)
        r"^mkdir\s+-p\s+",               # mkdir -p <dir>
        r"^mv\s+",                       # mv <src> <dst>
        r"^cp\s+",                       # cp <src> <dst>
    ],
    "python": [
        r"^pip\s+install\s+",            # pip install <package>
        r"^pip\s+uninstall\s+-y\s+",     # pip uninstall -y <package>
        r"^python\s+-m\s+pip\s+install", # python -m pip install <package>
    ],
}

# Banned metacharacters (security: prevent command injection)
BANNED_METACHARACTERS = [
    ";", "&&", "||", "`", "$(", "${", ">", ">>", "<", "|", "\n", "\r",
]

# Banned command prefixes (never execute)
BANNED_COMMAND_PREFIXES = [
    "sudo", "su ", "rm -rf /", "dd if=", "chmod 777", "mkfs", ":(){ :", "shutdown",
    "reboot", "poweroff", "halt", "init 0", "init 6",
]


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
        run_type: str = "project_build",
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
            run_type: Run type - 'project_build' (default), 'autopack_maintenance',
                      'autopack_upgrade', or 'self_repair'. Maintenance types allow
                      modification of src/autopack/ and config/ paths.
        """
        # Load environment variables from .env for CLI runs
        load_dotenv()

        self.run_id = run_id
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.workspace = workspace
        self.use_dual_auditor = use_dual_auditor
        self.run_type = run_type

        # Store API keys (GLM is primary, Anthropic for Claude, OpenAI as fallback)
        self.glm_key = os.getenv("GLM_API_KEY")
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")

        # Validate at least one API key is available
        if not self.glm_key and not self.anthropic_key and not self.openai_key:
            raise ValueError(
                "At least one LLM API key required: GLM_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
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

        # Initialize database for usage tracking (share DB config with API server)
        db_url = settings.database_url
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

        # NEW: Load BuilderOutputConfig once (per IMPLEMENTATION_PLAN2.md Phase 2.1)
        from autopack.builder_config import BuilderOutputConfig
        config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
        self.builder_output_config = BuilderOutputConfig.from_yaml(config_path)
        logger.info(
            f"Loaded BuilderOutputConfig: max_lines_for_full_file={self.builder_output_config.max_lines_for_full_file}, "
            f"max_lines_hard_limit={self.builder_output_config.max_lines_hard_limit}"
        )
        
        # NEW: Initialize FileSizeTelemetry (per IMPLEMENTATION_PLAN2.md Phase 2.1)
        from autopack.file_size_telemetry import FileSizeTelemetry
        self.file_size_telemetry = FileSizeTelemetry(Path(self.workspace))

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
        self._run_replan_count: int = 0  # Global replan count for this run
        self.REPLAN_TRIGGER_THRESHOLD = 2  # Trigger re-planning after this many same-type failures
        self.MAX_REPLANS_PER_PHASE = 1  # Maximum re-planning attempts per phase
        self.MAX_REPLANS_PER_RUN = 5  # Maximum re-planning attempts per run (prevents pathological projects)

        # [Goal Anchoring] Per GPT_RESPONSE27: Prevent context drift during re-planning
        # PhaseGoal-lite implementation - lightweight anchor + telemetry (Phase 1)
        self._phase_original_intent: Dict[str, str] = {}  # phase_id -> one-line intent extracted from description
        self._phase_original_description: Dict[str, str] = {}  # phase_id -> original description before any replanning
        self._phase_replan_history: Dict[str, List[Dict]] = {}  # phase_id -> list of {attempt, description, reason, alignment}
        self._run_replan_telemetry: List[Dict] = []  # All replans in this run for telemetry

        # [Run-Level Health Budget] Prevent infinite retry loops (GPT_RESPONSE5 recommendation)
        self._run_http_500_count: int = 0  # Count of HTTP 500 errors in this run
        self._run_patch_failure_count: int = 0  # Count of patch failures in this run
        self._run_total_failures: int = 0  # Total recoverable failures in this run
        self.MAX_HTTP_500_PER_RUN = 10  # Stop run after this many 500 errors
        self.MAX_PATCH_FAILURES_PER_RUN = 15  # Stop run after this many patch failures
        self.MAX_TOTAL_FAILURES_PER_RUN = 25  # Stop run after this many total failures

        # [Doctor Integration] Per GPT_RESPONSE8 Section 4 recommendations
        # Per-phase Doctor context tracking
        self._doctor_context_by_phase: Dict[str, DoctorContextSummary] = {}
        self._doctor_calls_by_phase: Dict[str, int] = {}  # phase_id -> doctor call count
        self._last_doctor_response_by_phase: Dict[str, DoctorResponse] = {}
        self._last_error_category_by_phase: Dict[str, str] = {}  # Track error categories for is_complex_failure
        self._distinct_error_cats_by_phase: Dict[str, set] = {}  # Track distinct error categories per phase
        # Run-level Doctor budgets
        self._run_doctor_calls: int = 0  # Total Doctor calls this run
        self._run_doctor_strong_calls: int = 0  # Strong-model Doctor calls this run
        self._run_doctor_infra_calls: int = 0  # Doctor calls for infra_error failures
        self.MAX_DOCTOR_CALLS_PER_PHASE = 2  # Per GPT_RESPONSE8 recommendation
        self.MAX_DOCTOR_CALLS_PER_RUN = 10  # Prevent runaway Doctor invocations
        self.MAX_DOCTOR_STRONG_CALLS_PER_RUN = 5  # Limit expensive strong-model calls
        self.MAX_DOCTOR_INFRA_CALLS_PER_RUN = 5  # Separate cap for infra-related diagnoses
        # Builder hint from Doctor (to pass to next Builder attempt)
        self._builder_hint_by_phase: Dict[str, str] = {}

        # [Phase 3: execute_fix] Track execute_fix attempts per phase
        self._execute_fix_by_phase: Dict[str, int] = {}  # phase_id -> execute_fix count
        # Configuration for execute_fix (user opt-in via models.yaml)
        self._allow_execute_fix: bool = False  # Disabled by default, load from config

        # Phase 1.4-1.5: Run proactive startup checks (from DEBUG_JOURNAL.md)
        self._run_startup_checks()

        # [GPT_RESPONSE26] Startup validation for token_soft_caps
        self._validate_config_at_startup()

        # T0 Health Checks: quick environment validation before executing phases
        t0_results = run_health_checks("t0")
        for result in t0_results:
            status = "PASSED" if result.passed else "FAILED"
            logger.info(
                f"[HealthCheck:T0] {result.check_name}: {status} "
                f"({result.duration_ms}ms) - {result.message}"
            )

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

    def _validate_config_at_startup(self):
        """
        Run startup validations from config_loader.
        
        Per GPT_RESPONSE26: Validate token_soft_caps configuration at startup.
        """
        try:
            import yaml
            config_path = Path(__file__).parent.parent.parent / "config" / "models.yaml"
            if config_path.exists():
                with open(config_path) as f:
                    config = yaml.safe_load(f)
                    from autopack.config_loader import validate_token_soft_caps
                    validate_token_soft_caps(config)
        except Exception as e:
            logger.debug(f"[Config] Startup validation skipped: {e}")

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
            self.project_rules = load_project_rules(project_id)
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
        # Get project_id first (it's a string, not a list)
        project_id = self._get_project_slug()
        relevant_rules = get_active_rules_for_phase(
            project_id,  # Pass project_id string, not self.project_rules list
            phase
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
            rules = load_project_rules(project_id)

            # Update marker
            marker = {
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "last_run_id": self.run_id,
                "promoted_this_run": promoted_count,
                "total_rules": len(rules),
                "update_history": existing.get("update_history", [])[-9:] + [
                    {
                        "run_id": self.run_id,
                        "promoted": promoted_count,
                        "timestamp": datetime.now(timezone.utc).isoformat()
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
                headers["X-API-Key"] = self.api_key

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
        scope_config = phase.get("scope") or {}
        allowed_scope_paths = self._derive_allowed_paths_from_scope(scope_config)
        logger.info(f"Executing phase: {phase_id}")

        # [Goal Anchoring] Initialize goal anchor for this phase on first execution
        # Per GPT_RESPONSE27: Store original intent before any re-planning occurs
        self._initialize_phase_goal_anchor(phase)

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
                return self._execute_phase_with_recovery(
                    phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_scope_paths,
                )

            try:
                success, status = self.error_recovery.execute_with_retry(
                    func=_execute_phase_inner,
                    operation_name=f"Phase execution: {phase_id}",
                    max_retries=1  # Only 1 retry for transient errors within an attempt
                )

                if success:
                    # Success: no need to record attempt outcome here; LlmService
                    # already tracked model usage and selection metadata.

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
                # Update health budget tracking
                self._run_total_failures += 1
                if status == "PATCH_FAILED":
                    self._run_patch_failure_count += 1

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

                # [Doctor Integration] Invoke Doctor for diagnosis after sufficient failures
                doctor_response = self._invoke_doctor(
                    phase=phase,
                    error_category=failure_outcome,
                    builder_attempts=attempt_index + 1,
                    last_patch=None,  # TODO: pass last patch from builder_result
                    patch_errors=[],  # TODO: pass patch errors if available
                    logs_excerpt=f"Status: {status}, Attempt: {attempt_index + 1}",
                )

                if doctor_response:
                    # Handle Doctor's recommended action
                    action_taken, should_continue = self._handle_doctor_action(
                        phase=phase,
                        response=doctor_response,
                        attempt_index=attempt_index,
                    )

                    if not should_continue:
                        # Doctor recommended skipping, fatal, or rollback
                        return False, status

                    if action_taken == "replan":
                        # Doctor recommended replanning - it's already been handled
                        attempt_index = 0
                        setattr(self, attempt_key, 0)
                        continue

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
                        self._run_replan_count += 1  # Increment global replan counter
                        logger.info(f"[{phase_id}] Re-planning successful (run total: {self._run_replan_count}/{self.MAX_REPLANS_PER_RUN}). Restarting with revised approach.")
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

                # Report detailed error context for debugging
                from .error_reporter import report_error
                report_error(
                    error=e,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    component="executor",
                    operation="execute_phase",
                    context_data={
                        "attempt_index": attempt_index,
                        "max_attempts": max_attempts,
                        "phase_description": phase.get("description", "")[:200],
                        "phase_complexity": phase.get("complexity"),
                        "phase_task_category": phase.get("task_category"),
                    }
                )

                # Update health budget tracking
                self._run_total_failures += 1
                error_str = str(e).lower()
                if "500" in error_str or "internal server error" in error_str:
                    self._run_http_500_count += 1

                # Mid-Run Re-Planning: Record error for approach flaw detection
                self._record_phase_error(
                    phase=phase,
                    error_type="infra_error",
                    error_details=str(e),
                    attempt_index=attempt_index
                )

                # [Doctor Integration] Invoke Doctor for diagnosis on exceptions
                doctor_response = self._invoke_doctor(
                    phase=phase,
                    error_category="infra_error",
                    builder_attempts=attempt_index + 1,
                    logs_excerpt=f"Exception: {type(e).__name__}: {str(e)[:500]}",
                )

                if doctor_response:
                    action_taken, should_continue = self._handle_doctor_action(
                        phase=phase,
                        response=doctor_response,
                        attempt_index=attempt_index,
                    )

                    if not should_continue:
                        return False, "FAILED"

                    if action_taken == "replan":
                        attempt_index = 0
                        setattr(self, attempt_key, 0)
                        continue

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
                        self._run_replan_count += 1  # Increment global replan counter
                        logger.info(f"[{phase_id}] Re-planning successful (run total: {self._run_replan_count}/{self.MAX_REPLANS_PER_RUN}). Restarting with revised approach.")
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
            # Structured REPLAN-TRIGGER logging per GPT recommendation
            logger.info(
                f"[REPLAN-TRIGGER] reason=fatal_error type={latest_error['error_type']} "
                f"phase={phase_id} attempt={len(errors)}"
            )
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
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={trigger_threshold}"
            )
            return error_type

        # Check message similarity between consecutive errors
        messages = [e.get("error_details", "") for e in recent_errors]

        # Skip if messages are too short
        if all(len(m) < min_message_length for m in messages):
            logger.debug(f"[Re-Plan] Messages too short for similarity check ({phase_id})")
            # Fall back to type-only check
            logger.info(
                f"[REPLAN-TRIGGER] reason=repeated_error_short_msg type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={trigger_threshold}"
            )
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
                f"[REPLAN-TRIGGER] reason=similar_errors type={error_type} "
                f"phase={phase_id} attempt={len(errors)} count={trigger_threshold} similarity_threshold={similarity_threshold}"
            )
            return error_type

        logger.debug(f"[Re-Plan] No approach flaw for {phase_id}: messages not similar enough")
        return None

    def _get_replan_count(self, phase_id: str) -> int:
        """Get how many times a phase has been re-planned."""
        return self._phase_revised_specs.get(f"_replan_count_{phase_id}", 0)

    # =========================================================================
    # GOAL ANCHORING METHODS (per GPT_RESPONSE27)
    # =========================================================================

    def _extract_one_line_intent(self, description: str) -> str:
        """
        Extract a concise one-line intent from a phase description.
        
        Per GPT_RESPONSE27: The original_intent should be a short, clear statement
        of WHAT the phase achieves (not HOW it achieves it).
        
        Args:
            description: Full phase description
            
        Returns:
            One-line intent statement (first sentence, capped at 200 chars)
        """
        if not description:
            return ""
        
        # Get first sentence (ends with . ! or ?)
        first_sentence_match = re.match(r'^[^.!?]*[.!?]', description.strip())
        if first_sentence_match:
            intent = first_sentence_match.group(0).strip()
        else:
            # No sentence ending found, use first 200 chars
            intent = description.strip()[:200]
            if len(description.strip()) > 200:
                intent += "..."
        
        # Cap at 200 chars
        if len(intent) > 200:
            intent = intent[:197] + "..."
        
        return intent

    def _initialize_phase_goal_anchor(self, phase: Dict) -> None:
        """
        Initialize goal anchoring for a phase on first execution.
        
        Per GPT_RESPONSE27 Phase 1 Implementation: Store original intent and description
        before any re-planning occurs.
        
        Args:
            phase: Phase specification dict
        """
        phase_id = phase.get("phase_id")
        if not phase_id:
            return
        
        # Only initialize once (on first execution)
        if phase_id not in self._phase_original_intent:
            description = phase.get("description", "")
            self._phase_original_intent[phase_id] = self._extract_one_line_intent(description)
            self._phase_original_description[phase_id] = description
            self._phase_replan_history[phase_id] = []
            
            logger.debug(
                f"[GoalAnchor] Initialized for {phase_id}: intent='{self._phase_original_intent[phase_id][:50]}...'"
            )

    def _detect_scope_narrowing(self, original: str, revised: str) -> bool:
        """
        Detect obvious scope narrowing using heuristics.
        
        Per GPT_RESPONSE27: Fast pre-filter to detect when revision reduces scope.
        
        Args:
            original: Original phase description
            revised: Revised phase description
            
        Returns:
            True if scope narrowing is detected
        """
        if not original or not revised:
            return False
        
        # Heuristic 1: Significant length shrinkage (>50%)
        if len(revised) < len(original) * 0.5:
            logger.debug("[GoalAnchor] Scope narrowing detected: length shrinkage")
            return True
        
        # Heuristic 2: Scope-reducing keywords
        scope_reducing_keywords = [
            "only", "just", "skip", "ignore", "defer", "later",
            "simplified", "minimal", "basic", "stub", "placeholder",
            "without", "except", "excluding", "partial"
        ]
        
        original_lower = original.lower()
        revised_lower = revised.lower()
        
        for keyword in scope_reducing_keywords:
            # Check if keyword was added in revision
            if keyword in revised_lower and keyword not in original_lower:
                logger.debug(f"[GoalAnchor] Scope narrowing detected: added keyword '{keyword}'")
                return True
        
        return False

    def _classify_replan_alignment(
        self,
        original_intent: str,
        revised_description: str
    ) -> Dict[str, Any]:
        """
        Classify alignment of revised description vs original intent.
        
        Per GPT_RESPONSE27: Use LLM to semantically compare original intent with
        revised approach to detect goal drift.
        
        Args:
            original_intent: One-line intent from original description
            revised_description: New description after re-planning
            
        Returns:
            Dict with {"alignment": "same_scope|narrower|broader|different_domain", "notes": "..."}
        """
        # First, apply fast heuristic pre-filter
        if self._detect_scope_narrowing(original_intent, revised_description):
            return {
                "alignment": "narrower",
                "notes": "Heuristic detection: revision appears to reduce scope"
            }
        
        # For Phase 1, we use simple heuristics + logging (no LLM call)
        # Per GPT_RESPONSE27: Full semantic classification is Phase 2
        
        # Simple keyword-based classification
        revised_lower = revised_description.lower()
        
        # Check for scope expansion
        expansion_keywords = ["also", "additionally", "expand", "enhance", "add more", "including"]
        has_expansion = any(kw in revised_lower for kw in expansion_keywords)
        
        # Check for domain change (different technology/approach)
        if has_expansion:
            return {
                "alignment": "broader",
                "notes": "Revision appears to expand scope"
            }
        
        # Default: assume same scope (conservative for Phase 1)
        return {
            "alignment": "same_scope",
            "notes": "No obvious scope change detected (Phase 1 heuristic)"
        }

    def _record_replan_telemetry(
        self,
        phase_id: str,
        attempt: int,
        original_description: str,
        revised_description: str,
        reason: str,
        alignment: Dict[str, Any],
        success: bool
    ) -> None:
        """
        Record re-planning telemetry for monitoring and analysis.
        
        Per GPT_RESPONSE27: Track replan_count, alignment, and outcomes.
        
        Args:
            phase_id: Phase identifier
            attempt: Re-plan attempt number
            original_description: Description before revision
            revised_description: Description after revision
            reason: Why re-planning was triggered
            alignment: Alignment classification result
            success: Whether the re-planning resulted in eventual phase success
        """
        telemetry_record = {
            "run_id": self.run_id,
            "phase_id": phase_id,
            "attempt": attempt,
            "timestamp": time.time(),
            "reason": reason,
            "alignment": alignment.get("alignment", "unknown"),
            "alignment_notes": alignment.get("notes", ""),
            "original_description_preview": original_description[:100],
            "revised_description_preview": revised_description[:100],
            "success": success,
        }
        
        # Add to phase-level history
        if phase_id not in self._phase_replan_history:
            self._phase_replan_history[phase_id] = []
        self._phase_replan_history[phase_id].append(telemetry_record)
        
        # Add to run-level telemetry
        self._run_replan_telemetry.append(telemetry_record)
        
        # Log for observability
        logger.info(
            f"[GoalAnchor] REPLAN_TELEMETRY: run_id={self.run_id} phase_id={phase_id} "
            f"attempt={attempt} alignment={alignment.get('alignment')} "
            f"replan_count_phase={len(self._phase_replan_history.get(phase_id, []))} "
            f"replan_count_run={len(self._run_replan_telemetry)}"
        )

    def _should_trigger_replan(self, phase: Dict) -> Tuple[bool, Optional[str]]:
        """
        Determine if re-planning should be triggered for a phase.

        Returns:
            Tuple of (should_replan: bool, detected_flaw_type: str or None)
        """
        phase_id = phase.get("phase_id")

        # Check global run-level replan limit (prevents pathological projects)
        if self._run_replan_count >= self.MAX_REPLANS_PER_RUN:
            logger.info(f"[Re-Plan] Global max replans ({self.MAX_REPLANS_PER_RUN}) reached for this run - no more replans allowed")
            return False, None

        # Check if we've exceeded max replans for this specific phase
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
        
        Per GPT_RESPONSE27: Now includes Goal Anchoring to prevent context drift:
        - Stores and references original_intent
        - Includes hard constraint in prompt
        - Classifies alignment of revision
        - Records telemetry for monitoring

        Args:
            phase: Original phase specification
            flaw_type: Detected flaw type
            error_history: History of errors for this phase

        Returns:
            Revised phase specification dict, or None if revision failed
        """
        phase_id = phase.get("phase_id")
        phase_name = phase.get("name", phase_id)
        current_description = phase.get("description", "")
        
        # [Goal Anchoring] Initialize if this is the first replan for this phase
        self._initialize_phase_goal_anchor(phase)
        
        # Get the true original intent (before any replanning)
        original_intent = self._phase_original_intent.get(phase_id, "")
        original_description = self._phase_original_description.get(phase_id, current_description)
        replan_attempt = len(self._phase_replan_history.get(phase_id, [])) + 1

        logger.info(f"[Re-Plan] Revising approach for {phase_id} due to {flaw_type} (attempt {replan_attempt})")
        logger.info(f"[GoalAnchor] Original intent: {original_intent[:100]}...")

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

        # [Goal Anchoring] Per GPT_RESPONSE27: Include original_intent with HARD CONSTRAINT
        replan_prompt = f"""You are a senior software architect. A phase in our automated build system has failed repeatedly with the same error pattern. Your task is to analyze the failures and provide a revised implementation approach.

## Original Phase Specification
**Phase**: {phase_name}
**Description**: {current_description}
**Category**: {phase.get('task_category', 'general')}
**Complexity**: {phase.get('complexity', 'medium')}

## Error Pattern Detected
**Flaw Type**: {flaw_type}
**Recent Errors**:
{error_summary}

## Learning Hints from Earlier Phases
{hints_summary if hints_summary else "(No hints available)"}

## CRITICAL CONSTRAINT - GOAL ANCHORING
The revised approach MUST still achieve this core goal:
**Original Intent**: {original_intent}

Do NOT reduce scope, skip functionality, or change what the phase achieves.
Only change HOW it achieves the goal, not WHAT it achieves.

## Your Task
Analyze why the current approach kept failing and provide a REVISED description that:
1. MAINTAINS the original intent and scope (CRITICAL - no scope reduction)
2. Addresses the root cause of the repeated failures
3. Uses a different implementation strategy if needed
4. Includes specific guidance to avoid the detected error pattern

## Output Format
Provide ONLY the revised description text. Do not include JSON, markdown headers, or explanations.
Just the new description that should replace the current one while preserving the original goal.
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
                # Record failed replan telemetry
                self._record_replan_telemetry(
                    phase_id=phase_id,
                    attempt=replan_attempt,
                    original_description=original_description,
                    revised_description="",
                    reason=flaw_type,
                    alignment={"alignment": "failed", "notes": "LLM returned empty revision"},
                    success=False
                )
                return None

            # [Goal Anchoring] Classify alignment of revision vs original intent
            alignment = self._classify_replan_alignment(original_intent, revised_description)
            
            # Log alignment classification
            logger.info(
                f"[GoalAnchor] Alignment classification: {alignment.get('alignment')} - {alignment.get('notes')}"
            )
            
            # [Goal Anchoring] Warn if scope appears narrowed (but don't block in Phase 1)
            if alignment.get("alignment") == "narrower":
                logger.warning(
                    f"[GoalAnchor] WARNING: Revision appears to narrow scope for {phase_id}. "
                    f"Original intent: '{original_intent[:50]}...' "
                    f"This may indicate goal drift."
                )

            # Create revised phase spec
            revised_phase = phase.copy()
            revised_phase["description"] = revised_description
            revised_phase["_original_description"] = original_description
            revised_phase["_original_intent"] = original_intent  # [Goal Anchoring]
            revised_phase["_revision_reason"] = f"Approach flaw: {flaw_type}"
            revised_phase["_revision_timestamp"] = time.time()
            revised_phase["_revision_alignment"] = alignment  # [Goal Anchoring]

            logger.info(f"[Re-Plan] Successfully revised phase {phase_id}")
            logger.info(f"[Re-Plan] Original: {original_description[:100]}...")
            logger.info(f"[Re-Plan] Revised: {revised_description[:100]}...")

            # Store and track
            self._phase_revised_specs[phase_id] = revised_phase
            self._phase_revised_specs[f"_replan_count_{phase_id}"] = self._get_replan_count(phase_id) + 1

            # Clear error history for fresh start with new approach
            self._phase_error_history[phase_id] = []

            # [Goal Anchoring] Record telemetry (success will be updated later if phase succeeds)
            self._record_replan_telemetry(
                phase_id=phase_id,
                attempt=replan_attempt,
                original_description=original_description,
                revised_description=revised_description,
                reason=flaw_type,
                alignment=alignment,
                success=False  # Will be updated if phase eventually succeeds
            )

            # Record this re-planning event
            log_build_event(
                event_type="PHASE_REPLANNED",
                description=f"Phase {phase_id} replanned due to {flaw_type}. Alignment: {alignment.get('alignment')}. Original: '{original_description[:50]}...' -> Revised approach applied.",
                deliverables=[f"Run: {self.run_id}", f"Phase: {phase_id}", f"Flaw: {flaw_type}", f"Alignment: {alignment.get('alignment')}"],
                project_slug=self._get_project_slug()
            )

            return revised_phase

        except Exception as e:
            logger.error(f"[Re-Plan] Failed to revise phase: {e}")
            # Record failed replan telemetry
            self._record_replan_telemetry(
                phase_id=phase_id,
                attempt=replan_attempt,
                original_description=original_description,
                revised_description="",
                reason=flaw_type,
                alignment={"alignment": "error", "notes": str(e)},
                success=False
            )
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

    # =========================================================================
    # DOCTOR INTEGRATION (GPT_RESPONSE8 Implementation)
    # =========================================================================

    def _get_health_budget(self) -> Dict[str, int]:
        """
        Get current health budget as a single source of truth.

        Per GPT_RESPONSE8 Section 2.2: Single health budget source.
        """
        return {
            "http_500": self._run_http_500_count,
            "patch_failures": self._run_patch_failure_count,
            "total_failures": self._run_total_failures,
            "total_cap": self.MAX_TOTAL_FAILURES_PER_RUN,
        }

    def _should_invoke_doctor(self, phase_id: str, builder_attempts: int, error_category: str) -> bool:
        """
        Determine if Doctor should be invoked for this failure.

        Per GPT_RESPONSE8 Section 4 (Guardrails):
        - Only invoke after DOCTOR_MIN_BUILDER_ATTEMPTS failures
        - Respect per-phase and run-level Doctor call limits
        - Invoke when health budget is near limit

        Args:
            phase_id: Phase identifier
            builder_attempts: Number of builder attempts so far
            error_category: Category of the current error

        Returns:
            True if Doctor should be invoked
        """
        is_infra = error_category == "infra_error"

        # Check minimum builder attempts (only for non-infra failures)
        if not is_infra and builder_attempts < DOCTOR_MIN_BUILDER_ATTEMPTS:
            logger.debug(
                f"[Doctor] Not invoking: builder_attempts={builder_attempts} < {DOCTOR_MIN_BUILDER_ATTEMPTS}"
            )
            return False

        # Check per-phase Doctor call limit
        phase_doctor_calls = self._doctor_calls_by_phase.get(phase_id, 0)
        if phase_doctor_calls >= self.MAX_DOCTOR_CALLS_PER_PHASE:
            logger.info(
                f"[Doctor] Not invoking: per-phase limit reached "
                f"({phase_doctor_calls}/{self.MAX_DOCTOR_CALLS_PER_PHASE})"
            )
            return False

        # Check run-level Doctor call limit (overall)
        if self._run_doctor_calls >= self.MAX_DOCTOR_CALLS_PER_RUN:
            logger.info(
                f"[Doctor] Not invoking: run-level limit reached "
                f"({self._run_doctor_calls}/{self.MAX_DOCTOR_CALLS_PER_RUN})"
            )
            return False

        # Additional cap for infra-related diagnostics
        if is_infra and self._run_doctor_infra_calls >= self.MAX_DOCTOR_INFRA_CALLS_PER_RUN:
            logger.info(
                f"[Doctor] Not invoking: run-level infra limit reached "
                f"({self._run_doctor_infra_calls}/{self.MAX_DOCTOR_INFRA_CALLS_PER_RUN})"
            )
            return False

        # Check health budget - invoke Doctor if near limit
        health_ratio = self._run_total_failures / max(self.MAX_TOTAL_FAILURES_PER_RUN, 1)
        if health_ratio >= DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO:
            logger.info(f"[Doctor] Health budget near limit ({health_ratio:.2f}), invoking Doctor")
            return True

        # Default: invoke Doctor for diagnosis
        return True

    def _build_doctor_context(self, phase_id: str, error_category: str) -> DoctorContextSummary:
        """
        Build Doctor context summary for model routing decisions.

        Per GPT_RESPONSE8 Section 2.1: Per-phase Doctor context tracking.

        Args:
            phase_id: Phase identifier
            error_category: Current error category

        Returns:
            DoctorContextSummary for model selection
        """
        # Track distinct error categories for this phase
        if phase_id not in self._distinct_error_cats_by_phase:
            self._distinct_error_cats_by_phase[phase_id] = set()
        self._distinct_error_cats_by_phase[phase_id].add(error_category)

        # Get prior Doctor response if any
        prior_response = self._last_doctor_response_by_phase.get(phase_id)
        prior_action = prior_response.action if prior_response else None
        prior_confidence = prior_response.confidence if prior_response else None

        return DoctorContextSummary(
            distinct_error_categories_for_phase=len(self._distinct_error_cats_by_phase[phase_id]),
            prior_doctor_action=prior_action,
            prior_doctor_confidence=prior_confidence,
        )

    def _invoke_doctor(
        self,
        phase: Dict,
        error_category: str,
        builder_attempts: int,
        last_patch: Optional[str] = None,
        patch_errors: Optional[List[Dict]] = None,
        logs_excerpt: str = "",
    ) -> Optional[DoctorResponse]:
        """
        Invoke the Autopack Doctor to diagnose a phase failure.

        Per GPT_RESPONSE8 Section 3: Doctor invocation flow.

        Args:
            phase: Phase specification
            error_category: Category of the current error
            builder_attempts: Number of builder attempts so far
            last_patch: Last patch content (if any)
            patch_errors: Patch validation errors (if any)
            logs_excerpt: Relevant log excerpt

        Returns:
            DoctorResponse if Doctor was invoked, None otherwise
        """
        phase_id = phase.get("phase_id")

        # Check if we should invoke Doctor
        if not self._should_invoke_doctor(phase_id, builder_attempts, error_category):
            return None

        # Check LlmService availability
        if not self.llm_service:
            logger.warning("[Doctor] LlmService not available, skipping Doctor invocation")
            return None

        # Build request
        request = DoctorRequest(
            phase_id=phase_id,
            error_category=error_category,
            builder_attempts=builder_attempts,
            health_budget=self._get_health_budget(),
            last_patch=last_patch,
            patch_errors=patch_errors or [],
            logs_excerpt=logs_excerpt,
            run_id=self.run_id,
        )

        # Build context summary
        ctx_summary = self._build_doctor_context(phase_id, error_category)

        try:
            # Invoke Doctor via LlmService
            response = self.llm_service.execute_doctor(
                request=request,
                ctx_summary=ctx_summary,
                run_id=self.run_id,
                phase_id=phase_id,
                allow_escalation=True,
            )

            # Update tracking
            self._doctor_calls_by_phase[phase_id] = self._doctor_calls_by_phase.get(phase_id, 0) + 1
            self._run_doctor_calls += 1
            if error_category == "infra_error":
                self._run_doctor_infra_calls += 1
            self._last_doctor_response_by_phase[phase_id] = response
            self._doctor_context_by_phase[phase_id] = ctx_summary

            # Store builder hint if provided
            if response.builder_hint:
                self._builder_hint_by_phase[phase_id] = response.builder_hint

            logger.info(
                f"[Doctor] Diagnosis complete: action={response.action}, "
                f"confidence={response.confidence:.2f}, phase_calls={self._doctor_calls_by_phase[phase_id]}, "
                f"run_calls={self._run_doctor_calls}"
            )

            return response

        except Exception as e:
            logger.error(f"[Doctor] Invocation failed: {e}")
            return None

    def _handle_doctor_action(
        self,
        phase: Dict,
        response: DoctorResponse,
        attempt_index: int,
    ) -> Tuple[Optional[str], bool]:
        """
        Handle Doctor's recommended action.

        Per GPT_RESPONSE8 Section 3.3: Action handling in executor.

        Args:
            phase: Phase specification
            response: Doctor's response
            attempt_index: Current attempt index

        Returns:
            Tuple of (action_taken: str or None, should_continue_retry: bool)
            - action_taken: What was done ("retry_with_hint", "replan", "skip", "fatal", "rollback")
            - should_continue_retry: Whether to continue the retry loop
        """
        phase_id = phase.get("phase_id")
        action = response.action

        # Apply any provider-level recommendations from Doctor before
        # interpreting the high-level action.
        disable_providers = getattr(response, "disable_providers", None)
        if disable_providers and self.llm_service:
            for provider in disable_providers:
                try:
                    self.llm_service.model_router.disable_provider(
                        provider,
                        reason=f"Doctor recommendation for phase {phase_id}",
                    )
                except Exception as e:
                    logger.warning(f"[Doctor] Failed to disable provider {provider}: {e}")

        if action == "retry_with_fix":
            # Doctor has a hint for the next Builder attempt
            hint = response.builder_hint or "Review previous errors and try a different approach"
            self._builder_hint_by_phase[phase_id] = hint
            logger.info(f"[Doctor] Action: retry_with_fix - hint stored for next attempt")
            return "retry_with_hint", True  # Continue retry loop with hint

        elif action == "replan":
            # Trigger mid-run re-planning
            logger.info(f"[Doctor] Action: replan - triggering approach revision")
            # Get error history for context
            error_history = self._phase_error_history.get(phase_id, [])
            revised_phase = self._revise_phase_approach(
                phase,
                f"doctor_replan:{response.rationale[:50]}",
                error_history
            )
            if revised_phase:
                self._run_replan_count += 1
                logger.info(f"[Doctor] Replan successful, phase revised")
                return "replan", True  # Continue with revised approach
            else:
                logger.warning(f"[Doctor] Replan failed, continuing with original approach")
                return "replan_failed", True

        elif action == "skip_phase":
            # Skip this phase and continue to next
            logger.info(f"[Doctor] Action: skip_phase - marking phase as FAILED and continuing")
            self._skipped_phases.add(phase_id)
            self._update_phase_status(phase_id, "FAILED")
            return "skip", False  # Exit retry loop

        elif action == "mark_fatal":
            # Unrecoverable error - human intervention required
            logger.critical(
                f"[Doctor] Action: mark_fatal - phase {phase_id} requires human intervention. "
                f"Rationale: {response.rationale}"
            )
            # Log to debug journal
            log_error(
                error_signature=f"Doctor FATAL: {phase_id}",
                symptom=response.rationale,
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor diagnosed unrecoverable failure",
                priority="CRITICAL"
            )
            self._update_phase_status(phase_id, "FAILED")
            return "fatal", False  # Exit retry loop

        elif action == "rollback_run":
            # Rollback all changes and abort run
            logger.critical(
                f"[Doctor] Action: rollback_run - aborting run {self.run_id}. "
                f"Rationale: {response.rationale}"
            )
            # Log to debug journal
            log_error(
                error_signature=f"Doctor ROLLBACK: {self.run_id}",
                symptom=response.rationale,
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor recommended run rollback due to accumulated failures",
                priority="CRITICAL"
            )
            # TODO: Implement branch-based rollback (git reset to pre-run state)
            # For now, mark phase as failed and let run terminate
            self._update_phase_status(phase_id, "FAILED")
            return "rollback", False  # Exit retry loop

        elif action == "execute_fix":
            # Phase 3: Direct infrastructure fix (GPT_RESPONSE9)
            return self._handle_execute_fix(phase, response)

        else:
            logger.warning(f"[Doctor] Unknown action: {action}, treating as retry_with_fix")
            return "unknown", True

    def _get_builder_hint_for_phase(self, phase_id: str) -> Optional[str]:
        """Get any Doctor-provided hint for the next Builder attempt."""
        hint = self._builder_hint_by_phase.get(phase_id)
        if hint:
            # Clear after use to avoid reusing stale hints
            del self._builder_hint_by_phase[phase_id]
        return hint

    # =========================================================================
    # EXECUTE_FIX IMPLEMENTATION (Phase 3 - GPT_RESPONSE9)
    # =========================================================================

    def _validate_fix_commands(
        self,
        commands: List[str],
        fix_type: str
    ) -> Tuple[bool, List[str]]:
        """
        Validate fix commands against whitelist and security rules.

        Per GPT_RESPONSE9: Use shlex + regex + banned metacharacters.

        Args:
            commands: List of shell commands to validate
            fix_type: Type of fix ("git", "file", "python")

        Returns:
            Tuple of (is_valid: bool, errors: List[str])
        """
        errors = []

        # Check fix_type is allowed
        if fix_type not in ALLOWED_FIX_TYPES:
            errors.append(f"fix_type '{fix_type}' not in allowed types: {ALLOWED_FIX_TYPES}")
            return False, errors

        # Get whitelist patterns for this fix_type
        whitelist_patterns = ALLOWED_FIX_COMMANDS.get(fix_type, [])
        if not whitelist_patterns:
            errors.append(f"No whitelist patterns defined for fix_type '{fix_type}'")
            return False, errors

        for cmd in commands:
            # Check for banned command prefixes
            for banned in BANNED_COMMAND_PREFIXES:
                if cmd.strip().startswith(banned):
                    errors.append(f"Command '{cmd}' uses banned prefix '{banned}'")
                    continue

            # Check for banned metacharacters
            for char in BANNED_METACHARACTERS:
                if char in cmd:
                    errors.append(f"Command '{cmd}' contains banned metacharacter '{char}'")
                    continue

            # Validate against whitelist using shlex + regex
            try:
                # Use shlex to properly tokenize (handles quoted arguments)
                tokens = shlex.split(cmd)
            except ValueError as e:
                errors.append(f"Command '{cmd}' failed shlex parsing: {e}")
                continue

            # Check if command matches any whitelist pattern
            matched = False
            for pattern in whitelist_patterns:
                if re.match(pattern, cmd):
                    matched = True
                    break

            if not matched:
                errors.append(
                    f"Command '{cmd}' does not match any whitelist pattern for type '{fix_type}'"
                )

        return len(errors) == 0, errors

    def _handle_execute_fix(
        self,
        phase: Dict,
        response: DoctorResponse
    ) -> Tuple[Optional[str], bool]:
        """
        Handle Doctor's execute_fix action - direct infrastructure fixes.

        Per GPT_RESPONSE9:
        - One execute_fix attempt per phase
        - Validate commands against whitelist
        - Create git checkpoint before execution
        - Execute commands via subprocess
        - Run verify_command if provided

        Args:
            phase: Phase specification
            response: Doctor's response with fix_commands, fix_type, verify_command

        Returns:
            Tuple of (action_taken: str or None, should_continue_retry: bool)
        """
        phase_id = phase.get("phase_id")

        # Check if execute_fix is enabled (user opt-in)
        if not self._allow_execute_fix:
            logger.warning(
                f"[Doctor] execute_fix requested but disabled. "
                f"Enable via models.yaml: doctor.allow_execute_fix_global: true"
            )
            log_error(
                error_signature=f"execute_fix disabled: {phase_id}",
                symptom="execute_fix action requested but feature is disabled",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="User opt-in required via models.yaml",
                priority="HIGH"
            )
            # Fall back to retry_with_fix behavior
            hint = response.builder_hint or "Infrastructure fix needed but execute_fix disabled"
            self._builder_hint_by_phase[phase_id] = hint
            return "execute_fix_disabled", True

        # Check per-phase limit
        current_count = self._execute_fix_by_phase.get(phase_id, 0)
        if current_count >= MAX_EXECUTE_FIX_PER_PHASE:
            logger.warning(
                f"[Doctor] execute_fix limit reached for phase {phase_id} "
                f"({current_count}/{MAX_EXECUTE_FIX_PER_PHASE})"
            )
            # Fall back to mark_fatal since we can't fix it
            self._update_phase_status(phase_id, "FAILED")
            return "execute_fix_limit", False

        # Validate fix_commands and fix_type
        fix_commands = response.fix_commands or []
        fix_type = response.fix_type or ""
        verify_command = response.verify_command

        if not fix_commands:
            logger.warning(f"[Doctor] execute_fix requested but no fix_commands provided")
            return "execute_fix_no_commands", True

        # Validate commands
        is_valid, validation_errors = self._validate_fix_commands(fix_commands, fix_type)
        if not is_valid:
            logger.error(
                f"[Doctor] execute_fix command validation failed: {validation_errors}"
            )
            log_error(
                error_signature=f"execute_fix validation failed: {phase_id}",
                symptom=f"Commands failed validation: {validation_errors}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor suggested invalid/unsafe commands",
                priority="HIGH"
            )
            # Fall back to retry_with_fix
            hint = f"execute_fix validation failed: {validation_errors[0]}"
            self._builder_hint_by_phase[phase_id] = hint
            return "execute_fix_invalid", True

        # Create git checkpoint (commit) before executing
        logger.info(f"[Doctor] Creating git checkpoint before execute_fix...")
        try:
            checkpoint_result = subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=30
            )
            if checkpoint_result.returncode == 0:
                checkpoint_result = subprocess.run(
                    ["git", "commit", "-m", f"[Autopack] Pre-execute_fix checkpoint for {phase_id}"],
                    cwd=str(self.workspace),
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if checkpoint_result.returncode == 0:
                    logger.info(f"[Doctor] Git checkpoint created successfully")
                else:
                    # No changes to commit - that's OK
                    logger.info(f"[Doctor] No changes to checkpoint (clean state)")
        except Exception as e:
            logger.warning(f"[Doctor] Failed to create git checkpoint: {e}")

        # Execute fix commands
        logger.info(
            f"[Doctor] Executing {len(fix_commands)} fix commands (type: {fix_type})..."
        )
        self._execute_fix_by_phase[phase_id] = current_count + 1

        all_succeeded = True
        for i, cmd in enumerate(fix_commands):
            logger.info(f"[Doctor] Executing [{i+1}/{len(fix_commands)}]: {cmd}")
            try:
                # Execute in workspace directory
                result = subprocess.run(
                    cmd,
                    shell=True,  # Required for complex commands
                    cwd=str(self.workspace),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if result.returncode != 0:
                    logger.error(
                        f"[Doctor] Command failed (exit {result.returncode}): {result.stderr}"
                    )
                    all_succeeded = False
                    break
                else:
                    logger.info(f"[Doctor] Command succeeded: {result.stdout[:200]}")
            except subprocess.TimeoutExpired:
                logger.error(f"[Doctor] Command timed out: {cmd}")
                all_succeeded = False
                break
            except Exception as e:
                logger.error(f"[Doctor] Command execution error: {e}")
                all_succeeded = False
                break

        # Run verify_command if provided
        if all_succeeded and verify_command:
            logger.info(f"[Doctor] Running verify command: {verify_command}")
            try:
                verify_result = subprocess.run(
                    verify_command,
                    shell=True,
                    cwd=str(self.workspace),
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if verify_result.returncode != 0:
                    logger.warning(
                        f"[Doctor] Verify command failed: {verify_result.stderr}"
                    )
                    all_succeeded = False
                else:
                    logger.info(f"[Doctor] Verify command passed")
            except Exception as e:
                logger.warning(f"[Doctor] Verify command error: {e}")
                all_succeeded = False

        if all_succeeded:
            logger.info(f"[Doctor] execute_fix succeeded - continuing retry loop")
            log_fix(
                error_signature=f"execute_fix success: {phase_id}",
                fix_description=f"Executed {len(fix_commands)} commands: {fix_commands}",
                run_id=self.run_id,
                phase_id=phase_id,
                outcome="RESOLVED_BY_EXECUTE_FIX"
            )
            return "execute_fix_success", True  # Continue retry loop
        else:
            logger.warning(f"[Doctor] execute_fix failed - marking phase as failed")
            self._update_phase_status(phase_id, "FAILED")
            return "execute_fix_failed", False

    def _execute_phase_with_recovery(
        self,
        phase: Dict,
        attempt_index: int = 0,
        allowed_paths: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Inner phase execution with error handling and model escalation support"""
        phase_id = phase.get("phase_id")

        try:
            # Step 1: Execute with Builder using LlmService
            logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...")

            # Load repository context for Builder
            try:
                file_context = self._load_repository_context(phase)
                logger.info(f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context")

                # NEW: Validate scope configuration if present (GPT recommendation - Option C)
                scope_config = phase.get("scope")
                if scope_config and scope_config.get("paths"):
                    self._validate_scope_context(phase, file_context, scope_config)

            except TypeError as e:
                if "unsupported operand type(s) for /" in str(e) and "list" in str(e):
                    logger.error(f"[{phase_id}] Path/list error in context loading: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    # Return empty context to allow execution to continue
                    file_context = {"existing_files": {}}
                else:
                    raise

            # ============================================================================
            # NEW: Pre-flight file size validation (per IMPLEMENTATION_PLAN2.md Phase 2.1)
            # This is the PRIMARY fix for the truncation bug - prevents LLM from seeing
            # files >1000 lines in full-file mode
            # ============================================================================
            use_full_file_mode = True  # Default mode
            
            if file_context:
                config = self.builder_output_config
                files = file_context.get("existing_files", {})
                
                # Per GPT_RESPONSE15: Simplified 2-bucket policy
                # Bucket A: ≤1000 lines → full-file mode
                # Bucket B: >1000 lines → fail fast (read-only context)
                too_large = []  # Files >1000 lines - read-only context
                
                for file_path, content in files.items():
                    if not isinstance(content, str):
                        continue
                    line_count = content.count('\n') + 1
                    
                    # Bucket B: >1000 lines - mark as read-only context
                    if line_count > config.max_lines_hard_limit:
                        too_large.append((file_path, line_count))
                
                # For files >1000 lines: Mark as read-only context
                # These files can be READ but NOT modified
                # Per GPT_RESPONSE15: Fail fast with clear error until structured edit mode is implemented
                if too_large:
                    logger.warning(
                        f"[{phase_id}] Large files in context (read-only, >{config.max_lines_hard_limit} lines): "
                        f"{', '.join(p for p, _ in too_large)}"
                    )
                    # Record telemetry for each large file
                    for file_path, line_count in too_large:
                        self.file_size_telemetry.record_preflight_reject(
                            run_id=self.run_id,
                            phase_id=phase_id,
                            file_path=file_path,
                            line_count=line_count,
                            limit=config.max_lines_hard_limit,
                            bucket="B"  # Now just "too large" bucket
                        )
                    # Don't fail - these files can be read-only context
                    # Parser will enforce that LLM doesn't try to modify them
                
                # Per GPT_RESPONSE15: Diff mode is disabled, so all files ≤1000 use full-file mode
                # No need to check for needs_diff_mode or switch modes
                # Defensive check: If diff mode is somehow enabled, log loudly
                if config.legacy_diff_fallback_enabled:
                    logger.error(
                        f"[{phase_id}] WARNING: legacy_diff_fallback_enabled is True but should be False! "
                        f"Diff mode is fundamentally broken per GPT_RESPONSE15. "
                        f"All files ≤{config.max_lines_for_full_file} lines will use full-file mode."
                    )

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
                use_full_file_mode=use_full_file_mode,  # NEW: Pass mode from pre-flight check
                config=self.builder_output_config,  # NEW: Pass config for consistency
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")
                self._post_builder_result(phase_id, builder_result, allowed_paths)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # Post builder result to API
            self._post_builder_result(phase_id, builder_result, allowed_paths)

            # Step 2: Apply patch first (so we can run CI on it)
            logger.info(f"[{phase_id}] Step 2/5: Applying patch...")

            # NEW: Check if this is a structured edit (Stage 2) or regular patch
            if builder_result.edit_plan:
                # Structured edit mode (Stage 2) - per IMPLEMENTATION_PLAN3.md Phase 4
                from pathlib import Path
                from autopack.structured_edits import StructuredEditApplicator
                
                logger.info(f"[{phase_id}] Applying structured edit plan with {len(builder_result.edit_plan.operations)} operations")
                
                # Get file contents from context
                file_contents = {}
                if file_context:
                    file_contents = file_context.get("existing_files", {})
                
                # Apply structured edits
                applicator = StructuredEditApplicator(workspace=Path(self.workspace))
                edit_result = applicator.apply_edit_plan(
                    plan=builder_result.edit_plan,
                    file_contents=file_contents,
                    dry_run=False
                )
                
                if not edit_result.success:
                    error_msg = edit_result.error_message or f"{edit_result.operations_failed} operations failed"
                    logger.error(f"[{phase_id}] Failed to apply structured edits: {error_msg}")
                    self._update_phase_status(phase_id, "FAILED")
                    return False, "STRUCTURED_EDIT_FAILED"
                
                logger.info(f"[{phase_id}] Structured edits applied successfully ({edit_result.operations_applied} operations)")
                patch_success = True
                error_msg = None
            else:
                # Regular patch mode (full-file or diff)
                from pathlib import Path
                from autopack.governed_apply import GovernedApplyPath

                # Enable internal mode for maintenance run types
                is_maintenance_run = self.run_type in ["autopack_maintenance", "autopack_upgrade", "self_repair"]

                # NEW: Extract scope_paths for Option C Layer 2 validation
                scope_config = phase.get("scope")
                scope_paths = scope_config.get("paths", []) if scope_config else []

                governed_apply = GovernedApplyPath(
                    workspace=Path(self.workspace),
                    run_type=self.run_type,
                    autopack_internal_mode=is_maintenance_run,
                    scope_paths=scope_paths,  # NEW: Pass scope for validation
                    allowed_paths=allowed_paths or None,
                )
                # Per GPT_RESPONSE15: Pass full_file_mode=True since we're using full-file mode for all files ≤1000 lines
                patch_success, error_msg = governed_apply.apply_patch(
                    builder_result.patch_content,
                    full_file_mode=True
                )

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

            # [Goal Anchoring] Update replan telemetry to mark successful if this phase was replanned
            if phase_id in self._phase_replan_history and self._phase_replan_history[phase_id]:
                # Mark the most recent replan as successful
                for replan_record in reversed(self._phase_replan_history[phase_id]):
                    if not replan_record.get("success", False):
                        replan_record["success"] = True
                        logger.debug(
                            f"[GoalAnchor] Marked replan attempt {replan_record.get('attempt')} "
                            f"as successful for {phase_id}"
                        )
                        break  # Only update the most recent one

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
            import traceback
            error_traceback = traceback.format_exc()
            error_msg = str(e)
            
            # Check if this is the Path/list error we're tracking
            if "unsupported operand type(s) for /" in error_msg and "list" in error_msg:
                logger.error(f"[{phase_id}] Path/list TypeError detected:\n{error_msg}\nFull traceback:\n{error_traceback}")
            else:
                logger.error(f"[{phase_id}] Execution failed: {error_msg}\nTraceback:\n{error_traceback}")

            # Log ALL exceptions to debug journal for tracking
            log_error(
                error_signature=f"Phase {phase_id} inner execution failure",
                symptom=f"{type(e).__name__}: {error_msg}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Unhandled exception in _execute_phase_with_recovery",
                priority="HIGH"
            )

            self._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

    def _load_repository_context(self, phase: Dict) -> Dict:
        """Load repository files for Claude Builder context

        Smart context loading with two modes:
        1. Scope-aware: If phase has scope configuration, use ContextSelector
           to load only specified files (for external projects)
        2. Heuristic-based: Legacy mode with freshness guarantees
           (for autopack_maintenance without scope)

        Args:
            phase: Phase specification (may include scope config)

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        import subprocess
        import re

        # NEW: Check for scope configuration (GPT recommendation)
        scope_config = phase.get("scope")
        if scope_config and scope_config.get("paths"):
            # Use ContextSelector for scope-aware loading
            return self._load_scoped_context(phase, scope_config)

        # Fallback: Original heuristic-based loading for backward compatibility
        workspace = Path(self.workspace)
        loaded_paths = set()  # Track loaded paths to avoid duplicates
        existing_files = {}  # Final output format
        max_files = 40  # Increased limit to accommodate recently modified files

        def _load_file(filepath: Path) -> bool:
            """Load a single file if not already loaded. Returns True if loaded."""
            if len(existing_files) >= max_files:
                return False
            rel_path = str(filepath.relative_to(workspace))
            if rel_path in loaded_paths:
                return False
            if not filepath.exists() or not filepath.is_file():
                return False
            if "__pycache__" in rel_path or ".pyc" in rel_path:
                return False
            try:
                content = filepath.read_text(encoding='utf-8', errors='ignore')
                existing_files[rel_path] = content[:15000]  # Increased limit for important files
                loaded_paths.add(rel_path)
                return True
            except Exception as e:
                logger.warning(f"Failed to read {filepath}: {e}")
                return False

        # Priority 0: Recently modified files from git status (ALWAYS FRESH)
        # This ensures Builder sees the latest state after earlier phases applied patches
        recently_modified = []
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(workspace),
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split('\n'):
                    if line and len(line) > 3:
                        # Parse git status format: "XY filename" or "XY old -> new"
                        file_part = line[3:].strip()
                        if ' -> ' in file_part:
                            file_part = file_part.split(' -> ')[1]
                        if file_part:
                            recently_modified.append(file_part)
        except Exception as e:
            logger.debug(f"Could not get git status for fresh context: {e}")

        # Load recently modified files first (highest priority for freshness)
        modified_count = 0
        for rel_path in recently_modified[:15]:  # Limit to 15 recently modified files
            # Defensive check: ensure rel_path is a string
            if not isinstance(rel_path, str):
                logger.warning(f"[Context] Skipping non-string rel_path: {rel_path} (type: {type(rel_path)})")
                continue
            if not rel_path or not rel_path.strip():
                continue
            try:
                filepath = workspace / rel_path
                if _load_file(filepath):
                    modified_count += 1
            except (TypeError, ValueError) as e:
                logger.warning(f"[Context] Error processing rel_path '{rel_path}': {e}")
                continue

        if modified_count > 0:
            logger.info(f"[Context] Loaded {modified_count} recently modified files for fresh context")

        # Priority 1: Files mentioned in phase description
        # Extract file paths from description using regex
        phase_description = phase.get("description", "")
        phase_criteria = " ".join(phase.get("acceptance_criteria", []))
        combined_text = f"{phase_description} {phase_criteria}"

        # Match patterns like: src/autopack/file.py, config/models.yaml, etc.
        # Use non-capturing group (?:...) to get full match, not just extension
        file_patterns = re.findall(r'[a-zA-Z_][a-zA-Z0-9_/\\.-]*\.(?:py|yaml|json|ts|js|md)', combined_text)
        mentioned_count = 0
        for pattern in file_patterns[:10]:  # Limit to 10 mentioned files
            # Defensive check: ensure pattern is a string
            if not isinstance(pattern, str):
                logger.warning(f"[Context] Skipping non-string pattern: {pattern} (type: {type(pattern)})")
                continue
            # Additional safety: ensure pattern is not empty and doesn't contain path separators that would break
            if not pattern or not pattern.strip():
                continue
            try:
                # Try exact match first
                filepath = workspace / pattern
                if _load_file(filepath):
                    mentioned_count += 1
                    continue
                # Try finding in src/ or config/ directories
                for prefix in ["src/autopack/", "config/", "src/", ""]:
                    # Ensure prefix is a string (defensive)
                    if not isinstance(prefix, str):
                        continue
                    filepath = workspace / prefix / pattern
                    if _load_file(filepath):
                        mentioned_count += 1
                        break
            except (TypeError, ValueError) as e:
                logger.warning(f"[Context] Error processing pattern '{pattern}': {e}")
                continue

        if mentioned_count > 0:
            logger.info(f"[Context] Loaded {mentioned_count} files mentioned in phase description")

        # Priority 2: Key config files (always include if they exist)
        priority_files = [
            "package.json",
            "setup.py",
            "requirements.txt",
            "pyproject.toml",
            "README.md",
            ".gitignore"
        ]

        for filename in priority_files:
            _load_file(workspace / filename)

        # Priority 3: Source files from common directories
        source_dirs = ["src", "backend", "app", "lib"]
        for source_dir in source_dirs:
            dir_path = workspace / source_dir
            if not dir_path.exists():
                continue

            # Load Python files
            for py_file in dir_path.rglob("*.py"):
                if len(existing_files) >= max_files:
                    break
                _load_file(py_file)

        logger.info(f"[Context] Total: {len(existing_files)} files loaded for Builder context "
                   f"(modified={modified_count}, mentioned={mentioned_count})")

        return {"existing_files": existing_files}

    def _determine_workspace_root(self, scope_config: Dict) -> Path:
        """Determine workspace root based on scope configuration.

        For external projects (project_build), derive workspace from first scope path.
        For autopack_maintenance, use Autopack root.

        Args:
            scope_config: Scope configuration dict

        Returns:
            Workspace root Path
        """
        # For autopack_maintenance, always use self.workspace (Autopack root)
        if self.run_type in ["autopack_maintenance", "autopack_upgrade", "self_repair"]:
            return Path(self.workspace)

        # For project_build, derive workspace from first scope path
        scope_paths = scope_config.get("paths", [])
        if scope_paths:
            # Assuming scope paths are like: ".autonomous_runs/file-organizer-app-v1/backend/requirements.txt"
            # Extract project root: ".autonomous_runs/file-organizer-app-v1/"
            first_path = scope_paths[0]
            parts = Path(first_path).parts

            # Look for .autonomous_runs prefix
            if len(parts) >= 2 and parts[0] == ".autonomous_runs":
                project_root = Path(self.workspace) / parts[0] / parts[1]
                logger.info(f"[Scope] Workspace root determined: {project_root}")
                return project_root

        # Fallback to default workspace
        logger.warning(f"[Scope] Could not determine workspace from scope paths, using default: {self.workspace}")
        return Path(self.workspace)

    def _resolve_scope_target(
        self,
        scope_path: str,
        workspace_root: Path,
        *,
        must_exist: bool = False
    ) -> Optional[Tuple[Path, str]]:
        """
        Resolve a scope path to an absolute file/dir and builder-relative path.

        Args:
            scope_path: Path from scope configuration (can be relative or prefixed with .autonomous_runs)
            workspace_root: Project workspace root (from _determine_workspace_root)
            must_exist: If True, only return when the path exists on disk

        Returns:
            Tuple of (absolute_path, builder_relative_path) or None if outside workspace.
        """
        base_workspace = Path(self.workspace).resolve()
        workspace_root = workspace_root.resolve()
        path_obj = Path(scope_path.strip())

        candidates = []
        if path_obj.is_absolute():
            candidates.append(path_obj)
        else:
            candidates.append(base_workspace / path_obj)
            candidates.append(workspace_root / path_obj)

        seen = set()
        for candidate in candidates:
            resolved = candidate.resolve()
            key = str(resolved)
            if key in seen:
                continue
            seen.add(key)

            # Ensure target is under workspace root
            try:
                resolved.relative_to(workspace_root)
            except ValueError:
                continue

            if must_exist and not resolved.exists():
                continue

            try:
                rel_to_base = resolved.relative_to(base_workspace)
            except ValueError:
                continue

            rel_key = str(rel_to_base).replace("\\", "/")
            return resolved, rel_key

        return None

    def _derive_allowed_paths_from_scope(
        self,
        scope_config: Optional[Dict],
        workspace_root: Optional[Path] = None
    ) -> List[str]:
        """Derive allowed path prefixes for GovernedApply from scope configuration."""
        if not scope_config or not scope_config.get("paths"):
            return []

        workspace_root = workspace_root or self._determine_workspace_root(scope_config)
        base_workspace = Path(self.workspace).resolve()

        try:
            rel_prefix = workspace_root.resolve().relative_to(base_workspace)
        except ValueError:
            return []

        rel_str = str(rel_prefix).replace("\\", "/")
        if not rel_str.endswith("/"):
            rel_str += "/"

        return [rel_str]

    def _load_scoped_context(self, phase: Dict, scope_config: Dict) -> Dict:
        """Load context using scope configuration (GPT recommendation).

        Args:
            phase: Phase specification
            scope_config: Scope configuration with paths and read_only_context

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        workspace_root = self._determine_workspace_root(scope_config).resolve()
        base_workspace = Path(self.workspace).resolve()
        existing_files: Dict[str, str] = {}
        scope_metadata: Dict[str, Dict[str, Any]] = {}
        missing_files: List[str] = []

        def _normalize_rel_path(path_str: str) -> str:
            if not path_str:
                return path_str
            normalized = path_str.replace("\\", "/")
            while normalized.startswith("./"):
                normalized = normalized[2:]
            return normalized

        def _add_file(abs_path: Path, rel_key: str) -> None:
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
                existing_files[rel_key] = content
            except Exception as exc:
                logger.warning(f"[Scope] Failed to read {abs_path}: {exc}")

        # Load modifiable scope paths
        for scoped_path in scope_config.get("paths", []):
            resolved = self._resolve_scope_target(scoped_path, workspace_root, must_exist=False)
            if not resolved:
                missing_files.append(scoped_path)
                rel_key = _normalize_rel_path(scoped_path)
                scope_metadata[rel_key] = {"category": "modifiable", "missing": True}
                existing_files.setdefault(rel_key, "")
                continue
            abs_path, rel_key = resolved
            rel_key = _normalize_rel_path(rel_key)
            scope_metadata[rel_key] = {"category": "modifiable", "missing": not abs_path.exists()}
            if not abs_path.exists():
                missing_files.append(scoped_path)
                existing_files.setdefault(rel_key, "")
                continue
            if abs_path.is_file():
                _add_file(abs_path, rel_key)
            else:
                logger.warning(f"[Scope] Path is not a file: {abs_path}")

        # Load read-only context (limited set of extensions)
        allowed_exts = {
            ".py", ".pyi", ".txt", ".md", ".json", ".yaml", ".yml",
            ".ini", ".cfg", ".conf", ".env", ".csv",
            ".ts", ".tsx", ".js", ".jsx", ".vue", ".css", ".scss"
        }
        denylist_dirs = {".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
        max_readonly_files = 200
        readonly_count = 0

        for readonly_entry in scope_config.get("read_only_context", []):
            resolved = self._resolve_scope_target(readonly_entry, workspace_root, must_exist=False)
            if not resolved:
                continue
            abs_path, rel_key = resolved
            rel_key = _normalize_rel_path(rel_key)

            if abs_path.is_file():
                if rel_key not in existing_files:
                    _add_file(abs_path, rel_key)
                scope_metadata.setdefault(rel_key, {"category": "read_only", "missing": False})
                continue

            if not abs_path.is_dir():
                continue

            for file_path in abs_path.rglob("*"):
                if readonly_count >= max_readonly_files:
                    logger.warning("[Scope] Read-only context limit reached (200 files).")
                    break
                if not file_path.is_file():
                    continue
                if any(part in denylist_dirs for part in file_path.parts):
                    continue
                if file_path.suffix and file_path.suffix.lower() not in allowed_exts:
                    continue
                try:
                    rel_builder = str(file_path.resolve().relative_to(base_workspace)).replace("\\", "/")
                except ValueError:
                    continue
                if rel_builder in existing_files:
                    continue
                _add_file(file_path, rel_builder)
                scope_metadata.setdefault(rel_builder, {"category": "read_only", "missing": False})
                readonly_count += 1

        if missing_files:
            logger.warning(f"[Scope] Missing scope files: {missing_files}")

        logger.info(f"[Scope] Loaded {len(existing_files)} files from scope configuration")
        logger.info(f"[Scope] Scope paths: {scope_config.get('paths', [])}")
        preview_paths = list(existing_files.keys())[:10]
        logger.info(f"[Scope] Loaded paths: {preview_paths}...")

        return {
            "existing_files": existing_files,
            "scope_metadata": scope_metadata,
            "missing_scope_files": missing_files,
        }

    def _validate_scope_context(self, phase: Dict, file_context: Dict, scope_config: Dict):
        """Validate that loaded context matches scope configuration (Option C - Layer 1).

        This is the first validation layer (pre-Builder).
        Second layer is in GovernedApplyPath (patch application).

        Args:
            phase: Phase specification
            file_context: Loaded file context from _load_repository_context
            scope_config: Scope configuration dict

        Raises:
            RuntimeError: If validation fails
        """
        phase_id = phase.get("phase_id")
        scope_paths = scope_config.get("paths", [])
        loaded_files = set(file_context.get("existing_files", {}).keys())

        workspace_root = self._determine_workspace_root(scope_config)
        normalized_scope = []
        for path_str in scope_paths:
            resolved = self._resolve_scope_target(path_str, workspace_root, must_exist=False)
            if resolved:
                _, rel_key = resolved
                normalized_scope.append(rel_key)
            else:
                normalized_scope.append(path_str.replace("\\", "/"))

        # Check for files outside scope (indicating scope loading bug)
        scope_set = set(normalized_scope)
        outside_scope = loaded_files - scope_set

        if outside_scope:
            readonly_context = scope_config.get("read_only_context", [])
            readonly_exact: Set[str] = set()
            readonly_prefixes: List[str] = []

            for path_str in readonly_context:
                resolved = self._resolve_scope_target(path_str, workspace_root, must_exist=False)
                if resolved:
                    _, rel_key = resolved
                    if rel_key.endswith("/"):
                        readonly_prefixes.append(rel_key)
                    elif Path(rel_key).suffix:
                        readonly_exact.add(rel_key)
                    else:
                        readonly_prefixes.append(rel_key + "/")
                else:
                    normalized = path_str.replace("\\", "/")
                    if normalized.endswith("/"):
                        readonly_prefixes.append(normalized)
                    else:
                        readonly_exact.add(normalized)

            def _is_readonly_allowed(file_path: str) -> bool:
                if file_path in readonly_exact:
                    return True
                for prefix in readonly_prefixes:
                    if file_path.startswith(prefix):
                        return True
                return False

            truly_outside = {path for path in outside_scope if not _is_readonly_allowed(path)}

            if truly_outside:
                error_msg = (
                    f"[Scope] VALIDATION FAILED: {len(truly_outside)} files loaded outside scope:\n"
                    f"  Scope paths: {normalized_scope}\n"
                    f"  Read-only context prefixes: {readonly_prefixes or readonly_exact}\n"
                    f"  Files outside scope: {list(truly_outside)[:10]}"
                )
                logger.error(error_msg)
                raise RuntimeError(f"Scope validation failed: loaded files outside scope.paths")

        logger.info(f"[Scope] Validation passed: {len(loaded_files)} files match scope configuration")

    def _post_builder_result(
        self,
        phase_id: str,
        result: BuilderResult,
        allowed_paths: Optional[List[str]] = None
    ):
        """POST builder result to Autopack API

        Args:
            phase_id: Phase ID
            result: Builder result from llm_client.BuilderResult dataclass
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/builder_result"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Map llm_client.BuilderResult to builder_schemas.BuilderResult
        # Parse patch statistics using GovernedApplyPath
        from pathlib import Path
        from autopack.governed_apply import GovernedApplyPath

        # Enable internal mode for maintenance run types (for consistency)
        is_maintenance_run = self.run_type in ["autopack_maintenance", "autopack_upgrade", "self_repair"]
        governed_apply = GovernedApplyPath(
            workspace=Path(self.workspace),
            run_type=self.run_type,
            autopack_internal_mode=is_maintenance_run,
        )
        files_changed, lines_added, lines_removed = governed_apply.parse_patch_stats(result.patch_content or "")

        payload = {
            "phase_id": phase_id,
            "run_id": self.run_id,
            "run_type": self.run_type,
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
            "allowed_paths": allowed_paths or [],
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
            headers["X-API-Key"] = self.api_key

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
                
                # GPT_RESPONSE12 Q2: Write full CI output to log file for diagnosis
                ci_log_dir = Path(self.workspace) / ".autonomous_runs" / self.run_id / "ci"
                ci_log_dir.mkdir(parents=True, exist_ok=True)
                ci_log_path = ci_log_dir / f"pytest_{phase_id}.log"
                try:
                    full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
                    ci_log_path.write_text(full_output, encoding='utf-8')
                    logger.info(f"[{phase_id}] CI output written to: {ci_log_path}")
                except Exception as log_err:
                    logger.warning(f"[{phase_id}] Failed to write CI log: {log_err}")
                
                # Log last 20 lines at WARNING for quick diagnosis
                all_lines = (result.stdout + result.stderr).strip().split('\n')
                last_lines = all_lines[-20:] if len(all_lines) > 20 else all_lines
                logger.warning(f"[{phase_id}] CI failure - last 20 lines:\n" + '\n'.join(last_lines))

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
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            response = requests.post(
                url,
                json={"state": status},
                headers=headers,
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

    def _ensure_api_server_running(self) -> bool:
        """Check if API server is running, start it if not
        
        Returns:
            True if API is running (or was started), False if failed to start
        """
        import socket
        from urllib.parse import urlparse
        
        # Parse API URL
        parsed = urlparse(self.api_url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 8000
        
        # Check if server is already running
        try:
            response = requests.get(f"{self.api_url}/health", timeout=2)
            if response.status_code == 200:
                logger.info("API server is already running")
                return True
        except Exception:
            pass  # Server not responding, continue to start it
        
        # Try to connect to port to see if something is listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                # Port is open but /health failed - might be different service
                logger.warning(f"Port {port} is open but API health check failed. Assuming API is running.")
                return True
        except Exception:
            pass
        
        # Server not running - try to start it
        logger.info(f"API server not detected at {self.api_url}, attempting to start it...")
        
        try:
            # Start API server in background
            import sys
            api_cmd = [
                sys.executable, "-m", "uvicorn",
                "src.autopack.main:app",
                "--host", host,
                "--port", str(port)
            ]
            
            # Start process in background (detached on Windows)
            if sys.platform == "win32":
                # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
                import subprocess
                process = subprocess.Popen(
                    api_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS
                )
            else:
                # Unix: use nohup-like behavior
                process = subprocess.Popen(
                    api_cmd,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True
                )
            
            # Wait a bit for server to start
            logger.info(f"Waiting for API server to start on {host}:{port}...")
            for i in range(10):  # Wait up to 10 seconds
                time.sleep(1)
                try:
                    response = requests.get(f"{self.api_url}/health", timeout=1)
                    if response.status_code == 200:
                        logger.info("✅ API server started successfully")
                        return True
                except Exception:
                    pass
                if i < 9:
                    logger.info(f"  Still waiting... ({i+1}/10)")
            
            logger.error("API server failed to start within 10 seconds")
            return False
            
        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            logger.info("Please start the API server manually:")
            logger.info(f"  python -m uvicorn src.autopack.main:app --host {host} --port {port}")
            return False

    def run_autonomous_loop(
        self,
        poll_interval: int = 10,
        max_iterations: Optional[int] = None,
        stop_on_first_failure: bool = False
    ):
        """Main autonomous execution loop

        Args:
            poll_interval: Seconds to wait between polling for next phase
            max_iterations: Maximum number of phases to execute (None = unlimited)
            stop_on_first_failure: If True, stop immediately when any phase fails
        """
        logger.info("Starting autonomous execution loop...")
        logger.info(f"Poll interval: {poll_interval}s")
        if max_iterations:
            logger.info(f"Max iterations: {max_iterations}")

        # Ensure API server is running (auto-start if needed)
        if not self._ensure_api_server_running():
            logger.error("Cannot proceed without API server. Exiting.")
            return

        # Initialize infrastructure
        self._init_infrastructure()

        iteration = 0
        phases_executed = 0
        phases_failed = 0
        stop_signal_file = Path(".autonomous_runs/.stop_executor")
        
        while True:
            # Check for stop signal (from monitor script)
            if stop_signal_file.exists():
                signal_content = stop_signal_file.read_text().strip()
                if signal_content.startswith(f"stop:{self.run_id}"):
                    logger.critical(f"[STOP_SIGNAL] Stop signal detected: {signal_content}")
                    logger.info("Stopping execution as requested by monitor")
                    stop_signal_file.unlink()  # Remove signal file
                    break
            
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
                
                # NEW: Stop on first failure if requested (saves token usage)
                if stop_on_first_failure:
                    logger.critical(
                        f"[STOP_ON_FAILURE] Phase {phase_id} failed with status: {status}. "
                        f"Stopping execution to save token usage."
                    )
                    logger.info(f"Total phases executed: {phases_executed}, failed: {phases_failed}")
                    break

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
  GLM_API_KEY          GLM (Zhipu AI) API key (primary provider)
  GLM_API_BASE         GLM API base URL (optional)
  ANTHROPIC_API_KEY    Anthropic API key (for Claude models)
  OPENAI_API_KEY       OpenAI API key (fallback for gpt-* models)
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
        "--glm-key",
        default=os.getenv("GLM_API_KEY"),
        help="GLM (Zhipu AI) API key - primary provider (default: $GLM_API_KEY)"
    )

    parser.add_argument(
        "--anthropic-key",
        default=os.getenv("ANTHROPIC_API_KEY"),
        help="Anthropic API key for Claude models (default: $ANTHROPIC_API_KEY)"
    )

    parser.add_argument(
        "--openai-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key - fallback for gpt-* models (default: $OPENAI_API_KEY)"
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
        "--run-type",
        choices=["project_build", "autopack_maintenance", "autopack_upgrade", "self_repair"],
        default="project_build",
        help="Run type: project_build (default), autopack_maintenance (allows src/autopack/ modification)"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--stop-on-first-failure",
        action="store_true",
        help="Stop execution immediately when any phase fails (saves token usage)"
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
            run_type=args.run_type,
        )
    except ValueError as e:
        logger.error(f"Failed to initialize executor: {e}")
        sys.exit(1)

    # Run autonomous loop
    try:
        executor.run_autonomous_loop(
            poll_interval=args.poll_interval,
            max_iterations=args.max_iterations,
            stop_on_first_failure=args.stop_on_first_failure
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
