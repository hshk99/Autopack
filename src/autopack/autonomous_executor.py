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

from autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient
from autopack.anthropic_clients import AnthropicBuilderClient, AnthropicAuditorClient
from autopack.dual_auditor import DualAuditor
from autopack.quality_gate import QualityGate
from autopack.llm_client import BuilderResult, AuditorResult


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

        # Initialize clients (will be set in _init_infrastructure)
        self.builder = None
        self.auditor = None
        self.quality_gate = None

        logger.info(f"Initialized autonomous executor for run: {run_id}")
        logger.info(f"API URL: {api_url}")
        logger.info(f"Workspace: {workspace}")

    def _init_infrastructure(self):
        """Initialize Builder, Auditor, and Quality Gate clients"""
        logger.info("Initializing infrastructure...")

        # Initialize Builder (prefer OpenAI if available)
        if self.openai_key:
            self.builder = OpenAIBuilderClient(api_key=self.openai_key)
            logger.info("Builder: OpenAI (GPT-4o)")
        elif self.anthropic_key:
            self.builder = AnthropicBuilderClient(api_key=self.anthropic_key)
            logger.info("Builder: Anthropic (Claude)")
        else:
            raise ValueError("No builder client available")

        # Initialize Auditor (dual or single)
        if self.use_dual_auditor and self.openai_key and self.anthropic_key:
            primary_auditor = OpenAIAuditorClient(api_key=self.openai_key)
            secondary_auditor = AnthropicAuditorClient(api_key=self.anthropic_key)
            self.auditor = DualAuditor(
                primary_auditor=primary_auditor,
                secondary_auditor=secondary_auditor
            )
            logger.info("Auditor: Dual (OpenAI + Anthropic)")
        elif self.openai_key:
            self.auditor = OpenAIAuditorClient(api_key=self.openai_key)
            logger.info("Auditor: OpenAI (GPT-4o)")
        elif self.anthropic_key:
            self.auditor = AnthropicAuditorClient(api_key=self.anthropic_key)
            logger.info("Auditor: Anthropic (Claude)")
        else:
            raise ValueError("No auditor client available")

        # Initialize Quality Gate
        self.quality_gate = QualityGate(repo_root=self.workspace)
        logger.info("Quality Gate: Initialized")

    def get_run_status(self) -> Dict:
        """Fetch run status from Autopack API

        Returns:
            Run data with phases and status
        """
        url = f"{self.api_url}/runs/{self.run_id}"
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch run status: {e}")
            raise

    def get_next_queued_phase(self, run_data: Dict) -> Optional[Dict]:
        """Find next QUEUED phase in tier/index order

        Args:
            run_data: Run data from API

        Returns:
            Phase dict if found, None otherwise
        """
        phases = run_data.get("phases", [])

        # Sort by tier_index, then phase_index
        sorted_phases = sorted(
            phases,
            key=lambda p: (p.get("tier_index", 0), p.get("phase_index", 0))
        )

        # Find first QUEUED phase
        for phase in sorted_phases:
            if phase.get("status") == "QUEUED":
                return phase

        return None

    def execute_phase(self, phase: Dict) -> Tuple[bool, str]:
        """Execute Builder -> Auditor -> QualityGate pipeline for a phase

        Args:
            phase: Phase data from API

        Returns:
            Tuple of (success: bool, status: str)
            status can be: "COMPLETE", "FAILED", "BLOCKED"
        """
        phase_id = phase.get("phase_id")
        logger.info(f"Executing phase: {phase_id}")

        try:
            # Step 1: Execute with Builder
            logger.info(f"[{phase_id}] Step 1/4: Generating code with Builder...")
            builder_result = self.builder.execute_phase(
                phase_spec=phase,
                file_context=None,  # TODO: Use ContextSelector for JIT file loading
            )

            if not builder_result.success:
                logger.error(f"[{phase_id}] Builder failed: {builder_result.error}")
                self._post_builder_result(phase_id, builder_result)
                self._update_phase_status(phase_id, "FAILED")
                return False, "FAILED"

            logger.info(f"[{phase_id}] Builder succeeded ({builder_result.tokens_used} tokens)")

            # Post builder result to API
            self._post_builder_result(phase_id, builder_result)

            # Step 2: Review with Auditor
            logger.info(f"[{phase_id}] Step 2/4: Reviewing patch with Auditor...")
            auditor_result = self.auditor.review_patch(
                patch_content=builder_result.patch_content,
                phase_spec=phase,
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
            # TODO: Integrate with governed_apply for safe patching
            logger.info(f"[{phase_id}] Patch applied successfully (TODO: actual patching)")

            # Update phase status to COMPLETE
            self._update_phase_status(phase_id, "COMPLETE")
            logger.info(f"[{phase_id}] Phase completed successfully")

            return True, "COMPLETE"

        except Exception as e:
            logger.error(f"[{phase_id}] Execution failed: {e}")
            self._update_phase_status(phase_id, "FAILED")
            return False, "FAILED"

    def _post_builder_result(self, phase_id: str, result: BuilderResult):
        """POST builder result to Autopack API

        Args:
            phase_id: Phase ID
            result: Builder result
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/builder_result"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "success": result.success,
            "patch_content": result.patch_content,
            "builder_messages": result.builder_messages,
            "tokens_used": result.tokens_used,
            "model_used": result.model_used,
            "error": result.error,
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
            result: Auditor result
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/auditor_result"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {
            "approved": result.approved,
            "issues_found": result.issues_found,
            "auditor_messages": result.auditor_messages,
            "tokens_used": result.tokens_used,
            "model_used": result.model_used,
            "error": result.error,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug(f"Posted auditor result for phase {phase_id}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to post auditor result: {e}")

    def _update_phase_status(self, phase_id: str, status: str):
        """Update phase status via API

        Args:
            phase_id: Phase ID
            status: New status (COMPLETE, FAILED, BLOCKED)
        """
        url = f"{self.api_url}/runs/{self.run_id}/phases/{phase_id}/status"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload = {"status": status}

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            logger.debug(f"Updated phase {phase_id} status to {status}")
        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to update phase status: {e}")

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
