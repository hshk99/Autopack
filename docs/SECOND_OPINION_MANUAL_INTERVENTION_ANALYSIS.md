# Second Opinion (Revised): Manual Intervention Policy for Autopack

**Date**: 2025-12-19  
**Context**: Research System v29 partial completion (6/8 chunks completed; integration/testing unfinished)  
**Question**: If some phases fail, should we “just manually implement the failed phases”? How often will that obsolete prior work, and is it practical?

---

## Executive Summary (my view)

Manual intervention is **not inherently incompatible** with Autopack. In fact, Autopack already supports *human-in-the-loop governance* via quality gates like `NEEDS_REVIEW` (see `docs/QUALITY_GATE_ANALYSIS.md`).

What *is* incompatible with Autopack’s spirit is **silent, ad-hoc manual coding** that bypasses:
- scope rules / protected paths,
- evidence capture (diagnostics + reasoning),
- and the “learn from outcomes” loop.

So the right question is not “manual vs not-manual”, but **which kind of intervention** and **how it’s recorded** so Autopack still improves.

**Recommendation**:
- Prefer an **intervention ladder**: retry → narrow/split → maintenance-mode run → *small* human patch with audit trail → redesign.
- Treat “integration chunks” as **high blast radius**: they are the most likely to invalidate earlier assumptions, so they should be split and/or done in maintenance mode.
- Replace hand-wavy “60–80% ripple probability” with **measured telemetry**: log “ripple events” and compute the rate from actual runs over time.

---

## 1. What “manual intervention” actually means (important distinction)

Autopack has at least three very different “manual” behaviors:

1. **Human governance (normal, recommended)**  
   - Example: a phase ends as `NEEDS_REVIEW`, a human decides whether to accept, request changes, or schedule follow-up work.
   - This is already part of Autopack’s quality gate design.

2. **Human input (still Autopack-native)**  
   - Example: human clarifies requirements, tightens scope, splits a phase, adds acceptance criteria.
   - The work is still executed by Builder/Auditor and remains inside the learning loop.

3. **Human coding (last resort)**  
   - Example: a human writes code to complete a failed chunk.
   - This can be necessary, but only if it is treated as a first-class event with logging, tests, and lessons captured.

When people say “manual intervention”, they often mean (3). Most of the time you actually want (1) or (2).

---

## 2. Critical assessment of the previous version of this doc

The earlier version had useful instincts (integration phases are high-risk; invest in meta-capabilities like preflight/ripple checks), but it overreached in ways that reduce decision quality:

- **Overstated incompatibility**: calling manual intervention “INCOMPATIBLE” conflicts with Autopack’s documented stance that some outcomes are expected to require human review (`NEEDS_REVIEW` workflows are explicitly accepted elsewhere).
- **Unreliable quantitative claims**:
  - “60–80% ripple probability” and “3–7 out of 10 projects” are presented as confident estimates but are derived from a tiny sample and mixed units (build chains ≠ phase ripples).
  - The “weighted score” combines hours with arbitrary categorical numbers (unit mismatch), producing numbers that look precise but aren’t meaningful.
- **Conflated concepts**:
  - “Cascading BUILD fixes” (framework evolution) is not the same as “phase ripple” (project plan invalidation).
  - Both are real, but they need different mitigations.
- **Actionability gap**:
  - The doc argued “don’t do manual coding” but didn’t give a crisp, operational alternative policy (what to do tomorrow when a run fails).

This revised doc keeps the good parts (blast-radius thinking, meta-capabilities) but grounds the decision process in a clear playbook.

---

## 3. The core risk is real: “ripple effects” are common, especially in integration work

The scenario you worried about is real:
- You fix the failed chunk,
- and that fix reveals an assumption mismatch (paths, contracts, schema, CLI, dependencies),
- making earlier chunks “wrong” or at least partially obsolete.

Rather than guessing a universal percentage, Autopack should treat ripple risk as **a function of blast radius**:

### 3.1 High blast radius (expect ripples unless proven otherwise)
- integration/bootstrapping phases
- schema/contract changes (DB, API, CLI)
- dependency/system-wide config changes
- anything that touches `src/autopack/` (by definition cross-cutting / protected)

### 3.2 Low blast radius (ripples are less likely)
- isolated leaf modules
- pure refactors behind stable interfaces
- docs-only changes

This suggests a policy: **integration work should be split into smaller phases and guarded more heavily** (maintenance-mode runs, checkpoints, targeted tests), whether it’s done by agents or a human.

---

## 4. Autopack-aligned Intervention Ladder (recommended policy)

When a phase fails (or a run stalls), follow this ladder in order. Escalate only when the earlier rung is clearly insufficient.

### 4.1 Rung 0: Accept partial success (ship the slice)
- Use when remaining work is non-MVP or doesn’t block real usage.
- Record “what works” and “what’s missing” in SOT docs.

### 4.2 Rung 1: Retry with better constraints (still autonomous)
- Tighten `allowed_paths`, clarify acceptance criteria, reduce deliverables.
- Add/clarify “do not touch protected paths” guidance (Autopack already does this in spirit; see `docs/BUILD-044_PROTECTED_PATH_ISOLATION.md`).

### 4.3 Rung 2: Split the phase (reduce blast radius)
- Break “integration chunk” into:
  - wiring + minimal entrypoint,
  - persistence/schema (if needed),
  - CLI (if needed),
  - tests (separate).

### 4.4 Rung 3: Maintenance-mode / propose-first run (preferred for core changes)
- Use checkpoints, propose-first, gated apply, and targeted tests.
- This keeps Builder/Auditor and evidence capture intact while allowing carefully scoped core modifications.

### 4.5 Rung 4: Human patch (allowed, but must be auditable)
If you must write code manually, treat it as an Autopack event:
- Create a short decision note: why autonomy was insufficient and what changed.
- Keep the change small and scoped; avoid “big redesigns” in this mode.
- Run tests and capture logs (or at least a governed diagnostics snapshot).
- Add (or prompt Autopack to add) a learned rule / guardrail describing why the failure happened and how to avoid it next time.

### 4.6 Rung 5: Human redesign → feed back into plan
If the real issue is architectural (wrong interface boundaries, wrong workflow), manual coding is usually a trap. Instead:
- Decide the architecture explicitly,
- update the plan/specs,
- then let Autopack implement in smaller phases.

---

## 5. What I would do for Research System v29

Given Chunk 4 is an integration chunk (high blast radius), the most Autopack-aligned sequence is:

1. **Accept that 6/8 completed is meaningful progress**, not failure.  
2. **Split Chunk 4** into smaller “wiring” phases and run them as a maintenance-mode plan (propose-first + checkpoint).  
3. Add **preflight checks** (paths/allowlists/deps/contracts) and a simple **ripple report** after each phase completion (even if initially manual and doc-only).  

That preserves the learning loop and avoids “hero manual coding” that might silently create incompatible interfaces.

---

## 6. Concrete improvement proposal: measure ripples instead of guessing them

If you want a real answer to “how often do ripples happen?”, instrument it:
- Define a **ripple event**: “a completed phase required modification because a later phase changed assumptions/contracts it depended on”.
- Log ripple events in run artifacts and SOT (and ideally DB).
- Track by category (integration/schema/config/paths/deps) and by blast radius.

After ~10–20 multi-phase runs, Autopack can compute real rates and use them to choose:
- when to split phases by default,
- when to force maintenance mode,
- and when to require human review earlier.

---

## Appendix: Manual intervention record template (use when Rung 4 happens)

When you do manual coding, record it in a short note (in the run artifacts or SOT):

- **Trigger**: what failed and why it could not converge autonomously
- **Blast radius**: what contracts/paths/schemas might ripple
- **Change summary**: what changed (files / behavior)
- **Validation**: tests run + result
- **Lessons**: what rule/guardrail should prevent recurrence
