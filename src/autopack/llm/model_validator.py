"""LLM Model Validator for capability assessment and benchmarking.

This module provides validation capabilities for LLM models including:
- Capability assessment through benchmark tests
- Hardware compatibility checking
- Performance benchmarking
- Model health validation

Part of IMP-LLM-001: LLM Model Validation & Routing System.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import yaml

from .model_registry import ModelRegistry, get_model_registry

logger = logging.getLogger(__name__)


class ValidationResultStatus(Enum):
    """Status of a validation result."""

    PASSED = "passed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ERROR = "error"


@dataclass
class BenchmarkResult:
    """Result of a single benchmark test."""

    benchmark_name: str
    status: ValidationResultStatus
    score: float
    latency_ms: float
    error_message: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ValidationResult:
    """Complete validation result for a model."""

    model_id: str
    status: ValidationResultStatus
    timestamp: datetime
    overall_score: float
    benchmark_results: List[BenchmarkResult]
    capabilities_validated: List[str]
    capabilities_missing: List[str]
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        """Check if validation passed."""
        return self.status == ValidationResultStatus.PASSED

    @property
    def benchmark_scores(self) -> Dict[str, float]:
        """Get dictionary of benchmark scores."""
        return {r.benchmark_name: r.score for r in self.benchmark_results}


class BenchmarkTest(ABC):
    """Abstract base class for benchmark tests."""

    def __init__(self, name: str, weight: float = 1.0, timeout_seconds: float = 30.0):
        """Initialize benchmark test.

        Args:
            name: Benchmark test name.
            weight: Weight for scoring (default 1.0).
            timeout_seconds: Test timeout in seconds.
        """
        self.name = name
        self.weight = weight
        self.timeout_seconds = timeout_seconds

    @abstractmethod
    async def run(
        self, model_id: str, model_call: Callable[..., Any]
    ) -> BenchmarkResult:
        """Run the benchmark test.

        Args:
            model_id: Model identifier being tested.
            model_call: Callable to invoke the model.

        Returns:
            BenchmarkResult with test outcomes.
        """
        pass


class ReasoningBenchmark(BenchmarkTest):
    """Benchmark for logical reasoning capabilities."""

    def __init__(self, weight: float = 0.3, timeout_seconds: float = 30.0):
        super().__init__("reasoning", weight, timeout_seconds)
        self.test_prompts = [
            {
                "prompt": "If all A are B, and all B are C, what can we conclude about A and C?",
                "expected_contains": ["all A are C", "A are C", "transitive"],
            },
            {
                "prompt": "A bat and a ball cost $1.10 in total. The bat costs $1.00 more than the ball. How much does the ball cost?",
                "expected_contains": ["$0.05", "5 cents", "0.05"],
            },
        ]

    async def run(
        self, model_id: str, model_call: Callable[..., Any]
    ) -> BenchmarkResult:
        """Run reasoning benchmark."""
        start_time = time.time()
        correct = 0
        total = len(self.test_prompts)

        try:
            for test in self.test_prompts:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(model_call, test["prompt"]),
                        timeout=self.timeout_seconds,
                    )
                    response_lower = str(response).lower()
                    if any(exp.lower() in response_lower for exp in test["expected_contains"]):
                        correct += 1
                except asyncio.TimeoutError:
                    logger.warning(f"[ReasoningBenchmark] Timeout for model {model_id}")
                except Exception as e:
                    logger.warning(f"[ReasoningBenchmark] Error for model {model_id}: {e}")

            latency_ms = (time.time() - start_time) * 1000
            score = correct / total if total > 0 else 0.0

            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.PASSED if score >= 0.5 else ValidationResultStatus.FAILED,
                score=score,
                latency_ms=latency_ms,
                details={"correct": correct, "total": total},
            )
        except Exception as e:
            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.ERROR,
                score=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )


class CodingBenchmark(BenchmarkTest):
    """Benchmark for code generation capabilities."""

    def __init__(self, weight: float = 0.3, timeout_seconds: float = 45.0):
        super().__init__("coding", weight, timeout_seconds)
        self.test_prompts = [
            {
                "prompt": "Write a Python function that checks if a number is prime. Return only the function, no explanation.",
                "expected_contains": ["def ", "return", "for", "prime"],
            },
            {
                "prompt": "Write a Python function to reverse a string. Return only the function.",
                "expected_contains": ["def ", "return", "[::-1]", "reversed"],
            },
        ]

    async def run(
        self, model_id: str, model_call: Callable[..., Any]
    ) -> BenchmarkResult:
        """Run coding benchmark."""
        start_time = time.time()
        correct = 0
        total = len(self.test_prompts)

        try:
            for test in self.test_prompts:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(model_call, test["prompt"]),
                        timeout=self.timeout_seconds,
                    )
                    response_str = str(response)
                    # Check for basic code structure
                    has_def = "def " in response_str
                    has_return = "return" in response_str
                    has_any_expected = any(
                        exp in response_str for exp in test["expected_contains"]
                    )
                    if has_def and has_return and has_any_expected:
                        correct += 1
                except asyncio.TimeoutError:
                    logger.warning(f"[CodingBenchmark] Timeout for model {model_id}")
                except Exception as e:
                    logger.warning(f"[CodingBenchmark] Error for model {model_id}: {e}")

            latency_ms = (time.time() - start_time) * 1000
            score = correct / total if total > 0 else 0.0

            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.PASSED if score >= 0.5 else ValidationResultStatus.FAILED,
                score=score,
                latency_ms=latency_ms,
                details={"correct": correct, "total": total},
            )
        except Exception as e:
            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.ERROR,
                score=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )


class AnalysisBenchmark(BenchmarkTest):
    """Benchmark for text analysis capabilities."""

    def __init__(self, weight: float = 0.2, timeout_seconds: float = 30.0):
        super().__init__("analysis", weight, timeout_seconds)
        self.test_prompts = [
            {
                "prompt": "Analyze the sentiment of: 'I absolutely love this product, it exceeded all my expectations!'",
                "expected_contains": ["positive", "happy", "satisfied", "love"],
            },
            {
                "prompt": "Summarize in one sentence: 'Machine learning is a subset of artificial intelligence that enables systems to learn from data.'",
                "expected_contains": ["machine learning", "AI", "data", "learn"],
            },
        ]

    async def run(
        self, model_id: str, model_call: Callable[..., Any]
    ) -> BenchmarkResult:
        """Run analysis benchmark."""
        start_time = time.time()
        correct = 0
        total = len(self.test_prompts)

        try:
            for test in self.test_prompts:
                try:
                    response = await asyncio.wait_for(
                        asyncio.to_thread(model_call, test["prompt"]),
                        timeout=self.timeout_seconds,
                    )
                    response_lower = str(response).lower()
                    if any(exp.lower() in response_lower for exp in test["expected_contains"]):
                        correct += 1
                except asyncio.TimeoutError:
                    logger.warning(f"[AnalysisBenchmark] Timeout for model {model_id}")
                except Exception as e:
                    logger.warning(f"[AnalysisBenchmark] Error for model {model_id}: {e}")

            latency_ms = (time.time() - start_time) * 1000
            score = correct / total if total > 0 else 0.0

            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.PASSED if score >= 0.5 else ValidationResultStatus.FAILED,
                score=score,
                latency_ms=latency_ms,
                details={"correct": correct, "total": total},
            )
        except Exception as e:
            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.ERROR,
                score=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )


class SpeedBenchmark(BenchmarkTest):
    """Benchmark for response time performance."""

    def __init__(self, weight: float = 0.2, timeout_seconds: float = 10.0):
        super().__init__("speed", weight, timeout_seconds)
        self.test_prompt = "Hello, how are you today?"
        self.target_latency_ms = 2000  # 2 seconds target

    async def run(
        self, model_id: str, model_call: Callable[..., Any]
    ) -> BenchmarkResult:
        """Run speed benchmark."""
        start_time = time.time()

        try:
            await asyncio.wait_for(
                asyncio.to_thread(model_call, self.test_prompt),
                timeout=self.timeout_seconds,
            )
            latency_ms = (time.time() - start_time) * 1000

            # Score based on latency (faster = higher score)
            if latency_ms <= self.target_latency_ms:
                score = 1.0
            elif latency_ms <= self.target_latency_ms * 2:
                score = 0.8
            elif latency_ms <= self.target_latency_ms * 3:
                score = 0.6
            else:
                score = max(0.2, 1.0 - (latency_ms / (self.target_latency_ms * 5)))

            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.PASSED if score >= 0.5 else ValidationResultStatus.FAILED,
                score=score,
                latency_ms=latency_ms,
                details={"target_latency_ms": self.target_latency_ms},
            )
        except asyncio.TimeoutError:
            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.FAILED,
                score=0.0,
                latency_ms=self.timeout_seconds * 1000,
                error_message="Timeout",
            )
        except Exception as e:
            return BenchmarkResult(
                benchmark_name=self.name,
                status=ValidationResultStatus.ERROR,
                score=0.0,
                latency_ms=(time.time() - start_time) * 1000,
                error_message=str(e),
            )


class ModelValidator:
    """Validates LLM model capabilities through benchmarks.

    Provides:
    - Capability assessment through benchmark tests
    - Performance benchmarking
    - Health validation
    - Validation result caching
    """

    def __init__(
        self,
        registry: Optional[ModelRegistry] = None,
        config_path: str = "config/llm_validation.yaml",
    ):
        """Initialize the model validator.

        Args:
            registry: Model registry instance (uses singleton if not provided).
            config_path: Path to validation configuration.
        """
        self.registry = registry or get_model_registry(config_path)
        self._config = self._load_config(config_path)
        self._benchmarks = self._create_benchmarks()
        self._validation_cache: Dict[str, ValidationResult] = {}

    def _load_config(self, config_path: str) -> Dict[str, Any]:
        """Load validation configuration."""
        config_file = Path(config_path)
        if not config_file.is_absolute():
            repo_root = Path(__file__).resolve().parents[3]
            config_file = repo_root / config_path

        if config_file.exists():
            try:
                return yaml.safe_load(config_file.read_text(encoding="utf-8")) or {}
            except Exception as e:
                logger.warning(f"[ModelValidator] Failed to load config: {e}")
        return {}

    def _create_benchmarks(self) -> List[BenchmarkTest]:
        """Create benchmark tests from configuration."""
        benchmarks = []
        benchmark_config = self._config.get("validation", {}).get("benchmark_tests", {})

        # Create benchmarks with configured weights
        reasoning_config = benchmark_config.get("reasoning", {})
        benchmarks.append(
            ReasoningBenchmark(
                weight=reasoning_config.get("weight", 0.3),
                timeout_seconds=reasoning_config.get("timeout_seconds", 30),
            )
        )

        coding_config = benchmark_config.get("coding", {})
        benchmarks.append(
            CodingBenchmark(
                weight=coding_config.get("weight", 0.3),
                timeout_seconds=coding_config.get("timeout_seconds", 45),
            )
        )

        analysis_config = benchmark_config.get("analysis", {})
        benchmarks.append(
            AnalysisBenchmark(
                weight=analysis_config.get("weight", 0.2),
                timeout_seconds=analysis_config.get("timeout_seconds", 30),
            )
        )

        speed_config = benchmark_config.get("speed", {})
        benchmarks.append(
            SpeedBenchmark(
                weight=speed_config.get("weight", 0.2),
                timeout_seconds=speed_config.get("timeout_seconds", 10),
            )
        )

        return benchmarks

    async def validate_model(
        self,
        model_id: str,
        model_call: Callable[..., Any],
        required_capabilities: Optional[List[str]] = None,
        skip_benchmarks: bool = False,
    ) -> ValidationResult:
        """Validate a model's capabilities.

        Args:
            model_id: Model identifier to validate.
            model_call: Callable to invoke the model.
            required_capabilities: List of required capabilities to check.
            skip_benchmarks: If True, skip benchmark tests.

        Returns:
            ValidationResult with validation outcomes.
        """
        model = self.registry.get_model(model_id)
        if model is None:
            return ValidationResult(
                model_id=model_id,
                status=ValidationResultStatus.ERROR,
                timestamp=datetime.now(timezone.utc),
                overall_score=0.0,
                benchmark_results=[],
                capabilities_validated=[],
                capabilities_missing=[],
                error_message=f"Model {model_id} not found in registry",
            )

        # Check required capabilities
        required_capabilities = required_capabilities or []
        capabilities_validated = []
        capabilities_missing = []

        for cap in required_capabilities:
            if model.capabilities.has_capability(cap):
                capabilities_validated.append(cap)
            else:
                capabilities_missing.append(cap)

        # Run benchmarks if not skipped
        benchmark_results = []
        if not skip_benchmarks:
            for benchmark in self._benchmarks:
                result = await benchmark.run(model_id, model_call)
                benchmark_results.append(result)

        # Calculate overall score
        if benchmark_results:
            total_weight = sum(b.weight for b in self._benchmarks)
            weighted_score = sum(
                r.score * b.weight
                for r, b in zip(benchmark_results, self._benchmarks)
            )
            overall_score = weighted_score / total_weight if total_weight > 0 else 0.0
        else:
            # Use pre-configured benchmark scores
            overall_score = model.capabilities.weighted_score()

        # Determine overall status
        min_score = self._config.get("validation", {}).get("min_capability_score", 0.8)
        if capabilities_missing:
            status = ValidationResultStatus.FAILED
        elif overall_score >= min_score:
            status = ValidationResultStatus.PASSED
        else:
            status = ValidationResultStatus.FAILED

        result = ValidationResult(
            model_id=model_id,
            status=status,
            timestamp=datetime.now(timezone.utc),
            overall_score=overall_score,
            benchmark_results=benchmark_results,
            capabilities_validated=capabilities_validated,
            capabilities_missing=capabilities_missing,
        )

        # Cache result
        self._validation_cache[model_id] = result

        # Update registry health based on validation
        if status == ValidationResultStatus.PASSED:
            avg_latency = (
                sum(r.latency_ms for r in benchmark_results) / len(benchmark_results)
                if benchmark_results
                else 0.0
            )
            self.registry.record_success(model_id, avg_latency)
        else:
            self.registry.record_failure(
                model_id, f"Validation failed: score={overall_score:.2f}"
            )

        return result

    def validate_model_sync(
        self,
        model_id: str,
        model_call: Callable[..., Any],
        required_capabilities: Optional[List[str]] = None,
        skip_benchmarks: bool = False,
    ) -> ValidationResult:
        """Synchronous wrapper for validate_model.

        Args:
            model_id: Model identifier to validate.
            model_call: Callable to invoke the model.
            required_capabilities: List of required capabilities to check.
            skip_benchmarks: If True, skip benchmark tests.

        Returns:
            ValidationResult with validation outcomes.
        """
        return asyncio.run(
            self.validate_model(model_id, model_call, required_capabilities, skip_benchmarks)
        )

    def quick_validate(
        self,
        model_id: str,
        required_capabilities: Optional[List[str]] = None,
    ) -> ValidationResult:
        """Quick validation without running benchmarks.

        Uses pre-configured benchmark scores from the registry.

        Args:
            model_id: Model identifier to validate.
            required_capabilities: List of required capabilities to check.

        Returns:
            ValidationResult with validation outcomes.
        """
        model = self.registry.get_model(model_id)
        if model is None:
            return ValidationResult(
                model_id=model_id,
                status=ValidationResultStatus.ERROR,
                timestamp=datetime.now(timezone.utc),
                overall_score=0.0,
                benchmark_results=[],
                capabilities_validated=[],
                capabilities_missing=[],
                error_message=f"Model {model_id} not found in registry",
            )

        required_capabilities = required_capabilities or []
        capabilities_validated = []
        capabilities_missing = []

        for cap in required_capabilities:
            if model.capabilities.has_capability(cap):
                capabilities_validated.append(cap)
            else:
                capabilities_missing.append(cap)

        # Use pre-configured benchmark scores
        overall_score = model.capabilities.weighted_score()

        min_score = self._config.get("validation", {}).get("min_capability_score", 0.8)
        if capabilities_missing:
            status = ValidationResultStatus.FAILED
        elif overall_score >= min_score:
            status = ValidationResultStatus.PASSED
        else:
            status = ValidationResultStatus.FAILED

        return ValidationResult(
            model_id=model_id,
            status=status,
            timestamp=datetime.now(timezone.utc),
            overall_score=overall_score,
            benchmark_results=[],
            capabilities_validated=capabilities_validated,
            capabilities_missing=capabilities_missing,
        )

    def get_cached_result(self, model_id: str) -> Optional[ValidationResult]:
        """Get cached validation result.

        Args:
            model_id: Model identifier.

        Returns:
            Cached ValidationResult or None.
        """
        return self._validation_cache.get(model_id)

    def clear_cache(self, model_id: Optional[str] = None) -> None:
        """Clear validation cache.

        Args:
            model_id: Specific model to clear, or None for all.
        """
        if model_id:
            self._validation_cache.pop(model_id, None)
        else:
            self._validation_cache.clear()

    def is_model_valid(
        self,
        model_id: str,
        required_capabilities: Optional[List[str]] = None,
    ) -> bool:
        """Quick check if a model passes validation.

        Args:
            model_id: Model identifier.
            required_capabilities: Required capabilities to check.

        Returns:
            True if model passes validation.
        """
        result = self.quick_validate(model_id, required_capabilities)
        return result.passed

    def get_valid_models(
        self,
        required_capabilities: Optional[List[str]] = None,
    ) -> List[str]:
        """Get list of valid model IDs.

        Args:
            required_capabilities: Required capabilities to check.

        Returns:
            List of model IDs that pass validation.
        """
        valid_models = []
        for model in self.registry.get_all_models():
            if self.is_model_valid(model.model_id, required_capabilities):
                valid_models.append(model.model_id)
        return valid_models


# Singleton instance
_validator: Optional[ModelValidator] = None


def get_model_validator(config_path: str = "config/llm_validation.yaml") -> ModelValidator:
    """Get or create the singleton ModelValidator instance.

    Args:
        config_path: Path to configuration file.

    Returns:
        ModelValidator singleton instance.
    """
    global _validator
    if _validator is None:
        _validator = ModelValidator(config_path=config_path)
    return _validator
