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
