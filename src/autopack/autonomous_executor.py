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
import shlex
import time
import json
import argparse
import logging
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import requests
import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

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
from autopack.debug_journal import log_error, log_fix
from autopack.error_reporter import report_error
from autopack.archive_consolidator import log_build_event
from autopack.learned_rules import (
    load_project_rules,
    get_active_rules_for_phase,
    get_relevant_hints_for_phase,
    promote_hints_to_rules,
    save_run_hint,
)
from autopack.health_checks import run_health_checks
from autopack.file_layout import RunFileLayout
from autopack.maintenance_auditor import (
    AuditorInput,
    DiffStats,
    TestResult,
    evaluate as audit_evaluate,
)
from autopack.backlog_maintenance import parse_patch_stats, create_git_checkpoint
from autopack.deliverables_validator import (
    validate_deliverables,
    format_validation_feedback_for_builder,
)

# Memory and validation imports
# BUILD-115: models.py removed - database write code disabled below
# from autopack import models
from autopack.diagnostics.diagnostics_agent import DiagnosticsAgent
from autopack.memory import MemoryService, should_block_on_drift, extract_goal_from_description
from autopack.validators import validate_yaml_syntax, validate_docker_compose

# BUILD-123v2: Manifest Generator imports
from autopack.manifest_generator import ManifestGenerator

# from autopack.scope_expander import ScopeExpander  # BUILD-126: Temporarily disabled

# BUILD-127 Phase 1: Completion authority with baseline tracking
from autopack.phase_finalizer import PhaseFinalizer
from autopack.test_baseline_tracker import TestBaselineTracker
from autopack.phase_auto_fixer import auto_fix_phase_scope


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

        # [Run-Level Health Budget] Prevent infinite retry loops (GPT_RESPONSE5 recommendation)
        self._run_http_500_count: int = 0  # Count of HTTP 500 errors in this run
        self._run_patch_failure_count: int = 0  # Count of patch failures in this run
        self._run_total_failures: int = 0  # Total recoverable failures in this run
        self.MAX_HTTP_500_PER_RUN = 10  # Stop run after this many 500 errors
        self.MAX_PATCH_FAILURES_PER_RUN = 15  # Stop run after this many patch failures

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
        #         self.scope_expander = ScopeExpander(
        #             workspace=self.workspace,
        #             repo_scanner=self.manifest_generator.scanner,
        #             autopack_internal_mode=autopack_internal_mode,
        #             run_type=self.run_type,
        #         )
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
        """
        Run a backlog maintenance plan with diagnostics + optional apply.
        - Diagnostics always run.
        - Apply happens only if:
            * auditor verdict == approve
            * checkpoint creation succeeded
            * patch is present
        """
        try:
            import json as _json

            plan = _json.loads(Path(plan_path).read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"[Backlog] Failed to load plan {plan_path}: {e}")
            return

        phases = plan.get("phases", [])
        default_allowed = allowed_paths or [
            "src/autopack/",
            "src/frontend/",
            "Dockerfile",
            "docker-compose",
            "README",
            "docs/",
            "scripts/",
            "tests/",
        ]
        protected_paths = ["config/", ".autonomous_runs/", ".git/"]

        diag_dir = Path(".autonomous_runs") / self.run_id / "diagnostics"
        diag_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_hash = None
        if apply and checkpoint:
            ok, checkpoint_hash = create_git_checkpoint(
                Path(self.workspace), message=f"[Autopack] Backlog checkpoint {self.run_id}"
            )
            if ok:
                logger.info(f"[Backlog] Checkpoint created: {checkpoint_hash}")
            else:
                logger.warning(f"[Backlog] Checkpoint failed: {checkpoint_hash}")

        summaries = []
        for phase in phases:
            phase_id = phase.get("id")
            desc = phase.get("description")
            logger.info(f"[Backlog] Diagnostics for {phase_id}: {desc}")
            outcome = self.diagnostics_agent.run_diagnostics(
                failure_class="maintenance",
                context={
                    "phase_id": phase_id,
                    "description": desc,
                    "backlog_summary": phase.get("metadata", {}).get("backlog_summary"),
                },
                phase_id=phase_id,
                mode="maintenance",
            )

            test_results = []
            if test_commands:
                try:
                    from autopack.maintenance_runner import run_tests

                    test_results = run_tests(test_commands, workspace=Path(self.workspace))
                except Exception as e:
                    logger.warning(f"[Backlog][Tests] Failed to run tests for {phase_id}: {e}")

            patch_path = None
            if patch_dir:
                candidate = Path(patch_dir) / f"{phase_id}.patch"
                if candidate.exists():
                    patch_path = candidate

            diff_stats = DiffStats(files_changed=[], lines_added=0, lines_deleted=0)
            if patch_path:
                diff_stats = parse_patch_stats(
                    patch_path.read_text(encoding="utf-8", errors="ignore")
                )

            auditor_input = AuditorInput(
                allowed_paths=default_allowed,
                protected_paths=protected_paths,
                diff=diff_stats,
                tests=[TestResult(name=t.name, status=t.status) for t in test_results],
                failure_class="maintenance",
                item_context=phase.get("metadata", {}).get("backlog_summary", "") or desc or "",
                diagnostics_summary=outcome.ledger_summary,
                max_files=max_files,
                max_lines=max_lines,
            )
            decision = audit_evaluate(auditor_input)
            logger.info(
                f"[Backlog][Auditor] {phase_id}: verdict={decision.verdict} reasons={decision.reasons}"
            )

            self._record_decision_entry(
                trigger="backlog_maintenance",
                choice=f"audit:{decision.verdict}",
                rationale="; ".join(decision.reasons)[:500],
                phase_id=phase_id,
                alternatives="approve,require_human,reject",
            )

            apply_result = None
            if apply and patch_path and decision.verdict == "approve" and checkpoint_hash:
                # If auto_apply_low_risk, enforce stricter bounds
                if auto_apply_low_risk:
                    if (
                        len(diff_stats.files_changed) > max_files
                        or (diff_stats.lines_added + diff_stats.lines_deleted) > max_lines
                    ):
                        logger.info(
                            f"[Backlog][Apply] Skipping apply (auto-apply low risk) due to size: files={len(diff_stats.files_changed)}, lines={diff_stats.lines_added + diff_stats.lines_deleted}"
                        )
                        apply_result = {"success": False, "error": "auto_apply_low_risk_size_guard"}
                    elif any(t.status != "passed" for t in test_results):
                        logger.info(
                            "[Backlog][Apply] Skipping apply (auto-apply low risk) due to tests not all passing"
                        )
                        apply_result = {
                            "success": False,
                            "error": "auto_apply_low_risk_tests_guard",
                        }
                    else:
                        gap = GovernedApplyPath(
                            workspace=Path(self.workspace),
                            allowed_paths=default_allowed,
                            protected_paths=protected_paths,
                            run_type="project_build",
                        )
                        success, err = gap.apply_patch(
                            patch_path.read_text(encoding="utf-8", errors="ignore")
                        )
                        apply_result = {"success": success, "error": err}
                        if success:
                            logger.info(f"[Backlog][Apply] Success for {phase_id}")
                        else:
                            logger.warning(f"[Backlog][Apply] Failed for {phase_id}: {err}")
                            if checkpoint_hash:
                                logger.info(
                                    "[Backlog][Apply] Reverting to checkpoint due to failure"
                                )
                                from autopack.backlog_maintenance import revert_to_checkpoint

                                revert_to_checkpoint(Path(self.workspace), checkpoint_hash)
                else:
                    gap = GovernedApplyPath(
                        workspace=Path(self.workspace),
                        allowed_paths=default_allowed,
                        protected_paths=protected_paths,
                        run_type="project_build",
                    )
                    success, err = gap.apply_patch(
                        patch_path.read_text(encoding="utf-8", errors="ignore")
                    )
                    apply_result = {"success": success, "error": err}
                    if success:
                        logger.info(f"[Backlog][Apply] Success for {phase_id}")
                    else:
                        logger.warning(f"[Backlog][Apply] Failed for {phase_id}: {err}")
                        if checkpoint_hash:
                            logger.info("[Backlog][Apply] Reverting to checkpoint due to failure")
                            from autopack.backlog_maintenance import revert_to_checkpoint

                            revert_to_checkpoint(Path(self.workspace), checkpoint_hash)
            elif apply and patch_path is None:
                logger.info(f"[Backlog][Apply] No patch for {phase_id}, skipping apply")
            elif apply and decision.verdict != "approve":
                logger.info(
                    f"[Backlog][Apply] Skipped {phase_id}: auditor verdict {decision.verdict}"
                )
            elif apply and not checkpoint_hash:
                logger.info(f"[Backlog][Apply] Skipped {phase_id}: no checkpoint")

            summaries.append(
                {
                    "phase_id": phase_id,
                    "ledger": outcome.ledger_summary,
                    "auditor_verdict": decision.verdict,
                    "auditor_reasons": decision.reasons,
                    "apply_result": apply_result,
                    "patch_path": str(patch_path) if patch_path else None,
                    "checkpoint": checkpoint_hash,
                    "tests": [t.__dict__ for t in test_results],
                }
            )

        try:
            import json as _json

            summary_path = diag_dir / "backlog_executor_summary.json"
            summary_path.write_text(_json.dumps(summaries, indent=2), encoding="utf-8")
            logger.info(f"[Backlog] Summary written to {summary_path}")
        except Exception as e:
            logger.warning(f"[Backlog] Failed to write summary: {e}")

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
            project_id, phase  # Pass project_id string, not self.project_rules list
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
        url = f"{self.api_url}/runs/{self.run_id}"
        headers = {}
        if self.api_key:
            headers["X-API-Key"] = self.api_key

        # Try to fetch status with circuit breaker logic
        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            # Classify error to determine retry strategy
            status_code = e.response.status_code if e.response else 0
            response_body = e.response.text if e.response else str(e)

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
                    f"[CircuitBreaker] Retrying after {backoff}s (attempt {attempt+1}/{max_retries})"
                )
                import time

                time.sleep(backoff)

                try:
                    response = requests.get(url, headers=headers, timeout=10)
                    response.raise_for_status()
                    logger.info(f"[CircuitBreaker] Retry successful on attempt {attempt+1}")
                    return response.json()
                except requests.exceptions.HTTPError:
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
        """Fetch phase from database with attempt tracking state

        Args:
            phase_id: Phase identifier (e.g., "fileorg-p2-test-fixes")

        Returns:
            Phase model instance with current attempt state, or None if not found
        """
        try:
            from autopack.database import SessionLocal
            from autopack.models import Phase

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            if phase:
                logger.debug(
                    f"[{phase_id}] Loaded from DB: retry_attempt={phase.retry_attempt}, revision_epoch={phase.revision_epoch}, escalation_level={phase.escalation_level}, "
                    f"state={phase.state}"
                )
            else:
                logger.warning(f"[{phase_id}] Not found in database")

            return phase

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to fetch from database: {e}")
            return None

    def _update_phase_attempts_in_db(
        self,
        phase_id: str,
        attempts_used: int = None,
        last_failure_reason: Optional[str] = None,
        timestamp: Optional[Any] = None,
        # BUILD-050 Phase 2: Support decoupled counters
        retry_attempt: Optional[int] = None,
        revision_epoch: Optional[int] = None,
        escalation_level: Optional[int] = None,
    ) -> bool:
        """Update phase attempt tracking in database

        Args:
            phase_id: Phase identifier
            attempts_used: DEPRECATED - use retry_attempt instead (kept for backwards compatibility)
            last_failure_reason: Failure status from most recent attempt
            timestamp: Timestamp of last attempt (defaults to now)
            retry_attempt: BUILD-050 - Monotonic retry counter (for hints and escalation)
            revision_epoch: BUILD-050 - Replan counter (increments on Doctor replan)
            escalation_level: BUILD-050 - Model escalation level (0=base, 1=escalated, etc.)

        Returns:
            True if update successful, False otherwise
        """
        try:
            from datetime import datetime, timezone
            from autopack.database import SessionLocal
            from autopack.models import Phase

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(
                        f"[{phase_id}] Cannot update attempts: phase not found in database"
                    )
                    return False

                # Update attempt tracking (backwards compatibility)
                if attempts_used is not None and hasattr(phase, "attempts_used"):
                    phase.attempts_used = attempts_used

                # BUILD-050 Phase 2: Update decoupled counters
                if retry_attempt is not None:
                    phase.retry_attempt = retry_attempt
                if revision_epoch is not None:
                    phase.revision_epoch = revision_epoch
                if escalation_level is not None:
                    phase.escalation_level = escalation_level

                if last_failure_reason:
                    phase.last_failure_reason = last_failure_reason
                if hasattr(phase, "last_attempt_timestamp"):
                    phase.last_attempt_timestamp = timestamp or datetime.now(timezone.utc)

                # Log while the instance is still bound to a live Session.
                if (
                    retry_attempt is not None
                    or revision_epoch is not None
                    or escalation_level is not None
                ):
                    logger.info(
                        f"[{phase_id}] Updated counters in DB: "
                        f"retry={phase.retry_attempt}, epoch={phase.revision_epoch}, "
                        f"escalation={phase.escalation_level} "
                        f"(reason: {last_failure_reason or 'N/A'})"
                    )
                else:
                    logger.info(
                        f"[{phase_id}] Updated attempts in DB: retry={retry_attempt}, epoch={revision_epoch}, escalation={escalation_level} "
                        f"(reason: {last_failure_reason or 'N/A'})"
                    )

                db.commit()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to update attempts in database: {e}")
            return False

    def _mark_phase_complete_in_db(self, phase_id: str) -> bool:
        """Mark phase as COMPLETE in database

        Args:
            phase_id: Phase identifier

        Returns:
            True if update successful, False otherwise
        """
        try:
            from datetime import datetime, timezone
            from autopack.database import SessionLocal
            from autopack.models import Phase, PhaseState

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark complete: phase not found in database")
                    return False

                # Update to COMPLETE state
                phase.state = PhaseState.COMPLETE
                phase.completed_at = datetime.now(timezone.utc)

                # Capture timestamps for phase proof
                phase_created_at = phase.created_at or datetime.now(timezone.utc)
                phase_completed_at = phase.completed_at

                db.commit()

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

            finally:
                try:
                    db.close()
                except Exception:
                    pass

            logger.info(f"[{phase_id}] Marked COMPLETE in database")
            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark complete in database: {e}")
            return False

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
        """Mark phase as FAILED in database

        Args:
            phase_id: Phase identifier
            reason: Failure reason (e.g., "MAX_ATTEMPTS_EXHAUSTED", "BUILDER_FAILED")

        Returns:
            True if update successful, False otherwise
        """
        try:
            from datetime import datetime, timezone
            from autopack.database import SessionLocal
            from autopack.models import Phase, PhaseState

            db = SessionLocal()
            try:
                phase = (
                    db.query(Phase)
                    .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                    .first()
                )

                if not phase:
                    logger.error(f"[{phase_id}] Cannot mark failed: phase not found in database")
                    return False

                # Update to FAILED state
                phase.state = PhaseState.FAILED
                phase.last_failure_reason = reason
                phase.completed_at = datetime.now(timezone.utc)

                # Capture timestamps and error for phase proof
                phase_created_at = phase.created_at or datetime.now(timezone.utc)
                phase_completed_at = phase.completed_at
                error_summary = reason

                db.commit()

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
                            error_summary=error_summary,
                        )
                    except Exception as proof_err:
                        logger.warning(
                            f"[{phase_id}] Failed to write phase proof (non-fatal): {proof_err}"
                        )

            finally:
                try:
                    db.close()
                except Exception:
                    pass

            logger.info(f"[{phase_id}] Marked FAILED in database (reason: {reason})")

            # BUILD-145 P1: Record token efficiency telemetry for failed phases
            self._record_token_efficiency_telemetry(phase_id, "FAILED")

            # Send Telegram notification for phase failure
            self._send_phase_failure_notification(phase_id, reason)

            return True

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to mark failed in database: {e}")
            return False

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

            # OBSOLETE CODE BELOW (kept for reference, never executes):
            # from autopack.database import get_db
            # from autopack.models import Phase, PhaseState, Tier, Run
            # from datetime import datetime, timezone
            #
            # db = next(get_db())
            #
            # # Tier gating: for multi-tier runs, only execute phases in the earliest tier
            # # that still has incomplete work. This prevents later chunks from running
            # # when an earlier chunk has FAILED and requires human review.
            # run = db.query(Run).filter(Run.id == self.run_id).first()
            # active_tier_index: Optional[int] = None
            # if run and getattr(run, "run_scope", None) == "multi_tier":
            #     # Find the earliest tier index that contains any non-COMPLETE phase.
            #     active_tier_index = db.query(Tier.tier_index).join(
            #         Phase, Phase.tier_id == Tier.id
            #     ).filter(
            #         Phase.run_id == self.run_id,
            #         Phase.state != PhaseState.COMPLETE,
            #     ).order_by(Tier.tier_index.asc()).limit(1).scalar()
            #
            # # AUTO-RESET: Reset FAILED phases with retries remaining to QUEUED
            # # This allows BUILD-041 through BUILD-045 fixes to be applied on retry
            # failed_phases_with_retries = db.query(Phase).filter(
            #     Phase.run_id == self.run_id,
            #     Phase.state == PhaseState.FAILED,
            #     # BUILD-041/050: retry budget is governed by retry_attempt (decoupled counters),
            #     # not builder_attempts. Using builder_attempts here can cause an infinite
            #     # FAILED↔QUEUED loop after retry_attempt is exhausted.
            #     Phase.retry_attempt < MAX_RETRY_ATTEMPTS
            # ).all()
            #
            # if failed_phases_with_retries:
            #     logger.info(f"[AUTO-RESET] Found {len(failed_phases_with_retries)} FAILED phases with retries remaining")
            #     for phase in failed_phases_with_retries:
            #         logger.info(
            #             f"[AUTO-RESET] Resetting {phase.phase_id} to QUEUED "
            #             f"(retry_attempt: {phase.retry_attempt}/{MAX_RETRY_ATTEMPTS})"
            #         )
            #         phase.state = PhaseState.QUEUED
            #         phase.started_at = None
            #         phase.completed_at = None
            #         phase.updated_at = datetime.now(timezone.utc)
            #     db.commit()
            #
            # # Query for executable phases:
            # # - QUEUED phases (not yet started OR just auto-reset from FAILED)
            # # - EXECUTING phases with retries available (retry_attempt < MAX_RETRY_ATTEMPTS)
            # executable_phases = db.query(Phase, Tier).join(
            #     Tier, Phase.tier_id == Tier.id
            # ).filter(
            #     Phase.run_id == self.run_id,
            #     (
            #         (Phase.state == PhaseState.QUEUED) |
            #         (
            #             (Phase.state == PhaseState.EXECUTING) &
            #             (Phase.retry_attempt < MAX_RETRY_ATTEMPTS)
            #         )
            #     ),
            #     # If multi-tier gating is active, only execute phases from the active tier.
            #     True if active_tier_index is None else (Tier.tier_index == active_tier_index),
            # ).order_by(
            #     Tier.tier_index,
            #     Phase.phase_index
            # ).all()
            #
            # if not executable_phases:
            #     logger.debug(f"[{self.run_id}] No executable phases found in database")
            #     return None
            #
            # # Unpack tuple from join (phase_db, tier_db)
            # phase_db, tier_db = executable_phases[0]
            # logger.info(
            #     f"[{phase_db.phase_id}] Found executable phase: "
            #     f"state={phase_db.state}, attempts={phase_db.builder_attempts}/{phase_db.max_builder_attempts}"
            # )
            #
            # # Convert database model to dict for compatibility with existing code
            # phase_dict = {
            #     "phase_id": phase_db.phase_id,
            #     "run_id": phase_db.run_id,
            #     # Prefer stable external tier identifier (string) for logs/issue tracking.
            #     "tier_id": tier_db.tier_id,
            #     # Keep DB PK available for internal/debug use.
            #     "tier_db_id": phase_db.tier_id,
            #     "tier_index": tier_db.tier_index,
            #     "phase_index": phase_db.phase_index,
            #     "name": phase_db.name,
            #     "description": phase_db.description,
            #     "state": phase_db.state.value if hasattr(phase_db.state, 'value') else str(phase_db.state),
            #     "complexity": phase_db.complexity,
            #     "task_category": phase_db.task_category,
            #     "scope": getattr(phase_db, 'scope', None) or {},  # Read actual scope config from database
            #     "dependencies": getattr(phase_db, 'dependencies', None) or [],
            #     "acceptance_criteria": getattr(phase_db, 'acceptance_criteria', None) or [],
            #     "builder_attempts": phase_db.builder_attempts,
            #     "max_builder_attempts": phase_db.max_builder_attempts,
            #     "auditor_attempts": phase_db.auditor_attempts,
            #     "max_auditor_attempts": phase_db.max_auditor_attempts,
            # }
            #
            # return phase_dict

        except Exception as e:
            logger.error(f"[{self.run_id}] Failed to query executable phases from database: {e}")
            return None

    def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
        """Execute Builder -> Auditor -> QualityGate pipeline for a phase with database-backed state persistence

        BUILD-041: This method now executes ONE attempt per call, relying on the database for retry state.
        - Database tracks: retry_attempt, revision_epoch, escalation_level, last_attempt_timestamp, last_failure_reason
        - Model escalation: attempts 0-1 use cheap models, 2-3 mid-tier, 4+ strongest
        - Main loop handles retries by re-invoking this method

        Args:
            phase: Phase data from API or database

        Returns:
            Tuple of (success: bool, status: str)
            status can be: "COMPLETE", "FAILED", "BLOCKED"
        """
        phase_id = phase.get("phase_id")

        # INSERTION POINT 2: Track phase state for intention-first loop (BUILD-161 Phase A)
        if hasattr(self, "_intention_wiring") and self._intention_wiring is not None:
            from autopack.autonomous.executor_wiring import get_or_create_phase_state

            phase_state = get_or_create_phase_state(self._intention_wiring, phase_id)
            # Increment iterations_used at phase start
            phase_state.iterations_used += 1
            logger.debug(
                f"[IntentionFirst] Phase {phase_id}: iteration {phase_state.iterations_used}"
            )
        else:
            phase_state = None

        # BUILD-123v2: Generate scope manifest if missing or incomplete
        scope_config = phase.get("scope") or {}
        if not scope_config.get("paths"):
            logger.info(f"[BUILD-123v2] Phase '{phase_id}' has no scope - generating manifest...")
            try:
                # Create minimal plan for this phase
                minimal_plan = {"run_id": self.run_id, "phases": [phase]}

                # Generate manifest
                result = self.manifest_generator.generate_manifest(
                    plan_data=minimal_plan, skip_validation=False  # Run preflight validation
                )

                if result.success and result.enhanced_plan["phases"]:
                    enhanced_phase = result.enhanced_plan["phases"][0]
                    scope_config = enhanced_phase.get("scope", {})

                    # Update phase with generated scope
                    phase["scope"] = scope_config

                    # Log confidence
                    confidence = result.confidence_scores.get(phase_id, 0.0)
                    category = enhanced_phase.get("metadata", {}).get("category", "unknown")
                    logger.info(
                        f"[BUILD-123v2] Generated scope for '{phase_id}': "
                        f"category={category}, confidence={confidence:.1%}, "
                        f"files={len(scope_config.get('paths', []))}"
                    )

                    # Warn if low confidence
                    if confidence < 0.30:
                        logger.warning(
                            f"[BUILD-123v2] Low confidence ({confidence:.1%}) for phase '{phase_id}' - "
                            f"scope may be incomplete. Builder may need to request expansion."
                        )
                else:
                    logger.warning(
                        f"[BUILD-123v2] Manifest generation failed for '{phase_id}': {result.error}"
                    )
                    # Continue with empty scope - Builder will handle
            except Exception as e:
                logger.error(f"[BUILD-123v2] Failed to generate manifest for '{phase_id}': {e}")
                import traceback

                traceback.print_exc()
                # Continue with empty scope

        allowed_scope_paths = self._derive_allowed_paths_from_scope(scope_config)

        # BUILD-115: Database queries disabled - use API phase data with defaults
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

        # Check if already exhausted attempts
        if phase_db.retry_attempt >= MAX_RETRY_ATTEMPTS:
            logger.warning(
                f"[{phase_id}] Phase has already exhausted all attempts "
                f"({phase_db.retry_attempt}/{MAX_RETRY_ATTEMPTS}). Marking as FAILED."
            )
            self._mark_phase_failed_in_db(phase_id, "MAX_ATTEMPTS_EXHAUSTED")
            return False, "FAILED"

        # [Goal Anchoring] Initialize goal anchor for this phase on first execution
        # Per GPT_RESPONSE27: Store original intent before any re-planning occurs
        self._initialize_phase_goal_anchor(phase)

        # Current attempt index from database
        attempt_index = phase_db.retry_attempt
        max_attempts = MAX_RETRY_ATTEMPTS

        # BUILD-129 Phase 3 P10: Apply persisted escalate-once budget on the *next* attempt.
        # We persist P10 decisions into token_budget_escalation_events with attempt_index=1-based attempt that triggered.
        # When retry_attempt increments from 0->1, we should apply the retry budget for that next attempt.
        try:
            from autopack.database import SessionLocal
            from autopack.models import TokenBudgetEscalationEvent

            db = SessionLocal()
            try:
                evt = (
                    db.query(TokenBudgetEscalationEvent)
                    .filter(
                        TokenBudgetEscalationEvent.run_id == self.run_id,
                        TokenBudgetEscalationEvent.phase_id == phase_id,
                    )
                    .order_by(TokenBudgetEscalationEvent.timestamp.desc())
                    .first()
                )
            finally:
                try:
                    db.close()
                except Exception:
                    pass

            if evt and (attempt_index == int(evt.attempt_index or 0)) and evt.retry_max_tokens:
                # Attach a transient override used by execute_builder_phase(max_tokens=...)
                phase["_escalated_tokens"] = int(evt.retry_max_tokens)
        except Exception:
            # Best-effort only; do not block execution if DB telemetry isn't available.
            pass

        # Reload project rules mid-run if rules_updated.json advanced
        self._refresh_project_rules_if_updated()

        # [BUILD-041] Execute single attempt with error recovery
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
                max_retries=1,  # Only 1 retry for transient errors within an attempt
            )

            if success:
                # [BUILD-041] Mark phase COMPLETE in database
                self._mark_phase_complete_in_db(phase_id)

                # Learning Pipeline: Record hint if succeeded after retries
                if attempt_index > 0:
                    self._record_learning_hint(
                        phase=phase,
                        hint_type="success_after_retry",
                        details=f"Succeeded on attempt {attempt_index + 1} after {attempt_index} failed attempts",
                    )

                # BUILD-145 P1.1: Record token efficiency telemetry
                self._record_token_efficiency_telemetry(phase_id, "COMPLETE")

                logger.info(
                    f"[{phase_id}] Phase completed successfully on attempt {attempt_index + 1}"
                )
                return True, "COMPLETE"

            # [BUILD-041] Attempt failed - update database and check if exhausted
            failure_outcome = self._status_to_outcome(status)

            # BUILD-129/P10 convergence: TOKEN_ESCALATION is not a diagnosable "approach flaw".
            # It's an intentional control-flow signal: retry with a larger completion budget.
            # Do NOT run diagnostics/Doctor/replan here; doing so resets state and prevents
            # the stateful retry budget from being applied across drain batches.
            if status == "TOKEN_ESCALATION":
                new_attempts = attempt_index + 1
                self._update_phase_attempts_in_db(
                    phase_id,
                    retry_attempt=new_attempts,
                    last_failure_reason=status,
                )
                logger.info(
                    f"[{phase_id}] TOKEN_ESCALATION recorded; advancing retry_attempt to {new_attempts} "
                    f"and deferring diagnosis so the next attempt can use the escalated max_tokens."
                )
                return False, status

            # Update health budget tracking
            self._run_total_failures += 1
            if status == "PATCH_FAILED":
                self._run_patch_failure_count += 1

            # Learning Pipeline: Record hint about what went wrong
            self._record_learning_hint(
                phase=phase,
                hint_type=failure_outcome,
                details=f"Failed with {status} on attempt {attempt_index + 1}",
            )

            # Mid-Run Re-Planning: Record error for approach flaw detection
            self._record_phase_error(
                phase=phase,
                error_type=failure_outcome,
                error_details=f"Status: {status}",
                attempt_index=attempt_index,
            )

            # [BUILD-146 P6.3] Deterministic Failure Hardening (before expensive diagnostics/Doctor)
            # Try deterministic mitigation FIRST to avoid token costs
            if os.getenv("AUTOPACK_ENABLE_FAILURE_HARDENING", "false").lower() == "true":
                from autopack.failure_hardening import detect_and_mitigate_failure

                error_text = f"Status: {status}, Attempt: {attempt_index + 1}"
                hardening_context = {
                    "workspace": (
                        Path(self.workspace_root) if hasattr(self, "workspace_root") else Path.cwd()
                    ),
                    "phase_id": phase_id,
                    "status": status,
                    "scope_paths": phase.get("scope", {}).get("paths", []),
                }

                mitigation_result = detect_and_mitigate_failure(error_text, hardening_context)

                if mitigation_result:
                    logger.info(
                        f"[{phase_id}] Failure hardening detected pattern: {mitigation_result.pattern_id} "
                        f"(success={mitigation_result.success}, fixed={mitigation_result.fixed})"
                    )
                    logger.info(f"[{phase_id}] Actions taken: {mitigation_result.actions_taken}")
                    logger.info(f"[{phase_id}] Suggestions: {mitigation_result.suggestions}")

                    # Record mitigation in learning hints
                    self._record_learning_hint(
                        phase=phase,
                        hint_type="failure_hardening_applied",
                        details=f"Pattern: {mitigation_result.pattern_id}, Fixed: {mitigation_result.fixed}",
                    )

                    # If mitigation claims it's fixed, skip diagnostics/Doctor and retry immediately
                    if mitigation_result.fixed:
                        logger.info(
                            f"[{phase_id}] Failure hardening claims fix applied, skipping diagnostics/Doctor"
                        )

                        # [BUILD-146 P2] Record Phase 6 telemetry for failure hardening
                        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() == "true":
                            try:
                                from autopack.usage_recorder import (
                                    record_phase6_metrics,
                                    estimate_doctor_tokens_avoided,
                                )
                                from autopack.database import SessionLocal

                                db = SessionLocal()
                                try:
                                    # BUILD-146 P3: Use median-based estimation with coverage tracking
                                    estimate, coverage_n, source = estimate_doctor_tokens_avoided(
                                        db=db,
                                        run_id=self.run_id,
                                        doctor_model=None,  # Could enhance to track expected model
                                    )

                                    record_phase6_metrics(
                                        db=db,
                                        run_id=self.run_id,
                                        phase_id=phase_id,
                                        failure_hardening_triggered=True,
                                        failure_pattern_detected=mitigation_result.pattern_id,
                                        failure_hardening_mitigated=True,
                                        doctor_call_skipped=True,
                                        doctor_tokens_avoided_estimate=estimate,
                                        estimate_coverage_n=coverage_n,
                                        estimate_source=source,
                                    )
                                finally:
                                    db.close()
                            except Exception as e:
                                logger.warning(
                                    f"[{phase_id}] Failed to record Phase 6 telemetry: {e}"
                                )

                        # Increment attempts and return for immediate retry (caller handles retry loop)
                        new_attempts = attempt_index + 1
                        self._update_phase_attempts_in_db(
                            phase_id,
                            retry_attempt=new_attempts,
                            last_failure_reason=f"HARDENING_MITIGATED: {mitigation_result.pattern_id}",
                        )
                        # Return FAILED status so caller can retry immediately with mitigation applied
                        return (False, "FAILED")

            # Run governed diagnostics to gather evidence before mutations
            self._run_diagnostics_for_failure(
                failure_class=failure_outcome,
                phase=phase,
                context={
                    "status": status,
                    "attempt_index": attempt_index,
                    "logs_excerpt": f"Status: {status}, Attempt: {attempt_index + 1}",
                },
            )

            # [Doctor Integration] Invoke Doctor for diagnosis after sufficient failures
            # [Phase C1] Extract patch and error info from last builder result
            last_patch = None
            patch_errors = []
            if self._last_builder_result:
                last_patch = self._last_builder_result.patch_content
                if self._last_builder_result.error:
                    patch_errors = [{"error": self._last_builder_result.error}]
                # Include builder messages as additional error context
                if self._last_builder_result.builder_messages:
                    for msg in self._last_builder_result.builder_messages:
                        if msg and "error" in msg.lower() or "failed" in msg.lower():
                            patch_errors.append({"message": msg})

            doctor_response = self._invoke_doctor(
                phase=phase,
                error_category=failure_outcome,
                builder_attempts=attempt_index + 1,
                last_patch=last_patch,
                patch_errors=patch_errors,
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
                    # [BUILD-041] Doctor recommended skipping - mark phase FAILED
                    self._mark_phase_failed_in_db(phase_id, f"DOCTOR_SKIP: {status}")
                    logger.warning(f"[{phase_id}] Doctor recommended skipping, marking FAILED")
                    return False, status

                if action_taken == "replan":
                    # BUILD-050 Phase 2: Non-destructive replanning - increment epoch, preserve retry progress
                    phase_db = self._get_phase_from_db(phase_id)
                    if phase_db:
                        new_epoch = phase_db.revision_epoch + 1
                        logger.info(
                            f"[{phase_id}] Doctor triggered re-planning (epoch {phase_db.revision_epoch} → {new_epoch}), "
                            f"preserving retry progress (retry_attempt={phase_db.retry_attempt}, escalation={phase_db.escalation_level})"
                        )
                        self._update_phase_attempts_in_db(
                            phase_id, revision_epoch=new_epoch, last_failure_reason="DOCTOR_REPLAN"
                        )
                    return False, "REPLAN_REQUESTED"

            # INSERTION POINT 3: Intention-first stuck handling dispatch (BUILD-161 Phase A)
            if (
                hasattr(self, "_intention_wiring")
                and self._intention_wiring is not None
                and self._intention_anchor is not None
            ):
                from autopack.autonomous.executor_wiring import decide_stuck_action
                from autopack.stuck_handling import StuckReason

                # Map failure status to stuck reason
                stuck_reason = StuckReason.REPEATED_FAILURES  # Default
                if "BUDGET" in status.upper():
                    stuck_reason = StuckReason.BUDGET_EXCEEDED
                elif "TRUNCAT" in status.upper():
                    stuck_reason = StuckReason.OUTPUT_TRUNCATION

                # BUILD-190: Use run-level accumulated token usage for budget decisions
                tokens_used = self._run_tokens_used
                context_chars_used = self._run_context_chars_used
                sot_chars_used = self._run_sot_chars_used

                try:
                    decision, decision_msg = decide_stuck_action(
                        wiring=self._intention_wiring,
                        phase_id=phase_id,
                        phase_spec=phase,
                        anchor=self._intention_anchor,
                        reason=stuck_reason,
                        tokens_used=tokens_used,
                        context_chars_used=context_chars_used,
                        sot_chars_used=sot_chars_used,
                    )
                    logger.info(f"[IntentionFirst] {decision_msg}")

                    # Dispatch based on decision
                    from autopack.stuck_handling import StuckResolutionDecision

                    if decision == StuckResolutionDecision.REPLAN:
                        # Use existing replan logic
                        logger.info(f"[IntentionFirst] Policy decided REPLAN for {phase_id}")
                        # Fall through to existing replan code below
                    elif decision == StuckResolutionDecision.ESCALATE_MODEL:
                        # Apply model escalation via routing snapshot
                        from autopack.autonomous.executor_wiring import apply_model_escalation
                        from autopack.executor.safety_profile import derive_safety_profile

                        current_tier = phase.get(
                            "_current_tier", "haiku"
                        )  # Default to haiku if not set
                        # BUILD-188 P5.5: Derive safety profile from intention anchor (closes TODO)
                        safety_profile = (
                            derive_safety_profile(self._intention_anchor)
                            if self._intention_anchor is not None
                            else "strict"  # Fail-safe default
                        )
                        escalated_entry = apply_model_escalation(
                            wiring=self._intention_wiring,
                            phase_id=phase_id,
                            phase_spec=phase,
                            current_tier=current_tier,
                            safety_profile=safety_profile,
                        )
                        if escalated_entry:
                            logger.info(
                                f"[IntentionFirst] Escalated {phase_id} to tier {escalated_entry.tier} (model: {escalated_entry.model_id})"
                            )
                            phase["_current_tier"] = escalated_entry.tier
                            # The run_context overrides are now set, llm_service will use them
                        else:
                            logger.warning(
                                f"[IntentionFirst] Escalation failed for {phase_id}, falling back to existing logic"
                            )
                        # Don't return - let existing retry logic continue
                    elif decision == StuckResolutionDecision.REDUCE_SCOPE:
                        # BUILD-190: Implement scope reduction with proposal generation
                        from autopack.executor.scope_reduction_flow import (
                            generate_scope_reduction_proposal as gen_scope_proposal,
                            write_scope_reduction_proposal,
                        )
                        from autopack.run_file_layout import RunFileLayout

                        logger.info(f"[IntentionFirst] Policy decided REDUCE_SCOPE for {phase_id}")

                        # Extract current scope from phase
                        current_tasks = phase.get("tasks", [])
                        if not current_tasks:
                            # Fallback: use deliverables as scope proxy
                            current_tasks = phase.get("deliverables", [])

                        if current_tasks:
                            # Compute budget remaining
                            budget_remaining = 1.0 - (tokens_used / max(self.run_budget_tokens, 1))
                            budget_remaining = max(0.0, min(1.0, budget_remaining))

                            # Generate scope reduction proposal
                            proposal = gen_scope_proposal(
                                run_id=self.run_id,
                                phase_id=phase_id,
                                anchor=self._intention_anchor,
                                current_scope=current_tasks,
                                budget_remaining=budget_remaining,
                            )

                            if proposal and proposal.proposed_scope:
                                # Write proposal as artifact
                                try:
                                    layout = RunFileLayout(
                                        self.run_id, project_id=self._get_project_slug()
                                    )
                                    write_scope_reduction_proposal(layout, proposal)
                                except Exception as write_err:
                                    logger.warning(
                                        f"[IntentionFirst] Failed to write scope proposal: {write_err}"
                                    )

                                # Apply reduced scope to phase
                                phase["tasks"] = proposal.proposed_scope
                                phase["_scope_reduced"] = True
                                phase["_dropped_tasks"] = proposal.dropped_items

                                logger.info(
                                    f"[IntentionFirst] Reduced scope from {len(current_tasks)} to "
                                    f"{len(proposal.proposed_scope)} tasks (dropped: {proposal.dropped_items})"
                                )
                            else:
                                logger.warning(
                                    "[IntentionFirst] Scope reduction proposal was empty, falling back"
                                )
                        else:
                            logger.warning(
                                "[IntentionFirst] No tasks to reduce scope from, falling back"
                            )
                    elif decision == StuckResolutionDecision.NEEDS_HUMAN:
                        logger.critical(
                            f"[IntentionFirst] Policy decided NEEDS_HUMAN for {phase_id} - blocking"
                        )
                        return False, "BLOCKED_NEEDS_HUMAN"
                    elif decision == StuckResolutionDecision.STOP:
                        logger.critical(
                            f"[IntentionFirst] Policy decided STOP for {phase_id} - budget exhausted or max retries"
                        )
                        return False, "FAILED"
                except Exception as e:
                    logger.warning(
                        f"[IntentionFirst] Stuck decision failed: {e}, falling back to existing logic"
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
                    # BUILD-050 Phase 2: Non-destructive replanning
                    self._run_replan_count += 1
                    phase_db = self._get_phase_from_db(phase_id)
                    if phase_db:
                        new_epoch = phase_db.revision_epoch + 1
                        logger.info(
                            f"[{phase_id}] Re-planning successful (run total: {self._run_replan_count}/{self.MAX_REPLANS_PER_RUN}, "
                            f"epoch {phase_db.revision_epoch} → {new_epoch}), preserving retry progress"
                        )
                        self._update_phase_attempts_in_db(
                            phase_id, revision_epoch=new_epoch, last_failure_reason="REPLANNED"
                        )
                    return False, "REPLAN_REQUESTED"
                else:
                    logger.warning(
                        f"[{phase_id}] Re-planning failed, continuing with original approach"
                    )

            # [BUILD-041] Increment attempts_used in database
            new_attempts = attempt_index + 1
            self._update_phase_attempts_in_db(
                phase_id, retry_attempt=new_attempts, last_failure_reason=status
            )

            # Token-efficiency guard: CI collection/import errors are deterministic environment/test failures.
            # Retrying (and escalating models / triggering deep retrieval) wastes tokens and can further dirty the workspace.
            status_lower = (status or "").lower()
            if (
                "ci collection/import error" in status_lower
                or "collection errors detected" in status_lower
            ):
                logger.error(
                    f"[{phase_id}] Deterministic CI collection/import failure. "
                    f"Skipping escalation/retry to avoid token waste."
                )
                return False, status

            # Check if attempts exhausted
            if new_attempts >= max_attempts:
                logger.error(
                    f"[{phase_id}] All {max_attempts} attempts exhausted. Marking phase as FAILED."
                )

                # Log to debug journal for persistent tracking
                log_error(
                    error_signature=f"Phase {phase_id} max attempts exhausted",
                    symptom=f"Phase failed after {max_attempts} attempts with model escalation",
                    run_id=self.run_id,
                    phase_id=phase_id,
                    suspected_cause="Task complexity exceeds model capabilities or task is impossible",
                    priority="HIGH",
                )

                self._mark_phase_failed_in_db(phase_id, "MAX_ATTEMPTS_EXHAUSTED")
                return False, "FAILED"

            logger.warning(
                f"[{phase_id}] Attempt {new_attempts}/{max_attempts} failed, will escalate model for next retry"
            )
            return False, status

        except Exception as e:
            # [BUILD-041] Handle exceptions with database state updates
            logger.error(f"[{phase_id}] Attempt {attempt_index + 1} raised exception: {e}")

            # Report detailed error context for debugging
            report_error(
                error=e,
                run_id=self.run_id,
                phase_id=phase_id,
                component="executor",
                operation="execute_phase",
                context_data={
                    "attempt_index": attempt_index,
                    "max_retry_attempts": MAX_RETRY_ATTEMPTS,
                    "phase_description": phase.get("description", "")[:200],
                    "phase_complexity": phase.get("complexity"),
                    "phase_task_category": phase.get("task_category"),
                },
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
                attempt_index=attempt_index,
            )

            # Diagnostics: gather evidence for infra errors before any mutations
            self._run_diagnostics_for_failure(
                failure_class="infra_error",
                phase=phase,
                context={
                    "exception": str(e)[:300],
                    "attempt_index": attempt_index,
                },
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
                    # [BUILD-041] Doctor recommended skipping - mark phase FAILED
                    self._mark_phase_failed_in_db(phase_id, f"DOCTOR_SKIP: {type(e).__name__}")
                    return False, "FAILED"

                if action_taken == "replan":
                    # BUILD-050 Phase 2: Non-destructive replanning after exception
                    phase_db = self._get_phase_from_db(phase_id)
                    if phase_db:
                        new_epoch = phase_db.revision_epoch + 1
                        logger.info(
                            f"[{phase_id}] Doctor triggered re-planning after exception (epoch {phase_db.revision_epoch} → {new_epoch}), "
                            f"preserving retry progress"
                        )
                        self._update_phase_attempts_in_db(
                            phase_id,
                            revision_epoch=new_epoch,
                            last_failure_reason="DOCTOR_REPLAN_AFTER_EXCEPTION",
                        )
                    return False, "REPLAN_REQUESTED"

            # Check if we should trigger re-planning before next retry
            should_replan, flaw_type = self._should_trigger_replan(phase)
            if should_replan:
                logger.info(f"[{phase_id}] Triggering mid-run re-planning due to {flaw_type}")
                error_history = self._phase_error_history.get(phase_id, [])
                revised_phase = self._revise_phase_approach(phase, flaw_type, error_history)
                if revised_phase:
                    # BUILD-050 Phase 2: Non-destructive replanning after exception
                    self._run_replan_count += 1
                    phase_db = self._get_phase_from_db(phase_id)
                    if phase_db:
                        new_epoch = phase_db.revision_epoch + 1
                        logger.info(
                            f"[{phase_id}] Re-planning successful (run total: {self._run_replan_count}/{self.MAX_REPLANS_PER_RUN}, "
                            f"epoch {phase_db.revision_epoch} → {new_epoch}), preserving retry progress"
                        )
                        self._update_phase_attempts_in_db(
                            phase_id,
                            revision_epoch=new_epoch,
                            last_failure_reason="REPLANNED_AFTER_EXCEPTION",
                        )
                    return False, "REPLAN_REQUESTED"

            # [BUILD-041] Increment attempts_used in database after exception
            new_attempts = attempt_index + 1
            self._update_phase_attempts_in_db(
                phase_id,
                retry_attempt=new_attempts,
                last_failure_reason=f"EXCEPTION: {type(e).__name__}",
            )

            # Check if attempts exhausted
            if new_attempts >= max_attempts:
                logger.error(
                    f"[{phase_id}] All {max_attempts} attempts exhausted after exception. Marking phase as FAILED."
                )

                # Log to debug journal for persistent tracking
                log_error(
                    error_signature=f"Phase {phase_id} max attempts exhausted (exception)",
                    symptom=f"Phase failed after {max_attempts} attempts with final exception: {type(e).__name__}",
                    run_id=self.run_id,
                    phase_id=phase_id,
                    suspected_cause=str(e)[:200],
                    priority="HIGH",
                )

                self._mark_phase_failed_in_db(
                    phase_id, f"MAX_ATTEMPTS_EXHAUSTED: {type(e).__name__}"
                )
                return False, "FAILED"

            logger.warning(
                f"[{phase_id}] Attempt {new_attempts}/{max_attempts} raised exception, will retry"
            )
            return False, "EXCEPTION_OCCURRED"

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
            phase.get("task_category", "general")
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

            # Save the hint
            save_run_hint(
                run_id=self.run_id,
                phase=phase,
                hint_text=hint_text,
                source_issue_keys=[f"{hint_type}_{phase_id}"],
            )

            logger.debug(f"[Learning] Recorded hint for {phase_id}: {hint_type}")

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
        normalized = re.sub(r"[/\\][\w\-./\\]+\.(py|js|ts|json|yaml|yml|md)", "[PATH]", normalized)
        normalized = re.sub(r"[a-z]:\\[\w\-\\]+", "[PATH]", normalized, flags=re.IGNORECASE)

        # Strip line numbers (e.g., "line 42", ":42:", "L42")
        normalized = re.sub(r"\bline\s*\d+\b", "line [N]", normalized)
        normalized = re.sub(r":\d+:", ":[N]:", normalized)
        normalized = re.sub(r"\bL\d+\b", "L[N]", normalized)

        # Strip UUIDs
        normalized = re.sub(
            r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", "[UUID]", normalized
        )

        # Strip run IDs (common patterns)
        normalized = re.sub(r"\b[a-z]+-\d{8}(-\d+)?\b", "[RUN_ID]", normalized)

        # Strip timestamps (ISO format and common patterns)
        normalized = re.sub(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}", "[TIMESTAMP]", normalized)
        normalized = re.sub(r"\d{2}:\d{2}:\d{2}", "[TIME]", normalized)

        # Strip stack trace lines
        normalized = re.sub(r'file "[^"]+", line \[n\]', "file [PATH], line [N]", normalized)
        normalized = re.sub(r"traceback \(most recent call last\):", "[TRACEBACK]", normalized)

        # Collapse whitespace
        normalized = re.sub(r"\s+", " ", normalized).strip()

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
        # try:
        #     plan_change = models.PlanChange(
        #         run_id=self.run_id,
        #         phase_id=phase_id,
        #         project_id=project_id,
        #         timestamp=timestamp,
        #         author="autonomous_executor",
        #         summary=summary,
        #         rationale=rationale,
        #         replaces_version=replaces_version,
        #         status="active",
        #         vector_id=vector_id or None,
        #     )
        #     self.db_session.add(plan_change)
        #     self.db_session.commit()
        # except Exception as e:
        #     logger.warning(f"[PlanChange] DB write failed: {e}")
        #     self.db_session.rollback()
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
        # try:
        #     decision = models.DecisionLog(
        #         run_id=self.run_id,
        #         phase_id=phase_id,
        #         project_id=project_id,
        #         timestamp=timestamp,
        #         trigger=trigger,
        #         alternatives=alternatives,
        #         choice=choice,
        #         rationale=rationale,
        #         vector_id=vector_id or None,
        #     )
        #     self.db_session.add(decision)
        #     self.db_session.commit()
        # except Exception as e:
        #     logger.warning(f"[DecisionLog] DB write failed: {e}")
        #     self.db_session.rollback()
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

        logger.info(
            f"[Re-Plan] Revising approach for {phase_id} due to {flaw_type} (attempt {replan_attempt})"
        )
        logger.info(f"[GoalAnchor] Original intent: {original_intent[:100]}...")

        # Build context from error history
        error_summary = "\n".join(
            [
                f"- Attempt {e['attempt'] + 1}: {e['error_type']} - {e['error_details'][:200]}"
                for e in error_history[-5:]  # Last 5 errors
            ]
        )

        # Get any run hints that might help
        learning_context = self._get_learning_context_for_phase(phase) or {}
        hints_summary = "\n".join(
            [f"- {hint}" for hint in learning_context.get("run_hints", [])[:3]]
        )

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

            # NOTE: Re-planning is best-effort. If Anthropic is disabled/unavailable (e.g., credits exhausted),
            # skip replanning rather than spamming repeated 400s.
            try:
                if hasattr(self.llm_service, "model_router") and "anthropic" in getattr(
                    self.llm_service.model_router, "disabled_providers", set()
                ):
                    logger.info(
                        "[Re-Plan] Skipping re-planning because provider 'anthropic' is disabled for this run/process"
                    )
                    return None
            except Exception:
                pass

            # Current implementation uses Anthropic directly for replanning; require key.
            import os

            api_key = os.environ.get("ANTHROPIC_API_KEY")
            if not api_key:
                logger.info("[Re-Plan] Skipping re-planning because ANTHROPIC_API_KEY is not set")
                return None

            # Use Claude for re-planning (strongest model)
            import anthropic

            client = anthropic.Anthropic(api_key=api_key)

            response = client.messages.create(
                model="claude-sonnet-4-20250514",  # Use strong model for re-planning
                max_tokens=2000,
                messages=[{"role": "user", "content": replan_prompt}],
            )

            # Defensive: ensure response has text content
            content_blocks = getattr(response, "content", None) or []
            first_block = content_blocks[0] if content_blocks else None
            revised_description = (getattr(first_block, "text", "") or "").strip()

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
                    success=False,
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
            self._phase_revised_specs[f"_replan_count_{phase_id}"] = (
                self._get_replan_count(phase_id) + 1
            )

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
                success=False,  # Will be updated if phase eventually succeeds
            )

            # Record this re-planning event
            log_build_event(
                event_type="PHASE_REPLANNED",
                description=f"Phase {phase_id} replanned due to {flaw_type}. Alignment: {alignment.get('alignment')}. Original: '{original_description[:50]}...' -> Revised approach applied.",
                deliverables=[
                    f"Run: {self.run_id}",
                    f"Phase: {phase_id}",
                    f"Flaw: {flaw_type}",
                    f"Alignment: {alignment.get('alignment')}",
                ],
                project_slug=self._get_project_slug(),
            )

            # Record plan change + decision log for memory/DB
            try:
                self._record_plan_change_entry(
                    summary=f"{phase_id} replanned (attempt {replan_attempt})",
                    rationale=f"flaw={flaw_type}; alignment={alignment.get('alignment')}",
                    phase_id=phase_id,
                    replaces_version=replan_attempt - 1 if replan_attempt > 1 else None,
                )
                self._record_decision_entry(
                    trigger=f"replan:{flaw_type}",
                    choice="replan",
                    rationale=f"Replanned to address {flaw_type}",
                    phase_id=phase_id,
                    alternatives="retry_with_fix,replan,skip,rollback",
                )
            except Exception as log_exc:
                logger.warning(f"[Re-Plan] Telemetry write failed: {log_exc}")

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
                success=False,
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

    def _validate_fix_commands(self, commands: List[str], fix_type: str) -> Tuple[bool, List[str]]:
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
                shlex.split(cmd)
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
        self, phase: Dict, response: DoctorResponse
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
                "[Doctor] execute_fix requested but disabled. "
                "Enable via models.yaml: doctor.allow_execute_fix_global: true"
            )
            log_error(
                error_signature=f"execute_fix disabled: {phase_id}",
                symptom="execute_fix action requested but feature is disabled",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="User opt-in required via models.yaml",
                priority="HIGH",
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

        # Safety: In project_build runs, do not allow Doctor to execute git-based fixes.
        # The git fix recipes commonly include `git reset --hard` / `git clean -fd` which will:
        # - wipe partially-generated deliverables needed for convergence
        # - create noisy checkpoint commits
        # - potentially discard unrelated local work in the repo
        #
        # For Autopack self-maintenance runs, git execute_fix is acceptable (controlled, intentional).
        if self.run_type == "project_build" and fix_type == "git":
            logger.warning(
                f"[Doctor] Blocking execute_fix of type 'git' for project_build run (phase={phase_id}). "
                f"Falling back to normal retry loop."
            )
            try:
                log_fix(
                    error_signature=f"execute_fix blocked (git) for {phase_id}",
                    fix_description=(
                        "Blocked Doctor execute_fix with fix_type='git' for project_build run to prevent "
                        "destructive repo operations (e.g., git reset --hard / git clean -fd) from wiping "
                        "partially-generated deliverables and obscuring debugging history."
                    ),
                    files_changed=[],
                    run_id=self.run_id,
                    phase_id=phase_id,
                    outcome="BLOCKED_GIT_EXECUTE_FIX",
                )
            except Exception:
                pass
            hint = (
                response.builder_hint
                or "Fix attempt blocked: git execute_fix is disabled for project_build runs"
            )
            self._builder_hint_by_phase[phase_id] = hint
            return "execute_fix_blocked_git_project_build", True

        if not fix_commands:
            logger.warning("[Doctor] execute_fix requested but no fix_commands provided")
            return "execute_fix_no_commands", True

        # Validate commands
        is_valid, validation_errors = self._validate_fix_commands(fix_commands, fix_type)
        if not is_valid:
            logger.error(f"[Doctor] execute_fix command validation failed: {validation_errors}")
            log_error(
                error_signature=f"execute_fix validation failed: {phase_id}",
                symptom=f"Commands failed validation: {validation_errors}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Doctor suggested invalid/unsafe commands",
                priority="HIGH",
            )
            # Fall back to retry_with_fix
            hint = f"execute_fix validation failed: {validation_errors[0]}"
            self._builder_hint_by_phase[phase_id] = hint
            return "execute_fix_invalid", True

        # Create git checkpoint (commit) before executing
        logger.info("[Doctor] Creating git checkpoint before execute_fix...")
        try:
            checkpoint_result = subprocess.run(
                ["git", "add", "-A"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
                timeout=30,
            )
            if checkpoint_result.returncode == 0:
                checkpoint_result = subprocess.run(
                    [
                        "git",
                        "commit",
                        "-m",
                        f"[Autopack] Pre-execute_fix checkpoint for {phase_id}",
                    ],
                    cwd=str(self.workspace),
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                if checkpoint_result.returncode == 0:
                    logger.info("[Doctor] Git checkpoint created successfully")
                else:
                    # No changes to commit - that's OK
                    logger.info("[Doctor] No changes to checkpoint (clean state)")
        except Exception as e:
            logger.warning(f"[Doctor] Failed to create git checkpoint: {e}")

        # Execute fix commands
        logger.info(f"[Doctor] Executing {len(fix_commands)} fix commands (type: {fix_type})...")
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
                    timeout=60,
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
                    timeout=60,
                )
                if verify_result.returncode != 0:
                    logger.warning(f"[Doctor] Verify command failed: {verify_result.stderr}")
                    all_succeeded = False
                else:
                    logger.info("[Doctor] Verify command passed")
            except Exception as e:
                logger.warning(f"[Doctor] Verify command error: {e}")
                all_succeeded = False

        if all_succeeded:
            logger.info("[Doctor] execute_fix succeeded - continuing retry loop")
            log_fix(
                error_signature=f"execute_fix success: {phase_id}",
                fix_description=f"Executed {len(fix_commands)} commands: {fix_commands}",
                run_id=self.run_id,
                phase_id=phase_id,
                outcome="RESOLVED_BY_EXECUTE_FIX",
            )
            return "execute_fix_success", True  # Continue retry loop
        else:
            logger.warning("[Doctor] execute_fix failed - marking phase as failed")
            self._update_phase_status(phase_id, "FAILED")
            return "execute_fix_failed", False

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
        import subprocess

        try:
            # Get current branch name
            branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if branch_result.returncode != 0:
                error_msg = branch_result.stderr.strip()
                logger.warning(f"[RunCheckpoint] Failed to get current branch: {error_msg}")
                return False, f"git_branch_failed: {error_msg}"

            current_branch = branch_result.stdout.strip()

            # Get current commit SHA
            commit_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10,
            )

            if commit_result.returncode != 0:
                error_msg = commit_result.stderr.strip()
                logger.warning(f"[RunCheckpoint] Failed to get current commit: {error_msg}")
                return False, f"git_commit_failed: {error_msg}"

            current_commit = commit_result.stdout.strip()

            # Store checkpoint info
            self._run_checkpoint_branch = current_branch
            self._run_checkpoint_commit = current_commit

            logger.info(
                f"[RunCheckpoint] Created run checkpoint: branch={current_branch}, commit={current_commit[:8]}"
            )
            return True, None

        except subprocess.TimeoutExpired:
            logger.warning("[RunCheckpoint] Timeout creating run checkpoint")
            return False, "git_timeout"
        except Exception as e:
            logger.warning(f"[RunCheckpoint] Exception creating run checkpoint: {e}")
            return False, f"exception: {str(e)}"

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
        import subprocess

        if not self._run_checkpoint_commit:
            logger.error("[RunCheckpoint] No checkpoint commit set - cannot rollback run")
            return False, "no_checkpoint_commit"

        try:
            logger.warning(
                f"[RunCheckpoint] Rolling back entire run to checkpoint: {self._run_checkpoint_commit[:8]}"
            )
            logger.warning(f"[RunCheckpoint] Reason: {reason}")

            # Reset to checkpoint commit (hard reset discards all changes)
            reset_result = subprocess.run(
                ["git", "reset", "--hard", self._run_checkpoint_commit],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if reset_result.returncode != 0:
                error_msg = reset_result.stderr.strip()
                logger.error(f"[RunCheckpoint] Failed to reset to checkpoint: {error_msg}")
                return False, f"git_reset_failed: {error_msg}"

            # Clean untracked files (same as RollbackManager safe clean logic)
            clean_result = subprocess.run(
                ["git", "clean", "-fd"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if clean_result.returncode != 0:
                error_msg = clean_result.stderr.strip()
                logger.warning(f"[RunCheckpoint] Failed to clean untracked files: {error_msg}")
                # Non-fatal - reset succeeded

            # If we were on a named branch, try to return to it
            if self._run_checkpoint_branch and self._run_checkpoint_branch != "HEAD":
                checkout_result = subprocess.run(
                    ["git", "checkout", self._run_checkpoint_branch],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )

                if checkout_result.returncode != 0:
                    logger.warning(
                        f"[RunCheckpoint] Could not return to branch {self._run_checkpoint_branch}"
                    )
                    # Non-fatal - we're at the right commit

            logger.info("[RunCheckpoint] Successfully rolled back run to pre-run state")

            # Log rollback action for audit trail
            self._log_run_rollback_action(reason)

            return True, None

        except subprocess.TimeoutExpired:
            logger.error("[RunCheckpoint] Timeout rolling back to run checkpoint")
            return False, "git_timeout"
        except Exception as e:
            logger.error(f"[RunCheckpoint] Exception during run rollback: {e}")
            return False, f"exception: {str(e)}"

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
        self, phase: Dict, attempt_index: int = 0, allowed_paths: Optional[List[str]] = None
    ) -> Tuple[bool, str]:
        """Inner phase execution with error handling and model escalation support"""
        phase_id = phase.get("phase_id")

        try:
            # Chunk 0 batching (research-tracer-bullet) is handled by a specialized executor path
            # to reduce patch size and avoid incomplete/truncated patches.
            if phase_id == "research-tracer-bullet":
                return self._execute_research_tracer_bullet_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Chunk 2B batching (research-gatherers-web-compilation) is handled by a specialized executor path
            # to reduce patch size and avoid incomplete/truncated patches (common for tests/docs).
            if phase_id == "research-gatherers-web-compilation":
                return self._execute_research_gatherers_web_compilation_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Diagnostics parity followups create multiple files (code + tests + docs) and
            # commonly hit truncation/malformed-diff convergence failures when generated as one patch.
            # Use in-phase batching (like Chunk 0 / Chunk 2B) to reduce patch size and tighten manifest gates.

            # Followup-1: handoff-bundle (4 files: 2 code + 1 test + 1 doc)
            if phase_id == "diagnostics-handoff-bundle":
                return self._execute_diagnostics_handoff_bundle_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Followup-2: cursor-prompt (4 files: 2 code + 1 test + 1 doc)
            if phase_id == "diagnostics-cursor-prompt":
                return self._execute_diagnostics_cursor_prompt_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Followup-3: second-opinion (3 files: 1 code + 1 test + 1 doc)
            if phase_id == "diagnostics-second-opinion-triage":
                return self._execute_diagnostics_second_opinion_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Followup-7: deep-retrieval (5 files: 2 code + 2 tests + 1 doc)
            if phase_id == "diagnostics-deep-retrieval":
                return self._execute_diagnostics_deep_retrieval_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Followup-8: iteration-loop (5 files: 2 code + 2 tests + 1 doc)
            if phase_id == "diagnostics-iteration-loop":
                return self._execute_diagnostics_iteration_loop_batched(
                    phase=phase,
                    attempt_index=attempt_index,
                    allowed_paths=allowed_paths,
                )

            # Step 1: Execute with Builder using LlmService
            logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...")

            # Load repository context for Builder
            try:
                file_context = self._load_repository_context(phase)
                # BUILD-145 P1.1: Store context for telemetry
                self._last_file_context = file_context
                logger.info(
                    f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
                )

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
                    self._last_file_context = file_context
                else:
                    raise

            # ============================================================================
            # NEW: Pre-flight file size validation (per IMPLEMENTATION_PLAN2.md Phase 2.1)
            # This is the PRIMARY fix for the truncation bug - prevents LLM from seeing
            # files >1000 lines in full-file mode
            # ============================================================================
            use_full_file_mode = True  # Default mode
            # Override to structured edits if phase explicitly requests it
            if phase.get("builder_mode") == "structured_edit":
                use_full_file_mode = False

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
                    line_count = content.count("\n") + 1

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
                            bucket="B",  # Now just "too large" bucket
                        )
                    # Don't fail - these files can be read-only context
                    # Parser will enforce that LLM doesn't try to modify them

                # For large scoped contexts, prefer structured edits to avoid truncation
                if len(files) >= 30:
                    use_full_file_mode = False

                # Defensive check: If diff mode is somehow enabled, log loudly
                if config.legacy_diff_fallback_enabled and use_full_file_mode:
                    logger.error(
                        f"[{phase_id}] WARNING: legacy_diff_fallback_enabled is True but should be False! "
                        f"All files ≤{config.max_lines_for_full_file} lines will use full-file mode."
                    )

            # Load learning context (Stage 0A hints + Stage 0B rules)
            learning_context = self._get_learning_context_for_phase(phase)
            project_rules = learning_context.get("project_rules", [])
            run_hints = learning_context.get("run_hints", [])

            if project_rules or run_hints:
                logger.info(
                    f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
                )

            # NEW: Retrieve supplemental context from vector memory (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
            retrieved_context = ""
            if self.memory_service and self.memory_service.enabled:
                try:
                    # Build query from phase description for retrieval
                    phase_description = phase.get("description", "")
                    query = f"{phase_description[:500]}"
                    project_id = self._get_project_slug() or self.run_id

                    # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
                    from autopack.config import settings

                    max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
                    include_sot = self._should_include_sot_retrieval(
                        max_context_chars, phase_id=phase_id
                    )

                    retrieved = self.memory_service.retrieve_context(
                        query=query,
                        project_id=project_id,
                        run_id=self.run_id,
                        include_code=True,
                        include_summaries=True,
                        include_errors=True,
                        include_hints=True,
                        include_planning=True,
                        include_plan_changes=True,
                        include_decisions=True,
                        include_sot=include_sot,
                    )
                    retrieved_context = self.memory_service.format_retrieved_context(
                        retrieved, max_chars=max_context_chars
                    )

                    # BUILD-155: Record SOT retrieval telemetry
                    self._record_sot_retrieval_telemetry(
                        phase_id=phase_id,
                        include_sot=include_sot,
                        max_context_chars=max_context_chars,
                        retrieved_context=retrieved,
                        formatted_context=retrieved_context,
                    )

                    if retrieved_context:
                        logger.info(
                            f"[{phase_id}] Retrieved {len(retrieved_context)} chars of context from memory"
                        )
                except Exception as e:
                    logger.warning(f"[{phase_id}] Memory retrieval failed: {e}")

            # [BUILD-146 P6.2] Intention Context Injection (compact semantic anchor)
            intention_context = ""
            if os.getenv("AUTOPACK_ENABLE_INTENTION_CONTEXT", "false").lower() == "true":
                try:
                    from autopack.intention_wiring import IntentionContextInjector

                    # Create injector (cached on first call per run)
                    if not hasattr(self, "_intention_injector"):
                        project_id = self._get_project_slug() or self.run_id
                        self._intention_injector = IntentionContextInjector(
                            run_id=self.run_id,
                            project_id=project_id,
                            memory_service=(
                                self.memory_service if hasattr(self, "memory_service") else None
                            ),
                        )

                    # Get bounded intention context (≤2KB)
                    intention_context = self._intention_injector.get_intention_context(
                        max_chars=2048
                    )

                    if intention_context:
                        logger.info(
                            f"[{phase_id}] Injected {len(intention_context)} chars of intention context"
                        )
                        # Prepend to retrieved_context so it's visible in Builder prompt
                        if retrieved_context:
                            retrieved_context = f"{intention_context}\n\n{retrieved_context}"
                        else:
                            retrieved_context = intention_context

                        # [BUILD-146 P2] Record Phase 6 telemetry for intention context
                        if os.getenv("TELEMETRY_DB_ENABLED", "false").lower() == "true":
                            try:
                                from autopack.usage_recorder import record_phase6_metrics
                                from autopack.database import SessionLocal

                                db = SessionLocal()
                                try:
                                    # Determine source: memory or fallback
                                    source = (
                                        "memory"
                                        if hasattr(self, "memory_service") and self.memory_service
                                        else "fallback"
                                    )

                                    record_phase6_metrics(
                                        db=db,
                                        run_id=self.run_id,
                                        phase_id=phase_id,
                                        intention_context_injected=True,
                                        intention_context_chars=len(intention_context),
                                        intention_context_source=source,
                                    )
                                finally:
                                    db.close()
                            except Exception as e:
                                logger.warning(
                                    f"[{phase_id}] Failed to record Phase 6 telemetry: {e}"
                                )

                except Exception as e:
                    logger.warning(f"[{phase_id}] Intention context injection failed: {e}")

            # BUILD-050 Phase 1: Add deliverables contract as hard constraint
            # This ensures Builder creates files at correct paths from the start
            deliverables_contract = self._build_deliverables_contract(phase, phase_id)

            # BUILD-044: Add protected paths to phase spec for LLM guidance
            # This prevents protected path violations by informing the LLM upfront
            # Protected paths: should block system/infra artifacts but NOT block normal code creation.
            # NOTE: Research phases legitimately create files under src/autopack/ (e.g., src/autopack/research/*).
            protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]
            phase_with_constraints = {
                **phase,
                "protected_paths": protected_paths,
                "deliverables_contract": deliverables_contract,  # BUILD-050: Hard constraint
            }

            # BUILD-065: Deliverables manifest gate (two-step)
            # Step 1: Ask LLM for an explicit manifest of file paths it will create (JSON array).
            # Step 2: Only if the manifest matches deliverables exactly do we run the normal Builder.
            try:
                from .deliverables_validator import extract_deliverables_from_scope

                scope_cfg = phase.get("scope") or {}
                expected_paths = extract_deliverables_from_scope(scope_cfg)
                if expected_paths and self.llm_service and deliverables_contract:
                    # Derive allowed roots (tight allowlist) but ensure ALL expected paths are covered.
                    expected_set = {p for p in expected_paths if isinstance(p, str)}
                    # Don't allow broad bucket prefixes (docs/tests/code/polish) to dilute the manifest.
                    # These "root bucket" deliverables are useful as prefixes for validation, but if they
                    # enter deliverables_manifest they allow wrong-root drift (e.g. docs/* instead of docs/research/*).
                    bucket_roots = {"docs", "tests", "code", "polish"}
                    expected_set = {
                        p
                        for p in expected_set
                        if p.rstrip("/").replace("\\", "/") not in bucket_roots
                    }
                    expected_list = sorted(expected_set)
                    allowed_roots: List[str] = []
                    preferred_roots = (
                        "src/autopack/research/",
                        "src/autopack/cli/",
                        "tests/research/",
                        "docs/research/",
                        "examples/",
                    )
                    for r in preferred_roots:
                        if any(p.startswith(r) for p in expected_list):
                            allowed_roots.append(r)

                    def _covered(path: str) -> bool:
                        return any(path.startswith(r) for r in allowed_roots)

                    if not allowed_roots or not all(_covered(p) for p in expected_list):
                        expanded: List[str] = []
                        for p in expected_list:
                            # Normalize trailing-slash directory prefixes like "docs/" so we don't
                            # accidentally generate roots like "docs//".
                            p_norm = p.rstrip("/")
                            parts = p_norm.split("/") if p_norm else []
                            # For root-level files (no "/"), include the file itself
                            if len(parts) == 1:
                                root = p
                            # If second segment contains '.', it's likely a filename, use first dir
                            elif len(parts) >= 2 and "." in parts[1]:
                                root = parts[0] + "/"
                            else:
                                root = "/".join(parts[:2]) + "/"
                            if root not in expanded:
                                expanded.append(root)
                        allowed_roots = expanded

                    ok_manifest, manifest_paths, manifest_error, _raw = (
                        self.llm_service.generate_deliverables_manifest(
                            expected_paths=list(expected_set),
                            allowed_roots=allowed_roots,
                            run_id=self.run_id,
                            phase_id=phase_id,
                            attempt_index=attempt_index,
                        )
                    )
                    if not ok_manifest:
                        err_details = manifest_error or "deliverables manifest gate failed"
                        logger.error(
                            f"[{phase_id}] Deliverables manifest gate FAILED: {err_details}"
                        )
                        self._record_phase_error(
                            phase, "deliverables_manifest_failed", err_details, attempt_index
                        )
                        self._record_learning_hint(
                            phase, "deliverables_manifest_failed", err_details
                        )
                        return False, "DELIVERABLES_VALIDATION_FAILED"
                    else:
                        logger.info(
                            f"[{phase_id}] Deliverables manifest gate PASSED ({len(manifest_paths or [])} paths)"
                        )
                        # Attach manifest to phase spec so Builder prompt can be constrained.
                        phase_with_constraints["deliverables_manifest"] = manifest_paths or []
            except Exception as e:
                # Manifest gate should not crash the executor; fall back to normal builder
                logger.warning(
                    f"[{phase_id}] Deliverables manifest gate error (skipping gate): {e}"
                )

            # Use LlmService for complexity-based model selection with escalation
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase_with_constraints,
                file_context=file_context,
                # If a prior attempt truncated, _escalated_tokens will be set and we must actually
                # pass it through so the retry uses a larger completion budget.
                max_tokens=phase.get("_escalated_tokens"),
                project_rules=project_rules,  # Stage 0B: Persistent project rules
                run_hints=run_hints,  # Stage 0A: Within-run hints from earlier phases
                run_id=self.run_id,
                phase_id=phase_id,
                run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
                attempt_index=attempt_index,  # Pass attempt for model escalation
                use_full_file_mode=use_full_file_mode,  # NEW: Pass mode from pre-flight check
                config=self.builder_output_config,  # NEW: Pass config for consistency
                retrieved_context=retrieved_context,  # NEW: Vector memory context
            )

            # [Phase C1] Store builder result for Doctor diagnostics
            self._last_builder_result = builder_result

            # BUILD-190: Accumulate token usage for run-level budget tracking
            self._run_tokens_used += getattr(builder_result, "tokens_used", 0) or 0

            # [Phase C2] Extract and store patch statistics for quality gate
            from autopack.governed_apply import GovernedApplyPath

            is_maintenance_run = self.run_type in [
                "autopack_maintenance",
                "autopack_upgrade",
                "self_repair",
            ]
            governed_apply = GovernedApplyPath(
                workspace=Path(self.workspace),
                run_type=self.run_type,
                autopack_internal_mode=is_maintenance_run,
            )
            self._last_files_changed, self._last_lines_added, self._last_lines_removed = (
                governed_apply.parse_patch_stats(builder_result.patch_content or "")
            )

            # BUILD-129 Phase 3 P10: Sync metadata from phase_spec back to phase
            # The builder call modifies phase_spec (via phase_with_constraints), setting actual_max_tokens
            # We need to sync this back to the phase dict so P10 can read it for escalation
            if "metadata" in phase_with_constraints:
                phase.setdefault("metadata", {}).update(phase_with_constraints["metadata"])

            # Auto-fallback: if full-file output failed due to truncation/parse, retry with structured edits
            # Also fallback when Builder returns wrong format (JSON when expecting git diff, or vice versa)
            retry_parse_markers = [
                "full_file_parse_failed",
                "expected json with 'files' array",
                "full-file json parse failed",
                "output was truncated",
                "stop_reason=max_tokens",
                "no git diff markers found",  # Builder returned JSON when git diff expected
                "output must start with 'diff --git'",  # Same issue, different phrasing
            ]
            error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
            # Remove use_full_file_mode requirement - format mismatches can happen with any mode
            should_retry_structured = not builder_result.success and any(
                m in error_text_lower for m in retry_parse_markers
            )
            if should_retry_structured:
                logger.warning(
                    f"[{phase_id}] Falling back to structured_edit after full-file parse/truncation failure"
                )
                phase_structured = {
                    **phase,
                    "builder_mode": "structured_edit",
                    "protected_paths": protected_paths,
                    "deliverables_contract": deliverables_contract,  # BUILD-050: Keep contract on retry
                }
                builder_result = self.llm_service.execute_builder_phase(
                    phase_spec=phase_structured,
                    file_context=file_context,
                    # Preserve any escalated budget across format fallback retries too.
                    max_tokens=phase.get("_escalated_tokens"),
                    project_rules=project_rules,
                    run_hints=run_hints,
                    run_id=self.run_id,
                    phase_id=phase_id,
                    run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
                    attempt_index=attempt_index,
                    use_full_file_mode=False,
                    config=self.builder_output_config,
                    retrieved_context=retrieved_context,  # NEW: Vector memory context
                )

                # [Phase C1] Store fallback builder result for Doctor diagnostics
                self._last_builder_result = builder_result

                # BUILD-190: Accumulate token usage for run-level budget tracking (fallback path)
                self._run_tokens_used += getattr(builder_result, "tokens_used", 0) or 0

                # [Phase C2] Extract and store patch statistics for quality gate (fallback path)
                from autopack.governed_apply import GovernedApplyPath

                is_maintenance_run = self.run_type in [
                    "autopack_maintenance",
                    "autopack_upgrade",
                    "self_repair",
                ]
                governed_apply = GovernedApplyPath(
                    workspace=Path(self.workspace),
                    run_type=self.run_type,
                    autopack_internal_mode=is_maintenance_run,
                )
                self._last_files_changed, self._last_lines_added, self._last_lines_removed = (
                    governed_apply.parse_patch_stats(builder_result.patch_content or "")
                )

                # BUILD-129 Phase 3 P10: Sync metadata from phase_structured back to phase
                if "metadata" in phase_structured:
                    phase.setdefault("metadata", {}).update(phase_structured["metadata"])

            # Output contract: reject empty/blank patch content before posting/applying.
            # Allow explicit structured-edit no-op (builder already warned) to pass through.
            # BUILD-141 Part 8: Allow explicit full-file no-op (idempotent phase) to pass through.
            # Allow edit_plan as valid alternative to patch_content (structured edits).
            has_patch = builder_result.patch_content and builder_result.patch_content.strip()
            has_edit_plan = (
                hasattr(builder_result, "edit_plan") and builder_result.edit_plan is not None
            )
            if builder_result.success and not has_patch and not has_edit_plan:
                messages = builder_result.builder_messages or []
                no_op_structured = any(
                    "Structured edit produced no operations" in m for m in messages
                )
                no_op_fullfile = any("Full-file produced no diffs" in m for m in messages)
                if not no_op_structured and not no_op_fullfile:
                    builder_result = BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=["empty_patch: builder produced no changes"],
                        tokens_used=builder_result.tokens_used,
                        model_used=getattr(builder_result, "model_used", None),
                        error="empty_patch: builder produced no changes",
                    )

            # BUILD-141 Telemetry Unblock: Targeted retry for "empty files array" errors
            # This error occurs when Builder returns files: [] despite having deliverables
            # Likely caused by prompt ambiguity (directory prefixes, deliverables contract)
            # T1 fixes the prompt, but this retry provides a safety net for edge cases
            empty_files_markers = ["empty files array", "llm returned empty files array"]
            error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
            is_empty_files_error = any(m in error_text_lower for m in empty_files_markers)

            if not builder_result.success and is_empty_files_error:
                # Check if we've already retried for empty files array (limit to 1 retry)
                empty_files_retry_count = phase.get("_empty_files_retry_count", 0)
                max_builder_attempts = phase.get("max_builder_attempts") or 5

                if empty_files_retry_count == 0 and attempt_index < (max_builder_attempts - 1):
                    logger.warning(
                        f"[{phase_id}] Empty files array detected - retrying ONCE with stronger deliverables emphasis "
                        f"(attempt {attempt_index+1}/{max_builder_attempts})"
                    )
                    phase["_empty_files_retry_count"] = 1

                    # The prompt fix (T1) should already handle this, so just retry with same config
                    # If it fails again, the error is deterministic and we should fail fast
                    return False, "EMPTY_FILES_RETRY"
                else:
                    logger.error(
                        f"[{phase_id}] Empty files array persists after targeted retry - failing fast to avoid token waste"
                    )
                    # Don't retry again - this is likely a deterministic error
                    # Fall through to normal error handling

            # Retryable infra errors: backoff and retry without burning through non-infra budgets
            infra_markers = [
                "connection error",
                "timeout",
                "timed out",
                "api failure",
                "server error",
                "http 500",
            ]
            error_text_lower = (builder_result.error or "").lower() if builder_result.error else ""
            is_infra_error = any(m in error_text_lower for m in infra_markers)

            if not builder_result.success and is_infra_error:
                backoff = min(5 * (attempt_index + 1), 20)
                logger.warning(
                    f"[{phase_id}] Infra error detected (retryable): {builder_result.error}. Backing off {backoff}s before retry."
                )

                # Provider health gating: disable provider after repeated infra errors
                model_used = getattr(builder_result, "model_used", "") or ""
                provider = self._model_to_provider(model_used)
                if provider:
                    self._provider_infra_errors[provider] = (
                        self._provider_infra_errors.get(provider, 0) + 1
                    )
                    if self._provider_infra_errors[provider] >= 2:
                        try:
                            self.llm_service.model_router.disable_provider(
                                provider, reason="infra_error"
                            )
                            logger.warning(
                                f"[{phase_id}] Disabled provider {provider} for this run after repeated infra errors."
                            )
                        except Exception as e:
                            logger.warning(
                                f"[{phase_id}] Failed to disable provider {provider}: {e}"
                            )

                time.sleep(backoff)
                return False, "INFRA_RETRY"

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")

                # BUILD-129 Phase 3 P10: Escalate-once for high utilization or truncation
                # If output was truncated OR high utilization (≥95%), increase token budget for retry
                # Limit to ONE escalation per phase to prevent runaway token spend
                max_builder_attempts = phase.get("max_builder_attempts") or 5
                metadata = phase.get("metadata", {})
                token_budget = metadata.get("token_budget", {})
                token_prediction = metadata.get("token_prediction", {})

                # Check if we should escalate
                was_truncated = getattr(builder_result, "was_truncated", False)
                output_utilization = token_budget.get("output_utilization", 0)
                should_escalate = was_truncated or output_utilization >= 95.0

                # Check if we've already escalated once
                already_escalated = phase.get("_escalated_once", False)

                if (
                    should_escalate
                    and not already_escalated
                    and attempt_index < (max_builder_attempts - 1)
                ):
                    # BUILD-129 Phase 3 P10: Escalate from highest evidence-based bound
                    # If truncation happened at ceiling, base must be at least the ceiling
                    # If high utilization, actual tokens used is the best signal
                    # Take max of: selected_budget (P7 intent), actual_max_tokens (P4 ceiling), tokens_used (actual)

                    selected_budget = token_prediction.get("selected_budget", 0)
                    actual_max_tokens = token_prediction.get("actual_max_tokens", 0)
                    tokens_used = token_budget.get("actual_output_tokens", 0)  # From API response

                    # Determine the highest evidence-based bound
                    base_candidates = {
                        "selected_budget": selected_budget,
                        "actual_max_tokens": actual_max_tokens,
                        "tokens_used": tokens_used,
                    }

                    # Find the max and track which source it came from
                    current_max_tokens = max(base_candidates.values())
                    base_source = max(base_candidates, key=base_candidates.get)

                    if current_max_tokens == 0:
                        # Fallback to complexity-based defaults (BUILD-042)
                        complexity = phase.get("complexity", "medium")
                        if complexity == "low":
                            current_max_tokens = 8192
                        elif complexity == "medium":
                            current_max_tokens = 12288
                        elif complexity == "high":
                            current_max_tokens = 16384
                        else:
                            current_max_tokens = 8192
                        base_source = "complexity_default"

                    # Escalate by 25% (conservative to save tokens)
                    escalation_factor = 1.25
                    escalated_tokens = min(int(current_max_tokens * escalation_factor), 64000)
                    phase["_escalated_tokens"] = escalated_tokens
                    phase["_escalated_once"] = True  # Prevent multiple escalations

                    # Record P10 escalation details in metadata for telemetry and dashboard
                    p10_metadata = {
                        "retry_budget_escalation_factor": escalation_factor,
                        "p10_base_value": current_max_tokens,
                        "p10_base_source": base_source,
                        "p10_retry_max_tokens": escalated_tokens,
                        "p10_selected_budget": selected_budget,
                        "p10_actual_max_tokens": actual_max_tokens,
                        "p10_tokens_used": tokens_used,
                    }
                    phase.setdefault("metadata", {}).setdefault("token_budget", {}).update(
                        p10_metadata
                    )

                    reason = (
                        "truncation" if was_truncated else f"{output_utilization:.1f}% utilization"
                    )
                    logger.info(
                        f"[BUILD-129:P10] ESCALATE-ONCE: phase={phase_id} attempt={attempt_index+1} "
                        f"base={current_max_tokens} (from {base_source}) → retry={escalated_tokens} (1.25x, {reason})"
                    )

                    # BUILD-129 Phase 3: Persist P10 decision to DB (deterministic validation).
                    # This avoids relying on reproducing truncation events or scraping logs.
                    try:
                        if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() in [
                            "1",
                            "true",
                            "yes",
                        ]:
                            from autopack.database import SessionLocal
                            from autopack.models import TokenBudgetEscalationEvent

                            session = SessionLocal()
                            try:
                                evt = TokenBudgetEscalationEvent(
                                    run_id=self.run_id,
                                    phase_id=phase_id,
                                    attempt_index=attempt_index + 1,
                                    reason="truncation" if was_truncated else "utilization",
                                    was_truncated=bool(was_truncated),
                                    output_utilization=(
                                        float(output_utilization)
                                        if output_utilization is not None
                                        else None
                                    ),
                                    escalation_factor=float(escalation_factor),
                                    base_value=int(current_max_tokens),
                                    base_source=str(base_source),
                                    retry_max_tokens=int(escalated_tokens),
                                    selected_budget=(
                                        int(selected_budget) if selected_budget else None
                                    ),
                                    actual_max_tokens=(
                                        int(actual_max_tokens) if actual_max_tokens else None
                                    ),
                                    tokens_used=int(tokens_used) if tokens_used else None,
                                )
                                session.add(evt)
                                session.commit()
                            finally:
                                try:
                                    session.close()
                                except Exception:
                                    pass
                    except Exception as e:
                        logger.warning(
                            f"[BUILD-129:P10] Failed to write DB escalation telemetry: {e}"
                        )

                    # Skip Doctor invocation for truncation/high-util - just retry with more tokens
                    # Return False to trigger retry in the calling loop
                    return False, "TOKEN_ESCALATION"

                # Record guardrail-type failures explicitly for learning / Doctor
                error_text = (builder_result.error or "").lower()
                if "churn_limit_exceeded" in error_text:
                    error_category = "builder_churn_limit_exceeded"
                elif any(
                    g in error_text
                    for g in [
                        "suspicious_growth",
                        "suspicious_shrinkage",
                        "truncation",
                        "pack_fullfile",
                    ]
                ):
                    error_category = "builder_guardrail"
                else:
                    error_category = "auditor_reject"

                # Learning + replan telemetry for early builder failures
                self._record_learning_hint(
                    phase=phase,
                    hint_type=error_category,
                    details=builder_result.error or "Builder failed without error message",
                )
                self._record_phase_error(
                    phase=phase,
                    error_type=error_category,
                    error_details=builder_result.error or "Builder failed without error message",
                    attempt_index=attempt_index,
                )

                # Optionally invoke Doctor for diagnosable builder failures
                doctor_response = self._invoke_doctor(
                    phase=phase,
                    error_category=error_category,
                    builder_attempts=attempt_index + 1,
                    last_patch=None,
                    patch_errors=[],
                    logs_excerpt=builder_result.error or "",
                )
                if doctor_response:
                    action_taken, should_continue = self._handle_doctor_action(
                        phase=phase,
                        response=doctor_response,
                        attempt_index=attempt_index,
                    )
                    if not should_continue:
                        self._post_builder_result(phase_id, builder_result, allowed_paths)
                        self._update_phase_status(phase_id, "FAILED")
                        return False, "FAILED"

                # Record a structured issue for builder guardrail failures so they appear under issues/
                try:
                    from autopack.issue_tracker import IssueTracker

                    tracker = IssueTracker(run_id=self.run_id)
                    tier_id = phase.get("tier_id", "unknown")
                    if error_category == "builder_churn_limit_exceeded":
                        issue_key = "builder_churn_limit_exceeded"
                        category = "builder_guardrail"
                    elif error_category == "builder_guardrail":
                        issue_key = "builder_guardrail_failure"
                        category = "builder_guardrail"
                    else:
                        issue_key = "builder_failure"
                        category = "builder_failure"

                    tracker.record_issue(
                        phase_index=phase.get("phase_index", 0),
                        phase_id=phase_id,
                        tier_id=tier_id,
                        issue_key=issue_key,
                        severity="major",
                        source="builder",
                        category=category,
                        task_category=phase.get("task_category"),
                        complexity=phase.get("complexity"),
                        evidence_refs=[builder_result.error] if builder_result.error else None,
                    )
                except Exception as e:
                    logger.warning(f"[IssueTracker] Failed to record builder guardrail issue: {e}")

                # Post failure to API and mark phase as failed
                self._post_builder_result(phase_id, builder_result, allowed_paths)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # DELIVERABLES VALIDATION: Check if patch creates required files
            # This prevents Builder from creating files in wrong locations
            scope_config = phase.get("scope", {})
            # If we computed a manifest for this attempt, pass it into deliverables validation so we can enforce consistency.
            if isinstance(
                phase_with_constraints.get("deliverables_manifest"), list
            ) and phase_with_constraints.get("deliverables_manifest"):
                try:
                    scope_config = {
                        **(scope_config or {}),
                        "deliverables_manifest": phase_with_constraints["deliverables_manifest"],
                    }
                except Exception:
                    pass

            # Structured-edit deliverables: when the Builder returns an EditPlan (patch_content == ""),
            # deliverables validation must still see which files would be touched. Otherwise we can
            # incorrectly fail with "Found in patch: 0 files" even though operations exist.
            touched_paths = None
            try:
                plan = getattr(builder_result, "edit_plan", None)
                ops = getattr(plan, "operations", None) if plan is not None else None
                if ops:
                    extracted = []
                    for op in ops:
                        p = getattr(op, "file_path", None)
                        if isinstance(p, str) and p.strip():
                            extracted.append(p.strip())
                    if extracted:
                        touched_paths = extracted
            except Exception:
                touched_paths = None

            is_valid, validation_errors, validation_details = validate_deliverables(
                patch_content=builder_result.patch_content or "",
                phase_scope=scope_config,
                phase_id=phase_id,
                workspace=Path(self.workspace),
                touched_paths=touched_paths,
            )

            if not is_valid:
                # Generate detailed feedback for Builder to self-correct
                feedback = format_validation_feedback_for_builder(
                    errors=validation_errors,
                    details=validation_details,
                    phase_description=phase.get("description", ""),
                )

                logger.error(f"[{phase_id}] Deliverables validation failed")
                logger.error(f"[{phase_id}] {feedback}")

                # BUILD-129 Phase 3 P10 (expanded): If the builder output was truncated / near-ceiling,
                # deliverables validation failures are often just "incomplete output". In that case,
                # skip feedback and escalate-once immediately.
                try:
                    max_builder_attempts = phase.get("max_builder_attempts") or 5
                    metadata = phase.get("metadata", {})
                    token_budget = metadata.get("token_budget", {})
                    token_prediction = metadata.get("token_prediction", {})

                    was_truncated = getattr(builder_result, "was_truncated", False)
                    output_utilization = token_budget.get("output_utilization", 0) or 0
                    should_escalate = was_truncated or output_utilization >= 95.0
                    already_escalated = phase.get("_escalated_once", False)

                    if (
                        should_escalate
                        and not already_escalated
                        and attempt_index < (max_builder_attempts - 1)
                    ):
                        selected_budget = token_prediction.get("selected_budget", 0)
                        actual_max_tokens = token_prediction.get("actual_max_tokens", 0)
                        tokens_used = token_budget.get("actual_output_tokens", 0)

                        base_candidates = {
                            "selected_budget": selected_budget,
                            "actual_max_tokens": actual_max_tokens,
                            "tokens_used": tokens_used,
                        }

                        current_max_tokens = max(base_candidates.values())
                        base_source = max(base_candidates, key=base_candidates.get)

                        if current_max_tokens == 0:
                            complexity = phase.get("complexity", "medium")
                            if complexity == "low":
                                current_max_tokens = 8192
                            elif complexity == "medium":
                                current_max_tokens = 12288
                            elif complexity == "high":
                                current_max_tokens = 16384
                            else:
                                current_max_tokens = 8192
                            base_source = "complexity_default"

                        escalation_factor = 1.25
                        escalated_tokens = min(int(current_max_tokens * escalation_factor), 64000)
                        phase["_escalated_tokens"] = escalated_tokens
                        phase["_escalated_once"] = True

                        p10_metadata = {
                            "retry_budget_escalation_factor": escalation_factor,
                            "p10_base_value": current_max_tokens,
                            "p10_base_source": base_source,
                            "p10_retry_max_tokens": escalated_tokens,
                            "p10_selected_budget": selected_budget,
                            "p10_actual_max_tokens": actual_max_tokens,
                            "p10_tokens_used": tokens_used,
                        }
                        phase.setdefault("metadata", {}).setdefault("token_budget", {}).update(
                            p10_metadata
                        )

                        reason = (
                            "truncation"
                            if was_truncated
                            else f"{output_utilization:.1f}% utilization"
                        )
                        logger.info(
                            f"[BUILD-129:P10] ESCALATE-ONCE: phase={phase_id} attempt={attempt_index+1} "
                            f"base={current_max_tokens} (from {base_source}) → retry={escalated_tokens} (1.25x, {reason})"
                        )

                        # Persist P10 decision to DB (deterministic validation).
                        try:
                            if os.environ.get("TELEMETRY_DB_ENABLED", "").lower() in [
                                "1",
                                "true",
                                "yes",
                            ]:
                                from autopack.database import SessionLocal
                                from autopack.models import TokenBudgetEscalationEvent

                                session = SessionLocal()
                                try:
                                    evt = TokenBudgetEscalationEvent(
                                        run_id=self.run_id,
                                        phase_id=phase_id,
                                        attempt_index=attempt_index + 1,
                                        reason="truncation" if was_truncated else "utilization",
                                        was_truncated=bool(was_truncated),
                                        output_utilization=(
                                            float(output_utilization)
                                            if output_utilization is not None
                                            else None
                                        ),
                                        escalation_factor=float(escalation_factor),
                                        base_value=int(current_max_tokens),
                                        base_source=str(base_source),
                                        retry_max_tokens=int(escalated_tokens),
                                        selected_budget=(
                                            int(selected_budget) if selected_budget else None
                                        ),
                                        actual_max_tokens=(
                                            int(actual_max_tokens) if actual_max_tokens else None
                                        ),
                                        tokens_used=int(tokens_used) if tokens_used else None,
                                    )
                                    session.add(evt)
                                    session.commit()
                                finally:
                                    try:
                                        session.close()
                                    except Exception:
                                        pass
                        except Exception as e:
                            logger.warning(
                                f"[BUILD-129:P10] Failed to write DB escalation telemetry: {e}"
                            )

                        return False, "TOKEN_ESCALATION"
                except Exception as e:
                    logger.warning(
                        f"[BUILD-129:P10] Deliverables-failure escalation check failed: {e}"
                    )

                # Create a Builder result with validation error for retry
                builder_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=[
                        "DELIVERABLES_VALIDATION_FAILED",
                        feedback,
                        f"Expected files: {', '.join(validation_details.get('expected_paths', [])[:5])}",
                        f"Your patch created: {', '.join(validation_details.get('actual_paths', [])[:5])}",
                    ],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error=f"Deliverables validation failed: {len(validation_details.get('missing_paths', []))} required files missing",
                )

                # Post failure to API and return for retry
                self._post_builder_result(phase_id, builder_result, allowed_paths)

                # Record as learning hint for future phases
                # Generate a hint that emphasizes the path structure pattern
                missing_paths = validation_details.get("missing_paths", [])
                misplaced = validation_details.get("misplaced_paths", {})

                hint_details = []

                # If there are misplaced files, emphasize the path correction
                if misplaced:
                    # Find common prefix in expected paths to show the pattern
                    expected_paths = validation_details.get("expected_paths", [])
                    if expected_paths:
                        # Get common directory prefix
                        from os.path import commonpath

                        try:
                            common_prefix = commonpath(expected_paths)
                            hint_details.append(f"All files must be under: {common_prefix}/")
                        except (ValueError, TypeError):
                            pass

                    # Show examples of wrong → correct
                    for expected, actual in list(misplaced.items())[:2]:
                        hint_details.append(f"Wrong: {actual} → Correct: {expected}")

                # Strong heuristic: if builder keeps creating a top-level tracer_bullet/ package,
                # explicitly forbid it and restate the required base directories.
                actual_paths = validation_details.get("actual_paths", []) or []
                if any(p.startswith("tracer_bullet/") for p in actual_paths):
                    hint_details.insert(
                        0,
                        "DO NOT create a top-level 'tracer_bullet/' package. "
                        "All tracer bullet code MUST live under 'src/autopack/research/tracer_bullet/'. "
                        "Tests MUST live under 'tests/research/tracer_bullet/'. "
                        "Docs MUST live under 'docs/research/'.",
                    )

                # If still space, add first few missing files
                if len(hint_details) < 3 and missing_paths:
                    hint_details.append(
                        f"Missing {len(missing_paths)} files including: {', '.join(missing_paths[:3])}"
                    )

                hint_text = (
                    "; ".join(hint_details)
                    if hint_details
                    else f"Missing: {', '.join(missing_paths[:3])}"
                )

                self._record_learning_hint(
                    phase=phase, hint_type="deliverables_validation_failed", details=hint_text
                )

                # Return False to trigger retry with validation feedback
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # BUILD-070: Pre-apply validation for new JSON deliverables (avoid burning attempts on apply corruption)
            try:
                from .deliverables_validator import (
                    extract_deliverables_from_scope,
                    validate_new_json_deliverables_in_patch,
                )

                expected_paths = extract_deliverables_from_scope(scope_config or {})
                ok_json, json_errors, json_details = validate_new_json_deliverables_in_patch(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                )
                if not ok_json:
                    # BUILD-075: Auto-repair empty/invalid required JSON deliverables (gold_set.json) to minimal valid JSON.
                    try:
                        from .deliverables_validator import (
                            repair_empty_required_json_deliverables_in_patch,
                        )

                        repaired, repaired_patch, repairs = (
                            repair_empty_required_json_deliverables_in_patch(
                                patch_content=builder_result.patch_content or "",
                                expected_paths=expected_paths,
                                workspace=Path(self.workspace),
                                minimal_json="[]\n",
                            )
                        )
                        if repaired:
                            logger.warning(
                                f"[{phase_id}] Auto-repaired {len(repairs)} required JSON deliverable(s) to minimal valid JSON"
                            )
                            for r in repairs[:5]:
                                logger.warning(
                                    f"[{phase_id}]    repaired {r.get('path')}: {r.get('reason')} -> {r.get('applied')}"
                                )

                            builder_result.patch_content = repaired_patch

                            ok_json2, json_errors2, json_details2 = (
                                validate_new_json_deliverables_in_patch(
                                    patch_content=builder_result.patch_content or "",
                                    expected_paths=expected_paths,
                                    workspace=Path(self.workspace),
                                )
                            )
                            if ok_json2:
                                self._record_learning_hint(
                                    phase=phase,
                                    hint_type="success_after_retry",
                                    details="Auto-repaired required JSON deliverable to minimal valid JSON placeholder ([]).",
                                )
                                ok_json = True
                                json_errors = []
                                json_details = json_details2
                            else:
                                json_errors = json_errors2
                                json_details = json_details2
                    except Exception as e:
                        logger.warning(
                            f"[{phase_id}] Auto-repair for JSON deliverables skipped due to error: {e}"
                        )

                if not ok_json:
                    logger.error(f"[{phase_id}] Pre-apply JSON deliverables validation failed")
                    for e in json_errors[:5]:
                        logger.error(f"[{phase_id}]    {e}")

                    feedback_lines = [
                        "❌ DELIVERABLES VALIDATION FAILED (JSON CONTENT)",
                        "",
                        "One or more required JSON deliverables are empty or invalid JSON.",
                        "Fix the JSON file content (must be non-empty valid JSON) and regenerate the patch.",
                        "Minimal acceptable placeholder is `[]`.",
                        "",
                    ]
                    for item in (json_details.get("invalid_json_files", []) or [])[:10]:
                        p = item.get("path")
                        r = item.get("reason")
                        feedback_lines.append(f"- {p}: {r}")

                    builder_result = BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[
                            "DELIVERABLES_VALIDATION_FAILED",
                            "\n".join(feedback_lines),
                        ],
                        tokens_used=builder_result.tokens_used,
                        model_used=getattr(builder_result, "model_used", None),
                        error="Deliverables JSON validation failed",
                    )
                    self._post_builder_result(phase_id, builder_result, allowed_paths)
                    self._record_learning_hint(
                        phase=phase,
                        hint_type="deliverables_validation_failed",
                        details="JSON deliverable invalid/empty (must be valid non-empty JSON; e.g. gold_set.json)",
                    )
                    return False, "DELIVERABLES_VALIDATION_FAILED"
            except Exception as e:
                logger.warning(f"[{phase_id}] Pre-apply JSON validation skipped due to error: {e}")

            # Post builder result to API
            self._post_builder_result(phase_id, builder_result, allowed_paths)

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

            # Step 2: Apply patch first (so we can run CI on it)
            logger.info(f"[{phase_id}] Step 2/5: Applying patch...")
            apply_stats: dict | None = None
            apply_stats_lines: list[str] = []

            # NEW: Check if this is a structured edit (Stage 2) or regular patch
            if builder_result.edit_plan:
                # Structured edit mode (Stage 2) - per IMPLEMENTATION_PLAN3.md Phase 4
                from autopack.structured_edits import StructuredEditApplicator

                ops_planned = len(builder_result.edit_plan.operations)
                touched_paths = sorted(
                    {
                        getattr(op, "file_path", "")
                        for op in builder_result.edit_plan.operations
                        if getattr(op, "file_path", "")
                    }
                )
                logger.info(
                    f"[{phase_id}] Applying structured edit plan with {ops_planned} operations"
                )

                # Get file contents from context
                file_contents = {}
                if file_context:
                    file_contents = file_context.get("existing_files", {})

                # Apply structured edits
                applicator = StructuredEditApplicator(workspace=Path(self.workspace))
                edit_result = applicator.apply_edit_plan(
                    plan=builder_result.edit_plan, file_contents=file_contents, dry_run=False
                )

                if not edit_result.success:
                    error_msg = (
                        edit_result.error_message
                        or f"{edit_result.operations_failed} operations failed"
                    )
                    logger.error(f"[{phase_id}] Failed to apply structured edits: {error_msg}")
                    self._update_phase_status(phase_id, "FAILED")
                    return False, "STRUCTURED_EDIT_FAILED"

                logger.info(
                    f"[{phase_id}] Structured edits applied successfully ({edit_result.operations_applied} operations)"
                )
                apply_stats = {
                    "mode": "structured_edit",
                    "operations_planned": ops_planned,
                    "operations_applied": int(edit_result.operations_applied or 0),
                    "operations_failed": int(edit_result.operations_failed or 0),
                    "touched_paths_count": len(touched_paths),
                    "touched_paths": touched_paths[:50],  # cap for logs/summaries
                }
                apply_stats_lines = [
                    "Apply mode: structured_edit",
                    f"Operations planned: {apply_stats['operations_planned']}",
                    f"Operations applied: {apply_stats['operations_applied']}",
                    f"Operations failed: {apply_stats['operations_failed']}",
                    f"Touched paths (count): {apply_stats['touched_paths_count']}",
                ]
                patch_success = True
                error_msg = None
            else:
                # Regular patch mode (full-file or diff)
                from autopack.governed_apply import GovernedApplyPath

                # NEW: Pre-apply YAML/compose validation (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
                # Check if patch contains YAML/compose files and validate them before apply
                patch_content = builder_result.patch_content or ""
                yaml_validation_failed = False
                if (
                    ".yaml" in patch_content.lower()
                    or ".yml" in patch_content.lower()
                    or "compose" in patch_content.lower()
                ):
                    try:
                        # Extract YAML content from patch (look for full-file JSON or diff hunks)
                        import json as json_mod

                        try:
                            parsed = json_mod.loads(patch_content)
                            if isinstance(parsed, dict) and "files" in parsed:
                                for file_entry in parsed.get("files", []):
                                    file_path = file_entry.get("path", "")
                                    if file_path.endswith((".yaml", ".yml")):
                                        content = file_entry.get("content", "")
                                        if (
                                            "compose" in file_path.lower()
                                            or "docker" in file_path.lower()
                                        ):
                                            result = validate_docker_compose(content, file_path)
                                        else:
                                            result = validate_yaml_syntax(content, file_path)
                                        if not result.valid:
                                            logger.error(
                                                f"[{phase_id}] YAML validation failed for {file_path}: {result.errors}"
                                            )
                                            yaml_validation_failed = True
                                        elif result.warnings:
                                            logger.warning(
                                                f"[{phase_id}] YAML warnings for {file_path}: {result.warnings}"
                                            )
                        except json_mod.JSONDecodeError:
                            pass  # Not JSON format, skip validation
                    except Exception as yaml_e:
                        logger.warning(f"[{phase_id}] YAML validation check failed: {yaml_e}")

                if yaml_validation_failed:
                    logger.error(f"[{phase_id}] Blocking apply due to YAML validation errors")
                    self._update_phase_status(phase_id, "FAILED")
                    return False, "YAML_VALIDATION_FAILED"

                # NEW: Goal drift check (per IMPLEMENTATION_PLAN_MEMORY_AND_CONTEXT.md)
                # Check if change drifts from run's goal anchor
                goal_anchor = getattr(self, "_run_goal_anchor", None)
                if goal_anchor:
                    change_intent = phase.get("description", "")[:200]
                    should_block, drift_message = should_block_on_drift(goal_anchor, change_intent)
                    if should_block:
                        logger.error(f"[{phase_id}] {drift_message}")
                        self._update_phase_status(phase_id, "FAILED")
                        return False, "GOAL_DRIFT_BLOCKED"
                    elif "ADVISORY" in drift_message:
                        logger.warning(f"[{phase_id}] {drift_message}")

                # Enable internal mode for maintenance run types
                is_maintenance_run = self.run_type in [
                    "autopack_maintenance",
                    "autopack_upgrade",
                    "self_repair",
                ]

                # NEW: Extract scope_paths for Option C Layer 2 validation
                scope_config = phase.get("scope")
                scope_paths = scope_config.get("paths", []) if scope_config else []

                # BUILD-068: If no allowed_paths were provided by scope, but this phase has explicit deliverables,
                # derive allowed root prefixes from deliverables so GovernedApply can write under those roots.
                # This is critical for research phases that create files under src/autopack/research/* (which is
                # protected by default in GovernedApplyPath).
                if not allowed_paths:
                    try:
                        from .deliverables_validator import extract_deliverables_from_scope

                        expected_paths = extract_deliverables_from_scope(scope_config or {})
                        expected_set = {p for p in expected_paths if isinstance(p, str)}
                        derived_allowed: List[str] = []
                        for r in (
                            "src/autopack/research/",
                            "src/autopack/cli/",
                            "tests/research/",
                            "docs/research/",
                        ):
                            if any(p.startswith(r) for p in expected_set):
                                derived_allowed.append(r)
                        if derived_allowed:
                            allowed_paths = derived_allowed
                    except Exception as e:
                        logger.debug(
                            f"[{phase_id}] Failed to derive allowed_paths from deliverables: {e}"
                        )

                governed_apply = GovernedApplyPath(
                    workspace=Path(self.workspace),
                    run_type=self.run_type,
                    autopack_internal_mode=is_maintenance_run,
                    scope_paths=scope_paths,  # NEW: Pass scope for validation
                    allowed_paths=allowed_paths or None,
                )
                # Per GPT_RESPONSE15: Pass full_file_mode=True since we're using full-file mode for all files ≤1000 lines
                patch_success, error_msg = governed_apply.apply_patch(
                    builder_result.patch_content, full_file_mode=True
                )
                patch_len = len(builder_result.patch_content or "")
                apply_stats = {
                    "mode": "patch",
                    "patch_nonempty": bool((builder_result.patch_content or "").strip()),
                    "patch_bytes": patch_len,
                }
                apply_stats_lines = [
                    "Apply mode: patch",
                    f"Patch non-empty: {apply_stats['patch_nonempty']}",
                    f"Patch bytes: {apply_stats['patch_bytes']}",
                ]

                if not patch_success:
                    # BUILD-127 Phase 2: Check if this is a governance request
                    governance_handled = self._try_handle_governance_request(
                        phase_id, error_msg, builder_result.patch_content, governed_apply
                    )

                    if governance_handled:
                        # Governance flow succeeded (either auto-approved or human-approved)
                        logger.info(f"[{phase_id}] Governance request approved, patch applied")
                    else:
                        # Regular patch failure or governance denied
                        logger.error(
                            f"[{phase_id}] Failed to apply patch to filesystem: {error_msg}"
                        )
                        self._update_phase_status(phase_id, "FAILED")
                        return False, "PATCH_FAILED"
                else:
                    logger.info(f"[{phase_id}] Patch applied successfully to filesystem")

            # Best-effort: write apply stats into the phase summary markdown for later forensic review.
            try:
                phase_index = int(phase.get("phase_index", 0) or 0)
                self.run_layout.write_phase_summary(
                    phase_index=phase_index,
                    phase_id=phase_id,
                    phase_name=str(phase.get("name") or phase_id),
                    state="EXECUTING",
                    task_category=phase.get("task_category"),
                    complexity=phase.get("complexity"),
                    execution_lines=apply_stats_lines or None,
                )
            except Exception:
                # Non-blocking: phase summaries are best-effort.
                pass

            # Step 3: Run CI checks on the applied code
            logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
            ci_result = self._run_ci_checks(phase_id, phase)
            if isinstance(ci_result, dict) and apply_stats:
                # Keep this small; it may be logged and passed to QualityGate.
                ci_result.setdefault("apply_stats", apply_stats)

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
                run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified  # TODO: Pass model_overrides if specified
                ci_result=ci_result,  # Now passing real CI results!
                coverage_delta=self._compute_coverage_delta(
                    ci_result
                ),  # [Phase C4] Coverage delta computation
                attempt_index=attempt_index,  # Pass attempt for model escalation
            )

            logger.info(
                f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, "
                f"issues={len(auditor_result.issues_found)}"
            )

            # Post auditor result to API
            self._post_auditor_result(phase_id, auditor_result)

            # Step 5: Apply Quality Gate (with real CI results)
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
        batching_label: str,
        manifest_allowed_roots: Tuple[str, ...],
        apply_allowed_roots: Tuple[str, ...],
    ) -> Tuple[bool, str]:
        """
        Generic in-phase batching mechanism for multi-file phases that frequently hit truncation/malformed
        diff convergence failures.

        Behavior:
        - Runs Builder once per batch, each with a batch-specific scope.paths list.
        - Enforces per-batch deliverables manifest gate + deliverables validation + new-file diff structure checks.
        - Applies each batch patch under governed apply using batch-derived allowed roots.
        - After all batches are applied, posts a combined (concatenated) diff and runs a single CI/Auditor/Quality Gate pass.
        """
        phase_id = phase.get("phase_id") or "unknown-phase"

        # Load repository context for Builder
        file_context = self._load_repository_context(phase)
        logger.info(
            f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
        )

        # Pre-flight policy (keep aligned with main execution path)
        use_full_file_mode = True
        if phase.get("builder_mode") == "structured_edit":
            use_full_file_mode = False
        if file_context and len(file_context.get("existing_files", {})) >= 30:
            use_full_file_mode = False

        learning_context = self._get_learning_context_for_phase(phase)
        project_rules = learning_context.get("project_rules", [])
        run_hints = learning_context.get("run_hints", [])
        if project_rules or run_hints:
            logger.info(
                f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
            )

        retrieved_context = ""
        if self.memory_service and self.memory_service.enabled:
            try:
                phase_description = phase.get("description", "")
                query = f"{phase_description[:500]}"
                project_id = self._get_project_slug() or self.run_id

                # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
                from autopack.config import settings

                max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
                include_sot = self._should_include_sot_retrieval(
                    max_context_chars, phase_id=phase_id
                )

                retrieved = self.memory_service.retrieve_context(
                    query=query,
                    project_id=project_id,
                    run_id=self.run_id,
                    include_code=True,
                    include_summaries=True,
                    include_errors=True,
                    include_hints=True,
                    include_planning=True,
                    include_plan_changes=True,
                    include_decisions=True,
                    include_sot=include_sot,
                )
                retrieved_context = self.memory_service.format_retrieved_context(
                    retrieved, max_chars=max_context_chars
                )

                # BUILD-155: Record SOT retrieval telemetry
                self._record_sot_retrieval_telemetry(
                    phase_id=phase_id,
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    retrieved_context=retrieved,
                    formatted_context=retrieved_context,
                )

                if retrieved_context:
                    logger.info(
                        f"[{phase_id}] Retrieved {len(retrieved_context)} chars of context from memory"
                    )
            except Exception as e:
                logger.warning(f"[{phase_id}] Memory retrieval failed: {e}")

        protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]

        from .deliverables_validator import (
            extract_deliverables_from_scope,
            validate_new_file_diffs_have_complete_structure,
        )

        logger.info(
            f"[{phase_id}] {batching_label} batching enabled: {len(batches)} batches "
            f"({', '.join(str(len(b)) for b in batches)} files)"
        )

        total_tokens = 0
        last_builder_result: Optional[BuilderResult] = None
        scope_base = phase.get("scope") or {}
        batch_patches: List[str] = []

        for idx, batch_paths in enumerate(batches, 1):
            logger.info(f"[{phase_id}] Batch {idx}/{len(batches)}: {len(batch_paths)} deliverables")

            # Use batch scope with only "paths" to avoid extract_deliverables_from_scope pulling the full deliverables dict.
            batch_scope = {
                k: v for k, v in (scope_base or {}).items() if k not in ("deliverables", "paths")
            }
            batch_scope["paths"] = list(batch_paths)
            phase_for_batch = {**phase, "scope": batch_scope}

            deliverables_contract = self._build_deliverables_contract(phase_for_batch, phase_id)
            phase_with_constraints = {
                **phase_for_batch,
                "protected_paths": protected_paths,
                "deliverables_contract": deliverables_contract,
            }

            # Retry optimization: if we are retrying the phase and this batch's deliverables already exist,
            # skip rebuilding/reapplying them to avoid wasting tokens (common when only docs batch fails).
            # We still attempt to include a scoped git diff for auditor visibility.
            if attempt_index > 0 and batch_paths:
                try:
                    ws = Path(self.workspace)

                    def _exists_nonempty(rel_path: str) -> bool:
                        try:
                            p = ws / rel_path
                            return p.exists() and p.is_file() and p.stat().st_size > 0
                        except Exception:
                            return False

                    if all(_exists_nonempty(p) for p in batch_paths):
                        logger.info(
                            f"[{phase_id}] Skipping batch {idx}/{len(batches)} on retry (attempt={attempt_index}) "
                            f"- all deliverables already exist"
                        )
                        try:
                            proc = subprocess.run(
                                ["git", "diff", "--no-color", "--", *batch_paths],
                                cwd=str(ws),
                                capture_output=True,
                                text=True,
                            )
                            if proc.returncode == 0 and (proc.stdout or "").strip():
                                batch_patches.append(proc.stdout)
                        except Exception as e:
                            logger.warning(
                                f"[{phase_id}] Failed to compute scoped git diff for skipped batch {idx}: {e}"
                            )

                        # Refresh context so later batches see the latest on-disk files for this batch.
                        try:
                            file_context = self._load_repository_context(phase_for_batch)
                        except Exception as e:
                            logger.warning(
                                f"[{phase_id}] Context refresh failed for skipped batch {idx}: {e}"
                            )
                        continue
                except Exception as e:
                    logger.warning(f"[{phase_id}] Retry-skip check failed for batch {idx}: {e}")

            # Manifest gate for this batch
            manifest_paths: List[str] = []
            try:
                expected_paths = extract_deliverables_from_scope(batch_scope)
                if expected_paths and self.llm_service and deliverables_contract:
                    expected_set = {p for p in expected_paths if isinstance(p, str)}
                    expected_list = sorted(expected_set)

                    allowed_roots: List[str] = []
                    for r in manifest_allowed_roots:
                        if any(p.startswith(r) for p in expected_list):
                            allowed_roots.append(r)
                    if not allowed_roots:
                        # Expand to first-2 segments roots
                        expanded: List[str] = []
                        for p in expected_list:
                            parts = p.split("/")
                            # For root-level files (no "/"), include the file itself
                            if len(parts) == 1:
                                root = p
                            # If second segment contains '.', it's likely a filename, use first dir
                            elif len(parts) >= 2 and "." in parts[1]:
                                root = parts[0] + "/"
                            else:
                                root = "/".join(parts[:2]) + "/"
                            if root not in expanded:
                                expanded.append(root)
                        allowed_roots = expanded

                    ok_manifest, manifest_paths, manifest_error, _raw = (
                        self.llm_service.generate_deliverables_manifest(
                            expected_paths=list(expected_set),
                            allowed_roots=allowed_roots,
                            run_id=self.run_id,
                            phase_id=phase_id,
                            attempt_index=attempt_index,
                        )
                    )
                    if not ok_manifest:
                        err_details = manifest_error or "deliverables manifest gate failed"
                        logger.error(
                            f"[{phase_id}] Deliverables manifest gate FAILED (batch {idx}): {err_details}"
                        )
                        self._record_phase_error(
                            phase, "deliverables_manifest_failed", err_details, attempt_index
                        )
                        self._record_learning_hint(
                            phase, "deliverables_manifest_failed", err_details
                        )
                        return False, "DELIVERABLES_VALIDATION_FAILED"
                    logger.info(
                        f"[{phase_id}] Deliverables manifest gate PASSED (batch {idx}, {len(manifest_paths or [])} paths)"
                    )
                    phase_with_constraints["deliverables_manifest"] = manifest_paths or []
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Deliverables manifest gate error (batch {idx}, skipping gate): {e}"
                )

            # Run Builder for this batch
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase_with_constraints,
                file_context=file_context,
                max_tokens=None,
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=self.run_id,
                phase_id=phase_id,
                run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
                attempt_index=attempt_index,
                use_full_file_mode=use_full_file_mode,
                config=self.builder_output_config,
                retrieved_context=retrieved_context,
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed (batch {idx}): {builder_result.error}")
                self._post_builder_result(phase_id, builder_result, allowed_paths)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            last_builder_result = builder_result
            total_tokens += int(getattr(builder_result, "tokens_used", 0) or 0)
            logger.info(
                f"[{phase_id}] Builder succeeded (batch {idx}, {builder_result.tokens_used} tokens)"
            )

            # Deliverables validation for this batch
            scope_config = dict(batch_scope)
            if manifest_paths:
                scope_config["deliverables_manifest"] = manifest_paths
            is_valid, validation_errors, validation_details = validate_deliverables(
                patch_content=builder_result.patch_content or "",
                phase_scope=scope_config,
                phase_id=phase_id,
                workspace=Path(self.workspace),
            )
            if not is_valid:
                feedback = format_validation_feedback_for_builder(
                    errors=validation_errors,
                    details=validation_details,
                    phase_description=phase.get("description", ""),
                )
                logger.error(f"[{phase_id}] Deliverables validation failed (batch {idx})")
                logger.error(f"[{phase_id}] {feedback}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", feedback],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Deliverables validation failed",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Structural validation for new files (headers + hunks + content where applicable)
            expected_paths = extract_deliverables_from_scope(scope_config or {})
            ok_struct, struct_errors, struct_details = (
                validate_new_file_diffs_have_complete_structure(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                    allow_empty_suffixes=["__init__.py", ".gitkeep"],
                )
            )
            if not ok_struct:
                logger.error(f"[{phase_id}] Patch format invalid for new file diffs (batch {idx})")
                for e in struct_errors[:10]:
                    logger.error(f"[{phase_id}]    {e}")
                feedback_lines = [
                    "❌ PATCH FORMAT ERROR (NEW FILE DIFFS)",
                    "",
                    "For EVERY new file deliverable, your patch MUST include:",
                    "- `--- /dev/null` and `+++ b/<path>` headers",
                    "- at least one `@@ ... @@` hunk header",
                    "- `+` content lines for the file body (do not emit header-only diffs)",
                    "",
                ]
                for p in (struct_details.get("missing_headers", []) or [])[:10]:
                    feedback_lines.append(f"- Missing headers: {p}")
                for p in (struct_details.get("missing_hunks", []) or [])[:10]:
                    feedback_lines.append(f"- Missing hunks: {p}")
                for p in (struct_details.get("empty_content", []) or [])[:10]:
                    feedback_lines.append(f"- Empty content: {p}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", "\n".join(feedback_lines)],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Patch format invalid for new file diffs (missing headers/hunks/content)",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Apply patch for this batch
            from autopack.governed_apply import GovernedApplyPath

            scope_paths = batch_scope.get("paths", []) if isinstance(batch_scope, dict) else []
            derived_allowed: List[str] = []
            for r in apply_allowed_roots:
                if any(p.startswith(r) for p in expected_paths):
                    derived_allowed.append(r)
            if not derived_allowed:
                derived_allowed = allowed_paths or []

            governed_apply = GovernedApplyPath(
                workspace=Path(self.workspace),
                run_type=self.run_type,
                autopack_internal_mode=self.run_type
                in ["autopack_maintenance", "autopack_upgrade", "self_repair"],
                scope_paths=scope_paths,
                allowed_paths=derived_allowed or None,
            )
            patch_success, error_msg = governed_apply.apply_patch(
                builder_result.patch_content, full_file_mode=True
            )
            if not patch_success:
                logger.error(f"[{phase_id}] Failed to apply patch (batch {idx}): {error_msg}")
                # Convergence fallback for docs-only batches:
                # Some models occasionally emit markdown placeholders like "# ..." which triggers truncation validation.
                # If this batch is a single docs/*.md deliverable, synthesize a minimal deterministic doc patch and apply it.
                try:
                    if (
                        len(batch_paths) == 1
                        and isinstance(batch_paths[0], str)
                        and batch_paths[0].startswith("docs/")
                        and batch_paths[0].endswith(".md")
                        and isinstance(error_msg, str)
                        and (
                            "truncation" in error_msg.lower()
                            or "ellipsis" in error_msg.lower()
                            or "patch validation failed" in error_msg.lower()
                        )
                    ):
                        doc_rel = batch_paths[0]
                        logger.warning(
                            f"[{phase_id}] Docs batch truncation detected; applying deterministic fallback doc for {doc_rel}"
                        )

                        # Minimal, deterministic content (kept short to avoid token blowups and truncation markers).
                        content = (
                            "\n".join(
                                [
                                    "# Diagnostics Iteration Loop",
                                    "",
                                    "This document describes the diagnostics iteration loop enhancements that make Autopack behave more like a guided Cursor debugging session.",
                                    "",
                                    "## Goals",
                                    "- Add a small, explicit **Evidence Requests** section to handoff prompts.",
                                    "- Accept compact human responses and fold them back into the handoff bundle without token blowups.",
                                    "",
                                    "## Evidence requests",
                                    "Evidence requests are a short list (<= 5) of concrete missing artifacts or questions, each with a rationale.",
                                    "",
                                    "Typical inputs:",
                                    "- Current handoff bundle (index/summary/excerpts).",
                                    "- Latest error category and failing command output (when available).",
                                    "",
                                    "Typical outputs:",
                                    "- A list of requested files/artifacts and targeted questions.",
                                    "",
                                    "## Human response ingestion",
                                    "The human response parser accepts a compact text format such as:",
                                    "",
                                    "```\nQ1: <answer>; Q2: <answer>; Attached: <path1>, <path2>\n```",
                                    "",
                                    "Rules:",
                                    "- Be tolerant of missing fields.",
                                    "- Treat attached paths as references (repo-relative or absolute) and validate existence when possible.",
                                    "",
                                    "## Iteration behavior",
                                    "- Each loop should stay small (<= 500 chars incremental overhead per round).",
                                    "- Prompts should become more targeted after 1-2 rounds.",
                                    "- Stop after 3 rounds (or when the operator indicates they are done).",
                                    "",
                                    "## Deliverables",
                                    "- Code: `src/autopack/diagnostics/evidence_requests.py`, `src/autopack/diagnostics/human_response_parser.py`",
                                    "- Tests: `tests/autopack/diagnostics/test_evidence_requests.py`, `tests/autopack/diagnostics/test_human_response_parser.py`",
                                    "- Docs: this file",
                                    "",
                                ]
                            )
                            + "\n"
                        )

                        fallback_patch = "\n".join(
                            [
                                f"diff --git a/{doc_rel} b/{doc_rel}",
                                "new file mode 100644",
                                "index 0000000..1111111",
                                "--- /dev/null",
                                f"+++ b/{doc_rel}",
                                "@@ -0,0 +1,999 @@",
                            ]
                            + [f"+{line}" for line in content.splitlines()]
                            + [""]
                        )

                        ok2, err2 = governed_apply.apply_patch(fallback_patch, full_file_mode=True)
                        if ok2:
                            logger.info(
                                f"[{phase_id}] Fallback doc patch applied successfully (batch {idx})"
                            )
                            batch_patches.append(fallback_patch)
                            try:
                                file_context = self._load_repository_context(phase_for_batch)
                            except Exception as e:
                                logger.warning(
                                    f"[{phase_id}] Context refresh failed after fallback doc batch {idx}: {e}"
                                )
                            continue
                        else:
                            logger.error(
                                f"[{phase_id}] Fallback doc patch failed (batch {idx}): {err2}"
                            )
                except Exception as e:
                    logger.warning(
                        f"[{phase_id}] Fallback doc apply encountered error (batch {idx}): {e}"
                    )

                self._update_phase_status(phase_id, "FAILED")
                return False, "PATCH_FAILED"
            logger.info(f"[{phase_id}] Patch applied successfully (batch {idx})")

            batch_patches.append(builder_result.patch_content or "")

            # Refresh context so next batch sees created files (and becomes scope-aware via scope.paths)
            try:
                file_context = self._load_repository_context(phase_for_batch)
            except Exception as e:
                logger.warning(f"[{phase_id}] Context refresh failed after batch {idx}: {e}")

        # Combined patch for auditor/quality gate: concatenate batch patches (do NOT use git diff; repo may be dirty)
        combined_patch = "\n".join([p for p in batch_patches if isinstance(p, str) and p.strip()])

        combined_result = BuilderResult(
            success=True,
            patch_content=combined_patch
            or (last_builder_result.patch_content if last_builder_result else ""),
            builder_messages=[f"batched_{batching_label}: {len(batches)} batches applied"],
            tokens_used=total_tokens,
            model_used=(
                getattr(last_builder_result, "model_used", None) if last_builder_result else None
            ),
            error=None,
        )
        self._post_builder_result(phase_id, combined_result, allowed_paths)

        # Proceed with normal CI/Auditor/Quality Gate using the combined patch content
        logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
        ci_result = self._run_ci_checks(phase_id, phase)

        logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")
        auditor_result = self.llm_service.execute_auditor_review(
            patch_content=combined_result.patch_content,
            phase_spec=phase,
            max_tokens=None,
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=self.run_id,
            phase_id=phase_id,
            run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
            ci_result=ci_result,
            coverage_delta=0.0,
            attempt_index=attempt_index,
        )
        logger.info(
            f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, issues={len(auditor_result.issues_found)}"
        )
        self._post_auditor_result(phase_id, auditor_result)

        logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
        quality_report = self.quality_gate.assess_phase(
            phase_id=phase_id,
            phase_spec=phase,
            auditor_result={
                "approved": auditor_result.approved,
                "issues_found": auditor_result.issues_found,
            },
            ci_result=ci_result,
            coverage_delta=0.0,
            patch_content=combined_result.patch_content,
            files_changed=None,
        )
        logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")
        if quality_report.is_blocked():
            logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
            for issue in quality_report.issues:
                logger.warning(f"  - {issue}")
            self._update_phase_status(phase_id, "BLOCKED")
            return False, "BLOCKED"

        self._update_phase_status(phase_id, "COMPLETE")
        logger.info(f"[{phase_id}] Phase completed successfully (batched)")
        return True, "COMPLETE"

    def _execute_diagnostics_deep_retrieval_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-7 `diagnostics-deep-retrieval` (code → tests → docs)."""
        from .deliverables_validator import extract_deliverables_from_scope

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]
        batch_code = sorted([p for p in all_paths if p.startswith("src/autopack/diagnostics/")])
        batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])
        batches = [b for b in [batch_code, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]

        return self._execute_batched_deliverables_phase(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label="diagnostics_deep_retrieval",
            manifest_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
            apply_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
        )

    def _execute_diagnostics_iteration_loop_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-8 `diagnostics-iteration-loop` (code → tests → docs)."""
        from .deliverables_validator import extract_deliverables_from_scope

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]
        batch_code = sorted([p for p in all_paths if p.startswith("src/autopack/diagnostics/")])
        batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])
        batches = [b for b in [batch_code, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]

        return self._execute_batched_deliverables_phase(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label="diagnostics_iteration_loop",
            manifest_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
            apply_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
        )

    def _execute_diagnostics_handoff_bundle_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-1 `diagnostics-handoff-bundle` (code → tests → docs)."""
        from .deliverables_validator import extract_deliverables_from_scope

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]

        # Batch 1: code files (src/autopack/)
        batch_code = sorted(
            [
                p
                for p in all_paths
                if p.startswith("src/autopack/") and not p.startswith("src/autopack/cli/")
            ]
        )
        # Batch 2: CLI code
        batch_cli = sorted([p for p in all_paths if p.startswith("src/autopack/cli/")])
        # Batch 3: tests
        batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
        # Batch 4: docs
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])

        batches = [b for b in [batch_code, batch_cli, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]

        return self._execute_batched_deliverables_phase(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label="diagnostics_handoff_bundle",
            manifest_allowed_roots=(
                "src/autopack/diagnostics/",
                "src/autopack/cli/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
            apply_allowed_roots=(
                "src/autopack/diagnostics/",
                "src/autopack/cli/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
        )

    def _execute_diagnostics_cursor_prompt_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-2 `diagnostics-cursor-prompt` (code → tests → docs)."""
        from .deliverables_validator import extract_deliverables_from_scope

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]

        # Batch 1: diagnostics code
        batch_diag = sorted([p for p in all_paths if p.startswith("src/autopack/diagnostics/")])
        # Batch 2: dashboard code
        batch_dash = sorted([p for p in all_paths if p.startswith("src/autopack/dashboard/")])
        # Batch 3: tests
        batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
        # Batch 4: docs
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])

        batches = [b for b in [batch_diag, batch_dash, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]

        return self._execute_batched_deliverables_phase(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label="diagnostics_cursor_prompt",
            manifest_allowed_roots=(
                "src/autopack/diagnostics/",
                "src/autopack/dashboard/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
            apply_allowed_roots=(
                "src/autopack/diagnostics/",
                "src/autopack/dashboard/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
        )

    def _execute_diagnostics_second_opinion_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """Specialized in-phase batching for followup-3 `diagnostics-second-opinion-triage` (code → tests → docs)."""
        from .deliverables_validator import extract_deliverables_from_scope

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]

        # Batch 1: code
        batch_code = sorted([p for p in all_paths if p.startswith("src/autopack/diagnostics/")])
        # Batch 2: tests
        batch_tests = sorted([p for p in all_paths if p.startswith("tests/autopack/diagnostics/")])
        # Batch 3: docs
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/autopack/")])

        batches = [b for b in [batch_code, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]

        return self._execute_batched_deliverables_phase(
            phase=phase,
            attempt_index=attempt_index,
            allowed_paths=allowed_paths,
            batches=batches,
            batching_label="diagnostics_second_opinion",
            manifest_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
            apply_allowed_roots=(
                "src/autopack/diagnostics/",
                "tests/autopack/diagnostics/",
                "docs/autopack/",
            ),
        )

    def _execute_research_tracer_bullet_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """
        Specialized in-phase batching for Chunk 0 (research-tracer-bullet).

        Why:
        - Chunk 0 creates 11 new files; LLM often returns truncated patches (unclosed quotes),
          or malformed header-only new-file diffs (no hunks), which prevents convergence.
        - Splitting into smaller batches materially reduces truncation probability and surfaces
          format issues earlier with tighter feedback.
        """
        phase_id = phase.get("phase_id") or "research-tracer-bullet"

        # Load repository context for Builder
        file_context = self._load_repository_context(phase)
        logger.info(
            f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
        )

        # Pre-flight policy (keep aligned with main execution path)
        use_full_file_mode = True
        if phase.get("builder_mode") == "structured_edit":
            use_full_file_mode = False
        if file_context and len(file_context.get("existing_files", {})) >= 30:
            use_full_file_mode = False

        learning_context = self._get_learning_context_for_phase(phase)
        project_rules = learning_context.get("project_rules", [])
        run_hints = learning_context.get("run_hints", [])
        if project_rules or run_hints:
            logger.info(
                f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
            )

        retrieved_context = ""
        if self.memory_service and self.memory_service.enabled:
            try:
                phase_description = phase.get("description", "")
                query = f"{phase_description[:500]}"
                project_id = self._get_project_slug() or self.run_id

                # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
                from autopack.config import settings

                max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
                include_sot = self._should_include_sot_retrieval(
                    max_context_chars, phase_id=phase_id
                )

                retrieved = self.memory_service.retrieve_context(
                    query=query,
                    project_id=project_id,
                    run_id=self.run_id,
                    include_code=True,
                    include_summaries=True,
                    include_errors=True,
                    include_hints=True,
                    include_planning=True,
                    include_plan_changes=True,
                    include_decisions=True,
                    include_sot=include_sot,
                )
                retrieved_context = self.memory_service.format_retrieved_context(
                    retrieved, max_chars=max_context_chars
                )

                # BUILD-155: Record SOT retrieval telemetry
                self._record_sot_retrieval_telemetry(
                    phase_id=phase_id,
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    retrieved_context=retrieved,
                    formatted_context=retrieved_context,
                )

                if retrieved_context:
                    logger.info(
                        f"[{phase_id}] Retrieved {len(retrieved_context)} chars of context from memory"
                    )
            except Exception as e:
                logger.warning(f"[{phase_id}] Memory retrieval failed: {e}")

        protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]

        # Partition deliverables into batches
        from .deliverables_validator import (
            extract_deliverables_from_scope,
            validate_new_file_diffs_have_complete_structure,
        )
        from .deliverables_validator import (
            validate_deliverables,
            format_validation_feedback_for_builder,
        )

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]
        batch_core = sorted(
            [p for p in all_paths if p.startswith("src/autopack/research/tracer_bullet/")]
        )
        batch_eval = sorted(
            [p for p in all_paths if p.startswith("src/autopack/research/evaluation/")]
        )
        batch_tests = sorted(
            [p for p in all_paths if p.startswith("tests/research/tracer_bullet/")]
        )
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/research/")])
        batches = [b for b in [batch_core, batch_eval, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]
        logger.info(
            f"[{phase_id}] Chunk0 batching enabled: {len(batches)} batches ({', '.join(str(len(b)) for b in batches)} files)"
        )

        # Baseline diff for combined patch generation
        try:
            proc = subprocess.run(
                ["git", "diff", "--no-color"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
            )
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to capture baseline git diff: {e}")

        total_tokens = 0
        last_builder_result: Optional[BuilderResult] = None

        for idx, batch_paths in enumerate(batches, 1):
            logger.info(f"[{phase_id}] Batch {idx}/{len(batches)}: {len(batch_paths)} deliverables")

            # Use batch scope with only "paths" to avoid extract_deliverables_from_scope pulling the full deliverables dict.
            batch_scope = {
                k: v for k, v in (scope_base or {}).items() if k not in ("deliverables", "paths")
            }
            batch_scope["paths"] = list(batch_paths)
            phase_for_batch = {**phase, "scope": batch_scope}

            deliverables_contract = self._build_deliverables_contract(phase_for_batch, phase_id)
            phase_with_constraints = {
                **phase_for_batch,
                "protected_paths": protected_paths,
                "deliverables_contract": deliverables_contract,
            }

            # Manifest gate for this batch
            manifest_paths: List[str] = []
            try:
                expected_paths = extract_deliverables_from_scope(batch_scope)
                if expected_paths and self.llm_service and deliverables_contract:
                    expected_set = {p for p in expected_paths if isinstance(p, str)}
                    expected_list = sorted(expected_set)
                    allowed_roots: List[str] = []
                    for r in (
                        "src/autopack/research/",
                        "tests/research/",
                        "docs/research/",
                        "examples/",
                    ):
                        if any(p.startswith(r) for p in expected_list):
                            allowed_roots.append(r)
                    if not allowed_roots:
                        # Expand to first-2 segments roots
                        expanded: List[str] = []
                        for p in expected_list:
                            parts = p.split("/")
                            # For root-level files (no "/"), include the file itself
                            if len(parts) == 1:
                                root = p
                            # If second segment contains '.', it's likely a filename, use first dir
                            elif len(parts) >= 2 and "." in parts[1]:
                                root = parts[0] + "/"
                            else:
                                root = "/".join(parts[:2]) + "/"
                            if root not in expanded:
                                expanded.append(root)
                        allowed_roots = expanded

                    ok_manifest, manifest_paths, manifest_error, _raw = (
                        self.llm_service.generate_deliverables_manifest(
                            expected_paths=list(expected_set),
                            allowed_roots=allowed_roots,
                            run_id=self.run_id,
                            phase_id=phase_id,
                            attempt_index=attempt_index,
                        )
                    )
                    if not ok_manifest:
                        err_details = manifest_error or "deliverables manifest gate failed"
                        logger.error(
                            f"[{phase_id}] Deliverables manifest gate FAILED (batch {idx}): {err_details}"
                        )
                        self._record_phase_error(
                            phase, "deliverables_manifest_failed", err_details, attempt_index
                        )
                        self._record_learning_hint(
                            phase, "deliverables_manifest_failed", err_details
                        )
                        return False, "DELIVERABLES_VALIDATION_FAILED"
                    logger.info(
                        f"[{phase_id}] Deliverables manifest gate PASSED (batch {idx}, {len(manifest_paths or [])} paths)"
                    )
                    phase_with_constraints["deliverables_manifest"] = manifest_paths or []
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Deliverables manifest gate error (batch {idx}, skipping gate): {e}"
                )

            # Run Builder for this batch
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase_with_constraints,
                file_context=file_context,
                max_tokens=None,
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=self.run_id,
                phase_id=phase_id,
                run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
                attempt_index=attempt_index,
                use_full_file_mode=use_full_file_mode,
                config=self.builder_output_config,
                retrieved_context=retrieved_context,
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed (batch {idx}): {builder_result.error}")
                self._post_builder_result(phase_id, builder_result, allowed_paths)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            last_builder_result = builder_result
            total_tokens += int(getattr(builder_result, "tokens_used", 0) or 0)
            logger.info(
                f"[{phase_id}] Builder succeeded (batch {idx}, {builder_result.tokens_used} tokens)"
            )

            # Deliverables validation for this batch
            scope_config = dict(batch_scope)
            if manifest_paths:
                scope_config["deliverables_manifest"] = manifest_paths
            is_valid, validation_errors, validation_details = validate_deliverables(
                patch_content=builder_result.patch_content or "",
                phase_scope=scope_config,
                phase_id=phase_id,
                workspace=Path(self.workspace),
            )
            if not is_valid:
                feedback = format_validation_feedback_for_builder(
                    errors=validation_errors,
                    details=validation_details,
                    phase_description=phase.get("description", ""),
                )
                logger.error(f"[{phase_id}] Deliverables validation failed (batch {idx})")
                logger.error(f"[{phase_id}] {feedback}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", feedback],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Deliverables validation failed",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Structural validation for new files (headers + hunks + content where applicable)
            expected_paths = extract_deliverables_from_scope(scope_config or {})
            ok_struct, struct_errors, struct_details = (
                validate_new_file_diffs_have_complete_structure(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                    allow_empty_suffixes=["__init__.py", ".gitkeep"],
                )
            )
            if not ok_struct:
                logger.error(f"[{phase_id}] Patch format invalid for new file diffs (batch {idx})")
                for e in struct_errors[:10]:
                    logger.error(f"[{phase_id}]    {e}")
                feedback_lines = [
                    "❌ PATCH FORMAT ERROR (NEW FILE DIFFS)",
                    "",
                    "For EVERY new file deliverable, your patch MUST include:",
                    "- `--- /dev/null` and `+++ b/<path>` headers",
                    "- at least one `@@ ... @@` hunk header",
                    "- `+` content lines for the file body (do not emit header-only diffs)",
                    "",
                ]
                for p in (struct_details.get("missing_headers", []) or [])[:10]:
                    feedback_lines.append(f"- Missing headers: {p}")
                for p in (struct_details.get("missing_hunks", []) or [])[:10]:
                    feedback_lines.append(f"- Missing hunks: {p}")
                for p in (struct_details.get("empty_content", []) or [])[:10]:
                    feedback_lines.append(f"- Empty content: {p}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", "\n".join(feedback_lines)],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Patch format invalid for new file diffs (missing headers/hunks/content)",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Pre-apply JSON deliverable validation + repair (reuse existing helpers)
            try:
                from .deliverables_validator import (
                    validate_new_json_deliverables_in_patch,
                    repair_empty_required_json_deliverables_in_patch,
                )

                ok_json, json_errors, _json_details = validate_new_json_deliverables_in_patch(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                )
                if not ok_json:
                    repaired, repaired_patch, repairs = (
                        repair_empty_required_json_deliverables_in_patch(
                            patch_content=builder_result.patch_content or "",
                            expected_paths=expected_paths,
                            workspace=Path(self.workspace),
                            minimal_json="[]\n",
                        )
                    )
                    if repaired:
                        logger.warning(
                            f"[{phase_id}] Auto-repaired {len(repairs)} JSON deliverable(s) (batch {idx})"
                        )
                        builder_result.patch_content = repaired_patch
                        ok_json2, json_errors2, _ = validate_new_json_deliverables_in_patch(
                            patch_content=builder_result.patch_content or "",
                            expected_paths=expected_paths,
                            workspace=Path(self.workspace),
                        )
                        ok_json = ok_json2
                        json_errors = json_errors2
                if not ok_json:
                    logger.error(
                        f"[{phase_id}] Pre-apply JSON deliverables validation failed (batch {idx})"
                    )
                    for e in (json_errors or [])[:5]:
                        logger.error(f"[{phase_id}]    {e}")
                    fail_result = BuilderResult(
                        success=False,
                        patch_content="",
                        builder_messages=[
                            "DELIVERABLES_VALIDATION_FAILED",
                            "JSON deliverable empty/invalid",
                        ],
                        tokens_used=builder_result.tokens_used,
                        model_used=getattr(builder_result, "model_used", None),
                        error="Deliverables JSON validation failed",
                    )
                    self._post_builder_result(phase_id, fail_result, allowed_paths)
                    return False, "DELIVERABLES_VALIDATION_FAILED"
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Pre-apply JSON validation skipped due to error (batch {idx}): {e}"
                )

            # Apply patch for this batch
            from autopack.governed_apply import GovernedApplyPath

            # Derive scope_paths and allowed_paths for governed apply from this batch scope
            scope_paths = batch_scope.get("paths", []) if isinstance(batch_scope, dict) else []
            derived_allowed: List[str] = []
            for r in ("src/autopack/research/", "tests/research/", "docs/research/"):
                if any(p.startswith(r) for p in expected_paths):
                    derived_allowed.append(r)
            if not derived_allowed:
                derived_allowed = allowed_paths or []

            governed_apply = GovernedApplyPath(
                workspace=Path(self.workspace),
                run_type=self.run_type,
                autopack_internal_mode=self.run_type
                in ["autopack_maintenance", "autopack_upgrade", "self_repair"],
                scope_paths=scope_paths,
                allowed_paths=derived_allowed or None,
            )
            patch_success, error_msg = governed_apply.apply_patch(
                builder_result.patch_content, full_file_mode=True
            )
            if not patch_success:
                logger.error(f"[{phase_id}] Failed to apply patch (batch {idx}): {error_msg}")
                self._update_phase_status(phase_id, "FAILED")
                return False, "PATCH_FAILED"
            logger.info(f"[{phase_id}] Patch applied successfully (batch {idx})")

            # Refresh context so next batch sees created files
            try:
                file_context = self._load_repository_context(phase_for_batch)
            except Exception as e:
                logger.warning(f"[{phase_id}] Context refresh failed after batch {idx}: {e}")

        # Build combined patch for auditor/quality gate
        combined_patch = ""
        try:
            proc = subprocess.run(
                ["git", "diff", "--no-color"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
            )
            combined_patch = proc.stdout or ""
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to compute combined patch after batching: {e}")

        # Post a single combined builder result to API for phase-level visibility
        combined_result = BuilderResult(
            success=True,
            patch_content=combined_patch
            or (last_builder_result.patch_content if last_builder_result else ""),
            builder_messages=[f"batched_chunk0: {len(batches)} batches applied"],
            tokens_used=total_tokens,
            model_used=(
                getattr(last_builder_result, "model_used", None) if last_builder_result else None
            ),
            error=None,
        )
        self._post_builder_result(phase_id, combined_result, allowed_paths)

        # Proceed with normal CI/Auditor/Quality Gate using the combined patch content
        logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
        ci_result = self._run_ci_checks(phase_id, phase)

        logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")
        auditor_result = self.llm_service.execute_auditor_review(
            patch_content=combined_result.patch_content,
            phase_spec=phase,
            max_tokens=None,
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=self.run_id,
            phase_id=phase_id,
            run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
            ci_result=ci_result,
            coverage_delta=0.0,
            attempt_index=attempt_index,
        )
        logger.info(
            f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, issues={len(auditor_result.issues_found)}"
        )
        self._post_auditor_result(phase_id, auditor_result)

        logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
        quality_report = self.quality_gate.assess_phase(
            phase_id=phase_id,
            phase_spec=phase,
            auditor_result={
                "approved": auditor_result.approved,
                "issues_found": auditor_result.issues_found,
            },
            ci_result=ci_result,
            coverage_delta=0.0,
            patch_content=combined_result.patch_content,
            files_changed=None,
        )
        logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")
        if quality_report.is_blocked():
            logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
            for issue in quality_report.issues:
                logger.warning(f"  - {issue}")
            self._update_phase_status(phase_id, "BLOCKED")
            return False, "BLOCKED"

        self._update_phase_status(phase_id, "COMPLETE")
        logger.info(f"[{phase_id}] Phase completed successfully (batched)")
        return True, "COMPLETE"

    def _execute_research_gatherers_web_compilation_batched(
        self,
        *,
        phase: Dict,
        attempt_index: int,
        allowed_paths: Optional[List[str]],
    ) -> Tuple[bool, str]:
        """
        Specialized in-phase batching for Chunk 2B (research-gatherers-web-compilation).

        Why:
        - Chunk 2B often produces truncated/incomplete patches (e.g., unclosed triple quotes in tests)
          and/or malformed header-only new file diffs for docs, which blocks convergence.
        - Splitting deliverables into smaller, prefix-based batches materially reduces truncation
          probability and yields earlier, tighter feedback.
        """
        phase_id = phase.get("phase_id") or "research-gatherers-web-compilation"

        # Load repository context for Builder
        file_context = self._load_repository_context(phase)
        logger.info(
            f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context"
        )

        # Pre-flight policy (keep aligned with main execution path)
        use_full_file_mode = True
        if phase.get("builder_mode") == "structured_edit":
            use_full_file_mode = False
        if file_context and len(file_context.get("existing_files", {})) >= 30:
            use_full_file_mode = False

        learning_context = self._get_learning_context_for_phase(phase)
        project_rules = learning_context.get("project_rules", [])
        run_hints = learning_context.get("run_hints", [])
        if project_rules or run_hints:
            logger.info(
                f"[{phase_id}] Learning context: {len(project_rules)} rules, {len(run_hints)} hints"
            )

        retrieved_context = ""
        if self.memory_service and self.memory_service.enabled:
            try:
                phase_description = phase.get("description", "")
                query = f"{phase_description[:500]}"
                project_id = self._get_project_slug() or self.run_id

                # BUILD-154: Make SOT budget gating + telemetry explicit and non-silent
                from autopack.config import settings

                max_context_chars = max(4000, settings.autopack_sot_retrieval_max_chars + 2000)
                include_sot = self._should_include_sot_retrieval(
                    max_context_chars, phase_id=phase_id
                )

                retrieved = self.memory_service.retrieve_context(
                    query=query,
                    project_id=project_id,
                    run_id=self.run_id,
                    include_code=True,
                    include_summaries=True,
                    include_errors=True,
                    include_hints=True,
                    include_planning=True,
                    include_plan_changes=True,
                    include_decisions=True,
                    include_sot=include_sot,
                )
                retrieved_context = self.memory_service.format_retrieved_context(
                    retrieved, max_chars=max_context_chars
                )

                # BUILD-155: Record SOT retrieval telemetry
                self._record_sot_retrieval_telemetry(
                    phase_id=phase_id,
                    include_sot=include_sot,
                    max_context_chars=max_context_chars,
                    retrieved_context=retrieved,
                    formatted_context=retrieved_context,
                )

                if retrieved_context:
                    logger.info(
                        f"[{phase_id}] Retrieved {len(retrieved_context)} chars of context from memory"
                    )
            except Exception as e:
                logger.warning(f"[{phase_id}] Memory retrieval failed: {e}")

        protected_paths = [".autonomous_runs/", ".git/", "autopack.db"]

        # Partition deliverables into batches
        from .deliverables_validator import (
            extract_deliverables_from_scope,
            validate_new_file_diffs_have_complete_structure,
        )
        from .deliverables_validator import (
            validate_deliverables,
            format_validation_feedback_for_builder,
        )

        scope_base = phase.get("scope") or {}
        all_paths = [
            p
            for p in extract_deliverables_from_scope(scope_base)
            if isinstance(p, str) and p.strip()
        ]

        # Suggested batches:
        # - src/research/gatherers/*
        # - src/research/agents/*
        # - tests/research/gatherers/* + tests/research/agents/*
        # - docs/research/*
        batch_gatherers = sorted([p for p in all_paths if p.startswith("src/research/gatherers/")])
        batch_agents = sorted([p for p in all_paths if p.startswith("src/research/agents/")])
        batch_tests = sorted(
            [
                p
                for p in all_paths
                if p.startswith("tests/research/gatherers/")
                or p.startswith("tests/research/agents/")
            ]
        )
        batch_docs = sorted([p for p in all_paths if p.startswith("docs/research/")])
        batches = [b for b in [batch_gatherers, batch_agents, batch_tests, batch_docs] if b]
        if not batches:
            batches = [sorted(set(all_paths))]
        logger.info(
            f"[{phase_id}] Chunk2B batching enabled: {len(batches)} batches ({', '.join(str(len(b)) for b in batches)} files)"
        )

        total_tokens = 0
        last_builder_result: Optional[BuilderResult] = None

        for idx, batch_paths in enumerate(batches, 1):
            logger.info(f"[{phase_id}] Batch {idx}/{len(batches)}: {len(batch_paths)} deliverables")

            # Use batch scope with only "paths" to avoid extract_deliverables_from_scope pulling the full deliverables dict.
            batch_scope = {
                k: v for k, v in (scope_base or {}).items() if k not in ("deliverables", "paths")
            }
            batch_scope["paths"] = list(batch_paths)
            phase_for_batch = {**phase, "scope": batch_scope}

            deliverables_contract = self._build_deliverables_contract(phase_for_batch, phase_id)
            phase_with_constraints = {
                **phase_for_batch,
                "protected_paths": protected_paths,
                "deliverables_contract": deliverables_contract,
            }

            # Manifest gate for this batch
            manifest_paths: List[str] = []
            try:
                expected_paths = extract_deliverables_from_scope(batch_scope)
                if expected_paths and self.llm_service and deliverables_contract:
                    expected_set = {p for p in expected_paths if isinstance(p, str)}
                    expected_list = sorted(expected_set)
                    allowed_roots: List[str] = []
                    for r in ("src/research/", "tests/research/", "docs/research/", "examples/"):
                        if any(p.startswith(r) for p in expected_list):
                            allowed_roots.append(r)
                    if not allowed_roots:
                        # Expand to first-2 segments roots
                        expanded: List[str] = []
                        for p in expected_list:
                            parts = p.split("/")
                            # For root-level files (no "/"), include the file itself
                            if len(parts) == 1:
                                root = p
                            # If second segment contains '.', it's likely a filename, use first dir
                            elif len(parts) >= 2 and "." in parts[1]:
                                root = parts[0] + "/"
                            else:
                                root = "/".join(parts[:2]) + "/"
                            if root not in expanded:
                                expanded.append(root)
                        allowed_roots = expanded

                    ok_manifest, manifest_paths, manifest_error, _raw = (
                        self.llm_service.generate_deliverables_manifest(
                            expected_paths=list(expected_set),
                            allowed_roots=allowed_roots,
                            run_id=self.run_id,
                            phase_id=phase_id,
                            attempt_index=attempt_index,
                        )
                    )
                    if not ok_manifest:
                        err_details = manifest_error or "deliverables manifest gate failed"
                        logger.error(
                            f"[{phase_id}] Deliverables manifest gate FAILED (batch {idx}): {err_details}"
                        )
                        self._record_phase_error(
                            phase, "deliverables_manifest_failed", err_details, attempt_index
                        )
                        self._record_learning_hint(
                            phase, "deliverables_manifest_failed", err_details
                        )
                        return False, "DELIVERABLES_VALIDATION_FAILED"
                    logger.info(
                        f"[{phase_id}] Deliverables manifest gate PASSED (batch {idx}, {len(manifest_paths or [])} paths)"
                    )
                    phase_with_constraints["deliverables_manifest"] = manifest_paths or []
            except Exception as e:
                logger.warning(
                    f"[{phase_id}] Deliverables manifest gate error (batch {idx}, skipping gate): {e}"
                )

            # Run Builder for this batch
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase_with_constraints,
                file_context=file_context,
                max_tokens=None,
                project_rules=project_rules,
                run_hints=run_hints,
                run_id=self.run_id,
                phase_id=phase_id,
                run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
                attempt_index=attempt_index,
                use_full_file_mode=use_full_file_mode,
                config=self.builder_output_config,
                retrieved_context=retrieved_context,
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed (batch {idx}): {builder_result.error}")
                self._post_builder_result(phase_id, builder_result, allowed_paths)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            last_builder_result = builder_result
            total_tokens += int(getattr(builder_result, "tokens_used", 0) or 0)
            logger.info(
                f"[{phase_id}] Builder succeeded (batch {idx}, {builder_result.tokens_used} tokens)"
            )

            # Deliverables validation for this batch
            scope_config = dict(batch_scope)
            if manifest_paths:
                scope_config["deliverables_manifest"] = manifest_paths
            is_valid, validation_errors, validation_details = validate_deliverables(
                patch_content=builder_result.patch_content or "",
                phase_scope=scope_config,
                phase_id=phase_id,
                workspace=Path(self.workspace),
            )
            if not is_valid:
                feedback = format_validation_feedback_for_builder(
                    errors=validation_errors,
                    details=validation_details,
                    phase_description=phase.get("description", ""),
                )
                logger.error(f"[{phase_id}] Deliverables validation failed (batch {idx})")
                logger.error(f"[{phase_id}] {feedback}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", feedback],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Deliverables validation failed",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Structural validation for new files (headers + hunks + content where applicable)
            expected_paths = extract_deliverables_from_scope(scope_config or {})
            ok_struct, struct_errors, struct_details = (
                validate_new_file_diffs_have_complete_structure(
                    patch_content=builder_result.patch_content or "",
                    expected_paths=expected_paths,
                    workspace=Path(self.workspace),
                    allow_empty_suffixes=["__init__.py", ".gitkeep"],
                )
            )
            if not ok_struct:
                logger.error(f"[{phase_id}] Patch format invalid for new file diffs (batch {idx})")
                for e in struct_errors[:10]:
                    logger.error(f"[{phase_id}]    {e}")
                feedback_lines = [
                    "❌ PATCH FORMAT ERROR (NEW FILE DIFFS)",
                    "",
                    "For EVERY new file deliverable, your patch MUST include:",
                    "- `--- /dev/null` and `+++ b/<path>` headers",
                    "- at least one `@@ ... @@` hunk header",
                    "- `+` content lines for the file body (do not emit header-only diffs)",
                    "",
                ]
                for p in (struct_details.get("missing_headers", []) or [])[:10]:
                    feedback_lines.append(f"- Missing headers: {p}")
                for p in (struct_details.get("missing_hunks", []) or [])[:10]:
                    feedback_lines.append(f"- Missing hunks: {p}")
                for p in (struct_details.get("empty_content", []) or [])[:10]:
                    feedback_lines.append(f"- Empty content: {p}")
                fail_result = BuilderResult(
                    success=False,
                    patch_content="",
                    builder_messages=["DELIVERABLES_VALIDATION_FAILED", "\n".join(feedback_lines)],
                    tokens_used=builder_result.tokens_used,
                    model_used=getattr(builder_result, "model_used", None),
                    error="Patch format invalid for new file diffs (missing headers/hunks/content)",
                )
                self._post_builder_result(phase_id, fail_result, allowed_paths)
                return False, "DELIVERABLES_VALIDATION_FAILED"

            # Apply patch for this batch
            from autopack.governed_apply import GovernedApplyPath

            # Derive scope_paths and allowed_paths for governed apply from this batch scope
            scope_paths = batch_scope.get("paths", []) if isinstance(batch_scope, dict) else []
            derived_allowed: List[str] = []
            for r in ("src/research/", "tests/research/", "docs/research/"):
                if any(p.startswith(r) for p in expected_paths):
                    derived_allowed.append(r)
            if not derived_allowed:
                derived_allowed = allowed_paths or []

            governed_apply = GovernedApplyPath(
                workspace=Path(self.workspace),
                run_type=self.run_type,
                autopack_internal_mode=self.run_type
                in ["autopack_maintenance", "autopack_upgrade", "self_repair"],
                scope_paths=scope_paths,
                allowed_paths=derived_allowed or None,
            )
            patch_success, error_msg = governed_apply.apply_patch(
                builder_result.patch_content, full_file_mode=True
            )
            if not patch_success:
                logger.error(f"[{phase_id}] Failed to apply patch (batch {idx}): {error_msg}")
                self._update_phase_status(phase_id, "FAILED")
                return False, "PATCH_FAILED"
            logger.info(f"[{phase_id}] Patch applied successfully (batch {idx})")

            # Refresh context so next batch sees created files
            try:
                file_context = self._load_repository_context(phase_for_batch)
            except Exception as e:
                logger.warning(f"[{phase_id}] Context refresh failed after batch {idx}: {e}")

        # Build combined patch for auditor/quality gate
        combined_patch = ""
        try:
            proc = subprocess.run(
                ["git", "diff", "--no-color"],
                cwd=str(self.workspace),
                capture_output=True,
                text=True,
            )
            combined_patch = proc.stdout or ""
        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to compute combined patch after batching: {e}")

        # Post a single combined builder result to API for phase-level visibility
        combined_result = BuilderResult(
            success=True,
            patch_content=combined_patch
            or (last_builder_result.patch_content if last_builder_result else ""),
            builder_messages=[f"batched_chunk2b: {len(batches)} batches applied"],
            tokens_used=total_tokens,
            model_used=(
                getattr(last_builder_result, "model_used", None) if last_builder_result else None
            ),
            error=None,
        )
        self._post_builder_result(phase_id, combined_result, allowed_paths)

        # Proceed with normal CI/Auditor/Quality Gate using the combined patch content
        logger.info(f"[{phase_id}] Step 3/5: Running CI checks...")
        ci_result = self._run_ci_checks(phase_id, phase)

        logger.info(f"[{phase_id}] Step 4/5: Reviewing patch with Auditor (via LlmService)...")
        auditor_result = self.llm_service.execute_auditor_review(
            patch_content=combined_result.patch_content,
            phase_spec=phase,
            max_tokens=None,
            project_rules=project_rules,
            run_hints=run_hints,
            run_id=self.run_id,
            phase_id=phase_id,
            run_context=self._build_run_context(),  # [Phase C3] Include model overrides if specified
            ci_result=ci_result,
            coverage_delta=0.0,
            attempt_index=attempt_index,
        )
        logger.info(
            f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, issues={len(auditor_result.issues_found)}"
        )
        self._post_auditor_result(phase_id, auditor_result)

        logger.info(f"[{phase_id}] Step 5/5: Applying Quality Gate...")
        quality_report = self.quality_gate.assess_phase(
            phase_id=phase_id,
            phase_spec=phase,
            auditor_result={
                "approved": auditor_result.approved,
                "issues_found": auditor_result.issues_found,
            },
            ci_result=ci_result,
            coverage_delta=0.0,
            patch_content=combined_result.patch_content,
            files_changed=None,
        )
        logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")
        if quality_report.is_blocked():
            logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
            for issue in quality_report.issues:
                logger.warning(f"  - {issue}")
            self._update_phase_status(phase_id, "BLOCKED")
            return False, "BLOCKED"

        self._update_phase_status(phase_id, "COMPLETE")
        logger.info(f"[{phase_id}] Phase completed successfully (batched)")
        return True, "COMPLETE"

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
        import subprocess
        import re

        # NEW: Phase 2 - Smart context reduction for known phase patterns
        # This reduces input token usage and gives more room for output tokens
        phase_id = phase.get("phase_id", "")
        phase_name = phase.get("name", "").lower()
        phase_desc = phase.get("description", "").lower()
        task_category = phase.get("task_category", "")

        # Scope MUST take precedence over targeted context.
        # Otherwise targeted loaders can pull in root-level files (package.json, vite.config.ts, etc.)
        # while scope expects a subproject prefix (e.g., fileorganizer/frontend/*), causing immediate
        # scope validation failures before Builder runs.
        scope_config = phase.get("scope")
        if scope_config and scope_config.get("paths"):
            logger.info(f"[{phase_id}] Using scope-aware context (overrides targeted context)")
            return self._load_scoped_context(phase, scope_config)

        # Pattern 1: Country template phases (UK, CA, AU templates)
        if "template" in phase_name and ("country" in phase_desc or "template" in phase_id):
            logger.info(f"[{phase_id}] Using targeted context for country template phase")
            return self._load_targeted_context_for_templates(phase)

        # Pattern 2: Frontend-only phases
        if task_category == "frontend" or "frontend" in phase_name:
            logger.info(f"[{phase_id}] Using targeted context for frontend phase")
            return self._load_targeted_context_for_frontend(phase)

        # Pattern 3: Docker/deployment phases
        if "docker" in phase_name or task_category == "deployment":
            logger.info(f"[{phase_id}] Using targeted context for docker/deployment phase")
            return self._load_targeted_context_for_docker(phase)

        # Fallback: Original heuristic-based loading for backward compatibility
        workspace = Path(self.workspace)
        loaded_paths = set()  # Track loaded paths to avoid duplicates
        existing_files = {}  # Final output format
        max_files = 40  # Increased limit to accommodate recently modified files

        # BUILD-043: Token-aware context loading
        # Target: Keep input context under 20K tokens to leave room for output
        TARGET_INPUT_TOKENS = 20000
        current_token_estimate = 0

        def _estimate_file_tokens(content: str) -> int:
            """Estimate token count for file content (~4 chars per token)"""
            return len(content) // 4

        def _load_file(filepath: Path) -> bool:
            """Load a single file if not already loaded. Returns True if loaded."""
            nonlocal current_token_estimate

            if len(existing_files) >= max_files:
                return False

            # BUILD-043: Check token budget before loading
            rel_path = str(filepath.relative_to(workspace))
            if rel_path in loaded_paths:
                return False
            if not filepath.exists() or not filepath.is_file():
                return False
            if "__pycache__" in rel_path or ".pyc" in rel_path:
                return False

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
                content_trimmed = content[:15000]  # Increased limit for important files

                # BUILD-043: Check if adding this file would exceed token budget
                file_tokens = _estimate_file_tokens(content_trimmed)
                if current_token_estimate + file_tokens > TARGET_INPUT_TOKENS:
                    logger.debug(
                        f"[Context] Skipping {rel_path} - would exceed token budget ({current_token_estimate + file_tokens} > {TARGET_INPUT_TOKENS})"
                    )
                    return False

                existing_files[rel_path] = content_trimmed
                loaded_paths.add(rel_path)
                current_token_estimate += file_tokens
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
                timeout=10,
            )
            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if line and len(line) > 3:
                        # Parse git status format: "XY filename" or "XY old -> new"
                        file_part = line[3:].strip()
                        if " -> " in file_part:
                            file_part = file_part.split(" -> ")[1]
                        if file_part:
                            recently_modified.append(file_part)
        except Exception as e:
            logger.debug(f"Could not get git status for fresh context: {e}")

        # Load recently modified files first (highest priority for freshness)
        modified_count = 0
        for rel_path in recently_modified[:15]:  # Limit to 15 recently modified files
            # Defensive check: ensure rel_path is a string
            if not isinstance(rel_path, str):
                logger.warning(
                    f"[Context] Skipping non-string rel_path: {rel_path} (type: {type(rel_path)})"
                )
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
            logger.info(
                f"[Context] Loaded {modified_count} recently modified files for fresh context"
            )

        # Priority 1: Files mentioned in phase description
        # Extract file paths from description using regex
        phase_description = phase.get("description", "")
        phase_criteria = " ".join(phase.get("acceptance_criteria", []))
        combined_text = f"{phase_description} {phase_criteria}"

        # Match patterns like: src/autopack/file.py, config/models.yaml, etc.
        # Use non-capturing group (?:...) to get full match, not just extension
        file_patterns = re.findall(
            r"[a-zA-Z_][a-zA-Z0-9_/\\.-]*\.(?:py|yaml|json|ts|js|md)", combined_text
        )
        mentioned_count = 0
        for pattern in file_patterns[:10]:  # Limit to 10 mentioned files
            # Defensive check: ensure pattern is a string
            if not isinstance(pattern, str):
                logger.warning(
                    f"[Context] Skipping non-string pattern: {pattern} (type: {type(pattern)})"
                )
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
            ".gitignore",
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

        # BUILD-043: Log token budget usage
        logger.info(
            f"[Context] Total: {len(existing_files)} files loaded for Builder context "
            f"(modified={modified_count}, mentioned={mentioned_count})"
        )
        logger.info(
            f"[TOKEN_BUDGET] Context loading: ~{current_token_estimate} tokens "
            f"({current_token_estimate * 100 // TARGET_INPUT_TOKENS}% of {TARGET_INPUT_TOKENS} budget)"
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
        """Load context using scope configuration (GPT recommendation).

        BUILD-145 P1: Artifact-first context loading for token efficiency.
        For read_only_context, prefers loading run artifacts (.autonomous_runs/<run_id>/)
        over full file contents when available, reducing token usage.

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

        # BUILD-145 P1: Initialize artifact loader for token-efficient context loading
        from autopack.artifact_loader import ArtifactLoader

        # Use executor's run_id (always available) instead of phase.get("run_id")
        artifact_loader = ArtifactLoader(base_workspace, self.run_id) if self.run_id else None
        total_tokens_saved = 0
        artifact_substitutions = 0

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
                # Path doesn't exist yet - compute proper relative key using same logic as _resolve_scope_target
                # to prevent fileorganizer/fileorganizer/... duplicate paths
                path_obj = Path(scoped_path.strip())
                if path_obj.is_absolute():
                    try:
                        rel_key = str(path_obj.relative_to(base_workspace)).replace("\\", "/")
                    except ValueError:
                        # Absolute path outside workspace - skip
                        continue
                else:
                    # Try relative to workspace_root first, then base_workspace
                    candidate = workspace_root / path_obj
                    try:
                        rel_key = str(candidate.resolve().relative_to(base_workspace)).replace(
                            "\\", "/"
                        )
                    except ValueError:
                        # Fall back to treating as relative to base_workspace
                        rel_key = str(path_obj).replace("\\", "/")

                rel_key = _normalize_rel_path(rel_key)
                missing_files.append(rel_key)  # Store normalized rel_key, not scoped_path
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
            elif abs_path.is_dir():
                # Load a bounded set of files from the directory to avoid empty context
                allowed_exts_mod = {
                    ".py",
                    ".pyi",
                    ".txt",
                    ".md",
                    ".json",
                    ".yaml",
                    ".yml",
                    ".ini",
                    ".cfg",
                    ".conf",
                    ".env",
                    ".csv",
                    ".ts",
                    ".tsx",
                    ".js",
                    ".jsx",
                    ".vue",
                    ".css",
                    ".scss",
                }
                dir_limit = 200
                loaded_dir = 0
                for file_path in abs_path.rglob("*"):
                    if loaded_dir >= dir_limit:
                        logger.warning("[Scope] Modifiable dir limit reached (200 files).")
                        break
                    if not file_path.is_file():
                        continue
                    if file_path.suffix.lower() not in allowed_exts_mod:
                        continue
                    rel_sub = _normalize_rel_path(
                        str(file_path.relative_to(base_workspace)).replace("\\", "/")
                    )
                    _add_file(file_path, rel_sub)
                    loaded_dir += 1
            else:
                logger.warning(f"[Scope] Path is not a file: {abs_path}")

        # Load read-only context (limited set of extensions)
        allowed_exts = {
            ".py",
            ".pyi",
            ".txt",
            ".md",
            ".json",
            ".yaml",
            ".yml",
            ".ini",
            ".cfg",
            ".conf",
            ".env",
            ".csv",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".vue",
            ".css",
            ".scss",
        }
        denylist_dirs = {".venv", "venv", "node_modules", "dist", "build", "__pycache__"}
        max_readonly_files = 200
        readonly_count = 0

        for readonly_entry in scope_config.get("read_only_context", []):
            # BUILD-145: Normalize read_only_context entry to support both formats:
            # - Legacy: ["path/to/file.py", ...]
            # - New: [{"path": "path/to/file.py", "reason": "..."}, ...]
            if isinstance(readonly_entry, dict):
                readonly_path = readonly_entry.get("path")
                readonly_reason = readonly_entry.get("reason", "")
                if not readonly_path:
                    logger.warning(
                        f"[Scope] Skipping invalid read_only_context entry (missing 'path'): {readonly_entry}"
                    )
                    continue
                if readonly_reason:
                    logger.debug(
                        f"[Scope] Read-only context: {readonly_path} (reason: {readonly_reason})"
                    )
            elif isinstance(readonly_entry, str):
                readonly_path = readonly_entry
            else:
                logger.warning(
                    f"[Scope] Skipping invalid read_only_context entry (expected str or dict): {type(readonly_entry).__name__}"
                )
                continue

            resolved = self._resolve_scope_target(readonly_path, workspace_root, must_exist=False)
            if not resolved:
                continue
            abs_path, rel_key = resolved
            rel_key = _normalize_rel_path(rel_key)

            if abs_path.is_file():
                if rel_key not in existing_files:
                    # BUILD-145 P1: Try artifact-first loading for read-only context
                    if artifact_loader:
                        try:
                            full_content = abs_path.read_text(encoding="utf-8", errors="ignore")
                            content, tokens_saved, source_type = (
                                artifact_loader.load_with_artifacts(
                                    rel_key, full_content, prefer_artifacts=True
                                )
                            )
                            existing_files[rel_key] = content

                            if tokens_saved > 0:
                                total_tokens_saved += tokens_saved
                                artifact_substitutions += 1
                                scope_metadata.setdefault(rel_key, {})
                                scope_metadata[rel_key].update(
                                    {
                                        "category": "read_only",
                                        "missing": False,
                                        "source": source_type,
                                        "tokens_saved": tokens_saved,
                                    }
                                )
                            else:
                                scope_metadata.setdefault(
                                    rel_key, {"category": "read_only", "missing": False}
                                )
                        except Exception as exc:
                            logger.warning(
                                f"[Scope] Artifact loading failed for {rel_key}, using full file: {exc}"
                            )
                            _add_file(abs_path, rel_key)
                            scope_metadata.setdefault(
                                rel_key, {"category": "read_only", "missing": False}
                            )
                    else:
                        _add_file(abs_path, rel_key)
                        scope_metadata.setdefault(
                            rel_key, {"category": "read_only", "missing": False}
                        )
                else:
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
                    rel_builder = str(file_path.resolve().relative_to(base_workspace)).replace(
                        "\\", "/"
                    )
                except ValueError:
                    continue
                if rel_builder in existing_files:
                    continue
                _add_file(file_path, rel_builder)
                scope_metadata.setdefault(rel_builder, {"category": "read_only", "missing": False})
                readonly_count += 1

        if missing_files:
            logger.warning(f"[Scope] Missing scope files: {missing_files}")
            # Auto-create empty stubs for common manifest/lockfiles to reduce churn and truncation
            for missing in list(missing_files):
                if missing.endswith(("package-lock.json", "yarn.lock")):
                    # missing is already a normalized relative path from base_workspace
                    missing_path = (base_workspace / missing).resolve()
                    missing_path.parent.mkdir(parents=True, exist_ok=True)
                    missing_path.write_text("{}", encoding="utf-8")
                    logger.info(f"[Scope] Created stub for missing file: {missing}")
                    _add_file(missing_path, missing.replace("\\", "/"))
                    scope_metadata.setdefault(
                        missing.replace("\\", "/"), {"category": "modifiable", "missing": False}
                    )
                    set(existing_files.keys())
                    if missing in missing_files:
                        missing_files.remove(missing)

        logger.info(f"[Scope] Loaded {len(existing_files)} files from scope configuration")
        logger.info(f"[Scope] Scope paths: {scope_config.get('paths', [])}")
        preview_paths = list(existing_files.keys())[:10]
        logger.info(f"[Scope] Loaded paths: {preview_paths}...")

        # BUILD-145 P1: Report artifact-first loading token savings
        if artifact_substitutions > 0:
            logger.info(
                f"[Scope] Artifact-first loading: {artifact_substitutions} files substituted, "
                f"~{total_tokens_saved:,} tokens saved"
            )

        # BUILD-145 P1.1: Apply context budgeting to loaded files
        from autopack.context_budgeter import select_files_for_context, reset_embedding_cache
        from autopack.config import settings

        # BUILD-145 P1 (hardening): Reset embedding cache per phase to enforce per-phase cap
        reset_embedding_cache()

        budget_selection = select_files_for_context(
            files=existing_files,
            scope_metadata=scope_metadata,
            deliverables=phase.get("deliverables", []),
            query=phase.get("description", ""),
            budget_tokens=settings.context_budget_tokens,
        )

        # Replace existing_files with budgeted selection
        existing_files = budget_selection.kept
        logger.info(
            f"[Context Budget] Mode: {budget_selection.mode}, "
            f"Used: {budget_selection.used_tokens_est}/{budget_selection.budget_tokens} tokens, "
            f"Files: {budget_selection.files_kept_count} kept, {budget_selection.files_omitted_count} omitted"
        )

        # BUILD-145 P1 (hardening): Recompute artifact stats for kept files only
        # Original artifact_stats were computed before budgeting, so some substituted files may have been omitted
        kept_artifact_substitutions = 0
        kept_tokens_saved = 0
        substituted_paths_sample = []
        kept_files = set(existing_files.keys())

        for path, metadata in scope_metadata.items():
            if path in kept_files and metadata.get("source", "").startswith("artifact:"):
                kept_artifact_substitutions += 1
                kept_tokens_saved += metadata.get("tokens_saved", 0)
                if len(substituted_paths_sample) < 10:
                    substituted_paths_sample.append(path)

        return {
            "existing_files": existing_files,
            "scope_metadata": scope_metadata,
            "missing_scope_files": missing_files,
            "artifact_stats": (
                {
                    "substitutions": kept_artifact_substitutions,
                    "tokens_saved": kept_tokens_saved,
                    "substituted_paths_sample": substituted_paths_sample,
                }
                if kept_artifact_substitutions > 0
                else None
            ),
            "budget_selection": budget_selection,  # Store for telemetry
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
        phase.get("phase_id")
        scope_paths = scope_config.get("paths", [])
        loaded_files = set(file_context.get("existing_files", {}).keys())

        workspace_root = self._determine_workspace_root(scope_config)
        normalized_scope: List[str] = []
        scope_dir_prefixes: List[str] = []
        for path_str in scope_paths:
            resolved = self._resolve_scope_target(path_str, workspace_root, must_exist=False)
            if resolved:
                abs_path, rel_key = resolved
                normalized_scope.append(rel_key)
                # If scope entry is a directory, treat all children as in-scope
                if abs_path.exists() and abs_path.is_dir():
                    prefix = rel_key if rel_key.endswith("/") else f"{rel_key}/"
                    scope_dir_prefixes.append(prefix)
            else:
                norm = path_str.replace("\\", "/")
                normalized_scope.append(norm)
                if norm.endswith("/"):
                    scope_dir_prefixes.append(norm)

        # Check for files outside scope (indicating scope loading bug)
        scope_set = set(normalized_scope)

        def _is_in_scope(file_path: str) -> bool:
            if file_path in scope_set:
                return True
            # Allow directory scope entries as prefixes
            if any(file_path.startswith(prefix) for prefix in scope_dir_prefixes):
                return True
            return False

        outside_scope = {f for f in loaded_files if not _is_in_scope(f)}

        if outside_scope:
            readonly_context = scope_config.get("read_only_context", [])
            readonly_exact: Set[str] = set()
            readonly_prefixes: List[str] = []

            for entry in readonly_context:
                # BUILD-145 P0: Handle both dict and legacy string format
                if isinstance(entry, dict):
                    path_str = entry.get("path", "")
                else:
                    path_str = entry

                if not path_str:
                    continue

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
                raise RuntimeError("Scope validation failed: loaded files outside scope.paths")

        logger.info(
            f"[Scope] Validation passed: {len(loaded_files)} files match scope configuration"
        )

    def _post_builder_result(
        self, phase_id: str, result: BuilderResult, allowed_paths: Optional[List[str]] = None
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
        is_maintenance_run = self.run_type in [
            "autopack_maintenance",
            "autopack_upgrade",
            "self_repair",
        ]
        governed_apply = GovernedApplyPath(
            workspace=Path(self.workspace),
            run_type=self.run_type,
            autopack_internal_mode=is_maintenance_run,
        )
        files_changed, lines_added, lines_removed = governed_apply.parse_patch_stats(
            result.patch_content or ""
        )

        # P1.2: Emit canonical BuilderResult payload matching builder_schemas.py
        # Use lowercase status vocabulary and top-level fields (no metadata wrapper)
        payload = {
            "phase_id": phase_id,
            "run_id": self.run_id,
            "run_type": self.run_type,
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
                    response = requests.post(url, headers=headers, json=payload, timeout=10)

                    # Phase 2.3: Handle 422 validation errors separately
                    if response.status_code == 422:
                        error_detail = response.json().get("detail", "Patch validation failed")
                        logger.error(f"[{phase_id}] Patch validation failed (422): {error_detail}")
                        logger.info(
                            f"[{phase_id}] Phase 2.3: Validation errors indicate malformed patch - LLM should regenerate"
                        )

                        # Log validation failures to debug journal
                        log_error(
                            error_signature="Patch validation failure (422)",
                            symptom=f"Phase {phase_id}: {error_detail}",
                            run_id=self.run_id,
                            phase_id=phase_id,
                            suspected_cause="LLM generated malformed patch - needs regeneration",
                            priority="MEDIUM",
                        )

                        # TODO: Implement automatic retry with LLM correction
                        response.raise_for_status()

                    response.raise_for_status()
                    logger.debug(f"Posted builder result for phase {phase_id}")
                    break
                except requests.exceptions.RequestException as e_inner:
                    status_code = getattr(getattr(e_inner, "response", None), "status_code", None)
                    if status_code and status_code >= 500:
                        self._run_http_500_count += 1
                        logger.warning(
                            f"[{phase_id}] HTTP 500 count this run: {self._run_http_500_count}/{self.MAX_HTTP_500_PER_RUN}"
                        )
                        if attempt < 2:
                            backoff = 1 * (2**attempt)
                            logger.info(
                                f"[{phase_id}] Retrying builder_result POST after {backoff}s (attempt {attempt+2}/3)"
                            )
                            time.sleep(backoff)
                            continue
                        if self._run_http_500_count >= self.MAX_HTTP_500_PER_RUN:
                            logger.error(
                                f"[{phase_id}] HTTP 500 budget exceeded for run {self.run_id}; consider aborting run."
                            )
                    # Non-retryable or retries exhausted
                    raise
        except requests.exceptions.RequestException as e:
            status_code = getattr(getattr(e, "response", None), "status_code", None)
            if status_code and status_code >= 500:
                self._run_http_500_count += 1
                logger.warning(
                    f"[{phase_id}] HTTP 500 count this run: {self._run_http_500_count}/{self.MAX_HTTP_500_PER_RUN}"
                )
            if (
                status_code
                and status_code >= 500
                and self._run_http_500_count >= self.MAX_HTTP_500_PER_RUN
            ):
                logger.error(
                    f"[{phase_id}] HTTP 500 budget exceeded for run {self.run_id}; consider aborting run."
                )
            logger.warning(f"Failed to post builder result: {e}")

            # Log API failures to debug journal
            log_error(
                error_signature="API failure: POST builder_result",
                symptom=f"Phase {phase_id}: {type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="API communication failure or server error",
                priority="MEDIUM",
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
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            if response.status_code == 422:
                # Backwards compatibility: some backend deployments still (incorrectly) expect BuilderResultRequest
                # at the auditor_result endpoint, requiring a "success" field.
                #
                # If we see this schema-mismatch signature, retry with a minimal BuilderResultRequest wrapper.
                try:
                    detail = response.json().get("detail")
                except Exception:
                    detail = None
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
                    response2 = requests.post(url, headers=headers, json=fallback, timeout=10)
                    response2.raise_for_status()
                    logger.debug(f"Posted auditor result for phase {phase_id} (compat retry)")
                    return

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
                priority="MEDIUM",
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

    def _should_include_sot_retrieval(
        self, max_context_chars: int, phase_id: Optional[str] = None
    ) -> bool:
        """Budget-aware gating for SOT retrieval.

        Args:
            max_context_chars: Total context budget allocated for this retrieval

        Returns:
            True if SOT retrieval should be included based on budget availability

        Notes:
            - SOT retrieval is only included if globally enabled AND budget allows
            - Budget check: max_context_chars >= (sot_budget + 2000)
            - The 2000-char reserve ensures room for other context sections
            - See docs/SOT_MEMORY_INTEGRATION_EXAMPLE.md for integration pattern
        """
        from autopack.config import settings

        phase_prefix = f"[{phase_id}] " if phase_id else ""

        # Global kill switch
        if not settings.autopack_sot_retrieval_enabled:
            logger.info(
                f"{phase_prefix}[SOT] Retrieval disabled by config (autopack_sot_retrieval_enabled=false)"
            )
            return False

        # Budget gating: ensure we have enough headroom for SOT + other context
        sot_budget = settings.autopack_sot_retrieval_max_chars  # Default: 4000
        min_required_budget = sot_budget + 2000  # Reserve 2K for non-SOT context

        if max_context_chars < min_required_budget:
            logger.info(
                f"{phase_prefix}[SOT] Skipping retrieval - insufficient budget "
                f"(available: {max_context_chars}, needs: {min_required_budget}, "
                f"sot_cap={sot_budget}, reserve=2000)"
            )
            return False

        logger.info(
            f"{phase_prefix}[SOT] Including retrieval (budget: {max_context_chars}, "
            f"sot_cap={sot_budget}, top_k={settings.autopack_sot_retrieval_top_k})"
        )
        return True

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
        logger.info(f"[{phase_id}] Running CI checks (pytest)...")

        workdir = Path(self.workspace) / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = Path(self.workspace)

        pytest_paths = ci_spec.get("paths")
        if not pytest_paths:
            project_slug = self._get_project_slug()
            if project_slug == "file-organizer-app-v1":
                candidate_paths = [
                    "fileorganizer/backend/tests/",
                    "src/backend/tests/",
                    "tests/backend/",
                ]
            else:
                candidate_paths = ["tests/"]

            for path in candidate_paths:
                if (workdir / path).exists():
                    pytest_paths = [path]
                    break

        if not pytest_paths:
            logger.warning(f"[{phase_id}] No pytest paths found, skipping CI checks")
            return {
                "status": "skipped",
                "message": "No pytest paths found",
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

        per_test_timeout = ci_spec.get("per_test_timeout", 60)
        default_args = [
            "-v",
            "--tb=line",
            "-q",
            "--no-header",
            f"--timeout={per_test_timeout}",
        ]
        pytest_args = ci_spec.get("args", [])
        # BUILD-127: Emit a structured pytest JSON report so PhaseFinalizer/TestBaselineTracker can
        # compute regressions safely. We still persist a full text log for humans.
        ci_dir = Path(self.workspace) / ".autonomous_runs" / self.run_id / "ci"
        ci_dir.mkdir(parents=True, exist_ok=True)
        json_report_path = ci_dir / ci_spec.get("json_report_name", f"pytest_{phase_id}.json")

        cmd = [sys.executable, "-m", "pytest", *pytest_paths, *default_args, *pytest_args]
        if "--json-report" not in cmd:
            cmd.append("--json-report")
        if not any(str(a).startswith("--json-report-file=") for a in cmd):
            cmd.append(f"--json-report-file={json_report_path}")

        env = os.environ.copy()
        env.setdefault("PYTHONPATH", str(workdir / "src"))
        env["TESTING"] = "1"
        env["PYTHONUTF8"] = "1"
        env.update(ci_spec.get("env", {}))

        timeout_seconds = ci_spec.get("timeout_seconds") or ci_spec.get("timeout") or 300
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"[{phase_id}] Pytest timeout after {duration:.1f}s")
            return {
                "status": "failed",
                "message": f"pytest timed out after {timeout_seconds}s",
                "passed": False,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": round(duration, 2),
                "output": "",
                "error": f"pytest timed out after {timeout_seconds}s",
                "skipped": False,
                "suspicious_zero_tests": False,
            }

        duration = time.time() - start_time
        output = self._trim_ci_output(result.stdout + result.stderr)
        tests_passed, tests_failed, tests_error = self._parse_pytest_counts(output)
        tests_run = tests_passed + tests_failed + tests_error
        passed = result.returncode == 0
        no_tests_detected = tests_run == 0

        error_msg = None
        if no_tests_detected and not passed:
            error_msg = "Possible collection error - no tests detected"
        elif no_tests_detected and passed:
            error_msg = "Warning: pytest reported success but no tests executed"

        # Always persist a CI log so downstream components (dashboard/humans) have a stable artifact.
        full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
        log_name = ci_spec.get("log_name", f"pytest_{phase_id}.log")
        log_path = self._persist_ci_log(log_name, full_output, phase_id)

        # Prefer structured JSON report for automated delta computation. Fall back to the log if missing.
        report_path: Optional[Path] = None
        try:
            if json_report_path.exists() and json_report_path.stat().st_size > 0:
                report_path = json_report_path
        except Exception:
            report_path = None
        if report_path is None:
            report_path = log_path

        if not passed and not error_msg:
            error_msg = f"pytest exited with code {result.returncode}"

        message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
        if not message:
            if passed:
                message = f"Pytest passed ({tests_passed}/{max(tests_run,1)} tests)"
            else:
                message = error_msg or "Pytest failed"

        if passed:
            logger.info(
                f"[{phase_id}] CI checks PASSED: {tests_passed}/{max(tests_run,1)} tests passed in {duration:.1f}s"
            )
        else:
            logger.warning(f"[{phase_id}] CI checks FAILED: return code {result.returncode}")

        # Extract collector error digest for phase summary and downstream components
        collector_digest = None
        if result.returncode == 2 or (no_tests_detected and not passed):
            # Exitcode 2 typically indicates collection/import errors
            # Extract digest using PhaseFinalizer's helper
            try:
                workspace_path = Path(self.workspace)
                collector_digest = self.phase_finalizer._extract_collection_error_digest(
                    {"report_path": str(report_path) if report_path else None},
                    workspace_path,
                    max_errors=5,
                )
                if collector_digest:
                    logger.warning(
                        f"[{phase_id}] Collection errors detected: {len(collector_digest)} failures"
                    )
            except Exception as e:
                logger.warning(f"[{phase_id}] Failed to extract collector digest: {e}")

        return {
            "status": "passed" if passed else "failed",
            "message": message,
            "passed": passed,
            "tests_run": tests_run,
            "tests_passed": tests_passed,
            "tests_failed": tests_failed,
            "tests_error": tests_error,
            "duration_seconds": round(duration, 2),
            "output": output,
            "error": error_msg,
            "report_path": str(report_path) if report_path else None,
            "log_path": str(log_path) if log_path else None,
            "skipped": False,
            "suspicious_zero_tests": no_tests_detected,
            "collector_error_digest": collector_digest,  # NEW: Collector error digest
        }

    def _run_custom_ci(self, phase_id: str, ci_spec: Dict[str, Any]) -> Dict[str, Any]:
        command = ci_spec.get("command")
        if not command:
            logger.warning(f"[{phase_id}] CI spec missing 'command'; skipping")
            return {
                "status": "skipped",
                "message": "CI command not configured",
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

        workdir = Path(self.workspace) / ci_spec.get("workdir", ".")
        if not workdir.exists():
            logger.warning(
                f"[{phase_id}] CI workdir {workdir} missing, defaulting to workspace root"
            )
            workdir = Path(self.workspace)

        timeout_seconds = ci_spec.get("timeout_seconds") or ci_spec.get("timeout") or 600
        env = os.environ.copy()
        env.update(ci_spec.get("env", {}))

        shell = ci_spec.get("shell", isinstance(command, str))
        cmd = command
        if isinstance(command, str) and not shell:
            cmd = shlex.split(command)

        logger.info(f"[{phase_id}] Running custom CI command: {command}")
        start_time = time.time()
        try:
            result = subprocess.run(
                cmd,
                cwd=str(workdir),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=env,
                shell=shell,
            )
        except subprocess.TimeoutExpired:
            duration = time.time() - start_time
            logger.error(f"[{phase_id}] CI command timeout after {duration:.1f}s")
            return {
                "status": "failed",
                "message": f"CI command timed out after {timeout_seconds}s",
                "passed": False,
                "tests_run": 0,
                "tests_passed": 0,
                "tests_failed": 0,
                "tests_error": 0,
                "duration_seconds": round(duration, 2),
                "output": "",
                "error": f"Command timed out after {timeout_seconds}s",
                "skipped": False,
                "suspicious_zero_tests": False,
            }

        duration = time.time() - start_time
        output = self._trim_ci_output(result.stdout + result.stderr)
        passed = result.returncode == 0

        # Always persist a CI log so downstream components have a stable report_path.
        full_output = result.stdout + "\n\n--- STDERR ---\n\n" + result.stderr
        log_name = ci_spec.get("log_name", f"ci_{phase_id}.log")
        report_path = self._persist_ci_log(log_name, full_output, phase_id)

        message = ci_spec.get("success_message") if passed else ci_spec.get("failure_message")
        if not message:
            message = (
                "CI command succeeded"
                if passed
                else f"CI command failed (exit {result.returncode})"
            )

        if passed:
            logger.info(f"[{phase_id}] Custom CI command passed in {duration:.1f}s")
        else:
            logger.warning(f"[{phase_id}] Custom CI command failed (exit {result.returncode})")

        return {
            "status": "passed" if passed else "failed",
            "message": message,
            "passed": passed,
            "tests_run": 0,
            "tests_passed": 0,
            "tests_failed": 0,
            "tests_error": 0,
            "duration_seconds": round(duration, 2),
            "output": output,
            "error": None if passed else f"Exit code {result.returncode}",
            "report_path": str(report_path) if report_path else None,
            "skipped": False,
            "suspicious_zero_tests": False,
        }

    def _trim_ci_output(self, output: str, limit: int = 10000) -> str:
        if len(output) <= limit:
            return output
        return output[: limit // 2] + "\n\n... (truncated) ...\n\n" + output[-limit // 2 :]

    def _persist_ci_log(self, log_name: str, content: str, phase_id: str) -> Optional[Path]:
        ci_log_dir = Path(self.workspace) / ".autonomous_runs" / self.run_id / "ci"
        ci_log_dir.mkdir(parents=True, exist_ok=True)
        log_path = ci_log_dir / log_name
        try:
            log_path.write_text(content, encoding="utf-8")
            logger.info(f"[{phase_id}] CI output written to: {log_path}")
            return log_path
        except Exception as log_err:
            logger.warning(f"[{phase_id}] Failed to write CI log ({log_name}): {log_err}")
            return None

    def _parse_pytest_counts(self, output: str) -> tuple[int, int, int]:
        import re

        tests_passed = tests_failed = tests_error = 0
        for line in output.split("\n"):
            line_lower = line.lower()
            collection_error = re.search(r"(\d+)\s+errors?\s+during\s+collection", line_lower)
            if collection_error:
                tests_error = int(collection_error.group(1))
                continue

            passed_match = re.search(r"(\d+)\s+passed", line_lower)
            if passed_match:
                tests_passed = int(passed_match.group(1))

            failed_match = re.search(r"(\d+)\s+failed", line_lower)
            if failed_match:
                tests_failed = int(failed_match.group(1))

            error_match = re.search(r"(\d+)\s+errors?(?!\s+during)", line_lower)
            if error_match:
                tests_error = int(error_match.group(1))

        return tests_passed, tests_failed, tests_error

    def _update_phase_status(self, phase_id: str, status: str):
        """Update phase status via API

        Uses the /runs/{run_id}/phases/{phase_id}/update_status endpoint.

        Args:
            phase_id: Phase ID
            status: New status (QUEUED, EXECUTING, GATE, CI_RUNNING, COMPLETE, FAILED, SKIPPED)
        """
        try:
            url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/update_status"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            # The API only accepts models.PhaseState values; "BLOCKED" is a quality-gate outcome,
            # not a phase state. Represent blocked states as FAILED (with quality_blocked set elsewhere)
            # or as GATE where appropriate.
            if status == "BLOCKED":
                status = "FAILED"

            response = requests.post(url, json={"state": status}, headers=headers, timeout=30)
            response.raise_for_status()
            logger.info(f"Updated phase {phase_id} status to {status}")
            # Best-effort run_summary rewrite when a phase reaches a terminal state
            if status in ("COMPLETE", "FAILED", "SKIPPED"):
                self._best_effort_write_run_summary()
        except requests.exceptions.RequestException as e:
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
        from autopack.governed_apply import GovernedApplyPath

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

        Sends approval request to backend API, which triggers Telegram notification.
        Polls for approval decision until timeout.

        Args:
            phase_id: Phase identifier
            quality_report: Quality gate report with risk assessment
            timeout_seconds: How long to wait for approval (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out
        """
        import time
        import requests

        logger.info(f"[{phase_id}] Requesting human approval via Telegram...")

        # Extract risk assessment from quality report
        risk_assessment = getattr(quality_report, "risk_assessment", None)
        if not risk_assessment:
            logger.warning(f"[{phase_id}] No risk assessment found in quality report")
            deletion_info = {
                "net_deletion": 0,
                "loc_removed": 0,
                "loc_added": 0,
                "files": [],
                "risk_level": "unknown",
                "risk_score": 0,
            }
        else:
            metadata = risk_assessment.get("metadata", {})
            # BUILD-190: Extract files from risk_assessment metadata or executor state
            changed_files = (
                metadata.get("files_changed", [])
                or metadata.get("files", [])
                or list(self._last_files_changed or [])
            )
            deletion_info = {
                "net_deletion": metadata.get("loc_removed", 0) - metadata.get("loc_added", 0),
                "loc_removed": metadata.get("loc_removed", 0),
                "loc_added": metadata.get("loc_added", 0),
                "files": changed_files[:10],  # Limit to 10 files for display
                "risk_level": risk_assessment.get("risk_level", "unknown"),
                "risk_score": risk_assessment.get("risk_score", 0),
            }

        # Send approval request to backend API
        try:
            url = f"{self.api_url}/approval/request"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            # BUILD-190: Derive context from phase metadata or quality report
            # Context helps operators understand the nature of the approval request
            phase_context = "general"
            if hasattr(quality_report, "phase_category"):
                phase_context = quality_report.phase_category
            elif risk_assessment and risk_assessment.get("metadata", {}).get("task_category"):
                phase_context = risk_assessment["metadata"]["task_category"]

            response = requests.post(
                url,
                json={
                    "phase_id": phase_id,
                    "deletion_info": deletion_info,
                    "run_id": self.run_id,
                    "context": phase_context,
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "rejected":
                logger.error(
                    f"[{phase_id}] Approval request rejected: {result.get('reason', 'Unknown')}"
                )
                return False

            # Check if immediately approved (auto-approve mode)
            if result.get("status") == "approved":
                logger.info(f"[{phase_id}] ✅ Approval GRANTED (auto-approved)")
                return True

            # Extract approval_id for polling
            approval_id = result.get("approval_id")
            if not approval_id:
                logger.error(f"[{phase_id}] No approval_id in response - cannot poll for status")
                return False

            logger.info(
                f"[{phase_id}] Approval request sent (approval_id={approval_id}), waiting for user decision..."
            )

        except Exception as e:
            logger.error(f"[{phase_id}] Failed to send approval request: {e}")
            # If Telegram is not configured, auto-reject
            return False

        # Poll for approval status
        elapsed = 0
        poll_interval = 10  # seconds

        while elapsed < timeout_seconds:
            try:
                url = f"{self.api_url}/approval/status/{approval_id}"
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")

                if status == "approved":
                    logger.info(f"[{phase_id}] ✅ Approval GRANTED by user")
                    return True

                if status == "rejected":
                    logger.warning(f"[{phase_id}] ❌ Approval REJECTED by user")
                    return False

                # Still pending, wait and check again
                time.sleep(poll_interval)
                elapsed += poll_interval

                if elapsed % 60 == 0:  # Log every minute
                    logger.info(
                        f"[{phase_id}] Still waiting for approval... ({elapsed}s / {timeout_seconds}s)"
                    )

            except Exception as e:
                logger.warning(f"[{phase_id}] Error checking approval status: {e}")
                time.sleep(poll_interval)
                elapsed += poll_interval

        # Timeout reached
        logger.warning(f"[{phase_id}] ⏱️  Approval timeout after {timeout_seconds}s")
        return False

    def _request_build113_approval(
        self, phase_id: str, decision, patch_content: str, timeout_seconds: int = 3600
    ) -> bool:
        """
        Request human approval for BUILD-113 RISKY decisions via Telegram.

        Sends approval request with decision details, risk assessment, and patch preview.
        Polls for approval decision until timeout.

        Args:
            phase_id: Phase identifier
            decision: BUILD-113 Decision object with risk/confidence details
            patch_content: Full patch content for preview
            timeout_seconds: How long to wait for approval (default: 1 hour)

        Returns:
            True if approved, False if rejected or timed out
        """
        import time
        import requests

        logger.info(f"[BUILD-113] Requesting human approval for RISKY decision on {phase_id}...")

        # Build approval request with BUILD-113 decision details
        try:
            url = f"{self.api_url}/approval/request"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            # Extract patch preview (first 500 chars)
            patch_preview = patch_content[:500] + ("..." if len(patch_content) > 500 else "")

            response = requests.post(
                url,
                json={
                    "phase_id": phase_id,
                    "run_id": self.run_id,
                    "context": "build113_risky_decision",
                    "decision_info": {
                        "type": decision.type.value,
                        "risk_level": decision.risk_level,
                        "confidence": f"{decision.confidence:.0%}",
                        "rationale": decision.rationale,
                        "files_modified": decision.files_modified[:5],  # First 5 files
                        "files_count": len(decision.files_modified),
                        "deliverables_met": decision.deliverables_met,
                        "net_deletion": decision.net_deletion,
                        "questions": decision.questions_for_human,
                    },
                    "patch_preview": patch_preview,
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "rejected":
                logger.error(
                    f"[BUILD-113] Approval request rejected: {result.get('reason', 'Unknown')}"
                )
                return False

            # Check if immediately approved (auto-approve mode)
            if result.get("status") == "approved":
                logger.info("[BUILD-113] ✅ RISKY patch APPROVED (auto-approved)")
                return True

            # Extract approval_id for polling
            approval_id = result.get("approval_id")
            if not approval_id:
                logger.error("[BUILD-113] No approval_id in response - cannot poll for status")
                return False

            logger.info(
                f"[BUILD-113] Approval request sent (approval_id={approval_id}), waiting for user decision..."
            )

        except Exception as e:
            logger.error(f"[BUILD-113] Failed to send approval request: {e}")
            # If Telegram is not configured, auto-reject high-risk patches
            logger.warning(
                "[BUILD-113] Defaulting to REJECT for RISKY decision without approval system"
            )
            return False

        # Poll for approval status (reuse same polling logic as regular approval)
        elapsed = 0
        poll_interval = 10  # seconds

        while elapsed < timeout_seconds:
            try:
                url = f"{self.api_url}/approval/status/{approval_id}"
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")

                if status == "approved":
                    logger.info("[BUILD-113] ✅ RISKY patch APPROVED by user")
                    return True

                if status == "rejected":
                    logger.warning("[BUILD-113] ❌ RISKY patch REJECTED by user")
                    return False

                # Still pending, wait and check again
                time.sleep(poll_interval)
                elapsed += poll_interval

                if elapsed % 60 == 0:  # Log every minute
                    logger.info(
                        f"[BUILD-113] Still waiting for approval... ({elapsed}s / {timeout_seconds}s)"
                    )

            except Exception as e:
                logger.warning(f"[BUILD-113] Error checking approval status: {e}")
                time.sleep(poll_interval)
                elapsed += poll_interval

        # Timeout reached
        logger.warning(
            f"[BUILD-113] ⏱️  Approval timeout after {timeout_seconds}s - defaulting to REJECT"
        )
        return False

    def _request_build113_clarification(
        self, phase_id: str, decision, timeout_seconds: int = 3600
    ) -> Optional[str]:
        """
        Request human clarification for BUILD-113 AMBIGUOUS decisions via Telegram.

        Sends clarification request with decision details and questions.
        Polls for human response until timeout.

        Args:
            phase_id: Phase identifier
            decision: BUILD-113 Decision object with questions
            timeout_seconds: How long to wait for clarification (default: 1 hour)

        Returns:
            Human response text if provided, None if timed out
        """
        import time
        import requests

        logger.info(
            f"[BUILD-113] Requesting human clarification for AMBIGUOUS decision on {phase_id}..."
        )

        # Build clarification request with BUILD-113 decision details
        try:
            url = f"{self.api_url}/clarification/request"
            headers = {"Content-Type": "application/json"}
            if self.api_key:
                headers["X-API-Key"] = self.api_key

            response = requests.post(
                url,
                json={
                    "phase_id": phase_id,
                    "run_id": self.run_id,
                    "context": "build113_ambiguous_decision",
                    "decision_info": {
                        "type": decision.type.value,
                        "risk_level": decision.risk_level,
                        "confidence": f"{decision.confidence:.0%}",
                        "rationale": decision.rationale,
                        "questions": decision.questions_for_human,
                        "alternatives": decision.alternatives_considered,
                    },
                },
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            result = response.json()

            if result.get("status") == "rejected":
                logger.error(
                    f"[BUILD-113] Clarification request rejected: {result.get('reason', 'Unknown')}"
                )
                return None

            logger.info("[BUILD-113] Clarification request sent, waiting for user response...")

        except Exception as e:
            logger.error(f"[BUILD-113] Failed to send clarification request: {e}")
            # If Telegram is not configured, cannot get clarification
            logger.warning(
                "[BUILD-113] No clarification system available - cannot resolve AMBIGUOUS decision"
            )
            return None

        # Poll for clarification response
        elapsed = 0
        poll_interval = 10  # seconds

        while elapsed < timeout_seconds:
            try:
                url = f"{self.api_url}/clarification/status/{phase_id}"
                headers = {}
                if self.api_key:
                    headers["X-API-Key"] = self.api_key

                response = requests.get(url, headers=headers, timeout=10)
                response.raise_for_status()
                status_data = response.json()

                status = status_data.get("status")

                if status == "answered":
                    clarification_text = status_data.get("response", "")
                    logger.info(
                        f"[BUILD-113] ✅ Clarification received: {clarification_text[:100]}..."
                    )
                    return clarification_text

                if status == "rejected":
                    logger.warning("[BUILD-113] ❌ Clarification request rejected by user")
                    return None

                # Still pending, wait and check again
                time.sleep(poll_interval)
                elapsed += poll_interval

                if elapsed % 60 == 0:  # Log every minute
                    logger.info(
                        f"[BUILD-113] Still waiting for clarification... ({elapsed}s / {timeout_seconds}s)"
                    )

            except Exception as e:
                logger.warning(f"[BUILD-113] Error checking clarification status: {e}")
                time.sleep(poll_interval)
                elapsed += poll_interval

        # Timeout reached
        logger.warning(f"[BUILD-113] ⏱️  Clarification timeout after {timeout_seconds}s")
        return None

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
        try:
            import subprocess
            from datetime import datetime

            # Generate tag name
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            tag_name = f"save-before-deletion-{phase_id}-{timestamp}"

            # Check if there are uncommitted changes
            result = subprocess.run(["git", "diff", "--quiet"], cwd=self.root, capture_output=True)

            if result.returncode != 0:
                # There are uncommitted changes - create a temporary commit first
                subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)

                commit_msg = (
                    f"[SAVE POINT] Before {phase_id} deletion ({net_deletion} lines)\n\n"
                    f"Automatic save point created by Autopack before large deletion.\n"
                    f"Phase: {phase_id}\n"
                    f"Net deletion: {net_deletion} lines\n"
                    f"Run: {self.run_id}\n\n"
                    f"To restore:\n"
                    f"  git reset --hard {tag_name}\n"
                    f"  # or\n"
                    f"  git checkout {tag_name} -- <file>\n"
                )

                subprocess.run(
                    ["git", "commit", "-m", commit_msg],
                    cwd=self.root,
                    check=True,
                    capture_output=True,
                )

            # Create lightweight tag at current HEAD
            subprocess.run(["git", "tag", tag_name], cwd=self.root, check=True, capture_output=True)

            logger.info(f"[{phase_id}] Created save point tag: {tag_name}")
            logger.info(f"[{phase_id}] To restore: git reset --hard {tag_name}")

            return tag_name

        except Exception as e:
            logger.warning(f"[{phase_id}] Failed to create save point: {e}")
            return None

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
        # Try direct database update first (more reliable than API)
        try:
            # BUILD-115: from autopack.models import Phase, PhaseState, Tier
            return None  # BUILD-115: Database query disabled

            # Expire all cached objects to get fresh data
            self.db_session.expire_all()

            phase = (
                self.db_session.query(Phase)
                .filter(Phase.phase_id == phase_id, Phase.run_id == self.run_id)
                .first()
            )

            if phase:
                phase.state = PhaseState.FAILED
                self.db_session.commit()
                # Force flush to ensure write is complete
                self.db_session.flush()
                logger.info(
                    f"[Self-Troubleshoot] Force-marked phase {phase_id} as FAILED in database"
                )
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
                # BUILD-129 Phase 3: /health should reflect DB readiness too (see src/autopack/main.py).
                # If DB is unhealthy, treat API as not usable for executor.
                try:
                    payload = response.json()
                    # Require that the service identify itself as the Autopack Supervisor API.
                    # This prevents false positives when another service is listening on the same port
                    # (e.g., src/backend FastAPI which has /health but not the supervisor API contract).
                    if payload.get("service") != "autopack":
                        logger.error(
                            "A service responded on /health but did not identify as the Autopack Supervisor API "
                            f"(service={payload.get('service')!r}). Refusing to use it."
                        )
                        return False

                    if payload.get("db_ok") is False or payload.get("status") not in (
                        None,
                        "healthy",
                    ):
                        logger.warning(
                            "API server responded to /health but reported unhealthy DB. "
                            "Executor requires a healthy API+DB; will attempt to start a local API server."
                        )
                    else:
                        logger.info("API server is already running")
                        return True
                except Exception:
                    # If health isn't JSON, treat as incompatible to avoid using the wrong service.
                    logger.error(
                        "Service responded 200 on /health but did not return JSON. Refusing to use it."
                    )
                    return False
        except Exception:
            pass  # Server not responding, continue to start it

        # Try to connect to port to see if something is listening
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                # Port is open but /health failed - likely a different service or a broken API.
                # Do NOT assume it's usable; this causes opaque 500s later.
                logger.error(
                    f"Port {port} is open but {self.api_url}/health is not healthy. "
                    "Another service may be using the port, or the API is misconfigured. "
                    "Stop the conflicting process or set AUTOPACK_API_URL to a different port."
                )
                return False
        except Exception:
            pass

        # Server not running - try to start it
        logger.info(f"API server not detected at {self.api_url}, attempting to start it...")

        try:
            # Start API server in background
            import sys
            import os
            from pathlib import Path

            # Configurable startup wait (Windows + cold start can exceed 10s).
            # Default: 30s. Override with AUTOPACK_API_STARTUP_TIMEOUT_SECONDS.
            try:
                startup_timeout_s = int(os.getenv("AUTOPACK_API_STARTUP_TIMEOUT_SECONDS", "30"))
            except Exception:
                startup_timeout_s = 30
            startup_timeout_s = max(5, min(300, startup_timeout_s))

            # Ensure the uvicorn subprocess can import `autopack.*` from `src/`.
            # NOTE: modifying sys.path in this process does NOT affect the subprocess.
            env = os.environ.copy()
            try:
                src_path = str((Path(self.workspace).resolve() / "src"))
                existing = env.get("PYTHONPATH", "")
                if src_path and (src_path not in existing.split(os.pathsep)):
                    env["PYTHONPATH"] = src_path + (os.pathsep + existing if existing else "")
            except Exception:
                pass
            env.setdefault("PYTHONUTF8", "1")

            # Capture uvicorn logs for RCA (previously discarded to DEVNULL).
            log_dir = Path(".autonomous_runs") / self.run_id / "diagnostics"
            try:
                log_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
            api_log_path = log_dir / f"api_server_{host}_{port}.log"
            log_fp = None
            try:
                log_fp = open(api_log_path, "ab")
            except Exception:
                log_fp = None
            api_cmd = [
                sys.executable,
                "-m",
                "uvicorn",
                # IMPORTANT: module path is relative to PYTHONPATH=src; 'src.autopack...' is not importable
                # because 'src/' is not a Python package (no src/__init__.py).
                "autopack.main:app",
                "--host",
                host,
                "--port",
                str(port),
            ]

            # Start process in background (detached on Windows)
            if sys.platform == "win32":
                # Windows: use CREATE_NEW_PROCESS_GROUP and DETACHED_PROCESS
                import subprocess

                process = subprocess.Popen(
                    api_cmd,
                    stdout=log_fp or subprocess.DEVNULL,
                    stderr=log_fp or subprocess.DEVNULL,
                    env=env,
                    cwd=str(Path(self.workspace).resolve()),
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS,
                )
            else:
                # Unix: use nohup-like behavior
                process = subprocess.Popen(
                    api_cmd,
                    stdout=log_fp or subprocess.DEVNULL,
                    stderr=log_fp or subprocess.DEVNULL,
                    env=env,
                    cwd=str(Path(self.workspace).resolve()),
                    start_new_session=True,
                )

            # Wait a bit for server to start
            logger.info(f"Waiting for API server to start on {host}:{port}...")
            for i in range(startup_timeout_s):  # Wait up to configured seconds
                time.sleep(1)

                # If the server process exits early, surface the log path.
                try:
                    if process.poll() is not None:
                        logger.error(
                            f"API server process exited early (code={process.returncode}). "
                            f"See log: {api_log_path}"
                        )
                        return False
                except Exception:
                    pass
                try:
                    response = requests.get(f"{self.api_url}/health", timeout=1)
                    if response.status_code == 200:
                        logger.info("✅ API server started successfully")
                        # Optional: fail fast if the API is healthy but the run is missing (common DB drift symptom).
                        if os.getenv("AUTOPACK_SKIP_RUN_EXISTENCE_CHECK") != "1":
                            try:
                                run_resp = requests.get(
                                    f"{self.api_url}/runs/{self.run_id}", timeout=2
                                )
                                if run_resp.status_code == 404:
                                    logger.error(
                                        "[DB_MISMATCH] API is healthy but run was not found. "
                                        f"run_id={self.run_id!r}. This usually means the API and executor are "
                                        "pointed at different SQLite files (cwd/relative path drift) or the run was not seeded "
                                        "into this DATABASE_URL."
                                    )
                                    # Hint: enable DEBUG_DB_IDENTITY=1 and re-check /health payload.
                                    logger.error(
                                        "Hint: set DEBUG_DB_IDENTITY=1 and re-check /health for sqlite_file + run counts."
                                    )
                                    return False
                            except Exception as _e:
                                logger.warning(f"Run existence check skipped due to error: {_e}")
                        return True
                except Exception:
                    pass
                if i < startup_timeout_s - 1:
                    logger.info(f"  Still waiting... ({i+1}/{startup_timeout_s})")

            logger.error(
                f"API server failed to start within {startup_timeout_s} seconds (log: {api_log_path})"
            )
            return False

        except Exception as e:
            logger.error(f"Failed to start API server: {e}")
            logger.info("Please start the API server manually:")
            logger.info(
                f"  (ensure PYTHONPATH=src) python -m uvicorn autopack.main:app --host {host} --port {port}"
            )
            return False

    def run_autonomous_loop(
        self,
        poll_interval: int = 10,
        max_iterations: Optional[int] = None,
        stop_on_first_failure: bool = False,
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

        # P0: Sanity check - verify run exists in API database before proceeding
        # This detects DB identity mismatch (API using different DB than expected)
        try:
            import requests

            url = f"{self.api_url}/runs/{self.run_id}"
            headers = {}
            if self.api_key:
                headers["X-API-Key"] = self.api_key
            response = requests.get(url, headers=headers, timeout=10)
            if response.status_code == 404:
                logger.error("=" * 70)
                logger.error("[DB_MISMATCH] RUN NOT FOUND IN API DATABASE")
                logger.error("=" * 70)
                logger.error(f"API server is healthy but run '{self.run_id}' not found")
                logger.error("This indicates database identity mismatch:")
                logger.error(
                    f"  - Executor DATABASE_URL: {os.environ.get('DATABASE_URL', 'NOT SET')}"
                )
                logger.error("  - API server may be using different database")
                logger.error("")
                logger.error("Recommended fixes:")
                logger.error("  1. Verify DATABASE_URL is set correctly before starting executor")
                logger.error("  2. Verify run was seeded in the correct database")
                logger.error("  3. Check API server logs for actual DATABASE_URL used")
                logger.error("  4. Use absolute paths for SQLite (not relative)")
                logger.error("=" * 70)
                raise RuntimeError(
                    f"Run '{self.run_id}' not found in API database. "
                    f"Database identity mismatch detected. "
                    f"Cannot proceed - would cause 404 errors on every API call."
                )
            response.raise_for_status()
            logger.info(f"✅ Run '{self.run_id}' verified in API database")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise  # Re-raise 404 as RuntimeError handled above
            logger.warning(f"Could not verify run existence (non-404 error): {e}")
            # Continue anyway - might be transient API error
        except Exception as e:
            logger.warning(f"Could not verify run existence: {e}")
            # Continue anyway - don't block execution on sanity check failure

        # Initialize infrastructure
        self._init_infrastructure()

        # INSERTION POINT 1: Initialize intention-first loop (BUILD-161 Phase A)
        from autopack.autonomous.executor_wiring import initialize_intention_first_loop
        from autopack.intention_anchor.storage import IntentionAnchorStorage

        # Load intention anchor for this run
        try:
            intention_anchor = IntentionAnchorStorage.load_anchor(self.run_id)
            if intention_anchor is None:
                logger.warning(
                    f"[IntentionFirst] No intention anchor found for run {self.run_id}, using defaults"
                )
                # Create minimal default anchor if none exists
                from autopack.intention_anchor.models import (
                    IntentionAnchor,
                    IntentionConstraints,
                    IntentionBudgets,
                )
                from datetime import datetime, timezone

                intention_anchor = IntentionAnchor(
                    anchor_id=f"default-{self.run_id}",
                    run_id=self.run_id,
                    project_id="default",
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    version=1,
                    north_star="Execute run according to phase specifications",
                    success_criteria=["All phases complete successfully"],
                    constraints=IntentionConstraints(must=[], must_not=[], preferences=[]),
                    budgets=IntentionBudgets(
                        max_context_chars=settings.run_token_cap * 4,  # Rough char estimate
                        max_sot_chars=500_000,
                    ),
                )
            logger.info(
                f"[IntentionFirst] Loaded intention anchor: {intention_anchor.anchor_id} (v{intention_anchor.version})"
            )

            # Initialize the intention-first loop with routing snapshot + state tracking
            wiring = initialize_intention_first_loop(
                run_id=self.run_id,
                project_id=intention_anchor.project_id,
                intention_anchor=intention_anchor,
            )
            logger.info(
                f"[IntentionFirst] Initialized loop with routing snapshot: {wiring.run_state.routing_snapshot.snapshot_id}"
            )
            # Store wiring state as instance variable for phase execution
            self._intention_wiring = wiring
            self._intention_anchor = intention_anchor
        except Exception as e:
            logger.warning(
                f"[IntentionFirst] Failed to initialize intention-first loop: {e}, continuing without it"
            )
            self._intention_wiring = None
            self._intention_anchor = None

        iteration = 0
        phases_executed = 0
        phases_failed = 0
        stop_signal_file = Path(".autonomous_runs/.stop_executor")
        stop_reason: str | None = None

        while True:
            # Check for stop signal (from monitor script)
            if stop_signal_file.exists():
                signal_content = stop_signal_file.read_text().strip()
                if signal_content.startswith(f"stop:{self.run_id}"):
                    logger.critical(f"[STOP_SIGNAL] Stop signal detected: {signal_content}")
                    logger.info("Stopping execution as requested by monitor")
                    stop_signal_file.unlink()  # Remove signal file
                    stop_reason = "stop_signal"
                    break

            # Check iteration limit
            if max_iterations and iteration >= max_iterations:
                logger.info(f"Reached max iterations ({max_iterations}), stopping")
                stop_reason = "max_iterations"
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

            # Auto-fix queued phases (normalize deliverables/scope, tune CI timeouts) before selection.
            try:
                self._autofix_queued_phases(run_data)
            except Exception as e:
                logger.warning(f"[AutoFix] Failed to auto-fix queued phases (non-blocking): {e}")

            # NEW: Initialize goal anchor on first iteration (for drift detection)
            if iteration == 1 and not hasattr(self, "_run_goal_anchor"):
                # Try to get goal_anchor from run data, or extract from first phase
                goal_anchor = run_data.get("goal_anchor")
                if not goal_anchor:
                    # Fall back to extracting from run description or first phase description
                    run_description = run_data.get("description", "")
                    if run_description:
                        goal_anchor = extract_goal_from_description(run_description)
                    else:
                        # Try first phase
                        phases = run_data.get("phases", [])
                        if phases:
                            first_phase_desc = phases[0].get("description", "")
                            goal_anchor = extract_goal_from_description(first_phase_desc)
                if goal_anchor:
                    self._run_goal_anchor = goal_anchor
                    logger.info(f"[GoalAnchor] Initialized: {goal_anchor[:100]}...")

            # Phase 1.6-1.7: Detect and reset stale EXECUTING phases
            try:
                self._detect_and_reset_stale_phases(run_data)
            except Exception as e:
                logger.warning(f"Stale phase detection failed: {e}")
                # Continue even if stale detection fails

            # BUILD-115: Use API-based phase selection instead of obsolete database queries
            next_phase = self.get_next_queued_phase(run_data)

            if not next_phase:
                logger.info("No more executable phases, execution complete")
                stop_reason = "no_more_executable_phases"
                break

            phase_id = next_phase.get("phase_id")
            logger.info(f"[BUILD-041] Next phase: {phase_id}")

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
                    logger.info(
                        f"Total phases executed: {phases_executed}, failed: {phases_failed}"
                    )
                    stop_reason = "stop_on_first_failure"
                    break

            # Wait before next iteration
            if max_iterations is None or iteration < max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                time.sleep(poll_interval)

        logger.info("Autonomous execution loop finished")

        # IMPORTANT: Only finalize a run when there are no executable phases remaining.
        # If we stop due to max-iterations/stop-signal/stop-on-failure, the run should remain resumable
        # (i.e., do NOT force it into a DONE_* state).
        if stop_reason == "no_more_executable_phases":
            # Log run completion summary to CONSOLIDATED_BUILD.md
            try:
                log_build_event(
                    event_type="RUN_COMPLETE",
                    description=f"Run {self.run_id} completed. Phases: {phases_executed} successful, {phases_failed} failed. Total iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.run_id}",
                        f"Successful: {phases_executed}",
                        f"Failed: {phases_failed}",
                    ],
                    project_slug=self._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run completion: {e}")

            # Best-effort fallback: ensure run_summary.md reflects terminal state even if API-side hook fails
            # Here we are truly finalizing the run (no executable phases remaining),
            # so allow mutating run.state to a terminal DONE_* state if needed.
            self._best_effort_write_run_summary(
                phases_failed=phases_failed, allow_run_state_mutation=True
            )

            # Learning Pipeline: Promote hints to persistent rules (Stage 0B)
            try:
                project_id = self._get_project_slug()
                promoted_count = promote_hints_to_rules(self.run_id, project_id)
                if promoted_count > 0:
                    logger.info(
                        f"Learning Pipeline: Promoted {promoted_count} hints to persistent project rules"
                    )
                    # Mark that rules have changed for future planning updates
                    self._mark_rules_updated(project_id, promoted_count)
                else:
                    logger.info(
                        "Learning Pipeline: No hints qualified for promotion (need 2+ occurrences)"
                    )
            except Exception as e:
                logger.warning(f"Failed to promote hints to rules: {e}")
        else:
            # Non-terminal stop: keep the run resumable.
            # Still log a lightweight event for visibility.
            try:
                log_build_event(
                    event_type="RUN_PAUSED",
                    description=f"Run {self.run_id} paused (reason={stop_reason}). Iterations: {iteration}",
                    deliverables=[
                        f"Run ID: {self.run_id}",
                        f"Reason: {stop_reason}",
                        f"Iterations: {iteration}",
                    ],
                    project_slug=self._get_project_slug(),
                )
            except Exception as e:
                logger.warning(f"Failed to log run pause: {e}")

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
