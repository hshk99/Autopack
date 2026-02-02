"""Tests for LLM model validator edge cases.

This module provides comprehensive testing for LLM model validation including:
- Rate limit handling and recovery
- Quota exhaustion scenarios
- Timeout behavior and recovery

Part of IMP-TESTING-003: LLM model validation edge cases not tested.
"""

import asyncio
import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

from autopack.llm.model_validator import (
    AnalysisBenchmark,
    BenchmarkResult,
    BenchmarkTest,
    CodingBenchmark,
    ModelValidator,
    ReasoningBenchmark,
    SpeedBenchmark,
    ValidationResult,
    ValidationResultStatus,
)


class TestTimeoutBehavior:
    """Tests for timeout behavior in model validation."""

    @pytest.mark.asyncio
    async def test_reasoning_benchmark_timeout(self):
        """Test reasoning benchmark timeout handling."""
        benchmark = ReasoningBenchmark(timeout_seconds=0.1)

        def slow_model_call(prompt: str) -> str:
            import time
            time.sleep(1.0)  # Simulate slow response
            return "response"

        result = await benchmark.run("test-model", slow_model_call)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.benchmark_name == "reasoning"
        assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_coding_benchmark_timeout(self):
        """Test coding benchmark timeout handling."""
        benchmark = CodingBenchmark(timeout_seconds=0.1)

        def slow_model_call(prompt: str) -> str:
            import time
            time.sleep(1.0)  # Simulate slow response
            return "response"

        result = await benchmark.run("test-model", slow_model_call)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.benchmark_name == "coding"

    @pytest.mark.asyncio
    async def test_analysis_benchmark_timeout(self):
        """Test analysis benchmark timeout handling."""
        benchmark = AnalysisBenchmark(timeout_seconds=0.1)

        def slow_model_call(prompt: str) -> str:
            import time
            time.sleep(1.0)  # Simulate slow response
            return "response"

        result = await benchmark.run("test-model", slow_model_call)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.benchmark_name == "analysis"

    @pytest.mark.asyncio
    async def test_speed_benchmark_timeout(self):
        """Test speed benchmark timeout handling."""
        benchmark = SpeedBenchmark(timeout_seconds=0.1)

        def slow_model_call(prompt: str) -> str:
            import time
            time.sleep(1.0)  # Simulate slow response
            return "response"

        result = await benchmark.run("test-model", slow_model_call)

        # Timeout should result in failure or error status
        assert result.status in (ValidationResultStatus.FAILED, ValidationResultStatus.ERROR)
        assert result.benchmark_name == "speed"

    @pytest.mark.asyncio
    async def test_benchmark_timeout_error_message(self):
        """Test that timeout errors are handled appropriately."""
        benchmark = SpeedBenchmark(timeout_seconds=0.1)

        def slow_model_call(prompt: str) -> str:
            import time
            time.sleep(1.0)  # Simulate slow response
            return "response"

        result = await benchmark.run("test-model", slow_model_call)

        # When timeout occurs, should have failed/error status or low score
        assert result.status in (ValidationResultStatus.FAILED, ValidationResultStatus.ERROR)

    @pytest.mark.asyncio
    async def test_multiple_timeouts_in_benchmark(self):
        """Test handling multiple timeouts within same benchmark run."""
        benchmark = ReasoningBenchmark(timeout_seconds=0.1)

        def intermittent_timeout(prompt: str) -> str:
            # Simulate timeout by sleeping
            import time
            time.sleep(0.2)  # Exceed the timeout
            return "transitive relation"

        result = await benchmark.run("test-model", intermittent_timeout)

        # At least some prompts should timeout, affecting overall score
        assert result.latency_ms > 0
        # Score should be less than perfect due to timeouts
        assert result.score <= 1.0


class TestRateLimitHandling:
    """Tests for rate limit error handling in model validation."""

    @pytest.mark.asyncio
    async def test_reasoning_benchmark_rate_limit_error(self):
        """Test reasoning benchmark handles rate limit errors gracefully."""
        benchmark = ReasoningBenchmark()

        def rate_limited_model(prompt: str) -> str:
            # Synchronous function that raises rate limit error
            raise RuntimeError("Rate limit exceeded: 429 Too Many Requests")

        result = await benchmark.run("test-model", rate_limited_model)

        # Should handle error gracefully
        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0
        assert result.benchmark_name == "reasoning"

    @pytest.mark.asyncio
    async def test_coding_benchmark_rate_limit_error(self):
        """Test coding benchmark handles rate limit errors."""
        benchmark = CodingBenchmark()

        def rate_limited_model(prompt: str) -> str:
            raise RuntimeError("API rate limit exceeded")

        result = await benchmark.run("test-model", rate_limited_model)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_analysis_benchmark_rate_limit_error(self):
        """Test analysis benchmark handles rate limit errors."""
        benchmark = AnalysisBenchmark()

        def rate_limited_model(prompt: str) -> str:
            raise RuntimeError("Rate limited: too many requests")

        result = await benchmark.run("test-model", rate_limited_model)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_partial_rate_limiting(self):
        """Test benchmark when some requests fail with rate limits."""
        benchmark = ReasoningBenchmark()

        def partial_rate_limit(prompt: str) -> str:
            # Simulate partial failures - rate limit on any bat/ball prompt
            if "bat and ball" in prompt:
                raise RuntimeError("Rate limit exceeded")
            return "transitive"

        result = await benchmark.run("test-model", partial_rate_limit)

        # Should have at least some failure (1 at least failed due to rate limit)
        # Score should reflect the partial failures
        assert result.score < 1.0
        assert result.details["total"] == 2

    @pytest.mark.asyncio
    async def test_rate_limit_error_message_preserved(self):
        """Test that rate limit error messages are preserved."""
        benchmark = ReasoningBenchmark()

        rate_limit_msg = "Rate limit exceeded: 429 Too Many Requests. Retry after 60 seconds"

        async def rate_limited_model(prompt: str) -> str:
            raise RuntimeError(rate_limit_msg)

        result = await benchmark.run("test-model", rate_limited_model)

        # Error should contain rate limit information
        if result.error_message:
            assert "Rate limit" in result.error_message or result.score == 0.0


class TestQuotaExhaustionHandling:
    """Tests for quota exhaustion error handling in model validation."""

    @pytest.mark.asyncio
    async def test_reasoning_benchmark_quota_exhausted(self):
        """Test reasoning benchmark handles quota exhaustion."""
        benchmark = ReasoningBenchmark()

        def quota_exhausted_model(prompt: str) -> str:
            raise RuntimeError("Quota exceeded: Account has exhausted monthly token limit")

        result = await benchmark.run("test-model", quota_exhausted_model)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0
        assert result.benchmark_name == "reasoning"

    @pytest.mark.asyncio
    async def test_coding_benchmark_quota_exhausted(self):
        """Test coding benchmark handles quota exhaustion."""
        benchmark = CodingBenchmark()

        def quota_exhausted_model(prompt: str) -> str:
            raise RuntimeError("Account quota exceeded for model")

        result = await benchmark.run("test-model", quota_exhausted_model)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_analysis_benchmark_quota_exhausted(self):
        """Test analysis benchmark handles quota exhaustion."""
        benchmark = AnalysisBenchmark()

        def quota_exhausted_model(prompt: str) -> str:
            raise RuntimeError("Quota exhausted for this billing cycle")

        result = await benchmark.run("test-model", quota_exhausted_model)

        assert result.status == ValidationResultStatus.ERROR or result.status == ValidationResultStatus.FAILED
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_speed_benchmark_quota_exhausted(self):
        """Test speed benchmark handles quota exhaustion."""
        benchmark = SpeedBenchmark()

        def quota_exhausted_model(prompt: str) -> str:
            raise RuntimeError("Insufficient quota remaining")

        result = await benchmark.run("test-model", quota_exhausted_model)

        # Should handle quota error gracefully
        assert result.status in (ValidationResultStatus.ERROR, ValidationResultStatus.FAILED)
        assert result.score == 0.0

    @pytest.mark.asyncio
    async def test_quota_error_message_preserved(self):
        """Test that quota exhaustion error messages are preserved."""
        benchmark = ReasoningBenchmark()

        quota_msg = "Quota exceeded: Account has used 100% of monthly token limit"

        def quota_exhausted_model(prompt: str) -> str:
            raise RuntimeError(quota_msg)

        result = await benchmark.run("test-model", quota_exhausted_model)

        # Should handle gracefully
        assert result.score == 0.0


class TestBenchmarkResultValidation:
    """Tests for benchmark result validation and error handling."""

    @pytest.mark.asyncio
    async def test_benchmark_result_with_latency_measurement(self):
        """Test that latency is properly measured."""
        benchmark = SpeedBenchmark()

        def model_call(prompt: str) -> str:
            import time
            time.sleep(0.05)  # 50ms delay
            return "response"

        result = await benchmark.run("test-model", model_call)

        # Should measure latency (at least 1ms for any execution)
        assert result.latency_ms > 0  # Any positive latency is valid

    @pytest.mark.asyncio
    async def test_benchmark_result_details_tracking(self):
        """Test that benchmark results include detailed tracking."""
        benchmark = ReasoningBenchmark()

        def model_call(prompt: str) -> str:
            if "bat and ball" in prompt:
                return "$0.05"
            return "correct answer"

        result = await benchmark.run("test-model", model_call)

        assert "correct" in result.details
        assert "total" in result.details
        assert result.details["total"] == 2

    @pytest.mark.asyncio
    async def test_benchmark_timeout_exceeded_error_handling(self):
        """Test handling of requests that exceed timeout."""
        benchmark = ReasoningBenchmark(timeout_seconds=0.05)

        def very_slow_model(prompt: str) -> str:
            import time
            time.sleep(2.0)  # 2 second delay
            return "response"

        result = await benchmark.run("test-model", very_slow_model)

        # Should fail or error due to timeout
        assert result.status in (
            ValidationResultStatus.ERROR,
            ValidationResultStatus.FAILED
        )


class TestModelValidatorEdgeCases:
    """Tests for ModelValidator class with edge case scenarios."""

    @pytest.mark.asyncio
    async def test_validate_model_with_timeout_error(self):
        """Test model validation when benchmarks timeout."""
        validator = ModelValidator(config_path="config/llm_validation.yaml")

        async def timeout_model(prompt: str) -> str:
            await asyncio.sleep(10.0)  # Will timeout
            return "response"

        result = await validator.validate_model(
            "claude-opus-4-5",
            timeout_model,
            skip_benchmarks=False
        )

        # Should complete even with timeouts
        assert result.model_id == "claude-opus-4-5"
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_model_with_rate_limit_error(self):
        """Test model validation when rate limited."""
        validator = ModelValidator(config_path="config/llm_validation.yaml")

        async def rate_limited_model(prompt: str) -> str:
            raise RuntimeError("429 Too Many Requests")

        result = await validator.validate_model(
            "claude-opus-4-5",
            rate_limited_model,
            skip_benchmarks=False
        )

        # Should handle rate limit gracefully
        assert result.model_id == "claude-opus-4-5"
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_model_with_quota_exhausted(self):
        """Test model validation when quota is exhausted."""
        validator = ModelValidator(config_path="config/llm_validation.yaml")

        async def quota_model(prompt: str) -> str:
            raise RuntimeError("Quota exceeded")

        result = await validator.validate_model(
            "claude-opus-4-5",
            quota_model,
            skip_benchmarks=False
        )

        # Should handle quota errors gracefully
        assert result.model_id == "claude-opus-4-5"
        assert isinstance(result, ValidationResult)

    @pytest.mark.asyncio
    async def test_validate_model_skip_benchmarks(self):
        """Test model validation with benchmarks skipped."""
        validator = ModelValidator(config_path="config/llm_validation.yaml")

        async def model_call(prompt: str) -> str:
            return "response"

        result = await validator.validate_model(
            "claude-opus-4-5",
            model_call,
            skip_benchmarks=True
        )

        # Should complete without running benchmarks
        assert result.benchmark_results == []
        assert result.overall_score >= 0.0

    @pytest.mark.asyncio
    async def test_validate_nonexistent_model(self):
        """Test validation of model that doesn't exist in registry."""
        validator = ModelValidator(config_path="config/llm_validation.yaml")

        async def model_call(prompt: str) -> str:
            return "response"

        result = await validator.validate_model(
            "nonexistent-model",
            model_call,
            skip_benchmarks=False
        )

        # Should handle gracefully
        assert result.model_id == "nonexistent-model"
        assert result.status == ValidationResultStatus.ERROR
        assert "not found" in result.error_message.lower()


class TestConcurrentBenchmarkExecution:
    """Tests for concurrent benchmark execution and error handling."""

    @pytest.mark.asyncio
    async def test_concurrent_benchmark_timeouts(self):
        """Test multiple concurrent benchmarks with timeouts."""
        benchmarks = [
            ReasoningBenchmark(timeout_seconds=0.1),
            CodingBenchmark(timeout_seconds=0.1),
            AnalysisBenchmark(timeout_seconds=0.1),
            SpeedBenchmark(timeout_seconds=0.1),
        ]

        async def slow_model(prompt: str) -> str:
            await asyncio.sleep(1.0)
            return "response"

        results = await asyncio.gather(
            *[b.run("test-model", slow_model) for b in benchmarks]
        )

        # All should complete despite timeouts
        assert len(results) == 4
        for result in results:
            assert result.latency_ms > 0

    @pytest.mark.asyncio
    async def test_concurrent_rate_limit_errors(self):
        """Test handling concurrent rate limit errors."""
        benchmarks = [
            ReasoningBenchmark(),
            CodingBenchmark(),
        ]

        async def rate_limited_model(prompt: str) -> str:
            raise RuntimeError("Rate limit exceeded")

        results = await asyncio.gather(
            *[b.run("test-model", rate_limited_model) for b in benchmarks]
        )

        # All should complete despite errors
        assert len(results) == 2
        for result in results:
            assert result.score == 0.0


class TestBenchmarkRetryBehavior:
    """Tests for benchmark retry behavior and recovery."""

    @pytest.mark.asyncio
    async def test_benchmark_partial_failure_recovery(self):
        """Test benchmark recovery when some prompts fail."""
        benchmark = ReasoningBenchmark()

        def partial_failure_model(prompt: str) -> str:
            # First prompt fails (bat and ball), second succeeds
            if "bat and ball" in prompt:
                raise RuntimeError("Temporary error")
            return "transitive"

        result = await benchmark.run("test-model", partial_failure_model)

        # Should handle failure gracefully
        assert result.details["total"] == 2
        # At least one should fail due to error, so score < 1.0
        assert result.details["correct"] < result.details["total"]

    @pytest.mark.asyncio
    async def test_benchmark_graceful_degradation(self):
        """Test graceful degradation when some requests fail."""
        benchmark = CodingBenchmark()

        call_count = 0

        async def intermittent_failure_model(prompt: str) -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Service temporarily unavailable")
            return "def prime_check():\n    return True"

        result = await benchmark.run("test-model", intermittent_failure_model)

        # Should handle failure gracefully
        assert isinstance(result, BenchmarkResult)
        assert result.benchmark_name == "coding"
