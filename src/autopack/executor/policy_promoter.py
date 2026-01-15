"""
ROAD-F: Policy Promotion from Validated Fixes

Auto-promote validated mitigations into strategy engine,
learned rules, and pattern expansion to prevent recurrence.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class PromovedRule:
    """Rule promoted from validated fix."""

    rule_id: str
    mitigation: str
    success_rate: float
    applicable_phases: List[str]
    promoted_at: str
    promotion_level: str  # strategy_engine, prevention_prompts, pattern_expansion

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "rule_id": self.rule_id,
            "mitigation": self.mitigation,
            "success_rate": self.success_rate,
            "applicable_phases": self.applicable_phases,
            "promoted_at": self.promoted_at,
            "promotion_level": self.promotion_level,
        }


class PolicyPromoter:
    """Promote validated rules to prevent future issues."""

    SUCCESS_THRESHOLD = 0.9  # 90% success to promote

    def __init__(self, policy_dir: Path = None):
        """Initialize promoter.

        Args:
            policy_dir: Directory containing policy files
        """
        self.policy_dir = policy_dir or Path("src/autopack/executor/policies")
        self.promoted_rules: Dict[str, PromovedRule] = {}

    def promote_rule(
        self,
        rule_id: str,
        mitigation: str,
        success_rate: float,
        applicable_phases: List[str],
    ) -> Optional[PromovedRule]:
        """Promote rule from validation data.

        Args:
            rule_id: Unique rule identifier
            mitigation: Mitigation strategy
            success_rate: Validation success rate
            applicable_phases: Phases this applies to

        Returns:
            PromovedRule if threshold met, None otherwise
        """
        if success_rate < self.SUCCESS_THRESHOLD:
            logger.info(
                f"Rule {rule_id} not promoted: "
                f"success_rate {success_rate:.1%} < threshold {self.SUCCESS_THRESHOLD:.1%}"
            )
            return None

        promoted = PromovedRule(
            rule_id=rule_id,
            mitigation=mitigation,
            success_rate=success_rate,
            applicable_phases=applicable_phases,
            promoted_at=datetime.now().isoformat(),
            promotion_level="strategy_engine",
        )

        self.promoted_rules[rule_id] = promoted
        logger.info(f"✅ Promoted rule: {rule_id} with {success_rate:.1%} success rate")

        return promoted

    def save_promoted_rules(self, output_path: Path) -> None:
        """Save promoted rules to file.

        Args:
            output_path: Path to save rules
        """
        output_path.parent.mkdir(parents=True, exist_ok=True)

        rules_data = {
            "promoted_at": datetime.now().isoformat(),
            "count": len(self.promoted_rules),
            "rules": {rule_id: rule.to_dict() for rule_id, rule in self.promoted_rules.items()},
        }

        with open(output_path, "w") as f:
            json.dump(rules_data, f, indent=2)

        logger.info(f"Saved {len(self.promoted_rules)} promoted rules to {output_path}")

    def get_rules_for_phase(self, phase_id: str) -> List[PromovedRule]:
        """Get promoted rules applicable to phase.

        Args:
            phase_id: Phase identifier

        Returns:
            List of applicable promoted rules
        """
        applicable = [
            rule
            for rule in self.promoted_rules.values()
            if not rule.applicable_phases or phase_id in rule.applicable_phases
        ]
        return applicable

    def generate_prevention_prompts(self) -> Dict[str, str]:
        """Generate prevention prompts from promoted rules.

        Returns:
            Dictionary of phase_id -> prevention_prompt
        """
        prompts = {}

        # Group rules by applicable phases
        phase_rules: Dict[str, List[str]] = {}
        for rule in self.promoted_rules.values():
            for phase in rule.applicable_phases or ["*"]:
                if phase not in phase_rules:
                    phase_rules[phase] = []
                phase_rules[phase].append(rule.mitigation)

        # Generate prompts
        for phase, mitigations in phase_rules.items():
            prompt = f"Based on past successful fixes in {phase}:\n\n" f"Recommended approaches:\n"
            for mitigation in mitigations:
                prompt += f"- {mitigation}\n"

            prompts[phase] = prompt

        return prompts


# Global promoter instance
_promoter = None


def get_promoter(policy_dir: Path = None) -> PolicyPromoter:
    """Get or create global promoter."""
    global _promoter
    if _promoter is None:
        _promoter = PolicyPromoter(policy_dir)
    return _promoter
