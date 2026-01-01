"""Test that StubClaudeAuditor emits proper deprecation warnings."""

import warnings
import pytest


def test_stub_claude_auditor_emits_deprecation_warning():
    """Test that StubClaudeAuditor emits DeprecationWarning when called."""
    from autopack.dual_auditor import StubClaudeAuditor

    stub = StubClaudeAuditor()

    # Verify deprecation warning is raised
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")

        result = stub.review_patch(
            patch_content="diff --git a/foo.py b/foo.py",
            phase_spec={"goal": "test"},
            max_tokens=1000,
            model="claude-sonnet-3-5"
        )

        # Check warning was raised
        assert len(w) == 1
        assert issubclass(w[0].category, DeprecationWarning)
        assert "StubClaudeAuditor is deprecated" in str(w[0].message)
        assert "AnthropicAuditorClient" in str(w[0].message)

    # Verify result contains deprecation messages
    assert result.approved is True
    assert result.tokens_used == 0  # Stub doesn't call API
    assert result.model_used == "claude-sonnet-3-5-stub"
    assert any("stub called" in msg.lower() for msg in result.auditor_messages)
    assert any("AnthropicAuditorClient" in msg for msg in result.auditor_messages)


def test_stub_returns_empty_issues():
    """Test that stub returns empty issues list (no real auditing)."""
    from autopack.dual_auditor import StubClaudeAuditor

    stub = StubClaudeAuditor()

    # Suppress deprecation warning for this test
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        result = stub.review_patch(
            patch_content="diff --git a/foo.py b/foo.py\n+bad code",
            phase_spec={"goal": "test"},
        )

    # Stub should always return empty issues (no real auditing)
    assert result.issues_found == []
    assert result.approved is True
