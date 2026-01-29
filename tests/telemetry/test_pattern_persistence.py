"""Tests for pattern registry persistence across sessions."""

import json
import tempfile
from pathlib import Path

import pytest

from telemetry.analysis_engine import AnalysisEngine
from telemetry.pattern_detector import PatternDetector
from telemetry.unified_event_log import UnifiedEventLog


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_log_path(temp_dir):
    """Create a temporary file path for event log."""
    return str(temp_dir / "events.jsonl")


@pytest.fixture
def temp_registry_path(temp_dir):
    """Create a temporary file path for pattern registry."""
    return temp_dir / "pattern_registry.json"


@pytest.fixture
def event_log(temp_log_path):
    """Create a UnifiedEventLog instance."""
    return UnifiedEventLog(temp_log_path)


class TestPatternDetectorSerialization:
    """Tests for PatternDetector to_dict/from_dict methods."""

    def test_to_dict_empty(self):
        """Test serialization of empty pattern detector."""
        detector = PatternDetector()
        data = detector.to_dict()

        assert data["version"] == 1
        assert data["patterns"] == {}

    def test_to_dict_with_patterns(self):
        """Test serialization with registered patterns."""
        detector = PatternDetector()
        events = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]
        detector.register_pattern(events)

        data = detector.to_dict()

        assert data["version"] == 1
        assert len(data["patterns"]) == 1

        pattern_data = list(data["patterns"].values())[0]
        assert pattern_data["occurrences"] == 1
        assert pattern_data["signature"]["event_type"] == "ci_failure"
        assert pattern_data["signature"]["source"] == "ci_retry"

    def test_from_dict_empty(self):
        """Test deserialization of empty data."""
        data = {"version": 1, "patterns": {}}
        detector = PatternDetector.from_dict(data)

        assert detector.get_pattern_count() == 0

    def test_from_dict_with_patterns(self):
        """Test deserialization restores patterns correctly."""
        data = {
            "version": 1,
            "patterns": {
                "abc123": {
                    "pattern_id": "abc123",
                    "occurrences": 5,
                    "first_seen": "2024-01-01T00:00:00",
                    "last_seen": "2024-01-02T00:00:00",
                    "signature": {
                        "event_type": "error",
                        "source": "ci_retry",
                        "sequence_length": 2,
                        "event_type_sequence": ["error", "retry"],
                    },
                }
            },
        }

        detector = PatternDetector.from_dict(data)

        assert detector.get_pattern_count() == 1
        pattern = detector.known_patterns["abc123"]
        assert pattern.occurrences == 5
        assert pattern.signature["event_type"] == "error"
        # Verify tuple conversion for event_type_sequence
        assert pattern.signature["event_type_sequence"] == ("error", "retry")

    def test_roundtrip_serialization(self):
        """Test that serialization and deserialization are reversible."""
        original = PatternDetector()

        # Register multiple patterns
        events1 = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]
        events2 = [
            {
                "event_type": "connection_error",
                "source": "api",
                "payload": {"error_type": "timeout"},
            }
        ]

        original.register_pattern(events1)
        original.register_pattern(events1)  # Increment occurrences
        original.register_pattern(events2)

        # Serialize and deserialize
        data = original.to_dict()
        restored = PatternDetector.from_dict(data)

        assert restored.get_pattern_count() == original.get_pattern_count()

        for pattern_id in original.known_patterns:
            orig_pattern = original.known_patterns[pattern_id]
            rest_pattern = restored.known_patterns[pattern_id]
            assert rest_pattern.occurrences == orig_pattern.occurrences
            assert rest_pattern.first_seen == orig_pattern.first_seen
            assert rest_pattern.last_seen == orig_pattern.last_seen

    def test_patterns_property(self):
        """Test that patterns property returns known_patterns."""
        detector = PatternDetector()
        events = [{"event_type": "test", "source": "test", "payload": {}}]
        detector.register_pattern(events)

        assert detector.patterns is detector.known_patterns
        assert len(detector.patterns) == 1


class TestAnalysisEnginePersistence:
    """Tests for AnalysisEngine pattern persistence."""

    def test_creates_new_detector_when_no_registry(self, event_log, temp_registry_path):
        """Test that a new detector is created when no registry exists."""
        engine = AnalysisEngine(event_log, registry_path=temp_registry_path)

        assert engine.pattern_detector.get_pattern_count() == 0
        assert not temp_registry_path.exists()

    def test_save_patterns_creates_file(self, event_log, temp_registry_path):
        """Test that save_patterns creates the registry file."""
        engine = AnalysisEngine(event_log, registry_path=temp_registry_path)

        engine.save_patterns()

        assert temp_registry_path.exists()
        with open(temp_registry_path, encoding="utf-8") as f:
            data = json.load(f)
        assert "version" in data
        assert "patterns" in data

    def test_save_patterns_creates_parent_directories(self, temp_dir, event_log):
        """Test that save_patterns creates parent directories if needed."""
        registry_path = temp_dir / "nested" / "dir" / "registry.json"
        engine = AnalysisEngine(event_log, registry_path=registry_path)

        engine.save_patterns()

        assert registry_path.exists()
        assert registry_path.parent.exists()

    def test_load_patterns_from_existing_registry(self, event_log, temp_registry_path):
        """Test loading patterns from an existing registry file."""
        # Create initial engine and register patterns
        engine1 = AnalysisEngine(event_log, registry_path=temp_registry_path)
        events = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]
        engine1.pattern_detector.register_pattern(events)
        engine1.pattern_detector.register_pattern(events)
        engine1.save_patterns()

        # Create new engine with same registry path
        engine2 = AnalysisEngine(event_log, registry_path=temp_registry_path)

        assert engine2.pattern_detector.get_pattern_count() == 1
        pattern = list(engine2.pattern_detector.patterns.values())[0]
        assert pattern.occurrences == 2

    def test_handles_corrupt_registry_file(self, event_log, temp_registry_path):
        """Test graceful handling of corrupt registry file."""
        # Write invalid JSON to registry
        with open(temp_registry_path, "w", encoding="utf-8") as f:
            f.write("{ invalid json }")

        # Should create new detector instead of failing
        engine = AnalysisEngine(event_log, registry_path=temp_registry_path)

        assert engine.pattern_detector.get_pattern_count() == 0

    def test_handles_missing_keys_in_registry(self, event_log, temp_registry_path):
        """Test handling of registry with missing required keys."""
        # Write registry with missing pattern data
        with open(temp_registry_path, "w", encoding="utf-8") as f:
            json.dump({"version": 1}, f)  # Missing "patterns" key

        engine = AnalysisEngine(event_log, registry_path=temp_registry_path)

        # Should handle gracefully with empty patterns
        assert engine.pattern_detector.get_pattern_count() == 0

    def test_default_registry_path(self, event_log):
        """Test that default registry path is set correctly."""
        engine = AnalysisEngine(event_log)

        expected_path = Path.home() / ".autopack" / "pattern_registry.json"
        assert engine.registry_path == expected_path

    def test_custom_registry_path(self, event_log, temp_registry_path):
        """Test that custom registry path is used."""
        engine = AnalysisEngine(event_log, registry_path=temp_registry_path)

        assert engine.registry_path == temp_registry_path

    def test_persistence_across_sessions(self, event_log, temp_registry_path):
        """Test full persistence workflow across multiple sessions."""
        # Session 1: Create patterns and save
        engine1 = AnalysisEngine(event_log, registry_path=temp_registry_path)
        events1 = [{"event_type": "ci_failure", "source": "ci_retry", "payload": {}}]
        events2 = [{"event_type": "timeout_error", "source": "api", "payload": {}}]

        engine1.pattern_detector.register_pattern(events1)
        engine1.pattern_detector.register_pattern(events1)
        engine1.pattern_detector.register_pattern(events2)
        engine1.save_patterns()

        # Session 2: Load and verify patterns persisted
        engine2 = AnalysisEngine(event_log, registry_path=temp_registry_path)
        assert engine2.pattern_detector.get_pattern_count() == 2

        # Session 2: Add more occurrences
        engine2.pattern_detector.register_pattern(events1)
        engine2.save_patterns()

        # Session 3: Verify accumulated state
        engine3 = AnalysisEngine(event_log, registry_path=temp_registry_path)
        assert engine3.pattern_detector.get_pattern_count() == 2

        # Find the ci_failure pattern and verify occurrences
        for pattern in engine3.pattern_detector.patterns.values():
            if pattern.signature.get("event_type") == "ci_failure":
                assert pattern.occurrences == 3
                break
