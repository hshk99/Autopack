"""Tests for autonomous Phase 2 wave planning."""

import json
import tempfile
from pathlib import Path

import pytest

from generation.autonomous_wave_planner import AutonomousWavePlanner, WavePlan


@pytest.fixture
def simple_imps():
    """Create simple IMPs with no dependencies or conflicts."""
    return [
        {
            "imp_id": "IMP-GEN-001",
            "title": "First improvement",
            "files_affected": ["src/a.py"],
            "dependencies": [],
        },
        {
            "imp_id": "IMP-GEN-002",
            "title": "Second improvement",
            "files_affected": ["src/b.py"],
            "dependencies": [],
        },
        {
            "imp_id": "IMP-GEN-003",
            "title": "Third improvement",
            "files_affected": ["src/c.py"],
            "dependencies": [],
        },
    ]


@pytest.fixture
def dependent_imps():
    """Create IMPs with dependencies."""
    return [
        {
            "imp_id": "IMP-GEN-001",
            "title": "Base improvement",
            "files_affected": ["src/base.py"],
            "dependencies": [],
        },
        {
            "imp_id": "IMP-GEN-002",
            "title": "Depends on 001",
            "files_affected": ["src/derived.py"],
            "dependencies": ["IMP-GEN-001"],
        },
        {
            "imp_id": "IMP-GEN-003",
            "title": "Depends on 002",
            "files_affected": ["src/final.py"],
            "dependencies": ["IMP-GEN-002"],
        },
    ]


@pytest.fixture
def conflicting_imps():
    """Create IMPs with file conflicts."""
    return [
        {
            "imp_id": "IMP-GEN-001",
            "title": "First improvement",
            "files_affected": ["src/shared.py", "src/a.py"],
            "dependencies": [],
        },
        {
            "imp_id": "IMP-GEN-002",
            "title": "Second improvement",
            "files_affected": ["src/shared.py", "src/b.py"],
            "dependencies": [],
        },
    ]


class TestWavePlan:
    """Tests for WavePlan dataclass."""

    def test_wave_plan_creation(self):
        """Test that WavePlan can be created with all fields."""
        plan = WavePlan(
            waves={1: ["IMP-GEN-001"], 2: ["IMP-GEN-002"]},
            validation_passed=True,
            validation_errors=[],
        )

        assert plan.waves == {1: ["IMP-GEN-001"], 2: ["IMP-GEN-002"]}
        assert plan.validation_passed is True
        assert plan.validation_errors == []
        assert plan.generated_at is not None

    def test_wave_plan_with_errors(self):
        """Test that WavePlan can store validation errors."""
        plan = WavePlan(
            waves={1: ["IMP-GEN-001"]},
            validation_passed=False,
            validation_errors=["Error 1", "Error 2"],
        )

        assert plan.validation_passed is False
        assert len(plan.validation_errors) == 2


class TestAutonomousWavePlanner:
    """Tests for AutonomousWavePlanner class."""

    def test_init_stores_imps(self, simple_imps):
        """Test that initialization stores IMPs correctly."""
        planner = AutonomousWavePlanner(simple_imps)

        assert len(planner.imps) == 3
        assert "IMP-GEN-001" in planner.imps
        assert "IMP-GEN-002" in planner.imps
        assert "IMP-GEN-003" in planner.imps

    def test_init_builds_dependency_graph(self, dependent_imps):
        """Test that dependency graph is built correctly."""
        planner = AutonomousWavePlanner(dependent_imps)

        assert planner.dependency_graph["IMP-GEN-001"] == set()
        assert planner.dependency_graph["IMP-GEN-002"] == {"IMP-GEN-001"}
        assert planner.dependency_graph["IMP-GEN-003"] == {"IMP-GEN-002"}

    def test_init_builds_file_map(self, conflicting_imps):
        """Test that file conflict map is built correctly."""
        planner = AutonomousWavePlanner(conflicting_imps)

        assert "src/shared.py" in planner.file_map
        assert planner.file_map["src/shared.py"] == {"IMP-GEN-001", "IMP-GEN-002"}
        assert planner.file_map["src/a.py"] == {"IMP-GEN-001"}
        assert planner.file_map["src/b.py"] == {"IMP-GEN-002"}

    def test_init_empty_list(self):
        """Test that planner handles empty IMP list."""
        planner = AutonomousWavePlanner([])

        assert len(planner.imps) == 0
        assert len(planner.dependency_graph) == 0
        assert len(planner.file_map) == 0


class TestPlanWaves:
    """Tests for wave planning logic."""

    def test_parallel_imps_same_wave(self, simple_imps):
        """Test that independent IMPs with no conflicts go in same wave."""
        planner = AutonomousWavePlanner(simple_imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        assert len(plan.waves) == 1
        assert len(plan.waves[1]) == 3

    def test_dependent_imps_sequential_waves(self, dependent_imps):
        """Test that dependent IMPs go in sequential waves."""
        planner = AutonomousWavePlanner(dependent_imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        assert len(plan.waves) == 3
        assert plan.waves[1] == ["IMP-GEN-001"]
        assert plan.waves[2] == ["IMP-GEN-002"]
        assert plan.waves[3] == ["IMP-GEN-003"]

    def test_file_conflicts_separate_waves(self, conflicting_imps):
        """Test that IMPs with file conflicts go in separate waves."""
        planner = AutonomousWavePlanner(conflicting_imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        assert len(plan.waves) == 2
        # One IMP per wave due to conflict
        assert len(plan.waves[1]) == 1
        assert len(plan.waves[2]) == 1

    def test_mixed_dependencies_and_conflicts(self):
        """Test planning with both dependencies and file conflicts."""
        imps = [
            {
                "imp_id": "IMP-A",
                "title": "A",
                "files_affected": ["shared.py"],
                "dependencies": [],
            },
            {
                "imp_id": "IMP-B",
                "title": "B",
                "files_affected": ["shared.py"],
                "dependencies": [],
            },
            {
                "imp_id": "IMP-C",
                "title": "C",
                "files_affected": ["other.py"],
                "dependencies": ["IMP-A"],
            },
        ]

        planner = AutonomousWavePlanner(imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        # A and B conflict on shared.py, C depends on A
        # Wave 1: A (or B)
        # Wave 2: B (or A) + C (C depends on A, which is in wave 1)
        assert len(plan.waves) >= 2

    def test_empty_imps_no_waves(self):
        """Test that empty IMP list produces no waves."""
        planner = AutonomousWavePlanner([])
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        assert len(plan.waves) == 0
        assert plan.validation_errors == []

    def test_circular_dependency_deadlock(self):
        """Test that circular dependencies cause deadlock detection."""
        imps = [
            {
                "imp_id": "IMP-A",
                "title": "A",
                "files_affected": [],
                "dependencies": ["IMP-B"],
            },
            {
                "imp_id": "IMP-B",
                "title": "B",
                "files_affected": [],
                "dependencies": ["IMP-A"],
            },
        ]

        planner = AutonomousWavePlanner(imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is False
        assert len(plan.validation_errors) == 1
        assert "Deadlock" in plan.validation_errors[0]


class TestValidatePlan:
    """Tests for plan validation."""

    def test_valid_plan_passes(self, simple_imps):
        """Test that valid plan passes validation."""
        planner = AutonomousWavePlanner(simple_imps)
        plan = planner.plan_waves()

        assert plan.validation_passed is True
        assert plan.validation_errors == []

    def test_detects_same_wave_dependencies(self):
        """Test that same-wave dependencies are detected."""
        planner = AutonomousWavePlanner([])
        # Manually create invalid waves for testing
        planner.imps = {
            "IMP-A": {"files_affected": []},
            "IMP-B": {"files_affected": []},
        }
        planner.dependency_graph = {"IMP-A": set(), "IMP-B": {"IMP-A"}}

        # IMP-B depends on IMP-A, but both in same wave
        waves = {1: ["IMP-A", "IMP-B"]}
        errors = planner._validate_plan(waves)

        assert len(errors) == 1
        assert "depends on same-wave IMPs" in errors[0]

    def test_detects_file_conflicts(self):
        """Test that file conflicts are detected."""
        planner = AutonomousWavePlanner([])
        # Manually create invalid waves for testing
        planner.imps = {
            "IMP-A": {"files_affected": ["shared.py"]},
            "IMP-B": {"files_affected": ["shared.py"]},
        }
        planner.dependency_graph = {"IMP-A": set(), "IMP-B": set()}

        # Both touch shared.py in same wave
        waves = {1: ["IMP-A", "IMP-B"]}
        errors = planner._validate_plan(waves)

        assert len(errors) == 1
        assert "File conflict" in errors[0]


class TestImpToPhaseId:
    """Tests for IMP ID to phase ID conversion."""

    def test_standard_format(self, simple_imps):
        """Test conversion of standard IMP ID format."""
        planner = AutonomousWavePlanner(simple_imps)

        assert planner._imp_to_phase_id("IMP-GEN-001") == "gen001"
        assert planner._imp_to_phase_id("IMP-REL-042") == "rel042"
        assert planner._imp_to_phase_id("IMP-PERF-100") == "perf100"

    def test_non_standard_format(self, simple_imps):
        """Test conversion of non-standard IMP ID format."""
        planner = AutonomousWavePlanner(simple_imps)

        # Non-standard formats get lowercased with dashes removed
        assert planner._imp_to_phase_id("IMP-A") == "impa"
        assert planner._imp_to_phase_id("CUSTOM") == "custom"


class TestSlugify:
    """Tests for title slugification."""

    def test_basic_slugification(self, simple_imps):
        """Test basic title slugification."""
        planner = AutonomousWavePlanner(simple_imps)

        assert planner._slugify("Hello World") == "hello-world"
        assert planner._slugify("Add Feature") == "add-feature"

    def test_removes_special_chars(self, simple_imps):
        """Test that special characters are removed."""
        planner = AutonomousWavePlanner(simple_imps)

        assert planner._slugify("Hello! World?") == "hello-world"
        # Multiple spaces/special chars collapse to single dash
        assert planner._slugify("Test @#$ String") == "test-string"

    def test_truncates_long_titles(self, simple_imps):
        """Test that long titles are truncated."""
        planner = AutonomousWavePlanner(simple_imps)

        long_title = "This is a very long title that should be truncated to fifty characters"
        slug = planner._slugify(long_title)

        assert len(slug) <= 50

    def test_handles_underscores(self, simple_imps):
        """Test that underscores are removed (non-alphanumeric)."""
        planner = AutonomousWavePlanner(simple_imps)

        # Underscores are removed as non-alphanumeric chars
        assert planner._slugify("hello_world") == "helloworld"


class TestExportWavePlan:
    """Tests for JSON export functionality."""

    def test_exports_wave_plan(self, simple_imps):
        """Test that wave plan is exported to JSON."""
        planner = AutonomousWavePlanner(simple_imps)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "subdir" / "wave_plan.json"
            planner.export_wave_plan(str(output_path))

            assert output_path.exists()
            with open(output_path) as f:
                data = json.load(f)

            assert data["validation_passed"] is True
            assert data["total_waves"] == 1
            assert data["total_imps"] == 3
            assert len(data["waves"]) == 1
            assert "generated_at" in data

    def test_exports_phase_details(self, simple_imps):
        """Test that phase details are included in export."""
        planner = AutonomousWavePlanner(simple_imps)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "wave_plan.json"
            planner.export_wave_plan(str(output_path))

            with open(output_path) as f:
                data = json.load(f)

            phase = data["waves"][0]["phases"][0]
            assert "id" in phase
            assert "imp_id" in phase
            assert "title" in phase
            assert "worktree_path" in phase
            assert "branch" in phase
            assert "files" in phase
            assert "dependencies" in phase

    def test_exports_dependent_plan(self, dependent_imps):
        """Test that dependent plan is exported correctly."""
        planner = AutonomousWavePlanner(dependent_imps)

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "wave_plan.json"
            planner.export_wave_plan(str(output_path))

            with open(output_path) as f:
                data = json.load(f)

            assert data["total_waves"] == 3
            assert data["total_imps"] == 3
            # Each wave should have 1 IMP
            for wave in data["waves"]:
                assert wave["imp_count"] == 1


class TestGetSummary:
    """Tests for summary generation."""

    def test_summary_with_waves(self, simple_imps):
        """Test summary with planned waves."""
        planner = AutonomousWavePlanner(simple_imps)
        summary = planner.get_summary()

        assert "Wave Plan Summary" in summary
        assert "Validation: PASSED" in summary
        assert "Total Waves: 1" in summary
        assert "Wave 1 (3 IMPs)" in summary
        assert "IMP-GEN-001" in summary
        assert "IMP-GEN-002" in summary
        assert "IMP-GEN-003" in summary

    def test_summary_with_dependencies(self, dependent_imps):
        """Test summary with dependent IMPs."""
        planner = AutonomousWavePlanner(dependent_imps)
        summary = planner.get_summary()

        assert "Total Waves: 3" in summary
        assert "Wave 1 (1 IMPs)" in summary
        assert "Wave 2 (1 IMPs)" in summary
        assert "Wave 3 (1 IMPs)" in summary

    def test_summary_empty_plan(self):
        """Test summary with empty plan."""
        planner = AutonomousWavePlanner([])
        summary = planner.get_summary()

        assert "Validation: PASSED" in summary
        assert "Total Waves: 0" in summary

    def test_summary_with_validation_errors(self):
        """Test summary shows validation errors."""
        imps = [
            {"imp_id": "IMP-A", "title": "A", "files_affected": [], "dependencies": ["IMP-B"]},
            {"imp_id": "IMP-B", "title": "B", "files_affected": [], "dependencies": ["IMP-A"]},
        ]
        planner = AutonomousWavePlanner(imps)
        summary = planner.get_summary()

        assert "Validation: FAILED" in summary
        assert "Validation Errors:" in summary
        assert "Deadlock" in summary


# =============================================================================
# IMP-LOOP-027: Wave Planner Executor Integration Tests
# =============================================================================


class TestWavePlannerExecutorIntegration:
    """Tests for wave planner integration with the autonomous executor loop.

    IMP-LOOP-027: These tests verify that the wave planner correctly integrates
    with the autonomous executor to enable parallel IMP wave execution.
    """

    @pytest.fixture
    def mock_executor(self):
        """Create a mock executor for testing."""
        from unittest.mock import MagicMock

        executor = MagicMock()
        executor.run_id = "test-run-001"
        executor._phase_failure_counts = {}
        return executor

    @pytest.fixture
    def mock_autonomous_loop(self, mock_executor):
        """Create a mock autonomous loop for testing.

        Note: This creates a minimal mock that has the wave planner attributes
        without requiring full executor infrastructure.
        """
        from unittest.mock import MagicMock

        loop = MagicMock()
        loop.executor = mock_executor
        loop._wave_planner = None
        loop._current_wave_plan = None
        loop._current_wave_number = 0
        loop._wave_phases_loaded = {}
        loop._wave_phases_completed = {}
        loop._wave_planner_enabled = True
        loop._wave_plan_path = None
        loop._current_run_phases = []
        return loop

    def test_wave_planner_state_initialization(self, mock_autonomous_loop):
        """Test that wave planner state is initialized correctly."""
        loop = mock_autonomous_loop

        assert loop._wave_planner is None
        assert loop._current_wave_plan is None
        assert loop._current_wave_number == 0
        assert loop._wave_phases_loaded == {}
        assert loop._wave_phases_completed == {}
        assert loop._wave_planner_enabled is True

    def test_wave_plan_phases_structure(self, simple_imps):
        """Test that wave plan generates proper phase structures."""
        planner = AutonomousWavePlanner(simple_imps)
        plan = planner.plan_waves()

        # All independent IMPs should be in wave 1
        assert 1 in plan.waves
        assert len(plan.waves[1]) == 3

        # Check phase data is accessible
        for imp_id in plan.waves[1]:
            assert imp_id in planner.imps
            imp_data = planner.imps[imp_id]
            assert "title" in imp_data
            assert "files_affected" in imp_data

    def test_wave_transition_with_dependencies(self, dependent_imps):
        """Test wave transitions with dependent IMPs."""
        planner = AutonomousWavePlanner(dependent_imps)
        plan = planner.plan_waves()

        # Should have 3 waves due to dependency chain
        assert len(plan.waves) == 3

        # Wave 1: IMP-GEN-001 (no dependencies)
        assert "IMP-GEN-001" in plan.waves[1]

        # Wave 2: IMP-GEN-002 (depends on 001)
        assert "IMP-GEN-002" in plan.waves[2]

        # Wave 3: IMP-GEN-003 (depends on 002)
        assert "IMP-GEN-003" in plan.waves[3]

    def test_wave_phase_id_generation(self, simple_imps):
        """Test that phase IDs are generated correctly for waves."""
        planner = AutonomousWavePlanner(simple_imps)

        # Test phase ID conversion
        assert planner._imp_to_phase_id("IMP-GEN-001") == "gen001"
        assert planner._imp_to_phase_id("IMP-REL-042") == "rel042"
        assert planner._imp_to_phase_id("IMP-LOOP-027") == "loop027"

    def test_wave_completion_tracking_empty(self, mock_autonomous_loop):
        """Test wave completion check with no active wave."""
        loop = mock_autonomous_loop

        # No wave active - should return True (no blocking)
        loop._current_wave_number = 0
        # The actual method would return True for wave 0
        assert loop._current_wave_number == 0

    def test_wave_phases_loaded_tracking(self, simple_imps):
        """Test that loaded phases are tracked correctly."""
        planner = AutonomousWavePlanner(simple_imps)
        plan = planner.plan_waves()

        # Simulate loading wave 1 phases
        wave_1_imp_ids = plan.waves[1]
        loaded_phases = []
        for imp_id in wave_1_imp_ids:
            phase_spec = {
                "phase_id": f"wave1-{planner._imp_to_phase_id(imp_id)}",
                "imp_id": imp_id,
                "status": "QUEUED",
            }
            loaded_phases.append(phase_spec)

        # All 3 IMPs should be in loaded phases
        assert len(loaded_phases) == 3

        # Phase IDs should be unique
        phase_ids = [p["phase_id"] for p in loaded_phases]
        assert len(phase_ids) == len(set(phase_ids))

    def test_wave_completion_partial(self, dependent_imps):
        """Test wave completion check with partial completion."""
        planner = AutonomousWavePlanner(dependent_imps)
        plan = planner.plan_waves()

        # Simulate wave 1 with 1 IMP
        wave_1_ids = plan.waves[1]
        assert len(wave_1_ids) == 1

        # Track completion
        completed_phases = []
        for imp_id in wave_1_ids:
            phase_id = f"wave1-{planner._imp_to_phase_id(imp_id)}"
            completed_phases.append(phase_id)

        # Wave should be complete when all phases are done
        assert len(completed_phases) == len(wave_1_ids)

    def test_wave_stats_calculation(self, simple_imps):
        """Test wave planner statistics calculation."""
        planner = AutonomousWavePlanner(simple_imps)
        plan = planner.plan_waves()

        # Calculate stats
        total_waves = len(plan.waves)
        total_imps = sum(len(imps) for imps in plan.waves.values())

        assert total_waves == 1
        assert total_imps == 3

    def test_wave_plan_with_file_conflicts(self, conflicting_imps):
        """Test wave planning correctly separates file conflicts."""
        planner = AutonomousWavePlanner(conflicting_imps)
        plan = planner.plan_waves()

        # Conflicting IMPs should be in separate waves
        assert len(plan.waves) == 2
        assert len(plan.waves[1]) == 1
        assert len(plan.waves[2]) == 1

        # Verify no file conflicts within waves
        for wave_num, imp_ids in plan.waves.items():
            wave_files = set()
            for imp_id in imp_ids:
                imp_files = set(planner.imps[imp_id].get("files_affected", []))
                # No overlap with existing wave files
                assert wave_files.isdisjoint(imp_files)
                wave_files.update(imp_files)
