### Goal
Automate conversion of implementation plans (markdown) into Autopack phase specs that conform to `docs/phase_spec_schema.md`, so Autopack can ingest plans without manual reformatting.

### Plan
1) Plan parser + schema mapper
   - Build a parser that ingests a markdown plan (headings/bullets) and extracts tasks into phase fields: id, description, complexity, task_category, acceptance_criteria, optional scope (paths/read_only_context), and safety flags.
   - Add heuristics/defaults for missing fields (e.g., complexity=medium, task_category=feature) and allow overrides via inline tags (e.g., `[complexity:low]`, `[category:tests]`, `[paths:src/,tests/]`).

2) CLI generator & validation
   - Create a CLI (e.g., `scripts/plan_from_markdown.py --in docs/PLAN.md --out .autonomous_runs/<proj>/phases_generated.json`) that emits a `{"phases":[...]}` JSON matching `phase_spec_schema`.
   - Integrate validation against the schema; fail fast with clear errors.

3) Integration hook (opt-in)
   - Add an optional executor/maintenance flag to load a generated plan file directly (propose-first) so maintenance/backlog runs can use the converted phases without manual edits.
   - Keep scope optional; allow a default allowed_paths list via CLI flag.

4) Tests
   - Unit tests for the parser/mapping (covers tags, defaults, acceptance criteria extraction).
   - Validation test to ensure generated output passes schema validation.

5) Docs
   - Update README (and a short note in `CONSOLIDATED_STRATEGY.md`) with usage examples for the new CLI and tagging conventions for complexities/categories/paths.

