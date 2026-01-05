"""File size telemetry for observability

Per GPT_RESPONSE14 Q4: Use JSONL format under .autonomous_runs/ for v1
Can migrate to database later if needed.

Per IMPLEMENTATION_PLAN2.md Phase 1.3
"""

import json
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class FileSizeTelemetry:
    """Records file size events to JSONL for observability"""

    def __init__(self, workspace: Path, project_id: str = "autopack"):
        """Initialize telemetry

        Args:
            workspace: Workspace root path
            project_id: Project identifier (default: "autopack")
        """
        self.telemetry_path = (
            workspace / ".autonomous_runs" / project_id / "file_size_telemetry.jsonl"
        )
        self.telemetry_path.parent.mkdir(parents=True, exist_ok=True)
        logger.info(f"FileSizeTelemetry initialized: {self.telemetry_path}")

    def record_event(self, event: Dict[str, Any]):
        """Append an event to the telemetry file

        Args:
            event: Event dict with at minimum: run_id, phase_id, event_type
        """
        event["timestamp"] = datetime.now(timezone.utc).isoformat()

        try:
            with open(self.telemetry_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(event) + "\n")
        except Exception as e:
            logger.warning(f"Failed to write telemetry event: {e}")

    def record_preflight_reject(
        self, run_id: str, phase_id: str, file_path: str, line_count: int, limit: int, bucket: str
    ):
        """Record when pre-flight guard rejects a file

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to rejected file
            line_count: Number of lines in file
            limit: Threshold that was exceeded
            bucket: Which bucket (B or C)
        """
        self.record_event(
            {
                "run_id": run_id,
                "phase_id": phase_id,
                "event_type": "preflight_reject_large_file",
                "file_path": file_path,
                "line_count": line_count,
                "limit": limit,
                "bucket": bucket,
            }
        )

    def record_bucket_switch(self, run_id: str, phase_id: str, files: list):
        """Record when phase switches from full-file to diff mode

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            files: List of (file_path, line_count) tuples that triggered switch
        """
        self.record_event(
            {
                "run_id": run_id,
                "phase_id": phase_id,
                "event_type": "bucket_b_switch_to_diff_mode",
                "files": [{"path": p, "line_count": lc} for p, lc in files],
            }
        )

    def record_shrinkage(
        self,
        run_id: str,
        phase_id: str,
        file_path: str,
        old_lines: int,
        new_lines: int,
        shrinkage_percent: float,
        allow_mass_deletion: bool,
    ):
        """Record when shrinkage detection fires

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to file
            old_lines: Original line count
            new_lines: New line count
            shrinkage_percent: Percentage of shrinkage
            allow_mass_deletion: Whether phase allows mass deletion
        """
        self.record_event(
            {
                "run_id": run_id,
                "phase_id": phase_id,
                "event_type": "suspicious_shrinkage",
                "file_path": file_path,
                "old_lines": old_lines,
                "new_lines": new_lines,
                "shrinkage_percent": shrinkage_percent,
                "allow_mass_deletion": allow_mass_deletion,
            }
        )

    def record_growth(
        self,
        run_id: str,
        phase_id: str,
        file_path: str,
        old_lines: int,
        new_lines: int,
        growth_multiplier: float,
        allow_mass_addition: bool,
    ):
        """Record when growth detection fires

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to file
            old_lines: Original line count
            new_lines: New line count
            growth_multiplier: Growth multiplier
            allow_mass_addition: Whether phase allows mass addition
        """
        self.record_event(
            {
                "run_id": run_id,
                "phase_id": phase_id,
                "event_type": "suspicious_growth",
                "file_path": file_path,
                "old_lines": old_lines,
                "new_lines": new_lines,
                "growth_multiplier": growth_multiplier,
                "allow_mass_addition": allow_mass_addition,
            }
        )

    def record_readonly_violation(
        self, run_id: str, phase_id: str, file_path: str, line_count: int, model: str
    ):
        """Record when LLM tries to modify a read-only file

        Args:
            run_id: Run identifier
            phase_id: Phase identifier
            file_path: Path to read-only file
            line_count: Number of lines in file
            model: Model that violated the contract
        """
        self.record_event(
            {
                "run_id": run_id,
                "phase_id": phase_id,
                "event_type": "readonly_violation",
                "file_path": file_path,
                "line_count": line_count,
                "model": model,
            }
        )
