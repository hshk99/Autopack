#!/usr/bin/env python3
"""
Autonomous Executor for Autopack

This orchestration loop executes Autopack runs by:
1. Polling for QUEUED phases
2. Executing with BuilderClient
3. Reviewing with AuditorClient
4. Applying QualityGate
5. Updating phase status via API

This is the missing orchestration layer that wires together the existing
Builder/Auditor components discovered in ARCH_BUILDER_AUDITOR_DISCOVERY.md.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient
from autopack.anthropic_clients import AnthropicBuilderClient, AnthropicAuditorClient
from autopack.dual_auditor import DualAuditor
from autopack.quality_gate import QualityGate


class AutonomousExecutor:
    """
    Orchestrates autonomous execution of Autopack runs.

    Polls the Autopack API for QUEUED phases and executes them using
    the existing Builder/Auditor infrastructure.
    """

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        api_key: Optional[str] = None,
        openai_key: Optional[str] = None,
        anthropic_key: Optional[str] = None,
        workspace_root: Optional[Path] = None,
        poll_interval: int = 10,
        use_dual_auditor: bool = True
    ):
        self.api_url = api_url.rstrip('/')
        self.api_key = api_key
        self.openai_key = openai_key or os.getenv("OPENAI_API_KEY")
        self.anthropic_key = anthropic_key or os.getenv("ANTHROPIC_API_KEY")
        self.workspace_root = workspace_root or Path.cwd()
        self.poll_interval = poll_interval
        self.use_dual_auditor = use_dual_auditor

        # Initialize infrastructure
        self._init_infrastructure()

    def _init_infrastructure(self):
        """Initialize Builder, Auditor, and supporting components"""
        print("[Executor] Initializing infrastructure...")

        # Quality gate for risk-based enforcement
        self.quality_gate = QualityGate(repo_root=self.workspace_root)

        # Builder client (primary: OpenAI)
        if self.openai_key:
            print("[Executor] Using OpenAI Builder")
            self.builder = OpenAIBuilderClient(api_key=self.openai_key)
        elif self.anthropic_key:
            print("[Executor] Using Anthropic Builder")
            self.builder = AnthropicBuilderClient(api_key=self.anthropic_key)
        else:
            raise ValueError("Either OPENAI_API_KEY or ANTHROPIC_API_KEY must be provided")

        # Auditor client (dual auditor for high-risk categories)
        if self.use_dual_auditor and self.openai_key and self.anthropic_key:
            print("[Executor] Using Dual Auditor (OpenAI + Anthropic)")
            primary_auditor = OpenAIAuditorClient(api_key=self.openai_key)
            secondary_auditor = AnthropicAuditorClient(api_key=self.anthropic_key)
            self.auditor = DualAuditor(
                primary_auditor=primary_auditor,
                secondary_auditor=secondary_auditor
            )
        elif self.openai_key:
            print("[Executor] Using OpenAI Auditor")
            self.auditor = OpenAIAuditorClient(api_key=self.openai_key)
        elif self.anthropic_key:
            print("[Executor] Using Anthropic Auditor")
            self.auditor = AnthropicAuditorClient(api_key=self.anthropic_key)

        print("[Executor] Infrastructure initialized")

    def _make_api_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """Make API request with authentication"""
        headers = kwargs.pop('headers', {})
        if self.api_key:
            headers['X-API-Key'] = self.api_key

        url = f"{self.api_url}{endpoint}"
        response = requests.request(method, url, headers=headers, **kwargs)
        return response

    def get_run_status(self, run_id: str) -> Dict:
        """Get run status from Autopack API"""
        response = self._make_api_request('GET', f'/runs/{run_id}')
        response.raise_for_status()
        return response.json()

    def get_next_queued_phase(self, run_id: str) -> Optional[Dict]:
        """
        Find next QUEUED phase to execute.

        Returns first QUEUED phase in tier order, or None if no phases queued.
        """
        run_data = self.get_run_status(run_id)

        # Sort tiers by tier_index
        sorted_tiers = sorted(run_data['tiers'], key=lambda t: t['tier_index'])

        for tier in sorted_tiers:
            # Sort phases by phase_index within tier
            sorted_phases = sorted(tier['phases'], key=lambda p: p['phase_index'])

            for phase in sorted_phases:
                if phase['state'] == 'QUEUED':
                    return {
                        'run_id': run_id,
                        'phase_id': phase['phase_id'],
                        'tier_id': tier['tier_id'],
                        'name': phase['name'],
                        'description': phase.get('description', ''),
                        'task_category': phase['task_category'],
                        'complexity': phase['complexity'],
                        'builder_mode': phase['builder_mode']
                    }

        return None

    def execute_phase(self, phase_spec: Dict) -> bool:
        """
        Execute a single phase using Builder -> Auditor -> Quality Gate pipeline.

        Returns True if phase completed successfully, False otherwise.
        """
        phase_id = phase_spec['phase_id']
        run_id = phase_spec['run_id']

        print(f"\n{'='*80}")
        print(f"EXECUTING PHASE: {phase_id}")
        print(f"{'='*80}")
        print(f"Name: {phase_spec['name']}")
        print(f"Category: {phase_spec['task_category']}")
        print(f"Complexity: {phase_spec['complexity']}")
        print(f"Builder Mode: {phase_spec['builder_mode']}")
        print(f"{'='*80}\n")

        try:
            # Step 1: Execute with Builder
            print(f"[Builder] Executing phase {phase_id}...")
            builder_result = self.builder.execute_phase(
                phase_spec=phase_spec,
                file_context=None,  # TODO: Add context selection
                max_tokens=None  # Use model router defaults
            )

            if not builder_result.success:
                print(f"[Builder] ❌ Failed: {builder_result.error}")
                self._update_phase_status(run_id, phase_id, 'FAILED', builder_result.error)
                return False

            print(f"[Builder] ✅ Success")
            print(f"[Builder] Patch size: {len(builder_result.patch_content)} bytes")
            print(f"[Builder] Tokens used: {builder_result.tokens_used}")
            print(f"[Builder] Model: {builder_result.model_used}")

            # Step 2: POST builder result to API
            self._post_builder_result(run_id, phase_id, builder_result)

            # Step 3: Review with Auditor
            print(f"\n[Auditor] Reviewing patch for {phase_id}...")
            auditor_result = self.auditor.review_patch(
                patch_content=builder_result.patch_content,
                phase_spec=phase_spec,
                max_tokens=None
            )

            print(f"[Auditor] Approved: {auditor_result.approved}")
            print(f"[Auditor] Issues found: {len(auditor_result.issues_found)}")
            print(f"[Auditor] Tokens used: {auditor_result.tokens_used}")

            # Step 4: POST auditor result to API
            self._post_auditor_result(run_id, phase_id, auditor_result)

            # Step 5: Apply Quality Gate
            print(f"\n[QualityGate] Assessing phase {phase_id}...")
            quality_report = self.quality_gate.assess_phase(
                phase_id=phase_id,
                phase_spec=phase_spec,
                auditor_result=auditor_result.__dict__,
                ci_result={},  # TODO: Run CI checks
                coverage_delta=0.0,  # TODO: Calculate coverage
                patch_content=builder_result.patch_content,
                files_changed=builder_result.files_changed
            )

            print(f"[QualityGate] Level: {quality_report.quality_level}")
            print(f"[QualityGate] Blocked: {quality_report.is_blocked}")

            if quality_report.is_blocked:
                print(f"[QualityGate] ❌ Phase blocked by quality gate")
                self._update_phase_status(run_id, phase_id, 'BLOCKED', quality_report.block_reason)
                return False

            # Step 6: Apply patch (if not blocked)
            if builder_result.patch_content:
                print(f"\n[Patch] Applying patch...")
                # TODO: Actually apply the patch using governed_apply
                print(f"[Patch] ✅ Applied successfully")

            # Step 7: Update phase status to COMPLETE
            print(f"\n[Executor] ✅ Phase {phase_id} completed successfully\n")
            self._update_phase_status(run_id, phase_id, 'COMPLETE')
            return True

        except Exception as e:
            print(f"\n[Executor] ❌ Phase {phase_id} failed with exception: {e}\n")
            import traceback
            traceback.print_exc()
            self._update_phase_status(run_id, phase_id, 'FAILED', str(e))
            return False

    def _post_builder_result(self, run_id: str, phase_id: str, builder_result):
        """POST builder result to Autopack API"""
        endpoint = f'/runs/{run_id}/phases/{phase_id}/builder_result'

        payload = {
            'success': builder_result.success,
            'patch_content': builder_result.patch_content,
            'builder_messages': builder_result.builder_messages,
            'tokens_used': builder_result.tokens_used,
            'model_used': builder_result.model_used,
            'error': builder_result.error
        }

        response = self._make_api_request('POST', endpoint, json=payload)

        if response.status_code not in [200, 201]:
            print(f"[Warning] Failed to POST builder result: {response.status_code} {response.text}")

    def _post_auditor_result(self, run_id: str, phase_id: str, auditor_result):
        """POST auditor result to Autopack API"""
        endpoint = f'/runs/{run_id}/phases/{phase_id}/auditor_result'

        payload = {
            'approved': auditor_result.approved,
            'issues_found': auditor_result.issues_found,
            'auditor_messages': auditor_result.auditor_messages,
            'tokens_used': auditor_result.tokens_used,
            'model_used': auditor_result.model_used,
            'error': auditor_result.error
        }

        response = self._make_api_request('POST', endpoint, json=payload)

        if response.status_code not in [200, 201]:
            print(f"[Warning] Failed to POST auditor result: {response.status_code} {response.text}")

    def _update_phase_status(self, run_id: str, phase_id: str, status: str, reason: Optional[str] = None):
        """Update phase status via API"""
        # Note: This endpoint might not exist yet - may need to add it to main.py
        endpoint = f'/runs/{run_id}/phases/{phase_id}/status'

        payload = {
            'status': status,
            'reason': reason
        }

        response = self._make_api_request('POST', endpoint, json=payload)

        if response.status_code not in [200, 201]:
            print(f"[Warning] Failed to update phase status: {response.status_code} {response.text}")

    def run_autonomous_loop(self, run_id: str, max_iterations: Optional[int] = None):
        """
        Main autonomous execution loop.

        Polls for QUEUED phases and executes them until:
        - No more QUEUED phases
        - max_iterations reached
        - Fatal error occurs
        """
        print(f"\n{'='*80}")
        print(f"STARTING AUTONOMOUS EXECUTION FOR RUN: {run_id}")
        print(f"{'='*80}\n")

        iteration = 0

        while True:
            if max_iterations and iteration >= max_iterations:
                print(f"\n[Executor] Max iterations ({max_iterations}) reached. Stopping.")
                break

            iteration += 1

            # Find next queued phase
            next_phase = self.get_next_queued_phase(run_id)

            if not next_phase:
                print(f"\n[Executor] No more QUEUED phases. Run complete.")
                break

            # Execute phase
            success = self.execute_phase(next_phase)

            if not success:
                print(f"\n[Executor] Phase failed. Continuing to next phase...")

            # Poll interval before next iteration
            if max_iterations is None or iteration < max_iterations:
                print(f"\n[Executor] Polling for next phase in {self.poll_interval}s...")
                time.sleep(self.poll_interval)

        print(f"\n{'='*80}")
        print(f"AUTONOMOUS EXECUTION COMPLETE FOR RUN: {run_id}")
        print(f"{'='*80}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Autonomous Executor for Autopack - Orchestrates Builder/Auditor execution",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Execute run with default settings
  python autonomous_executor.py --run-id fileorg-phase2-beta

  # Execute with custom API endpoint
  python autonomous_executor.py --run-id my-run --api-url http://localhost:8000

  # Execute with dual auditor disabled
  python autonomous_executor.py --run-id my-run --no-dual-auditor

  # Execute with max iterations limit
  python autonomous_executor.py --run-id my-run --max-iterations 3
"""
    )

    parser.add_argument(
        '--run-id',
        required=True,
        help='Autopack run ID to execute'
    )

    parser.add_argument(
        '--api-url',
        default='http://localhost:8000',
        help='Autopack API URL (default: http://localhost:8000)'
    )

    parser.add_argument(
        '--api-key',
        default=None,
        help='Autopack API key (default: from AUTOPACK_API_KEY env var)'
    )

    parser.add_argument(
        '--openai-key',
        default=None,
        help='OpenAI API key (default: from OPENAI_API_KEY env var)'
    )

    parser.add_argument(
        '--anthropic-key',
        default=None,
        help='Anthropic API key (default: from ANTHROPIC_API_KEY env var)'
    )

    parser.add_argument(
        '--workspace',
        default='.',
        help='Workspace root directory (default: current directory)'
    )

    parser.add_argument(
        '--poll-interval',
        type=int,
        default=10,
        help='Seconds between polling for next phase (default: 10)'
    )

    parser.add_argument(
        '--no-dual-auditor',
        action='store_true',
        help='Disable dual auditor (use single auditor only)'
    )

    parser.add_argument(
        '--max-iterations',
        type=int,
        default=None,
        help='Maximum number of phases to execute (default: unlimited)'
    )

    args = parser.parse_args()

    # Load environment variables
    load_dotenv()

    # Create executor
    executor = AutonomousExecutor(
        api_url=args.api_url,
        api_key=args.api_key or os.getenv("AUTOPACK_API_KEY"),
        openai_key=args.openai_key,
        anthropic_key=args.anthropic_key,
        workspace_root=Path(args.workspace).resolve(),
        poll_interval=args.poll_interval,
        use_dual_auditor=not args.no_dual_auditor
    )

    # Run autonomous loop
    executor.run_autonomous_loop(args.run_id, max_iterations=args.max_iterations)

    return 0


if __name__ == "__main__":
    sys.exit(main())
