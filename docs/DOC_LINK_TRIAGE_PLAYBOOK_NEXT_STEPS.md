# Doc Link Triage — Next Steps Playbook (Post BUILD-166 Follow-Up)

This playbook removes ambiguity and gives an incremental, safe path to reduce deep-scan noise **without weakening nav-only CI**.

---

## Ground rules (match README “navigation trust” philosophy)

- **Nav docs are sacred**: `README.md`, `docs/INDEX.md`, `docs/BUILD_HISTORY.md`
  - In nav mode, **never ignore `missing_file`**. Only **fix**, **manual**, or **redirect stub**.
- **Deep scans are report-first** until noise is low.
- **Prefer fixes over broad ignores**:
  - Ignore only truly non-file references (runtime endpoints, external URLs, intentionally historical refs).
- **Redirect stubs > broken history**:
  - If an old doc name is referenced historically and a replacement exists, create a small redirect stub rather than ignoring.

---

## Step 0 — Confirm CI policy (do this once)

- **Nav-only CI** must fail only on `missing_file` in nav docs.
- **Deep scan** must remain report-only (scheduled/optional; never PR-blocking).

---

## Step 1 — Nav mode sanity (fast, always)

Run:

```bash
python scripts/doc_links/apply_triage.py --mode nav --dry-run --report
python scripts/check_doc_links.py
```

Acceptance:
- `apply_triage.py --mode nav` shows **0 ignored `missing_file`**.
- `check_doc_links.py` reports **0 missing_file** for nav docs.

If nav docs still show missing_file:
- **Do not add ignores**.
- Choose one:
  - update the link target to the canonical doc, or
  - create a redirect stub for the missing doc, or
  - mark manual review with rationale.

---

## Step 2 — Deep mode “top offenders first”

Run deep scan report:

```bash
python scripts/check_doc_links.py --deep --verbose
python scripts/doc_links/apply_triage.py --mode deep --dry-run --report
```

Then prioritize by:
1. **Top offenders by source file** (largest counts first)
2. **Auto-fixable high-confidence** candidates
3. Long-tail unmatched cases

---

## Step 3 — Apply safe actions in deep mode (incremental)

### 3.1 Apply ignores only (safe)

Use this when you’re expanding rules for runtime endpoints/historical refs:

```bash
python scripts/doc_links/apply_triage.py --mode deep --report
```

### 3.2 Apply fixes (writes) only after review

```bash
python scripts/doc_links/apply_triage.py --mode deep --report --apply-fixes
python scripts/check_doc_links.py --deep --verbose
```

Acceptance:
- Missing-file count decreases or stays stable.
- No new missing_file appears in nav docs.

---

## Step 4 — Redirect stubs (preferred for moved docs)

When to use:
- A doc path is referenced historically and the “new canonical” doc exists.

Create a stub file that redirects:
- `docs/OLD_NAME.md`:
  - “Moved to `docs/NEW_NAME.md`”
  - include a link to new location

This preserves history without turning the reference into an ignore.

---

## Step 5 — Avoid the “backticks are links” trap

This repo’s link checker treats backticks (`` `path` ``) as path references. That is useful for deep scans, but it can inflate “broken links” counts and push you toward ignore-list inflation.

**Stricter recommendation (preferred, aligns with README’s “navigation trust”)**:
- **Nav-only enforcement should enforce only real markdown links** (`[text](path)`).
- **Nav-only enforcement should ignore backticks by default** (treat them as informational code formatting).
- Deep scans may include backticks for reporting, but deep scan must remain report-only until noise is low.

If you keep backticks enforced (opt-in only):
- Only ignore true runtime endpoints/external URLs; do not ignore real missing docs.

---

## Operational note: recommended checker behavior in CI

To avoid ambiguity and policy drift:
- CI nav-only job should run a mode that **does not parse backticks** as links.
- CI deep scan job (scheduled) may parse backticks, but must remain **report-only**.

## Step 6 — What to add to configs (with rationale)

### `config/doc_link_triage_overrides.yaml`

- Each rule should include:
  - `id`, `scope` (nav/deep/both), `action`, `reason`
  - patterns that are as narrow as possible

### `config/doc_link_check_ignore.yaml`

Keep nav-only ignores conservative:
- runtime endpoints, external URLs, anchor-only

Avoid broad ignores that can hide missing docs.

---

## Completion targets (suggested)

- **Target A (near-term)**: nav docs remain 0 missing_file; deep scan missing_file reduced by ~50%.
- **Target B (later)**: deep scan missing_file reduced to a manageable tail (< 50–100), with redirect stubs used for important moved docs.
