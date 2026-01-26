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
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.supervisor import SupervisorApiClient
from autopack.quality_gate import QualityGate
from autopack.config import settings
from autopack.llm_client import BuilderResult, AuditorResult
from autopack.executor_lock import ExecutorLockManager  # BUILD-048-T1
from autopack.error_recovery import (
    ErrorRecoverySystem,
    DoctorRequest,
    DoctorResponse,
    DoctorContextSummary,
    DOCTOR_MIN_BUILDER_ATTEMPTS,
    DOCTOR_HEALTH_BUDGET_NEAR_LIMIT_RATIO,
)
from autopack.llm_service import LlmService
from autopack.debug_journal import log_error
from autopack.archive_consolidator import log_build_event
from autopack.learned_rules import (
    load_project_rules,
    get_active_rules_for_phase,
    get_relevant_hints_for_phase,
    save_run_hint,
)
from autopack.health_checks import run_health_checks
from autopack.file_layout import RunFileLayout
from autopack.governed_apply import GovernedApplyPath

# Memory and validation imports
# BUILD-115: models.py removed - database write code disabled below
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.memory import MemoryService

# BUILD-123v2: Manifest Generator imports
from autopack.manifest_generator import ManifestGenerator

# BUILD-127 Phase 1: Completion authority with baseline tracking
from autopack.phase_finalizer import PhaseFinalizer
from autopack.test_baseline_tracker import TestBaselineTracker
from autopack.phase_auto_fixer import auto_fix_phase_scope

# PR-EXE-2: Approval flow consolidation
from autopack.executor.approval_flow import (
    request_human_approval,
    request_build113_approval,
    request_build113_clarification,
)

# PR-EXE-6: Heuristic context loader extraction
from autopack.executor.context_loading_heuristic import (
    HeuristicContextLoader,
    get_default_priority_files,
)

# PR-EXE-4: Run checkpoint and rollback extraction
from autopack.executor.run_checkpoint import (
    create_run_checkpoint,
    rollback_to_run_checkpoint,
    create_deletion_savepoint,
)

# PR-EXE-9: Phase state persistence manager
from autopack.executor.phase_state_manager import PhaseStateManager

# PR-EXE-10: Error analysis and learning pipeline
from autopack.executor.error_analysis import ErrorAnalyzer
from autopack.executor.learning_pipeline import LearningPipeline

# PR-EXE-12: Large helper method extraction
from autopack.executor.backlog_maintenance import BacklogMaintenance
from autopack.executor.scoped_context_loader import ScopedContextLoader
from autopack.api.builder_result_poster import BuilderResultPoster
from autopack.api.auditor_result_poster import AuditorResultPoster
from autopack.executor.autonomous_loop import AutonomousLoop
from autopack.api.server_lifecycle import APIServerLifecycle

# PR-EXE-13: Final helper extraction - reach 5,000 lines!
from autopack.executor.scope_context_validator import ScopeContextValidator
from autopack.ci.pytest_runner import PytestRunner
from autopack.ci.custom_runner import CustomRunner
from autopack.executor.execute_fix_handler import ExecuteFixHandler
from autopack.executor.phase_approach_reviser import PhaseApproachReviser
from autopack.executor.batched_deliverables_executor import (
    BatchedDeliverablesExecutor,
    BatchedExecutionContext,
)

# Configure logging
from dotenv import load_dotenv

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# =============================================================================
# EXECUTE_FIX CONSTANTS (Phase 3 - GPT_RESPONSE9)
# =============================================================================
# Configuration for Doctor's execute_fix action - direct infrastructure fixes.
# Disabled by default (user opt-in via models.yaml).

MAX_EXECUTE_FIX_PER_PHASE = 1  # Maximum execute_fix attempts per phase

# BUILD-050 Phase 2: Maximum retry attempts per phase
MAX_RETRY_ATTEMPTS = 5  # Maximum Builder retry attempts before phase fails

# Allowed fix types (v1: git, file, python; later: docker, shell)
ALLOWED_FIX_TYPES = {"git", "file", "python"}

# Command whitelists by fix_type (regex patterns)
ALLOWED_FIX_COMMANDS = {
    "git": [
        r"^git\s+checkout\s+",  # git checkout <file>/<branch>
        r"^git\s+reset\s+--hard\s+HEAD",  # git reset --hard HEAD
        r"^git\s+stash\s*$",  # git stash
        r"^git\s+stash\s+pop$",  # git stash pop
        r"^git\s+clean\s+-fd$",  # git clean -fd
        r"^git\s+merge\s+--abort$",  # git merge --abort
        r"^git\s+rebase\s+--abort$",  # git rebase --abort
        r"^git\s+status\s+--porcelain$",  # git status --porcelain (safe status)
        r"^git\s+diff\s+--name-only$",  # git diff --name-only (safe diff)
        r"^git\s+diff\s+--cached$",  # git diff --cached (Doctor log/validate)
    ],
    "file": [
        r"^rm\s+-f\s+",  # rm -f <file> (single file)
        r"^mkdir\s+-p\s+",  # mkdir -p <dir>
        r"^mv\s+",  # mv <src> <dst>
        r"^cp\s+",  # cp <src> <dst>
    ],
    "python": [
        r"^pip\s+install\s+",  # pip install <package>
        r"^pip\s+uninstall\s+-y\s+",  # pip uninstall -y <package>
        r"^python\s+-m\s+pip\s+install",  # python -m pip install <package>
    ],
}

# Banned metacharacters (security: prevent command injection)
BANNED_METACHARACTERS = [
    ";",
    "&&",
    "||",
    "`",
    "$(",
    "${",
    ">",
    ">>",
    "<",
    "|",
    "\n",
    "\r",
]

# Banned command prefixes (never execute)
BANNED_COMMAND_PREFIXES = [
    "sudo",
    "su ",
    "rm -rf /",
    "dd if=",
    "chmod 777",
    "mkfs",
    ":(){ :",
    "shutdown",
    "reboot",
    "poweroff",
    "halt",
    "init 0",
    "init 6",
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
        enable_second_opinion: bool = False,
        enable_autonomous_fixes: bool = False,
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
            enable_second_opinion: Enable second opinion triage for diagnostics (requires API key)
            enable_autonomous_fixes: Enable autonomous fixes for low-risk issues (BUILD-113)
        """
        # Load environment variables from .env for CLI runs
        load_dotenv()

        self.run_id = run_id
        self.api_url = api_url.rstrip("/")
        self.enable_second_opinion = enable_second_opinion
        self.enable_autonomous_fixes = enable_autonomous_fixes
        self.api_key = api_key
        self.workspace = workspace
        self.use_dual_auditor = use_dual_auditor
        self.run_type = run_type
        self._backlog_mode = self.run_type == "backlog_maintenance"

        # Store API keys (GLM is primary, Anthropic for Claude, OpenAI as fallback)
        self.glm_key = os.getenv("GLM_API_KEY")
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")

        # IMP-R06: Enhanced API key validation
        self._validate_api_keys()

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
            severity=ErrorSeverity.RECOVERABLE,
        )
        logger.info("Applying pre-emptive encoding fix...")
        self.error_recovery._fix_encoding_error(dummy_ctx)

        # Initialize database for usage tracking (share DB config with API server)
        from autopack.config import get_database_url
        from autopack.database import init_db

        # Use get_database_url() for runtime binding (respects DATABASE_URL env var)
        db_url = get_database_url()
        engine = create_engine(db_url)
        Session = sessionmaker(bind=engine)
        self.db_session = Session()

        # Initialize ALL database tables (not just llm_usage_events)
        # This creates runs, phases, tiers, llm_usage_events, token_estimation_v2_events, etc.
        init_db()
        logger.info("Database tables initialized")

        # Initialize SupervisorApiClient for all HTTP communication (BUILD-135)
        self.api_client = SupervisorApiClient(
            base_url=self.api_url, api_key=self.api_key, default_timeout=10.0
        )
        logger.info("SupervisorApiClient initialized")

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

        # Load Doctor execute_fix opt-in from models.yaml (user-controlled)
        self._allow_execute_fix = self._load_execute_fix_flag(config_path)
        logger.info(f"Doctor execute_fix enabled: {self._allow_execute_fix}")

        # NEW: Initialize FileSizeTelemetry (per IMPLEMENTATION_PLAN2.md Phase 2.1)
        from autopack.file_size_telemetry import FileSizeTelemetry

        self.file_size_telemetry = FileSizeTelemetry(Path(self.workspace))

        # NEW: Initialize MemoryService for vector retrieval (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
        try:
            self.memory_service = MemoryService()
            logger.info(f"MemoryService initialized (enabled={self.memory_service.enabled})")
        except Exception as e:
            logger.warning(f"MemoryService initialization failed, running without memory: {e}")
            self.memory_service = None

        # Optional: Index SOT docs at startup if enabled
        self._maybe_index_sot_docs()

        # PR-EXE-5: Initialize context preflight and retrieval injection (extracted modules)
        from autopack.executor.context_preflight import ContextPreflight
        from autopack.executor.retrieval_injection import RetrievalInjection
        from autopack.config import settings

        self.context_preflight = ContextPreflight(
            max_files=40,
            max_total_size_mb=5.0,
            read_only_threshold_mb=2.0,
            max_lines_hard_limit=self.builder_output_config.max_lines_hard_limit,
        )
        self.retrieval_injection = RetrievalInjection.from_settings(settings)
        logger.info(
            f"[PR-EXE-5] Context preflight initialized (max_lines_hard_limit={self.builder_output_config.max_lines_hard_limit})"
        )
        logger.info(
            f"[PR-EXE-5] Retrieval injection initialized (enabled={self.retrieval_injection.enabled}, "
            f"sot_budget_limit={self.retrieval_injection.sot_budget_limit})"
        )

        # PR-EXE-6: Initialize heuristic context loader (extracted module)
        self.heuristic_loader = HeuristicContextLoader(
            max_files=40, target_tokens=20000, max_chars_per_file=15000
        )
        logger.info("[PR-EXE-6] Heuristic context loader initialized")

        # Run file layout + diagnostics directories
        # Project ID is auto-detected from run_id prefix by RunFileLayout
        self.project_id = self._detect_project_id(self.run_id)
        self.run_layout = RunFileLayout(self.run_id, project_id=self.project_id)
        logger.info(
            f"[FileLayout] Project: {self.project_id}, Family: {self.run_layout.family}, Base: {self.run_layout.base_dir}"
        )
        try:
            self.run_layout.ensure_directories()
            self.run_layout.ensure_diagnostics_dirs()
        except Exception as e:
            logger.warning(f"[Diagnostics] Failed to prime run directories: {e}")

        # Governed diagnostics agent (evidence-first troubleshooting)
        try:
            self.diagnostics_agent = DiagnosticsAgent(
                run_id=self.run_id,
                workspace=Path(self.workspace),
                memory_service=self.memory_service,
                decision_logger=self._record_decision_entry,
                diagnostics_dir=self.run_layout.get_diagnostics_dir(),
                max_probes=8,
                max_seconds=300,
            )
        except Exception as e:
            logger.warning(f"[Diagnostics] Initialization failed; diagnostics disabled: {e}")
            self.diagnostics_agent = None

        # BUILD-113: Iterative Autonomous Investigation (goal-aware autonomous fixes)
        self.iterative_investigator = None
        if self.enable_autonomous_fixes and self.diagnostics_agent:
            try:
                from autopack.diagnostics.iterative_investigator import IterativeInvestigator
                from autopack.diagnostics.goal_aware_decision import GoalAwareDecisionMaker
                from autopack.diagnostics.decision_executor import DecisionExecutor

                decision_maker = GoalAwareDecisionMaker(
                    low_risk_threshold=100,
                    medium_risk_threshold=200,
                    min_confidence_for_auto_fix=0.7,
                )

                self.decision_executor = DecisionExecutor(
                    run_id=self.run_id,
                    workspace=Path(self.workspace),
                    memory_service=self.memory_service,
                    decision_logger=self._record_decision_entry,
                )

                self.iterative_investigator = IterativeInvestigator(
                    run_id=self.run_id,
                    workspace=Path(self.workspace),
                    diagnostics_agent=self.diagnostics_agent,
                    decision_maker=decision_maker,
                    memory_service=self.memory_service,
                    max_rounds=5,
                    max_probes_per_round=3,
                )
                logger.info("[BUILD-113] Iterative Autonomous Investigation enabled")
            except Exception as e:
                logger.warning(
                    f"[BUILD-113] Iterative Investigation init failed; autonomous fixes disabled: {e}"
                )
                self.iterative_investigator = None
        else:
            if self.enable_autonomous_fixes and not self.diagnostics_agent:
                logger.warning(
                    "[BUILD-113] Autonomous fixes require diagnostics_agent; feature disabled"
                )

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
        self.MAX_REPLANS_PER_RUN = (
            5  # Maximum re-planning attempts per run (prevents pathological projects)
        )

        # [Goal Anchoring] Per GPT_RESPONSE27: Prevent context drift during re-planning
        # PhaseGoal-lite implementation - lightweight anchor + telemetry (Phase 1)
        # Note: These are still used for goal anchoring (not moved to PhaseStateManager)
        self._phase_original_intent: Dict[str, str] = (
            {}
        )  # phase_id -> one-line intent extracted from description
        self._phase_original_description: Dict[str, str] = (
            {}
        )  # phase_id -> original description before any replanning
        self._phase_replan_history: Dict[str, List[Dict]] = (
            {}
        )  # phase_id -> list of {attempt, description, reason, alignment}
        self._run_replan_telemetry: List[Dict] = []  # All replans in this run for telemetry

        # PR-EXE-9: Initialize phase state manager for database state persistence
        self.phase_state_mgr = PhaseStateManager(
            run_id=self.run_id, workspace=Path(self.workspace), project_id=self.project_id
        )
        logger.info("[PR-EXE-9] Phase state manager initialized")

        # PR-EXE-10: Initialize error analyzer and learning pipeline
        self.error_analyzer = ErrorAnalyzer(
            trigger_threshold=self.REPLAN_TRIGGER_THRESHOLD,
            similarity_threshold=0.8,
            min_message_length=30,
            fatal_error_types=[],
            similarity_enabled=True,
        )
        self.learning_pipeline = LearningPipeline(run_id=self.run_id)
        logger.info("[PR-EXE-10] Error analyzer and learning pipeline initialized")

        # PR-EXE-11: Initialize Builder/Auditor pipeline orchestrators
        from autopack.executor.builder_orchestrator import BuilderOrchestrator
        from autopack.executor.patch_application_flow import PatchApplicationFlow
        from autopack.executor.ci_execution_flow import CIExecutionFlow
        from autopack.executor.auditor_orchestrator import AuditorOrchestrator

        self.builder_orchestrator = BuilderOrchestrator(self)
        self.patch_flow = PatchApplicationFlow(self)
        self.ci_flow = CIExecutionFlow(self)
        self.auditor_orchestrator = AuditorOrchestrator(self)
        logger.info("[PR-EXE-11] Builder/Auditor pipeline orchestrators initialized")

        # IMP-AUTOPILOT-001: Initialize autopilot for periodic gap scanning and improvement proposals
        self.autopilot = None
        self._autopilot_phase_count = 0  # Track phases for periodic invocation
        if settings.autopilot_enabled:
            try:
                from autopack.autonomy.autopilot import AutopilotController

                self.autopilot = AutopilotController(
                    workspace_root=Path(self.workspace),
                    project_id=self.project_id,
                    run_id=self.run_id,
                    enabled=True,
                )
                logger.info(
                    f"[IMP-AUTOPILOT-001] Autopilot enabled "
                    f"(frequency: every {settings.autopilot_gap_scan_frequency} phases, "
                    f"max_proposals: {settings.autopilot_max_proposals_per_session})"
                )
            except Exception as e:
                logger.warning(f"[IMP-AUTOPILOT-001] Autopilot initialization failed: {e}")
                self.autopilot = None
        else:
            logger.info(
                "[IMP-AUTOPILOT-001] Autopilot disabled (set AUTOPILOT_ENABLED=true to enable)"
            )

        # [Run-Level Health Budget] Prevent infinite retry loops (GPT_RESPONSE5 recommendation)
        self._run_http_500_count: int = 0  # Count of HTTP 500 errors in this run
        self._run_patch_failure_count: int = 0  # Count of patch failures in this run
        self._run_total_failures: int = 0  # Total recoverable failures in this run
        self.MAX_HTTP_500_PER_RUN = 10  # Stop run after this many 500 errors
        self.MAX_PATCH_FAILURES_PER_RUN = 15  # Stop run after this many patch failures

        # BUILD-195: Payload correction tracker for one-shot 422 handling
        from autopack.executor.payload_correction import PayloadCorrectionTracker

        self._payload_correction_tracker = PayloadCorrectionTracker()

        # [Phase C1] Store last builder result for Doctor diagnostics
        self._last_builder_result: Optional["BuilderResult"] = (
            None  # Last builder result (for patch/error info)
        )

        # [Phase C2] Store patch statistics extracted from builder result
        self._last_files_changed: Optional[List[str]] = None
        self._last_lines_added: int = 0
        self._last_lines_removed: int = 0

        # [Phase C5] Run-level branch checkpoint for rollback_run support
        self._run_checkpoint_branch: Optional[str] = None  # Original branch before run started
        self._run_checkpoint_commit: Optional[str] = None  # Original commit SHA before run started

        # BUILD-190: Run-level token usage tracking for budget decisions
        self._run_tokens_used: int = 0  # Accumulated tokens used in this run
        self._run_context_chars_used: int = 0  # Accumulated context chars used
        self._run_sot_chars_used: int = 0  # Accumulated SOT chars used
        self.run_budget_tokens: int = getattr(
            settings, "run_budget_tokens", 500_000
        )  # Default 500k

        self.MAX_TOTAL_FAILURES_PER_RUN = 25  # Stop run after this many total failures
        # Provider infra-error tracking (per-run)
        self._provider_infra_errors: Dict[str, int] = {}

        # [Doctor Integration] Per GPT_RESPONSE8 Section 4 recommendations
        # Per-(run, phase) Doctor context tracking (keyed by f"{run_id}:{phase_id}")
        self._doctor_context_by_phase: Dict[str, DoctorContextSummary] = {}
        self._doctor_calls_by_phase: Dict[str, int] = {}  # (run_id:phase_id) -> doctor call count
        self._last_doctor_response_by_phase: Dict[str, DoctorResponse] = {}
        self._last_error_category_by_phase: Dict[str, str] = (
            {}
        )  # Track error categories for is_complex_failure
        self._distinct_error_cats_by_phase: Dict[str, set] = (
            {}
        )  # Track distinct error categories per (run, phase)
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

        # [Learning Pipeline] Track rules marker for mid-run refresh
        self._rules_marker_path = None
        self._rules_marker_mtime = None

        # Phase 1.4-1.5: Run proactive startup checks (from DEBUG_JOURNAL.md)
        self._run_startup_checks()

        # [Phase C5] Create run checkpoint for rollback_run support
        checkpoint_success, checkpoint_error = self._create_run_checkpoint()
        if not checkpoint_success:
            logger.warning(f"[RunCheckpoint] Failed to create run checkpoint: {checkpoint_error}")
            logger.warning("[RunCheckpoint] Continuing without rollback_run support")

        # [GPT_RESPONSE26] Startup validation for token_soft_caps
        self._validate_config_at_startup()

        # BUILD-123v2: Initialize Manifest Generator for deterministic scope generation
        autopack_internal_mode = self.run_type in [
            "autopack_maintenance",
            "autopack_upgrade",
            "self_repair",
        ]
        self.manifest_generator = ManifestGenerator(
            workspace=self.workspace,
            autopack_internal_mode=autopack_internal_mode,
            run_type=self.run_type,
        )
        logger.info("[BUILD-123v2] Manifest generator initialized (deterministic scope generation)")

        # T0 Health Checks: quick environment validation before executing phases
        t0_results = run_health_checks("t0")
        for result in t0_results:
            status = "PASSED" if result.passed else "FAILED"
            logger.info(
                f"[HealthCheck:T0] {result.check_name}: {status} "
                f"({result.duration_ms}ms) - {result.message}"
            )

        # BUILD-127 Phase 1: Initialize completion authority components
        # P0.1: Pass run_id for run-scoped baseline artifacts (prevents parallel-run collisions)
        self.baseline_tracker = TestBaselineTracker(workspace=self.workspace, run_id=self.run_id)
        self.phase_finalizer = PhaseFinalizer(baseline_tracker=self.baseline_tracker)
        logger.info(
            f"[BUILD-127] Completion authority initialized (PhaseFinalizer + TestBaselineTracker, run_id={self.run_id})"
        )

        # PR-EXE-12: Initialize extracted helper modules
        self.backlog_maintenance = BacklogMaintenance(self)
        self.scoped_context_loader = ScopedContextLoader(self)
        self.builder_result_poster = BuilderResultPoster(self)
        self.auditor_result_poster = AuditorResultPoster(self)
        self.autonomous_loop = AutonomousLoop(self)
        self.api_server_lifecycle = APIServerLifecycle(self)
        logger.info("[PR-EXE-12] Large helper modules initialized")

        # BUILD-127 Phase 1: Capture T0 test baseline (for regression detection)
        try:
            import subprocess

            commit_sha_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if commit_sha_result.returncode == 0:
                commit_sha = commit_sha_result.stdout.strip()
                logger.info(f"[BUILD-127] Capturing T0 baseline at commit {commit_sha[:8]}...")
                self.t0_baseline = self.baseline_tracker.capture_baseline(
                    run_id=self.run_id,
                    commit_sha=commit_sha,
                    timeout=180,  # 3 minutes for baseline capture
                )
                logger.info(
                    f"[BUILD-127] T0 baseline: {self.t0_baseline.total_tests} tests, "
                    f"{self.t0_baseline.passing_tests} passing, "
                    f"{self.t0_baseline.failing_tests} failing, "
                    f"{self.t0_baseline.error_tests} errors"
                )
            else:
                logger.warning(
                    "[BUILD-127] Could not get git commit SHA - baseline tracking disabled"
                )
                self.t0_baseline = None
        except Exception as e:
            logger.warning(f"[BUILD-127] T0 baseline capture failed (non-blocking): {e}")
            self.t0_baseline = None

        # PR-EXE-13: Initialize final helper modules - reach 5,000 lines!
        self.scope_context_validator = ScopeContextValidator(self)
        self.pytest_runner = PytestRunner(
            workspace=Path(self.workspace), run_id=self.run_id, phase_finalizer=self.phase_finalizer
        )
        self.custom_runner = CustomRunner(workspace=Path(self.workspace), run_id=self.run_id)
        self.execute_fix_handler = ExecuteFixHandler(self)
        self.phase_approach_reviser = PhaseApproachReviser(self)
        self.batched_deliverables_executor = BatchedDeliverablesExecutor(self)
        logger.info(
            "[PR-EXE-14] Batched deliverables executor initialized - exceeding 5,000 line target!"
        )

    # =========================================================================
    # BACKLOG MAINTENANCE (propose-first apply with auditor gating)
    # =========================================================================

    def run_backlog_maintenance(
        self,
        plan_path: Path,
        patch_dir: Optional[Path] = None,
        apply: bool = False,
        allowed_paths: Optional[List[str]] = None,
        max_files: int = 10,
        max_lines: int = 500,
        checkpoint: bool = True,
        test_commands: Optional[List[str]] = None,
        auto_apply_low_risk: bool = False,
    ) -> None:
        """Run a backlog maintenance plan with diagnostics + optional apply.

        Extracted to BacklogMaintenance in PR-EXE-12.
        """
        return self.backlog_maintenance.run_maintenance(
            plan_path=plan_path,
            patch_dir=patch_dir,
            apply=apply,
            allowed_paths=allowed_paths,
            max_files=max_files,
            max_lines=max_lines,
            checkpoint=checkpoint,
            test_commands=test_commands,
            auto_apply_low_risk=auto_apply_low_risk,
        )

    def _validate_api_keys(self) -> None:
        """IMP-R06: Validate API keys before execution.

        Ensures at least one LLM API key is configured and validates format.
        Prevents execution with invalid/missing API keys.

        Raises:
            ValueError: If no valid API keys are configured or keys have invalid format
        """
        invalid_keys = []

        # Check if at least one key is present
        if not self.glm_key and not self.anthropic_key and not self.openai_key:
            raise ValueError(
                "At least one LLM API key required: GLM_API_KEY, ANTHROPIC_API_KEY, or OPENAI_API_KEY"
            )

        # Validate GLM key format if present
        if self.glm_key:
            if not isinstance(self.glm_key, str) or len(self.glm_key.strip()) == 0:
                invalid_keys.append("GLM_API_KEY (empty or invalid format)")
            elif len(self.glm_key) < 10:  # Basic length check
                invalid_keys.append("GLM_API_KEY (suspiciously short)")

        # Validate Anthropic key format if present
        if self.anthropic_key:
            if not isinstance(self.anthropic_key, str) or len(self.anthropic_key.strip()) == 0:
                invalid_keys.append("ANTHROPIC_API_KEY (empty or invalid format)")
            elif not self.anthropic_key.startswith("sk-"):
                invalid_keys.append("ANTHROPIC_API_KEY (invalid format - must start with 'sk-')")
            elif len(self.anthropic_key) < 20:
                invalid_keys.append("ANTHROPIC_API_KEY (suspiciously short)")

        # Validate OpenAI key format if present
        if self.openai_key:
            if not isinstance(self.openai_key, str) or len(self.openai_key.strip()) == 0:
                invalid_keys.append("OPENAI_API_KEY (empty or invalid format)")
            elif not self.openai_key.startswith("sk-"):
                invalid_keys.append("OPENAI_API_KEY (invalid format - must start with 'sk-')")
            elif len(self.openai_key) < 20:
                invalid_keys.append("OPENAI_API_KEY (suspiciously short)")

        # Raise error if any keys are invalid
        if invalid_keys:
            raise ValueError("Invalid API key(s) detected:\n  - " + "\n  - ".join(invalid_keys))

        logger.info("API key validation passed")

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
                        logger.warning("  Check FAILED - applying proactive fix...")
                        if callable(fix_fn):
                            fix_fn()
                            logger.info("  Fix applied successfully")
                        else:
                            logger.warning("  No fix function available")
                    else:
                        logger.info("  Check PASSED")

                except Exception as e:
                    logger.warning(f"  Startup check failed with error: {e}")
                    # Continue with other checks even if one fails

        except Exception as e:
            # Gracefully continue if startup checks system fails
            logger.warning(f"Startup checks system unavailable: {e}")

        # BUILD-130: Schema validation on startup (fail-fast if schema invalid)
        try:
            from autopack.schema_validator import SchemaValidator
            from autopack.config import get_database_url

            database_url = get_database_url()
            if database_url:
                validator = SchemaValidator(database_url)
                schema_result = validator.validate_on_startup()

                if not schema_result.is_valid:
                    logger.error("[FATAL] Schema validation failed on startup!")
                    logger.error(f"[FATAL] Found {len(schema_result.errors)} schema violations")
                    logger.error("[FATAL] Run: python scripts/break_glass_repair.py diagnose")
                    raise RuntimeError(
                        f"Database schema validation failed: {len(schema_result.errors)} violations detected. "
                        f"Run 'python scripts/break_glass_repair.py diagnose' to see details."
                    )
            else:
                logger.warning(
                    "[SchemaValidator] No database URL found - skipping schema validation"
                )

        except ImportError as e:
            logger.warning(f"[SchemaValidator] Schema validator not available: {e}")
        except Exception as e:
            logger.warning(f"[SchemaValidator] Schema validation failed: {e}")

        logger.info("Startup checks complete")

    def _detect_project_id(self, run_id: str) -> str:
        """Detect project ID from run_id prefix

        Args:
            run_id: Run identifier (e.g., 'fileorg-country-uk-20251205-132826')

        Returns:
            Project identifier (e.g., 'file-organizer-app-v1', 'autopack')
        """
        if run_id.startswith("fileorg-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("backlog-"):
            return "file-organizer-app-v1"
        elif run_id.startswith("maintenance-"):
            return "file-organizer-app-v1"
        else:
            return "autopack"

    def _load_execute_fix_flag(self, config_path: Path) -> bool:
        """
        Read doctor.allow_execute_fix_global from models.yaml to decide whether
        Doctor is permitted to run execute_fix during a run.

        Defaults to False on missing/invalid config to stay safe.
        """
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f) or {}
            doctor_cfg = config.get("doctor", {}) or {}
            return bool(doctor_cfg.get("allow_execute_fix_global", False))
        except Exception as e:  # pragma: no cover - defensive guard
            logger.warning(f"Failed to load execute_fix flag from {config_path}: {e}")
            return False

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
        self.project_id = project_id
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

        # Track marker path/mtime for mid-run refresh
        try:
            marker_path = Path(".autonomous_runs") / project_id / "rules_updated.json"
            self._rules_marker_path = marker_path
            if marker_path.exists():
                self._rules_marker_mtime = marker_path.stat().st_mtime
        except Exception:
            self._rules_marker_path = None
            self._rules_marker_mtime = None

        logger.info("Learning context loaded successfully")

    def _refresh_project_rules_if_updated(self):
        """
        Check rules_updated.json mtime and reload project rules mid-run if advanced.
        """
        if not self.project_id or not self._rules_marker_path:
            return
        try:
            if not self._rules_marker_path.exists():
                return
            mtime = self._rules_marker_path.stat().st_mtime
            if self._rules_marker_mtime is None or mtime > self._rules_marker_mtime:
                self._rules_marker_mtime = mtime
                self.project_rules = load_project_rules(self.project_id)
                logger.info(
                    f"[Learning] Reloaded project rules (now {len(self.project_rules)} rules) after marker update."
                )
        except Exception as e:
            logger.warning(f"[Learning] Failed to refresh project rules mid-run: {e}")

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
            project_id,
            phase,  # Pass project_id string, not self.project_rules list
        )

        # Get run-local hints from earlier phases (Stage 0A - within-run hints)
        relevant_hints = get_relevant_hints_for_phase(self.run_id, phase, max_hints=5)

        if relevant_rules:
            logger.debug(f"  Found {len(relevant_rules)} relevant project rules for phase")
        if relevant_hints:
            logger.debug(f"  Found {len(relevant_hints)} hints from earlier phases")

        return {
            "project_rules": relevant_rules,
            "run_hints": relevant_hints,
        }

    def _build_deliverables_contract(self, phase: Dict, phase_id: str) -> Optional[str]:
        """
        Build deliverables contract as hard constraint for Builder prompt.

        Per BUILD-050 Phase 1: Extract deliverables from phase scope and format them
        as non-negotiable requirements BEFORE learning hints.

        Args:
            phase: Phase specification dict
            phase_id: Phase identifier for logging

        Returns:
            Formatted deliverables contract string or None if no deliverables specified
        """
        from .deliverables_validator import extract_deliverables_from_scope
        from os.path import commonpath

        scope = phase.get("scope")
        if not scope:
            return None

        # Extract expected deliverables
        expected_paths = extract_deliverables_from_scope(scope)
        if not expected_paths:
            return None

        # Find common path prefix to emphasize structure
        common_prefix = "/"
        if len(expected_paths) > 1:
            try:
                common_prefix = commonpath(expected_paths)
            except (ValueError, TypeError):
                pass  # No common prefix, use root

        # Get forbidden patterns from recent validation failures
        forbidden_patterns: List[str] = []
        learning_context = self._get_learning_context_for_phase(phase)
        run_hints = learning_context.get("run_hints", [])

        for hint in run_hints:
            hint_text = hint if isinstance(hint, str) else getattr(hint, "hint_text", "")
            # Extract patterns like "Wrong: path/to/file"
            if "Wrong:" in hint_text and "→" in hint_text:
                parts = hint_text.split("Wrong:")
                if len(parts) > 1:
                    wrong_part = parts[1].split("→")[0].strip()
                    if wrong_part and wrong_part not in forbidden_patterns:
                        forbidden_patterns.append(wrong_part)

            # Also honor explicit "DO NOT create a top-level 'X/'" style hints.
            # (We use these for repeated deliverables misplacement patterns.)
            if "DO NOT create" in hint_text and "'" in hint_text:
                try:
                    # Example: DO NOT create a top-level 'tracer_bullet/' package.
                    quoted = hint_text.split("'")[1]
                    if quoted.endswith("/") and quoted not in forbidden_patterns:
                        forbidden_patterns.append(quoted)
                except Exception:
                    pass

        # Heuristic defaults: if expected paths indicate a specific required root,
        # explicitly forbid common wrong roots even before we have structured "Wrong:" hints.
        expected_set = set(expected_paths)
        if any(p.startswith("src/autopack/research/tracer_bullet/") for p in expected_set):
            for bad in ("tracer_bullet/", "src/tracer_bullet/", "tests/tracer_bullet/"):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)
            # Also forbid common "near-miss" placements inside src/autopack/
            for bad in ("src/autopack/tracer_bullet.py", "src/autopack/tracer_bullet/"):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)

        # Strict allowlist roots derived from expected deliverables.
        # This is used as a hard constraint in the prompt: Builder must not create files outside these roots.
        allowed_roots: List[str] = []
        preferred_roots = [
            "src/autopack/research/",
            "src/autopack/cli/",
            "tests/research/",
            "docs/research/",
        ]
        for r in preferred_roots:
            if any(p.startswith(r) for p in expected_set) and r not in allowed_roots:
                allowed_roots.append(r)

        # Build contract
        contract_parts = []
        contract_parts.append("=" * 80)
        contract_parts.append("⚠️  CRITICAL FILE PATH REQUIREMENTS (NON-NEGOTIABLE)")
        contract_parts.append("=" * 80)
        contract_parts.append("")
        contract_parts.append("You MUST create files at these EXACT paths. This is not negotiable.")
        contract_parts.append("")

        if common_prefix and common_prefix != "/":
            contract_parts.append(f"📁 All files MUST be under: {common_prefix}/")
            contract_parts.append("")

        if allowed_roots:
            contract_parts.append("✅ ALLOWED ROOTS (HARD RULE):")
            contract_parts.append(
                "You may ONLY create/modify files under these root prefixes. Creating ANY file outside them will be rejected."
            )
            for r in allowed_roots:
                contract_parts.append(f"   • {r}")
            contract_parts.append("")

        if forbidden_patterns:
            contract_parts.append("❌ FORBIDDEN patterns (from previous failed attempts):")
            for pattern in forbidden_patterns[:3]:  # Show first 3
                contract_parts.append(f"   • DO NOT use: {pattern}")
            contract_parts.append("")

        contract_parts.append("✓ REQUIRED file paths:")
        for path in expected_paths:
            contract_parts.append(f"   {path}")
        contract_parts.append("")

        # Chunk 0 core requirement: gold_set.json must be non-empty valid JSON.
        # We fail fast on empty/invalid JSON before apply (BUILD-070), but also harden the prompt contract here
        # so the Builder stops emitting empty placeholders.
        if any(
            p.endswith("src/autopack/research/evaluation/gold_set.json")
            or p.endswith("/gold_set.json")
            for p in expected_set
        ):
            contract_parts.append("🧾 JSON DELIVERABLES (HARD RULE):")
            contract_parts.append(
                "- `src/autopack/research/evaluation/gold_set.json` MUST be valid, non-empty JSON."
            )
            contract_parts.append(
                "- Minimal acceptable placeholder is `[]` (empty array) — but the file must NOT be blank."
            )
            contract_parts.append("- Any empty/invalid JSON will be rejected before patch apply.")
            contract_parts.append("")

        contract_parts.append("=" * 80)
        contract_parts.append("")

        logger.info(
            f"[{phase_id}] Built deliverables contract: {len(expected_paths)} required paths, {len(forbidden_patterns)} forbidden patterns"
        )

        return "\n".join(contract_parts)

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
                    with open(marker_path, "r") as f:
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
                "update_history": existing.get("update_history", [])[-9:]
                + [
                    {
                        "run_id": self.run_id,
                        "promoted": promoted_count,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    }
                ],
            }

            with open(marker_path, "w") as f:
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
                db=self.db_session, config_path="config/models.yaml", repo_root=self.workspace
            )
            logger.info("LlmService: Initialized with ModelRouter and UsageRecorder")

            # Initialize Quality Gate
            self.quality_gate = QualityGate(repo_root=self.workspace)
            logger.info("Quality Gate: Initialized")

        # Wrap initialization with error recovery
        self.error_recovery.execute_with_retry(
            func=_do_init, operation_name="Infrastructure initialization", max_retries=3
        )

    def get_run_status(self) -> Dict:
        """Fetch run status from Autopack API with error recovery and circuit breaker

        Returns:
            Run data with phases and status
        """
        from autopack.error_classifier import ErrorClassifier

        classifier = ErrorClassifier()
        # Try to fetch status with circuit breaker logic
        from autopack.supervisor.api_client import (
            SupervisorApiHttpError,
        )

        try:
            return self.api_client.get_run(self.run_id, timeout=10)
        except SupervisorApiHttpError as e:
            # Classify error to determine retry strategy
            status_code = e.status_code
            response_body = e.response_body or str(e)

            error_class, remediation = classifier.classify_api_error(
                status_code=status_code, response_body=response_body
            )

            # Log classification
            should_retry = classifier.should_retry(error_class)
            logger.error(f"[CircuitBreaker] API error classified as {error_class.value}")
            logger.error(f"[CircuitBreaker] Remediation: {remediation}")
            logger.error(
                f"[CircuitBreaker] Retry decision: {'RETRY' if should_retry else 'FAIL-FAST'}"
            )

            # Fail-fast on deterministic errors
            if not should_retry:
                logger.error("[CircuitBreaker] Deterministic error detected - stopping execution")
                logger.error(f"[CircuitBreaker] Error: HTTP {status_code} - {response_body[:500]}")
                raise RuntimeError(f"Deterministic API error: {remediation}") from e

            # Retry transient errors with exponential backoff
            max_retries = 3
            for attempt in range(max_retries):
                backoff = classifier.get_backoff_seconds(error_class, attempt)
                logger.warning(
                    f"[CircuitBreaker] Retrying after {backoff}s (attempt {attempt + 1}/{max_retries})"
                )
                import time

                time.sleep(backoff)

                try:
                    result = self.api_client.get_run(self.run_id, timeout=10)
                    logger.info(f"[CircuitBreaker] Retry successful on attempt {attempt + 1}")
                    return result
                except SupervisorApiHttpError:
                    if attempt == max_retries - 1:
                        # Last retry failed
                        logger.error("[CircuitBreaker] All retries exhausted for transient error")
                        raise
                    continue

            # Should not reach here
            raise
        except Exception as e:
            # Non-HTTP errors (connection errors, timeouts, etc.)
            logger.error(f"[CircuitBreaker] Non-HTTP error: {type(e).__name__}: {str(e)}")
            raise

    def _detect_and_reset_stale_phases(self, run_data: Dict):
        """
        Phase 1.6-1.7: Detect and auto-reset stale EXECUTING phases

        Identifies phases stuck in EXECUTING state for >10 minutes
        and automatically resets them to QUEUED for retry.

        This prevents the system from getting permanently stuck on
        failed infrastructure issues (network timeouts, API errors, etc.)
        """
        from datetime import datetime, timedelta

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
                    logger.warning(
                        f"[{phase_id}] EXECUTING phase has no timestamp - assuming stale and resetting"
                    )
                    self._update_phase_status(phase_id, "QUEUED")
                    continue

                try:
                    # Parse timestamp (assuming ISO format)
                    last_updated = datetime.fromisoformat(last_updated_str.replace("Z", "+00:00"))

                    # Make timezone-naive for comparison (assuming UTC)
                    if last_updated.tzinfo:
                        last_updated = last_updated.replace(tzinfo=None)

                    time_stale = now - last_updated

                    if time_stale > stale_threshold:
                        logger.warning(f"[{phase_id}] STALE PHASE DETECTED")
                        logger.warning("  State: EXECUTING")
                        logger.warning(f"  Last Updated: {last_updated_str}")
                        logger.warning(f"  Time Stale: {time_stale.total_seconds():.0f} seconds")
                        logger.warning("  Auto-resetting to QUEUED...")

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
                                result="success",
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
                                priority="HIGH",
                            )

                except Exception as e:
                    logger.warning(
                        f"[{phase_id}] Failed to parse timestamp '{last_updated_str}': {e}"
                    )

    def _get_tier_index(self, tier_id: int, tiers: List[Dict]) -> int:
        """Get tier_index for a given tier_id

        Args:
            tier_id: Database tier ID (integer)
            tiers: List of tier dicts from API

        Returns:
            tier_index if found, else 999 (sort to end)
        """
        for tier in tiers:
            if tier.get("id") == tier_id or tier.get("tier_id") == tier_id:
                return tier.get("tier_index", 999)
        return 999

    # =========================================================================
    # BUILD-041: Database Helper Methods for State Persistence
    # =========================================================================

    def _get_phase_from_db(self, phase_id: str) -> Optional[Any]:
        """Fetch phase from database with attempt tracking state.

        PR-EXE-9: Delegates to PhaseStateManager.
        """
        return self.phase_state_mgr._get_phase_from_db(phase_id)

    def _update_phase_attempts_in_db(
        self,
        phase_id: str,
        attempts_used: int = None,
        last_failure_reason: Optional[str] = None,
        timestamp: Optional[Any] = None,
        retry_attempt: Optional[int] = None,
        revision_epoch: Optional[int] = None,
        escalation_level: Optional[int] = None,
    ) -> bool:
        """Update phase attempt tracking in database.

        PR-EXE-9: Delegates to PhaseStateManager.
        """
        return self.phase_state_mgr._update_phase_attempts_in_db(
            phase_id=phase_id,
            attempts_used=attempts_used,
            last_failure_reason=last_failure_reason,
            timestamp=timestamp,
            retry_attempt=retry_attempt,
            revision_epoch=revision_epoch,
            escalation_level=escalation_level,
        )

    def _mark_phase_complete_in_db(self, phase_id: str) -> bool:
        """Mark phase as COMPLETE in database.

        PR-EXE-9: Core database logic delegated to PhaseStateManager,
        but phase proof writing remains here (requires _intention_wiring access).
        """
        # Get phase for timestamps before marking complete
        phase_db = self._get_phase_from_db(phase_id)
        if not phase_db:
            logger.error(f"[{phase_id}] Cannot mark complete: phase not found")
            return False

        from datetime import datetime, timezone

        phase_created_at = getattr(phase_db, "created_at", None) or datetime.now(timezone.utc)
        phase_completed_at = datetime.now(timezone.utc)

        # Delegate database update to PhaseStateManager
        success = self.phase_state_mgr.mark_complete(phase_id)

        if success:
            # INSERTION POINT 4: Write phase proof on success (BUILD-161 Phase A)
            if hasattr(self, "_intention_wiring") and self._intention_wiring is not None:
                try:
                    from autopack.phase_proof_writer import write_minimal_phase_proof

                    write_minimal_phase_proof(
                        run_id=self.run_id,
                        project_id=self.project_id,
                        phase_id=phase_id,
                        success=True,
                        created_at=phase_created_at,
                        completed_at=phase_completed_at,
                        error_summary=None,
                    )
                except Exception as proof_err:
                    logger.warning(
                        f"[{phase_id}] Failed to write phase proof (non-fatal): {proof_err}"
                    )

        return success

    def _record_token_efficiency_telemetry(self, phase_id: str, phase_outcome: str) -> None:
        """Record token efficiency telemetry for a phase (BUILD-145 P1 hardening).

        Best-effort telemetry recording that never fails the phase.
        Records metrics for terminal outcomes: COMPLETE, FAILED, BLOCKED.

        Args:
            phase_id: Phase identifier
            phase_outcome: Terminal outcome (COMPLETE, FAILED, BLOCKED, etc.)
        """
        try:
            # Check if we have context data from _load_scoped_context
            if not hasattr(self, "_last_file_context"):
                return

            file_ctx = self._last_file_context
            artifact_stats = file_ctx.get("artifact_stats", {})
            budget_selection = file_ctx.get("budget_selection")

            if not (artifact_stats or budget_selection):
                return

            from autopack.usage_recorder import record_token_efficiency_metrics

            # Extract artifact stats (BUILD-145 P1: now reflects kept files only)
            artifact_substitutions = artifact_stats.get("substitutions", 0) if artifact_stats else 0
            tokens_saved_artifacts = artifact_stats.get("tokens_saved", 0) if artifact_stats else 0
            substituted_paths_sample = (
                artifact_stats.get("substituted_paths_sample", []) if artifact_stats else []
            )

            # Extract budget selection stats
            if budget_selection:
                budget_mode = budget_selection.mode
                budget_used = budget_selection.used_tokens_est
                budget_cap = budget_selection.budget_tokens
                files_kept = budget_selection.files_kept_count
                files_omitted = budget_selection.files_omitted_count
            else:
                budget_mode = "unknown"
                budget_used = 0
                budget_cap = 0
                files_kept = 0
                files_omitted = 0

            # Record metrics with phase outcome
            record_token_efficiency_metrics(
                db=self.db,
                run_id=self.run_id,
                phase_id=phase_id,
                artifact_substitutions=artifact_substitutions,
                tokens_saved_artifacts=tokens_saved_artifacts,
                budget_mode=budget_mode,
                budget_used=budget_used,
                budget_cap=budget_cap,
                files_kept=files_kept,
                files_omitted=files_omitted,
                phase_outcome=phase_outcome,
            )

            # Compact logging: cap list at 10, join with commas
            paths_preview = ", ".join(substituted_paths_sample[:10])
            if substituted_paths_sample:
                paths_suffix = f" paths=[{paths_preview}]"
            else:
                paths_suffix = ""

            logger.info(
                f"[TOKEN_EFFICIENCY] phase={phase_id} outcome={phase_outcome} "
                f"artifacts={artifact_substitutions} saved={tokens_saved_artifacts}tok "
                f"budget={budget_mode} used={budget_used}/{budget_cap}tok "
                f"files={files_kept}kept/{files_omitted}omitted{paths_suffix}"
            )
        except Exception as e:
            # Best-effort telemetry - never fail the phase
            logger.warning(f"[{phase_id}] Failed to record token efficiency telemetry: {e}")

    def _mark_phase_failed_in_db(self, phase_id: str, reason: str) -> bool:
        """Mark phase as FAILED in database.

        PR-EXE-9: Core database logic delegated to PhaseStateManager,
        but phase proof writing and telemetry remain here (require executor context).
        """
        # Get phase for timestamps before marking failed
        phase_db = self._get_phase_from_db(phase_id)
        if not phase_db:
            logger.error(f"[{phase_id}] Cannot mark failed: phase not found")
            return False

        from datetime import datetime, timezone

        phase_created_at = getattr(phase_db, "created_at", None) or datetime.now(timezone.utc)
        phase_completed_at = datetime.now(timezone.utc)

        # Delegate database update to PhaseStateManager
        success = self.phase_state_mgr.mark_failed(phase_id, reason)

        if success:
            # INSERTION POINT 4: Write phase proof on failure (BUILD-161 Phase A)
            if hasattr(self, "_intention_wiring") and self._intention_wiring is not None:
                try:
                    from autopack.phase_proof_writer import write_minimal_phase_proof

                    write_minimal_phase_proof(
                        run_id=self.run_id,
                        project_id=self.project_id,
                        phase_id=phase_id,
                        success=False,
                        created_at=phase_created_at,
                        completed_at=phase_completed_at,
                        error_summary=reason,
                    )
                except Exception as proof_err:
                    logger.warning(
                        f"[{phase_id}] Failed to write phase proof (non-fatal): {proof_err}"
                    )

            # BUILD-145 P1: Record token efficiency telemetry for failed phases
            self._record_token_efficiency_telemetry(phase_id, "FAILED")

            # Send Telegram notification for phase failure
            self._send_phase_failure_notification(phase_id, reason)

        return success

    # =========================================================================
    # End of BUILD-041 Database Helper Methods
    # =========================================================================

    def get_next_queued_phase(self, run_data: Dict) -> Optional[Dict]:
        """Find next QUEUED phase in tier/index order

        Supports both flat (current API) and nested (legacy) phase structures.

        Flat structure (current API):
            {"phases": [...], "tiers": [...]}

        Nested structure (legacy):
            {"tiers": [{"phases": [...]}]}

        Args:
            run_data: Run data from API

        Returns:
            Phase dict if found, None otherwise
        """
        # Try flat structure first (current API format)
        phases = run_data.get("phases", [])
        tiers = run_data.get("tiers", [])

        if phases:
            # Sort by tier_index (via tier_id lookup) and phase_index
            sorted_phases = sorted(
                phases,
                key=lambda p: (
                    self._get_tier_index(p.get("tier_id"), tiers),
                    p.get("phase_index", 0),
                ),
            )

            for phase in sorted_phases:
                if phase.get("state") == "QUEUED":
                    return phase

        # Fallback to nested structure (legacy format)
        # This ensures backward compatibility with older runs
        if tiers:
            sorted_tiers = sorted(tiers, key=lambda t: t.get("tier_index", 0))

            for tier in sorted_tiers:
                tier_phases = tier.get("phases", [])
                sorted_tier_phases = sorted(tier_phases, key=lambda p: p.get("phase_index", 0))

                for phase in sorted_tier_phases:
                    if phase.get("state") == "QUEUED":
                        return phase

        return None

    def get_next_executable_phase(self) -> Optional[Dict]:
        """Find next executable phase using database state (BUILD-041)

        Queries database for phases that are either:
        1. QUEUED (not yet started), OR
        2. EXECUTING with retries available (retry_attempt < MAX_RETRY_ATTEMPTS), OR
        3. FAILED with retries available (auto-reset to QUEUED for retry)

        This replaces instance-based phase selection with database-backed selection,
        fixing the infinite loop bug where phases stuck in EXECUTING state weren't
        being retried.

        AUTO-RESET FEATURE:
        FAILED phases with remaining retry attempts are automatically reset to QUEUED.
        This eliminates the need for manual intervention when phases fail due to
        transient issues (max_tokens truncation, network errors, etc.).

        Returns:
            Phase dict if found, None otherwise
        """
        try:
            # BUILD-115: models.py removed, database ORM queries replaced with API calls
            # This method is obsolete - executor uses _select_next_queued_phase_from_tiers() instead
            logger.debug("[BUILD-115] get_next_executable_phase() is obsolete - returning None")
            return None

        except Exception as e:
            logger.error(f"[{self.run_id}] Failed to query executable phases from database: {e}")
            return None

    def execute_phase(self, phase: Dict, **kwargs) -> Tuple[bool, str]:
        """Execute Builder -> Auditor -> QualityGate pipeline for a phase

        Delegates to PhaseOrchestrator for execution flow (PR-EXE-8).

        BUILD-041: This method now executes ONE attempt per call, relying on the database for retry state.
        - Database tracks: retry_attempt, revision_epoch, escalation_level, last_attempt_timestamp, last_failure_reason
        - Model escalation: attempts 0-1 use cheap models, 2-3 mid-tier, 4+ strongest
        - Main loop handles retries by re-invoking this method

        Args:
            phase: Phase data from API or database
            **kwargs: Optional adjustments:
                - memory_context: Memory context to inject (IMP-ARCH-002)
                - context_reduction_factor: Factor to reduce context by
                - model_downgrade: Model to downgrade to
                - timeout_increase_factor: Factor to increase timeout by

        Returns:
            Tuple of (success: bool, status: str)
            status can be: "COMPLETE", "FAILED", "BLOCKED"
        """
        # Extract optional parameters
        memory_context = kwargs.get("memory_context")
        from autopack.executor.phase_orchestrator import (
            PhaseOrchestrator,
            ExecutionContext,
            PhaseResult,
        )

        phase_id = phase.get("phase_id")

        # Get DB state
        phase_db = self._get_phase_from_db(phase_id)
        if not phase_db:
            logger.debug(
                f"[{phase_id}] No database state (BUILD-115), using API data with defaults"
            )

            # Create a simple object with default retry state
            class PhaseDefaults:
                retry_attempt = 0
                revision_epoch = 0
                escalation_level = 0

            phase_db = PhaseDefaults()

        # Derive allowed paths from scope
        scope_config = phase.get("scope") or {}
        allowed_scope_paths = self._derive_allowed_paths_from_scope(scope_config)

        # [Goal Anchoring] Initialize goal anchor for this phase on first execution
        # Per GPT_RESPONSE27: Store original intent before any re-planning occurs
        self._initialize_phase_goal_anchor(phase)

        # Build execution context
        context = ExecutionContext(
            phase=phase,
            attempt_index=phase_db.retry_attempt,
            max_attempts=MAX_RETRY_ATTEMPTS,
            escalation_level=phase_db.escalation_level,
            allowed_paths=allowed_scope_paths,
            run_id=self.run_id,
            llm_service=self.llm_service,
            diagnostics_agent=getattr(self, "diagnostics_agent", None),
            iterative_investigator=getattr(self, "iterative_investigator", None),
            intention_wiring=getattr(self, "_intention_wiring", None),
            intention_anchor=getattr(self, "_intention_anchor", None),
            manifest_generator=getattr(self, "manifest_generator", None),
            run_total_failures=self._run_total_failures,
            run_http_500_count=self._run_http_500_count,
            run_patch_failure_count=self._run_patch_failure_count,
            run_doctor_calls=self._run_doctor_calls,
            run_replan_count=self._run_replan_count,
            run_tokens_used=getattr(self, "_run_tokens_used", 0),
            run_context_chars_used=getattr(self, "_run_context_chars_used", 0),
            run_sot_chars_used=getattr(self, "_run_sot_chars_used", 0),
            # Pass executor methods as callables
            get_phase_from_db=self._get_phase_from_db,
            mark_phase_complete_in_db=self._mark_phase_complete_in_db,
            mark_phase_failed_in_db=self._mark_phase_failed_in_db,
            update_phase_attempts_in_db=self._update_phase_attempts_in_db,
            record_learning_hint=self._record_learning_hint,
            record_phase_error=self._record_phase_error,
            run_diagnostics_for_failure=self._run_diagnostics_for_failure,
            record_token_efficiency_telemetry=self._record_token_efficiency_telemetry,
            status_to_outcome=self._status_to_outcome,
            refresh_project_rules_if_updated=self._refresh_project_rules_if_updated,
            phase_error_history=self._phase_error_history,
            last_builder_result=getattr(self, "_last_builder_result", None),
            workspace_root=getattr(self, "workspace_root", None),
            run_budget_tokens=getattr(self, "run_budget_tokens", 0),
            memory_context=memory_context,  # IMP-ARCH-002: Memory context injection
        )

        # Execute phase via orchestrator
        orchestrator = PhaseOrchestrator(max_retry_attempts=MAX_RETRY_ATTEMPTS)
        result = orchestrator.execute_phase_attempt(context)

        # Update counters from orchestrator result
        for key, value in result.updated_counters.items():
            setattr(self, f"_run_{key}", value)

        # Return result based on phase result
        if result.phase_result == PhaseResult.COMPLETE:
            return True, "COMPLETE"
        elif result.phase_result == PhaseResult.REPLAN_REQUESTED:
            return False, "REPLAN_REQUESTED"
        elif result.phase_result == PhaseResult.BLOCKED:
            return False, result.status
        else:
            return False, result.status

    def _status_to_outcome(self, status: str) -> str:
        """Map phase status to outcome for escalation tracking."""
        outcome_map = {
            "FAILED": "auditor_reject",
            "PATCH_FAILED": "patch_apply_error",
            "BLOCKED": "auditor_reject",
            "CI_FAILED": "ci_fail",
            # BUILD-049 / DBG-014: treat deliverables validation failures as tactical path-correction issues
            "DELIVERABLES_VALIDATION_FAILED": "deliverables_validation_failed",
        }
        return outcome_map.get(status, "auditor_reject")

    def _record_learning_hint(self, phase: Dict, hint_type: str, details: str):
        """
        Learning Pipeline: Record a hint for this run (PR-EXE-10).

        Delegates to LearningPipeline module for hint recording.
        Also saves to database for persistence (backward compatibility).

        Args:
            phase: Phase specification dict
            hint_type: Type of hint (e.g., auditor_reject, ci_fail, success_after_retry)
            details: Human-readable details about what was learned
        """
        try:
            # PR-EXE-10: Use learning pipeline module
            self.learning_pipeline.record_hint(phase, hint_type, details)

            # Backward compatibility: Also save to database
            phase_id = phase.get("phase_id", "unknown")
            phase_name = phase.get("name", phase_id)

            # Generate descriptive hint text based on type
            hint_templates = {
                "auditor_reject": f"Phase '{phase_name}' was rejected by auditor - ensure code quality and completeness",
                "ci_fail": f"Phase '{phase_name}' failed CI tests - verify tests pass before submitting",
                "patch_apply_error": f"Phase '{phase_name}' generated invalid patch - ensure proper diff format",
                "infra_error": f"Phase '{phase_name}' hit infrastructure error - check API connectivity",
                "success_after_retry": f"Phase '{phase_name}' succeeded after retries - model escalation was needed",
                "builder_churn_limit_exceeded": f"Phase '{phase_name}' exceeded churn limit - reduce change scope or increase complexity",
                "builder_guardrail": f"Phase '{phase_name}' blocked by builder guardrail (growth/shrinkage/truncation) - check output size",
            }

            hint_text = hint_templates.get(hint_type, f"Phase '{phase_name}': {hint_type}")
            hint_text = f"{hint_text}. Details: {details}"

            # Save the hint to database
            save_run_hint(
                run_id=self.run_id,
                phase=phase,
                hint_text=hint_text,
                source_issue_keys=[f"{hint_type}_{phase_id}"],
            )

        except Exception as e:
            # Don't let hint recording break phase execution
            logger.warning(f"Failed to record learning hint: {e}")

    # =========================================================================
    # Mid-Run Re-Planning System
    # =========================================================================

    def _record_phase_error(
        self, phase: Dict, error_type: str, error_details: str, attempt_index: int
    ):
        """
        Record an error for approach flaw detection (PR-EXE-10).

        Delegates to ErrorAnalyzer module for error pattern tracking.

        Args:
            phase: Phase specification
            error_type: Category of error (e.g., 'auditor_reject', 'ci_fail', 'patch_error')
            error_details: Detailed error message
            attempt_index: Current attempt number
        """
        phase_id = phase.get("phase_id")

        # PR-EXE-10: Use error analyzer module
        self.error_analyzer.record_error(
            phase_id=phase_id,
            attempt=attempt_index,
            error_type=error_type,
            error_details=error_details,
        )

        # Backward compatibility: Also store in local dict for phase_orchestrator
        if phase_id not in self._phase_error_history:
            self._phase_error_history[phase_id] = []

        error_record = {
            "attempt": attempt_index,
            "error_type": error_type,
            "error_details": error_details,
            "timestamp": time.time(),
        }

        self._phase_error_history[phase_id].append(error_record)

    def _detect_approach_flaw(self, phase: Dict) -> Optional[str]:
        """
        Analyze error history to detect fundamental approach flaws (PR-EXE-10).

        Delegates to ErrorAnalyzer module for approach flaw detection.

        Returns:
            Error type if approach flaw detected, None otherwise
        """
        phase_id = phase.get("phase_id")

        # PR-EXE-10: Use error analyzer module
        error_pattern = self.error_analyzer.detect_approach_flaw(phase_id)
        if error_pattern:
            return error_pattern.error_type

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
        first_sentence_match = re.match(r"^[^.!?]*[.!?]", description.strip())
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
            "only",
            "just",
            "skip",
            "ignore",
            "defer",
            "later",
            "simplified",
            "minimal",
            "basic",
            "stub",
            "placeholder",
            "without",
            "except",
            "excluding",
            "partial",
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
        self, original_intent: str, revised_description: str
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
                "notes": "Heuristic detection: revision appears to reduce scope",
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
            return {"alignment": "broader", "notes": "Revision appears to expand scope"}

        # Default: assume same scope (conservative for Phase 1)
        return {
            "alignment": "same_scope",
            "notes": "No obvious scope change detected (Phase 1 heuristic)",
        }

    def _record_replan_telemetry(
        self,
        phase_id: str,
        attempt: int,
        original_description: str,
        revised_description: str,
        reason: str,
        alignment: Dict[str, Any],
        success: bool,
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

    def _record_plan_change_entry(
        self,
        summary: str,
        rationale: str,
        phase_id: Optional[str],
        replaces_version: Optional[int] = None,
    ) -> None:
        """Persist plan change to DB and vector memory."""
        project_id = self._get_project_slug() or self.run_id
        timestamp = datetime.now(timezone.utc)

        if self.memory_service:
            try:
                self.memory_service.write_plan_change(
                    summary=summary,
                    rationale=rationale,
                    project_id=project_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    replaces_version=replaces_version,
                    timestamp=timestamp.isoformat(),
                )
            except Exception as e:
                logger.warning(f"[PlanChange] Failed to write to memory: {e}")

        # BUILD-115: models.PlanChange removed - skip database write
        logger.debug("[PlanChange] Skipped DB write (models.py removed)")

    def _record_decision_entry(
        self,
        trigger: str,
        choice: str,
        rationale: str,
        phase_id: Optional[str],
        alternatives: Optional[str] = None,
    ) -> None:
        """Persist decision log with memory embedding."""
        project_id = self._get_project_slug() or self.run_id
        timestamp = datetime.now(timezone.utc)

        if self.memory_service:
            try:
                self.memory_service.write_decision_log(
                    trigger=trigger,
                    choice=choice,
                    rationale=rationale,
                    project_id=project_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    alternatives=alternatives,
                    timestamp=timestamp.isoformat(),
                )
            except Exception as e:
                logger.warning(f"[DecisionLog] Failed to write to memory: {e}")

        # BUILD-115: models.DecisionLog removed - skip database write
        logger.debug("[DecisionLog] Skipped DB write (models.py removed)")

    def _should_trigger_replan(self, phase: Dict) -> Tuple[bool, Optional[str]]:
        """
        Determine if re-planning should be triggered for a phase.

        Returns:
            Tuple of (should_replan: bool, detected_flaw_type: str or None)
        """
        phase_id = phase.get("phase_id")

        # Check global run-level replan limit (prevents pathological projects)
        if self._run_replan_count >= self.MAX_REPLANS_PER_RUN:
            logger.info(
                f"[Re-Plan] Global max replans ({self.MAX_REPLANS_PER_RUN}) reached for this run - no more replans allowed"
            )
            return False, None

        # Check if we've exceeded max replans for this specific phase
        replan_count = self._get_replan_count(phase_id)
        if replan_count >= self.MAX_REPLANS_PER_PHASE:
            logger.info(
                f"[Re-Plan] Max replans ({self.MAX_REPLANS_PER_PHASE}) reached for {phase_id}"
            )
            return False, None

        # Detect approach flaw
        flaw_type = self._detect_approach_flaw(phase)
        if flaw_type:
            # DBG-014 / BUILD-049 coordination: deliverables path failures should be handled
            # by the deliverables validator + learning hints loop, not mid-run replanning.
            #
            # Mid-run replanning here can introduce conflicting guidance and de-stabilize convergence.
            if flaw_type == "deliverables_validation_failed":
                try:
                    phase_id = phase.get("phase_id")
                    phase_db = self._get_phase_from_db(phase_id) if phase_id else None
                    max_attempts = (
                        getattr(phase_db, "max_builder_attempts", None) if phase_db else None
                    )
                    builder_attempts = (
                        getattr(phase_db, "builder_attempts", None) if phase_db else None
                    )
                    if (
                        isinstance(max_attempts, int)
                        and max_attempts > 0
                        and isinstance(builder_attempts, int)
                    ):
                        if builder_attempts < max_attempts:
                            logger.info(
                                f"[Re-Plan] Deferring for deliverables validation failure "
                                f"(attempt {builder_attempts}/{max_attempts}) - allowing learning hints to converge"
                            )
                            return False, None
                except Exception as e:
                    logger.warning(
                        f"[Re-Plan] Failed to evaluate deliverables replan deferral: {e}"
                    )
                    return False, None

            return True, flaw_type

        return False, None

    def _revise_phase_approach(
        self, phase: Dict, flaw_type: str, error_history: List[Dict]
    ) -> Optional[Dict]:
        """Revise phase approach based on failure context.

        Extracted to PhaseApproachReviser in PR-EXE-13.
        """
        return self.phase_approach_reviser.revise_approach(phase, flaw_type, error_history)

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
    # DIAGNOSTICS AGENT (governed probes + evidence capture)
    # =========================================================================

    def _run_diagnostics_for_failure(
        self,
        failure_class: str,
        phase: Dict,
        context: Optional[Dict] = None,
    ):
        """Invoke governed diagnostics with safety/budget controls.

        If autonomous fixes are enabled (BUILD-113), attempts iterative investigation
        with goal-aware decision making. Otherwise, runs standard diagnostics.
        """
        if not getattr(self, "diagnostics_agent", None):
            return None

        ctx = dict(context or {})
        ctx.setdefault("phase_id", phase.get("phase_id"))
        ctx.setdefault("phase_name", phase.get("name"))

        # BUILD-113: Try iterative investigation if enabled
        if getattr(self, "iterative_investigator", None):
            try:
                logger.info(
                    f"[BUILD-113] Running iterative investigation for {phase.get('phase_id')}"
                )

                # Construct PhaseSpec from phase
                from autopack.diagnostics.diagnostics_models import PhaseSpec, DecisionType

                phase_spec = PhaseSpec(
                    phase_id=phase.get("phase_id", "unknown"),
                    deliverables=phase.get("deliverables", []),
                    acceptance_criteria=phase.get("acceptance_criteria", []),
                    allowed_paths=phase.get("allowed_paths", []),
                    protected_paths=phase.get("protected_paths", []),
                    complexity=phase.get("complexity", "medium"),
                    category=phase.get("category", "feature"),
                )

                # Run iterative investigation
                investigation_result = self.iterative_investigator.investigate_and_resolve(
                    failure_context={"failure_class": failure_class, **ctx}, phase_spec=phase_spec
                )

                # Handle decision
                decision = investigation_result.decision
                logger.info(f"[BUILD-113] Investigation decision: {decision.type.value}")

                if decision.type == DecisionType.CLEAR_FIX:
                    # Auto-apply fix
                    logger.info(f"[BUILD-113] Applying autonomous fix: {decision.fix_strategy}")
                    execution_result = self.decision_executor.execute_decision(
                        decision=decision, phase_spec=phase_spec
                    )

                    if execution_result.success:
                        logger.info(
                            f"[BUILD-113] Autonomous fix applied successfully: {execution_result.commit_sha}"
                        )
                        return investigation_result  # Return investigation result as diagnostic outcome
                    else:
                        logger.warning(
                            f"[BUILD-113] Autonomous fix failed: {execution_result.error_message}"
                        )
                        # Fall through to standard diagnostics

                elif decision.type in [DecisionType.RISKY, DecisionType.AMBIGUOUS]:
                    # Escalate to human - just return the investigation result for now
                    logger.info(f"[BUILD-113] Decision requires human input: {decision.type.value}")
                    # Could integrate with TelegramNotifier here for notifications
                    return investigation_result

                # If NEED_MORE_EVIDENCE or fall-through, continue with standard diagnostics below

            except Exception as e:
                logger.exception(f"[BUILD-113] Iterative investigation failed: {e}")
                # Fall through to standard diagnostics

        # Standard diagnostics (original behavior)
        try:
            return self.diagnostics_agent.run_diagnostics(
                failure_class=failure_class,
                context=ctx,
                phase_id=phase.get("phase_id"),
            )
        except Exception as e:
            logger.warning(f"[Diagnostics] Failed to run diagnostics for {failure_class}: {e}")
            return None

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

    def _should_invoke_doctor(
        self, phase_id: str, builder_attempts: int, error_category: str
    ) -> bool:
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
        # DBG-014 / BUILD-049 coordination: deliverables validation failures are tactical path-correction
        # problems that should be handled by the deliverables validator + learning hints loop.
        #
        # Invoking Doctor here can trigger re-planning which may introduce conflicting guidance and
        # destabilize monotonic self-correction (see docs/DBG-014_REPLAN_INTERFERENCE_ANALYSIS.md).
        #
        # Defer Doctor until we've exhausted the normal retry budget for this phase.
        if error_category == "deliverables_validation_failed":
            try:
                phase_db = self._get_phase_from_db(phase_id)
                max_attempts = getattr(phase_db, "max_builder_attempts", None) if phase_db else None
                if (
                    isinstance(max_attempts, int)
                    and max_attempts > 0
                    and builder_attempts < max_attempts
                ):
                    logger.info(
                        f"[Doctor] Deferring for deliverables validation failure "
                        f"(attempt {builder_attempts}/{max_attempts}) - allowing learning hints to converge"
                    )
                    return False
            except Exception as e:
                # Best-effort safety: if DB read fails, still avoid Doctor on deliverables failures.
                logger.warning(f"[Doctor] Failed to read phase max attempts for {phase_id}: {e}")
                return False

        is_infra = error_category == "infra_error"

        # Check minimum builder attempts (only for non-infra failures)
        if not is_infra and builder_attempts < DOCTOR_MIN_BUILDER_ATTEMPTS:
            logger.debug(
                f"[Doctor] Not invoking: builder_attempts={builder_attempts} < {DOCTOR_MIN_BUILDER_ATTEMPTS}"
            )
            return False

        # Check per-(run, phase) Doctor call limit
        phase_key = f"{self.run_id}:{phase_id}"
        phase_doctor_calls = self._doctor_calls_by_phase.get(phase_key, 0)
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
        # Track distinct error categories for this (run, phase)
        phase_key = f"{self.run_id}:{phase_id}"
        if phase_key not in self._distinct_error_cats_by_phase:
            self._distinct_error_cats_by_phase[phase_key] = set()
        self._distinct_error_cats_by_phase[phase_key].add(error_category)

        # Get prior Doctor response if any
        prior_response = self._last_doctor_response_by_phase.get(phase_key)
        prior_action = prior_response.action if prior_response else None
        prior_confidence = prior_response.confidence if prior_response else None

        return DoctorContextSummary(
            distinct_error_categories_for_phase=len(self._distinct_error_cats_by_phase[phase_key]),
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
        phase_key = f"{self.run_id}:{phase_id}"

        # Check if we should invoke Doctor
        if not self._should_invoke_doctor(phase_id, builder_attempts, error_category):
            return None

        # Check LlmService availability
        if not self.llm_service:
            logger.warning("[Doctor] LlmService not available, skipping Doctor invocation")
            return None

        # [BUILD-146 P6.2] Add intention context to Doctor logs_excerpt
        doctor_logs_excerpt = logs_excerpt
        if os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT", "false").lower() == "true":
            try:
                if hasattr(self, "_intention_injector"):
                    intention_reminder = self._intention_injector.get_intention_context(
                        max_chars=512
                    )
                    if intention_reminder:
                        doctor_logs_excerpt = f"[Project Intention]\n{intention_reminder}\n\n[Error Context]\n{logs_excerpt}"
                        logger.debug(f"[{phase_id}] Added intention reminder to Doctor context")
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to add intention to Doctor logs: {e}")

        # Build request
        request = DoctorRequest(
            phase_id=phase_id,
            error_category=error_category,
            builder_attempts=builder_attempts,
            health_budget=self._get_health_budget(),
            last_patch=last_patch,
            patch_errors=patch_errors or [],
            logs_excerpt=doctor_logs_excerpt,
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

            # Update tracking (per run+phase key)
            self._doctor_calls_by_phase[phase_key] = (
                self._doctor_calls_by_phase.get(phase_key, 0) + 1
            )
            self._run_doctor_calls += 1
            if error_category == "infra_error":
                self._run_doctor_infra_calls += 1
            self._last_doctor_response_by_phase[phase_key] = response
            self._doctor_context_by_phase[phase_key] = ctx_summary

            # Store builder hint if provided
            if response.builder_hint:
                self._builder_hint_by_phase[phase_id] = response.builder_hint

            logger.info(
                f"[Doctor] Diagnosis complete: action={response.action}, "
                f"confidence={response.confidence:.2f}, phase_calls={self._doctor_calls_by_phase[phase_key]}, "
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
            logger.info("[Doctor] Action: retry_with_fix - hint stored for next attempt")
            self._record_decision_entry(
                trigger="doctor",
                choice="retry_with_fix",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "retry_with_hint", True  # Continue retry loop with hint

        elif action == "replan":
            # Trigger mid-run re-planning
            logger.info("[Doctor] Action: replan - triggering approach revision")
            # Get error history for context
            error_history = self._phase_error_history.get(phase_id, [])
            revised_phase = self._revise_phase_approach(
                phase, f"doctor_replan:{response.rationale[:50]}", error_history
            )
            if revised_phase:
                self._run_replan_count += 1
                logger.info("[Doctor] Replan successful, phase revised")
                return "replan", True  # Continue with revised approach
            else:
                logger.warning("[Doctor] Replan failed, continuing with original approach")
                self._record_decision_entry(
                    trigger="doctor",
                    choice="replan_failed",
                    rationale=response.rationale,
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )
                return "replan_failed", True

        elif action == "skip_phase":
            # Skip this phase and continue to next
            logger.info("[Doctor] Action: skip_phase - marking phase as FAILED and continuing")
            self._skipped_phases.add(phase_id)
            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="skip_phase",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
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
                priority="CRITICAL",
            )
            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="mark_fatal",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
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
                priority="CRITICAL",
            )

            # [Phase C5] Execute branch-based rollback to pre-run state
            rollback_success, rollback_error = self._rollback_to_run_checkpoint(
                reason=f"Doctor rollback_run: {response.rationale}"
            )

            if rollback_success:
                logger.info("[Doctor] Successfully rolled back run to pre-run state")
            else:
                logger.error(f"[Doctor] Failed to rollback run: {rollback_error}")
                logger.error(
                    "[Doctor] Working tree may be in inconsistent state - manual intervention required"
                )

            # Mark phase as failed and let run terminate
            self._update_phase_status(phase_id, "FAILED")
            self._record_decision_entry(
                trigger="doctor",
                choice="rollback_run",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
            return "rollback", False  # Exit retry loop

        elif action == "execute_fix":
            # Phase 3: Direct infrastructure fix (GPT_RESPONSE9)
            self._record_decision_entry(
                trigger="doctor",
                choice="execute_fix",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback,execute_fix",
            )
            return self._handle_execute_fix(phase, response)

        else:
            logger.warning(f"[Doctor] Unknown action: {action}, treating as retry_with_fix")
            self._record_decision_entry(
                trigger="doctor",
                choice="unknown_action",
                rationale=response.rationale,
                phase_id=phase_id,
                alternatives="retry_with_fix,replan,skip,rollback",
            )
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

    def _handle_execute_fix(
        self, phase: Dict, response: DoctorResponse
    ) -> Tuple[Optional[str], bool]:
        """Handle Doctor's execute_fix action.

        Extracted to ExecuteFixHandler in PR-EXE-13.
        """
        result = self.execute_fix_handler.execute_fix(phase, response)
        return result.action_taken, result.should_continue_retry

    def _build_run_context(self) -> Dict[str, Any]:
        """Build run context with model overrides if specified.

        [Phase C3] Centralized run context builder for consistency across all LLM calls.
        [Phase E] Use intention-first loop routing overrides when available.

        Returns:
            Dict with model_overrides if they exist, otherwise empty dict
        """
        # Phase E: Use intention-first loop routing context if available
        if hasattr(self, "_intention_wiring") and self._intention_wiring is not None:
            return self._intention_wiring.run_context

        # Fallback: legacy model_overrides attribute
        run_context = {}
        if hasattr(self, "model_overrides") and self.model_overrides:
            run_context["model_overrides"] = self.model_overrides
        return run_context

    def _compute_coverage_delta(self, ci_result: Optional[Dict[str, Any]]) -> Optional[float]:
        """Compute coverage delta from CI results.

        BUILD-190: Uses coverage_metrics module for deterministic handling.
        Returns None when coverage data unavailable (not 0.0 placeholder).

        When CI includes coverage data in the result dictionary, this will
        parse and return the actual coverage delta.

        Args:
            ci_result: CI test results (may contain coverage data)

        Returns:
            Coverage delta as float (e.g., +5.2 for 5.2% increase),
            or None if coverage data unavailable
        """
        from autopack.executor.coverage_metrics import compute_coverage_delta

        return compute_coverage_delta(ci_result)

    def _create_run_checkpoint(self) -> Tuple[bool, Optional[str]]:
        """Create a git checkpoint before run execution starts.

        [Phase C5] Branch-based rollback support for Doctor rollback_run action.

        Stores current branch name and commit SHA so we can rollback the entire
        run if Doctor determines the run should be abandoned.

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # PR-EXE-4: Delegated to run_checkpoint module
        success, branch, commit, error = create_run_checkpoint(Path(self.workspace))

        if success:
            # Store checkpoint info in instance variables
            self._run_checkpoint_branch = branch
            self._run_checkpoint_commit = commit
            return True, None
        else:
            return False, error

    def _rollback_to_run_checkpoint(self, reason: str) -> Tuple[bool, Optional[str]]:
        """Rollback entire run to pre-run checkpoint.

        [Phase C5] Implements Doctor rollback_run action support.

        Resets working tree to the commit/branch that existed before run started.
        This is a destructive operation that discards all patches applied during the run.

        Args:
            reason: Reason for rollback (for logging/audit)

        Returns:
            Tuple of (success: bool, error_message: Optional[str])
        """
        # PR-EXE-4: Delegated to run_checkpoint module
        success, error = rollback_to_run_checkpoint(
            workspace=Path(self.workspace),
            checkpoint_branch=self._run_checkpoint_branch,
            checkpoint_commit=self._run_checkpoint_commit,
            reason=reason,
        )

        if success:
            # Log rollback action for audit trail
            self._log_run_rollback_action(reason)

        return success, error

    def _log_run_rollback_action(self, reason: str) -> None:
        """Log run rollback action to audit file.

        [Phase C5] Audit trail for run-level rollbacks.

        Args:
            reason: Reason for rollback
        """
        try:
            # Log to .autonomous_runs/{run_id}/run_rollback.log
            from autopack.file_layout import RunFileLayout

            layout = RunFileLayout(self.run_id, project_id=self.project_id)
            layout.ensure_directories()

            rollback_log = layout.base_dir / "run_rollback.log"

            timestamp = datetime.utcnow().isoformat()
            log_entry = (
                f"{timestamp} | Run: {self.run_id} | "
                f"Checkpoint: {self._run_checkpoint_commit[:8] if self._run_checkpoint_commit else 'unknown'} | "
                f"Reason: {reason}\n"
            )

            with open(rollback_log, "a", encoding="utf-8") as f:
                f.write(log_entry)

            logger.info(f"[RunCheckpoint] Logged run rollback to {rollback_log}")

        except Exception as e:
            logger.warning(f"[RunCheckpoint] Failed to write run rollback audit log: {e}")

    def _execute_phase_with_recovery(
        self,
        phase: Dict,
        attempt_index: int = 0,
        allowed_paths: Optional[List[str]] = None,
        memory_context: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """Inner phase execution with error handling and model escalation support"""
        # PR-D: Local import to reduce import-time weight and avoid E402

        phase_id = phase.get("phase_id")

        try:
            # Special-case phase handlers (in-phase batching) are routed via a tiny registry
            # to reduce merge conflicts in this file.
            from autopack.executor.phase_dispatch import resolve_special_phase_method

            special_method_name = resolve_special_phase_method(phase_id)
            if special_method_name:
                handler = getattr(self, special_method_name, None)
                if handler is None:
                    raise RuntimeError(
                        f"Phase '{phase_id}' mapped to missing handler '{special_method_name}'"
                    )
                return handler(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # =====================================================================
            # SECTION 1: BUILDER ORCHESTRATION (PR-EXE-11: Delegated to BuilderOrchestrator)
            # =====================================================================
            logger.info(f"[{phase_id}] Step 1/5: Generating code with Builder...")

            # IMP-COORD-001: Clear cached context if scope changed
            # PhaseOrchestrator marks phases with _require_context_refresh when scope is generated/modified
            # This ensures Builder and Auditor receive fresh context matching the new scope
            if phase.get("_require_context_refresh"):
                refresh_reason = phase.get("_context_refresh_reason", "unknown")
                logger.info(
                    f"[IMP-COORD-001] Clearing cached context for '{phase_id}' (reason: {refresh_reason})"
                )

                # Clear the _last_file_context cache used by BuilderOrchestrator (builder_orchestrator.py:211)
                if hasattr(self, "_last_file_context"):
                    self._last_file_context = None
                    logger.debug(f"[IMP-COORD-001] Cleared _last_file_context for '{phase_id}'")

                # Clear the LRU file cache in ScopedContextLoader to force disk re-reads
                try:
                    from autopack.executor.scoped_context_loader import clear_file_cache

                    clear_file_cache()
                    logger.debug(f"[IMP-COORD-001] Cleared LRU file cache for '{phase_id}'")
                except Exception as e:
                    logger.debug(f"[IMP-COORD-001] Failed to clear LRU cache (non-critical): {e}")

                # Clear the flag so we don't clear again on retry
                phase["_require_context_refresh"] = False

            # Execute Builder with full validation pipeline
            builder_result, context_info = (
                self.builder_orchestrator.execute_builder_with_validation(
                    phase_id=phase_id,
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                    memory_context=memory_context,  # IMP-ARCH-002: Memory context injection
                )
            )

            # Extract context for downstream use
            file_context = context_info.get("file_context")
            project_rules = context_info.get("project_rules", [])
            run_hints = context_info.get("run_hints", [])

            # Handle Builder retry/failure responses
            if not builder_result.success:
                # Check for special return codes that indicate retry/escalation
                if builder_result.error in ["TOKEN_ESCALATION", "EMPTY_FILES_RETRY", "INFRA_RETRY"]:
                    return False, builder_result.error
                # Other failures already handled by BuilderOrchestrator
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # =====================================================================
            # SECTION 1T: BUILD-113 PROACTIVE DECISION ANALYSIS (Stays in main method)
            # =====================================================================
            # BUILD-113 Proactive Mode: Assess patch before applying (if enabled)
            if (
                self.enable_autonomous_fixes
                and getattr(self, "iterative_investigator", None)
                and (builder_result.patch_content or getattr(builder_result, "edit_plan", None))
            ):
                logger.info(f"[BUILD-113] Running proactive decision analysis for {phase_id}")

                try:
                    from autopack.diagnostics.diagnostics_models import PhaseSpec, DecisionType

                    # Use GoalAwareDecisionMaker directly (no investigation needed for fresh features)
                    decision_maker = self.iterative_investigator.decision_maker

                    # Construct PhaseSpec from phase dict
                    phase_spec = PhaseSpec(
                        phase_id=phase_id,
                        deliverables=phase.get("deliverables", []),
                        acceptance_criteria=phase.get("acceptance_criteria", []),
                        allowed_paths=allowed_paths or [],
                        protected_paths=phase.get("protected_paths", []),
                        complexity=phase.get("complexity", "medium"),
                        category=phase.get("category", "feature"),
                    )

                    # Make proactive decision based on generated patch (or edit_plan)
                    decision = decision_maker.make_proactive_decision(
                        patch_content=builder_result.patch_content,
                        edit_plan=getattr(builder_result, "edit_plan", None),
                        phase_spec=phase_spec,
                    )

                    logger.info(
                        f"[BUILD-113] Proactive decision: {decision.type.value} "
                        f"(risk={decision.risk_level}, confidence={decision.confidence:.0%}, "
                        f"deliverables_met={len(decision.deliverables_met)}/{len(phase_spec.deliverables)})"
                    )

                    if decision.type == DecisionType.CLEAR_FIX:
                        # Auto-apply low/medium risk patch with high confidence
                        logger.info(
                            "[BUILD-113] CLEAR_FIX decision - auto-applying patch via DecisionExecutor"
                        )

                        execution_result = self.decision_executor.execute_decision(
                            decision=decision, phase_spec=phase_spec
                        )

                        if execution_result.success:
                            logger.info(
                                f"[BUILD-113] ✓ Autonomous implementation complete: {execution_result.commit_sha}\n"
                                f"  Files modified: {', '.join(decision.files_modified[:3])}"
                                f"{'...' if len(decision.files_modified) > 3 else ''}\n"
                                f"  Decision ID: {execution_result.decision_id}\n"
                                f"  Save point: {execution_result.save_point}"
                            )
                            self._update_phase_status(phase_id, "COMPLETE")
                            return True, "AUTONOMOUS_FIX_APPLIED"
                        else:
                            logger.warning(
                                f"[BUILD-113] Autonomous fix failed: {execution_result.error_message}\n"
                                f"  Rollback performed: {execution_result.rollback_performed}\n"
                                f"  Falling through to standard flow..."
                            )
                            # Fall through to standard flow

                    elif decision.type == DecisionType.RISKY:
                        # High-risk patch - request approval BEFORE applying
                        logger.info(
                            "[BUILD-113] RISKY decision - requesting human approval before applying patch"
                        )

                        approval_granted = self._request_build113_approval(
                            phase_id=phase_id,
                            decision=decision,
                            patch_content=builder_result.patch_content,
                            timeout_seconds=3600,
                        )

                        if not approval_granted:
                            logger.error(
                                "[BUILD-113] High-risk patch denied or timed out - blocking phase"
                            )
                            self._update_phase_status(phase_id, "BLOCKED")
                            return False, "BUILD113_APPROVAL_DENIED"

                        logger.info(
                            "[BUILD-113] High-risk patch approved - continuing with standard flow"
                        )
                        # Continue to standard patch application below

                    elif decision.type == DecisionType.AMBIGUOUS:
                        # Ambiguous - ask clarifying questions
                        logger.info(
                            "[BUILD-113] AMBIGUOUS decision - requesting human clarification"
                        )

                        clarification = self._request_build113_clarification(
                            phase_id=phase_id, decision=decision, timeout_seconds=3600
                        )

                        if not clarification:
                            logger.error("[BUILD-113] Clarification timed out - blocking phase")
                            self._update_phase_status(phase_id, "BLOCKED")
                            return False, "BUILD113_CLARIFICATION_TIMEOUT"

                        logger.info(
                            "[BUILD-113] Human clarification received - continuing with standard flow"
                        )
                        # Continue to standard patch application below

                except Exception as e:
                    logger.exception(f"[BUILD-113] Proactive decision analysis failed: {e}")
                    logger.warning("[BUILD-113] Continuing with standard flow after error")
                    # Continue to standard patch application

            # =====================================================================
            # SECTION 2: PATCH APPLICATION (PR-EXE-11: Delegated to PatchApplicationFlow)
            # =====================================================================
            logger.info(f"[{phase_id}] Step 2/5: Applying patch...")

            # Apply patch with validation and governance checks
            patch_success, error_msg, apply_stats = self.patch_flow.apply_patch_with_validation(
                phase_id=phase_id,
                phase=phase,
                builder_result=builder_result,
                file_context=file_context,
                allowed_paths=allowed_paths,
            )

            if not patch_success:
                return False, error_msg

            # =====================================================================
            # SECTION 3: CI EXECUTION (PR-EXE-11: Delegated to CIExecutionFlow)
            # =====================================================================
            logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")

            # Execute CI checks
            ci_result = self.ci_flow.execute_ci_checks(phase_id, phase)

            # Store apply_stats in ci_result for downstream use
            if ci_result and apply_stats:
                ci_result["apply_stats"] = apply_stats

            # =====================================================================
            # SECTION 4: AUDITOR REVIEW (PR-EXE-11: Delegated to AuditorOrchestrator)
            # =====================================================================
            logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor...")

            # Execute Auditor review
            auditor_result = self.auditor_orchestrator.execute_auditor_review(
                phase_id=phase_id,
                phase=phase,
                builder_result=builder_result,
                ci_result=ci_result,
                project_rules=project_rules,
                run_hints=run_hints,
                attempt_index=attempt_index,
            )

            # =====================================================================
            # SECTION 5: QUALITY GATE & FINALIZATION (Stays in main method)
            # =====================================================================
            logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
            # [Phase C2] Use extracted patch statistics for quality gate
            quality_report = self.quality_gate.assess_phase(
                phase_id=phase_id,
                phase_spec=phase,
                auditor_result={
                    "approved": auditor_result.approved,
                    "issues_found": auditor_result.issues_found,
                },
                ci_result=ci_result,  # Now passing real CI results!
                coverage_delta=self._compute_coverage_delta(
                    ci_result
                ),  # [Phase C4] Coverage delta computation
                patch_content=builder_result.patch_content,
                files_changed=self._last_files_changed,
            )

            logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")

            # Check for any large deletion (>50 lines) - create save point
            if quality_report.risk_assessment:
                checks = quality_report.risk_assessment.get("checks", {})
                net_deletion = checks.get("net_deletion", 0)

                if net_deletion > 50:
                    # Create automatic save point before large deletions
                    logger.info(
                        f"[{phase_id}] Large deletion detected ({net_deletion} lines) - creating save point"
                    )
                    save_point_tag = self._create_deletion_save_point(phase_id, net_deletion)
                    if save_point_tag:
                        logger.info(f"[{phase_id}] Save point created: {save_point_tag}")

                # Send notification for 100-200 line deletions (informational only)
                if checks.get("deletion_notification_needed") and not checks.get(
                    "deletion_approval_required"
                ):
                    # Send informational notification (don't block)
                    logger.info(
                        f"[{phase_id}] Large deletion detected (100+ lines) - sending notification"
                    )
                    self._send_deletion_notification(phase_id, quality_report)

            # Check if blocked (due to CI failure or other issues)
            approval_granted = False
            if quality_report.is_blocked():
                logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
                for issue in quality_report.issues:
                    logger.warning(f"  - {issue}")

                # NEW: Request human approval via Telegram
                approval_granted = self._request_human_approval(
                    phase_id=phase_id,
                    quality_report=quality_report,
                    timeout_seconds=3600,  # 1 hour timeout
                )

                if not approval_granted:
                    logger.error(f"[{phase_id}] Approval denied or timed out")
                    self._update_phase_status(phase_id, "BLOCKED")
                    return False, "BLOCKED: Human approval denied or timed out"

                logger.info(f"[{phase_id}] Human approval GRANTED - proceeding with phase")
                # Continue execution below

            # BUILD-127 Phase 1: Use PhaseFinalizer for authoritative completion check
            # Extract applied files from patch for deliverables validation
            applied_files = []
            if patch_success and builder_result.patch_content:
                try:
                    from autopack.governed_apply import parse_patch_stats

                    applied_files, _, _ = parse_patch_stats(builder_result.patch_content)
                    logger.info(f"[{phase_id}] Applied files: {applied_files}")
                except Exception as e:
                    logger.warning(f"[{phase_id}] Could not parse applied files: {e}")

            # BUILD-127 Phase 1: Assess completion using PhaseFinalizer
            # Extract apply_stats from ci_result if available, otherwise use local apply_stats
            finalizer_apply_stats = None
            if isinstance(ci_result, dict) and "apply_stats" in ci_result:
                finalizer_apply_stats = ci_result.get("apply_stats")
            elif apply_stats:
                finalizer_apply_stats = apply_stats

            finalization_decision = self.phase_finalizer.assess_completion(
                phase_id=phase_id,
                phase_spec=phase,
                ci_result=ci_result,  # CI test results
                baseline=self.t0_baseline,  # T0 baseline for regression detection
                quality_report={
                    "quality_level": quality_report.quality_level,
                    "is_blocked": quality_report.is_blocked(),
                    # If the phase was blocked but explicitly approved via governance,
                    # PhaseFinalizer should not hard-block solely on quality gate.
                    "human_approved": bool(approval_granted),
                },
                auditor_result={
                    "approved": auditor_result.approved,
                    "issues_found": auditor_result.issues_found,
                },
                deliverables=phase.get("deliverables", []),
                applied_files=applied_files,
                workspace=Path(self.workspace),
                apply_stats=finalizer_apply_stats,
            )

            # Handle finalization decision
            if not finalization_decision.can_complete:
                # BLOCKED or FAILED - phase cannot complete
                logger.error(
                    f"[{phase_id}] Phase finalization BLOCKED: {finalization_decision.reason}"
                )
                for issue in finalization_decision.blocking_issues:
                    logger.error(f"  ❌ {issue}")
                for warning in finalization_decision.warnings:
                    logger.warning(f"  ⚠️  {warning}")

                # Write phase summary with issues (including collector error digest if available)
                try:
                    issues_lines = list(finalization_decision.blocking_issues)
                    # Add collector error digest if present in ci_result
                    if isinstance(ci_result, dict) and ci_result.get("collector_error_digest"):
                        digest = ci_result["collector_error_digest"]
                        issues_lines.append(f"Collection/Import Errors ({len(digest)}):")
                        for error_line in digest:
                            issues_lines.append(f"  {error_line}")

                    phase_index = int(phase.get("phase_index", 0) or 0)
                    self.run_layout.write_phase_summary(
                        phase_index=phase_index,
                        phase_id=phase_id,
                        phase_name=str(phase.get("name") or phase_id),
                        state=finalization_decision.status,
                        task_category=phase.get("task_category"),
                        complexity=phase.get("complexity"),
                        issues_lines=issues_lines,
                    )
                except Exception as e:
                    logger.warning(f"[{phase_id}] Failed to write phase summary with issues: {e}")

                self._update_phase_status(phase_id, finalization_decision.status)
                return False, finalization_decision.reason

            # Finalization passed - phase can complete
            logger.info(f"[{phase_id}] Phase finalization PASSED: {finalization_decision.reason}")
            for warning in finalization_decision.warnings:
                logger.warning(f"  ⚠️  {warning}")

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
                builder_tokens = getattr(builder_result, "tokens_used", 0)
                log_build_event(
                    event_type="PHASE_COMPLETE",
                    description=f"Phase {phase_id} ({phase_name}) completed. Builder: {builder_tokens} tokens. Auditor: {'approved' if auditor_result.approved else 'rejected'} ({len(auditor_result.issues_found)} issues). Quality: {quality_report.quality_level}",
                    deliverables=[f"Run: {self.run_id}", f"Phase: {phase_id}"],
                    token_usage={"builder": builder_tokens},
                    project_slug=self._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to log build event: {e}")

            # NEW: Post-phase hook - write phase summary to vector memory
            if self.memory_service and self.memory_service.enabled:
                try:
                    project_id = self._get_project_slug() or self.run_id
                    phase_name = phase.get("name", phase_id)
                    summary = f"{phase_name}: {phase.get('description', '')[:200]}"
                    # BUILD-190: Extract changed files from parsed patch stats
                    changes = list(self._last_files_changed) if self._last_files_changed else []
                    # ci_result is a dict returned by _run_ci_checks with a boolean "passed" field
                    # (or skipped=True for skipped CI).
                    ci_success = (
                        bool(ci_result.get("passed", False))
                        if isinstance(ci_result, dict)
                        else False
                    )
                    ci_result = "pass" if ci_success else "fail"

                    self.memory_service.write_phase_summary(
                        run_id=self.run_id,
                        phase_id=phase_id,
                        project_id=project_id,
                        summary=summary,
                        changes=changes,
                        ci_result=ci_result,
                        task_type=phase.get("category"),
                    )
                    logger.debug(f"[{phase_id}] Wrote phase summary to memory")

                    # MEM-001: Persist learning hints to memory for cross-run learning
                    hints_persisted = self.learning_pipeline.persist_to_memory(
                        memory_service=self.memory_service,
                        project_id=project_id,
                    )
                    if hints_persisted > 0:
                        logger.debug(
                            f"[{phase_id}] Persisted {hints_persisted} learning hints to memory"
                        )
                except Exception as e:
                    logger.warning(f"[{phase_id}] Failed to write phase summary to memory: {e}")

            return True, "COMPLETE"

        except Exception as e:
            import traceback

            error_traceback = traceback.format_exc()
            error_msg = str(e)

            # Check if this is the Path/list error we're tracking
            if "unsupported operand type(s) for /" in error_msg and "list" in error_msg:
                logger.error(
                    f"[{phase_id}] Path/list TypeError detected:\n{error_msg}\nFull traceback:\n{error_traceback}"
                )
            else:
                logger.error(
                    f"[{phase_id}] Execution failed: {error_msg}\nTraceback:\n{error_traceback}"
                )

            # Log ALL exceptions to debug journal for tracking
            log_error(
                error_signature=f"Phase {phase_id} inner execution failure",
                symptom=f"{type(e).__name__}: {error_msg}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Unhandled exception in _execute_phase_with_recovery",
                priority="HIGH",
            )

            # NEW: Post-phase hook - write error to vector memory
            if self.memory_service and self.memory_service.enabled:
                try:
                    project_id = self._get_project_slug() or self.run_id
                    self.memory_service.write_error(
                        run_id=self.run_id,
                        phase_id=phase_id,
                        project_id=project_id,
                        error_text=f"{type(e).__name__}: {error_msg}\n{error_traceback[:2000]}",
                        error_type=type(e).__name__,
                    )
                    logger.debug(f"[{phase_id}] Wrote error to memory")

                    # MEM-001: Persist learning hints to memory for cross-run learning
                    hints_persisted = self.learning_pipeline.persist_to_memory(
                        memory_service=self.memory_service,
                        project_id=project_id,
                    )
                    if hints_persisted > 0:
                        logger.debug(
                            f"[{phase_id}] Persisted {hints_persisted} learning hints to memory"
                        )
                except Exception as mem_e:
                    logger.warning(f"[{phase_id}] Failed to write error to memory: {mem_e}")

            self._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

    def _execute_batched_deliverables_phase(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
        batches: List[List[str]],
        batching_label: str,
        manifest_allowed_roots: Tuple[str, ...],
        apply_allowed_roots: Tuple[str, ...],
    ) -> Tuple[bool, str]:
        """Execute phase using batched deliverables strategy.

        Delegates to BatchedDeliverablesExecutor for implementation.
        Extracted in PR-EXE-14 to reduce god file complexity.
        """
        context = BatchedExecutionContext(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label=batching_label,
            manifest_allowed_roots=manifest_allowed_roots,
            apply_allowed_roots=apply_allowed_roots,
        )

        result = self.batched_deliverables_executor.execute_batched_phase(context)
        return result.success, result.status

    def _execute_diagnostics_deep_retrieval_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-7 `diagnostics-deep-retrieval` (code → tests → docs)."""
        from autopack.executor.phase_handlers import batched_diagnostics_deep_retrieval

        return batched_diagnostics_deep_retrieval.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_diagnostics_iteration_loop_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-8 `diagnostics-iteration-loop` (code → tests → docs)."""
        from autopack.executor.phase_handlers import batched_diagnostics_iteration_loop

        return batched_diagnostics_iteration_loop.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_diagnostics_handoff_bundle_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-1 `diagnostics-handoff-bundle` (code → tests → docs)."""
        from autopack.executor.phase_handlers import batched_diagnostics_handoff_bundle

        return batched_diagnostics_handoff_bundle.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_diagnostics_cursor_prompt_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-2 `diagnostics-cursor-prompt` (code → tests → docs)."""
        from autopack.executor.phase_handlers import batched_diagnostics_cursor_prompt

        return batched_diagnostics_cursor_prompt.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_diagnostics_second_opinion_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-3 `diagnostics-second-opinion-triage` (code → tests → docs)."""
        from autopack.executor.phase_handlers import batched_diagnostics_second_opinion

        return batched_diagnostics_second_opinion.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_research_tracer_bullet_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for Chunk 0 (research-tracer-bullet)."""
        from autopack.executor.phase_handlers import batched_research_tracer_bullet

        return batched_research_tracer_bullet.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _execute_research_gatherers_web_compilation_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for Chunk 2B (research-gatherers-web-compilation)."""
        from autopack.executor.phase_handlers import batched_research_gatherers_web_compilation

        return batched_research_gatherers_web_compilation.execute(
            self, phase=phase, attempt_index=attempt_index, allowed_paths=allowed_paths
        )

    def _load_repository_context(self, phase: Dict) -> Dict:
        """Load repository files for Claude Builder context

        Smart context loading with three modes:
        1. Scope-aware (highest priority): If phase has scope configuration, load ONLY
           specified files and read-only context. This must override pattern-based targeting;
           otherwise we can accidentally load files outside scope and fail validation.
        2. Pattern-based targeting: If phase matches known patterns (country templates,
           frontend, docker), load only relevant files to reduce input context
        3. Heuristic-based: Legacy mode with freshness guarantees
           (for autopack_maintenance without scope)

        Args:
            phase: Phase specification (may include scope config)

        Returns:
            Dict with 'existing_files' key containing {path: content} dict
        """
        from autopack.executor.context_loading import load_repository_context

        return load_repository_context(self, phase)

    def _load_repository_context_heuristic(self, phase: Dict) -> Dict:
        """Legacy heuristic loader - delegates to HeuristicContextLoader.

        Extracted to dedicated module in PR-EXE-6 as part of god file refactoring.
        """
        workspace = Path(self.workspace)

        # Get git status files
        git_files = self.heuristic_loader.extract_git_status_files(workspace)

        # Extract mentioned files from description
        phase_description = phase.get("description", "")
        acceptance_criteria = phase.get("acceptance_criteria", [])
        mentioned_files = self.heuristic_loader.extract_mentioned_files(
            phase_description, acceptance_criteria
        )

        # Get priority files from default config
        priority_files = get_default_priority_files()

        # Load using heuristic context loader
        existing_files = self.heuristic_loader.load_context_files(
            workspace=workspace,
            git_status_files=git_files,
            mentioned_files=mentioned_files,
            priority_files=priority_files,
        )

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

        # For project_build, derive workspace from first scope path.
        # Scope paths can be either:
        # - ".autonomous_runs/<project>/(...)" (historical)
        # - "<project_slug>/(...)" e.g. "fileorganizer/frontend/..." (current external-project layout)
        scope_paths = scope_config.get("paths", [])
        if scope_paths:
            first_path = scope_paths[0]
            parts = Path(first_path).parts

            # Look for .autonomous_runs prefix
            if len(parts) >= 2 and parts[0] == ".autonomous_runs":
                project_root = Path(self.workspace) / parts[0] / parts[1]
                logger.info(f"[Scope] Workspace root determined: {project_root}")
                return project_root

            # Autopack monorepo heuristic: if scope paths start with standard repo-top-level buckets,
            # the workspace root should be the repo root (NOT the bucket directory). This prevents
            # accidental scope isolation where writes to e.g. "src/*" are blocked because the derived
            # workspace is "docs/" or "tests/".
            repo_root_buckets = {
                "src",
                "docs",
                "tests",
                "config",
                "scripts",
                "migrations",
                "archive",
                "examples",
            }
            if parts and parts[0] in repo_root_buckets:
                repo_root = Path(self.workspace).resolve()
                logger.info(
                    f"[Scope] Workspace root determined as repo root for bucket '{parts[0]}': {repo_root}"
                )
                return repo_root

            # Common external project layouts: "fileorganizer/<...>" or "file-organizer-app-v1/<...>"
            # If the first segment exists as a directory under repo root, treat it as workspace root.
            if parts:
                candidate = (Path(self.workspace) / parts[0]).resolve()
                if candidate.exists() and candidate.is_dir():
                    logger.info(f"[Scope] Workspace root determined from scope prefix: {candidate}")
                    return candidate

        # Fallback to default workspace
        logger.warning(
            f"[Scope] Could not determine workspace from scope paths, using default: {self.workspace}"
        )
        return Path(self.workspace)

    def _resolve_scope_target(
        self, scope_path: str, workspace_root: Path, *, must_exist: bool = False
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
        self, scope_config: Optional[Dict], workspace_root: Optional[Path] = None
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

    def _load_targeted_context_for_templates(self, phase: Dict) -> Dict:
        """Load minimal context for country template phases (UK, CA, AU)

        These phases typically create:
        - templates/countries/{country}/template.yaml
        - src/autopack/document_categories.py (or similar)

        We only need to load template-related files, not the entire codebase.
        """
        workspace = Path(self.workspace)
        existing_files = {}

        # Load only template-related files
        patterns = [
            "templates/**/*.yaml",
            "src/autopack/document_categories.py",
            "src/autopack/validation.py",
            "src/autopack/models.py",
            "config/**/*.yaml",
        ]

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file() and "__pycache__" not in str(filepath):
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} template-related files (targeted)")
        return {"existing_files": existing_files}

    def _load_targeted_context_for_frontend(self, phase: Dict) -> Dict:
        """Load minimal context for frontend phases

        Frontend phases only need:
        - frontend/ directory contents
        - package.json, vite.config.ts, tsconfig.json
        """
        workspace = Path(self.workspace)
        existing_files = {}

        patterns = [
            "frontend/**/*.ts",
            "frontend/**/*.tsx",
            "frontend/**/*.css",
            "frontend/**/*.json",
            "package.json",
            "vite.config.ts",
            "tsconfig.json",
            "tailwind.config.js",
        ]

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file() and "node_modules" not in str(filepath):
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} frontend files (targeted)")
        return {"existing_files": existing_files}

    def _load_targeted_context_for_docker(self, phase: Dict) -> Dict:
        """Load minimal context for Docker/deployment phases

        Docker phases only need:
        - Dockerfile, docker-compose.yml, .dockerignore
        - Database initialization scripts
        - Configuration files
        """
        workspace = Path(self.workspace)
        existing_files = {}

        patterns = [
            "Dockerfile",
            "docker-compose.yml",
            ".dockerignore",
            "scripts/init-db.sql",
            "scripts/**/*.sh",
            "config/**/*.yaml",
            "requirements.txt",
            "package.json",
        ]

        for pattern in patterns:
            for filepath in workspace.glob(pattern):
                if filepath.is_file():
                    try:
                        rel_path = str(filepath.relative_to(workspace))
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        existing_files[rel_path] = content[:15000]
                    except Exception as e:
                        logger.debug(f"Could not load {filepath}: {e}")

        logger.info(f"[Context] Loaded {len(existing_files)} docker/deployment files (targeted)")
        return {"existing_files": existing_files}

    def _load_scoped_context(self, phase: Dict, scope_config: Dict) -> Dict:
        """Extracted to ScopedContextLoader in PR-EXE-12."""
        return self.scoped_context_loader.load_context(phase, scope_config)

    def _validate_scope_context(self, phase: Dict, file_context: Dict, scope_config: Dict):
        """Validate that loaded context matches scope configuration (Option C - Layer 1).

        Extracted to ScopeContextValidator in PR-EXE-13.
        """
        return self.scope_context_validator.validate(phase, file_context, scope_config)

    def _post_builder_result(
        self, phase_id: str, result: BuilderResult, allowed_paths: Optional[List[str]] = None
    ):
        """Extracted to BuilderResultPoster in PR-EXE-12."""
        return self.builder_result_poster.post_result(phase_id, result, allowed_paths)

    def _post_auditor_result(self, phase_id: str, result: AuditorResult):
        """Extracted to AuditorResultPoster in PR-EXE-12."""
        return self.auditor_result_poster.post_result(phase_id, result)

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

    def _should_include_sot_retrieval(
        self, max_context_chars: int, phase_id: Optional[str] = None
    ) -> bool:
        """Budget-aware gating for SOT retrieval.

        Args:
            max_context_chars: Total context budget allocated for this retrieval

        Returns:
            True if SOT retrieval should be included based on budget availability

        Notes:
            - Delegated to RetrievalInjection module (PR-EXE-5)
            - SOT retrieval is only included if globally enabled AND budget allows
            - Budget check: max_context_chars >= (sot_budget + 2000)
            - The 2000-char reserve ensures room for other context sections
            - See docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md for integration pattern
        """
        # PR-EXE-5: Delegate to extracted RetrievalInjection module
        gate = self.retrieval_injection.gate_sot_retrieval(
            max_context_chars=max_context_chars, phase_id=phase_id
        )
        return gate.allowed

    def _record_sot_retrieval_telemetry(
        self,
        phase_id: str,
        include_sot: bool,
        max_context_chars: int,
        retrieved_context: dict,
        formatted_context: str,
    ) -> None:
        """Record SOT retrieval telemetry to database.

        Args:
            phase_id: Phase identifier
            include_sot: Whether SOT retrieval was attempted
            max_context_chars: Total context budget allocated
            retrieved_context: Raw context dict from retrieve_context()
            formatted_context: Final formatted string from format_retrieved_context()

        Notes:
            - Only records when TELEMETRY_DB_ENABLED=1
            - Failures are logged as warnings and do not crash execution
            - See docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md for metrics explanation
        """
        # Always emit an operator-visible log line so this can never be "silent bloat".
        # DB persistence remains opt-in (TELEMETRY_DB_ENABLED=1).
        try:
            from autopack.config import settings

            sot_chunks = retrieved_context.get("sot", []) or []
            sot_chunks_retrieved = len(sot_chunks)
            sot_chars_raw = sum(len(chunk.get("content", "")) for chunk in sot_chunks)
            total_context_chars = len(formatted_context)
            budget_utilization_pct = (
                (total_context_chars / max_context_chars * 100) if max_context_chars > 0 else 0.0
            )
            logger.info(
                f"[{phase_id}] [SOT] Context telemetry: include_sot={include_sot}, "
                f"sot_chunks={sot_chunks_retrieved}, sot_chars_raw={sot_chars_raw}, "
                f"total_chars={total_context_chars}/{max_context_chars} ({budget_utilization_pct:.1f}%), "
                f"sot_cap={settings.autopack_sot_retrieval_max_chars}, top_k={settings.autopack_sot_retrieval_top_k}"
            )
        except Exception:
            # Never block execution if telemetry formatting fails.
            pass

        # Skip DB persistence if telemetry disabled
        if not os.getenv("TELEMETRY_DB_ENABLED") == "1":
            return

        try:
            from autopack.config import settings
            from autopack.database import SessionLocal
            from autopack.models import SOTRetrievalEvent
            from datetime import datetime, timezone

            # Calculate metrics
            sot_chunks = retrieved_context.get("sot", [])
            sot_chunks_retrieved = len(sot_chunks)
            sot_chars_raw = sum(len(chunk.get("content", "")) for chunk in sot_chunks)

            total_context_chars = len(formatted_context)
            budget_utilization_pct = (
                (total_context_chars / max_context_chars * 100) if max_context_chars > 0 else 0.0
            )

            # Determine sections included
            sections_included = [k for k, v in retrieved_context.items() if v]

            # Estimate SOT contribution in formatted output (approximate)
            # Since format_retrieved_context() doesn't expose per-section breakdowns,
            # we can't measure exact SOT chars after formatting.
            # For now, set to None if SOT wasn't included, or sot_chars_raw if it was
            # (this is an upper bound - actual may be lower if truncated).
            sot_chars_formatted = sot_chars_raw if include_sot and sot_chunks else None

            # Detect if SOT was truncated (heuristic: raw > formatted and formatted < max)
            sot_truncated = False
            if include_sot and sot_chars_raw > 0:
                # If total context hit the cap, SOT might have been truncated
                sot_truncated = total_context_chars >= max_context_chars * 0.95  # Within 5% of cap

            # Create telemetry event
            session = SessionLocal()
            try:
                event = SOTRetrievalEvent(
                    run_id=self.run_id,
                    phase_id=phase_id,
                    timestamp=datetime.now(timezone.utc),
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    sot_budget_chars=settings.autopack_sot_retrieval_max_chars,
                    sot_chunks_retrieved=sot_chunks_retrieved,
                    sot_chars_raw=sot_chars_raw,
                    total_context_chars=total_context_chars,
                    sot_chars_formatted=sot_chars_formatted,
                    budget_utilization_pct=budget_utilization_pct,
                    sot_truncated=sot_truncated,
                    sections_included=sections_included,
                    retrieval_enabled=settings.autopack_sot_retrieval_enabled,
                    top_k=settings.autopack_sot_retrieval_top_k,
                    created_at=datetime.now(timezone.utc),
                )
                session.add(event)
                session.commit()

                logger.debug(
                    f"[{phase_id}] SOT telemetry recorded: "
                    f"include_sot={include_sot}, "
                    f"chunks={sot_chunks_retrieved}, "
                    f"chars_raw={sot_chars_raw}, "
                    f"total={total_context_chars}/{max_context_chars} "
                    f"({budget_utilization_pct:.1f}%)"
                )
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to record SOT retrieval telemetry: {e}")

    def _resolve_project_docs_dir(self, project_id: str) -> Path:
        """Resolve the correct docs directory for a project.

        Args:
            project_id: Project identifier (e.g., 'autopack', 'telemetry-collection-v5')

        Returns:
            Path to the project's docs directory

        Notes:
            - For repo-root projects (project_id == 'autopack'), uses <workspace>/docs
            - For sub-projects, checks <workspace>/.autonomous_runs/<project_id>/docs
            - Falls back to <workspace>/docs with a warning if sub-project docs not found
        """
        ws = Path(self.workspace)

        # Check for sub-project docs directory
        candidate = ws / ".autonomous_runs" / project_id / "docs"
        if candidate.exists():
            logger.debug(f"[Executor] Using sub-project docs dir: {candidate}")
            return candidate

        # Fallback to root docs directory
        root_docs = ws / "docs"
        if not candidate.exists() and project_id != "autopack":
            logger.warning(
                f"[Executor] Sub-project docs dir not found: {candidate}, "
                f"falling back to {root_docs}"
            )
        return root_docs

    def _maybe_index_sot_docs(self) -> None:
        """Index SOT documentation files at startup if enabled.

        Only indexes when:
        - Memory service is enabled
        - AUTOPACK_ENABLE_SOT_MEMORY_INDEXING=true

        Failures are logged as warnings and do not crash the run.
        """
        # Log SOT configuration for operator visibility
        logger.info(
            f"[SOT] Configuration: "
            f"indexing_enabled={settings.autopack_enable_sot_memory_indexing}, "
            f"retrieval_enabled={settings.autopack_sot_retrieval_enabled}, "
            f"memory_enabled={self.memory_service.enabled if self.memory_service else False}"
        )

        if not self.memory_service or not self.memory_service.enabled:
            logger.debug("[SOT] Memory service disabled, skipping SOT indexing")
            return

        project_id = self._get_project_slug() or self.run_id

        # Optional: if tidy marked SOT as dirty, we can opportunistically re-index at startup.
        # This keeps the "tidy → SOT → semantic indexing → retrieval" pipeline fresh without re-indexing on every run.
        ws = Path(self.workspace)
        if project_id == "autopack":
            dirty_marker = ws / ".autonomous_runs" / "sot_index_dirty_autopack.json"
        else:
            dirty_marker = (
                ws / ".autonomous_runs" / project_id / ".autonomous_runs" / "sot_index_dirty.json"
            )

        dirty_requested = dirty_marker.exists()

        if not settings.autopack_enable_sot_memory_indexing:
            if dirty_requested:
                logger.info(
                    f"[SOT] Dirty marker present but indexing disabled; leaving marker in place: {dirty_marker}"
                )
            else:
                logger.debug("[SOT] SOT indexing disabled by config")
            return

        try:
            docs_dir = self._resolve_project_docs_dir(project_id=project_id)
            if dirty_requested:
                logger.info(f"[SOT] Dirty marker detected; re-indexing SOT now: {dirty_marker}")
            logger.info(f"[SOT] Starting indexing for project={project_id}, docs_dir={docs_dir}")

            result = self.memory_service.index_sot_docs(
                project_id=project_id,
                workspace_root=Path(self.workspace),
                docs_dir=docs_dir,
            )

            if result.get("skipped"):
                logger.info(f"[SOT] Indexing skipped: {result.get('reason', 'unknown')}")
            else:
                indexed_count = result.get("indexed", 0)
                logger.info(
                    f"[SOT] Indexing complete: {indexed_count} chunks indexed "
                    f"(project={project_id}, docs={docs_dir})"
                )

            # Clear dirty marker only after a successful indexing attempt (even if it indexed 0).
            if dirty_requested:
                try:
                    dirty_marker.unlink(missing_ok=True)
                    logger.info(f"[SOT] Cleared dirty marker: {dirty_marker}")
                except Exception as e:
                    logger.warning(f"[SOT] Failed to clear dirty marker {dirty_marker}: {e}")
        except Exception as e:
            logger.warning(f"[SOT] Indexing failed: {e}", exc_info=True)

    def _autofix_queued_phases(self, run_data: Dict[str, Any]) -> None:
        """
        Auto-fix queued phases into a known-good shape and persist updates to the DB.

        This targets common "known-bad" failure causes:
        - deliverables annotated strings (e.g. "path (10+ tests)") -> normalized path
        - missing/empty scope.paths -> derived from deliverables
        - CI timeouts too short -> tuned by complexity + prior timeout evidence

        Persistence is done through `self.db_session` so the API server and retries see the fixed scope.
        """
        phases = run_data.get("phases") or []
        if not isinstance(phases, list) or not phases:
            return

        changed = 0
        for p in phases:
            if not isinstance(p, dict):
                continue
            if p.get("state") != "QUEUED":
                continue
            phase_id = p.get("phase_id")
            if not phase_id:
                continue

            result = auto_fix_phase_scope(p)
            if not result.changed:
                continue

            # Update in-memory dict so this loop iteration uses the fixed scope.
            p["scope"] = result.new_scope

            try:
                from autopack.models import Phase

                row = (
                    self.db_session.query(Phase)
                    .filter(Phase.run_id == self.run_id, Phase.phase_id == phase_id)
                    .first()
                )
                if row:
                    row.scope = result.new_scope
                    changed += 1
            except Exception as e:
                logger.debug(f"[AutoFix:{phase_id}] DB update failed (non-fatal): {e}")

        if changed:
            try:
                self.db_session.commit()
                logger.info(f"[AutoFix] Updated {changed} queued phases in DB")
            except Exception as e:
                self.db_session.rollback()
                logger.warning(f"[AutoFix] Failed to commit phase auto-fixes (non-blocking): {e}")

    def _run_ci_checks(self, phase_id: str, phase: Dict) -> Dict[str, Any]:
        """Run CI checks based on the phase's CI specification (default: pytest)."""
        # BUILD-141 Part 8: Support AUTOPACK_SKIP_CI=1 for telemetry seeding runs
        # (avoids blocking on unrelated test import errors during telemetry collection)
        # GUARDRAIL: Only honor AUTOPACK_SKIP_CI for telemetry runs to prevent weakening production runs
        if os.getenv("AUTOPACK_SKIP_CI") == "1":
            is_telemetry_run = self.run_id.startswith("telemetry-collection-")
            if is_telemetry_run:
                logger.info(
                    f"[{phase_id}] CI skipped (AUTOPACK_SKIP_CI=1 - telemetry seeding mode)"
                )
                return None  # Return None so PhaseFinalizer doesn't run collection error detection
            else:
                logger.warning(
                    f"[{phase_id}] AUTOPACK_SKIP_CI=1 set but run_id '{self.run_id}' is not a telemetry run - ignoring flag and running CI normally"
                )

        # Phase dict from API does not typically include a top-level "ci". Persisted CI hints live under scope.
        scope = phase.get("scope") or {}
        ci_spec = phase.get("ci") or scope.get("ci") or {}

        if ci_spec.get("skip"):
            reason = ci_spec.get("reason", "CI skipped per phase configuration")
            logger.info(f"[{phase_id}] CI skipped: {reason}")
            return {
                "status": "skipped",
                "message": reason,
                "passed": True,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": 0.0,
                "output": "",
                "error": None,
                "skipped": True,
                "suspicious_zero_tests": False,
            }

        ci_type = ci_spec.get("type")
        if ci_spec.get("command") and not ci_type:
            ci_type = "custom"
        if not ci_type:
            ci_type = "pytest"

        if ci_type == "custom":
            return self._run_custom_ci(phase_id, ci_spec)
        else:
            return self._run_pytest_ci(phase_id, ci_spec)

    def _run_pytest_ci(self, phase_id: str, ci_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Run pytest CI checks.

        Extracted to PytestRunner in PR-EXE-13.
        """
        result = self.pytest_runner.run(phase_id, ci_spec, project_slug=self._get_project_slug())
        return result.__dict__

    def _run_custom_ci(self, phase_id: str, ci_spec: Dict[str, Any]) -> Dict[str, Any]:
        """Run custom CI command.

        Extracted to CustomRunner in PR-EXE-13.
        """
        result = self.custom_runner.run(phase_id, ci_spec)
        return result.__dict__

    def _update_phase_status(self, phase_id: str, status: str):
        """Update phase status via API

        Uses the /runs/{run_id}/phases/{phase_id}/update_status endpoint.

        Args:
            phase_id: Phase ID
            status: New status (QUEUED, EXECUTING, GATE, CI_RUNNING, COMPLETE, FAILED, SKIPPED)
        """
        try:
            # The API only accepts models.PhaseState values; "BLOCKED" is a quality-gate outcome,
            # not a phase state. Represent blocked states as FAILED (with quality_blocked set elsewhere)
            # or as GATE where appropriate.
            if status == "BLOCKED":
                status = "FAILED"

            self.api_client.update_phase_status(self.run_id, phase_id, status, timeout=30)
            logger.info(f"Updated phase {phase_id} status to {status}")
            # Best-effort run_summary rewrite when a phase reaches a terminal state
            if status in ("COMPLETE", "FAILED", "SKIPPED"):
                self._best_effort_write_run_summary()
        except Exception as e:
            logger.warning(f"Failed to update phase {phase_id} status: {e}")

    def _try_handle_governance_request(
        self, phase_id: str, error_msg: str, patch_content: str, governed_apply: Any
    ) -> bool:
        """
        Handle protected path governance request (BUILD-127 Phase 2).

        Args:
            phase_id: Phase ID
            error_msg: Error message from apply_patch (may be structured JSON)
            patch_content: Patch content that failed
            governed_apply: GovernedApplyPath instance

        Returns:
            True if governance request was approved and patch applied, False otherwise
        """
        import json
        from autopack.governance_requests import create_governance_request

        # Try to parse as structured error
        try:
            error_data = json.loads(error_msg)

            if error_data.get("error_type") != "protected_path_violation":
                # Not a governance error
                return False

            violated_paths = error_data.get("violated_paths", [])
            justification = error_data.get("justification", "")

            logger.info(
                f"[Governance:{phase_id}] Protected path violation detected: "
                f"{len(violated_paths)} paths"
            )

        except (json.JSONDecodeError, KeyError, TypeError):
            # Not a structured error
            return False

        # Create governance request in database
        request = create_governance_request(
            db_session=self.db_session,
            run_id=self.run_id,
            phase_id=phase_id,
            violated_paths=violated_paths,
            justification=justification,
            risk_scorer=getattr(self, "risk_scorer", None),
        )

        logger.info(
            f"[Governance:{phase_id}] Request {request.request_id} created: "
            f"risk={request.risk_level}, auto_approved={request.auto_approved}"
        )

        # Check if auto-approved
        if request.auto_approved:
            logger.info(f"[Governance:{phase_id}] Auto-approved, retrying patch application")
            return self._retry_with_allowance(
                phase_id, patch_content, violated_paths, governed_apply
            )

        # Request human approval
        logger.info(f"[Governance:{phase_id}] Requesting human approval for {request.request_id}")

        # BUILD-190: Integrate with Telegram approval flow
        try:
            from autopack.notifications.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()
            if notifier.is_configured():
                notifier.send_governance_approval_request(
                    request_id=request.request_id,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    requested_paths=request.requested_paths,
                    risk_level=request.risk_level,
                    justification=request.justification,
                )
                logger.info(f"[Governance:{phase_id}] Sent Telegram approval request")
            else:
                logger.warning(
                    f"[Governance:{phase_id}] Telegram not configured. "
                    f"Approve via: POST /api/governance/approve/{request.request_id}"
                )
        except Exception as e:
            logger.warning(f"[Governance:{phase_id}] Failed to send Telegram notification: {e}")
            logger.warning(
                f"[Governance:{phase_id}] Manual approval required. "
                f"Approve via: POST /api/governance/approve/{request.request_id}"
            )

        # Mark as FAILED (phase state) — the governance request is tracked separately.
        self._update_phase_status(phase_id, "FAILED")
        return False

    def _retry_with_allowance(
        self,
        phase_id: str,
        patch_content: str,
        allowed_paths: List[str],
        original_governed_apply: Any,
    ) -> bool:
        """
        Retry patch application with temporary path allowance overlay (BUILD-127 Phase 2).

        Args:
            phase_id: Phase ID
            patch_content: Patch content to retry
            allowed_paths: Additional paths to allow
            original_governed_apply: Original GovernedApplyPath instance

        Returns:
            True if retry succeeded, False otherwise
        """
        logger.info(f"[Governance:{phase_id}] Retrying with allowance: {len(allowed_paths)} paths")

        # Create permissive governed_apply instance
        governed_apply_permissive = GovernedApplyPath(
            workspace=Path(self.workspace),
            run_type=self.run_type,
            autopack_internal_mode=getattr(
                original_governed_apply, "autopack_internal_mode", False
            ),
            scope_paths=getattr(original_governed_apply, "scope_paths", None),
            allowed_paths=getattr(original_governed_apply, "allowed_paths", []) + allowed_paths,
        )

        # Retry patch application
        patch_success, error_msg = governed_apply_permissive.apply_patch(
            patch_content, full_file_mode=True
        )

        if patch_success:
            logger.info(f"[Governance:{phase_id}] ✅ Retry succeeded with allowance")
            return True
        else:
            logger.error(
                f"[Governance:{phase_id}] ❌ Retry failed even with allowance: {error_msg}"
            )
            return False

    def _request_human_approval(
        self, phase_id: str, quality_report, timeout_seconds: int = 3600
    ) -> bool:
        """
        Request human approval via Telegram for blocked phases.

        Delegates to approval_flow.request_human_approval for testability.

        Args:
            phase_id: Phase identifier
            quality_report: Quality gate report with risk assessment
            timeout_seconds: How long to wait for approval (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out
        """
        return request_human_approval(
            api_client=self.api_client,
            phase_id=phase_id,
            quality_report=quality_report,
            run_id=self.run_id,
            last_files_changed=self._last_files_changed,
            timeout_seconds=timeout_seconds,
        )

    def _request_build113_approval(
        self, phase_id: str, decision, patch_content: str, timeout_seconds: int = 3600
    ) -> bool:
        """
        Request human approval for BUILD-113 RISKY decisions via Telegram.

        Delegates to approval_flow.request_build113_approval for testability.

        Args:
            phase_id: Phase identifier
            decision: BUILD-113 Decision object with risk/confidence details
            patch_content: Full patch content for preview
            timeout_seconds: How long to wait for approval (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out
        """
        return request_build113_approval(
            api_client=self.api_client,
            phase_id=phase_id,
            decision=decision,
            patch_content=patch_content,
            run_id=self.run_id,
            timeout_seconds=timeout_seconds,
        )

    def _request_build113_clarification(
        self, phase_id: str, decision, timeout_seconds: int = 3600
    ) -> Optional[str]:
        """
        Request human clarification for BUILD-113 AMBIGUOUS decisions via Telegram.

        Delegates to approval_flow.request_build113_clarification for testability.

        Args:
            phase_id: Phase identifier
            decision: BUILD-113 Decision object with questions
            timeout_seconds: How long to wait for clarification (default: 1 hour)

        Returns:
            Human response text if provided, None if timed out
        """
        return request_build113_clarification(
            api_client=self.api_client,
            phase_id=phase_id,
            decision=decision,
            run_id=self.run_id,
            timeout_seconds=timeout_seconds,
        )

    def _create_deletion_save_point(self, phase_id: str, net_deletion: int) -> Optional[str]:
        """
        Create a git tag save point before applying large deletions.
        This allows easy recovery if the deletion was a mistake.

        Args:
            phase_id: Phase identifier
            net_deletion: Number of net lines being deleted

        Returns:
            Tag name if successful, None otherwise
        """
        # PR-EXE-4: Delegated to run_checkpoint module
        return create_deletion_savepoint(
            workspace=Path(self.root),
            phase_id=phase_id,
            run_id=self.run_id,
            net_deletion=net_deletion,
        )

    def _send_deletion_notification(self, phase_id: str, quality_report) -> None:
        """
        Send informational Telegram notification for large deletions (100-200 lines).
        This is notification-only - does not block execution.

        Args:
            phase_id: Phase identifier
            quality_report: QualityReport with risk assessment
        """
        try:
            from autopack.notifications.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()

            if not notifier.is_configured():
                return  # Silently skip if not configured

            # Extract deletion info from risk assessment
            risk_assessment = quality_report.risk_assessment
            if not risk_assessment:
                return

            metadata = risk_assessment.get("metadata", {})
            checks = risk_assessment.get("checks", {})
            net_deletion = checks.get("net_deletion", 0)
            loc_removed = metadata.get("loc_removed", 0)
            loc_added = metadata.get("loc_added", 0)
            risk_level = risk_assessment.get("risk_level", "unknown")
            risk_score = risk_assessment.get("risk_score", 0)

            # Determine emoji based on risk level
            risk_emoji = {
                "low": "✅",
                "medium": "⚠️",
                "high": "🔴",
                "critical": "🚨",
            }.get(risk_level, "❓")

            # Format message
            message = (
                f"📊 *Autopack Deletion Notification*\\n\\n"
                f"*Run*: `{self.run_id}`\\n"
                f"*Phase*: `{phase_id}`\\n"
                f"*Risk*: {risk_emoji} {risk_level.upper()} (score: {risk_score}/100)\\n\\n"
                f"*Net Deletion*: {net_deletion} lines\\n"
                f"  ├─ Removed: {loc_removed}\\n"
                f"  └─ Added: {loc_added}\\n\\n"
                f"ℹ️ _This is informational only. Execution continues automatically._\\n\\n"
                f"_Time_: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

            # Send notification (no buttons needed, just FYI)
            notifier.send_completion_notice(phase_id=phase_id, status="info", message=message)

            logger.info(f"[{phase_id}] Sent deletion notification to Telegram (informational only)")

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to send deletion notification: {e}")

    def _send_phase_failure_notification(self, phase_id: str, reason: str) -> None:
        """
        Send Telegram notification when a phase fails or gets stuck.

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED", "BUILDER_FAILED")
        """
        try:
            from autopack.notifications.telegram_notifier import TelegramNotifier

            notifier = TelegramNotifier()

            if not notifier.is_configured():
                return  # Silently skip if not configured

            # Determine emoji based on failure type
            emoji = "❌"
            if "EXHAUSTED" in reason:
                emoji = "🔁"  # Retry exhausted
            elif "TIMEOUT" in reason:
                emoji = "⏱️"  # Timeout
            elif "STUCK" in reason:
                emoji = "⚠️"  # Stuck

            # Format message
            message = (
                f"{emoji} *Autopack Phase Failed*\\n\\n"
                f"*Run*: `{self.run_id}`\\n"
                f"*Phase*: `{phase_id}`\\n"
                f"*Reason*: {reason}\\n\\n"
                f"The executor has halted. Please review the logs and take action.\\n\\n"
                f"_Time_: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )

            # Send notification (no buttons needed for failures, just FYI)
            notifier.send_completion_notice(phase_id=phase_id, status="failed", message=message)

            logger.info(f"[{phase_id}] Sent failure notification to Telegram")

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to send Telegram notification: {e}")

    def _force_mark_phase_failed(self, phase_id: str) -> bool:
        """
        [Self-Troubleshoot] Force mark a phase as FAILED directly in database.

        This bypasses the API when it's returning errors, ensuring we can
        progress past stuck phases.

        Returns:
            bool: True if successfully updated, False otherwise
        """
        # BUILD-115: Direct database update disabled (models.py removed)
        # Fall through to API-based status update below

        # Try API as fallback (with retries)
        for attempt in range(3):
            try:
                self._update_phase_status(phase_id, "FAILED")
                logger.info(
                    f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED via API (attempt {attempt + 1})"
                )
                return True
            except Exception as e:
                logger.warning(f"[Self-Troubleshoot] API update attempt {attempt + 1} failed: {e}")
                time.sleep(1)

        logger.error(
            f"[Self-Troubleshoot] All attempts to mark phase {phase_id} as FAILED have failed"
        )
        return False

    def _ensure_api_server_running(self) -> bool:
        """Extracted to ApiServerLifecycle in PR-EXE-12."""
        return self.api_server_lifecycle.ensure_server_running()

    def run_autonomous_loop(
        self,
        poll_interval: int = 10,
        max_iterations: Optional[int] = None,
        stop_on_first_failure: bool = False,
    ):
        """Extracted to AutonomousLoop in PR-EXE-12."""
        return self.autonomous_loop.run(poll_interval, max_iterations, stop_on_first_failure)

    def _best_effort_write_run_summary(
        self,
        phases_failed: Optional[int] = None,
        failure_reason: Optional[str] = None,
        allow_run_state_mutation: bool = False,
    ):
        """
        Write run_summary.md even if API hooks fail (covers short single-phase runs).
        """
        try:
            # BUILD-115: from autopack import models
            from autopack import models
            from datetime import datetime, timezone

            run = self.db_session.query(models.Run).filter(models.Run.id == self.run_id).first()
            if not run:
                return

            # IMPORTANT:
            # This helper is invoked opportunistically (e.g., after a phase hits a terminal status),
            # and MUST NOT finalize or otherwise mutate the run state unless explicitly requested.
            #
            # Without this guard, a single transient failure (with retries remaining) can incorrectly
            # flip the run into DONE_FAILED_REQUIRES_HUMAN_REVIEW, preventing convergence.
            if allow_run_state_mutation:
                # Derive a conservative terminal state if DB state is missing or stale
                terminal_run_states = {
                    models.RunState.DONE_SUCCESS,
                    models.RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW,
                    models.RunState.DONE_FAILED_BUDGET_EXHAUSTED,
                    models.RunState.DONE_FAILED_POLICY_VIOLATION,
                    models.RunState.DONE_FAILED_ENVIRONMENT,
                }
                if run.state not in terminal_run_states:
                    # If caller provided explicit failure count, trust it
                    if phases_failed is not None and phases_failed > 0:
                        run.state = models.RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                    else:
                        # Fall back to DB snapshot: if any phase is non-COMPLETE, mark failed
                        failed_phases = [
                            p for p in run.phases if p.state != models.PhaseState.COMPLETE
                        ]
                        if failed_phases:
                            run.state = models.RunState.DONE_FAILED_REQUIRES_HUMAN_REVIEW
                        else:
                            run.state = models.RunState.DONE_SUCCESS

            # Calculate phase stats
            all_phases = list(run.phases)
            phases_complete = sum(1 for p in all_phases if p.state == models.PhaseState.COMPLETE)
            actual_phases_failed = sum(1 for p in all_phases if p.state == models.PhaseState.FAILED)

            layout = RunFileLayout(self.run_id, project_id=self.project_id)
            layout.write_run_summary(
                run_id=run.id,
                state=run.state.value,
                safety_profile=run.safety_profile,
                run_scope=run.run_scope,
                created_at=run.created_at.isoformat(),
                tier_count=len(run.tiers),
                phase_count=len(all_phases),
                tokens_used=run.tokens_used,
                phases_complete=phases_complete,
                phases_failed=phases_failed if phases_failed is not None else actual_phases_failed,
                failure_reason=failure_reason or getattr(run, "failure_reason", None),
                completed_at=datetime.now(timezone.utc).isoformat(),
            )
            self.db_session.commit()
        except Exception as e:
            logger.warning(f"Failed to write run_summary from executor: {e}")

    def _model_to_provider(self, model: str) -> Optional[str]:
        """
        Lightweight model→provider mapping for infra health gating.
        """
        if not model:
            return None
        m = model.lower()
        if m.startswith("claude") or "opus" in m:
            return "anthropic"
        if m.startswith("gpt") or m.startswith("o1"):
            return "openai"
        if m.startswith("gemini"):
            return "google_gemini"
        if m.startswith("glm"):
            return "zhipu_glm"
        return None


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

  # Backlog maintenance (diagnostics/apply gated)
  python autonomous_executor.py --run-id backlog-maint ^
    --maintenance-plan .autonomous_runs/backlog_plan.json ^
    --maintenance-patch-dir patches ^
    --maintenance-apply --maintenance-checkpoint

Environment Variables:
  GLM_API_KEY          GLM (Zhipu AI) API key (primary provider)
  GLM_API_BASE         GLM API base URL (optional)
  ANTHROPIC_API_KEY    Anthropic API key (for Claude models)
  OPENAI_API_KEY       OpenAI API key (fallback for gpt-* models)
  AUTOPACK_API_KEY     Autopack API key (optional)
  AUTOPACK_API_URL     Autopack API URL (default: http://localhost:8000)
        """,
    )

    # Required arguments
    parser.add_argument("--run-id", required=True, help="Autopack run ID to execute")
    parser.add_argument(
        "--maintenance-plan",
        type=Path,
        default=None,
        help="Optional backlog maintenance plan JSON (propose-first diagnostics, optional apply)",
    )
    parser.add_argument(
        "--maintenance-patch-dir",
        type=Path,
        default=None,
        help="Directory containing patches named <item_id>.patch for maintenance apply",
    )
    parser.add_argument(
        "--maintenance-apply",
        action="store_true",
        help="Attempt to apply maintenance patches if auditor approves (requires checkpoint)",
    )
    parser.add_argument(
        "--maintenance-auto-apply-low-risk",
        action="store_true",
        help="Auto-apply only auditor-approved, low-risk patches (in-scope, small diff, tests passing) with checkpoint",
    )
    parser.add_argument(
        "--maintenance-checkpoint",
        action="store_true",
        help="Create a git checkpoint before maintenance apply (required for apply path)",
    )

    # Optional arguments
    parser.add_argument(
        "--api-url",
        default=os.getenv("AUTOPACK_API_URL", "http://localhost:8000"),
        help="Autopack API URL (default: http://localhost:8000)",
    )

    parser.add_argument(
        "--api-key",
        default=os.getenv("AUTOPACK_API_KEY"),
        help="Autopack API key (default: $AUTOPACK_API_KEY)",
    )

    parser.add_argument(
        "--glm-key",
        default=os.getenv("GLM_API_KEY"),
        help="GLM (Zhipu AI) API key - primary provider (default: $GLM_API_KEY)",
    )

    parser.add_argument(
        "--anthropic-key",
        default=os.getenv("ANTHROPIC_API_KEY"),
        help="Anthropic API key for Claude models (default: $ANTHROPIC_API_KEY)",
    )

    parser.add_argument(
        "--openai-key",
        default=os.getenv("OPENAI_API_KEY"),
        help="OpenAI API key - fallback for gpt-* models (default: $OPENAI_API_KEY)",
    )

    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("."),
        help="Workspace root directory (default: current directory)",
    )

    parser.add_argument(
        "--poll-interval",
        type=int,
        default=10,
        help="Seconds between polling for next phase (default: 10)",
    )

    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum number of phases to execute (default: unlimited)",
    )

    parser.add_argument(
        "--no-dual-auditor",
        action="store_true",
        help="Disable dual auditor mode (use single auditor)",
    )

    parser.add_argument(
        "--run-type",
        choices=["project_build", "autopack_maintenance", "autopack_upgrade", "self_repair"],
        default="project_build",
        help="Run type: project_build (default), autopack_maintenance (allows src/autopack/ modification)",
    )

    parser.add_argument(
        "--enable-second-opinion",
        action="store_true",
        help="Enable second opinion triage for diagnostics (requires API key)",
    )

    parser.add_argument(
        "--enable-autonomous-fixes",
        action="store_true",
        help="Enable autonomous fixes for low-risk issues (BUILD-113)",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    parser.add_argument(
        "--stop-on-first-failure",
        action="store_true",
        help="Stop execution immediately when any phase fails (saves token usage)",
    )

    # BUILD-146 P6.1: Plan Normalization CLI integration
    parser.add_argument(
        "--raw-plan-file",
        type=Path,
        default=None,
        help="Path to raw unstructured plan file (enables plan normalization)",
    )

    parser.add_argument(
        "--enable-plan-normalization",
        action="store_true",
        help="Enable plan normalization (transform unstructured plans to structured run specs)",
    )

    args = parser.parse_args()

    # Configure logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # BUILD-146 P6.1: Plan Normalization (ingestion-time transformation)
    if args.enable_plan_normalization and args.raw_plan_file:
        try:
            from autopack.plan_normalizer import PlanNormalizer

            logger.info(f"[BUILD-146 P6.1] Normalizing raw plan from: {args.raw_plan_file}")

            # Read raw plan
            with open(args.raw_plan_file, "r") as f:
                raw_plan_text = f.read()

            # Normalize to structured run spec
            normalizer = PlanNormalizer(project_id=args.run_id)
            normalized_run = normalizer.normalize_plan(
                raw_plan_text=raw_plan_text, run_id=args.run_id
            )

            # Write normalized run spec to file
            normalized_path = args.raw_plan_file.parent / f"{args.run_id}_normalized.json"
            with open(normalized_path, "w") as f:
                json.dump(normalized_run.to_dict(), f, indent=2)

            logger.info(f"[BUILD-146 P6.1] Normalized plan written to: {normalized_path}")
            logger.info(f"[BUILD-146 P6.1] Run ID: {normalized_run.run_id}")
            logger.info(f"[BUILD-146 P6.1] Tiers: {len(normalized_run.tiers)}")
            logger.info(
                f"[BUILD-146 P6.1] Total phases: {sum(len(t.phases) for t in normalized_run.tiers)}"
            )

            # Exit after normalization (user should review before execution)
            logger.info(
                "[BUILD-146 P6.1] Plan normalization complete. Review the normalized plan and submit to API."
            )
            sys.exit(0)

        except Exception as e:
            logger.error(f"[BUILD-146 P6.1] Plan normalization failed: {e}", exc_info=True)
            sys.exit(1)
    elif args.enable_plan_normalization and not args.raw_plan_file:
        logger.error("[BUILD-146 P6.1] --enable-plan-normalization requires --raw-plan-file")
        sys.exit(1)

    # BUILD-048-T1: Acquire executor lock to prevent duplicates
    lock_manager = ExecutorLockManager(args.run_id)
    if not lock_manager.acquire():
        logger.error(
            f"Another executor is already running for run_id={args.run_id}. "
            f"Exiting to prevent duplicate work and token waste."
        )
        sys.exit(1)

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
            enable_second_opinion=args.enable_second_opinion,
            enable_autonomous_fixes=args.enable_autonomous_fixes,
        )
    except ValueError as e:
        logger.error(f"Failed to initialize executor: {e}")
        sys.exit(1)

    if args.maintenance_plan:
        executor.run_backlog_maintenance(
            plan_path=args.maintenance_plan,
            patch_dir=args.maintenance_patch_dir,
            apply=args.maintenance_apply or args.maintenance_auto_apply_low_risk,
            allowed_paths=None,
            # Default to checkpointing for maintenance runs even without apply (safe guard)
            checkpoint=True,
            auto_apply_low_risk=args.maintenance_auto_apply_low_risk,
        )
        return

    # Run autonomous loop
    try:
        executor.run_autonomous_loop(
            poll_interval=args.poll_interval,
            max_iterations=args.max_iterations,
            stop_on_first_failure=args.stop_on_first_failure,
        )
    except KeyboardInterrupt:
        logger.info("Interrupted by user, shutting down...")
        sys.exit(0)
    except Exception as e:
        import traceback

        logger.error(f"Fatal error: {e}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")
        sys.exit(1)
    finally:
        # BUILD-048-T1: Release executor lock
        lock_manager.release()


if __name__ == "__main__":
    main()
