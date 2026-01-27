"""Tests for memory context injection into builder prompts.

Tests IMP-ARCH-002: Integrate Memory Context Retrieval into Executor Phase Loop
"""

import pytest
from unittest.mock import Mock

from autopack.memory.context_injector import ContextInjector, ContextInjection
from autopack.memory.memory_service import MemoryService


@pytest.fixture
def mock_memory_service():
    """Create a mock MemoryService for testing."""
    service = Mock(spec=MemoryService)
    service.enabled = True

    # Mock search methods to return sample results
    service.search_errors.return_value = [
        {
            "payload": {
                "error_snippet": "Timeout error in API call",
                "error_type": "timeout",
            }
        },
        {
            "payload": {
                "error_snippet": "Connection refused to database",
                "error_type": "connection",
            }
        },
    ]

    service.search_summaries.return_value = [
        {
            "payload": {
                "summary": "Used async/await pattern for I/O operations to avoid blocking",
            }
        },
        {
            "payload": {
                "summary": "Implemented circuit breaker for external API calls",
            }
        },
    ]

    service.search_doctor_hints.return_value = [
        {
            "payload": {
                "hint": "Check rate limits on external APIs before making calls",
            }
        },
    ]

    service.search_code.return_value = [
        {
            "payload": {
                "content": "User authentication module uses OAuth 2.0 with JWT tokens",
            }
        },
        {
            "payload": {
                "content": "Database connection pooling is configured with max 20 connections",
            }
        },
    ]

    return service


class TestContextInjector:
    """Test ContextInjector class."""

    @pytest.fixture(autouse=True)
    def mock_default_memory_service(self, monkeypatch):
        """Prevent real MemoryService creation when not explicitly provided.

        IMP-TEST-001: Tests that create ContextInjector() without passing a
        memory_service would otherwise trigger real Qdrant connection attempts,
        causing 24-second timeouts per test in CI environments without Qdrant.
        """
        from unittest.mock import MagicMock

        mock = MagicMock(spec=MemoryService)
        mock.enabled = True
        self._default_mock_memory = mock
        monkeypatch.setattr(
            "autopack.memory.context_injector.MemoryService",
            lambda: mock,
        )

    def test_context_injector_initialization_with_service(self, mock_memory_service):
        """Test ContextInjector initialization with provided service."""
        injector = ContextInjector(memory_service=mock_memory_service)
        assert injector._memory == mock_memory_service

    def test_context_injector_initialization_without_service(self):
        """Test ContextInjector initialization creates default service.

        Note: The autouse fixture mocks MemoryService to prevent Qdrant timeouts.
        This test verifies that the default factory is called when no service is provided.
        """
        injector = ContextInjector()
        # Verify the mocked default service was used
        assert injector._memory == self._default_mock_memory

    def test_get_context_for_phase_returns_injection(self, mock_memory_service):
        """Test get_context_for_phase returns ContextInjection with retrieved data."""
        injector = ContextInjector(memory_service=mock_memory_service)

        injection = injector.get_context_for_phase(
            phase_type="build",
            current_goal="implement user authentication",
            project_id="test-project",
            max_tokens=500,
        )

        # Verify returned type
        assert isinstance(injection, ContextInjection)

        # Verify content was retrieved
        assert len(injection.past_errors) == 2
        assert "Timeout error" in injection.past_errors[0]
        assert "Connection refused" in injection.past_errors[1]

        assert len(injection.successful_strategies) == 2
        assert "async" in injection.successful_strategies[0].lower()
        assert "circuit breaker" in injection.successful_strategies[1].lower()

        assert len(injection.doctor_hints) == 1
        assert "rate limit" in injection.doctor_hints[0].lower()

        assert len(injection.relevant_insights) == 2
        assert injection.total_token_estimate >= 0

    def test_get_context_for_phase_with_disabled_memory(self):
        """Test get_context_for_phase returns empty injection when memory disabled."""
        service = Mock(spec=MemoryService)
        service.enabled = False

        injector = ContextInjector(memory_service=service)
        injection = injector.get_context_for_phase(
            phase_type="build",
            current_goal="implement feature",
            project_id="test-project",
        )

        assert injection.past_errors == []
        assert injection.successful_strategies == []
        assert injection.doctor_hints == []
        assert injection.relevant_insights == []
        assert injection.discovery_insights == []  # IMP-DISC-001
        assert injection.total_token_estimate == 0

    def test_get_context_for_phase_handles_exception(self, mock_memory_service):
        """Test get_context_for_phase gracefully handles exceptions."""
        mock_memory_service.search_errors.side_effect = Exception("Search failed")

        injector = ContextInjector(memory_service=mock_memory_service)
        injection = injector.get_context_for_phase(
            phase_type="build",
            current_goal="implement feature",
            project_id="test-project",
        )

        # Should return empty injection on error
        assert injection.past_errors == []
        assert injection.total_token_estimate == 0

    def test_format_for_prompt_creates_valid_output(self):
        """Test format_for_prompt creates formatted markdown output."""
        injection = ContextInjection(
            past_errors=["Error: timeout in API call", "Error: connection refused"],
            successful_strategies=["Use async for I/O", "Implement caching"],
            doctor_hints=["Check rate limits", "Monitor memory usage"],
            relevant_insights=["Auth uses OAuth 2.0", "DB pool max 20"],
            discovery_insights=[],  # IMP-DISC-001
            total_token_estimate=150,
        )

        injector = ContextInjector()
        formatted = injector.format_for_prompt(injection)

        # Verify formatting
        assert "Past Errors to Avoid" in formatted
        assert "timeout in API call" in formatted
        assert "connection refused" in formatted

        assert "Successful Strategies" in formatted
        assert "Use async for I/O" in formatted
        assert "Implement caching" in formatted

        assert "Doctor Recommendations" in formatted
        assert "Check rate limits" in formatted
        assert "Monitor memory usage" in formatted

        assert "Relevant Historical Insights" in formatted
        assert "Auth uses OAuth 2.0" in formatted
        assert "DB pool max 20" in formatted

    def test_format_for_prompt_empty_injection(self):
        """Test format_for_prompt returns empty string for empty injection."""
        injection = ContextInjection(
            past_errors=[],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],  # IMP-DISC-001
            total_token_estimate=0,
        )

        injector = ContextInjector()
        formatted = injector.format_for_prompt(injection)

        assert formatted == ""

    def test_format_for_prompt_partial_injection(self):
        """Test format_for_prompt with only some fields populated."""
        injection = ContextInjection(
            past_errors=["Error: timeout"],
            successful_strategies=[],
            doctor_hints=["Check limits"],
            relevant_insights=[],
            discovery_insights=[],  # IMP-DISC-001
            total_token_estimate=50,
        )

        injector = ContextInjector()
        formatted = injector.format_for_prompt(injection)

        assert "Past Errors to Avoid" in formatted
        assert "Doctor Recommendations" in formatted
        assert "Successful Strategies" not in formatted
        assert "Relevant Historical Insights" not in formatted

    def test_estimate_tokens(self):
        """Test token estimation."""
        injector = ContextInjector()

        # Test with various content
        tokens = injector._estimate_tokens(["This is a test", "Another test", "More content here"])

        # Each char ≈ 0.25 tokens, so rough estimate
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_estimate_tokens_empty_list(self):
        """Test token estimation with empty list."""
        injector = ContextInjector()
        tokens = injector._estimate_tokens([])

        assert tokens == 0

    def test_injection_dataclass(self):
        """Test ContextInjection dataclass."""
        injection = ContextInjection(
            past_errors=["error1"],
            successful_strategies=["strategy1"],
            doctor_hints=["hint1"],
            relevant_insights=["insight1"],
            discovery_insights=["discovery1"],  # IMP-DISC-001
            total_token_estimate=100,
        )

        assert injection.past_errors == ["error1"]
        assert injection.successful_strategies == ["strategy1"]
        assert injection.doctor_hints == ["hint1"]
        assert injection.relevant_insights == ["insight1"]
        assert injection.discovery_insights == ["discovery1"]  # IMP-DISC-001
        assert injection.total_token_estimate == 100

    def test_format_for_prompt_truncates_long_content(self):
        """Test format_for_prompt truncates long content items."""
        long_text = "x" * 300  # Create very long text

        injection = ContextInjection(
            past_errors=[long_text],
            successful_strategies=[],
            doctor_hints=[],
            relevant_insights=[],
            discovery_insights=[],  # IMP-DISC-001
            total_token_estimate=300,
        )

        injector = ContextInjector()
        formatted = injector.format_for_prompt(injection)

        # Should truncate to 150 chars per item
        assert len(formatted) < len(long_text)
        assert "Past Errors to Avoid" in formatted
