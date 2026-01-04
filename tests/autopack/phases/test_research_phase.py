"""Tests for research phase implementation."""

import pytest

from autopack.phases.research_phase import (
    ResearchPhase,
    ResearchPhaseManager,
    ResearchQuery,
    ResearchResult,
    ResearchStatus,
    ResearchPriority,
    create_research_phase_from_task,
)


@pytest.fixture
def manager(tmp_path):
    """Create research phase manager."""
    return ResearchPhaseManager(storage_dir=tmp_path / "research")


@pytest.fixture
def sample_queries():
    """Sample research queries."""
    return [
        ResearchQuery(
            query_text="Best practices for API design",
            context={"language": "Python"},
        ),
        ResearchQuery(
            query_text="Common API security issues",
            max_results=5,
        ),
    ]


class TestResearchPhase:
    """Test research phase data structures."""
    
    def test_research_phase_creation(self, sample_queries):
        """Test creating a research phase."""
        phase = ResearchPhase(
            phase_id="test_phase",
            title="Test Research",
            description="Testing research phase",
            queries=sample_queries,
        )
        
        assert phase.phase_id == "test_phase"
        assert phase.status == ResearchStatus.PENDING
        assert len(phase.queries) == 2
        assert len(phase.results) == 0
    
    def test_research_phase_serialization(self, sample_queries):
        """Test phase serialization."""
        phase = ResearchPhase(
            phase_id="test_phase",
            title="Test Research",
            description="Testing",
            queries=sample_queries,
        )
        
        # Serialize
        data = phase.to_dict()
        assert data["phase_id"] == "test_phase"
        assert data["status"] == "pending"
        
        # Deserialize
        restored = ResearchPhase.from_dict(data)
        assert restored.phase_id == phase.phase_id
        assert restored.status == phase.status
        assert len(restored.queries) == len(phase.queries)


class TestResearchPhaseManager:
    """Test research phase manager."""
    
    def test_create_phase(self, manager, sample_queries):
        """Test creating a phase."""
        phase = manager.create_phase(
            title="Test Research",
            description="Testing phase creation",
            queries=sample_queries,
            priority=ResearchPriority.HIGH,
        )
        
        assert phase.phase_id.startswith("research_")
        assert phase.status == ResearchStatus.PENDING
        assert phase.priority == ResearchPriority.HIGH
        
        # Should be retrievable
        retrieved = manager.get_phase(phase.phase_id)
        assert retrieved is not None
        assert retrieved.phase_id == phase.phase_id
    
    def test_start_phase(self, manager, sample_queries):
        """Test starting a phase."""
        phase = manager.create_phase(
            title="Test",
            description="Test",
            queries=sample_queries,
        )
        
        manager.start_phase(phase.phase_id)
        
        updated = manager.get_phase(phase.phase_id)
        assert updated.status == ResearchStatus.IN_PROGRESS
        assert updated.started_at is not None
    
    def test_add_result(self, manager, sample_queries):
        """Test adding research results."""
        phase = manager.create_phase(
            title="Test",
            description="Test",
            queries=sample_queries,
        )
        
        result = ResearchResult(
            query=sample_queries[0],
            findings=[{"title": "Finding 1"}],
            summary="Test summary",
            confidence=0.85,
        )
        
        manager.add_result(phase.phase_id, result)
        
        updated = manager.get_phase(phase.phase_id)
        assert len(updated.results) == 1
        assert updated.results[0].confidence == 0.85
    
    def test_complete_phase(self, manager, sample_queries):
        """Test completing a phase."""
        phase = manager.create_phase(
            title="Test",
            description="Test",
            queries=sample_queries,
        )
        
        manager.complete_phase(phase.phase_id, success=True)
        
        updated = manager.get_phase(phase.phase_id)
        assert updated.status == ResearchStatus.COMPLETED
        assert updated.completed_at is not None
    
    def test_cancel_phase(self, manager, sample_queries):
        """Test cancelling a phase."""
        phase = manager.create_phase(
            title="Test",
            description="Test",
            queries=sample_queries,
        )
        
        manager.cancel_phase(phase.phase_id)
        
        updated = manager.get_phase(phase.phase_id)
        assert updated.status == ResearchStatus.CANCELLED
    
    def test_list_phases(self, manager, sample_queries):
        """Test listing phases."""
        # Create multiple phases
        phase1 = manager.create_phase(
            title="Test 1",
            description="Test",
            queries=sample_queries,
            priority=ResearchPriority.HIGH,
        )
        
        phase2 = manager.create_phase(
            title="Test 2",
            description="Test",
            queries=sample_queries,
            priority=ResearchPriority.LOW,
        )
        
        manager.complete_phase(phase1.phase_id)
        
        # List all
        all_phases = manager.list_phases()
        assert len(all_phases) == 2
        
        # Filter by status
        pending = manager.list_phases(status=ResearchStatus.PENDING)
        assert len(pending) == 1
        assert pending[0].phase_id == phase2.phase_id
        
        # Filter by priority
        high_priority = manager.list_phases(priority=ResearchPriority.HIGH)
        assert len(high_priority) == 1
        assert high_priority[0].phase_id == phase1.phase_id
    
    def test_persistence(self, tmp_path, sample_queries):
        """Test phase persistence across manager instances."""
        storage_dir = tmp_path / "research"
        
        # Create phase with first manager
        manager1 = ResearchPhaseManager(storage_dir=storage_dir)
        phase = manager1.create_phase(
            title="Test",
            description="Test persistence",
            queries=sample_queries,
        )
        
        # Load with second manager
        manager2 = ResearchPhaseManager(storage_dir=storage_dir)
        retrieved = manager2.get_phase(phase.phase_id)
        
        assert retrieved is not None
        assert retrieved.phase_id == phase.phase_id
        assert retrieved.title == phase.title


class TestCreateResearchPhaseFromTask:
    """Test automatic research phase creation from tasks."""
    
    def test_create_from_task(self, tmp_path):
        """Test creating research phase from task description."""
        phase = create_research_phase_from_task(
            task_description="Implement user authentication system",
            task_category="IMPLEMENT_FEATURE",
            context={"framework": "Django"},
        )
        
        assert phase.phase_id.startswith("research_")
        assert "authentication" in phase.description.lower()
        assert len(phase.queries) >= 3  # Should generate multiple queries
        assert phase.metadata["task_category"] == "IMPLEMENT_FEATURE"
        assert phase.metadata["auto_generated"] is True
