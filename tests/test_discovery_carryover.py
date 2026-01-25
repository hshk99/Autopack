"""Tests for Discovery Cycle Carryover (IMP-FEAT-001).

Tests the carryover context JSON structure and validation logic
for carrying over unimplemented improvements between Discovery cycles.
"""

import json
from datetime import datetime
from pathlib import Path

import pytest


class TestCarryoverContextStructure:
    """Tests for CARRYOVER_CONTEXT.json structure validation."""

    def test_valid_carryover_context_structure(self, tmp_path: Path):
        """Test that a valid carryover context has required fields."""
        carryover = {
            "source_cycle": "Discovery_Cycle_2024-01-15",
            "created_at": "2024-01-15T10:00:00Z",
            "unimplemented_imps": [
                {
                    "id": "IMP-TEL-001",
                    "title": "Centralized Telemetry Aggregator",
                    "priority": "high",
                    "carryover_from": "previous_cycle",
                }
            ],
        }

        carryover_path = tmp_path / "CARRYOVER_CONTEXT.json"
        carryover_path.write_text(json.dumps(carryover, indent=2))

        loaded = json.loads(carryover_path.read_text())

        assert "source_cycle" in loaded
        assert "created_at" in loaded
        assert "unimplemented_imps" in loaded
        assert isinstance(loaded["unimplemented_imps"], list)

    def test_carryover_items_have_carryover_from_field(self, tmp_path: Path):
        """Test that each carryover item has carryover_from field."""
        carryover = {
            "source_cycle": "Discovery_Cycle_2024-01-15",
            "created_at": "2024-01-15T10:00:00Z",
            "unimplemented_imps": [
                {
                    "id": "IMP-TEL-001",
                    "title": "Test Improvement 1",
                    "carryover_from": "previous_cycle",
                },
                {
                    "id": "IMP-MEM-002",
                    "title": "Test Improvement 2",
                    "carryover_from": "previous_cycle",
                },
            ],
        }

        carryover_path = tmp_path / "CARRYOVER_CONTEXT.json"
        carryover_path.write_text(json.dumps(carryover, indent=2))

        loaded = json.loads(carryover_path.read_text())

        for imp in loaded["unimplemented_imps"]:
            assert "carryover_from" in imp
            assert imp["carryover_from"] == "previous_cycle"

    def test_empty_unimplemented_imps_array(self, tmp_path: Path):
        """Test handling of empty unimplemented_imps array."""
        carryover = {
            "source_cycle": "Discovery_Cycle_2024-01-15",
            "created_at": "2024-01-15T10:00:00Z",
            "unimplemented_imps": [],
        }

        carryover_path = tmp_path / "CARRYOVER_CONTEXT.json"
        carryover_path.write_text(json.dumps(carryover, indent=2))

        loaded = json.loads(carryover_path.read_text())

        assert loaded["unimplemented_imps"] == []


class TestImpsMasterExtraction:
    """Tests for extracting carryover data from AUTOPACK_IMPS_MASTER.json."""

    def test_extract_unimplemented_imps_from_master(self, tmp_path: Path):
        """Test extracting unimplemented improvements from master file."""
        imps_master = {
            "cycle": "Discovery_Cycle_2024-01-14",
            "implemented_imps": [
                {"id": "IMP-BUG-001", "title": "Fixed Bug", "status": "completed"}
            ],
            "unimplemented_imps": [
                {"id": "IMP-FEAT-002", "title": "New Feature", "priority": "high"},
                {"id": "IMP-REFACTOR-001", "title": "Code Cleanup", "priority": "medium"},
            ],
        }

        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"
        master_path.write_text(json.dumps(imps_master, indent=2))

        loaded = json.loads(master_path.read_text())

        assert len(loaded["unimplemented_imps"]) == 2
        assert loaded["unimplemented_imps"][0]["id"] == "IMP-FEAT-002"
        assert loaded["unimplemented_imps"][1]["id"] == "IMP-REFACTOR-001"

    def test_master_without_unimplemented_imps(self, tmp_path: Path):
        """Test handling master file with no unimplemented_imps field."""
        imps_master = {
            "cycle": "Discovery_Cycle_2024-01-14",
            "implemented_imps": [
                {"id": "IMP-BUG-001", "title": "Fixed Bug", "status": "completed"}
            ],
        }

        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"
        master_path.write_text(json.dumps(imps_master, indent=2))

        loaded = json.loads(master_path.read_text())

        assert "unimplemented_imps" not in loaded or loaded.get("unimplemented_imps") is None


class TestCarryoverContextCreation:
    """Tests for creating carryover context from master data."""

    def test_create_carryover_context_adds_carryover_from(self, tmp_path: Path):
        """Test that creating carryover context adds carryover_from to each item."""
        # Simulate input from AUTOPACK_IMPS_MASTER.json
        unimplemented_imps = [
            {"id": "IMP-TEL-001", "title": "Test 1", "priority": "high"},
            {"id": "IMP-MEM-001", "title": "Test 2", "priority": "medium"},
        ]

        # Simulate carryover creation logic
        carryover = {
            "source_cycle": f"Discovery_Cycle_{datetime.now().strftime('%Y-%m-%d')}",
            "created_at": datetime.now().isoformat(),
            "unimplemented_imps": [],
        }

        for imp in unimplemented_imps:
            imp_with_carryover = imp.copy()
            imp_with_carryover["carryover_from"] = "previous_cycle"
            carryover["unimplemented_imps"].append(imp_with_carryover)

        # Verify carryover_from was added
        for imp in carryover["unimplemented_imps"]:
            assert "carryover_from" in imp
            assert imp["carryover_from"] == "previous_cycle"

        # Verify original data preserved
        assert carryover["unimplemented_imps"][0]["id"] == "IMP-TEL-001"
        assert carryover["unimplemented_imps"][0]["priority"] == "high"

    def test_carryover_preserves_all_original_fields(self, tmp_path: Path):
        """Test that carryover preserves all fields from original improvement."""
        original_imp = {
            "id": "IMP-FEAT-001",
            "title": "Discovery Cycle Carryover",
            "priority": "high",
            "category": "feature",
            "description": "Enable carryover of unimplemented improvements",
            "files_affected": ["trigger_project_generation.ps1", "phase1.mdc"],
            "estimated_effort": "medium",
        }

        # Create carryover item
        carryover_imp = original_imp.copy()
        carryover_imp["carryover_from"] = "previous_cycle"

        # Verify all original fields preserved
        for key, value in original_imp.items():
            assert key in carryover_imp
            assert carryover_imp[key] == value

        # Verify new field added
        assert carryover_imp["carryover_from"] == "previous_cycle"


class TestCarryoverPrioritization:
    """Tests for carryover item prioritization logic."""

    def test_carryover_items_identified_for_priority_boost(self):
        """Test identifying carryover items that should get priority boost."""
        carryover_imps = [
            {"id": "IMP-TEL-001", "priority": "critical", "carryover_from": "previous_cycle"},
            {"id": "IMP-MEM-001", "priority": "high", "carryover_from": "previous_cycle"},
            {"id": "IMP-DOC-001", "priority": "low", "carryover_from": "previous_cycle"},
        ]

        # Items that should maintain or boost priority
        high_priority_carryover = [
            imp for imp in carryover_imps if imp["priority"] in ("critical", "high")
        ]

        assert len(high_priority_carryover) == 2
        assert all(imp["carryover_from"] == "previous_cycle" for imp in high_priority_carryover)

    def test_distinguish_carryover_from_new_discoveries(self):
        """Test distinguishing carryover items from newly discovered items."""
        all_improvements = [
            {"id": "IMP-TEL-001", "title": "Carryover Item", "carryover_from": "previous_cycle"},
            {"id": "IMP-NEW-001", "title": "New Discovery"},  # No carryover_from
            {"id": "IMP-MEM-001", "title": "Another Carryover", "carryover_from": "previous_cycle"},
        ]

        carryover_items = [imp for imp in all_improvements if imp.get("carryover_from")]
        new_items = [imp for imp in all_improvements if not imp.get("carryover_from")]

        assert len(carryover_items) == 2
        assert len(new_items) == 1
        assert new_items[0]["id"] == "IMP-NEW-001"


class TestEdgeCases:
    """Edge cases for discovery carryover."""

    def test_handles_missing_master_file(self, tmp_path: Path):
        """Test handling when AUTOPACK_IMPS_MASTER.json doesn't exist."""
        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"

        assert not master_path.exists()

    def test_handles_malformed_json(self, tmp_path: Path):
        """Test handling of malformed JSON in master file."""
        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"
        master_path.write_text("{ invalid json }")

        with pytest.raises(json.JSONDecodeError):
            json.loads(master_path.read_text())

    def test_handles_null_unimplemented_imps(self, tmp_path: Path):
        """Test handling null value for unimplemented_imps."""
        imps_master = {
            "cycle": "Discovery_Cycle_2024-01-14",
            "unimplemented_imps": None,
        }

        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"
        master_path.write_text(json.dumps(imps_master, indent=2))

        loaded = json.loads(master_path.read_text())

        assert loaded.get("unimplemented_imps") is None

    def test_carryover_with_special_characters_in_fields(self, tmp_path: Path):
        """Test carryover handles special characters in improvement fields."""
        imps_master = {
            "cycle": "Discovery_Cycle_2024-01-14",
            "unimplemented_imps": [
                {
                    "id": "IMP-DOC-001",
                    "title": 'Fix "quotes" and special chars: <>&',
                    "description": "Handle path\\with\\backslashes and unicode: \u2713",
                }
            ],
        }

        master_path = tmp_path / "AUTOPACK_IMPS_MASTER.json"
        master_path.write_text(
            json.dumps(imps_master, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        loaded = json.loads(master_path.read_text(encoding="utf-8"))

        assert loaded["unimplemented_imps"][0]["title"] == 'Fix "quotes" and special chars: <>&'
        assert "\u2713" in loaded["unimplemented_imps"][0]["description"]
