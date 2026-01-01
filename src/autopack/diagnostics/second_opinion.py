"""Second Opinion Triage System

Provides optional bounded "second opinion" triage for diagnostics.
Given an existing handoff bundle, optionally calls a strong model to produce:
- Hypotheses about root causes
- Missing evidence identification
- Next probes to run
- Minimal patch strategy

This is Stage 2 of the diagnostics parity implementation.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class SecondOpinionConfig:
    """Configuration for second opinion triage."""

    def __init__(
        self,
        enabled: bool = False,
        model: str = "claude-opus-4",
        max_tokens: int = 8192,
        temperature: float = 0.3,
        token_budget: int = 50000,
    ):
        """Initialize second opinion configuration.

        Args:
            enabled: Whether second opinion is enabled
            model: Strong model to use for triage (default: claude-opus-4)
            max_tokens: Maximum tokens for triage output
            temperature: Temperature for model sampling
            token_budget: Maximum tokens to spend on second opinion
        """
        self.enabled = enabled
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.token_budget = token_budget


class TriageReport:
    """Structured triage report from second opinion."""

    def __init__(
        self,
        hypotheses: List[Dict[str, Any]],
        missing_evidence: List[str],
        next_probes: List[Dict[str, str]],
        minimal_patch_strategy: Dict[str, Any],
        confidence: float,
        reasoning: str,
    ):
        """Initialize triage report.

        Args:
            hypotheses: List of root cause hypotheses with likelihood scores
            missing_evidence: List of missing evidence items
            next_probes: List of diagnostic probes to run next
            minimal_patch_strategy: Strategy for minimal patch to fix issue
            confidence: Overall confidence in triage (0.0-1.0)
            reasoning: Detailed reasoning for triage conclusions
        """
        self.hypotheses = hypotheses
        self.missing_evidence = missing_evidence
        self.next_probes = next_probes
        self.minimal_patch_strategy = minimal_patch_strategy
        self.confidence = confidence
        self.reasoning = reasoning
        self.timestamp = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert triage report to dictionary."""
        return {
            "hypotheses": self.hypotheses,
            "missing_evidence": self.missing_evidence,
            "next_probes": self.next_probes,
            "minimal_patch_strategy": self.minimal_patch_strategy,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "timestamp": self.timestamp,
        }

    def to_json(self) -> str:
        """Convert triage report to JSON string."""
        return json.dumps(self.to_dict(), indent=2)


class SecondOpinionTriageSystem:
    """Second opinion triage system for diagnostics."""

    def __init__(self, config: Optional[SecondOpinionConfig] = None):
        """Initialize second opinion triage system.

        Args:
            config: Configuration for second opinion (default: disabled)
        """
        self.config = config or SecondOpinionConfig(enabled=False)
        self._tokens_used = 0

    def is_enabled(self) -> bool:
        """Check if second opinion is enabled."""
        return self.config.enabled

    def within_budget(self) -> bool:
        """Check if we're within token budget."""
        return self._tokens_used < self.config.token_budget

    def get_tokens_used(self) -> int:
        """Get total tokens used by second opinion."""
        return self._tokens_used

    def get_tokens_remaining(self) -> int:
        """Get remaining token budget."""
        return max(0, self.config.token_budget - self._tokens_used)

    def generate_triage(
        self,
        handoff_bundle: Dict[str, Any],
        phase_context: Optional[Dict[str, Any]] = None,
    ) -> Optional[TriageReport]:
        """Generate second opinion triage report.

        Args:
            handoff_bundle: Existing handoff bundle with diagnostics
            phase_context: Optional phase context for additional information

        Returns:
            TriageReport if successful, None if disabled or budget exceeded
        """
        if not self.is_enabled():
            logger.debug("[SecondOpinion] Disabled - skipping triage")
            return None

        if not self.within_budget():
            logger.warning(
                f"[SecondOpinion] Token budget exceeded "
                f"({self._tokens_used}/{self.config.token_budget}) - skipping triage"
            )
            return None

        logger.info(
            f"[SecondOpinion] Generating triage report with {self.config.model} "
            f"(budget: {self.get_tokens_remaining()} tokens remaining)"
        )

        try:
            # Build triage prompt from handoff bundle
            prompt = self._build_triage_prompt(handoff_bundle, phase_context)

            # Call strong model for triage
            triage_result = self._call_triage_model(prompt)

            # Parse and validate triage response
            report = self._parse_triage_response(triage_result)

            # Update token usage
            tokens_used = triage_result.get("usage", {}).get("total_tokens", 0)
            self._tokens_used += tokens_used

            logger.info(
                f"[SecondOpinion] Triage complete - confidence: {report.confidence:.2f}, "
                f"tokens used: {tokens_used}, total: {self._tokens_used}"
            )

            return report

        except Exception as e:
            logger.error(f"[SecondOpinion] Triage generation failed: {e}", exc_info=True)
            return None

    def _build_triage_prompt(self, handoff_bundle: Dict[str, Any], phase_context: Optional[Dict[str, Any]]) -> str:
        """Build triage prompt from handoff bundle.

        Args:
            handoff_bundle: Handoff bundle with diagnostics
            phase_context: Optional phase context

        Returns:
            Formatted prompt for triage model
        """
        prompt_parts = [
            "You are an expert diagnostician performing a second opinion triage.",
            "",
            "Given the following handoff bundle from a failed phase, provide:",
            "1. Hypotheses about root causes (with likelihood scores 0.0-1.0)",
            "2. Missing evidence that would help confirm/reject hypotheses",
            "3. Next diagnostic probes to run (specific commands/checks)",
            "4. Minimal patch strategy to fix the issue",
            "",
            "# Handoff Bundle",
            "",
        ]

        # Add phase information
        if "phase" in handoff_bundle:
            phase = handoff_bundle["phase"]
            prompt_parts.extend([
                f"## Phase: {phase.get('name', 'Unknown')}",
                f"Description: {phase.get('description', 'N/A')}",
                f"State: {phase.get('state', 'N/A')}",
                f"Attempts: {phase.get('builder_attempts', 0)}/{phase.get('max_builder_attempts', 5)}",
                "",
            ])

        # Add failure information
        if "failure_reason" in handoff_bundle:
            prompt_parts.extend([
                "## Failure Reason",
                handoff_bundle["failure_reason"],
                "",
            ])

        # Add diagnostics
        if "diagnostics" in handoff_bundle:
            diagnostics = handoff_bundle["diagnostics"]
            prompt_parts.extend([
                "## Diagnostics",
                json.dumps(diagnostics, indent=2),
                "",
            ])

        # Add phase context if available
        if phase_context:
            prompt_parts.extend([
                "## Phase Context",
                json.dumps(phase_context, indent=2),
                "",
            ])

        # Add output format instructions
        prompt_parts.extend([
            "# Output Format",
            "",
            "Provide your triage as a JSON object with this structure:",
            "",
            "```json",
            "{",
            '  "hypotheses": [',
            '    {',
            '      "description": "Root cause hypothesis",',
            '      "likelihood": 0.8,',
            '      "evidence_for": ["Supporting evidence"],',
            '      "evidence_against": ["Contradicting evidence"]',
            '    }',
            '  ],',
            '  "missing_evidence": [',
            '    "Specific evidence item needed"',
            '  ],',
            '  "next_probes": [',
            '    {',
            '      "type": "command|check|inspection",',
            '      "description": "What to probe",',
            '      "command": "Specific command to run (if applicable)"',
            '    }',
            '  ],',
            '  "minimal_patch_strategy": {',
            '    "approach": "High-level strategy",',
            '    "files_to_modify": ["file1.py", "file2.py"],',
            '    "key_changes": ["Change 1", "Change 2"],',
            '    "risks": ["Risk 1", "Risk 2"]',
            '  },',
            '  "confidence": 0.75,',
            '  "reasoning": "Detailed reasoning for triage conclusions"',
            "}",
            "```",
            "",
            "Focus on actionable insights and specific next steps.",
        ])

        return "\n".join(prompt_parts)

    def _call_triage_model(self, prompt: str) -> Dict[str, Any]:
        """Call triage model with prompt.

        Args:
            prompt: Formatted triage prompt

        Returns:
            Model response with triage and usage information
        """
        import os

        # Check if Anthropic API key is available
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning(
                "[SecondOpinion] ANTHROPIC_API_KEY not set - returning mock response. "
                "Set ANTHROPIC_API_KEY to enable real second opinion triage."
            )
            return self._mock_triage_response()

        try:
            # Import Anthropic client
            try:
                from anthropic import Anthropic
            except ImportError:
                logger.warning(
                    "[SecondOpinion] anthropic package not installed - returning mock response. "
                    "Install with: pip install anthropic"
                )
                return self._mock_triage_response()

            # Initialize Anthropic client
            client = Anthropic(api_key=api_key)

            # Make API call with strict token budget enforcement
            logger.debug(
                f"[SecondOpinion] Calling {self.config.model} with {self.config.max_tokens} max_tokens"
            )

            response = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract content from response
            content = ""
            for block in response.content:
                if hasattr(block, "text"):
                    content += block.text

            # Track usage
            usage_info = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

            logger.debug(
                f"[SecondOpinion] API call successful - "
                f"tokens: {usage_info['total_tokens']} "
                f"(prompt: {usage_info['prompt_tokens']}, completion: {usage_info['completion_tokens']})"
            )

            return {
                "content": content,
                "usage": usage_info,
            }

        except Exception as e:
            logger.error(
                f"[SecondOpinion] LLM API call failed: {e} - returning mock response",
                exc_info=True,
            )
            return self._mock_triage_response()

    def _mock_triage_response(self) -> Dict[str, Any]:
        """Return mock triage response for testing or when API unavailable.

        Returns:
            Mock response in expected format
        """
        mock_response = {
            "content": json.dumps({
                "hypotheses": [
                    {
                        "description": "Token budget exceeded during code generation",
                        "likelihood": 0.9,
                        "evidence_for": [
                            "max_tokens truncation in logs",
                            "Incomplete file generation",
                        ],
                        "evidence_against": [],
                    },
                    {
                        "description": "Protected path violation",
                        "likelihood": 0.3,
                        "evidence_for": ["Isolation warnings in logs"],
                        "evidence_against": ["No explicit rejection messages"],
                    },
                ],
                "missing_evidence": [
                    "Actual token counts from failed attempt",
                    "Full LLM response before truncation",
                    "Context size at time of generation",
                ],
                "next_probes": [
                    {
                        "type": "check",
                        "description": "Check token usage in phase logs",
                        "command": "grep 'TOKEN_BUDGET' phase.log",
                    },
                    {
                        "type": "inspection",
                        "description": "Inspect phase complexity vs token allocation",
                        "command": None,
                    },
                ],
                "minimal_patch_strategy": {
                    "approach": "Increase token budget for this complexity level",
                    "files_to_modify": ["src/autopack/anthropic_clients.py"],
                    "key_changes": [
                        "Increase max_tokens from 8192 to 12288 for medium complexity",
                        "Add token usage logging",
                    ],
                    "risks": [
                        "Higher API costs",
                        "May not fully resolve if context is too large",
                    ],
                },
                "confidence": 0.85,
                "reasoning": "Token truncation is the most likely cause based on log patterns. "
                "The phase attempted to generate multiple files but was cut off mid-generation. "
                "Increasing token budget should resolve this, but we should also verify context size.",
            }),
            "usage": {
                "prompt_tokens": 0,  # Mock has no real usage
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        }

        return mock_response

    def _parse_triage_response(self, response: Dict[str, Any]) -> TriageReport:
        """Parse and validate triage response.

        Args:
            response: Raw model response

        Returns:
            Validated TriageReport

        Raises:
            ValueError: If response is invalid
        """
        try:
            # Extract content from response
            content = response.get("content", "")

            # Parse JSON (handle code blocks if present)
            if "```json" in content:
                # Extract JSON from code block
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                content = content[json_start:json_end].strip()

            triage_data = json.loads(content)

            # Validate required fields
            required_fields = [
                "hypotheses",
                "missing_evidence",
                "next_probes",
                "minimal_patch_strategy",
                "confidence",
                "reasoning",
            ]
            for field in required_fields:
                if field not in triage_data:
                    raise ValueError(f"Missing required field: {field}")

            # Validate confidence range
            confidence = triage_data["confidence"]
            if not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Confidence must be between 0.0 and 1.0, got {confidence}")

            # Create TriageReport
            return TriageReport(
                hypotheses=triage_data["hypotheses"],
                missing_evidence=triage_data["missing_evidence"],
                next_probes=triage_data["next_probes"],
                minimal_patch_strategy=triage_data["minimal_patch_strategy"],
                confidence=confidence,
                reasoning=triage_data["reasoning"],
            )

        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in triage response: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse triage response: {e}")

    def save_triage_report(self, report: TriageReport, output_path: Path) -> None:
        """Save triage report to file.

        Args:
            report: Triage report to save
            output_path: Path to save report (JSON file)
        """
        try:
            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "w") as f:
                f.write(report.to_json())
            logger.info(f"[SecondOpinion] Triage report saved to {output_path}")
        except Exception as e:
            logger.error(f"[SecondOpinion] Failed to save triage report: {e}", exc_info=True)

    def load_triage_report(self, input_path: Path) -> Optional[TriageReport]:
        """Load triage report from file.

        Args:
            input_path: Path to load report from (JSON file)

        Returns:
            TriageReport if successful, None if file not found or invalid
        """
        try:
            with open(input_path, "r") as f:
                data = json.load(f)

            return TriageReport(
                hypotheses=data["hypotheses"],
                missing_evidence=data["missing_evidence"],
                next_probes=data["next_probes"],
                minimal_patch_strategy=data["minimal_patch_strategy"],
                confidence=data["confidence"],
                reasoning=data["reasoning"],
            )
        except FileNotFoundError:
            logger.warning(f"[SecondOpinion] Triage report not found: {input_path}")
            return None
        except Exception as e:
            logger.error(f"[SecondOpinion] Failed to load triage report: {e}", exc_info=True)
            return None
