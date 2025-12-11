"""
Supervisor Orchestration Module

This module implements the Supervisor loop that orchestrates autonomous builds
by coordinating Builder and Auditor according to the v7 playbook.

Per v7 GPT architect recommendation:
- Uses OpenAI API directly (not Cursor Cloud Agents)
- ModelSelector chooses models based on complexity/risk
- Tracks tokens and costs at phase/tier/run levels

The Supervisor:
1. Creates runs via Autopack API
2. Queues phases for execution
3. Dispatches work to Builder (OpenAI)
4. Dispatches reviews to Auditor (OpenAI)
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

import sys
import os
import yaml
import requests
import time
from typing import List, Dict, Optional
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.autopack.openai_clients import OpenAIBuilderClient, OpenAIAuditorClient
from src.autopack.llm_client import ModelSelector
from src.autopack.learned_rules import (
    load_project_learned_rules,
    get_relevant_rules_for_phase,
    load_run_rule_hints,
    get_relevant_hints_for_phase,
    record_run_rule_hint,
    promote_hints_to_rules,
)

# Import agent launcher for event-driven agents
try:
    sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
    from launch_claude_agents import launch_agents
    AGENTS_AVAILABLE = True
except ImportError:
    AGENTS_AVAILABLE = False
    print("[Supervisor] Warning: Claude agent launcher not available")


class Supervisor:
    """Autonomous build supervisor with real LLM integration"""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        openai_api_key: Optional[str] = None,
        target_repo_path: Optional[str] = None,
        project_id: str = "Autopack",
        enable_aux_agents: bool = True
    ):
        """
        Initialize Supervisor for autonomous builds.

        Args:
            api_url: Autopack API URL
            openai_api_key: OpenAI API key (defaults to env var)
            target_repo_path: Path to target project repository
                             If None, uses current directory
                             Example: "c:\\Projects\\my-app"
            project_id: Project identifier for learned rules isolation
                       Used to store/load project-specific learned rules
            enable_aux_agents: Enable auxiliary Claude agents (planner, marketing, etc.)
        """
        self.api_url = api_url.rstrip("/")

        # Target repository path for multi-project isolation
        self.target_repo_path = target_repo_path or os.getcwd()
        print(f"[Supervisor] Target repository: {self.target_repo_path}")

        # Project ID for learned rules
        self.project_id = project_id
        print(f"[Supervisor] Project ID: {self.project_id}")

        # Auxiliary agents configuration
        self.enable_aux_agents = enable_aux_agents and AGENTS_AVAILABLE
        if self.enable_aux_agents:
            print(f"[Supervisor] Auxiliary agents: ENABLED")
        else:
            print(f"[Supervisor] Auxiliary agents: DISABLED")

        # Load configurations
        self.models_config = self._load_models_config()
        self.pricing_config = self._load_pricing_config()

        # Initialize LLM clients
        self.builder = OpenAIBuilderClient(api_key=openai_api_key)
        self.auditor = OpenAIAuditorClient(api_key=openai_api_key)

        # Initialize model selector
        self.model_selector = ModelSelector(self.models_config)

        # Learned rules storage (Stage 0A + 0B)
        self.project_rules = []  # Persistent cross-run rules (Stage 0B)
        self.run_rules_snapshot = []  # Rules loaded at run start (frozen during run)

        # Track HIGH_RISK categories from strategy engine
        self.high_risk_categories = {
            "cross_cutting_refactor",
            "index_registry_change",
            "schema_contract_change",
            "bulk_multi_file_operation",
            "security_auth_change",
            "external_feature_reuse",
            "external_code_intake",
        }

    def _load_models_config(self) -> Dict:
        """Load models configuration from config/models.yaml"""
        config_path = Path(__file__).parent.parent / "config" / "models.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

    def _load_pricing_config(self) -> Dict:
        """Load pricing configuration from config/pricing.yaml"""
        config_path = Path(__file__).parent.parent / "config" / "pricing.yaml"
        with open(config_path) as f:
            return yaml.safe_load(f)

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
        Execute a single phase with real LLM integration.

        Workflow:
        1. ModelSelector chooses appropriate models
        2. Builder (OpenAI) executes the phase
        3. Auditor (OpenAI) reviews the output
        4. Based on review, either approve or retry
        """
        phase_id = phase["phase_id"]
        task_category = phase.get("task_category", "feature_scaffolding")
        complexity = phase.get("complexity", "medium")

        print(f"\n[Supervisor] ═══ Executing Phase: {phase_id} ═══")
        print(f"[Supervisor] Task: {phase.get('name', 'N/A')}")
        print(f"[Supervisor] Category: {task_category}")
        print(f"[Supervisor] Complexity: {complexity}")

        # Step 1: Select models based on complexity and risk
        is_high_risk = task_category in self.high_risk_categories
        model_selection = self.model_selector.select_models(
            task_category=task_category,
            complexity=complexity,
            is_high_risk=is_high_risk
        )

        print(f"\n[Supervisor] 🧠 Model Selection:")
        print(f"[Supervisor]    Builder: {model_selection.builder_model}")
        print(f"[Supervisor]    Auditor: {model_selection.auditor_model}")
        print(f"[Supervisor]    Rationale: {model_selection.rationale}")

        # Stage 0A + 0B: Get relevant rules and hints for this phase
        print(f"\n[Supervisor] 📚 Loading learned rules for phase...")

        # Stage 0B: Get persistent project rules (from snapshot)
        relevant_project_rules = get_relevant_rules_for_phase(
            self.run_rules_snapshot, phase, max_rules=10
        )

        # Stage 0A: Get run-local hints from earlier phases
        relevant_run_hints = get_relevant_hints_for_phase(
            run_id, phase, max_hints=5
        )

        if relevant_project_rules or relevant_run_hints:
            print(f"[Supervisor]    Project rules: {len(relevant_project_rules)}")
            print(f"[Supervisor]    Run hints: {len(relevant_run_hints)}")
        else:
            print(f"[Supervisor]    No relevant rules or hints found")

        # Step 2: Builder executes
        print(f"\n[Supervisor] → Dispatching to Builder (OpenAI {model_selection.builder_model})...")

        # Prepare phase spec for Builder
        phase_spec = {
            "phase_id": phase_id,
            "task_category": task_category,
            "complexity": complexity,
            "description": phase.get("description", ""),
            "acceptance_criteria": phase.get("acceptance_criteria", []),
        }

        builder_result = self.builder.execute_phase(
            phase_spec=phase_spec,
            file_context=None,  # TODO: Add repo file context
            max_tokens=phase.get("incident_token_cap", 500000),
            model=model_selection.builder_model,
            project_rules=relevant_project_rules,  # Stage 0B
            run_hints=relevant_run_hints  # Stage 0A
        )

        if not builder_result.success:
            print(f"\n[Supervisor] ❌ Builder failed: {builder_result.error}")
            return {
                "status": "builder_failed",
                "phase_id": phase_id,
                "error": builder_result.error
            }

        print(f"[Supervisor] ✅ Builder completed")
        print(f"[Supervisor]    Tokens used: {builder_result.tokens_used:,}")
        print(f"[Supervisor]    Patch size: {len(builder_result.patch_content)} chars")

        # Step 3: Submit builder result to API
        print(f"\n[Supervisor] → Submitting builder result to API...")

        submit_result = self._submit_builder_result(
            run_id=run_id,
            phase_id=phase_id,
            builder_result=builder_result
        )

        if not submit_result:
            print(f"[Supervisor] ⚠️  Warning: Failed to submit builder result")

        # Step 4: Auditor reviews
        print(f"\n[Supervisor] → Dispatching to Auditor (OpenAI {model_selection.auditor_model})...")

        auditor_result = self.auditor.review_patch(
            patch_content=builder_result.patch_content,
            phase_spec=phase_spec,
            max_tokens=phase.get("incident_token_cap", 500000) // 2,  # Auditor gets half the budget
            model=model_selection.auditor_model,
            project_rules=relevant_project_rules,  # Stage 0B
            run_hints=relevant_run_hints  # Stage 0A
        )

        if not auditor_result.approved:
            print(f"\n[Supervisor] ⚠️  Auditor found {len(auditor_result.issues_found)} issues")
            for issue in auditor_result.issues_found:
                severity = issue.get("severity", "unknown")
                description = issue.get("description", "No description")
                print(f"[Supervisor]    [{severity.upper()}] {description}")

        print(f"[Supervisor] Auditor tokens used: {auditor_result.tokens_used:,}")

        # Step 5: Submit auditor result to API
        print(f"\n[Supervisor] → Submitting auditor result to API...")

        audit_submit_result = self._submit_auditor_result(
            run_id=run_id,
            phase_id=phase_id,
            auditor_result=auditor_result
        )

        if not audit_submit_result:
            print(f"[Supervisor] ⚠️  Warning: Failed to submit auditor result")

        # Step 6: Determine outcome
        total_tokens = builder_result.tokens_used + auditor_result.tokens_used

        if auditor_result.approved:
            print(f"\n[Supervisor] ✅ Phase {phase_id} APPROVED")
            print(f"[Supervisor]    Total tokens: {total_tokens:,}")

            # Stage 0A: Record hint if issues were resolved in this phase
            # TODO: Track issues_before and issues_after from CI/test results
            # For now, we use auditor issues as proxy
            issues_before = []  # Would come from CI before this phase
            issues_after = auditor_result.issues_found

            try:
                hint = record_run_rule_hint(
                    run_id=run_id,
                    phase=phase,
                    issues_before=issues_before,
                    issues_after=issues_after,
                    context={"file_paths": []}  # TODO: Extract from patch
                )
                if hint:
                    print(f"[Supervisor] 📝 Recorded run hint: {hint.hint_text[:60]}...")
            except Exception as e:
                print(f"[Supervisor] Warning: Could not record hint: {e}")

            return {
                "status": "approved",
                "phase_id": phase_id,
                "tokens_used": total_tokens,
                "issues_found": len(auditor_result.issues_found)
            }
        else:
            print(f"\n[Supervisor] ⚠️  Phase {phase_id} NEEDS REVISION")
            print(f"[Supervisor]    Total tokens: {total_tokens:,}")
            return {
                "status": "needs_revision",
                "phase_id": phase_id,
                "tokens_used": total_tokens,
                "issues_found": len(auditor_result.issues_found)
            }

    def _submit_builder_result(
        self,
        run_id: str,
        phase_id: str,
        builder_result
    ) -> bool:
        """Submit builder result to Autopack API"""
        url = f"{self.api_url}/runs/{run_id}/phases/{phase_id}/builder_result"

        payload = {
            "patch_content": builder_result.patch_content,
            "phase_id": phase_id,
            "builder_messages": builder_result.builder_messages,
            "tokens_used": builder_result.tokens_used,
            "success": builder_result.success,
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"[Supervisor] Error submitting builder result: {e}")
            return False

    def _submit_auditor_result(
        self,
        run_id: str,
        phase_id: str,
        auditor_result
    ) -> bool:
        """Submit auditor result to Autopack API"""
        url = f"{self.api_url}/runs/{run_id}/phases/{phase_id}/auditor_result"

        payload = {
            "phase_id": phase_id,
            "approved": auditor_result.approved,
            "issues_found": auditor_result.issues_found,
            "auditor_messages": auditor_result.auditor_messages,
            "tokens_used": auditor_result.tokens_used,
        }

        try:
            response = requests.post(url, json=payload)
            response.raise_for_status()
            return True
        except Exception as e:
            print(f"[Supervisor] Error submitting auditor result: {e}")
            return False

    def run_autonomous_build(
        self,
        run_id: str,
        tiers: List[Dict],
        phases: List[Dict],
        safety_profile: str = "normal",
        run_scope: str = "incremental",
    ) -> Dict:
        """
        Execute a full autonomous build with real LLM integration.

        This orchestrates the entire build process:
        1. Create run
        2. Execute phases sequentially
        3. Monitor progress
        4. Report results
        """
        print(f"\n{'='*60}")
        print(f"🤖 AUTONOMOUS BUILD: {run_id}")
        print(f"{'='*60}\n")

        # Stage 0B: Load persistent project rules (before run starts)
        print(f"[Supervisor] 📚 Loading project learned rules...")
        self.project_rules = load_project_learned_rules(self.project_id)
        self.run_rules_snapshot = self.project_rules.copy()  # Freeze for this run
        print(f"[Supervisor] Loaded {len(self.project_rules)} persistent rules for project '{self.project_id}'")

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
        total_tokens = 0

        for phase in phases:
            result = self.execute_phase(run_id, phase)
            results.append(result)

            total_tokens += result.get("tokens_used", 0)

            # Check if we should stop
            if result["status"] == "builder_failed":
                print(f"\n[Supervisor] ⚠️  Build stopped due to builder failure")
                break

        # Get final summary
        try:
            summary = self.get_run_summary(run_id)
        except Exception as e:
            print(f"[Supervisor] Warning: Could not get run summary: {e}")
            summary = {}

        # Stage 0B: Promote run hints to persistent rules (after run completes)
        print(f"\n[Supervisor] 🎓 Promoting run hints to persistent rules...")
        promoted_count = promote_hints_to_rules(run_id, self.project_id)
        if promoted_count > 0:
            print(f"[Supervisor] ✅ Promoted {promoted_count} new rules to project '{self.project_id}'")
            print(f"[Supervisor] These rules will be available for future runs")
        else:
            print(f"[Supervisor] No new rules promoted (no recurring patterns found)")

        print(f"\n{'='*60}")
        print(f"✅ AUTONOMOUS BUILD COMPLETE: {run_id}")
        print(f"{'='*60}\n")
        print(f"Phases executed: {len(results)}")
        print(f"Tokens used: {total_tokens:,}")
        print(f"Approved: {sum(1 for r in results if r['status'] == 'approved')}")
        print(f"Needs revision: {sum(1 for r in results if r['status'] == 'needs_revision')}")

        # Event trigger: Launch auxiliary Claude agents after run completion
        if self.enable_aux_agents:
            print(f"\n[Supervisor] 🤖 Launching auxiliary Claude agents...")
            try:
                agent_results = launch_agents(
                    event="run_complete",
                    run_id=run_id,
                    project_id=self.project_id,
                    context={
                        "phase_results": results,
                        "total_tokens": total_tokens,
                        "rules_promoted": promoted_count,
                        "summary": summary,
                    }
                )
                print(f"[Supervisor] ✅ Launched {len(agent_results)} agent(s)")
                for agent_result in agent_results:
                    print(f"[Supervisor]    - {agent_result['agent_role']}: {agent_result['status']}")
            except Exception as e:
                print(f"[Supervisor] ⚠️  Warning: Agent launch failed: {e}")
                print(f"[Supervisor]    Build completed successfully despite agent failure")

        return {
            "run_id": run_id,
            "phase_results": results,
            "total_tokens": total_tokens,
            "summary": summary,
            "rules_promoted": promoted_count,
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
    """Example: Run a simple autonomous build with real OpenAI integration"""

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("❌ Error: OPENAI_API_KEY environment variable not set")
        print("Please set it with: export OPENAI_API_KEY='your-key-here'")
        return None

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
            "description": "Add a /health endpoint to the FastAPI application that returns status 200 and {\"status\": \"healthy\"}",
            "task_category": "feature_scaffolding",
            "complexity": "low",
            "builder_mode": "compose",
            "acceptance_criteria": [
                "Endpoint responds at GET /health",
                "Returns 200 status code",
                "Returns JSON with status field"
            ],
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
    print("Autopack Supervisor - Autonomous Build Orchestration")
    print("Per v7 GPT Architect: OpenAI API with ModelSelector\n")

    result = example_build()

    if result:
        print(f"\n{'='*60}")
        print(f"Final Result Summary:")
        print(f"{'='*60}")
        print(f"Run ID: {result['run_id']}")
        print(f"Phases: {len(result['phase_results'])}")
        print(f"Total Tokens: {result['total_tokens']:,}")
        print(f"\nPhase Results:")
        for pr in result['phase_results']:
            status_icon = "✅" if pr['status'] == 'approved' else "⚠️"
            print(f"  {status_icon} {pr['phase_id']}: {pr['status']} ({pr.get('tokens_used', 0):,} tokens)")
