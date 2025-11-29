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
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient
from autopack.anthropic_clients import AnthropicBuilderClient, AnthropicAuditorClient
from autopack.dual_auditor import DualAuditor
from autopack.quality_gate import QualityGate
from autopack.llm_client import BuilderResult, AuditorResult
from autopack.error_recovery import ErrorRecoverySystem, get_error_recovery, safe_execute
from autopack.llm_service import LlmService
from autopack.debug_journal import log_error, log_fix, mark_resolved


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

        # Initialize clients (will be set in _init_infrastructure for backward compatibility)
        self.builder = None
        self.auditor = None
        self.quality_gate = None

        logger.info(f"Initialized autonomous executor for run: {run_id}")
        logger.info(f"API URL: {api_url}")
        logger.info(f"Workspace: {workspace}")

    def _init_infrastructure(self):
        """Initialize LlmService, Builder, Auditor, and Quality Gate with error recovery"""
        def _do_init():
            logger.info("Initializing infrastructure...")

            # Initialize LlmService (handles model routing, usage tracking, quality gate)
            self.llm_service = LlmService(
                db=self.db_session,
                config_path="config/models.yaml",
                repo_root=self.workspace
            )
            logger.info("LlmService: Initialized with ModelRouter and UsageRecorder")

            # DEPRECATED: Direct client instantiation for backward compatibility
            # TODO: Remove these once all code uses LlmService.execute_builder_phase/execute_auditor_review
            # NOTE: These are only needed for legacy code paths. LlmService handles all model routing.
            # Initialize Builder (prefer Anthropic Claude if available, fallback to OpenAI)
            if self.anthropic_key:
                self.builder = AnthropicBuilderClient(api_key=self.anthropic_key)
                logger.info("[DEPRECATED] Builder: Anthropic (Claude Sonnet 4.5) - Use LlmService instead")
            elif self.openai_key:
                self.builder = OpenAIBuilderClient(api_key=self.openai_key)
                logger.info("[DEPRECATED] Builder: OpenAI (GPT-4o) - Use LlmService instead")
            else:
                # No API keys available - this will fail but with a clear message
                logger.warning("[DEPRECATED] No API keys available for Builder backward compatibility layer")
                self.builder = None

            # Initialize Auditor (dual or single)
            if self.use_dual_auditor and self.openai_key and self.anthropic_key:
                primary_auditor = OpenAIAuditorClient(api_key=self.openai_key)
                secondary_auditor = AnthropicAuditorClient(api_key=self.anthropic_key)
                self.auditor = DualAuditor(
                    primary_auditor=primary_auditor,
                    secondary_auditor=secondary_auditor
                )
                logger.info("[DEPRECATED] Auditor: Dual (OpenAI + Anthropic) - Use LlmService instead")
            elif self.anthropic_key:
                self.auditor = AnthropicAuditorClient(api_key=self.anthropic_key)
                logger.info("[DEPRECATED] Auditor: Anthropic (Claude) - Use LlmService instead")
            elif self.openai_key:
                self.auditor = OpenAIAuditorClient(api_key=self.openai_key)
                logger.info("[DEPRECATED] Auditor: OpenAI (GPT-4o) - Use LlmService instead")
            else:
                # No API keys available - this will fail but with a clear message
                logger.warning("[DEPRECATED] No API keys available for Auditor backward compatibility layer")
                self.auditor = None

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
        """Execute Builder -> Auditor -> QualityGate pipeline for a phase with error recovery

        Args:
            phase: Phase data from API

        Returns:
            Tuple of (success: bool, status: str)
            status can be: "COMPLETE", "FAILED", "BLOCKED"
        """
        phase_id = phase.get("phase_id")
        logger.info(f"Executing phase: {phase_id}")

        # Wrap phase execution with error recovery
        def _execute_phase_inner():
            return self._execute_phase_with_recovery(phase)

        try:
            return self.error_recovery.execute_with_retry(
                func=_execute_phase_inner,
                operation_name=f"Phase execution: {phase_id}",
                max_retries=2  # Retry twice for transient errors
            )
        except Exception as e:
            logger.error(f"[{phase_id}] Phase execution failed permanently: {e}")

            # Log to debug journal for persistent tracking
            log_error(
                error_signature=f"Phase {phase_id} execution failure",
                symptom=f"{type(e).__name__}: {str(e)}",
                run_id=self.run_id,
                phase_id=phase_id,
                suspected_cause="Unhandled exception in phase execution pipeline",
                priority="HIGH"
            )

            self._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

    def _execute_phase_with_recovery(self, phase: Dict) -> Tuple[bool, str]:
        """Inner phase execution with error handling"""
        phase_id = phase.get("phase_id")

        try:
            # Step 1: Execute with Builder using LlmService
            logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...")

            # Load repository context for Builder
            file_context = self._load_repository_context(phase)
            logger.info(f"[{phase_id}] Loaded {len(file_context.get('existing_files', {}))} files for context")

            # Use LlmService for complexity-based model selection and usage tracking
            builder_result = self.llm_service.execute_builder_phase(
                phase_spec=phase,
                file_context=file_context,
                max_tokens=None,  # Let ModelRouter decide based on phase config
                project_rules=[],  # TODO: Load from .autopack/learned_rules.yaml
                run_hints=[],  # TODO: Collect within-run hints
                run_id=self.run_id,
                phase_id=phase_id,
                run_context={},  # TODO: Pass model_overrides if specified in run config
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")
                self._post_builder_result(phase_id, builder_result)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # Post builder result to API
            self._post_builder_result(phase_id, builder_result)

            # Step 2: Review with Auditor using LlmService
            logger.info(f"[{phase_id}] Step 2/4: Reviewing patch with Auditor (via LlmService)...")

            # Use LlmService for complexity-based model selection, usage tracking, and quality gate
            auditor_result = self.llm_service.execute_auditor_review(
                patch_content=builder_result.patch_content,
                phase_spec=phase,
                max_tokens=None,  # Let ModelRouter decide
                project_rules=[],  # TODO: Load from .autopack/learned_rules.yaml
                run_hints=[],  # TODO: Collect within-run hints
                run_id=self.run_id,
                phase_id=phase_id,
                run_context={},  # TODO: Pass model_overrides if specified
                ci_result={},  # TODO: Run pytest/mypy and get actual CI result
                coverage_delta=0.0,  # TODO: Calculate actual coverage delta
            )

            logger.info(f"[{phase_id}] Auditor completed: approved={auditor_result.approved}, "
                       f"issues={len(auditor_result.issues_found)}")

            # Post auditor result to API
            self._post_auditor_result(phase_id, auditor_result)

            # Step 3: Apply Quality Gate
            logger.info(f"[{phase_id}] Step 3/4: Applying Quality Gate...")
            quality_report = self.quality_gate.assess_phase(
                phase_id=phase_id,
                phase_spec=phase,
                auditor_result={
                    "approved": auditor_result.approved,
                    "issues_found": auditor_result.issues_found,
                },
                ci_result={},  # TODO: Run pytest/mypy and get actual CI result
                coverage_delta=0.0,  # TODO: Calculate actual coverage delta
                patch_content=builder_result.patch_content,
                files_changed=None,  # TODO: Extract from builder result
            )

            logger.info(f"[{phase_id}] Quality Gate: {quality_report.quality_level}")

            # Check if blocked
            if quality_report.is_blocked():
                logger.warning(f"[{phase_id}] Phase BLOCKED by quality gate")
                for issue in quality_report.issues:
                    logger.warning(f"  - {issue}")
                self._update_phase_status(phase_id, "BLOCKED")
                return False, "BLOCKED"

            # Step 4: Apply patch (if not blocked)
            logger.info(f"[{phase_id}] Step 4/4: Applying patch...")

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

            # Update phase status to COMPLETE
            self._update_phase_status(phase_id, "COMPLETE")
            logger.info(f"[{phase_id}] Phase completed successfully")

            return True, "COMPLETE"

        except Exception as e:
            logger.error(f"[{phase_id}] Execution failed: {e}")
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
            response.raise_for_status()
            logger.debug(f"Posted builder result for phase {phase_id}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to post builder result: {e}")

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

    def _update_phase_status(self, phase_id: str, status: str):
        """Update phase status via API

        NOTE: Phase status is automatically updated by the API when builder/auditor
        results are posted. This method is kept for backward compatibility but
        does nothing since the /status endpoint doesn't exist.

        Args:
            phase_id: Phase ID
            status: New status (COMPLETE, FAILED, BLOCKED)
        """
        # Phase status updates handled by builder/auditor result endpoints
        logger.debug(f"Phase {phase_id} status will be updated to {status} via builder/auditor results")

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

            # Get next queued phase
            next_phase = self.get_next_queued_phase(run_data)

            if not next_phase:
                logger.info("No more QUEUED phases, execution complete")
                break

            phase_id = next_phase.get("phase_id")
            logger.info(f"Next phase: {phase_id}")

            # Execute phase
            success, status = self.execute_phase(next_phase)

            if success:
                logger.info(f"Phase {phase_id} completed successfully")
            else:
                logger.warning(f"Phase {phase_id} finished with status: {status}")

            # Wait before next iteration
            if max_iterations is None or iteration < max_iterations:
                logger.info(f"Waiting {poll_interval}s before next phase...")
                time.sleep(poll_interval)

        logger.info("Autonomous execution loop finished")


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
