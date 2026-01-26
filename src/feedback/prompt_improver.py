"""Prompt improvement based on failure history."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PromptEnhancement:
    """Represents an enhancement to add to a prompt."""

    category: str  # 'warning', 'pattern', 'context', 'checklist'
    content: str
    priority: str  # 'high', 'medium', 'low'
    source: str  # Where this enhancement came from
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


class PromptImprover:
    """Adjusts prompts to prevent recurring failures."""

    def __init__(
        self,
        failure_analyzer=None,
        metrics_db=None,
        prompt_template_path: Optional[str] = None,
    ):
        """Initialize with failure analyzer and metrics database."""
        self.failure_analyzer = failure_analyzer
        self.metrics_db = metrics_db
        self.template_path = Path(prompt_template_path) if prompt_template_path else None
        self.base_prompts: Dict[str, str] = {}
        self.enhancement_cache: Dict[str, List[PromptEnhancement]] = {}

        if self.template_path and self.template_path.exists():
            self._load_templates()

    def _load_templates(self) -> Dict[str, str]:
        """Load base prompt templates from file."""
        if not self.template_path or not self.template_path.exists():
            return {}

        with open(self.template_path, "r", encoding="utf-8") as f:
            content = f.read()

        # Parse templates by phase type
        template_pattern = r"## Template: (\w+)\n```\n(.*?)```"
        matches = re.findall(template_pattern, content, re.DOTALL)

        self.base_prompts = {name: template for name, template in matches}
        return self.base_prompts

    def get_improved_prompt(self, phase_id: str, phase_type: str, context: Dict[str, Any]) -> str:
        """Generate improved prompt with failure-prevention context."""
        # Get base prompt
        base = self.base_prompts.get(phase_type, context.get("original_prompt", ""))

        # Gather enhancements
        enhancements: List[PromptEnhancement] = []

        # Add warnings for recurring failures
        warnings = self._get_failure_warnings(phase_id, phase_type)
        enhancements.extend(warnings)

        # Add successful patterns
        patterns = self._get_success_patterns(phase_type)
        enhancements.extend(patterns)

        # Add context-specific guidance
        guidance = self._get_contextual_guidance(phase_type, context)
        enhancements.extend(guidance)

        # Cache enhancements for this phase
        self.enhancement_cache[phase_id] = enhancements

        # Compose final prompt
        return self._compose_prompt(base, enhancements, context)

    def _get_failure_warnings(self, phase_id: str, phase_type: str) -> List[PromptEnhancement]:
        """Get warnings from past failures for this phase type."""
        warnings = []

        if not self.failure_analyzer:
            return warnings

        # Get failure statistics
        stats = self.failure_analyzer.get_failure_statistics()

        # Check for recurring patterns
        for pattern in stats.get("top_patterns", []):
            if pattern.get("occurrence_count", 0) >= 2:
                failure_type = pattern.get("failure_type", "unknown")
                resolution = pattern.get("resolution", "")

                warning_content = f"RECURRING ISSUE ({failure_type}): "
                if resolution:
                    warning_content += f"Previous fix: {resolution}"
                else:
                    warning_content += (
                        "This failure type has occurred multiple times. Check carefully."
                    )

                warnings.append(
                    PromptEnhancement(
                        category="warning",
                        content=warning_content,
                        priority="high",
                        source=f"failure_pattern:{pattern.get('pattern_hash', '')}",
                    )
                )

        # Check phase-specific failures
        phase_failures = self._get_phase_failures(phase_id)
        for failure in phase_failures:
            warnings.append(
                PromptEnhancement(
                    category="warning",
                    content=(
                        f"Previous attempt failed: "
                        f"{failure.get('error_summary', 'Unknown error')}"
                    ),
                    priority="high",
                    source=f"phase_history:{phase_id}",
                )
            )

        return warnings

    def _get_phase_failures(self, phase_id: str) -> List[Dict]:
        """Get failures specific to this phase."""
        if not self.metrics_db:
            return []

        outcomes = self.metrics_db.get_phase_outcomes()
        return [
            o for o in outcomes if o.get("phase_id") == phase_id and o.get("outcome") == "failed"
        ]

    def _get_success_patterns(self, phase_type: str) -> List[PromptEnhancement]:
        """Get patterns from past successes for this phase type."""
        patterns = []

        if not self.metrics_db:
            return patterns

        # Get successful phases of same type
        outcomes = self.metrics_db.get_phase_outcomes()
        successes = [
            o
            for o in outcomes
            if o.get("outcome") == "success"
            and self._extract_phase_type(o.get("phase_id", "")) == phase_type
        ]

        if len(successes) >= 3:
            # Calculate average duration for successful phases
            durations = [
                o.get("duration_seconds", 0) for o in successes if o.get("duration_seconds")
            ]
            if durations:
                avg_duration = sum(durations) / len(durations)
                patterns.append(
                    PromptEnhancement(
                        category="pattern",
                        content=(
                            f"Similar phases typically complete in "
                            f"{int(avg_duration / 60)} minutes"
                        ),
                        priority="low",
                        source="success_metrics",
                    )
                )

        return patterns

    def _get_contextual_guidance(self, phase_type: str, context: Dict) -> List[PromptEnhancement]:
        """Get context-specific guidance based on phase type."""
        guidance = []

        # Common issues by phase type
        type_guidance = {
            "tel": [
                "Ensure EventLogger uses append mode for JSONL files",
                "Add proper file locking for concurrent access",
            ],
            "mem": [
                "Use parameterized queries to prevent SQL injection",
                "Ensure database connections are properly closed",
            ],
            "gen": [
                "Validate dependency graph has no cycles before planning",
                "Ensure file paths use platform-appropriate separators",
            ],
            "loop": [
                "Add rate limiting to prevent excessive feedback cycles",
                "Ensure graceful handling when dependencies are unavailable",
            ],
        }

        # Try full phase type first, then 3-char prefix
        phase_key = phase_type.lower() if phase_type else ""
        if phase_key not in type_guidance:
            phase_key = phase_type[:3].lower() if phase_type else ""
        if phase_key in type_guidance:
            for tip in type_guidance[phase_key]:
                guidance.append(
                    PromptEnhancement(
                        category="context",
                        content=f"TIP: {tip}",
                        priority="medium",
                        source=f"type_guidance:{phase_key}",
                    )
                )

        return guidance

    def _extract_phase_type(self, phase_id: str) -> str:
        """Extract type from phase ID (e.g., 'tel001' -> 'tel')."""
        match = re.match(r"([a-z]+)", phase_id.lower())
        return match.group(1) if match else ""

    def _compose_prompt(
        self, base: str, enhancements: List[PromptEnhancement], context: Dict
    ) -> str:
        """Compose final prompt with all components."""
        sections = []

        # Sort enhancements by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        sorted_enhancements = sorted(enhancements, key=lambda e: priority_order.get(e.priority, 3))

        # Group by category
        warnings = [e for e in sorted_enhancements if e.category == "warning"]
        patterns = [e for e in sorted_enhancements if e.category == "pattern"]
        guidance = [e for e in sorted_enhancements if e.category in ["context", "checklist"]]

        # Build warning section
        if warnings:
            sections.append("## IMPORTANT WARNINGS (from failure history)")
            for w in warnings:
                sections.append(w.content)
            sections.append("")

        # Add base prompt
        sections.append(base)

        # Add guidance section
        if guidance:
            sections.append("\n## Guidance (from success patterns)")
            for g in guidance:
                sections.append(g.content)

        # Add success patterns
        if patterns:
            sections.append("\n## Historical Context")
            for p in patterns:
                sections.append(p.content)

        return "\n".join(sections)

    def record_prompt_outcome(
        self, phase_id: str, prompt_hash: str, outcome: str, feedback: Optional[str] = None
    ):
        """Record outcome of a prompt execution for learning."""
        if not self.metrics_db:
            return

        self.metrics_db.record_phase_outcome(
            phase_id=phase_id,
            outcome=outcome,
            metadata={
                "prompt_hash": prompt_hash,
                "feedback": feedback,
                "enhancements_applied": len(self.enhancement_cache.get(phase_id, [])),
            },
        )

    def get_enhancement_summary(self, phase_id: str) -> str:
        """Get summary of enhancements applied to a phase."""
        enhancements = self.enhancement_cache.get(phase_id, [])
        if not enhancements:
            return "No enhancements applied"

        lines = [f"Enhancements for {phase_id}:"]
        for e in enhancements:
            lines.append(f"  [{e.priority}] {e.category}: {e.content[:50]}...")

        return "\n".join(lines)

    def export_state(self, output_path: str) -> None:
        """Export improver state to JSON."""
        output = {
            "templates_loaded": len(self.base_prompts),
            "enhancement_cache_size": sum(len(v) for v in self.enhancement_cache.values()),
            "template_types": list(self.base_prompts.keys()),
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)
