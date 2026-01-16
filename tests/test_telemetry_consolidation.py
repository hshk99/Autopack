"""Tests for telemetry consolidation into SOT files.

Tests cover:
- Pattern extraction from telemetry insights
- LEARNED_RULES.json generation and updates
- DEBUG_LOG.md consolidation
- Confidence and occurrence thresholds
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock

import pytest

from autopack.tidy.telemetry_consolidator import TelemetryConsolidator
from autopack.memory.memory_service import MemoryService


@pytest.fixture
def tmp_sot_dir():
    """Create a temporary directory for SOT files."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service for testing."""
    mock_service = Mock(spec=MemoryService)
    mock_service.store = MagicMock()
    mock_service.store.scroll = MagicMock(return_value=[])
    mock_service.enabled = True
    return mock_service


class TestTelemetryConsolidator:
    """Tests for TelemetryConsolidator class."""

    def test_consolidator_initialization(self, mock_memory_service, tmp_sot_dir):
        """Test consolidator initializes with correct parameters."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )
        assert consolidator._sot_root == tmp_sot_dir
        assert consolidator._memory is not None

    def test_consolidator_with_custom_memory_service(self, mock_memory_service, tmp_sot_dir):
        """Test consolidator with custom memory service."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )
        assert consolidator._memory is mock_memory_service

    def test_load_existing_rules_no_file(self, mock_memory_service, tmp_sot_dir):
        """Test loading rules when file doesn't exist."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )
        rules_path = tmp_sot_dir / "LEARNED_RULES.json"

        rules = consolidator._load_existing_rules(rules_path)

        assert "version" in rules
        assert rules["version"] == "1.0"
        assert rules["rules"] == []
        assert rules["last_updated"] is None

    def test_load_existing_rules_with_file(self, mock_memory_service, tmp_sot_dir):
        """Test loading existing rules from file."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )
        rules_path = tmp_sot_dir / "LEARNED_RULES.json"

        # Create existing rules file
        existing_rules = {
            "version": "1.0",
            "rules": [{"pattern": "test pattern", "confidence": 0.9}],
            "last_updated": "2026-01-01T00:00:00",
        }
        with open(rules_path, "w") as f:
            json.dump(existing_rules, f)

        rules = consolidator._load_existing_rules(rules_path)

        assert len(rules["rules"]) == 1
        assert rules["rules"][0]["pattern"] == "test pattern"

    def test_extract_patterns_from_insights(self, mock_memory_service, tmp_sot_dir):
        """Test pattern extraction from insights."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        # Create test insights
        insights = [
            {
                "payload": {
                    "summary": "test error type failure",
                    "type": "summary",
                }
            },
            {
                "payload": {
                    "summary": "test error type failure",
                    "type": "summary",
                }
            },
            {
                "payload": {
                    "summary": "different pattern here",
                    "type": "summary",
                }
            },
        ]

        patterns = consolidator._extract_patterns(insights)

        assert len(patterns) == 2
        # Check that occurrence counts are correct
        pattern_occurrences = {p["pattern"]: p["occurrences"] for p in patterns}
        # Pattern is first 5 words
        assert pattern_occurrences["test error type failure"] == 2
        assert pattern_occurrences["different pattern here"] == 1

    def test_get_pattern_key_from_summary(self, mock_memory_service, tmp_sot_dir):
        """Test pattern key extraction from summary field."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        insight = {"summary": "test error type failure detailed"}
        key = consolidator._get_pattern_key(insight)

        # Pattern is first 5 words
        assert key == "test error type failure detailed"

    def test_get_pattern_key_from_error_type(self, mock_memory_service, tmp_sot_dir):
        """Test pattern key extraction from error_type field."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        insight = {"error_type": "connection timeout retry"}
        key = consolidator._get_pattern_key(insight)

        assert key == "connection timeout retry"

    def test_merge_rules_new_patterns(self, mock_memory_service, tmp_sot_dir):
        """Test merging new patterns into existing rules."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        existing_rules = {
            "version": "1.0",
            "rules": [{"pattern": "old pattern", "occurrences": 1}],
            "last_updated": None,
        }

        new_patterns = [
            {"pattern": "new pattern", "occurrences": 5, "confidence": 0.9},
        ]

        merged = consolidator._merge_rules(existing_rules, new_patterns)

        assert len(merged["rules"]) == 2
        assert merged["last_updated"] is not None
        pattern_keys = [r["pattern"] for r in merged["rules"]]
        assert "old pattern" in pattern_keys
        assert "new pattern" in pattern_keys

    def test_merge_rules_update_existing(self, mock_memory_service, tmp_sot_dir):
        """Test updating existing patterns in rules."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        existing_rules = {
            "version": "1.0",
            "rules": [
                {
                    "pattern": "existing pattern",
                    "occurrences": 2,
                    "confidence": 0.5,
                }
            ],
            "last_updated": None,
        }

        new_patterns = [
            {
                "pattern": "existing pattern",
                "occurrences": 5,
                "confidence": 0.85,
            },
        ]

        merged = consolidator._merge_rules(existing_rules, new_patterns)

        # Should still have only 1 rule, but with updated values
        assert len(merged["rules"]) == 1
        assert merged["rules"][0]["occurrences"] == 5
        assert merged["rules"][0]["confidence"] == 0.85

    def test_consolidate_learned_rules(self, mock_memory_service, tmp_sot_dir):
        """Test full consolidation of learned rules."""
        # Setup mock to return test insights
        mock_memory_service.store.scroll.side_effect = [
            [{"payload": {"summary": "test pattern one", "type": "summary"}}]
            * 5,  # First call - run_summaries
            [{"payload": {"error_type": "test pattern one error"}}] * 3,  # Second call - errors_ci
        ]

        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        rules = consolidator.consolidate_learned_rules(min_occurrences=2, min_confidence=0.2)

        # Should extract patterns that meet threshold
        assert isinstance(rules, list)
        # Verify LEARNED_RULES.json was created
        rules_file = tmp_sot_dir / "LEARNED_RULES.json"
        assert rules_file.exists()

        with open(rules_file) as f:
            saved_rules = json.load(f)
        assert "rules" in saved_rules
        assert saved_rules["last_updated"] is not None

    def test_append_to_debug_log_empty_insights(self, mock_memory_service, tmp_sot_dir):
        """Test appending to debug log with no significant insights."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        insights = [{"type": "info", "content": "minor event", "severity": "low"}]

        count = consolidator.append_to_debug_log(insights)

        assert count == 0
        debug_log = tmp_sot_dir / "DEBUG_LOG.md"
        assert not debug_log.exists()

    def test_append_to_debug_log_with_insights(self, mock_memory_service, tmp_sot_dir):
        """Test appending significant insights to debug log."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        insights = [
            {
                "type": "error",
                "content": "critical error occurred",
                "severity": "high",
            },
            {"type": "warning", "summary": "warning message", "confidence": 0.9},
        ]

        count = consolidator.append_to_debug_log(insights)

        assert count == 2
        debug_log = tmp_sot_dir / "DEBUG_LOG.md"
        assert debug_log.exists()

        with open(debug_log) as f:
            content = f.read()
        assert "critical error occurred" in content
        assert "warning message" in content

    def test_append_to_debug_log_append_mode(self, mock_memory_service, tmp_sot_dir):
        """Test appending multiple times to debug log."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        # First append
        insights1 = [
            {
                "type": "error",
                "content": "first error",
                "severity": "high",
            }
        ]
        consolidator.append_to_debug_log(insights1)

        # Second append
        insights2 = [
            {
                "type": "error",
                "content": "second error",
                "severity": "high",
            }
        ]
        consolidator.append_to_debug_log(insights2)

        debug_log = tmp_sot_dir / "DEBUG_LOG.md"
        with open(debug_log) as f:
            content = f.read()

        # Both insights should be present
        assert "first error" in content
        assert "second error" in content
        # Should have two telemetry insight sections
        assert content.count("## Telemetry Insights") == 2

    def test_confidence_calculation(self, mock_memory_service, tmp_sot_dir):
        """Test that confidence is calculated correctly."""
        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=tmp_sot_dir
        )

        insights = [
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},
            {"payload": {"summary": "pattern test"}},  # 10 occurrences
        ]

        patterns = consolidator._extract_patterns(insights)

        assert len(patterns) == 1
        # Confidence = min(1.0, 10/10) = 1.0
        assert patterns[0]["confidence"] == 1.0

    def test_sot_directory_creation(self, mock_memory_service, tmp_sot_dir):
        """Test that SOT directory is created if it doesn't exist."""
        nested_dir = tmp_sot_dir / "nested" / "docs"
        assert not nested_dir.exists()

        consolidator = TelemetryConsolidator(
            memory_service=mock_memory_service, sot_root=nested_dir
        )

        # Should create directory when calling consolidate_learned_rules
        consolidator.consolidate_learned_rules()

        assert nested_dir.exists()
