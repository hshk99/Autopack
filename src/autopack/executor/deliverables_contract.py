"""
Deliverables Contract Module

Extracted from autonomous_executor.py as part of IMP-GOD-001.

Builds deliverables contracts as hard constraints for Builder prompts.
These contracts define:
- Required file paths that MUST be created
- Forbidden patterns from previous failed attempts
- Allowed roots (directory prefixes) for file creation
- JSON deliverable requirements

Key responsibilities:
- Extract expected deliverables from phase scope
- Build forbidden pattern lists from learning hints
- Generate formatted contract text for Builder prompts
"""

import logging
from os.path import commonpath
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class DeliverablesContractBuilder:
    """Builds deliverables contracts for Builder prompts.

    IMP-GOD-001: Extracted from AutonomousExecutor to reduce god file complexity.

    Per BUILD-050 Phase 1: Extract deliverables from phase scope and format them
    as non-negotiable requirements BEFORE learning hints.
    """

    def __init__(self, get_learning_context_fn: Callable[[Dict], Dict]):
        """Initialize deliverables contract builder.

        Args:
            get_learning_context_fn: Function to get learning context for a phase
        """
        self._get_learning_context_for_phase = get_learning_context_fn

    def build_contract(self, phase: Dict, phase_id: str) -> Optional[str]:
        """
        Build deliverables contract as hard constraint for Builder prompt.

        Per BUILD-050 Phase 1: Extract deliverables from phase scope and format them
        as non-negotiable requirements BEFORE learning hints.

        Args:
            phase: Phase specification dict
            phase_id: Phase identifier for logging

        Returns:
            Formatted deliverables contract string or None if no deliverables specified
        """
        from autopack.deliverables_validator import extract_deliverables_from_scope

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
        forbidden_patterns = self._extract_forbidden_patterns(phase, expected_paths)

        # Strict allowlist roots derived from expected deliverables.
        allowed_roots = self._derive_allowed_roots(expected_paths)

        # Build contract
        contract_parts = self._format_contract(
            expected_paths=expected_paths,
            common_prefix=common_prefix,
            forbidden_patterns=forbidden_patterns,
            allowed_roots=allowed_roots,
        )

        logger.info(
            f"[{phase_id}] Built deliverables contract: {len(expected_paths)} required paths, "
            f"{len(forbidden_patterns)} forbidden patterns"
        )

        return "\n".join(contract_parts)

    def _extract_forbidden_patterns(self, phase: Dict, expected_paths: List[str]) -> List[str]:
        """Extract forbidden patterns from learning hints and heuristics.

        Args:
            phase: Phase specification dict
            expected_paths: List of expected deliverable paths

        Returns:
            List of forbidden patterns
        """
        forbidden_patterns: List[str] = []
        learning_context = self._get_learning_context_for_phase(phase)
        run_hints = learning_context.get("run_hints", [])

        for hint in run_hints:
            hint_text = hint if isinstance(hint, str) else getattr(hint, "hint_text", "")
            # Extract patterns like "Wrong: path/to/file"
            if "Wrong:" in hint_text and "\u2192" in hint_text:  # Unicode arrow
                parts = hint_text.split("Wrong:")
                if len(parts) > 1:
                    wrong_part = parts[1].split("\u2192")[0].strip()
                    if wrong_part and wrong_part not in forbidden_patterns:
                        forbidden_patterns.append(wrong_part)

            # Also honor explicit "DO NOT create a top-level 'X/'" style hints.
            if "DO NOT create" in hint_text and "'" in hint_text:
                try:
                    quoted = hint_text.split("'")[1]
                    if quoted.endswith("/") and quoted not in forbidden_patterns:
                        forbidden_patterns.append(quoted)
                except Exception:
                    pass

        # Heuristic defaults: if expected paths indicate a specific required root,
        # explicitly forbid common wrong roots even before structured hints.
        expected_set = set(expected_paths)
        if any(p.startswith("src/autopack/research/tracer_bullet/") for p in expected_set):
            for bad in ("tracer_bullet/", "src/tracer_bullet/", "tests/tracer_bullet/"):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)
            # Also forbid common "near-miss" placements inside src/autopack/
            for bad in ("src/autopack/tracer_bullet.py", "src/autopack/tracer_bullet/"):
                if bad not in forbidden_patterns:
                    forbidden_patterns.append(bad)

        return forbidden_patterns

    def _derive_allowed_roots(self, expected_paths: List[str]) -> List[str]:
        """Derive allowed path roots from expected deliverables.

        Args:
            expected_paths: List of expected deliverable paths

        Returns:
            List of allowed root prefixes
        """
        expected_set = set(expected_paths)
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

        return allowed_roots

    def _format_contract(
        self,
        expected_paths: List[str],
        common_prefix: str,
        forbidden_patterns: List[str],
        allowed_roots: List[str],
    ) -> List[str]:
        """Format the deliverables contract text.

        Args:
            expected_paths: Required file paths
            common_prefix: Common path prefix
            forbidden_patterns: Patterns to forbid
            allowed_roots: Allowed root prefixes

        Returns:
            List of contract lines
        """
        expected_set = set(expected_paths)
        contract_parts = []
        contract_parts.append("=" * 80)
        contract_parts.append("\u26a0\ufe0f  CRITICAL FILE PATH REQUIREMENTS (NON-NEGOTIABLE)")
        contract_parts.append("=" * 80)
        contract_parts.append("")
        contract_parts.append("You MUST create files at these EXACT paths. This is not negotiable.")
        contract_parts.append("")

        if common_prefix and common_prefix != "/":
            contract_parts.append(f"\U0001f4c1 All files MUST be under: {common_prefix}/")
            contract_parts.append("")

        if allowed_roots:
            contract_parts.append("\u2705 ALLOWED ROOTS (HARD RULE):")
            contract_parts.append(
                "You may ONLY create/modify files under these root prefixes. "
                "Creating ANY file outside them will be rejected."
            )
            for r in allowed_roots:
                contract_parts.append(f"   \u2022 {r}")
            contract_parts.append("")

        if forbidden_patterns:
            contract_parts.append("\u274c FORBIDDEN patterns (from previous failed attempts):")
            for pattern in forbidden_patterns[:3]:  # Show first 3
                contract_parts.append(f"   \u2022 DO NOT use: {pattern}")
            contract_parts.append("")

        contract_parts.append("\u2713 REQUIRED file paths:")
        for path in expected_paths:
            contract_parts.append(f"   {path}")
        contract_parts.append("")

        # Chunk 0 core requirement: gold_set.json must be non-empty valid JSON.
        if any(
            p.endswith("src/autopack/research/evaluation/gold_set.json")
            or p.endswith("/gold_set.json")
            for p in expected_set
        ):
            contract_parts.append("\U0001f9fe JSON DELIVERABLES (HARD RULE):")
            contract_parts.append(
                "- `src/autopack/research/evaluation/gold_set.json` MUST be valid, non-empty JSON."
            )
            contract_parts.append(
                "- Minimal acceptable placeholder is `[]` (empty array) \u2014 but the file must NOT be blank."
            )
            contract_parts.append("- Any empty/invalid JSON will be rejected before patch apply.")
            contract_parts.append("")

        contract_parts.append("=" * 80)
        contract_parts.append("")

        return contract_parts
