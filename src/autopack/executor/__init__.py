"""
Executor subpackage for AutonomousExecutor refactor modules.

Autonomous Executor with Execution Hardening (BUILD-146)
See: docs/BUILD_HISTORY.md "Phase 6" Naming Clarification section
     docs/PHASE_NAMING.md for full clarification

Includes Phase 6 Execution Hardening work from BUILD-146:
- Failure recovery hardening
- Plan normalization
- Retry budget management

NOT to be confused with "Intentions Framework v2" from BUILD-178
(src/autopack/intention_anchor/) which covers intention anchoring
and pivot types for autonomous execution guidance.
"""

# IMP-MAINT-002: Circuit breaker extraction from autonomous_loop.py
from autopack.executor.circuit_breaker import (CircuitBreaker,
                                               CircuitBreakerOpenError,
                                               CircuitBreakerState,
                                               SOTDriftError)
# PR-EXE-6: Heuristic context loader extraction (IMP-REF-002)
from autopack.executor.context_loading_heuristic import (
    HeuristicContextLoader, get_default_priority_files)
# IMP-MAINT-001: Additional module extractions for executor split
from autopack.executor.doctor_facade import (DoctorFacade, DoctorState,
                                             HealthBudget)
# IMP-MAINT-001: Goal anchoring and SOT manager extraction
from autopack.executor.goal_anchoring import GoalAnchoringManager
from autopack.executor.learning_context_manager import LearningContextManager
from autopack.executor.run_lifecycle_manager import (ApiKeyValidationError,
                                                     RunLifecycleManager)
from autopack.executor.sot_manager import SOTManager
from autopack.executor.stale_phase_handler import StalePhaseHandler

__all__ = [
    "HeuristicContextLoader",
    "get_default_priority_files",
    "GoalAnchoringManager",
    "SOTManager",
    # IMP-MAINT-002: Circuit breaker exports
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "CircuitBreakerState",
    "SOTDriftError",
    # IMP-MAINT-001: New extraction modules
    "DoctorFacade",
    "DoctorState",
    "HealthBudget",
    "LearningContextManager",
    "RunLifecycleManager",
    "ApiKeyValidationError",
    "StalePhaseHandler",
]
