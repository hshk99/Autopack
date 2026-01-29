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

# PR-EXE-6: Heuristic context loader extraction (IMP-REF-002)
from autopack.executor.context_loading_heuristic import (
    HeuristicContextLoader,
    get_default_priority_files,
)

# IMP-MAINT-001: Goal anchoring and SOT manager extraction
from autopack.executor.goal_anchoring import GoalAnchoringManager
from autopack.executor.sot_manager import SOTManager

__all__ = [
    "HeuristicContextLoader",
    "get_default_priority_files",
    "GoalAnchoringManager",
    "SOTManager",
]
