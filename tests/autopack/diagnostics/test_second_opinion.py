"""Tests for Second Opinion Triage System

Tests the optional bounded "second opinion" triage functionality
that provides diagnostic hypotheses, missing evidence identification,
next probes, and minimal patch strategies.
"""

import json

import pytest

from autopack.diagnostics.second_opinion import (
    SecondOpinionConfig,
    SecondOpinionTriageSystem,
    TriageReport,
)


class TestSecondOpinionConfig:
    """Tests for SecondOpinionConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = SecondOpinionConfig()

        assert config.enabled is False
        assert config.model == "claude-opus-4"
        assert config.max_tokens == 8192
        assert config.temperature == 0.3
        assert config.token_budget == 50000

    def test_custom_config(self):
        """Test custom configuration values."""
        config = SecondOpinionConfig(
            enabled=True,
            model="gpt-4",
            max_tokens=4096,
            temperature=0.5,
            token_budget=100000,
        )

        assert config.enabled is True
        assert config.model == "gpt-4"
        assert config.max_tokens == 4096
        assert config.temperature == 0.5
        assert config.token_budget == 100000


class TestTriageReport:
    """Tests for TriageReport."""

    def test_triage_report_creation(self):
        """Test creating a triage report."""
        report = TriageReport(
            hypotheses=[
                {
                    "description": "Token budget exceeded",
                    "likelihood": 0.9,
                    "evidence_for": ["Truncated output"],
                    "evidence_against": [],
                }
            ],
            missing_evidence=["Actual token counts"],
            next_probes=[
                {
                    "type": "check",
                    "description": "Check logs",
                    "command": "grep TOKEN logs.txt",
                }
            ],
            minimal_patch_strategy={
                "approach": "Increase token budget",
                "files_to_modify": ["config.py"],
                "key_changes": ["Increase max_tokens"],
                "risks": ["Higher costs"],
            },
            confidence=0.85,
            reasoning="Token truncation is most likely cause",
        )

        assert len(report.hypotheses) == 1
        assert report.hypotheses[0]["likelihood"] == 0.9
        assert len(report.missing_evidence) == 1
        assert len(report.next_probes) == 1
        assert report.confidence == 0.85
        assert "Token truncation" in report.reasoning
        assert report.timestamp is not None

    def test_triage_report_to_dict(self):
        """Test converting triage report to dictionary."""
        report = TriageReport(
            hypotheses=[{"description": "Test hypothesis", "likelihood": 0.8}],
            missing_evidence=["Evidence 1"],
            next_probes=[{"type": "check", "description": "Test probe"}],
            minimal_patch_strategy={"approach": "Test strategy"},
            confidence=0.75,
            reasoning="Test reasoning",
        )

        report_dict = report.to_dict()

        assert "hypotheses" in report_dict
        assert "missing_evidence" in report_dict
        assert "next_probes" in report_dict
        assert "minimal_patch_strategy" in report_dict
        assert "confidence" in report_dict
        assert "reasoning" in report_dict
        assert "timestamp" in report_dict
        assert report_dict["confidence"] == 0.75

    def test_triage_report_to_json(self):
        """Test converting triage report to JSON string."""
        report = TriageReport(
            hypotheses=[{"description": "Test", "likelihood": 0.9}],
            missing_evidence=["Evidence"],
            next_probes=[{"type": "check"}],
            minimal_patch_strategy={"approach": "Strategy"},
            confidence=0.8,
            reasoning="Reasoning",
        )

        json_str = report.to_json()

        # Verify it's valid JSON
        parsed = json.loads(json_str)
        assert parsed["confidence"] == 0.8
        assert len(parsed["hypotheses"]) == 1
        assert "timestamp" in parsed


class TestSecondOpinionTriageSystem:
    """Tests for SecondOpinionTriageSystem."""

    def test_system_initialization_default(self):
        """Test system initialization with default config."""
        system = SecondOpinionTriageSystem()

        assert system.config is not None
        assert system.config.enabled is False
        assert system.get_tokens_used() == 0

    def test_system_initialization_custom(self):
        """Test system initialization with custom config."""
        config = SecondOpinionConfig(enabled=True, token_budget=10000)
        system = SecondOpinionTriageSystem(config)

        assert system.config.enabled is True
        assert system.config.token_budget == 10000

    def test_is_enabled(self):
        """Test checking if system is enabled."""
        # Disabled system
        system_disabled = SecondOpinionTriageSystem(SecondOpinionConfig(enabled=False))
        assert system_disabled.is_enabled() is False

        # Enabled system
        system_enabled = SecondOpinionTriageSystem(SecondOpinionConfig(enabled=True))
        assert system_enabled.is_enabled() is True

    def test_within_budget(self):
        """Test token budget checking."""
        config = SecondOpinionConfig(enabled=True, token_budget=1000)
        system = SecondOpinionTriageSystem(config)

        # Initially within budget
        assert system.within_budget() is True

        # Simulate token usage
        system._tokens_used = 500
        assert system.within_budget() is True

        # Exceed budget
        system._tokens_used = 1001
        assert system.within_budget() is False

    def test_get_tokens_used(self):
        """Test getting tokens used."""
        system = SecondOpinionTriageSystem()

        assert system.get_tokens_used() == 0

        system._tokens_used = 1234
        assert system.get_tokens_used() == 1234

    def test_get_tokens_remaining(self):
        """Test getting remaining token budget."""
        config = SecondOpinionConfig(enabled=True, token_budget=5000)
        system = SecondOpinionTriageSystem(config)

        assert system.get_tokens_remaining() == 5000

        system._tokens_used = 2000
        assert system.get_tokens_remaining() == 3000

        system._tokens_used = 6000
        assert system.get_tokens_remaining() == 0

    def test_generate_triage_disabled(self):
        """Test triage generation when disabled."""
        system = SecondOpinionTriageSystem(SecondOpinionConfig(enabled=False))

        handoff_bundle = {"phase": {"name": "test-phase"}}
        report = system.generate_triage(handoff_bundle)

        assert report is None

    def test_generate_triage_budget_exceeded(self):
        """Test triage generation when budget is exceeded."""
        config = SecondOpinionConfig(enabled=True, token_budget=100)
        system = SecondOpinionTriageSystem(config)
        system._tokens_used = 101

        handoff_bundle = {"phase": {"name": "test-phase"}}
        report = system.generate_triage(handoff_bundle)

        assert report is None

    def test_generate_triage_success(self):
        """Test successful triage generation."""
        config = SecondOpinionConfig(enabled=True, token_budget=10000)
        system = SecondOpinionTriageSystem(config)

        handoff_bundle = {
            "phase": {
                "name": "test-phase",
                "description": "Test phase",
                "state": "FAILED",
                "builder_attempts": 2,
                "max_builder_attempts": 5,
            },
            "failure_reason": "Token budget exceeded",
            "diagnostics": {"error": "Truncated output"},
        }

        report = system.generate_triage(handoff_bundle)

        # Should get mock response
        assert report is not None
        assert isinstance(report, TriageReport)
        assert len(report.hypotheses) > 0
        assert report.confidence > 0
        assert system.get_tokens_used() > 0

    def test_generate_triage_with_phase_context(self):
        """Test triage generation with phase context."""
        config = SecondOpinionConfig(enabled=True, token_budget=10000)
        system = SecondOpinionTriageSystem(config)

        handoff_bundle = {
            "phase": {"name": "test-phase"},
            "failure_reason": "Test failure",
        }
        phase_context = {
            "complexity": "MEDIUM",
            "category": "IMPLEMENT_FEATURE",
        }

        report = system.generate_triage(handoff_bundle, phase_context)

        assert report is not None
        assert isinstance(report, TriageReport)

    def test_build_triage_prompt_basic(self):
        """Test building triage prompt with basic handoff bundle."""
        system = SecondOpinionTriageSystem()

        handoff_bundle = {
            "phase": {
                "name": "test-phase",
                "description": "Test description",
                "state": "FAILED",
            },
            "failure_reason": "Test failure",
        }

        prompt = system._build_triage_prompt(handoff_bundle, None)

        assert "test-phase" in prompt
        assert "Test failure" in prompt
        assert "Output Format" in prompt
        assert "hypotheses" in prompt

    def test_build_triage_prompt_with_diagnostics(self):
        """Test building triage prompt with diagnostics."""
        system = SecondOpinionTriageSystem()

        handoff_bundle = {
            "phase": {"name": "test-phase"},
            "failure_reason": "Test failure",
            "diagnostics": {
                "error_type": "TokenBudgetExceeded",
                "details": "Output truncated",
            },
        }

        prompt = system._build_triage_prompt(handoff_bundle, None)

        assert "TokenBudgetExceeded" in prompt
        assert "Output truncated" in prompt

    def test_build_triage_prompt_with_context(self):
        """Test building triage prompt with phase context."""
        system = SecondOpinionTriageSystem()

        handoff_bundle = {"phase": {"name": "test-phase"}}
        phase_context = {"complexity": "HIGH", "attempts": 3}

        prompt = system._build_triage_prompt(handoff_bundle, phase_context)

        assert "Phase Context" in prompt
        assert "HIGH" in prompt

    def test_parse_triage_response_valid(self):
        """Test parsing valid triage response."""
        system = SecondOpinionTriageSystem()

        response = {
            "content": json.dumps(
                {
                    "hypotheses": [{"description": "Test", "likelihood": 0.8}],
                    "missing_evidence": ["Evidence 1"],
                    "next_probes": [{"type": "check", "description": "Probe 1"}],
                    "minimal_patch_strategy": {"approach": "Strategy"},
                    "confidence": 0.75,
                    "reasoning": "Test reasoning",
                }
            ),
            "usage": {"total_tokens": 1000},
        }

        report = system._parse_triage_response(response)

        assert isinstance(report, TriageReport)
        assert report.confidence == 0.75
        assert len(report.hypotheses) == 1

    def test_parse_triage_response_with_code_block(self):
        """Test parsing triage response with JSON code block."""
        system = SecondOpinionTriageSystem()

        json_content = {
            "hypotheses": [{"description": "Test", "likelihood": 0.9}],
            "missing_evidence": ["Evidence"],
            "next_probes": [{"type": "check"}],
            "minimal_patch_strategy": {"approach": "Strategy"},
            "confidence": 0.8,
            "reasoning": "Reasoning",
        }

        response = {
            "content": f"Here's the triage:\n```json\n{json.dumps(json_content)}\n```\n",
            "usage": {"total_tokens": 1000},
        }

        report = system._parse_triage_response(response)

        assert isinstance(report, TriageReport)
        assert report.confidence == 0.8

    def test_parse_triage_response_missing_field(self):
        """Test parsing triage response with missing required field."""
        system = SecondOpinionTriageSystem()

        response = {
            "content": json.dumps(
                {
                    "hypotheses": [],
                    "missing_evidence": [],
                    # Missing next_probes
                    "minimal_patch_strategy": {},
                    "confidence": 0.5,
                    "reasoning": "Test",
                }
            ),
        }

        with pytest.raises(ValueError, match="Missing required field"):
            system._parse_triage_response(response)

    def test_parse_triage_response_invalid_confidence(self):
        """Test parsing triage response with invalid confidence."""
        system = SecondOpinionTriageSystem()

        response = {
            "content": json.dumps(
                {
                    "hypotheses": [],
                    "missing_evidence": [],
                    "next_probes": [],
                    "minimal_patch_strategy": {},
                    "confidence": 1.5,  # Invalid: > 1.0
                    "reasoning": "Test",
                }
            ),
        }

        with pytest.raises(ValueError, match="Confidence must be between"):
            system._parse_triage_response(response)

    def test_parse_triage_response_invalid_json(self):
        """Test parsing triage response with invalid JSON."""
        system = SecondOpinionTriageSystem()

        response = {"content": "Not valid JSON {{{"}

        with pytest.raises(ValueError, match="Invalid JSON"):
            system._parse_triage_response(response)

    def test_save_triage_report(self, tmp_path):
        """Test saving triage report to file."""
        system = SecondOpinionTriageSystem()

        report = TriageReport(
            hypotheses=[{"description": "Test", "likelihood": 0.8}],
            missing_evidence=["Evidence"],
            next_probes=[{"type": "check"}],
            minimal_patch_strategy={"approach": "Strategy"},
            confidence=0.75,
            reasoning="Test reasoning",
        )

        output_path = tmp_path / "triage" / "report.json"
        system.save_triage_report(report, output_path)

        assert output_path.exists()

        # Verify content
        with open(output_path, "r") as f:
            data = json.load(f)

        assert data["confidence"] == 0.75
        assert len(data["hypotheses"]) == 1

    def test_load_triage_report(self, tmp_path):
        """Test loading triage report from file."""
        system = SecondOpinionTriageSystem()

        # Create report file
        report_data = {
            "hypotheses": [{"description": "Test", "likelihood": 0.9}],
            "missing_evidence": ["Evidence"],
            "next_probes": [{"type": "check"}],
            "minimal_patch_strategy": {"approach": "Strategy"},
            "confidence": 0.85,
            "reasoning": "Test reasoning",
        }

        report_path = tmp_path / "report.json"
        with open(report_path, "w") as f:
            json.dump(report_data, f)

        # Load report
        report = system.load_triage_report(report_path)

        assert report is not None
        assert isinstance(report, TriageReport)
        assert report.confidence == 0.85
        assert len(report.hypotheses) == 1

    def test_load_triage_report_not_found(self, tmp_path):
        """Test loading triage report from non-existent file."""
        system = SecondOpinionTriageSystem()

        report_path = tmp_path / "nonexistent.json"
        report = system.load_triage_report(report_path)

        assert report is None

    def test_load_triage_report_invalid_json(self, tmp_path):
        """Test loading triage report from invalid JSON file."""
        system = SecondOpinionTriageSystem()

        report_path = tmp_path / "invalid.json"
        with open(report_path, "w") as f:
            f.write("Not valid JSON {{{")

        report = system.load_triage_report(report_path)

        assert report is None

    def test_token_tracking_across_multiple_calls(self):
        """Test token tracking across multiple triage calls."""
        config = SecondOpinionConfig(enabled=True, token_budget=10000)
        system = SecondOpinionTriageSystem(config)

        handoff_bundle = {"phase": {"name": "test-phase"}}

        # First call
        report1 = system.generate_triage(handoff_bundle)
        tokens_after_first = system.get_tokens_used()

        assert report1 is not None
        assert tokens_after_first > 0

        # Second call
        report2 = system.generate_triage(handoff_bundle)
        tokens_after_second = system.get_tokens_used()

        assert report2 is not None
        assert tokens_after_second > tokens_after_first

    def test_full_workflow(self, tmp_path):
        """Test complete workflow: generate, save, load triage report."""
        config = SecondOpinionConfig(enabled=True, token_budget=10000)
        system = SecondOpinionTriageSystem(config)

        # Generate triage
        handoff_bundle = {
            "phase": {
                "name": "test-phase",
                "description": "Test phase",
                "state": "FAILED",
            },
            "failure_reason": "Test failure",
            "diagnostics": {"error": "Test error"},
        }

        report = system.generate_triage(handoff_bundle)
        assert report is not None

        # Save report
        report_path = tmp_path / "triage_report.json"
        system.save_triage_report(report, report_path)
        assert report_path.exists()

        # Load report
        loaded_report = system.load_triage_report(report_path)
        assert loaded_report is not None
        assert loaded_report.confidence == report.confidence
        assert len(loaded_report.hypotheses) == len(report.hypotheses)
