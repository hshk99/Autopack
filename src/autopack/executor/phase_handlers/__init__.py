"""Phase handlers for special batched execution paths.

This package contains extracted phase handler bodies for special phases
that require custom batching or execution logic.

Migration approach (per PR-F+ plan):
- Move method bodies to top-level functions with signature:
  execute(executor, *, phase, attempt_index, allowed_paths) -> tuple[bool, str]
- Keep AutonomousExecutor methods as thin wrappers calling module functions.
- Keep phase_dispatch.SPECIAL_PHASE_METHODS pointing at wrapper method names.

Order of migration (least entangled → most):
1. batched_research_tracer_bullet
2. batched_research_gatherers_web_compilation
3. diagnostics batch handlers (one per PR)
"""
