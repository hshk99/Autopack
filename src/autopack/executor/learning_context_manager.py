"""Learning Context Manager for Phase Execution.

Extracted from autonomous_executor.py as part of IMP-MAINT-001.
Manages project rules, run hints, and deliverables contracts for
Builder/Auditor context injection.

This module implements:
- Stage 0B: Loading persistent project rules (promoted from hints)
- Stage 0A: Loading run-local hints from earlier phases
- Mid-run refresh of rules when marker file changes
- Deliverables contract building for hard constraints

See LEARNED_RULES_README.md for the full learning pipeline architecture.
"""

import json
import logging
from datetime import datetime, timezone
from os.path import commonpath
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional

from autopack.learned_rules import (get_active_rules_for_phase,
                                    get_relevant_hints_for_phase,
                                    load_project_rules)

if TYPE_CHECKING:
    from autopack.executor.learning_pipeline import LearningPipeline

logger = logging.getLogger(__name__)


class LearningContextManager:
    """Manages learning context for phase execution.

    Provides:
    - Project rules loading and mid-run refresh
    - Run hints retrieval for within-run learning
    - Deliverables contract building for hard constraints
    - Rules marker tracking for planning coordination
    """

    def __init__(
        self,
        run_id: str,
        project_id: str,
        learning_pipeline: "LearningPipeline",
        get_project_slug_fn: Optional[Callable[[], str]] = None,
    ):
        """Initialize learning context manager.

        Args:
            run_id: Unique run identifier
            project_id: Project identifier
            learning_pipeline: Learning pipeline for effectiveness tracking
            get_project_slug_fn: Optional callback to get project slug
        """
        self.run_id = run_id
        self.project_id = project_id
        self.learning_pipeline = learning_pipeline
        self._get_project_slug = get_project_slug_fn

        # Project rules (Stage 0B - cross-run persistent)
        self.project_rules: List[Any] = []

        # Rules marker tracking for mid-run refresh
        self._rules_marker_path: Optional[Path] = None
        self._rules_marker_mtime: Optional[float] = None

    def load_project_learning_context(self) -> None:
        """Load project learned rules.

        This implements Stage 0B from LEARNED_RULES_README.md:
        - Loads persistent project rules from project_learned_rules.json
        - Rules are promoted from hints recorded during troubleshooting
        - These will be passed to Builder/Auditor for context-aware generation
        """
        project_id = self._get_project_slug() if self._get_project_slug else self.project_id
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

    def refresh_project_rules_if_updated(self) -> bool:
        """Check rules_updated.json mtime and reload project rules mid-run if advanced.

        Returns:
            True if rules were refreshed, False otherwise
        """
        if not self.project_id or not self._rules_marker_path:
            return False

        try:
            if not self._rules_marker_path.exists():
                return False

            mtime = self._rules_marker_path.stat().st_mtime
            if self._rules_marker_mtime is None or mtime > self._rules_marker_mtime:
                self._rules_marker_mtime = mtime
                self.project_rules = load_project_rules(self.project_id)
                logger.info(
                    f"[Learning] Reloaded project rules "
                    f"(now {len(self.project_rules)} rules) after marker update."
                )
                return True
        except Exception as e:
            logger.warning(f"[Learning] Failed to refresh project rules mid-run: {e}")

        return False

    def get_learning_context_for_phase(self, phase: Dict[str, Any]) -> Dict[str, Any]:
        """Get relevant learning context for a specific phase.

        Filters project rules and run hints relevant to this phase's
        task category for injection into Builder/Auditor prompts.

        IMP-LOOP-018: Also registers applied rules with learning pipeline
        for effectiveness tracking when phase completes.

        Args:
            phase: Phase specification dict

        Returns:
            Dict with 'project_rules' and 'run_hints' keys
        """
        # Get relevant project rules (Stage 0B - cross-run persistent rules)
        project_id = self._get_project_slug() if self._get_project_slug else self.project_id
        relevant_rules = get_active_rules_for_phase(project_id, phase)

        # Get run-local hints from earlier phases (Stage 0A - within-run hints)
        relevant_hints = get_relevant_hints_for_phase(self.run_id, phase, max_hints=5)

        if relevant_rules:
            logger.debug(f"  Found {len(relevant_rules)} relevant project rules for phase")
            # IMP-LOOP-018: Register applied rules for effectiveness tracking
            phase_id = phase.get("phase_id", "unknown")
            rule_ids = [r.rule_id for r in relevant_rules]
            self.learning_pipeline.register_applied_rules(phase_id, rule_ids)

        if relevant_hints:
            logger.debug(f"  Found {len(relevant_hints)} hints from earlier phases")

        return {
            "project_rules": relevant_rules,
            "run_hints": relevant_hints,
        }

    def build_deliverables_contract(self, phase: Dict[str, Any], phase_id: str) -> Optional[str]:
        """Build deliverables contract as hard constraint for Builder prompt.

        Per BUILD-050 Phase 1: Extract deliverables from phase scope and format
        them as non-negotiable requirements BEFORE learning hints.

        Args:
            phase: Phase specification dict
            phase_id: Phase identifier for logging

        Returns:
            Formatted deliverables contract string or None if no deliverables
        """
        from autopack.deliverables_validator import \
            extract_deliverables_from_scope

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
        learning_context = self.get_learning_context_for_phase(phase)
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

            # Also honor explicit "DO NOT create a top-level 'X/'" style hints
            if "DO NOT create" in hint_text and "'" in hint_text:
                try:
                    quoted = hint_text.split("'")[1]
                    if quoted.endswith("/") and quoted not in forbidden_patterns:
                        forbidden_patterns.append(quoted)
                except Exception:
                    pass

        # Heuristic defaults for common wrong roots
        expected_set = set(expected_paths)
        if any(p.startswith("src/autopack/research/tracer_bullet/") for p in expected_set):
            for bad in (
                "tracer_bullet/",
                "src/tracer_bullet/",
                "tests/tracer_bullet/",
            ):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)
            for bad in (
                "src/autopack/tracer_bullet.py",
                "src/autopack/tracer_bullet/",
            ):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)

        # Strict allowlist roots derived from expected deliverables
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
                "You may ONLY create/modify files under these root prefixes. "
                "Creating ANY file outside them will be rejected."
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

        # Chunk 0 core requirement: gold_set.json must be non-empty valid JSON
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
            f"[{phase_id}] Built deliverables contract: "
            f"{len(expected_paths)} required paths, {len(forbidden_patterns)} forbidden patterns"
        )

        return "\n".join(contract_parts)

    def mark_rules_updated(self, promoted_count: int) -> None:
        """Mark that project rules have been updated.

        This creates/updates a marker file that future planning agents can detect
        to know when rules have changed since the last plan was generated.

        Args:
            promoted_count: Number of new rules promoted in this run
        """
        try:
            marker_path = Path(".autonomous_runs") / self.project_id / "rules_updated.json"
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
            rules = load_project_rules(self.project_id)

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

            # Log to console for visibility
            logger.info(
                f"[PLANNING NOTICE] {promoted_count} new rules promoted. "
                f"Future planning should incorporate {len(rules)} total project rules."
            )

        except Exception as e:
            logger.warning(f"Failed to mark rules updated: {e}")
