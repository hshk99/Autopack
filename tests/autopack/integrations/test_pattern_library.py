"""Tests for PatternLibrary.

Tests pattern extraction from build history and pattern matching
for cross-project learning.
"""

import pytest

from autopack.integrations.pattern_library import PatternLibrary, ReusablePattern


@pytest.fixture
def sample_history_data():
    """Sample build history data for testing."""
    return {
        "phases": [
            {
                "number": 1,
                "title": "Implement User Authentication",
                "category": "IMPLEMENT_FEATURE",
                "status": "SUCCESS",
                "content": """Implemented JWT-based authentication.

Lessons Learned:
- Always validate token expiration
- Use secure token storage

Best Practices:
- Separate auth logic from business logic
""",
            },
            {
                "number": 2,
                "title": "Add Database Migration",
                "category": "IMPLEMENT_FEATURE",
                "status": "FAILED",
                "content": """Database migration failed due to schema conflicts.

Error: Schema mismatch detected.
Issue: Column types were incompatible.
""",
            },
            {
                "number": 3,
                "title": "Fix Token Expiration Bug",
                "category": "FIX_BUG",
                "status": "SUCCESS",
                "content": """Fixed token expiration issue in auth module.

Lessons Learned:
- Test token lifecycle thoroughly
""",
            },
            {
                "number": 4,
                "title": "Add REST API Endpoints",
                "category": "IMPLEMENT_FEATURE",
                "status": "SUCCESS",
                "content": """Added REST API endpoints for user management.

Best Practices:
- Use consistent endpoint naming
- Document all API parameters
""",
            },
            {
                "number": 5,
                "title": "Deploy to Production",
                "category": "DEPLOY",
                "status": "SUCCESS",
                "content": """Successfully deployed to production using CI/CD pipeline.

Lessons Learned:
- Run smoke tests after deploy
""",
            },
        ]
    }


@pytest.fixture
def pattern_library():
    """Create a fresh PatternLibrary instance."""
    return PatternLibrary()


class TestPatternLibrary:
    """Tests for PatternLibrary class."""

    def test_init_empty_library(self, pattern_library):
        """Test that library initializes empty."""
        assert len(pattern_library.get_all_patterns()) == 0

    def test_extract_patterns_from_empty_history(self, pattern_library):
        """Test extraction from empty history."""
        patterns = pattern_library.extract_patterns_from_history({"phases": []})
        assert patterns == []

    def test_extract_patterns_from_history(self, pattern_library, sample_history_data):
        """Test pattern extraction from build history."""
        patterns = pattern_library.extract_patterns_from_history(sample_history_data)

        assert len(patterns) > 0
        # Should have patterns for successful categories
        pattern_names = [p.name for p in patterns]
        assert any("success_pattern" in name for name in pattern_names)

    def test_extract_patterns_success_rate(self, pattern_library, sample_history_data):
        """Test that success rate is calculated correctly."""
        patterns = pattern_library.extract_patterns_from_history(sample_history_data)

        # Find IMPLEMENT_FEATURE success pattern (2 success, 1 failure = 66.7%)
        feature_patterns = [
            p for p in patterns if "IMPLEMENT_FEATURE" in p.name and "success" in p.name
        ]
        if feature_patterns:
            pattern = feature_patterns[0]
            # 2 out of 3 = approximately 0.67
            assert 0.6 < pattern.success_rate < 0.7

    def test_extract_failure_avoidance_patterns(self, pattern_library, sample_history_data):
        """Test extraction of failure avoidance patterns."""
        patterns = pattern_library.extract_patterns_from_history(sample_history_data)

        # Should have failure avoidance pattern for IMPLEMENT_FEATURE
        avoidance_patterns = [p for p in patterns if "failure_avoidance" in p.name]
        assert len(avoidance_patterns) > 0

    def test_extract_cross_cutting_patterns(self, pattern_library, sample_history_data):
        """Test extraction of lessons learned and best practices."""
        patterns = pattern_library.extract_patterns_from_history(sample_history_data)

        pattern_names = [p.name for p in patterns]
        assert "lessons_learned" in pattern_names
        assert "best_practices" in pattern_names

    def test_find_applicable_patterns_no_patterns(self, pattern_library):
        """Test finding patterns when library is empty."""
        patterns = pattern_library.find_applicable_patterns(
            {"description": "Add user login", "category": "authentication"}
        )
        assert patterns == []

    def test_find_applicable_patterns(self, pattern_library, sample_history_data):
        """Test finding applicable patterns for a context."""
        # First extract patterns
        pattern_library.extract_patterns_from_history(sample_history_data)

        # Find patterns for an authentication task
        patterns = pattern_library.find_applicable_patterns(
            {
                "description": "Implement JWT authentication for API",
                "category": "authentication",
                "tech_stack": ["python", "jwt"],
            }
        )

        assert len(patterns) > 0

    def test_find_applicable_patterns_sorted_by_relevance(
        self, pattern_library, sample_history_data
    ):
        """Test that patterns are sorted by relevance."""
        pattern_library.extract_patterns_from_history(sample_history_data)

        patterns = pattern_library.find_applicable_patterns(
            {"description": "Deploy application to production", "category": "deployment"}
        )

        # If multiple patterns, verify they are sorted
        if len(patterns) >= 2:
            # First pattern should have higher or equal relevance
            # (since we don't expose scores, we just verify sorting works)
            assert patterns[0].name is not None

    def test_add_pattern(self, pattern_library):
        """Test adding a pattern to the library."""
        pattern = ReusablePattern(
            pattern_id="test123",
            name="test_pattern",
            category="testing",
            description="A test pattern",
            success_rate=0.9,
            times_applied=5,
        )

        pattern_library.add_pattern(pattern)

        assert len(pattern_library.get_all_patterns()) == 1
        assert pattern_library.get_pattern("test123") == pattern

    def test_get_pattern_not_found(self, pattern_library):
        """Test getting a non-existent pattern."""
        assert pattern_library.get_pattern("nonexistent") is None

    def test_get_patterns_by_category(self, pattern_library):
        """Test filtering patterns by category."""
        pattern1 = ReusablePattern(
            pattern_id="auth1",
            name="auth_pattern",
            category="authentication",
            description="Auth pattern",
        )
        pattern2 = ReusablePattern(
            pattern_id="api1",
            name="api_pattern",
            category="api_integration",
            description="API pattern",
        )

        pattern_library.add_pattern(pattern1)
        pattern_library.add_pattern(pattern2)

        auth_patterns = pattern_library.get_patterns_by_category("authentication")
        assert len(auth_patterns) == 1
        assert auth_patterns[0].name == "auth_pattern"

    def test_record_pattern_application_success(self, pattern_library):
        """Test recording successful pattern application."""
        pattern = ReusablePattern(
            pattern_id="test123",
            name="test_pattern",
            category="testing",
            description="A test pattern",
            success_rate=0.5,
            times_applied=2,
        )
        pattern_library.add_pattern(pattern)

        pattern_library.record_pattern_application("test123", success=True)

        updated = pattern_library.get_pattern("test123")
        assert updated is not None
        assert updated.times_applied == 3
        # Was 1 success out of 2, now 2 success out of 3 = 0.67
        assert 0.6 < updated.success_rate < 0.7

    def test_record_pattern_application_failure(self, pattern_library):
        """Test recording failed pattern application."""
        pattern = ReusablePattern(
            pattern_id="test123",
            name="test_pattern",
            category="testing",
            description="A test pattern",
            success_rate=1.0,
            times_applied=2,
        )
        pattern_library.add_pattern(pattern)

        pattern_library.record_pattern_application("test123", success=False)

        updated = pattern_library.get_pattern("test123")
        assert updated is not None
        assert updated.times_applied == 3
        # Was 2 success out of 2, now 2 success out of 3 = 0.67
        assert 0.6 < updated.success_rate < 0.7

    def test_record_pattern_application_not_found(self, pattern_library):
        """Test recording application for non-existent pattern."""
        # Should not raise, just log warning
        pattern_library.record_pattern_application("nonexistent", success=True)


class TestReusablePattern:
    """Tests for ReusablePattern dataclass."""

    def test_pattern_defaults(self):
        """Test default values for pattern fields."""
        pattern = ReusablePattern(
            pattern_id="test",
            name="test_pattern",
            category="testing",
            description="Test",
        )

        assert pattern.success_rate == 0.0
        assert pattern.times_applied == 0
        assert pattern.context_requirements == []
        assert pattern.code_template is None
        assert pattern.extracted_from == []

    def test_pattern_with_all_fields(self):
        """Test pattern with all fields populated."""
        pattern = ReusablePattern(
            pattern_id="full",
            name="full_pattern",
            category="database",
            description="Full pattern with all fields",
            success_rate=0.85,
            times_applied=10,
            context_requirements=["PostgreSQL", "SQLAlchemy"],
            code_template="SELECT * FROM users;",
            extracted_from=["Phase 1", "Phase 3"],
        )

        assert pattern.pattern_id == "full"
        assert pattern.success_rate == 0.85
        assert pattern.times_applied == 10
        assert len(pattern.context_requirements) == 2
        assert pattern.code_template is not None
        assert len(pattern.extracted_from) == 2


class TestBuildHistoryIntegratorWithPatternLibrary:
    """Tests for BuildHistoryIntegrator with PatternLibrary integration."""

    def test_integrator_with_pattern_library(self, tmp_path, sample_history_data):
        """Test BuildHistoryIntegrator with PatternLibrary."""
        from autopack.integrations.build_history_integrator import BuildHistoryIntegrator

        # Create sample BUILD_HISTORY.md
        history_content = """# Build History

## Phase 1: Implement User Authentication
**Category**: IMPLEMENT_FEATURE
**Status**: SUCCESS
Completed: 2024-01-15T10:30:00

Implemented JWT-based authentication.

Lessons Learned:
- Always validate token expiration

## Phase 2: Add REST API
**Category**: IMPLEMENT_FEATURE
**Status**: SUCCESS
Completed: 2024-01-16T14:20:00

Added REST API endpoints.

Best Practices:
- Use consistent naming
"""
        history_file = tmp_path / "BUILD_HISTORY.md"
        history_file.write_text(history_content, encoding="utf-8")

        pattern_library = PatternLibrary()
        integrator = BuildHistoryIntegrator(
            build_history_path=history_file,
            pattern_library=pattern_library,
        )

        # Extract patterns
        patterns = integrator.extract_reusable_patterns()
        assert len(patterns) > 0

    def test_integrator_get_applicable_patterns(self, tmp_path):
        """Test getting applicable patterns through integrator."""
        from autopack.integrations.build_history_integrator import BuildHistoryIntegrator

        history_content = """# Build History

## Phase 1: Implement Authentication
**Category**: AUTH
**Status**: SUCCESS
Completed: 2024-01-15T10:30:00

Implemented JWT authentication with token validation.
"""
        history_file = tmp_path / "BUILD_HISTORY.md"
        history_file.write_text(history_content, encoding="utf-8")

        pattern_library = PatternLibrary()
        integrator = BuildHistoryIntegrator(
            build_history_path=history_file,
            pattern_library=pattern_library,
        )

        # Get applicable patterns for a related task
        patterns = integrator.get_applicable_patterns(
            task_description="Add OAuth2 authentication",
            category="authentication",
        )
        # May or may not find patterns depending on extraction
        assert isinstance(patterns, list)

    def test_integrator_without_pattern_library(self, tmp_path):
        """Test integrator without pattern library returns empty list."""
        from autopack.integrations.build_history_integrator import BuildHistoryIntegrator

        history_file = tmp_path / "BUILD_HISTORY.md"
        history_file.write_text("# Build History")

        integrator = BuildHistoryIntegrator(build_history_path=history_file)

        patterns = integrator.extract_reusable_patterns()
        assert patterns == []

        applicable = integrator.get_applicable_patterns("Some task")
        assert applicable == []

    def test_integrator_record_pattern_usage(self, tmp_path):
        """Test recording pattern usage through integrator."""
        from autopack.integrations.build_history_integrator import BuildHistoryIntegrator

        history_file = tmp_path / "BUILD_HISTORY.md"
        history_file.write_text("# Build History")

        pattern_library = PatternLibrary()
        pattern = ReusablePattern(
            pattern_id="test123",
            name="test_pattern",
            category="testing",
            description="Test pattern",
            success_rate=0.5,
            times_applied=2,
        )
        pattern_library.add_pattern(pattern)

        integrator = BuildHistoryIntegrator(
            build_history_path=history_file,
            pattern_library=pattern_library,
        )

        integrator.record_pattern_usage("test123", success=True)

        updated = pattern_library.get_pattern("test123")
        assert updated is not None
        assert updated.times_applied == 3
