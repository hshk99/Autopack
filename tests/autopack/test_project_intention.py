"""Tests for Project Intention Memory (Phase 0).

Validates:
- Intention creation and artifact writing
- Path resolution via RunFileLayout
- Anchor size caps
- Digest stability
- Memory service integration (write + retrieve)
- Graceful degradation when memory disabled
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from autopack.file_layout import RunFileLayout
from autopack.project_intention import (INTENTION_SCHEMA_VERSION,
                                        MAX_INTENTION_ANCHOR_CHARS,
                                        ProjectIntention,
                                        ProjectIntentionManager,
                                        create_and_store_intention)


class TestProjectIntention:
    """Test ProjectIntention dataclass."""

    def test_to_dict(self):
        """Test conversion to dictionary."""
        intention = ProjectIntention(
            project_id="test-project",
            created_at="2025-01-01T00:00:00Z",
            raw_input_digest="abc123",
            intent_anchor="Test anchor",
            intent_facts=["Fact 1", "Fact 2"],
            non_goals=["Non-goal 1"],
        )
        d = intention.to_dict()
        assert d["project_id"] == "test-project"
        assert d["created_at"] == "2025-01-01T00:00:00Z"
        assert d["raw_input_digest"] == "abc123"
        assert d["intent_anchor"] == "Test anchor"
        assert d["intent_facts"] == ["Fact 1", "Fact 2"]
        assert d["non_goals"] == ["Non-goal 1"]
        assert d["schema_version"] == INTENTION_SCHEMA_VERSION

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "project_id": "test-project",
            "created_at": "2025-01-01T00:00:00Z",
            "raw_input_digest": "abc123",
            "intent_anchor": "Test anchor",
            "intent_facts": ["Fact 1"],
            "non_goals": [],
            "acceptance_criteria": ["Criteria 1"],
            "constraints": {"budget": 1000},
            "toolchain_hypotheses": ["python"],
            "open_questions": ["Question 1"],
            "schema_version": "v1",
        }
        intention = ProjectIntention.from_dict(data)
        assert intention.project_id == "test-project"
        assert intention.raw_input_digest == "abc123"
        assert intention.intent_facts == ["Fact 1"]
        assert intention.acceptance_criteria == ["Criteria 1"]
        assert intention.constraints == {"budget": 1000}

    def test_from_dict_filters_unknown_fields(self):
        """Test that unknown fields are filtered during deserialization."""
        data = {
            "project_id": "test-project",
            "created_at": "2025-01-01T00:00:00Z",
            "raw_input_digest": "abc123",
            "intent_anchor": "Test anchor",
            "unknown_field": "should be ignored",
        }
        intention = ProjectIntention.from_dict(data)
        assert intention.project_id == "test-project"
        assert not hasattr(intention, "unknown_field")


class TestProjectIntentionManager:
    """Test ProjectIntentionManager."""

    def test_init(self):
        """Test manager initialization."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        assert manager.run_id == "test-run-001"
        assert manager.project_id == "autopack"  # Default project detection
        assert isinstance(manager.layout, RunFileLayout)

    def test_init_with_project_id(self):
        """Test manager initialization with explicit project_id."""
        manager = ProjectIntentionManager(
            run_id="test-run-001",
            project_id="custom-project",
        )
        assert manager.project_id == "custom-project"

    def test_compute_digest_stability(self):
        """Test that digest is stable for same input."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        input1 = "Build a REST API for user authentication"
        input2 = "Build a REST API for user authentication"
        digest1 = manager._compute_digest(input1)
        digest2 = manager._compute_digest(input2)
        assert digest1 == digest2
        assert len(digest1) == 16  # First 16 chars of SHA256

    def test_compute_digest_uniqueness(self):
        """Test that different inputs produce different digests."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        input1 = "Build a REST API"
        input2 = "Build a GraphQL API"
        digest1 = manager._compute_digest(input1)
        digest2 = manager._compute_digest(input2)
        assert digest1 != digest2

    def test_create_anchor_respects_size_cap(self):
        """Test that anchor is capped at MAX_INTENTION_ANCHOR_CHARS."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        # Create very large input
        large_input = "x" * 10000
        anchor = manager._create_anchor(large_input)
        assert len(anchor) <= MAX_INTENTION_ANCHOR_CHARS

    def test_create_anchor_includes_facts(self):
        """Test that anchor includes intent facts when provided."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        facts = ["Fact 1", "Fact 2", "Fact 3"]
        anchor = manager._create_anchor("Raw input", intent_facts=facts)
        assert "Key Facts" in anchor
        assert "Fact 1" in anchor
        assert "Fact 2" in anchor

    def test_create_anchor_limits_facts(self):
        """Test that anchor limits number of facts included."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        # Provide 10 facts, only 5 should be included
        facts = [f"Fact {i}" for i in range(10)]
        anchor = manager._create_anchor("Raw input", intent_facts=facts)
        # Count occurrences
        fact_count = sum(1 for i in range(10) if f"Fact {i}" in anchor)
        assert fact_count <= 5

    def test_get_intention_dir_uses_layout(self):
        """Test that intention directory path uses RunFileLayout."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout  # Override with test layout

            intention_dir = manager._get_intention_dir()
            assert "intention" in str(intention_dir)
            assert "test-run-001" in str(intention_dir)

    def test_create_intention(self):
        """Test creating a complete intention object."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        intention = manager.create_intention(
            raw_input="Build a REST API for user authentication",
            intent_facts=["Support JWT tokens", "RESTful design"],
            non_goals=["No GraphQL support"],
            acceptance_criteria=["Tests pass", "API documented"],
            constraints={"budget": 5000, "deadline": "2025-06-01"},
            toolchain_hypotheses=["python", "fastapi"],
            open_questions=["Which database?"],
        )

        assert intention.project_id == "autopack"
        assert len(intention.raw_input_digest) == 16
        assert len(intention.intent_anchor) <= MAX_INTENTION_ANCHOR_CHARS
        assert intention.intent_facts == ["Support JWT tokens", "RESTful design"]
        assert intention.non_goals == ["No GraphQL support"]
        assert intention.acceptance_criteria == ["Tests pass", "API documented"]
        assert intention.constraints == {"budget": 5000, "deadline": "2025-06-01"}
        assert intention.toolchain_hypotheses == ["python", "fastapi"]
        assert intention.open_questions == ["Which database?"]
        assert intention.schema_version == INTENTION_SCHEMA_VERSION

    def test_write_intention_artifacts(self):
        """Test writing intention artifacts to disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout

            intention = manager.create_intention(
                raw_input="Build a REST API",
                intent_facts=["Fact 1"],
            )

            paths = manager.write_intention_artifacts(intention)

            # Verify JSON artifact
            assert "json" in paths
            assert paths["json"].exists()
            json_data = json.loads(paths["json"].read_text())
            assert json_data["project_id"] == "autopack"
            assert json_data["intent_facts"] == ["Fact 1"]

            # Verify anchor artifact
            assert "anchor" in paths
            assert paths["anchor"].exists()
            anchor_text = paths["anchor"].read_text()
            assert len(anchor_text) <= MAX_INTENTION_ANCHOR_CHARS
            assert "Project Intention" in anchor_text

    def test_read_intention_from_disk(self):
        """Test reading intention from disk artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout

            # Create and write
            original = manager.create_intention(
                raw_input="Build a REST API",
                intent_facts=["Fact 1", "Fact 2"],
                constraints={"budget": 1000},
            )
            manager.write_intention_artifacts(original)

            # Read back
            loaded = manager.read_intention_from_disk()
            assert loaded is not None
            assert loaded.project_id == original.project_id
            assert loaded.raw_input_digest == original.raw_input_digest
            assert loaded.intent_facts == ["Fact 1", "Fact 2"]
            assert loaded.constraints == {"budget": 1000}

    def test_read_intention_from_disk_missing(self):
        """Test reading intention when no artifacts exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout

            loaded = manager.read_intention_from_disk()
            assert loaded is None

    def test_write_intention_to_memory_enabled(self):
        """Test writing intention to memory when enabled."""
        mock_memory = MagicMock()
        mock_memory.enabled = True
        mock_memory.write_planning_artifact.return_value = "test-point-id-123"

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        intention = manager.create_intention(
            raw_input="Build a REST API",
            intent_facts=["Fact 1"],
        )

        point_id = manager.write_intention_to_memory(intention)

        assert point_id == "test-point-id-123"
        mock_memory.write_planning_artifact.assert_called_once()
        call_kwargs = mock_memory.write_planning_artifact.call_args[1]
        assert call_kwargs["project_id"] == "autopack"
        assert call_kwargs["version"] == 1
        assert call_kwargs["status"] == "active"

    def test_write_intention_to_memory_disabled(self):
        """Test writing intention to memory when disabled (graceful degradation)."""
        mock_memory = MagicMock()
        mock_memory.enabled = False

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        intention = manager.create_intention(raw_input="Build a REST API")

        point_id = manager.write_intention_to_memory(intention)

        assert point_id is None
        mock_memory.write_planning_artifact.assert_not_called()

    def test_write_intention_to_memory_no_service(self):
        """Test writing intention when no memory service provided."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        assert manager.memory is None

        intention = manager.create_intention(raw_input="Build a REST API")
        point_id = manager.write_intention_to_memory(intention)

        assert point_id is None

    def test_retrieve_intention_from_memory_enabled(self):
        """Test retrieving intention from memory when enabled."""
        mock_memory = MagicMock()
        mock_memory.enabled = True
        mock_memory.search_planning.return_value = [
            {
                "id": "test-point-id",
                "score": 0.95,
                "payload": {
                    "type": "planning_artifact",
                    "summary": "Project intention: 2 facts",
                    "content_preview": "# Project Intention\n\nBuild a REST API",
                },
            }
        ]

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        result = manager.retrieve_intention_from_memory()

        assert result is not None
        assert result["id"] == "test-point-id"
        assert result["score"] == 0.95
        mock_memory.search_planning.assert_called_once()

    def test_retrieve_intention_from_memory_disabled(self):
        """Test retrieving intention from memory when disabled."""
        mock_memory = MagicMock()
        mock_memory.enabled = False

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        result = manager.retrieve_intention_from_memory()

        assert result is None
        mock_memory.search_planning.assert_not_called()

    def test_retrieve_intention_from_memory_not_found(self):
        """Test retrieving intention when none exists in memory."""
        mock_memory = MagicMock()
        mock_memory.enabled = True
        mock_memory.search_planning.return_value = []

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        result = manager.retrieve_intention_from_memory()

        assert result is None

    def test_get_intention_context_from_disk(self):
        """Test getting intention context from disk artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout

            intention = manager.create_intention(
                raw_input="Build a REST API",
                intent_facts=["Support JWT tokens"],
            )
            manager.write_intention_artifacts(intention)

            context = manager.get_intention_context()
            assert context
            assert "Project Intention" in context
            assert len(context) <= 2048

    def test_get_intention_context_size_bounded(self):
        """Test that intention context respects max_chars limit."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            layout = RunFileLayout(run_id="test-run-001", base_dir=base_dir)
            manager = ProjectIntentionManager(run_id="test-run-001")
            manager.layout = layout

            # Create large intention
            large_input = "x" * 5000
            intention = manager.create_intention(raw_input=large_input)
            manager.write_intention_artifacts(intention)

            context = manager.get_intention_context(max_chars=500)
            assert len(context) <= 500

    def test_get_intention_context_from_memory_fallback(self):
        """Test getting intention context from memory when disk unavailable."""
        mock_memory = MagicMock()
        mock_memory.enabled = True
        mock_memory.search_planning.return_value = [
            {
                "payload": {
                    "content_preview": "# Project Intention\n\nBuild a REST API",
                }
            }
        ]

        manager = ProjectIntentionManager(
            run_id="test-run-001",
            memory_service=mock_memory,
        )

        context = manager.get_intention_context()
        assert context
        assert "Project Intention" in context

    def test_get_intention_context_unavailable(self):
        """Test getting intention context when neither disk nor memory available."""
        manager = ProjectIntentionManager(run_id="test-run-001")
        context = manager.get_intention_context()
        assert context == ""


class TestConvenienceFunctions:
    """Test convenience functions."""

    def test_create_and_store_intention(self):
        """Test create_and_store_intention convenience function."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Mock memory service
            mock_memory = MagicMock()
            mock_memory.enabled = True
            mock_memory.write_planning_artifact.return_value = "test-point-id"

            # Patch RunFileLayout to use temp directory and explicit project_id
            with patch("autopack.project_intention.RunFileLayout") as mock_layout_class:
                mock_layout = RunFileLayout(
                    run_id="test-run-001",
                    project_id="test-project",
                    base_dir=base_dir,
                )
                mock_layout_class.return_value = mock_layout

                intention = create_and_store_intention(
                    run_id="test-run-001",
                    raw_input="Build a REST API",
                    project_id="test-project",
                    memory_service=mock_memory,
                    intent_facts=["Fact 1", "Fact 2"],
                    acceptance_criteria=["Tests pass"],
                )

                assert intention.project_id == "test-project"
                assert intention.intent_facts == ["Fact 1", "Fact 2"]
                assert intention.acceptance_criteria == ["Tests pass"]

                # Verify artifacts were written
                json_path = (
                    mock_layout.base_dir / "intention" / f"intent_{INTENTION_SCHEMA_VERSION}.json"
                )
                assert json_path.exists()

                # Verify memory was called
                mock_memory.write_planning_artifact.assert_called_once()
