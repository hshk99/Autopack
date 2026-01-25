"""Tests for Smart Nudge Template Learning (IMP-GEN-003)."""

import json

import pytest

from autopack.learning_memory_manager import LearningMemoryManager


@pytest.fixture
def temp_memory_file(tmp_path):
    """Create a temporary memory file path."""
    return tmp_path / "LEARNING_MEMORY.json"


@pytest.fixture
def manager(temp_memory_file):
    """Create a fresh LearningMemoryManager instance."""
    return LearningMemoryManager(temp_memory_file)


class TestRecordNudgeSent:
    """Tests for record_nudge_sent functionality."""

    def test_records_nudge_with_template_id(self, manager):
        """Test that nudge is recorded with template ID."""
        manager.record_nudge_sent(
            template_id="template_continue_task",
            slot_id=1,
            context={"phase_id": "IMP-GEN-001"},
        )

        pending = manager.get_pending_nudges()
        assert len(pending) == 1
        assert pending[0]["template_id"] == "template_continue_task"
        assert pending[0]["slot_id"] == 1
        assert pending[0]["context"]["phase_id"] == "IMP-GEN-001"

    def test_records_nudge_without_context(self, manager):
        """Test that nudge can be recorded without context."""
        manager.record_nudge_sent(
            template_id="template_retry_action",
            slot_id=3,
        )

        pending = manager.get_pending_nudges()
        assert len(pending) == 1
        assert pending[0]["template_id"] == "template_retry_action"
        assert pending[0]["context"] == {}

    def test_increments_template_usage_count(self, manager):
        """Test that template usage count is incremented."""
        manager.record_nudge_sent("template_continue_task", slot_id=1)
        manager.record_nudge_sent("template_continue_task", slot_id=2)
        manager.record_nudge_sent("template_continue_task", slot_id=3)

        templates = manager.get_effective_templates()
        template = next(t for t in templates if t["template_id"] == "template_continue_task")
        assert template["times_used"] == 3

    def test_records_timestamp(self, manager):
        """Test that nudge includes timestamp."""
        manager.record_nudge_sent("template_test", slot_id=1)

        pending = manager.get_pending_nudges()
        assert "sent_at" in pending[0]
        assert "T" in pending[0]["sent_at"]  # ISO format


class TestRecordNudgeEffectiveness:
    """Tests for record_nudge_effectiveness functionality."""

    def test_records_effective_nudge(self, manager):
        """Test recording an effective nudge."""
        manager.record_nudge_sent("template_continue_task", slot_id=1)
        manager.record_nudge_effectiveness(
            template_id="template_continue_task",
            effective=True,
            recovery_time_seconds=30,
        )

        templates = manager.get_effective_templates()
        template = next(t for t in templates if t["template_id"] == "template_continue_task")
        assert template["times_effective"] == 1
        assert template["avg_recovery_time_seconds"] == 30.0

    def test_records_ineffective_nudge(self, manager):
        """Test recording an ineffective nudge."""
        manager.record_nudge_sent("template_retry_action", slot_id=1)
        manager.record_nudge_effectiveness(
            template_id="template_retry_action",
            effective=False,
        )

        templates = manager.get_effective_templates()
        template = next(t for t in templates if t["template_id"] == "template_retry_action")
        assert template["times_effective"] == 0
        assert template["times_used"] == 1

    def test_calculates_average_recovery_time(self, manager):
        """Test that average recovery time is calculated correctly."""
        template_id = "template_continue_task"
        manager.record_nudge_sent(template_id, slot_id=1)
        manager.record_nudge_effectiveness(template_id, effective=True, recovery_time_seconds=20)

        manager.record_nudge_sent(template_id, slot_id=2)
        manager.record_nudge_effectiveness(template_id, effective=True, recovery_time_seconds=40)

        templates = manager.get_effective_templates()
        template = next(t for t in templates if t["template_id"] == template_id)
        assert template["avg_recovery_time_seconds"] == 30.0  # (20 + 40) / 2


class TestResolvePendingNudge:
    """Tests for resolve_pending_nudge functionality."""

    def test_resolves_pending_nudge_for_slot(self, manager):
        """Test resolving a pending nudge for a specific slot."""
        manager.record_nudge_sent("template_continue_task", slot_id=1)
        manager.record_nudge_sent("template_retry_action", slot_id=2)

        template_id = manager.resolve_pending_nudge(
            slot_id=1, effective=True, recovery_time_seconds=15
        )

        assert template_id == "template_continue_task"
        pending = manager.get_pending_nudges(slot_id=1)
        assert len(pending) == 0

    def test_resolves_most_recent_nudge_for_slot(self, manager):
        """Test that the most recent pending nudge is resolved."""
        manager.record_nudge_sent("template_old", slot_id=1)
        manager.record_nudge_sent("template_new", slot_id=1)

        template_id = manager.resolve_pending_nudge(slot_id=1, effective=True)

        assert template_id == "template_new"

    def test_returns_none_when_no_pending_nudge(self, manager):
        """Test that None is returned when no pending nudge exists."""
        template_id = manager.resolve_pending_nudge(slot_id=99, effective=True)
        assert template_id is None

    def test_records_effectiveness_on_resolve(self, manager):
        """Test that effectiveness is recorded when resolving."""
        manager.record_nudge_sent("template_continue_task", slot_id=1)
        manager.resolve_pending_nudge(slot_id=1, effective=True, recovery_time_seconds=25)

        templates = manager.get_effective_templates()
        template = next(t for t in templates if t["template_id"] == "template_continue_task")
        assert template["times_effective"] == 1


class TestGetEffectiveTemplates:
    """Tests for get_effective_templates functionality."""

    def test_returns_empty_when_no_templates(self, manager):
        """Test that empty list is returned with no templates."""
        templates = manager.get_effective_templates()
        assert templates == []

    def test_returns_templates_sorted_by_effectiveness(self, manager):
        """Test that templates are sorted by effectiveness rate."""
        # Template A: 2/4 = 50% effective
        for _ in range(4):
            manager.record_nudge_sent("template_a", slot_id=1)
        manager.record_nudge_effectiveness("template_a", effective=True)
        manager.record_nudge_effectiveness("template_a", effective=True)

        # Template B: 3/3 = 100% effective
        for _ in range(3):
            manager.record_nudge_sent("template_b", slot_id=2)
        for _ in range(3):
            manager.record_nudge_effectiveness("template_b", effective=True)

        templates = manager.get_effective_templates()

        assert len(templates) == 2
        assert templates[0]["template_id"] == "template_b"  # 100% first
        assert templates[0]["effectiveness_rate"] == 1.0
        assert templates[1]["template_id"] == "template_a"  # 50% second
        assert templates[1]["effectiveness_rate"] == 0.5

    def test_includes_all_template_stats(self, manager):
        """Test that all stats are included in template data."""
        manager.record_nudge_sent("template_test", slot_id=1)
        manager.record_nudge_effectiveness(
            "template_test", effective=True, recovery_time_seconds=45
        )

        templates = manager.get_effective_templates()

        assert len(templates) == 1
        template = templates[0]
        assert "template_id" in template
        assert "times_used" in template
        assert "times_effective" in template
        assert "effectiveness_rate" in template
        assert "avg_recovery_time_seconds" in template
        assert "last_used" in template


class TestGetPendingNudges:
    """Tests for get_pending_nudges functionality."""

    def test_returns_all_pending_when_no_filter(self, manager):
        """Test returning all pending nudges without filter."""
        manager.record_nudge_sent("template_a", slot_id=1)
        manager.record_nudge_sent("template_b", slot_id=2)
        manager.record_nudge_sent("template_c", slot_id=3)

        pending = manager.get_pending_nudges()
        assert len(pending) == 3

    def test_filters_by_slot_id(self, manager):
        """Test filtering pending nudges by slot ID."""
        manager.record_nudge_sent("template_a", slot_id=1)
        manager.record_nudge_sent("template_b", slot_id=2)
        manager.record_nudge_sent("template_c", slot_id=1)

        pending = manager.get_pending_nudges(slot_id=1)
        assert len(pending) == 2
        assert all(p["slot_id"] == 1 for p in pending)

    def test_returns_empty_for_nonexistent_slot(self, manager):
        """Test that empty list is returned for nonexistent slot."""
        manager.record_nudge_sent("template_a", slot_id=1)

        pending = manager.get_pending_nudges(slot_id=99)
        assert pending == []


class TestNudgeEffectivenessPersistence:
    """Tests for nudge effectiveness persistence."""

    def test_nudge_data_persists_after_save(self, temp_memory_file):
        """Test that nudge data persists after save and reload."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_nudge_sent("template_continue_task", slot_id=1)
        manager1.record_nudge_effectiveness(
            "template_continue_task", effective=True, recovery_time_seconds=30
        )
        manager1.save()

        manager2 = LearningMemoryManager(temp_memory_file)

        templates = manager2.get_effective_templates()
        assert len(templates) == 1
        assert templates[0]["template_id"] == "template_continue_task"
        assert templates[0]["times_effective"] == 1

    def test_pending_nudges_persist_after_save(self, temp_memory_file):
        """Test that pending nudges persist after save and reload."""
        manager1 = LearningMemoryManager(temp_memory_file)
        manager1.record_nudge_sent("template_test", slot_id=5, context={"test": "data"})
        manager1.save()

        manager2 = LearningMemoryManager(temp_memory_file)

        pending = manager2.get_pending_nudges()
        assert len(pending) == 1
        assert pending[0]["slot_id"] == 5

    def test_memory_structure_includes_nudge_effectiveness(self, temp_memory_file):
        """Test that saved JSON includes nudge_effectiveness structure."""
        manager = LearningMemoryManager(temp_memory_file)
        manager.record_nudge_sent("template_test", slot_id=1)
        manager.save()

        with open(temp_memory_file, encoding="utf-8") as f:
            data = json.load(f)

        assert "nudge_effectiveness" in data
        assert "templates" in data["nudge_effectiveness"]
        assert "pending_nudges" in data["nudge_effectiveness"]


class TestNudgeEffectivenessEdgeCases:
    """Tests for edge cases in nudge effectiveness tracking."""

    def test_handles_missing_nudge_effectiveness_key(self, temp_memory_file):
        """Test handling of missing nudge_effectiveness key in old files."""
        old_data = {
            "version": "1.0.0",
            "improvement_outcomes": [],
            "success_patterns": [],
            "failure_patterns": [],
            "wave_history": [],
        }
        temp_memory_file.write_text(json.dumps(old_data))

        manager = LearningMemoryManager(temp_memory_file)
        # Should not raise
        manager.record_nudge_sent("template_test", slot_id=1)
        templates = manager.get_effective_templates()
        assert len(templates) == 1

    def test_effectiveness_rate_zero_when_no_effective(self, manager):
        """Test effectiveness rate is 0 when no nudges are effective."""
        manager.record_nudge_sent("template_test", slot_id=1)
        manager.record_nudge_sent("template_test", slot_id=2)
        manager.record_nudge_effectiveness("template_test", effective=False)
        manager.record_nudge_effectiveness("template_test", effective=False)

        templates = manager.get_effective_templates()
        assert templates[0]["effectiveness_rate"] == 0.0

    def test_avg_recovery_time_none_when_ineffective(self, manager):
        """Test avg recovery time is None when no effective nudges."""
        manager.record_nudge_sent("template_test", slot_id=1)
        manager.record_nudge_effectiveness("template_test", effective=False)

        templates = manager.get_effective_templates()
        assert templates[0]["avg_recovery_time_seconds"] is None
