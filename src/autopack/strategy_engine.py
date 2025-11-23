"""StrategyEngine for Autopack (Chunk C implementation)

Per §7 of v7 playbook:
- Reads ruleset + backlog
- Compiles per-run strategy
- Maps task categories to budgets and thresholds
"""

import json
from pathlib import Path
from typing import Dict, List, Optional

from .config import settings
from .issue_tracker import IssueTracker
from .strategy_schemas import (
    CategoryDefaults,
    PhaseStrategySlice,
    ProjectImplementationStrategy,
    ProjectRuleset,
    SafetyProfileConfig,
    TierStrategySlice,
)


class StrategyEngine:
    """Compiles project rulesets into per-run strategies"""

    # High-risk category defaults per §6 of v7 playbook
    HIGH_RISK_DEFAULTS = {
        "cross_cutting_refactor": CategoryDefaults(
            complexity="high",
            ci_profile="strict",
            max_builder_attempts=2,
            max_auditor_attempts=2,
            incident_token_cap=1_000_000,
            tier_max_minor_issues_multiplier=1.0,
            tier_max_major_issues_tolerated=0,
            auto_apply=False,
            auditor_profile="refactor_review",
            default_severity="major",
        ),
        "index_registry_change": CategoryDefaults(
            complexity="high",
            ci_profile="strict",
            max_builder_attempts=2,
            max_auditor_attempts=2,
            incident_token_cap=800_000,
            tier_max_minor_issues_multiplier=1.0,
            tier_max_major_issues_tolerated=0,
            auto_apply=False,
            auditor_profile="index_review",
            default_severity="major",
        ),
        "schema_contract_change": CategoryDefaults(
            complexity="high",
            ci_profile="strict",
            max_builder_attempts=2,
            max_auditor_attempts=3,
            incident_token_cap=1_000_000,
            tier_max_minor_issues_multiplier=1.0,
            tier_max_major_issues_tolerated=0,
            auto_apply=False,
            auditor_profile="schema_review",
            default_severity="major",
        ),
        "bulk_multi_file_operation": CategoryDefaults(
            complexity="high",
            ci_profile="strict",
            max_builder_attempts=1,
            max_auditor_attempts=2,
            incident_token_cap=1_500_000,
            tier_max_minor_issues_multiplier=1.0,
            tier_max_major_issues_tolerated=0,
            auto_apply=False,
            auditor_profile="bulk_review",
            default_severity="major",
        ),
        "security_auth_change": CategoryDefaults(
            complexity="high",
            ci_profile="strict",
            max_builder_attempts=2,
            max_auditor_attempts=3,
            incident_token_cap=800_000,
            tier_max_minor_issues_multiplier=0.5,
            tier_max_major_issues_tolerated=0,
            auto_apply=False,
            auditor_profile="security_review",
            default_severity="major",
        ),
    }

    # Normal category defaults
    NORMAL_CATEGORY_DEFAULTS = {
        "feature_scaffolding": CategoryDefaults(
            complexity="medium",
            ci_profile="normal",
            max_builder_attempts=3,
            max_auditor_attempts=2,
            incident_token_cap=500_000,
            auto_apply=True,
        ),
        "docs": CategoryDefaults(
            complexity="low",
            ci_profile="normal",
            max_builder_attempts=2,
            max_auditor_attempts=1,
            incident_token_cap=200_000,
            auto_apply=True,
        ),
        "tests": CategoryDefaults(
            complexity="low",
            ci_profile="normal",
            max_builder_attempts=3,
            max_auditor_attempts=1,
            incident_token_cap=300_000,
            auto_apply=True,
        ),
        "debt_cleanup": CategoryDefaults(
            complexity="medium",
            ci_profile="normal",
            max_builder_attempts=2,
            max_auditor_attempts=1,
            incident_token_cap=400_000,
            auto_apply=False,  # Cleanup requires review
            auditor_profile="debt_cleanup_review",
        ),
    }

    def __init__(self, project_id: str = "Autopack"):
        self.project_id = project_id

    def get_ruleset_path(self) -> Path:
        """Get path to project ruleset"""
        return Path(settings.autonomous_runs_dir).parent / f"project_ruleset_{self.project_id}.json"

    def load_ruleset(self) -> ProjectRuleset:
        """Load project ruleset or create default"""
        path = self.get_ruleset_path()
        if path.exists():
            return ProjectRuleset.model_validate_json(path.read_text())

        # Create default ruleset
        return self.create_default_ruleset()

    def create_default_ruleset(self) -> ProjectRuleset:
        """Create default ruleset with high-risk categories"""
        # Merge high-risk and normal defaults
        all_defaults = {**self.NORMAL_CATEGORY_DEFAULTS, **self.HIGH_RISK_DEFAULTS}

        # Create safety profiles
        safety_profiles = {
            "normal": SafetyProfileConfig(
                name="normal",
                description="Cost-conscious; minor issues can accumulate",
                minor_issue_aging_runs_threshold=3,
                minor_issue_aging_tiers_threshold=2,
                run_scope_preference="multi_tier",
            ),
            "safety_critical": SafetyProfileConfig(
                name="safety_critical",
                description="Correctness-first; any tier with major issues fails",
                minor_issue_aging_runs_threshold=2,
                minor_issue_aging_tiers_threshold=1,
                run_scope_preference="single_tier",
            ),
        }

        ruleset = ProjectRuleset(
            project_id=self.project_id,
            category_defaults=all_defaults,
            safety_profiles=safety_profiles,
        )

        # Save for future use
        path = self.get_ruleset_path()
        path.write_text(ruleset.model_dump_json(indent=2))

        return ruleset

    def save_ruleset(self, ruleset: ProjectRuleset) -> None:
        """Save project ruleset"""
        path = self.get_ruleset_path()
        path.write_text(ruleset.model_dump_json(indent=2))

    def compile_strategy(
        self,
        run_id: str,
        phases: Optional[List[Dict]] = None,
        tiers: Optional[List[Dict]] = None,
        safety_profile_override: Optional[str] = None,
        run_scope_override: Optional[str] = None,
    ) -> ProjectImplementationStrategy:
        """
        Compile a per-run strategy from ruleset and backlog.

        Per §7 of v7 playbook:
        - Reads ruleset
        - Checks issue backlog for aged issues
        - Computes per-phase and per-tier budgets
        - Returns frozen strategy for the run
        """
        ruleset = self.load_ruleset()

        # Determine safety profile
        safety_profile = safety_profile_override or ruleset.default_safety_profile
        run_scope = run_scope_override or ruleset.default_run_scope

        # Get safety profile config
        profile_config = ruleset.safety_profiles.get(
            safety_profile,
            SafetyProfileConfig(
                name=safety_profile,
                minor_issue_aging_runs_threshold=3,
                minor_issue_aging_tiers_threshold=2,
            ),
        )

        # Start strategy
        strategy = ProjectImplementationStrategy(
            run_id=run_id,
            project_id=self.project_id,
            safety_profile=safety_profile,
            run_scope=run_scope,
            run_token_cap=ruleset.run_token_cap,
            run_max_phases=ruleset.run_max_phases,
            run_max_duration_minutes=ruleset.run_max_duration_minutes,
            minor_issue_aging_runs_threshold=profile_config.minor_issue_aging_runs_threshold,
            minor_issue_aging_tiers_threshold=profile_config.minor_issue_aging_tiers_threshold,
        )

        # Add category strategies
        strategy.category_strategies = ruleset.category_defaults

        # Compute phase strategies if phases provided
        if phases:
            strategy.run_max_minor_issues_total = len(phases) * 3  # per §9.1

            for phase in phases:
                phase_id = phase.get("phase_id")
                task_category = phase.get("task_category")
                complexity = phase.get("complexity", "medium")
                builder_mode = phase.get("builder_mode")

                # Get category defaults
                if task_category and task_category in ruleset.category_defaults:
                    defaults = ruleset.category_defaults[task_category]
                else:
                    # Fallback to medium complexity defaults
                    defaults = CategoryDefaults()

                # Create phase strategy
                strategy.phase_strategies[phase_id] = PhaseStrategySlice(
                    task_category=task_category,
                    complexity=complexity,
                    builder_mode=builder_mode,
                    max_builder_attempts=defaults.max_builder_attempts,
                    max_auditor_attempts=defaults.max_auditor_attempts,
                    incident_token_cap=defaults.incident_token_cap,
                    ci_profile=defaults.ci_profile,
                    auto_apply=defaults.auto_apply,
                    auditor_profile=defaults.auditor_profile,
                )

        # Compute tier strategies if tiers provided
        if tiers and phases:
            for tier in tiers:
                tier_id = tier.get("tier_id")

                # Get phases for this tier
                tier_phases = [p for p in phases if p.get("tier_id") == tier_id]

                # Compute tier budgets per §9.2
                total_incident_cap = sum(
                    strategy.phase_strategies.get(
                        p.get("phase_id"), PhaseStrategySlice(
                            task_category=None,
                            complexity="medium",
                            builder_mode=None,
                            max_builder_attempts=3,
                            max_auditor_attempts=2,
                            incident_token_cap=500_000,
                            ci_profile="normal",
                            auto_apply=True,
                            auditor_profile=None,
                        )
                    ).incident_token_cap
                    for p in tier_phases
                )

                tier_token_cap = int(total_incident_cap * 3.0)
                tier_ci_run_cap = len(tier_phases) * 2

                # Determine minor issue tolerance based on safety profile
                if safety_profile == "safety_critical":
                    tier_max_minor = len(tier_phases)
                else:
                    tier_max_minor = len(tier_phases) * 2

                strategy.tier_strategies[tier_id] = TierStrategySlice(
                    tier_id=tier_id,
                    token_cap=tier_token_cap,
                    ci_run_cap=tier_ci_run_cap,
                    max_minor_issues_tolerated=tier_max_minor,
                    max_major_issues_tolerated=0,  # Zero tolerance for major per §9.2
                )

        return strategy

    def save_strategy(self, strategy: ProjectImplementationStrategy) -> Path:
        """Save compiled strategy for a run"""
        run_dir = Path(settings.autonomous_runs_dir) / strategy.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        path = run_dir / f"project_implementation_strategy_{strategy.version}.json"
        path.write_text(strategy.model_dump_json(indent=2))
        return path

    def dry_run_strategy(
        self,
        sample_phases: List[Dict],
        sample_tiers: List[Dict],
        safety_profile: str = "normal",
    ) -> ProjectImplementationStrategy:
        """
        Dry-run strategy compilation without creating a real run.
        Useful for testing ruleset changes.
        """
        return self.compile_strategy(
            run_id="dry-run-test",
            phases=sample_phases,
            tiers=sample_tiers,
            safety_profile_override=safety_profile,
        )
