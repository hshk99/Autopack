"""Claude Agent Launcher

Per GPT recommendation: Event-driven launcher for auxiliary Claude agents.

Integrates with learned rules system (Stage 0A + 0B):
- Planner agent receives learned rules → adjusts plans
- Postmortem agent analyzes promoted rules → generates lessons
- Marketing agent incorporates rules into release notes

Usage:
    # Manual launch
    python scripts/launch_claude_agents.py --project-id MyProject --event project_init

    # Called by Autopack on run completion
    python scripts/launch_claude_agents.py --project-id MyProject --run-id auto-001 --event run_complete

    # Launch specific agents only
    python scripts/launch_claude_agents.py --project-id MyProject --agents planner brainstormer
"""

import os
import sys
import argparse
import yaml
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.autopack.learned_rules import (
    load_project_learned_rules,
    load_run_rule_hints,
    format_rules_for_prompt,
    format_hints_for_prompt,
)


class AgentLauncher:
    """Launches Claude agents for planning, brainstorming, marketing, postmortem"""

    def __init__(self, project_id: str, config_path: Optional[str] = None):
        """Initialize agent launcher

        Args:
            project_id: Project identifier
            config_path: Path to project_types.yaml (defaults to config/project_types.yaml)
        """
        self.project_id = project_id
        self.config_path = config_path or Path("config/project_types.yaml")
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load project types and agent role definitions"""
        if not Path(self.config_path).exists():
            raise FileNotFoundError(f"Config not found: {self.config_path}")

        with open(self.config_path) as f:
            return yaml.safe_load(f)

    def _load_project_config(self) -> Dict:
        """Load project-specific config with type resolution

        Per GPT recommendation: Hybrid approach with central + local overrides
        """
        # Try to load local project config
        local_config_path = Path(f"./{self.project_id}/config/project.yaml")
        if local_config_path.exists():
            with open(local_config_path) as f:
                local_config = yaml.safe_load(f)
        else:
            # Default to autopack_like if no local config
            local_config = {"project_type": "autopack_like"}

        project_type = local_config.get("project_type", "autopack_like")

        # Get central template
        if project_type not in self.config["project_types"]:
            raise ValueError(f"Unknown project type: {project_type}")

        template = self.config["project_types"][project_type].copy()

        # Apply local overrides (per GPT hybrid approach)
        if "agent_overrides" in local_config:
            overrides = local_config["agent_overrides"]

            # Start with default agents from template
            agents = set(template.get("default_agents", []))

            # Remove disabled agents
            if "disabled" in overrides:
                agents -= set(overrides["disabled"])

            # Add enabled agents
            if "enabled" in overrides:
                agents |= set(overrides["enabled"])

            template["default_agents"] = list(agents)

        return template

    def get_enabled_agents(self, event: str) -> List[str]:
        """Get list of agents to run for this event

        Args:
            event: Event type (project_init, run_complete, manual)

        Returns:
            List of agent role names to launch
        """
        project_config = self._load_project_config()
        all_agents = project_config.get("default_agents", [])

        # Filter by event
        if event == "project_init":
            # Only planner on project init
            return [a for a in all_agents if a == "planner"]
        elif event == "run_complete":
            # Postmortem + marketing on run complete
            return [a for a in all_agents if a in ("postmortem", "marketing_pack")]
        else:
            # Manual: run all configured agents
            return all_agents

    def launch_agent(
        self, agent_role: str, run_id: Optional[str] = None, context: Optional[Dict] = None
    ) -> Dict:
        """Launch a single Claude agent

        Args:
            agent_role: Role name (planner, brainstormer, etc.)
            run_id: Optional run ID (for postmortem agent)
            context: Additional context to pass to agent

        Returns:
            Dict with agent result (output_files, tokens_used, success)
        """
        print(f"\n[AgentLauncher] 🚀 Launching agent: {agent_role}")

        # Get agent definition
        if agent_role not in self.config["agent_roles"]:
            raise ValueError(f"Unknown agent role: {agent_role}")

        agent_def = self.config["agent_roles"][agent_role]

        # Build prompt
        prompt = self._build_agent_prompt(agent_role, agent_def, run_id, context)

        # Call Claude API
        result = self._call_claude_api(
            prompt=prompt,
            model=agent_def.get("model", "claude-sonnet-3-5"),
            max_tokens=agent_def.get("max_tokens", 100_000),
        )

        if not result["success"]:
            print(f"[AgentLauncher] ❌ Agent failed: {result['error']}")
            return result

        # Save outputs
        output_files = self._save_agent_outputs(agent_role, agent_def, result["content"], run_id)

        print("[AgentLauncher] ✅ Agent completed")
        print(f"[AgentLauncher]    Tokens used: {result['tokens_used']:,}")
        print(f"[AgentLauncher]    Outputs: {len(output_files)} files")

        return {
            "success": True,
            "agent_role": agent_role,
            "output_files": output_files,
            "tokens_used": result["tokens_used"],
        }

    def _build_agent_prompt(
        self, agent_role: str, agent_def: Dict, run_id: Optional[str], context: Optional[Dict]
    ) -> str:
        """Build prompt for agent with learned rules integration

        Per GPT recommendation: Agents receive learned rules as input
        """
        # Load prompt template
        template_path = Path(agent_def["prompt_template"])
        if not template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {template_path}")

        with open(template_path) as f:
            template = f.read()

        # Build context dict
        prompt_context = context or {}

        # Add learned rules (Stage 0B integration)
        learned_rules = load_project_learned_rules(self.project_id)
        prompt_context["learned_rules"] = format_rules_for_prompt(learned_rules)

        # For postmortem agent: add run hints and promoted rules
        if agent_role == "postmortem" and run_id:
            run_hints = load_run_rule_hints(run_id)
            prompt_context["run_hints"] = format_hints_for_prompt(run_hints)

            # Get promoted rules from this run
            # (Simplified: in production, track which rules were promoted in this specific run)
            prompt_context["promoted_count"] = len(
                [
                    h
                    for h in run_hints
                    if len([h2 for h2 in run_hints if h2.source_issue_keys == h.source_issue_keys])
                    >= 2
                ]
            )
            prompt_context["promoted_rules"] = format_rules_for_prompt(learned_rules[:5])  # Last 5

        # Add project context
        prompt_context.setdefault("project_name", self.project_id)
        prompt_context.setdefault("project_type", "Not specified")
        prompt_context.setdefault("run_id", run_id or "N/A")

        # Format template (simple string replacement for now)
        prompt = template
        for key, value in prompt_context.items():
            placeholder = "{" + key + "}"
            prompt = prompt.replace(placeholder, str(value))

        return prompt

    def _call_claude_api(self, prompt: str, model: str, max_tokens: int) -> Dict:
        """Call Claude API to execute agent

        TODO: Implement actual Claude API call via Anthropic SDK
        For now, returns stub

        Args:
            prompt: Full prompt for agent
            model: Claude model to use
            max_tokens: Token budget

        Returns:
            Dict with success, content, tokens_used, error
        """
        # Check for API key
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            return {
                "success": False,
                "error": "ANTHROPIC_API_KEY not set",
                "content": "",
                "tokens_used": 0,
            }

        # TODO: Implement actual API call
        # For now, return stub indicating implementation needed
        print("[AgentLauncher] ⚠️  Claude API call not implemented yet")
        print(f"[AgentLauncher]    Model: {model}, Max tokens: {max_tokens:,}")
        print(f"[AgentLauncher]    Prompt length: {len(prompt)} chars")

        return {
            "success": True,
            "content": f"# Agent Output (Stub)\n\nAgent would generate output here.\n\nPrompt received: {len(prompt)} chars\nLearned rules: {'Yes' if '{learned_rules}' not in prompt else 'No'}",
            "tokens_used": 1000,  # Stub
            "model": model,
        }

    def _save_agent_outputs(
        self, agent_role: str, agent_def: Dict, content: str, run_id: Optional[str]
    ) -> List[str]:
        """Save agent outputs to configured file paths

        Args:
            agent_role: Role name
            agent_def: Agent definition with outputs list
            content: Generated content
            run_id: Optional run ID (for filename templating)

        Returns:
            List of saved file paths
        """
        output_files = []
        outputs = agent_def.get("outputs", [])

        if not outputs:
            print(f"[AgentLauncher] ⚠️  No outputs configured for {agent_role}")
            return []

        # For simplicity, save same content to all output files
        # (In production, agent would generate structured output for each file)
        for output_path in outputs:
            # Template run_id if present
            if run_id:
                output_path = output_path.replace("{run_id}", run_id)

            # Ensure directory exists
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)

            # Save content
            with open(output_file, "w") as f:
                f.write(content)

            output_files.append(str(output_file))
            print(f"[AgentLauncher]    Saved: {output_file}")

        return output_files

    def launch_for_event(
        self,
        event: str,
        run_id: Optional[str] = None,
        agents: Optional[List[str]] = None,
        context: Optional[Dict] = None,
    ) -> Dict:
        """Launch agents for a specific event

        Args:
            event: Event type (project_init, run_complete, manual)
            run_id: Optional run ID
            agents: Optional list of specific agents to run (overrides event filtering)
            context: Additional context

        Returns:
            Dict with results per agent
        """
        print(f"\n{'=' * 60}")
        print(f"🤖 Agent Launcher: {event}")
        print(f"{'=' * 60}\n")
        print(f"[AgentLauncher] Project: {self.project_id}")
        if run_id:
            print(f"[AgentLauncher] Run ID: {run_id}")

        # Get agents to launch
        if agents:
            agents_to_launch = agents
        else:
            agents_to_launch = self.get_enabled_agents(event)

        print(f"[AgentLauncher] Agents to launch: {', '.join(agents_to_launch)}")

        # Launch each agent
        results = {}
        total_tokens = 0

        for agent_role in agents_to_launch:
            try:
                result = self.launch_agent(agent_role, run_id, context)
                results[agent_role] = result
                total_tokens += result.get("tokens_used", 0)
            except Exception as e:
                print(f"[AgentLauncher] ⚠️  Agent {agent_role} failed: {e}")
                results[agent_role] = {"success": False, "error": str(e), "tokens_used": 0}

        # Summary
        print(f"\n{'=' * 60}")
        print("✅ Agent Launcher Complete")
        print(f"{'=' * 60}\n")
        print(f"Agents launched: {len(results)}")
        print(f"Total tokens: {total_tokens:,}")
        print(f"Successes: {sum(1 for r in results.values() if r.get('success'))}")
        print(f"Failures: {sum(1 for r in results.values() if not r.get('success'))}")

        return {
            "event": event,
            "project_id": self.project_id,
            "run_id": run_id,
            "agents_launched": len(results),
            "results": results,
            "total_tokens": total_tokens,
        }


def main():
    parser = argparse.ArgumentParser(
        description="Launch Claude agents for planning, brainstorming, marketing, postmortem"
    )
    parser.add_argument("--project-id", required=True, help="Project identifier")
    parser.add_argument(
        "--event",
        choices=["project_init", "run_complete", "manual"],
        default="manual",
        help="Event type",
    )
    parser.add_argument("--run-id", help="Run ID (for postmortem agent)")
    parser.add_argument(
        "--agents", nargs="+", help="Specific agents to launch (overrides event filtering)"
    )
    parser.add_argument("--config", help="Path to project_types.yaml")

    args = parser.parse_args()

    # Create launcher
    launcher = AgentLauncher(project_id=args.project_id, config_path=args.config)

    # Launch agents
    result = launcher.launch_for_event(event=args.event, run_id=args.run_id, agents=args.agents)

    # Exit code based on success
    if all(r.get("success") for r in result["results"].values()):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
