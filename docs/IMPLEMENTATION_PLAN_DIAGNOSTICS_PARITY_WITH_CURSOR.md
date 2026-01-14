# Implementation Plan: Diagnostics Parity with Cursor (Handoff Bundle + Prompt + Second Opinion)

**Last Updated**: 2025-12-20
**Status**: PROPOSED
**Scope**: Autopack core (framework-level; benefits all projects)

---

## 1. Objective

Make Autopack’s “failure-to-Cursor” workflow as smooth and high-signal as a human-led Cursor debugging session, while staying **token-efficient** and **safe-by-default**.

This plan implements three complementary features:
- **A. Deterministic handoff bundle** (artifact pack + index + summaries)
- **C. Cursor-ready prompt generation** (copy/paste prompt with exact files to open/attach)
- **B. Optional strong-model second opinion triage** (hypotheses + missing evidence + next probes + minimal patch strategy)

**Two-stage strategy (to close the Cursor gap without drowning in tokens/noise)**:
- **Stage 1 (default)**: Deterministic evidence bundling + Cursor prompt generation (cheap, reliable).
- **Stage 2 (escalation)**: Gated deep retrieval + optional strong-model triage (higher cost, higher recall, stricter controls).

---

## 2. Design principles (non-negotiable)

1. **Artifacts first, tokens second**
   - Store full evidence on disk.
   - Feed models only compact summaries + targeted excerpts.

2. **Determinism**
   - Given the same run directory, the handoff bundle should be reproducible.

3. **Triage != solving**
   - Second opinion produces triage guidance, not sweeping architectural rewrites.

4. **Operator-friendly**
   - Output should be immediately usable in Cursor with minimal edits.

5. **Deep retrieval is gated**
   - Deep retrieval is valuable, but only when it is **scoped** (project/run), **bounded** (per-category caps), and **recency-aware** to prevent “context noise” from lowering accuracy.

---

## 3. MVP feature set

### 3.1 Handoff Bundle (Option A)

**Output directory**: `.autonomous_runs/<project>/runs/<family>/<run_id>/handoff/`

**Files**:
- `index.json`
  - run_id, project_id, timestamp
  - list of included files: `{path, kind, bytes, sha256, rationale}`
- `summary.md`
  - “what happened” + “current failure” + “what to do next”
- `excerpts/`
  - curated snippets (example: last 120 lines of `run.log`, last error report text)

### 3.2 Cursor-ready prompt (Option C)

Single text blob containing:
- background intent (vibe-coding-first; takeover is expected)
- run + phase context
- failure symptoms + most relevant excerpts
- exact file list to open/attach (absolute or repo-relative paths)
- constraints: protected paths, allowed paths, deliverables
- explicit questions / unknowns

### 3.3 Second Opinion triage (Option B)

Triggered only when:
- bundle exists, and
- `--second-opinion` is enabled, and
- provider/model is available (e.g., OpenAI key set).

**Output**:
- `second_opinion.json` (structured) + `second_opinion.md` (human-readable)

**Strict scope**:
- root-cause hypotheses (ranked)
- what evidence is missing
- next probes checklist
- minimal patch strategy (or “needs redesign”)

---

## 4. Architecture sketch (token-efficient “diagnostics parity” loop)

### Stage 1 (default): Deterministic bundle → Cursor prompt

1. **Evidence acquisition (deterministic)**
   - Use existing diagnostics agent artifacts + run summaries + phase summaries + error reports + phase specs.
   - Prefer “canonical paths” and “latest failure artifacts” over similarity search.

2. **Compression**
   - Summarize large artifacts into compact ledgers.
   - Keep “full text” on disk, never inline by default.

3. **Prompt assembly**
   - Merge: run context + curated excerpt set + file list + constraints.

4. **Operator loop**
   - Operator pastes prompt into Cursor, attaches listed artifacts, proceeds.

### Stage 2 (escalation): Deep retrieval → (optional) second opinion → evidence requests

5. **Deep retrieval (gated, bounded)**
   - Trigger only when Stage 1 is insufficient (see “Stage 2 triggers” below).
   - Retrieve *snippets + citations* and update bundle index; do not inline full docs/logs.

6. **(Optional) LLM triage**
   - Call strongest model with the compact bundle + retrieved snippets (not raw logs).

7. **Interactive evidence requests**
   - If ambiguity remains, generate a short “I’m missing X; please provide Y” list for the operator.

---

## 5. Implementation phases

### Phase 1 — Handoff bundle generator (core)
**Goal**: Generate `handoff/` folder from a run directory.

**Implementation tasks**:
- Add a `HandoffBundler` utility that:
  - locates run dir via `RunFileLayout`
  - enumerates canonical artifacts (run_summary, phase summary, diagnostics summaries, error reports)
  - writes `handoff/index.json` and `handoff/summary.md`
  - creates `handoff/excerpts/*` using fixed-size tailing

**Acceptance criteria**:
- Works with missing/partial artifacts (never crashes; includes “missing” entries).
- Produces deterministic `index.json` for same run contents.

### Phase 2 — Cursor prompt generator (CLI + dashboard)
**Goal**: Produce a copy/paste prompt referencing the handoff bundle.

**Implementation tasks**:
- Add a CLI entry (intent router) and a dashboard endpoint/button.
- Output prompt text + also write `handoff/cursor_prompt.md`.

**Acceptance criteria**:
- Prompt always includes the “attach/open these files” list (paths).
- Prompt includes constraints (protected paths, allowed paths, deliverables if known).

### Phase 3 — Stage 2: Deep retrieval escalation (bounded + recency-aware)
**Goal**: When Stage 1 lacks enough signal, pull the same “obvious” files a human would open in Cursor, without flooding the prompt.

**Stage 2 triggers** (any one is sufficient):
- Missing key artifacts (no error report, no diagnostics summary, no failing test output).
- Ambiguous failure category (“unknown”, mixed symptoms, or multiple competing root causes).
- Repeated failures with similar messages across attempts (approach-flaw signal).
- High blast-radius phases (integration/core/protected-path-related).

**Retrieval sources** (in priority order):
1. Run-local artifacts (current run directory: diagnostics, errors, phase summaries).
2. SOT docs (project-scoped): `docs/DEBUG_LOG.md`, `docs/BUILD_HISTORY.md`, relevant `docs/BUILD-*.md`, `docs/DBG-*.md`.
3. Structured memory index (vector memory) *only after* 1–2 fail-open fallbacks above.

**Hard bounds** (token + noise control):
- Per category cap: at most **3** snippets each from:
  - SOT debug history (DBG entries)
  - SOT build history (BUILD entries)
  - code docs / API docs
  - prior run summaries
- Recency window: prefer last **30–60 days** unless operator overrides.
- Scope: same project_id; avoid cross-project retrieval by default.
- Snippet size: ≤ **120 lines** or ≤ **8,000 chars** per snippet.

**Acceptance criteria**:
- Deep retrieval never produces more than the configured caps.
- Retrieval output always includes citations (file path + section header or line-range hint).
- Retrieval improves “time-to-first-good-human-action” in at least 2 replayed incidents (manual eval).

### Phase 4 — Optional “Second Opinion” triage (strong model, bounded)
**Goal**: Given a bundle, call a strong model and generate a triage report.

**Implementation tasks**:
- Implement a triage-only system prompt + JSON schema.
- Gate execution:
  - requires keys configured
  - requires bundle exists
  - requires run not already marked fatal for environment reasons
- Persist outputs into `handoff/second_opinion.*`.

**Acceptance criteria**:
- Output is always parseable JSON + readable markdown.
- Output never suggests out-of-scope destructive actions.

### Phase 5 — Iteration loop enhancements (Cursor-like steering)
**Goal**: Let Autopack ask for missing evidence explicitly (without token blowups).

**Implementation tasks**:
- Add “evidence requests” section to prompt:
  - list missing files/artifacts
  - ask targeted questions
- Add compact “human response” ingestion (e.g., paste back a short answer + attach file paths).

**Acceptance criteria**:
- Prompts become progressively more targeted after 1–2 iterations.

---

## 6. Token budget strategy

Default caps:
- Bundle `summary.md`: ≤ 2,000 chars
- Each excerpt: ≤ 120 lines (or ≤ 8,000 chars)
- Stage 2 retrieval total: ≤ 12 snippets across all categories by default (cap first; then truncate).
- Second opinion prompt input: ≤ 12,000–20,000 tokens (soft cap; enforce via truncation + prioritization)

Prioritization order:
1. error reports (structured)
2. diagnostics ledger summary
3. last error stack / last failing test excerpt
4. run summary + current phase summary
5. only then: tail of run.log

---

## 7. Rollout and measurement

**Metrics to add**:
- time-to-first-good-human-action (manual; proxy)
- number of “wrong direction” fixes before resolution
- token usage of triage calls
- bundle generation success rate

---

## 8. Risks

- Over-automation: second opinion may be mistaken; must remain advisory and gated.
- Missing artifacts: some runs may not emit run.log or phase logs; bundle must degrade gracefully.
- Token regression: bundler must remain conservative; never inline huge logs by default.
