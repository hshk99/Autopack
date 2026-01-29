"""
Tests for sub-agent guardrails.

BUILD-197: Claude Code sub-agent guardrails
"""

import pytest

from autopack.subagent.guardrails import (GuardrailResult, GuardrailType,
                                          GuardrailViolation,
                                          SubagentGuardrails,
                                          ViolationSeverity)
from autopack.subagent.output_contract import OutputType, SubagentOutput


class TestGuardrailViolation:
    """Tests for GuardrailViolation dataclass."""

    def test_basic_violation(self):
        """Test creating a basic violation."""
        violation = GuardrailViolation(
            guardrail=GuardrailType.NO_SECRETS,
            severity=ViolationSeverity.CRITICAL,
            message="API key detected",
            location="content",
            snippet="api_key=[REDACTED]",
            remediation="Remove the API key",
        )

        assert violation.guardrail == GuardrailType.NO_SECRETS
        assert violation.severity == ViolationSeverity.CRITICAL


class TestGuardrailResult:
    """Tests for GuardrailResult dataclass."""

    def test_critical_violations_filter(self):
        """Test filtering critical violations."""
        result = GuardrailResult(
            passed=False,
            violations=[
                GuardrailViolation(
                    guardrail=GuardrailType.NO_SECRETS,
                    severity=ViolationSeverity.CRITICAL,
                    message="Secret found",
                ),
                GuardrailViolation(
                    guardrail=GuardrailType.BOUNDED_SCOPE,
                    severity=ViolationSeverity.WARNING,
                    message="Outside scope",
                ),
            ],
        )

        critical = result.critical_violations
        assert len(critical) == 1
        assert critical[0].guardrail == GuardrailType.NO_SECRETS

    def test_to_markdown_passed(self):
        """Test markdown output for passed result."""
        result = GuardrailResult(
            passed=True,
            checked_guardrails=[GuardrailType.NO_SECRETS, GuardrailType.NO_SIDE_EFFECTS],
        )
        md = result.to_markdown()

        assert "**Status**: PASSED" in md
        assert "## Checked Guardrails" in md
        assert "no_secrets" in md

    def test_to_markdown_failed(self):
        """Test markdown output for failed result."""
        result = GuardrailResult(
            passed=False,
            violations=[
                GuardrailViolation(
                    guardrail=GuardrailType.NO_SECRETS,
                    severity=ViolationSeverity.CRITICAL,
                    message="API key found",
                    location="line 42",
                    snippet="sk-[REDACTED]",
                    remediation="Remove the key",
                )
            ],
            warnings=[
                GuardrailViolation(
                    guardrail=GuardrailType.DETERMINISTIC_PATHS,
                    severity=ViolationSeverity.WARNING,
                    message="Timestamp in path",
                )
            ],
        )
        md = result.to_markdown()

        assert "**Status**: FAILED" in md
        assert "## Critical Violations" in md
        assert "API key found" in md
        assert "## Warnings" in md
        assert "Timestamp in path" in md


class TestSubagentGuardrails:
    """Tests for SubagentGuardrails class."""

    @pytest.fixture
    def guardrails(self):
        """Create a guardrails instance."""
        return SubagentGuardrails()

    # ===== No Secrets Tests =====

    def test_detects_openai_api_key(self, guardrails):
        """Test detection of OpenAI API keys."""
        content = 'api_key = "sk-1234567890abcdefghijklmnop"'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1
        assert any(v.guardrail == GuardrailType.NO_SECRETS for v in violations)

    def test_detects_anthropic_api_key(self, guardrails):
        """Test detection of Anthropic API keys."""
        content = 'ANTHROPIC_API_KEY="sk-ant-api03-abcdefghijklmnopqrstuvwxyz"'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_detects_bearer_token(self, guardrails):
        """Test detection of bearer tokens."""
        content = 'headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."}'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_detects_aws_access_key(self, guardrails):
        """Test detection of AWS access keys."""
        content = 'aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_detects_database_connection_string(self, guardrails):
        """Test detection of database connection strings with passwords."""
        content = 'DATABASE_URL = "postgres://user:secretpassword123@localhost:5432/db"'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_detects_private_key_header(self, guardrails):
        """Test detection of private key headers."""
        content = "-----BEGIN RSA PRIVATE KEY-----\nMIIE..."
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_detects_generic_password(self, guardrails):
        """Test detection of generic password fields."""
        content = 'password = "supersecretpassword123"'
        violations = guardrails.check_no_secrets(content)

        assert len(violations) >= 1

    def test_no_false_positive_for_safe_content(self, guardrails):
        """Test that safe content doesn't trigger false positives."""
        content = """
        # This is documentation about API authentication

        Users should set their API key in environment variables.
        The key format is: MYAPP_API_KEY=your-key-here

        Example configuration (with placeholder):
        api_key = "YOUR_API_KEY_HERE"
        """
        violations = guardrails.check_no_secrets(content)

        # Should not detect placeholder values as secrets
        # (may have some matches for patterns but not critical ones)
        critical = [v for v in violations if "YOUR_API_KEY" not in str(v.snippet)]
        assert len(critical) == 0

    def test_snippet_is_redacted(self, guardrails):
        """Test that detected secrets are redacted in snippets."""
        content = 'api_key = "sk-realkey1234567890abcdefgh"'
        violations = guardrails.check_no_secrets(content)

        for v in violations:
            if v.snippet:
                assert "[REDACTED]" in v.snippet or len(v.snippet) < 30

    # ===== No Side Effects Tests =====

    def test_detects_http_post(self, guardrails):
        """Test detection of HTTP POST requests."""
        content = 'response = requests.post("https://api.example.com/data", json=payload)'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) >= 1
        assert any("HTTP" in v.message for v in violations)

    def test_detects_subprocess(self, guardrails):
        """Test detection of subprocess calls."""
        content = 'subprocess.run(["rm", "-rf", "/"])'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) >= 1
        assert any("Subprocess" in v.message for v in violations)

    def test_detects_database_insert(self, guardrails):
        """Test detection of database write operations."""
        content = 'cursor.execute("INSERT INTO users VALUES (?)", (name,))'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) >= 1

    def test_detects_marketplace_operations(self, guardrails):
        """Test detection of marketplace operations."""
        content = 'etsy_client.create_listing(title="My Product", price=19.99)'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) >= 1

    def test_detects_trading_operations(self, guardrails):
        """Test detection of trading operations."""
        content = 'alpaca.place_order(symbol="AAPL", qty=100, side="buy")'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) >= 1

    def test_http_get_not_flagged(self, guardrails):
        """Test that HTTP GET is not flagged as side effect."""
        content = 'response = requests.get("https://api.example.com/data")'
        violations = guardrails.check_no_side_effects(content)

        assert len(violations) == 0

    # ===== Deterministic Paths Tests =====

    def test_detects_timestamp_in_path(self, guardrails):
        """Test detection of timestamps in file paths."""
        violations = guardrails.check_deterministic_paths(["handoff/output_1704067200123.md"])

        assert len(violations) >= 1
        assert any("timestamp" in v.message.lower() for v in violations)

    def test_detects_absolute_path_unix(self, guardrails):
        """Test detection of Unix absolute paths."""
        violations = guardrails.check_deterministic_paths(["/home/user/project/file.md"])

        assert len(violations) >= 1
        assert any("absolute" in v.message.lower() for v in violations)

    def test_detects_absolute_path_windows(self, guardrails):
        """Test detection of Windows absolute paths."""
        violations = guardrails.check_deterministic_paths(["C:\\Users\\user\\project\\file.md"])

        assert len(violations) >= 1
        assert any("absolute" in v.message.lower() for v in violations)

    def test_relative_path_accepted(self, guardrails):
        """Test that relative paths are accepted."""
        violations = guardrails.check_deterministic_paths(
            ["handoff/research_codebase.md", "phases/phase_01.md"]
        )

        # Only checking for deterministic path violations, not file existence
        deterministic_violations = [
            v for v in violations if v.guardrail == GuardrailType.DETERMINISTIC_PATHS
        ]
        assert len(deterministic_violations) == 0

    def test_validates_file_existence(self, guardrails, tmp_path):
        """Test validation of file existence when run_dir is set."""
        guardrails_with_dir = SubagentGuardrails(run_dir=tmp_path)

        # Create one file
        (tmp_path / "existing.md").write_text("content")

        violations = guardrails_with_dir.check_deterministic_paths(
            ["existing.md", "nonexistent.md"]
        )

        existence_violations = [
            v for v in violations if v.guardrail == GuardrailType.FILE_REFERENCE_VALIDITY
        ]
        assert len(existence_violations) == 1
        assert "nonexistent.md" in str(existence_violations[0])

    # ===== Output Path Tests =====

    def test_allowed_output_path(self, guardrails):
        """Test that handoff paths are allowed."""
        violations = guardrails.check_output_path("handoff/research_test.md")
        assert len(violations) == 0

    def test_blocked_output_path_outside_handoff(self, guardrails):
        """Test that paths outside handoff are blocked."""
        violations = guardrails.check_output_path("src/main.py")

        assert len(violations) >= 1
        assert any(v.severity == ViolationSeverity.CRITICAL for v in violations)

    def test_blocked_path_traversal(self, guardrails):
        """Test that path traversal is blocked."""
        violations = guardrails.check_output_path("handoff/../src/main.py")

        assert len(violations) >= 1
        assert any("traversal" in v.message.lower() for v in violations)

    # ===== Full Validation Tests =====

    def test_validate_output_passes_for_clean_content(self, guardrails):
        """Test that clean content passes validation."""
        result = guardrails.validate_output(
            content="## Findings\n\nThe codebase is well-structured.",
            output_path="handoff/research_codebase.md",
            file_references=["src/main.py"],
        )

        assert result.passed
        assert len(result.violations) == 0

    def test_validate_output_fails_for_secret(self, guardrails):
        """Test that content with secrets fails validation."""
        result = guardrails.validate_output(
            content='Found API key: "sk-secret123456789012345678"',
            output_path="handoff/research.md",
        )

        assert not result.passed
        assert len(result.critical_violations) >= 1

    def test_validate_output_fails_for_bad_path(self, guardrails):
        """Test that bad output path fails validation."""
        result = guardrails.validate_output(
            content="Clean content",
            output_path="src/malicious.py",
        )

        assert not result.passed
        assert any(v.guardrail == GuardrailType.BOUNDED_SCOPE for v in result.violations)

    def test_side_effects_are_warnings(self, guardrails):
        """Test that side effects are warnings, not blocking violations."""
        result = guardrails.validate_output(
            content="# Research\n\nWe could use requests.post() to send data.",
            output_path="handoff/research.md",
        )

        # Should pass because side effects are warnings
        assert result.passed
        assert len(result.warnings) >= 1

    # ===== Redaction Tests =====

    def test_redact_secrets_api_key(self, guardrails):
        """Test redacting API keys."""
        content = 'api_key = "sk-reallylongsecretkey1234567890"'
        redacted = guardrails.redact_secrets(content)

        assert "sk-reallylongsecretkey1234567890" not in redacted
        assert "[REDACTED]" in redacted

    def test_redact_secrets_preserves_safe_content(self, guardrails):
        """Test that safe content is preserved."""
        content = "This is documentation about API usage."
        redacted = guardrails.redact_secrets(content)

        assert redacted == content

    # ===== SubagentOutput Validation Tests =====

    def test_validate_subagent_output(self, guardrails):
        """Test validating a SubagentOutput object."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test Research",
            content="## Findings\n\nClean content without secrets.",
            file_references=["src/main.py"],
        )

        result = guardrails.validate_subagent_output(output, strict=False)

        assert result.passed

    def test_validate_subagent_output_strict_mode(self, guardrails):
        """Test strict mode elevates warnings to violations."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content='We should use requests.post("url") to send data.',
            file_references=["src/main.py"],
        )

        # Non-strict should pass (side effects are warnings)
        result_normal = guardrails.validate_subagent_output(output, strict=False)
        assert result_normal.passed

        # Strict should fail
        result_strict = guardrails.validate_subagent_output(output, strict=True)
        assert not result_strict.passed

    def test_validate_subagent_output_with_secret(self, guardrails):
        """Test that output with secrets fails validation."""
        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="test",
            agent_type="researcher",
            run_id="run-001",
            title="Test",
            content='Found key: api_key = "sk-secret12345678901234567890"',
            file_references=[],
        )

        result = guardrails.validate_subagent_output(output, strict=False)

        assert not result.passed
        assert len(result.critical_violations) >= 1


class TestGuardrailsIntegration:
    """Integration tests for guardrails with real-world scenarios."""

    @pytest.fixture
    def guardrails(self, tmp_path):
        """Create guardrails with a run directory."""
        return SubagentGuardrails(run_dir=tmp_path)

    def test_full_research_output_validation(self, guardrails, tmp_path):
        """Test validating a complete research output."""
        # Create some reference files
        (tmp_path / "src").mkdir()
        (tmp_path / "src/main.py").write_text("# Main module")
        (tmp_path / "src/utils.py").write_text("# Utilities")

        output = SubagentOutput(
            output_type=OutputType.RESEARCH,
            topic="codebase_analysis",
            agent_type="researcher",
            run_id="run-001",
            title="Codebase Analysis",
            content="""
## Objective

Analyze the codebase structure and patterns.

## Methodology

1. Scanned all Python files
2. Analyzed import patterns
3. Documented module dependencies

## Findings

The codebase follows a clean architecture pattern with:
- Clear separation of concerns
- Well-defined module boundaries
- Consistent naming conventions

## Recommendations

1. Consider adding type hints to improve maintainability
2. Add docstrings to public functions
            """,
            file_references=["src/main.py", "src/utils.py"],
            findings_summary=["Clean architecture", "Good separation"],
            proposed_actions=["Add type hints", "Add docstrings"],
        )

        result = guardrails.validate_subagent_output(output, strict=False)

        assert result.passed
        assert len(result.critical_violations) == 0
