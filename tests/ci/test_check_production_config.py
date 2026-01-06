"""Tests for production config CI guard (BUILD-180 Phase 4).

Validates that scripts/ci/check_production_config.py blocks DEBUG
enablement in production configs.
"""

from pathlib import Path
import tempfile

# Import will be available after implementation
# from scripts.ci.check_production_config import (
#     check_file_for_debug,
#     check_production_configs,
#     DebugViolation,
# )


class TestDebugPatternDetection:
    """Test DEBUG pattern detection."""

    def test_detects_debug_equals_1(self):
        """Should detect DEBUG=1."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations = check_content_for_debug("DEBUG=1", "test.env")
        assert len(violations) >= 1
        assert any("DEBUG" in v.pattern for v in violations)

    def test_detects_debug_equals_true(self):
        """Should detect DEBUG=true."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations = check_content_for_debug("DEBUG=true", "test.env")
        assert len(violations) >= 1

    def test_detects_debug_quoted(self):
        """Should detect DEBUG='1' and DEBUG=\"1\"."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations1 = check_content_for_debug("DEBUG='1'", "test.env")
        violations2 = check_content_for_debug('DEBUG="1"', "test.env")

        assert len(violations1) >= 1
        assert len(violations2) >= 1

    def test_ignores_debug_equals_0(self):
        """Should ignore DEBUG=0 (disabled)."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations = check_content_for_debug("DEBUG=0", "test.env")
        assert len(violations) == 0

    def test_ignores_debug_equals_false(self):
        """Should ignore DEBUG=false (disabled)."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations = check_content_for_debug("DEBUG=false", "test.env")
        assert len(violations) == 0

    def test_ignores_commented_debug(self):
        """Should ignore commented out DEBUG lines."""
        from scripts.ci.check_production_config import check_content_for_debug

        violations = check_content_for_debug("# DEBUG=1", "test.env")
        assert len(violations) == 0

    def test_detects_yaml_debug_true(self):
        """Should detect debug: true in YAML."""
        from scripts.ci.check_production_config import check_content_for_debug

        content = """
settings:
  debug: true
  log_level: INFO
"""
        violations = check_content_for_debug(content, "config.yaml")
        assert len(violations) >= 1


class TestProductionConfigFiles:
    """Test production config file detection."""

    def test_checks_env_production(self):
        """Should check .env.production files."""
        from scripts.ci.check_production_config import is_production_config

        assert is_production_config(Path(".env.production"))
        assert is_production_config(Path("config/.env.production"))

    def test_checks_production_yaml(self):
        """Should check production.yaml files."""
        from scripts.ci.check_production_config import is_production_config

        assert is_production_config(Path("config/production.yaml"))
        assert is_production_config(Path("deploy/production.yml"))

    def test_ignores_development_configs(self):
        """Should ignore development config files."""
        from scripts.ci.check_production_config import is_production_config

        assert not is_production_config(Path(".env.development"))
        assert not is_production_config(Path("config/development.yaml"))
        assert not is_production_config(Path(".env.local"))


class TestCIGuardIntegration:
    """Integration tests for CI guard."""

    def test_returns_zero_on_clean_config(self):
        """Should return 0 when no DEBUG in production."""
        from scripts.ci.check_production_config import check_production_configs

        with tempfile.TemporaryDirectory() as tmpdir:
            prod_env = Path(tmpdir) / ".env.production"
            prod_env.write_text("LOG_LEVEL=INFO\nAPI_KEY=secret\n")

            result = check_production_configs(Path(tmpdir))

            assert result.exit_code == 0
            assert len(result.violations) == 0

    def test_returns_nonzero_on_debug_found(self):
        """Should return non-zero when DEBUG found in production."""
        from scripts.ci.check_production_config import check_production_configs

        with tempfile.TemporaryDirectory() as tmpdir:
            prod_env = Path(tmpdir) / ".env.production"
            prod_env.write_text("DEBUG=1\nLOG_LEVEL=INFO\n")

            result = check_production_configs(Path(tmpdir))

            assert result.exit_code != 0
            assert len(result.violations) >= 1

    def test_provides_remediation_message(self):
        """Should provide clear remediation message."""
        from scripts.ci.check_production_config import check_production_configs

        with tempfile.TemporaryDirectory() as tmpdir:
            prod_env = Path(tmpdir) / ".env.production"
            prod_env.write_text("DEBUG=1\n")

            result = check_production_configs(Path(tmpdir))

            assert result.remediation_message is not None
            assert "DEBUG" in result.remediation_message


class TestDebugViolationDataclass:
    """Test DebugViolation dataclass."""

    def test_violation_has_required_fields(self):
        """DebugViolation should have file, line, pattern fields."""
        from scripts.ci.check_production_config import DebugViolation

        violation = DebugViolation(
            file_path="config/production.yaml",
            line_number=5,
            pattern="DEBUG=1",
            line_content="DEBUG=1",
        )

        assert violation.file_path == "config/production.yaml"
        assert violation.line_number == 5
        assert violation.pattern == "DEBUG=1"
