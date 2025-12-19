# Research System Capability Gap Analysis (Second Opinion)
**Date**: 2025-12-19  
**Analyst**: Cursor (second opinion)  
**Context**: Cross-check the planned Research System chunks in `.autonomous_runs/file-organizer-app-v1/archive/research/active/requirements/` against the **actual, current** Autopack repo state.

---

## Executive Summary

**TL;DR (updated)**: Autopack now has **system-level convergence support** for the remaining research phases (Chunk 2B–5) that previously failed deterministically:
- Chunk 2B: in-phase batching prevents oversized/truncated patches
- Chunk 4: protected-path isolation no longer blocks required `src/autopack/*` integration subtrees
- Chunk 5: deliverables/manifest logic now supports annotated + directory-style deliverables

**Overall Assessment**: **🟢 EXECUTOR-CAPABLE (CONVERGENCE UNBLOCKED)** — the executor/validation/apply pipeline is now capable of converging through Chunk 5 without the earlier deterministic blockers. Remaining concerns are mostly **deliverable correctness/quality**, not system mechanics.

**Confidence Level**: ~85% (based on post-fix runs completing Chunk 2B/4/5 and direct inspection of the apply/validation gates; baseline CI green-ness is still not guaranteed).

---

## What I Checked (Evidence-Based)

### 1) Requirements sanity check (planned phases)
The planned chunks are defined by:
- `chunk0-tracer-bullet.yaml`
- `chunk1a-foundation-orchestrator.yaml`
- `chunk1b-foundation-intent-discovery.yaml`
- `chunk2a-gatherers-social.yaml`
- `chunk2b-gatherers-web-compilation.yaml`
- `chunk3-meta-analysis.yaml`
- `chunk4-integration.yaml`
- `chunk5-testing-polish.yaml`

### 2) Current repo “research system” footprint
Autopack currently contains **multiple parallel research implementations**:

- **`src/autopack/research/…`**: research “core” namespace (models/validators/tracer_bullet/evaluation/gatherers).
- **`src/research/…`**: separate research implementation (intent/discovery/gatherers/security).
- **Top-level prototypes**: `tracer_bullet/` and `research_tracer/` directories.

This is important because the requirements assume a single coherent module tree; right now it’s split and inconsistent.

---

## Key Findings (Issues / Concerns)

### 1) Requirements path inconsistency (still a risk; now less likely to hard-block)
The requirements are not consistent about where the research system “lives”:

- **Chunk 0 + Chunk 1A** deliverables target `src/autopack/research/...`
- **Chunks 1B / 2A / 2B / 3** deliverables target `src/research/...`
- **Chunk 4** returns to `src/autopack/...` (and mostly *outside* `src/autopack/research/`)

Even if Autopack can generate code, this mismatch will cause:
- duplicated implementations,
- inconsistent imports,
- higher chance of deliverables/manifest failures,
- and hard-to-debug runtime behavior.

**Recommended requirement revision**: pick a single root (`src/autopack/research/...` is the safer choice given Autopack’s isolation rules) and update all chunk YAML deliverables accordingly.

### 2) Baseline research test health / CI may still be failing (quality risk, not necessarily a system blocker)
Running the existing research test suite shows the current implementation is **not in a passing state**:

- `pytest tests/research/test_orchestrator.py` fails with `NameError: ResearchStage is not defined` (orchestrator bug).
- `pytest tests/research` fails at collection with missing dependencies and import issues:
  - `ModuleNotFoundError: No module named 'bs4'`
  - `ModuleNotFoundError: No module named 'praw'`
  - `ModuleNotFoundError: No module named 'compiler'` (bad import in evaluator)
  - `ModuleNotFoundError: No module named 'src.autopack.research.evaluation.gatherer'` (missing module)
  - `import file mismatch` due to duplicate test module basenames (`test_orchestrator.py` collision)

**Updated implication**:
- These failures primarily impact **quality gates / CI outcomes**, not the executor’s ability to generate/apply deliverables.
- Expect “CI exit code 2 (collection/import errors)” to still happen until deliverables themselves are corrected and dependencies are aligned. This is usually **deliverable correctness**, not a convergence mechanism bug.

### 3) Missing declared dependencies for required gatherers (still a practical runtime blocker if tests are enforced)
The requirements explicitly rely on packages like `requests`, `beautifulsoup4`, `praw`, etc.

However, current dependency declarations (`requirements.txt` / `pyproject.toml`) do **not** include:
- `requests`
- `beautifulsoup4` / `bs4`
- `praw`
- `aiohttp`
- `tenacity`
- `readability-lxml`
- `fuzzywuzzy`
- `reppy`
- `jinja2`
- `numpy`

And the current code *does* import at least `requests`, `bs4`, and `praw` in `src/research/...` and `src/autopack/research/...`.

**Implication**: even if phases generate code successfully, execution + tests will fail unless dependencies are added and pinned.

### 4) Chunk 4 protected-path isolation (was a hard blocker; now fixed)
**Status**: ✅ Resolved as a system-level convergence blocker.

Autopack still protects `src/autopack/` broadly, but now explicitly allowlists the narrow safe subtrees required by Chunk 4:
- `src/autopack/integrations/`
- `src/autopack/phases/`
- `src/autopack/autonomous/`
- `src/autopack/workflow/`

**Implication**: Chunk 4 is now autonomously self-implementable under normal project runs (without unlocking all of `src/autopack/`).

### 5) Phase state mismatch: requirements expect `AWAITING_REVIEW`, code uses `GATE`
Chunk 4 requirements reference `AWAITING_REVIEW`. Current `PhaseState` in `src/autopack/models.py` does not include that state; it uses `GATE`.

That’s not necessarily fatal (you can map “awaiting review” behavior to `GATE`), but:
- the requirements should be aligned with current state machine **or**
- you’ll need to modify the enum and DB behavior (which again is under protected paths).

### 6) CLI mismatch: requirements say `autopack research ...`, repo does not expose that CLI
There is a click-based module at `src/autopack/cli/commands/research.py`, but:
- the “main” CLI at `src/autopack/cli.py` is an argparse CLI for tidy scripts,
- there are no `entry_points`/`console_scripts` wired in `pyproject.toml`,
- and `src/autopack/__main__.py` is not a CLI entrypoint for research.

**Implication**: chunk requirements that hinge on `autopack research ...` will not work until the CLI entrypoint strategy is clarified and implemented.

---

## Chunk-by-Chunk “Can Autopack Implement This Itself?” Assessment

### Chunk 0 (Tracer Bullet)
**Capability**: **🟡 Possible**, but current state indicates significant cleanup needed first.  
**Concern**: There is already tracer bullet code in multiple places; tests and imports currently break; dependencies missing.

### Chunk 1A (Orchestrator + Evidence Model)
**Capability**: **🟡 Possible**, but current orchestrator implementation is failing basic tests and needs foundational fixes.

### Chunk 1B / 2A / 2B (Intent/Discovery/Gatherers/Web)
**Capability**: **🟡 Possible**, but depends on:
- adding dependencies,
- fixing import/package hygiene,
- and aligning deliverable paths (currently split between `src/autopack/research` and `src/research`).

### Chunk 3 (Meta-analysis / Decision Frameworks)
**Capability**: **🟡 Implementable**, but still requires explicit formula ownership + gold tests (the original report’s warning stands).  
**Additional concern**: none of the decision framework modules currently exist in the expected locations; this is net-new work.

### Chunk 4 (Integration)
**Capability**: **🟢 Now autonomously self-implementable under default constraints**.  
**Reason**: the required safe `src/autopack/*` subtrees are now allowlisted (without unlocking all of `src/autopack/`).

### Chunk 5 (Testing & Polish)
**Capability**: **🟢 Convergence-capable**, but “100+ tests / 80% coverage” remains a deliverable-quality challenge.  
**Current concern**: requirements include directory-style deliverables (e.g. `tests/research/unit/`), and baseline test/dep hygiene still matters for “coverage” claims to be meaningful.

---

## Recommended Updates to the Plan / Requirements (to make autonomous execution realistic)

### 1) Unify deliverable roots
Pick one of:
- **Option A (recommended)**: move everything under `src/autopack/research/...` and adjust chunk YAMLs.
- Option B: keep `src/research/...` but then explicitly treat it as a supported, first-class package and ensure isolation/manifest rules won’t fight it.

### 2) Explicitly handle Chunk 4 isolation
**Status**: Already handled in the codebase via narrow allowlisting of required subtrees.

### 3) Add/lock dependencies
Before running research chunks that import external libs, add the required packages and pin them (at least in `requirements.txt` and ideally also `pyproject.toml`).

### 4) Fix test/package hygiene early
Before treating Chunk 0 as a feasibility gate, ensure:
- no duplicate test module basenames in the same package namespace,
- import paths are consistent (`src.autopack...` vs `autopack...` vs `research...`),
- evaluation modules import their siblings correctly.

---

## Bottom Line

Autopack’s executor and safety scaffolding are strong, and the most important “can it converge at all?” blockers have been addressed:

- ✅ **Resolved blocker**: Chunk 4 protected-path apply rejection.
- ✅ **Resolved blocker**: Chunk 2B patch truncation / malformed new-file diffs via batching.
- ✅ **Resolved blocker**: Chunk 5 annotated + directory-style deliverables causing deterministic validation failures.
- **Remaining quality risks**: dependency declarations, import hygiene, and the real ability to hit “coverage” targets.

**Revised overall verdict**: **🟢 convergence-capable**, with remaining work largely in deliverable correctness and repo hygiene.

---

## Does this report cover the intended meta-capability (preflight + continuous replanning)?

**Intent you described**:
- At project start, Autopack should **scan all phases/chunks**, detect inconsistencies, and **revise the plan/requirements** (or suggest alternatives) *before* executing.
- During execution, if troubleshooting/replans change assumptions, Autopack should **re-check downstream phases** and propose/perform **requirements updates** to keep the remaining plan viable.

**Status**: **Partially reflected before; explicitly reflected now.**

This report already identified concrete “plan/requirements” inconsistencies and blockers, but it did not explicitly describe them as a **system-level capability** Autopack must have. The key missing piece is: *what Autopack needs to implement to make this behavior reliable and autonomous*, not just “what’s wrong with the plan”.

---

## Capability Gap: “Phase Preflight + Downstream Replan Ripple Check”

### What Autopack appears to have already
- **Deliverables validation + allowed-roots derivation**: good at catching file-placement mistakes *during* a phase.
- **Limited replanning controls**: the executor has mechanisms for replanning and drift control, and can mark phases for review.
- **Human review gates**: can stop before proceeding.
 - **(New) Convergence robustness for research phases**:
   - in-phase batching for large deliverable sets (Chunk 0 + Chunk 2B)
   - deliverables sanitization (strip annotations) + directory-prefix deliverables/manifest support
   - narrow safe allowlists for required `src/autopack/*` subtrees (Chunk 4)

### What Autopack is missing (to fully satisfy the intent)
#### 1) Up-front preflight that spans *all phases*
Today the guardrails are heavily “per-phase”. There is no explicit “scan all planned chunks first, then revise” workflow in the repo that:
- loads all requirement YAMLs,
- checks for cross-chunk path consistency (e.g., `src/autopack/research/...` vs `src/research/...`),
- checks protected-path feasibility (e.g., Chunk 4 writing outside allowlisted prefixes),
- checks dependency feasibility (imports vs `requirements.txt` / `pyproject.toml`),
- checks test naming collisions and module import hygiene.

#### 2) Automatic downstream plan revision after replans/troubleshooting
The repo can replan within a phase, but there’s no explicit “ripple analysis” that:
- records what assumptions changed (paths, states, CLI entrypoints, schema),
- re-validates future deliverables against those new constraints,
- updates future chunk requirements (or marks them “NEEDS_REVIEW”) before execution continues.

#### 3) Self-modification constraints for “fix Autopack itself”
To revise Autopack’s own code to add these capabilities, the system must be able to write outside `src/autopack/research/` and `src/autopack/cli/`. Under default protected-path isolation, that’s blocked for normal runs.

---

## Recommended Implementation Approach (so Autopack can do this autonomously)

### A) Add a “Preflight Analyzer” step before execution
Add a first step to `execute-phase` (or a separate command) that:
- reads **all chunk requirement YAMLs** for a run (not just the current chunk),
- produces a **Plan Viability Report** with:
  - path/layout consistency checks,
  - protected-path feasibility checks,
  - dependency/import feasibility checks,
  - test namespace collision checks,
  - CLI wiring checks (entrypoints vs requirements),
- optionally generates a **proposed requirements patch** (YAML edits) to normalize paths and mark phases that require maintenance mode.

### B) Add a “Ripple Check” after any replan/troubleshoot
After a phase replan/revision, run a smaller version of the preflight against remaining phases:
- if constraints changed, update downstream requirements or automatically mark them as **NEEDS_REVIEW** with actionable reasons.

### C) Decide how Autopack is allowed to change itself (policy)
Because this capability touches core orchestrator/executor code, you’ll need an explicit policy:
- **Option 1**: allow maintenance/internal run type for “self-upgrades”
- **Option 2**: extend allowlists narrowly for specific new prefixes/modules required by the preflight/ripple features
- **Option 3**: keep it human-driven (Autopack only *suggests* changes; human applies them)

Without this, the meta-capability can’t be fully autonomous for phases like Chunk 4 that inherently require modifying `src/autopack/...` outside the current allowlist.
