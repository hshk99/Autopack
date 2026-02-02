"""Model discovery and validation system for generative models.

This module provides tools for discovering, validating, and evaluating
generative models from various registries and sources.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class ModelType(str, Enum):
    """Types of generative models."""

    REASONING = "reasoning"
    CODE = "code"
    MULTIMODAL = "multimodal"
    FAST = "fast"
    SPECIALIZED = "specialized"
    GENERAL = "general"


class HardwareRequirement(str, Enum):
    """Hardware categories for model deployment."""

    DATACENTER_GPU = "datacenter_gpu"
    SERVER_GPU = "server_gpu"
    CONSUMER_GPU = "consumer_gpu"
    CPU_ONLY = "cpu_only"
    EDGE_DEVICE = "edge_device"
    API_ONLY = "api_only"


@dataclass
class BenchmarkScore:
    """Benchmark performance metrics."""

    name: str
    score: float
    max_score: float = 100.0
    percentile: Optional[float] = None
    source: str = ""

    def normalized_score(self) -> float:
        """Return score normalized to 0-100 scale."""
        return (self.score / self.max_score) * 100.0


@dataclass
class InferenceMetrics:
    """Inference performance metrics."""

    time_to_first_token_ms: float
    tokens_per_second: float
    memory_bf16_gb: float
    quantization_friendly: bool = True


@dataclass
class HardwareCompatibility:
    """Hardware compatibility information."""

    hardware_type: HardwareRequirement
    min_vram_gb: float
    recommended_vram_gb: float
    supported_precisions: List[str] = field(default_factory=lambda: ["fp32"])
    max_batch_size: int = 1
    framework: str = ""
    notes: str = ""


@dataclass
class ModelMetadata:
    """Complete model metadata and validation results."""

    name: str
    provider: str
    model_type: ModelType
    release_date: str
    context_window: int
    parameters: Optional[str] = None
    description: str = ""

    # Performance metrics
    benchmarks: Dict[str, BenchmarkScore] = field(default_factory=dict)
    inference_metrics: Optional[InferenceMetrics] = None
    overall_score: float = 0.0

    # Reasoning capabilities
    reasoning_score: Optional[float] = None
    reasoning_strengths: List[str] = field(default_factory=list)
    reasoning_limitations: List[str] = field(default_factory=list)

    # Hardware compatibility
    hardware_options: List[HardwareCompatibility] = field(default_factory=list)

    # Community feedback
    community_sentiment: str = "neutral"
    community_stars: float = 3.0
    community_feedback_count: int = 0

    # Deployment info
    deployment_success_rate: float = 0.0
    recommended_use_cases: List[str] = field(default_factory=list)
    not_recommended_for: List[str] = field(default_factory=list)

    # Validation metadata
    validation_date: str = field(default_factory=lambda: datetime.now().isoformat())
    validation_confidence: str = "medium"

    def calculate_overall_score(self) -> float:
        """Calculate overall model score from benchmarks."""
        if not self.benchmarks:
            return 0.0

        scores = [b.normalized_score() for b in self.benchmarks.values()]
        return sum(scores) / len(scores) if scores else 0.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "name": self.name,
            "provider": self.provider,
            "type": self.model_type.value,
            "release_date": self.release_date,
            "context_window": self.context_window,
            "parameters": self.parameters,
            "benchmarks": {
                name: {
                    "score": score.score,
                    "max": score.max_score,
                    "normalized": score.normalized_score(),
                    "source": score.source,
                }
                for name, score in self.benchmarks.items()
            },
            "overall_score": self.overall_score,
            "reasoning_score": self.reasoning_score,
            "community_sentiment": self.community_sentiment,
            "community_stars": self.community_stars,
            "deployment_success_rate": self.deployment_success_rate,
            "validation_date": self.validation_date,
        }


class ModelRegistry:
    """Registry for discovered and validated models."""

    def __init__(self):
        """Initialize the model registry."""
        self.models: Dict[str, ModelMetadata] = {}
        self.validation_results: List[Dict[str, Any]] = []

    def register_model(self, metadata: ModelMetadata) -> None:
        """Register a validated model."""
        self.models[metadata.name] = metadata

    def get_model(self, name: str) -> Optional[ModelMetadata]:
        """Get model by name."""
        return self.models.get(name)

    def list_models(
        self,
        model_type: Optional[ModelType] = None,
        min_score: float = 0.0,
    ) -> List[ModelMetadata]:
        """List models with optional filtering."""
        models = list(self.models.values())

        if model_type:
            models = [m for m in models if m.model_type == model_type]

        if min_score > 0:
            models = [m for m in models if m.overall_score >= min_score]

        return sorted(models, key=lambda m: m.overall_score, reverse=True)

    def find_best_for_hardware(
        self,
        hardware: HardwareRequirement,
        min_performance: float = 0.0,
    ) -> List[ModelMetadata]:
        """Find best models for specific hardware."""
        compatible = []

        for model in self.models.values():
            if any(h.hardware_type == hardware for h in model.hardware_options):
                if model.overall_score >= min_performance:
                    compatible.append(model)

        return sorted(compatible, key=lambda m: m.overall_score, reverse=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert registry to dictionary."""
        return {
            "models": {name: m.to_dict() for name, m in self.models.items()},
            "total_models": len(self.models),
            "timestamp": datetime.now().isoformat(),
        }


class ModelValidator:
    """Validates model capabilities and compatibility."""

    def __init__(self):
        """Initialize the validator."""
        self.registry = ModelRegistry()
        self.validation_rules: Dict[str, callable] = {}

    def validate_benchmarks(self, metadata: ModelMetadata) -> bool:
        """Validate benchmark data."""
        if not metadata.benchmarks:
            return False

        for score in metadata.benchmarks.values():
            if score.score < 0 or score.score > score.max_score:
                return False

        return True

    def validate_hardware_compatibility(self, metadata: ModelMetadata) -> bool:
        """Validate hardware compatibility info."""
        if not metadata.hardware_options:
            return False

        for compat in metadata.hardware_options:
            if compat.min_vram_gb > compat.recommended_vram_gb:
                return False
            if compat.max_batch_size < 1:
                return False

        return True

    def validate_reasoning_assessment(self, metadata: ModelMetadata) -> bool:
        """Validate reasoning capability assessment."""
        if metadata.reasoning_score is None:
            return True  # Optional

        if metadata.reasoning_score < 0 or metadata.reasoning_score > 100:
            return False

        return True

    def validate_community_feedback(self, metadata: ModelMetadata) -> bool:
        """Validate community feedback data."""
        if metadata.community_stars < 0 or metadata.community_stars > 5:
            return False

        if metadata.community_feedback_count < 0:
            return False

        return True

    def validate_model(self, metadata: ModelMetadata) -> tuple[bool, List[str]]:
        """Validate complete model metadata.

        Returns:
            Tuple of (is_valid, list_of_errors)
        """
        errors = []

        # Validate required fields
        if not metadata.name or not metadata.provider:
            errors.append("Missing required fields: name or provider")

        if metadata.context_window < 1:
            errors.append("Invalid context window")

        # Run validation checks
        if not self.validate_benchmarks(metadata):
            errors.append("Benchmark validation failed")

        if not self.validate_hardware_compatibility(metadata):
            errors.append("Hardware compatibility validation failed")

        if not self.validate_reasoning_assessment(metadata):
            errors.append("Reasoning assessment validation failed")

        if not self.validate_community_feedback(metadata):
            errors.append("Community feedback validation failed")

        # Calculate overall score if not set
        if metadata.overall_score == 0.0:
            metadata.overall_score = metadata.calculate_overall_score()

        return (len(errors) == 0, errors)

    def register_and_validate(self, metadata: ModelMetadata) -> tuple[bool, List[str]]:
        """Validate and register a model."""
        is_valid, errors = self.validate_model(metadata)

        if is_valid:
            self.registry.register_model(metadata)

        return (is_valid, errors)


class ModelDiscoverySystem:
    """Discovers models from various registries."""

    def __init__(self):
        """Initialize the discovery system."""
        self.discovered_models: List[Dict[str, Any]] = []
        self.discovery_metadata = {
            "scan_date": datetime.now().isoformat(),
            "registries_scanned": [],
            "total_models_found": 0,
        }

    def discover_from_huggingface(self, filters: Optional[Dict] = None) -> List[Dict]:
        """Discover models from HuggingFace Hub.

        Args:
            filters: Optional filters (e.g., task, license)

        Returns:
            List of discovered model metadata
        """
        # This would typically fetch from HuggingFace API
        # For now, return structure
        return []

    def discover_from_ollama(self) -> List[Dict]:
        """Discover models from Ollama registry."""
        # This would fetch from Ollama registry
        return []

    def discover_from_openrouter(self) -> List[Dict]:
        """Discover models from OpenRouter."""
        # This would fetch from OpenRouter API
        return []

    def scan_registries(self) -> None:
        """Scan all configured registries."""
        sources = [
            ("huggingface", self.discover_from_huggingface()),
            ("ollama", self.discover_from_ollama()),
            ("openrouter", self.discover_from_openrouter()),
        ]

        for source_name, models in sources:
            self.discovered_models.extend(models)
            self.discovery_metadata["registries_scanned"].append(source_name)

        self.discovery_metadata["total_models_found"] = len(self.discovered_models)

    def get_discovered_models(self) -> List[Dict]:
        """Get list of discovered models."""
        return self.discovered_models


def create_example_model() -> ModelMetadata:
    """Create an example model for testing."""
    return ModelMetadata(
        name="Claude 3.5 Sonnet",
        provider="Anthropic",
        model_type=ModelType.REASONING,
        release_date="2024-10",
        context_window=200000,
        parameters="Unknown (estimated 100B+)",
        description="Advanced reasoning model with extended context",
        benchmarks={
            "mmlu": BenchmarkScore("mmlu", 95.0, source="anthropic"),
            "mtbench": BenchmarkScore("mtbench", 9.2, max_score=10.0, source="lmsys"),
            "humaneval": BenchmarkScore("humaneval", 92.0, source="anthropic"),
        },
        inference_metrics=InferenceMetrics(
            time_to_first_token_ms=400,
            tokens_per_second=60,
            memory_bf16_gb=150,
            quantization_friendly=False,
        ),
        reasoning_score=98.0,
        reasoning_strengths=[
            "Exceptional reasoning",
            "Code generation",
            "Long context understanding",
        ],
        hardware_options=[
            HardwareCompatibility(
                hardware_type=HardwareRequirement.API_ONLY,
                min_vram_gb=0,
                recommended_vram_gb=0,
                supported_precisions=["N/A"],
                framework="API",
            )
        ],
        community_sentiment="excellent",
        community_stars=4.8,
        community_feedback_count=500,
        deployment_success_rate=0.98,
        recommended_use_cases=[
            "Complex analysis",
            "Multi-step reasoning",
            "Production systems",
        ],
        validation_confidence="high",
    )


if __name__ == "__main__":
    # Example usage
    validator = ModelValidator()

    # Create and validate example model
    model = create_example_model()
    model.overall_score = model.calculate_overall_score()

    is_valid, errors = validator.register_and_validate(model)

    if is_valid:
        print(f"✓ Model '{model.name}' validated and registered")
        print(f"  Overall Score: {model.overall_score:.1f}")
    else:
        print(f"✗ Validation failed for '{model.name}':")
        for error in errors:
            print(f"  - {error}")

    # List registered models
    models = validator.registry.list_models()
    print(f"\nRegistered models: {len(models)}")
    for m in models:
        print(f"  - {m.name}: {m.overall_score:.1f}")
