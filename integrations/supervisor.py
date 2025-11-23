"""
Supervisor Orchestration Module

This module implements the Supervisor loop that orchestrates autonomous builds
by coordinating Cursor (Builder) and Codex (Auditor) according to the v7 playbook.

The Supervisor:
1. Creates runs via Autopack API
2. Queues phases for execution
3. Dispatches work to Builder (Cursor)
4. Dispatches reviews to Auditor (Codex)
5. Monitors progress via metrics endpoints
6. Handles state transitions

Usage:
    from supervisor import Supervisor

    supervisor = Supervisor(api_url="http://localhost:8000")
    supervisor.run_autonomous_build(
        run_id="my-build",
        tiers=[...],
        phases=[...]
    )
"""

import requests
import time
from typing import List, Dict, Optional
from datetime import datetime

from cursor_integration import CursorBuilder
from codex_integration import CodexAuditor


class Supervisor:
    """Autonomous build supervisor"""

    def __init__(self, api_url: str = "http://localhost:8000"):
        self.api_url = api_url.rstrip("/")
        self.builder = CursorBuilder(api_url)
        self.auditor = CodexAuditor(api_url)

    def create_run(
        self,
        run_id: str,
        tiers: List[Dict],
        phases: List[Dict],
        safety_profile: str = "normal",
        run_scope: str = "incremental",
        token_cap: int = 5000000,
        max_phases: int = 25,
    ) -> Dict:
        """
        Create a new autonomous run.

        Returns:
            Run details from API
        """
        url = f"{self.api_url}/runs/start"

        payload = {
            "run": {
                "run_id": run_id,
                "safety_profile": safety_profile,
                "run_scope": run_scope,
                "token_cap": token_cap,
                "max_phases": max_phases,
            },
            "tiers": tiers,
            "phases": phases,
        }

        print(f"[Supervisor] Creating run: {run_id}")
        print(f"[Supervisor] Tiers: {len(tiers)}, Phases: {len(phases)}")

        response = requests.post(url, json=payload)
        response.raise_for_status()

        result = response.json()
        print(f"[Supervisor] ✅ Run created: {result['run_id']}")
        return result

    def execute_phase(self, run_id: str, phase: Dict) -> Dict:
        """
        Execute a single phase.

        Workflow:
        1. Builder (Cursor) executes the phase
        2. Auditor (Codex) reviews the output
        3. Based on review, either approve or retry
        """
        phase_id = phase["phase_id"]
        print(f"\n[Supervisor] ═══ Executing Phase: {phase_id} ═══")
        print(f"[Supervisor] Task: {phase.get('name', 'N/A')}")
        print(f"[Supervisor] Category: {phase.get('task_category', 'N/A')}")
        print(f"[Supervisor] Complexity: {phase.get('complexity', 'N/A')}")

        # Step 1: Builder executes
        print(f"\n[Supervisor] → Dispatching to Builder (Cursor)...")
        builder_result = self.builder.execute_phase(
            run_id=run_id,
            phase_id=phase_id,
            task_description=phase.get("description", ""),
            builder_mode=phase.get("builder_mode", "compose"),
        )

        # Step 2: Auditor reviews
        print(f"\n[Supervisor] → Dispatching to Auditor (Codex)...")
        audit_result = self.auditor.review_phase(
            run_id=run_id,
            phase_id=phase_id,
            diff_content=builder_result.get("patch_content", ""),
        )

        recommendation = audit_result.get("recommendation", "")
        print(f"\n[Supervisor] Auditor recommendation: {recommendation}")

        if recommendation == "approve":
            print(f"[Supervisor] ✅ Phase {phase_id} approved")
            return {"status": "approved", "phase_id": phase_id}
        elif recommendation == "revise":
            print(f"[Supervisor] ⚠️  Phase {phase_id} needs revision")
            # TODO: Implement retry logic
            return {"status": "needs_revision", "phase_id": phase_id}
        else:  # escalate
            print(f"[Supervisor] 🚨 Phase {phase_id} escalated for manual review")
            return {"status": "escalated", "phase_id": phase_id}

    def run_autonomous_build(
        self,
        run_id: str,
        tiers: List[Dict],
        phases: List[Dict],
        safety_profile: str = "normal",
        run_scope: str = "incremental",
    ) -> Dict:
        """
        Execute a full autonomous build.

        This orchestrates the entire build process:
        1. Create run
        2. Execute phases sequentially
        3. Monitor progress
        4. Report results
        """
        print(f"\n{'='*60}")
        print(f"🤖 AUTONOMOUS BUILD: {run_id}")
        print(f"{'='*60}\n")

        # Create run
        run = self.create_run(
            run_id=run_id,
            tiers=tiers,
            phases=phases,
            safety_profile=safety_profile,
            run_scope=run_scope,
        )

        # Execute each phase
        results = []
        for phase in phases:
            result = self.execute_phase(run_id, phase)
            results.append(result)

            # Check if we should stop
            if result["status"] == "escalated":
                print(f"\n[Supervisor] ⚠️  Build paused due to escalation")
                break

        # Get final summary
        summary = self.get_run_summary(run_id)

        print(f"\n{'='*60}")
        print(f"✅ AUTONOMOUS BUILD COMPLETE: {run_id}")
        print(f"{'='*60}\n")
        print(f"Phases executed: {len(results)}")
        print(f"Tokens used: {summary.get('budgets', {}).get('tokens_used', 0):,}")
        print(f"Issues found: {summary.get('issues', {}).get('minor_count', 0)} minor, {summary.get('issues', {}).get('major_count', 0)} major")

        return {
            "run_id": run_id,
            "phase_results": results,
            "summary": summary,
        }

    def get_run_summary(self, run_id: str) -> Dict:
        """Get comprehensive run summary"""
        url = f"{self.api_url}/reports/run_summary/{run_id}"
        response = requests.get(url)
        response.raise_for_status()
        return response.json()

    def monitor_run(self, run_id: str, poll_interval: int = 5) -> None:
        """
        Monitor a running build (for async scenarios).

        Args:
            poll_interval: Seconds between status checks
        """
        print(f"[Supervisor] Monitoring run: {run_id}")
        print(f"[Supervisor] Press Ctrl+C to stop monitoring\n")

        try:
            while True:
                summary = self.get_run_summary(run_id)
                state = summary.get("state", "UNKNOWN")

                print(f"[{datetime.now().strftime('%H:%M:%S')}] Run state: {state}")

                if state.startswith("DONE_"):
                    print(f"\n[Supervisor] Run completed with state: {state}")
                    break

                time.sleep(poll_interval)
        except KeyboardInterrupt:
            print(f"\n[Supervisor] Monitoring stopped by user")


def example_build():
    """Example: Run a simple autonomous build"""
    supervisor = Supervisor()

    # Define a simple build
    tiers = [
        {
            "tier_id": "T1",
            "tier_index": 0,
            "name": "Foundation Tier",
            "description": "Basic infrastructure",
        }
    ]

    phases = [
        {
            "phase_id": "P1.1",
            "phase_index": 0,
            "tier_id": "T1",
            "name": "Add Health Check",
            "description": "Add health check endpoint to API",
            "task_category": "feature_scaffolding",
            "complexity": "low",
            "builder_mode": "compose",
        },
        {
            "phase_id": "P1.2",
            "phase_index": 1,
            "tier_id": "T1",
            "name": "Add Logging",
            "description": "Add structured logging to application",
            "task_category": "feature_scaffolding",
            "complexity": "low",
            "builder_mode": "compose",
        },
    ]

    # Run the build
    result = supervisor.run_autonomous_build(
        run_id=f"auto-build-{int(time.time())}",
        tiers=tiers,
        phases=phases,
        safety_profile="normal",
        run_scope="incremental",
    )

    return result


if __name__ == "__main__":
    print("Autopack Supervisor - Autonomous Build Orchestration\n")
    print("This is a demonstration of the supervisor loop.")
    print("In production, Cursor and Codex would be real AI agents.\n")

    result = example_build()
    print(f"\nFinal result: {result}")
