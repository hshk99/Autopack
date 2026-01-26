"""Autonomous Phase 2 wave planning for IMP grouping."""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Set

import json


@dataclass
class WavePlan:
    """Represents a complete wave plan."""

    waves: Dict[int, List[str]]  # wave_number -> list of imp_ids
    validation_passed: bool
    validation_errors: List[str]
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class AutonomousWavePlanner:
    """Plans wave groupings for discovered IMPs.

    Takes discovered IMPs from Phase 1 and groups them into optimal waves
    based on dependencies, file conflicts, and parallelization potential.
    """

    def __init__(self, discovered_imps: List[Dict[str, Any]]) -> None:
        """Initialize with list of discovered IMPs.

        Args:
            discovered_imps: List of IMP dictionaries with keys:
                - imp_id: Unique identifier (e.g., "IMP-GEN-001")
                - title: Human-readable title
                - files_affected: List of file paths this IMP modifies
                - dependencies: List of imp_ids this IMP depends on
        """
        self.imps = {imp["imp_id"]: imp for imp in discovered_imps}
        self.dependency_graph: Dict[str, Set[str]] = {}
        self.file_map: Dict[str, Set[str]] = {}  # file -> set of imp_ids
        self._build_graphs()

    def _build_graphs(self) -> None:
        """Build dependency and file conflict graphs."""
        for imp_id, imp in self.imps.items():
            # Build dependency graph
            self.dependency_graph[imp_id] = set(imp.get("dependencies", []))

            # Build file conflict map
            for file in imp.get("files_affected", []):
                if file not in self.file_map:
                    self.file_map[file] = set()
                self.file_map[file].add(imp_id)

    def plan_waves(self) -> WavePlan:
        """Generate optimal wave groupings.

        Returns:
            WavePlan with waves assigned to maximize parallelization
            while respecting dependencies and avoiding file conflicts.
        """
        waves: Dict[int, List[str]] = {}
        assigned: Set[str] = set()
        current_wave = 1

        while len(assigned) < len(self.imps):
            # Find all IMPs that can be in current wave
            candidates = self._find_wave_candidates(assigned, current_wave, waves)

            if not candidates:
                # Deadlock detection
                unassigned = set(self.imps.keys()) - assigned
                return WavePlan(
                    waves=waves,
                    validation_passed=False,
                    validation_errors=[f"Deadlock: cannot assign IMPs {unassigned}"],
                )

            waves[current_wave] = candidates
            assigned.update(candidates)
            current_wave += 1

        # Validate the plan
        errors = self._validate_plan(waves)

        return WavePlan(
            waves=waves,
            validation_passed=len(errors) == 0,
            validation_errors=errors,
        )

    def _find_wave_candidates(
        self,
        assigned: Set[str],
        wave_num: int,
        current_waves: Dict[int, List[str]],
    ) -> List[str]:
        """Find IMPs that can be assigned to current wave.

        Args:
            assigned: Set of already assigned IMP IDs
            wave_num: Current wave number being filled
            current_waves: Waves assigned so far

        Returns:
            List of IMP IDs that can be assigned to this wave
        """
        candidates: List[str] = []
        wave_files: Set[str] = set()

        for imp_id, imp in self.imps.items():
            if imp_id in assigned:
                continue

            # Check dependencies are satisfied
            deps = self.dependency_graph.get(imp_id, set())
            if not deps.issubset(assigned):
                continue

            # Check file conflicts with other candidates in this wave
            imp_files = set(imp.get("files_affected", []))
            if imp_files & wave_files:
                continue  # File conflict

            candidates.append(imp_id)
            wave_files.update(imp_files)

        return candidates

    def _validate_plan(self, waves: Dict[int, List[str]]) -> List[str]:
        """Validate the wave plan.

        Args:
            waves: The planned wave assignments

        Returns:
            List of validation error messages (empty if valid)
        """
        errors: List[str] = []

        for wave_num, imp_ids in waves.items():
            # Check for same-wave dependencies
            for imp_id in imp_ids:
                deps = self.dependency_graph.get(imp_id, set())
                same_wave_deps = deps & set(imp_ids)
                if same_wave_deps:
                    errors.append(
                        f"Wave {wave_num}: {imp_id} depends on same-wave IMPs {same_wave_deps}"
                    )

            # Check for file conflicts
            files_in_wave: Dict[str, List[str]] = {}
            for imp_id in imp_ids:
                imp = self.imps[imp_id]
                for file in imp.get("files_affected", []):
                    if file not in files_in_wave:
                        files_in_wave[file] = []
                    files_in_wave[file].append(imp_id)

            for file, touching_imps in files_in_wave.items():
                if len(touching_imps) > 1:
                    errors.append(
                        f"Wave {wave_num}: File conflict on {file} between {touching_imps}"
                    )

        return errors

    def export_wave_plan(self, output_path: str) -> None:
        """Export wave plan to JSON file.

        Args:
            output_path: Path to write the JSON output
        """
        plan = self.plan_waves()

        output = {
            "generated_at": plan.generated_at,
            "validation_passed": plan.validation_passed,
            "validation_errors": plan.validation_errors,
            "total_waves": len(plan.waves),
            "total_imps": sum(len(imps) for imps in plan.waves.values()),
            "waves": [
                {
                    "wave_number": wave_num,
                    "imp_count": len(imp_ids),
                    "imp_ids": imp_ids,
                    "phases": [
                        {
                            "id": self._imp_to_phase_id(imp_id),
                            "imp_id": imp_id,
                            "title": self.imps[imp_id].get("title", ""),
                            "worktree_path": (
                                f"C:\\dev\\Autopack_w{wave_num}_{self._imp_to_phase_id(imp_id)}"
                            ),
                            "branch": (
                                f"wave{wave_num}/{self._imp_to_phase_id(imp_id)}-"
                                f"{self._slugify(self.imps[imp_id].get('title', ''))}"
                            ),
                            "files": self.imps[imp_id].get("files_affected", []),
                            "dependencies": list(self.dependency_graph.get(imp_id, set())),
                        }
                        for imp_id in imp_ids
                    ],
                }
                for wave_num, imp_ids in sorted(plan.waves.items())
            ],
        }

        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(output, f, indent=2)

    def _imp_to_phase_id(self, imp_id: str) -> str:
        """Convert IMP-XXX-NNN to xxxnnn format.

        Args:
            imp_id: IMP identifier (e.g., "IMP-GEN-001")

        Returns:
            Phase ID format (e.g., "gen001")
        """
        # IMP-GEN-001 -> gen001
        parts = imp_id.split("-")
        if len(parts) >= 3:
            return f"{parts[1].lower()}{parts[2]}"
        return imp_id.lower().replace("-", "")

    def _slugify(self, text: str) -> str:
        """Convert title to URL-friendly slug.

        Args:
            text: Title to slugify

        Returns:
            URL-friendly slug (max 50 chars)
        """
        slug = text.lower()
        slug = re.sub(r"[^a-z0-9\s-]", "", slug)
        slug = re.sub(r"[\s_]+", "-", slug)
        return slug[:50]

    def get_summary(self) -> str:
        """Get human-readable wave plan summary.

        Returns:
            Multi-line summary string of the wave plan
        """
        plan = self.plan_waves()

        lines = [f"Wave Plan Summary ({plan.generated_at})"]
        lines.append(f"Validation: {'PASSED' if plan.validation_passed else 'FAILED'}")

        if plan.validation_errors:
            lines.append("\nValidation Errors:")
            for error in plan.validation_errors:
                lines.append(f"  - {error}")

        lines.append(f"\nTotal Waves: {len(plan.waves)}")
        for wave_num, imp_ids in sorted(plan.waves.items()):
            lines.append(f"\nWave {wave_num} ({len(imp_ids)} IMPs):")
            for imp_id in imp_ids:
                title = self.imps[imp_id].get("title", "Unknown")
                lines.append(f"  - [{imp_id}] {title}")

        return "\n".join(lines)
