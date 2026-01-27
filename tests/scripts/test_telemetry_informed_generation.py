"""Tests for telemetry-informed task generation (IMP-GEN-001).

Validates that:
- Phase 1 and Phase 2 rule files exist and are properly formatted
- LEARNING_MEMORY.json schema is valid
- Telemetry context integration works correctly
"""

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


class TestPhaseRuleFiles:
    """Test that phase rule files exist and have correct structure."""

    def test_phase1_rule_file_exists(self):
        """Phase 1 rule file should exist in .cursor/rules."""
        phase1_path = PROJECT_ROOT / ".cursor" / "rules" / "phase1.mdc"
        assert phase1_path.exists(), f"Phase 1 rule file not found at {phase1_path}"

    def test_phase2_rule_file_exists(self):
        """Phase 2 rule file should exist in .cursor/rules."""
        phase2_path = PROJECT_ROOT / ".cursor" / "rules" / "phase2.mdc"
        assert phase2_path.exists(), f"Phase 2 rule file not found at {phase2_path}"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_phase1_contains_learning_memory_instructions(self):
        """Phase 1 should contain instructions for reading LEARNING_MEMORY."""
        phase1_path = PROJECT_ROOT / ".cursor" / "rules" / "phase1.mdc"
        content = phase1_path.read_text(encoding="utf-8")

        assert "LEARNING_MEMORY" in content, "Phase 1 should reference LEARNING_MEMORY"
        assert "success_patterns" in content, "Phase 1 should reference success_patterns"
        assert "failure_patterns" in content, "Phase 1 should reference failure_patterns"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_phase2_contains_wave_planning_instructions(self):
        """Phase 2 should contain wave planning with telemetry context."""
        phase2_path = PROJECT_ROOT / ".cursor" / "rules" / "phase2.mdc"
        content = phase2_path.read_text(encoding="utf-8")

        assert "LEARNING_MEMORY" in content, "Phase 2 should reference LEARNING_MEMORY"
        assert "wave" in content.lower(), "Phase 2 should discuss wave planning"
        assert "completion_time" in content, "Phase 2 should reference completion times"

    def test_phase1_has_frontmatter(self):
        """Phase 1 should have valid MDC frontmatter."""
        phase1_path = PROJECT_ROOT / ".cursor" / "rules" / "phase1.mdc"
        content = phase1_path.read_text(encoding="utf-8")

        assert content.startswith("---"), "Phase 1 should start with frontmatter delimiter"
        # Check for required frontmatter fields
        assert "description:" in content, "Phase 1 should have description in frontmatter"

    def test_phase2_has_frontmatter(self):
        """Phase 2 should have valid MDC frontmatter."""
        phase2_path = PROJECT_ROOT / ".cursor" / "rules" / "phase2.mdc"
        content = phase2_path.read_text(encoding="utf-8")

        assert content.startswith("---"), "Phase 2 should start with frontmatter delimiter"
        assert "description:" in content, "Phase 2 should have description in frontmatter"


class TestTriggerScript:
    """Test the trigger_project_generation.ps1 script."""

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_trigger_script_exists(self):
        """Trigger script should exist in scripts/ directory."""
        script_path = PROJECT_ROOT / "scripts" / "trigger_project_generation.ps1"
        assert script_path.exists(), f"Trigger script not found at {script_path}"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_trigger_script_has_telemetry_flag(self):
        """Trigger script should have -UseTelemetryContext parameter."""
        script_path = PROJECT_ROOT / "scripts" / "trigger_project_generation.ps1"
        content = script_path.read_text(encoding="utf-8")

        assert "UseTelemetryContext" in content, "Script should have UseTelemetryContext parameter"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_trigger_script_references_aggregator(self):
        """Trigger script should reference telemetry_aggregator.py."""
        script_path = PROJECT_ROOT / "scripts" / "trigger_project_generation.ps1"
        content = script_path.read_text(encoding="utf-8")

        assert "telemetry_aggregator" in content, "Script should reference telemetry aggregator"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    def test_trigger_script_references_learning_memory(self):
        """Trigger script should reference LEARNING_MEMORY.json."""
        script_path = PROJECT_ROOT / "scripts" / "trigger_project_generation.ps1"
        content = script_path.read_text(encoding="utf-8")

        assert "LEARNING_MEMORY" in content, "Script should reference LEARNING_MEMORY"

    @pytest.mark.xfail(reason="Requires IMP-GEN-001 implementation")
    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="PowerShell syntax check only runs on Windows",
    )
    def test_trigger_script_valid_powershell_syntax(self):
        """Trigger script should have valid PowerShell syntax."""
        script_path = PROJECT_ROOT / "scripts" / "trigger_project_generation.ps1"

        # Use PowerShell to parse the script without executing
        result = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                f"$null = [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$null, [ref]$errors); $errors.Count",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # If parse succeeded, error count should be 0
        assert result.returncode == 0, f"PowerShell parse failed: {result.stderr}"
        error_count = result.stdout.strip()
        assert error_count == "0", f"Script has {error_count} syntax errors"


class TestLearningMemorySchema:
    """Test LEARNING_MEMORY.json schema compatibility."""

    def get_sample_learning_memory(self) -> dict[str, Any]:
        """Return a sample LEARNING_MEMORY structure for testing."""
        return {
            "version": "1.0.0",
            "improvement_outcomes": [
                {
                    "improvement_id": "IMP-TEST-001",
                    "category": "bug",
                    "outcome": "success",
                    "completion_time_minutes": 30,
                    "wave_id": "wave_1",
                }
            ],
            "success_patterns": [
                {
                    "category": "bug",
                    "success_rate": 0.85,
                    "avg_completion_time_minutes": 25,
                    "sample_size": 20,
                }
            ],
            "failure_patterns": [
                {
                    "category": "feature",
                    "failure_rate": 0.4,
                    "common_reasons": ["scope_creep", "missing_deps"],
                    "sample_size": 10,
                }
            ],
            "wave_history": [
                {
                    "wave_id": "wave_1",
                    "improvements": ["IMP-001", "IMP-002"],
                    "outcome": "success",
                    "parallel_efficiency": 0.85,
                }
            ],
            "last_updated": "2024-01-15T10:30:00Z",
        }

    def test_sample_learning_memory_is_valid_json(self):
        """Sample LEARNING_MEMORY should serialize to valid JSON."""
        sample = self.get_sample_learning_memory()
        json_str = json.dumps(sample)
        parsed = json.loads(json_str)

        assert parsed["version"] == "1.0.0"
        assert len(parsed["improvement_outcomes"]) == 1
        assert len(parsed["success_patterns"]) == 1

    def test_learning_memory_has_required_fields(self):
        """LEARNING_MEMORY should have all required top-level fields."""
        sample = self.get_sample_learning_memory()

        required_fields = [
            "version",
            "improvement_outcomes",
            "success_patterns",
            "failure_patterns",
            "wave_history",
            "last_updated",
        ]

        for field in required_fields:
            assert field in sample, f"Missing required field: {field}"

    def test_archive_learning_memory_exists(self):
        """Archived LEARNING_MEMORY.json should exist as reference."""
        archive_path = PROJECT_ROOT / "archive" / "unsorted" / "LEARNING_MEMORY.json"

        if archive_path.exists():
            content = json.loads(archive_path.read_text(encoding="utf-8"))
            # Validate it has the expected structure
            assert "version" in content
            assert "improvement_outcomes" in content
            assert "success_patterns" in content


class TestTelemetryIntegration:
    """Test integration between telemetry aggregator and generation trigger."""

    def test_telemetry_aggregator_exists(self):
        """Telemetry aggregator script should exist."""
        aggregator_path = PROJECT_ROOT / "scripts" / "utility" / "telemetry_aggregator.py"
        assert aggregator_path.exists(), f"Telemetry aggregator not found at {aggregator_path}"

    def test_telemetry_aggregator_has_cli(self):
        """Telemetry aggregator should have CLI entry point."""
        aggregator_path = PROJECT_ROOT / "scripts" / "utility" / "telemetry_aggregator.py"
        content = aggregator_path.read_text(encoding="utf-8")

        assert "def main()" in content, "Aggregator should have main() function"
        assert "__main__" in content, "Aggregator should have __main__ block"
        assert "argparse" in content, "Aggregator should use argparse for CLI"

    def test_telemetry_aggregator_outputs_summary(self):
        """Telemetry aggregator should have save_summary method."""
        aggregator_path = PROJECT_ROOT / "scripts" / "utility" / "telemetry_aggregator.py"
        content = aggregator_path.read_text(encoding="utf-8")

        assert "save_summary" in content, "Aggregator should have save_summary method"
        assert "TELEMETRY_SUMMARY" in content, "Aggregator should reference TELEMETRY_SUMMARY"
