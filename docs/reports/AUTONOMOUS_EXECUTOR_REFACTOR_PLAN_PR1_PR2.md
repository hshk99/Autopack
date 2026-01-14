## Autonomous Executor Refactor Plan (PR1 + PR2, seam-first, low-risk)

**Target file**: `src/autopack/autonomous_executor.py` (currently ~11k LOC)

**Goal**: reduce development slowness (merge conflicts + navigation + cognitive load) by extracting **seams** without behavior change.

**Strategy**: strangler façade
- Keep `AutonomousExecutor` as the public orchestrator initially.
- Extract small, high-churn blocks into `src/autopack/executor/*`.
- Add contract tests before moving large bodies.

---

## Direction (explicit decisions)

- **No behavior change** in PR1/PR2.
- **No moving of the large handler bodies** in PR1/PR2; only routing and policy seams.
- Use **tracked-code contracts** (unit tests) rather than runtime integration tests for the first steps.
- Avoid new import cycles: new `autopack.executor.*` modules must not import `autonomous_executor.py`.

---

## Existing seams (verified in code)

- **Special phase dispatch ladder** in `_execute_phase_with_recovery`:
  - phase ids routed to specialized batching methods:
    - `research-tracer-bullet`
    - `research-gatherers-web-compilation`
    - `diagnostics-handoff-bundle`
    - `diagnostics-cursor-prompt`
    - `diagnostics-second-opinion-triage`
    - `diagnostics-deep-retrieval`
    - `diagnostics-iteration-loop`

- **Context loading policy** in `_load_repository_context`:
  - scope precedence over targeted loaders
  - targeted loaders for templates / frontend / docker
  - fallback heuristic loader

---

## Module tree to introduce (PR1/PR2 only)

Add:
- `src/autopack/executor/phase_dispatch.py`
- `src/autopack/executor/context_loading.py`

Add tests:
- `tests/unit/test_executor_phase_dispatch_contract.py`
- `tests/unit/test_executor_context_loading_precedence.py`

---

## PR1: Extract special phase dispatch registry (minimal diff)

### Why PR1 is safe
- The handler bodies stay in `AutonomousExecutor`.
- We only replace the `if phase_id == ...` ladder with a registry lookup + `getattr`.
- Failure mode is explicit: if registry references a missing method, raise a clear error.

### Files changed in PR1
- **Add** `src/autopack/executor/phase_dispatch.py`
- **Edit** `src/autopack/autonomous_executor.py` (only `_execute_phase_with_recovery` special-case ladder block)
- **Add** `tests/unit/test_executor_phase_dispatch_contract.py`

### PR1 exact patch (apply as-is)

```diff
diff --git a/src/autopack/executor/phase_dispatch.py b/src/autopack/executor/phase_dispatch.py
new file mode 100644
index 00000000..11111111
--- /dev/null
+++ b/src/autopack/executor/phase_dispatch.py
@@
+\"\"\"Phase dispatch helpers for AutonomousExecutor.
+
+Goal:
+- Reduce merge conflicts and cognitive load in `autonomous_executor.py` by moving
+  the special-case phase-id ladder into a small registry.
+
+Design (PR1):
+- Keep it extremely small and non-invasive.
+- The registry returns *method names* that already exist on AutonomousExecutor.
+  This avoids moving large handler bodies in the first refactor PR.
+
+Follow-ups:
+- Migrate method-name mapping to real handler objects under `executor/phase_handlers/`.
+\"\"\"
+
+from __future__ import annotations
+
+from typing import Optional
+
+SPECIAL_PHASE_METHODS: dict[str, str] = {
+    \"research-tracer-bullet\": \"_execute_research_tracer_bullet_batched\",
+    \"research-gatherers-web-compilation\": \"_execute_research_gatherers_web_compilation_batched\",
+    \"diagnostics-handoff-bundle\": \"_execute_diagnostics_handoff_bundle_batched\",
+    \"diagnostics-cursor-prompt\": \"_execute_diagnostics_cursor_prompt_batched\",
+    \"diagnostics-second-opinion-triage\": \"_execute_diagnostics_second_opinion_batched\",
+    \"diagnostics-deep-retrieval\": \"_execute_diagnostics_deep_retrieval_batched\",
+    \"diagnostics-iteration-loop\": \"_execute_diagnostics_iteration_loop_batched\",
+}
+
+
+def resolve_special_phase_method(phase_id: Optional[str]) -> Optional[str]:
+    \"\"\"Return AutonomousExecutor method name for special phase_id, else None.\"\"\"
+    if not phase_id:
+        return None
+    return SPECIAL_PHASE_METHODS.get(phase_id)
+
diff --git a/src/autopack/autonomous_executor.py b/src/autopack/autonomous_executor.py
index XXXXXXXX..YYYYYYYY 100644
--- a/src/autopack/autonomous_executor.py
+++ b/src/autopack/autonomous_executor.py
@@
     def _execute_phase_with_recovery(
         self, phase: Dict, attempt_index: int = 0, allowed_paths: Optional[List[str]] = None
     ) -> Tuple[bool, str]:
         \"\"\"Inner phase execution with error handling and model escalation support\"\"\"
         phase_id = phase.get(\"phase_id\")

         try:
-            # Chunk 0 batching (research-tracer-bullet) is handled by a specialized executor path
-            # to reduce patch size and avoid incomplete/truncated patches.
-            if phase_id == \"research-tracer-bullet\":
-                return self._execute_research_tracer_bullet_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Chunk 2B batching (research-gatherers-web-compilation) is handled by a specialized executor path
-            # to reduce patch size and avoid incomplete/truncated patches (common for tests/docs).
-            if phase_id == \"research-gatherers-web-compilation\":
-                return self._execute_research_gatherers_web_compilation_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Diagnostics parity followups create multiple files (code + tests + docs) and
-            # commonly hit truncation/malformed-diff convergence failures when generated as one patch.
-            # Use in-phase batching (like Chunk 0 / Chunk 2B) to reduce patch size and tighten manifest gates.
-
-            # Followup-1: handoff-bundle (4 files: 2 code + 1 test + 1 doc)
-            if phase_id == \"diagnostics-handoff-bundle\":
-                return self._execute_diagnostics_handoff_bundle_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Followup-2: cursor-prompt (4 files: 2 code + 1 test + 1 doc)
-            if phase_id == \"diagnostics-cursor-prompt\":
-                return self._execute_diagnostics_cursor_prompt_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Followup-3: second-opinion (3 files: 1 code + 1 test + 1 doc)
-            if phase_id == \"diagnostics-second-opinion-triage\":
-                return self._execute_diagnostics_second_opinion_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Followup-7: deep-retrieval (5 files: 2 code + 2 tests + 1 doc)
-            if phase_id == \"diagnostics-deep-retrieval\":
-                return self._execute_diagnostics_deep_retrieval_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
-
-            # Followup-8: iteration-loop (5 files: 2 code + 2 tests + 1 doc)
-            if phase_id == \"diagnostics-iteration-loop\":
-                return self._execute_diagnostics_iteration_loop_batched(
-                    phase=phase,
-                    attempt_index=attempt_index,
-                    allowed_paths=allowed_paths,
-                )
+            # Special-case phase handlers (in-phase batching) are routed via a tiny registry
+            # to reduce merge conflicts in this file.
+            from autopack.executor.phase_dispatch import resolve_special_phase_method
+
+            special_method_name = resolve_special_phase_method(phase_id)
+            if special_method_name:
+                handler = getattr(self, special_method_name, None)
+                if handler is None:
+                    raise RuntimeError(
+                        f\"Phase '{phase_id}' mapped to missing handler '{special_method_name}'\"
+                    )
+                return handler(
+                    phase=phase,
+                    attempt_index=attempt_index,
+                    allowed_paths=allowed_paths,
+                )

             # Step 1: Execute with Builder using LlmService
             logger.info(f\"[{phase_id}] Step 1/4: Generating code with Builder (via LlmService)...\")

diff --git a/tests/unit/test_executor_phase_dispatch_contract.py b/tests/unit/test_executor_phase_dispatch_contract.py
new file mode 100644
index 00000000..22222222
--- /dev/null
+++ b/tests/unit/test_executor_phase_dispatch_contract.py
@@
+from __future__ import annotations
+
+from autopack.executor.phase_dispatch import SPECIAL_PHASE_METHODS, resolve_special_phase_method
+
+
+def test_phase_dispatch_registry_has_expected_special_phases() -> None:
+    expected = {
+        \"research-tracer-bullet\",
+        \"research-gatherers-web-compilation\",
+        \"diagnostics-handoff-bundle\",
+        \"diagnostics-cursor-prompt\",
+        \"diagnostics-second-opinion-triage\",
+        \"diagnostics-deep-retrieval\",
+        \"diagnostics-iteration-loop\",
+    }
+    assert expected.issubset(set(SPECIAL_PHASE_METHODS.keys()))
+
+
+def test_resolve_special_phase_method_returns_none_for_unknown() -> None:
+    assert resolve_special_phase_method(\"not-a-phase\") is None
+
+
+def test_resolve_special_phase_method_returns_method_name() -> None:
+    assert (
+        resolve_special_phase_method(\"research-tracer-bullet\")
+        == \"_execute_research_tracer_bullet_batched\"
+    )
```

### PR1 test commands
- `pytest -q tests/unit/test_executor_phase_dispatch_contract.py`
- `ruff check src/ tests/`
- `black --check src/ tests/`

---

## PR2: Extract context-loading *policy* seam (scope precedence) with a stable wrapper

### Why PR2 is safe
- We keep the huge heuristic loader in-place for now.
- We only extract *selection logic* (scope precedence + pattern-based routing) into a small module.
- We add a unit test for the most important invariant: **scope overrides targeted**.

### Files changed in PR2
- **Add** `src/autopack/executor/context_loading.py`
- **Edit** `src/autopack/autonomous_executor.py`
  - add a thin wrapper call in `_load_repository_context`
  - move the existing heuristic loader body to `_load_repository_context_heuristic` (mechanical move)
- **Add** `tests/unit/test_executor_context_loading_precedence.py`

### PR2 exact patch (apply as-is)

```diff
diff --git a/src/autopack/executor/context_loading.py b/src/autopack/executor/context_loading.py
new file mode 100644
index 00000000..33333333
--- /dev/null
+++ b/src/autopack/executor/context_loading.py
@@
+\"\"\"Context loading policy for AutonomousExecutor.
+
+Goal (PR2):
+- Keep the *policy* (scope precedence + pattern targeting selection) in a small,
+  testable module to reduce merge conflicts in `autonomous_executor.py`.
+
+Non-goal (PR2):
+- Move the full heuristic loader implementation out of the executor yet.
+
+Design:
+- Expects an executor object with:
+  - _load_scoped_context
+  - _load_targeted_context_for_templates
+  - _load_targeted_context_for_frontend
+  - _load_targeted_context_for_docker
+  - _load_repository_context_heuristic (fallback)
+\"\"\"
+
+from __future__ import annotations
+
+import logging
+from typing import Any
+
+logger = logging.getLogger(__name__)
+
+
+def load_repository_context(executor: Any, phase: dict) -> dict:
+    phase_id = phase.get(\"phase_id\", \"\")
+    phase_name = (phase.get(\"name\", \"\") or \"\").lower()
+    phase_desc = (phase.get(\"description\", \"\") or \"\").lower()
+    task_category = phase.get(\"task_category\", \"\")
+
+    scope_config = phase.get(\"scope\")
+    if scope_config and scope_config.get(\"paths\"):
+        logger.info(f\"[{phase_id}] Using scope-aware context (overrides targeted context)\")
+        return executor._load_scoped_context(phase, scope_config)
+
+    if \"template\" in phase_name and (\"country\" in phase_desc or \"template\" in phase_id):
+        logger.info(f\"[{phase_id}] Using targeted context for country template phase\")
+        return executor._load_targeted_context_for_templates(phase)
+
+    if task_category == \"frontend\" or \"frontend\" in phase_name:
+        logger.info(f\"[{phase_id}] Using targeted context for frontend phase\")
+        return executor._load_targeted_context_for_frontend(phase)
+
+    if \"docker\" in phase_name or task_category == \"deployment\":
+        logger.info(f\"[{phase_id}] Using targeted context for docker/deployment phase\")
+        return executor._load_targeted_context_for_docker(phase)
+
+    return executor._load_repository_context_heuristic(phase)
+
diff --git a/src/autopack/autonomous_executor.py b/src/autopack/autonomous_executor.py
index AAAAAAAA..BBBBBBBB 100644
--- a/src/autopack/autonomous_executor.py
+++ b/src/autopack/autonomous_executor.py
@@
     def _load_repository_context(self, phase: Dict) -> Dict:
         \"\"\"Load repository files for Claude Builder context
@@
-        import subprocess
-        import re
-
-        # NEW: Phase 2 - Smart context reduction for known phase patterns
-        # This reduces input token usage and gives more room for output tokens
-        phase_id = phase.get(\"phase_id\", \"\")
-        phase_name = phase.get(\"name\", \"\").lower()
-        phase_desc = phase.get(\"description\", \"\").lower()
-        task_category = phase.get(\"task_category\", \"\")
-
-        # Scope MUST take precedence over targeted context.
-        scope_config = phase.get(\"scope\")
-        if scope_config and scope_config.get(\"paths\"):
-            logger.info(f\"[{phase_id}] Using scope-aware context (overrides targeted context)\")
-            return self._load_scoped_context(phase, scope_config)
-
-        # Pattern 1: Country template phases (UK, CA, AU templates)
-        if \"template\" in phase_name and (\"country\" in phase_desc or \"template\" in phase_id):
-            logger.info(f\"[{phase_id}] Using targeted context for country template phase\")
-            return self._load_targeted_context_for_templates(phase)
-
-        # Pattern 2: Frontend-only phases
-        if task_category == \"frontend\" or \"frontend\" in phase_name:
-            logger.info(f\"[{phase_id}] Using targeted context for frontend phase\")
-            return self._load_targeted_context_for_frontend(phase)
-
-        # Pattern 3: Docker/deployment phases
-        if \"docker\" in phase_name or task_category == \"deployment\":
-            logger.info(f\"[{phase_id}] Using targeted context for docker/deployment phase\")
-            return self._load_targeted_context_for_docker(phase)
-
-        # Fallback: Original heuristic-based loading for backward compatibility
-        workspace = Path(self.workspace)
+        from autopack.executor.context_loading import load_repository_context
+        return load_repository_context(self, phase)
+
+    def _load_repository_context_heuristic(self, phase: Dict) -> Dict:
+        \"\"\"Legacy heuristic loader (moved from _load_repository_context in PR2).\"\"\"
+        import subprocess
+        import re
+        phase_id = phase.get(\"phase_id\", \"\")
+        workspace = Path(self.workspace)
         loaded_paths = set()  # Track loaded paths to avoid duplicates
         existing_files = {}  # Final output format
         max_files = 40  # Increased limit to accommodate recently modified files

diff --git a/tests/unit/test_executor_context_loading_precedence.py b/tests/unit/test_executor_context_loading_precedence.py
new file mode 100644
index 00000000..44444444
--- /dev/null
+++ b/tests/unit/test_executor_context_loading_precedence.py
@@
+from __future__ import annotations
+
+from autopack.executor.context_loading import load_repository_context
+
+
+class FakeExecutor:
+    def __init__(self) -> None:
+        self.scoped_called = False
+        self.frontend_called = False
+
+    def _load_scoped_context(self, phase: dict, scope_config: dict) -> dict:
+        self.scoped_called = True
+        return {\"existing_files\": {\"_sentinel\": \"scoped\"}}
+
+    def _load_targeted_context_for_templates(self, phase: dict) -> dict:
+        raise AssertionError(\"templates loader should not be called when scope.paths exists\")
+
+    def _load_targeted_context_for_frontend(self, phase: dict) -> dict:
+        self.frontend_called = True
+        raise AssertionError(\"frontend loader should not be called when scope.paths exists\")
+
+    def _load_targeted_context_for_docker(self, phase: dict) -> dict:
+        raise AssertionError(\"docker loader should not be called when scope.paths exists\")
+
+    def _load_repository_context_heuristic(self, phase: dict) -> dict:
+        raise AssertionError(\"heuristic loader should not be called when scope.paths exists\")
+
+
+def test_scope_precedence_over_targeted_loaders() -> None:
+    ex = FakeExecutor()
+    phase = {
+        \"phase_id\": \"any\",
+        \"name\": \"Frontend phase\",
+        \"description\": \"\",
+        \"task_category\": \"frontend\",
+        \"scope\": {\"paths\": [\"src/autopack/something.py\"]},
+    }
+    ctx = load_repository_context(ex, phase)
+    assert ex.scoped_called is True
+    assert ex.frontend_called is False
+    assert ctx[\"existing_files\"][\"_sentinel\"] == \"scoped\"
```

### PR2 test commands
- `pytest -q tests/unit/test_executor_context_loading_precedence.py`
- `ruff check src/ tests/`
- `black --check src/ tests/`

---

## Known ambiguities + how to resolve them (explicit)

1) **Should PR2 move the full heuristic loader out of `autonomous_executor.py`?**
   - **Decision**: No. PR2 only extracts routing policy; keep heuristic body in-place as `_load_repository_context_heuristic` to minimize churn.

2) **Should PR1 use handler objects instead of method-name strings?**
   - **Decision**: No for PR1. Use method-name strings to avoid moving huge method bodies. Upgrade to handler objects later.

3) **Should these tests be integration tests against a real workspace?**
   - **Decision**: No for PR1/PR2. Use unit tests that assert invariants (dispatch mapping + scope precedence).

4) **Risk of circular imports**
   - **Decision**: keep `autopack.executor.*` “leafy.” They must not import `autonomous_executor.py`.
