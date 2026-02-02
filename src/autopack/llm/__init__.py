"""LLM integration package for Autopack.

This package contains extracted modules from anthropic_clients.py as part of
the god file refactoring (Item 1.1 - PR-LLM-1).

Current modules:
- providers: Provider-specific transport wrappers (Anthropic, OpenAI, etc.)
- client_resolution: Client resolution and provider fallback logic (PR-SVC-1)
- model_registry: Central model registry with capability metadata (IMP-LLM-001)
- model_validator: Model capability validation and benchmarking (IMP-LLM-001)
- routing_engine: Intelligent model routing and fallback (IMP-LLM-001)

Future modules (to be extracted):
- prompts: System and user prompt builders
- parsers: Response parsing for various output formats (JSON, NDJSON, diff)
- diff_generator: Unified diff generation utilities

Usage:
    from autopack.llm.providers import AnthropicTransport
    from autopack.llm.client_resolution import resolve_client_and_model
    from autopack.llm import get_model_registry, get_routing_engine
"""

# Import client resolution functions (PR-SVC-1)
from autopack.llm.client_resolution import (  # noqa: F401
    resolve_auditor_client,
    resolve_builder_client,
    resolve_client_and_model,
)

# Import LLM auditor (IMP-LLM-002)
from autopack.llm.llm_auditor import (  # noqa: F401
    AuditFlag,
    AuditLogEntry,
    AuditResult,
    ExecutionMetrics,
    LLMAuditor,
    ModelPerformanceStats,
    OverrideReason,
    OverrideSuggestion,
    RoutingReport,
    get_llm_auditor,
)

# Import model registry (IMP-LLM-001)
from autopack.llm.model_registry import (  # noqa: F401
    ModelCapabilities,
    ModelCost,
    ModelHealth,
    ModelInfo,
    ModelLimits,
    ModelRegistry,
    ModelStatus,
    ModelTier,
    get_model_registry,
)

# Import model validator (IMP-LLM-001)
from autopack.llm.model_validator import (  # noqa: F401
    BenchmarkResult,
    BenchmarkTest,
    ModelValidator,
    ValidationResult,
    ValidationResultStatus,
    get_model_validator,
)

# Import prompt builders (PR-LLM-2)
from autopack.llm.prompts.anthropic_builder_prompts import (  # noqa: F401
    build_minimal_system_prompt,
    build_system_prompt,
    build_user_prompt,
)

# Import routing engine (IMP-LLM-001)
from autopack.llm.routing_engine import (  # noqa: F401
    ComplexityEstimate,
    FallbackChain,
    FallbackTrigger,
    RoutingDecision,
    RoutingEngine,
    RoutingRule,
    RoutingStrategy,
    get_routing_engine,
)

__all__ = [
    # Client resolution
    "resolve_client_and_model",
    "resolve_builder_client",
    "resolve_auditor_client",
    # Prompt builders
    "build_system_prompt",
    "build_minimal_system_prompt",
    "build_user_prompt",
    # Model registry (IMP-LLM-001)
    "ModelCapabilities",
    "ModelCost",
    "ModelHealth",
    "ModelInfo",
    "ModelLimits",
    "ModelRegistry",
    "ModelStatus",
    "ModelTier",
    "get_model_registry",
    # Model validator (IMP-LLM-001)
    "BenchmarkResult",
    "BenchmarkTest",
    "ModelValidator",
    "ValidationResult",
    "ValidationResultStatus",
    "get_model_validator",
    # Routing engine (IMP-LLM-001)
    "ComplexityEstimate",
    "FallbackChain",
    "FallbackTrigger",
    "RoutingDecision",
    "RoutingEngine",
    "RoutingRule",
    "RoutingStrategy",
    "get_routing_engine",
    # LLM auditor (IMP-LLM-002)
    "AuditFlag",
    "AuditLogEntry",
    "AuditResult",
    "ExecutionMetrics",
    "LLMAuditor",
    "ModelPerformanceStats",
    "OverrideReason",
    "OverrideSuggestion",
    "RoutingReport",
    "get_llm_auditor",
]
