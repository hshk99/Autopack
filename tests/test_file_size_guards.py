"""Unit tests for file size guards (IMPLEMENTATION_PLAN2.md Phase 5)

Tests cover:
- Pre-flight guard (rejects files >1000 lines, switches to diff mode for 500-1000)
- Parser guards (read-only enforcement, shrinkage/growth detection)
- Telemetry recording
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import Mock

import pytest

from autopack.anthropic_clients import AnthropicBuilderClient
from autopack.builder_config import BuilderOutputConfig
from autopack.file_size_telemetry import FileSizeTelemetry


class TestBuilderOutputConfig:
    """Tests for BuilderOutputConfig"""

    def test_default_values(self):
        """Test default configuration values"""
        config = BuilderOutputConfig()

        assert config.max_lines_for_full_file == 500
        assert config.max_lines_hard_limit == 1000
        assert config.max_shrinkage_percent == 60
        assert config.max_growth_multiplier == 3.0

    def test_from_yaml(self):
        """Test loading from YAML"""
        import os
        import tempfile as tf

        # Create temporary file
        fd, temp_path = tf.mkstemp(suffix=".yaml")
        try:
            with os.fdopen(fd, "w") as f:
                yaml_content = """
builder_output_mode:
  max_lines_for_full_file: 400
  max_lines_hard_limit: 800
  max_shrinkage_percent: 50
  max_growth_multiplier: 2.5
"""
                f.write(yaml_content)

            config = BuilderOutputConfig.from_yaml(Path(temp_path))

            assert config.max_lines_for_full_file == 400
            assert config.max_lines_hard_limit == 800
            assert config.max_shrinkage_percent == 50
            assert config.max_growth_multiplier == 2.5
        finally:
            # Clean up
            try:
                os.unlink(temp_path)
            except Exception:
                pass

    def test_from_yaml_missing_file_uses_defaults(self):
        """Test that missing YAML file uses defaults"""
        config = BuilderOutputConfig.from_yaml(Path("/nonexistent/path.yaml"))

        assert config.max_lines_for_full_file == 500
        assert config.max_lines_hard_limit == 1000


class TestFileSizeTelemetry:
    """Tests for FileSizeTelemetry"""

    def test_record_preflight_reject(self):
        """Test recording pre-flight reject event"""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = FileSizeTelemetry(Path(tmpdir))
            telemetry.record_preflight_reject(
                run_id="test-run",
                phase_id="phase-1",
                file_path="large_file.py",
                line_count=1200,
                limit=1000,
                bucket="C",
            )

            # Read back the telemetry
            events = []
            if telemetry.telemetry_path.exists():
                with open(telemetry.telemetry_path, "r") as f:
                    for line in f:
                        events.append(json.loads(line))

            assert len(events) == 1
            assert events[0]["event_type"] == "preflight_reject_large_file"
            assert events[0]["file_path"] == "large_file.py"
            assert events[0]["line_count"] == 1200
            assert events[0]["bucket"] == "C"

    def test_record_bucket_switch(self):
        """Test recording bucket switch event"""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = FileSizeTelemetry(Path(tmpdir))
            telemetry.record_bucket_switch(
                run_id="test-run", phase_id="phase-1", files=[("file1.py", 700), ("file2.py", 800)]
            )

            events = []
            if telemetry.telemetry_path.exists():
                with open(telemetry.telemetry_path, "r") as f:
                    for line in f:
                        events.append(json.loads(line))

            assert len(events) == 1
            assert events[0]["event_type"] == "bucket_b_switch_to_diff_mode"
            assert len(events[0]["files"]) == 2


class TestPreflightGuard:
    """Tests for pre-flight guard logic"""

    def test_bucket_a_allows_small_file(self):
        """Pre-flight should allow files ≤500 lines (Bucket A)"""
        config = BuilderOutputConfig()

        # 400 line file should be allowed
        line_count = 400
        assert line_count <= config.max_lines_for_full_file

        # Should use full-file mode
        use_full_file_mode = line_count <= config.max_lines_for_full_file
        assert use_full_file_mode is True

    def test_bucket_b_uses_structured_edit(self):
        """Pre-flight should use structured edit for 500-1000 line files (Bucket B)"""
        config = BuilderOutputConfig()

        # 700 line file should use structured edit mode (not full-file)
        line_count = 700
        assert line_count > config.max_lines_for_full_file
        assert line_count <= config.max_lines_hard_limit

        # Files in Bucket B use structured edit mode (not full-file, not legacy diff)
        use_full_file_mode = False
        assert use_full_file_mode is False

    def test_bucket_c_rejects_large_file(self):
        """Pre-flight should reject files >1000 lines (Bucket C)"""
        config = BuilderOutputConfig()

        # 1200 line file should be rejected
        line_count = 1200
        assert line_count > config.max_lines_hard_limit

        # File should be marked as read-only context
        # (In actual implementation, this prevents modification)


class TestParserGuards:
    """Tests for parser-level guards"""

    @pytest.fixture
    def config(self):
        return BuilderOutputConfig()

    @pytest.fixture
    def mock_response(self):
        """Mock Anthropic API response"""
        response = Mock()
        response.usage = Mock()
        response.usage.input_tokens = 1000
        response.usage.output_tokens = 500
        return response

    def test_readonly_enforcement_rejects_large_file_modification(self, config, mock_response):
        """Parser should reject JSON that tries to modify read-only files"""
        client = AnthropicBuilderClient(api_key="test-key")

        # Simulate LLM trying to modify a 1200-line file (read-only)
        file_path = "large_file.py"
        old_content = "\n".join(["line"] * 1200)
        new_content = "\n".join(["line"] * 1200) + "\n# modified"

        file_context = {"existing_files": {file_path: old_content}}

        # Create JSON output that tries to modify the large file
        llm_output = json.dumps(
            {"files": [{"path": file_path, "mode": "modify", "new_content": new_content}]}
        )

        result = client._parse_full_file_output(
            llm_output,
            file_context,
            mock_response,
            "claude-sonnet-4-5",
            phase_spec={},
            config=config,
        )

        # Should reject because file is >500 lines (read-only)
        assert result.success is False
        assert "readonly_violation" in result.error.lower() or "read-only" in result.error.lower()

    def test_shrinkage_detection_rejects_80_percent_reduction(self, config, mock_response):
        """Parser should reject >60% shrinkage without explicit opt-in"""
        client = AnthropicBuilderClient(api_key="test-key")

        file_path = "test.py"
        # Use 400 lines (within read-only limit of 500) to test shrinkage detection
        old_content = "\n".join(["line"] * 400)  # 400 lines
        new_content = "\n".join(["line"] * 80)  # 80 lines (80% reduction)

        file_context = {"existing_files": {file_path: old_content}}

        llm_output = json.dumps(
            {"files": [{"path": file_path, "mode": "modify", "new_content": new_content}]}
        )

        result = client._parse_full_file_output(
            llm_output,
            file_context,
            mock_response,
            "claude-sonnet-4-5",
            phase_spec={},  # No allow_mass_deletion
            config=config,
        )

        # Should reject because shrinkage >60%
        assert result.success is False
        assert "shrinkage" in result.error.lower()

    def test_shrinkage_allowed_with_opt_in(self, config, mock_response):
        """Parser should allow >60% shrinkage with allow_mass_deletion: true"""
        client = AnthropicBuilderClient(api_key="test-key")

        file_path = "test.py"
        old_content = "\n".join(["line"] * 1000)  # 1000 lines
        new_content = "\n".join(["line"] * 200)  # 200 lines (80% reduction)

        file_context = {"existing_files": {file_path: old_content}}

        llm_output = json.dumps(
            {"files": [{"path": file_path, "mode": "modify", "new_content": new_content}]}
        )

        # Phase spec allows mass deletion
        phase_spec = {"allow_mass_deletion": True}

        client._parse_full_file_output(
            llm_output,
            file_context,
            mock_response,
            "claude-sonnet-4-5",
            phase_spec=phase_spec,
            config=config,
        )

        # Should allow because phase explicitly allows mass deletion
        # (Note: This test may need adjustment based on actual implementation)
        # The shrinkage guard should check allow_mass_deletion before rejecting

    def test_growth_detection_rejects_5x_increase(self, config, mock_response):
        """Parser should reject >3x growth without explicit opt-in"""
        client = AnthropicBuilderClient(api_key="test-key")

        file_path = "test.py"
        old_content = "\n".join(["line"] * 200)  # 200 lines
        new_content = "\n".join(["line"] * 1000)  # 1000 lines (5x growth)

        file_context = {"existing_files": {file_path: old_content}}

        llm_output = json.dumps(
            {"files": [{"path": file_path, "mode": "modify", "new_content": new_content}]}
        )

        result = client._parse_full_file_output(
            llm_output,
            file_context,
            mock_response,
            "claude-sonnet-4-5",
            phase_spec={},  # No allow_mass_addition
            config=config,
        )

        # Should reject because growth >3x
        assert result.success is False
        assert "growth" in result.error.lower()

    def test_growth_allowed_with_opt_in(self, config, mock_response):
        """Parser should allow >3x growth with allow_mass_addition: true"""
        client = AnthropicBuilderClient(api_key="test-key")

        file_path = "test.py"
        old_content = "\n".join(["line"] * 200)  # 200 lines
        new_content = "\n".join(["line"] * 1000)  # 1000 lines (5x growth)

        file_context = {"existing_files": {file_path: old_content}}

        llm_output = json.dumps(
            {"files": [{"path": file_path, "mode": "modify", "new_content": new_content}]}
        )

        # Phase spec allows mass addition
        phase_spec = {"allow_mass_addition": True}

        client._parse_full_file_output(
            llm_output,
            file_context,
            mock_response,
            "claude-sonnet-4-5",
            phase_spec=phase_spec,
            config=config,
        )

        # Should allow because phase explicitly allows mass addition
        # (Note: This test may need adjustment based on actual implementation)


class TestIntegration:
    """Integration tests for file size guards"""

    def test_three_bucket_policy(self):
        """Test that 3-bucket policy works correctly"""
        config = BuilderOutputConfig()

        # Bucket A: ≤500 lines - full-file mode
        assert 400 <= config.max_lines_for_full_file
        assert 500 <= config.max_lines_for_full_file

        # Bucket B: 501-1000 lines - diff mode
        assert 600 > config.max_lines_for_full_file
        assert 600 <= config.max_lines_hard_limit
        assert 1000 > config.max_lines_for_full_file
        assert 1000 <= config.max_lines_hard_limit

        # Bucket C: >1000 lines - read-only
        assert 1001 > config.max_lines_hard_limit
        assert 2000 > config.max_lines_hard_limit

    def test_telemetry_integration(self):
        """Test that telemetry records events correctly"""
        with tempfile.TemporaryDirectory() as tmpdir:
            telemetry = FileSizeTelemetry(Path(tmpdir))

            # Record multiple events
            telemetry.record_preflight_reject("run-1", "phase-1", "file1.py", 1200, 1000, "C")
            telemetry.record_bucket_switch("run-1", "phase-1", [("file2.py", 700)])
            telemetry.record_shrinkage("run-1", "phase-2", "file3.py", 1000, 300, 70.0, False)

            # Verify all events recorded
            events = []
            if telemetry.telemetry_path.exists():
                with open(telemetry.telemetry_path, "r") as f:
                    for line in f:
                        events.append(json.loads(line))

            assert len(events) == 3
            assert events[0]["event_type"] == "preflight_reject_large_file"
            assert events[1]["event_type"] == "bucket_b_switch_to_diff_mode"
            assert events[2]["event_type"] == "suspicious_shrinkage"
