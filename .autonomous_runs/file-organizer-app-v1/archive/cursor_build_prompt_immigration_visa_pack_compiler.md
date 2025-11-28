# Cursor Build Prompt: Implement Immigration / Visa Evidence Pack Compiler

## 1. Context

The FileOrganizer desktop application is a privacy-first, AI-assisted file organiser that also supports **scenario-based packs** such as tax packs, legal evidence packs, and immigration/visa packs.

You already have (or will have) research artefacts describing **tax / immigration / legal packs** and, specifically, a dedicated research report for **immigration / visa evidence packs** across Australia, Canada, United States, United Kingdom and New Zealand.

This build prompt tells you how to **turn that research into a concrete feature**: a **Visa Evidence Pack Compiler** that:

- Uses **visa-specific templates** derived from official guidance.
- Classifies user documents into those categories.
- Shows the user their **coverage vs gaps**.
- Compiles selected evidence into **final uploadable files** (PDF and optionally PPT) aligned to typical portal upload structures.

You are not implementing government integrations or legal advice. You are implementing **offline organisation and packaging tooling** driven by templates and user confirmation.

---

## 2. Files to Read First

Before designing or coding anything, read (if available in the repo):

1. `fileorganizer_product_intent_and_features.md`  
   – High-level intent, target users, and key differentiators for the FileOrganizer app.

2. `MASTER_BUILD_PLAN_FILEORGANIZER.md`  
   – The current global build plan and phase structure for the project.

3. `research_report_tax_immigration_legal_packs.md`  
   – Overall research on tax, immigration, and legal pack use cases.

4. `research_report_immigration_visa_evidence_packs.md`  
   – The immigration-specific research produced from the companion research brief.  
   This is the **primary** input for this feature.

5. Any implementation plans already created for tax/legal packs, e.g.  
   `implementation_plan_tax_immigration_legal_packs.md`  
   – to reuse patterns and avoid duplication.

Your job is to **extend** the existing system with an immigration / visa pack compiler that reuses as much of the existing architecture as possible (OCR, classification, pack-building primitives, UI shell).

---

## 3. Core User Story

> “As a person applying for a visa to [country] under [visa type], I want to drop all my evidence documents into one or more folders and have the app organise, check, and compile them into a small set of upload-ready files that match typical categories in the official application portal, so that uploading is fast and I can clearly see if I am missing anything.”

Key constraints:

- The app never logs into government systems or calls government APIs.
- The app does **not** decide eligibility or give legal advice.
- Everything is local-first and privacy-respecting, with optional cloud calls (e.g. OCR/LLM) controlled by the existing settings.

---

## 4. Functional Requirements

### 4.1 Template-driven country/visa selection

1. Load a **visa pack template catalog** (e.g. from JSON/YAML) as defined in `research_report_immigration_visa_evidence_packs.md`. Each template should map to a `(country, visa_family, visa_code_or_program)` combination.

2. UI requirements:
   - Provide a “**Build immigration / visa pack**” entry point.
   - Step 1: **Country selection** – show the supported countries.
   - Step 2: **Visa selection** – show supported visa templates for that country, grouped by visa family (e.g. Skilled, Student, Partner).  
     - Distinguish **Phase 1, fully supported templates** from generic/limited templates.
   - Step 3: Show a **template summary**:
     - Short description.
     - High-level evidence categories.
     - Volatility level (e.g. “requirements often change”).
     - Disclaimer text.

3. All template data (labels, categories, disclaimers) must come from the external template catalog, **not hard-coded**.

### 4.2 Evidence ingestion and classification

1. Allow the user to pick one or more **source folders** containing candidate evidence.

2. For each file:
   - Run the **existing ingest pipeline** (OCR, text extraction, metadata extraction) where available.
   - Classify each document into **zero, one, or more template categories** using the app’s classification/LLM capabilities, guided by:
     - Category labels.
     - Example document types.
     - Country/visa context.

3. Store classification results in the local database/index, including:
   - Primary category.
   - Secondary categories (if relevant).
   - Confidence scores, where available.

4. Provide a **UI review table** where the user can:
   - See all documents and their proposed category assignments.
   - Reassign categories manually (drag/drop or dropdown).
   - Exclude documents from the pack.
   - See which documents remain **unassigned/unmatched** to any category.

### 4.3 Checklist and coverage view

1. Based on the chosen visa template, show a **checklist view** organised by category:

   - For each category:
     - Category label and description.
     - Whether research labelled it as **required / strongly recommended / optional / stream-specific**.
     - How many candidate documents have been assigned.
     - Whether category is currently **“covered”**, **“partially covered”**, or **“no documents found”**.

2. Allow the user to:
   - Mark a category as **“not applicable in my case”** with an optional explanation (stored locally; may be included in a cover note if the user wants).
   - Quickly jump to the underlying documents for that category.
   - Add free-form notes (e.g. “Waiting for new bank statement”).

3. Provide a **summary bar** showing overall coverage (e.g. “10/12 categories covered, 2 missing, 1 marked not applicable”).

### 4.4 Packaging engine (PDF and PPT outputs)

Using the packaging guidance from the research report and template catalog:

1. Support these **packaging modes**, configurable per template:

   - **Single application PDF**:
     - One combined PDF for the entire application.
     - Ordered by category, with each category starting on a new page.
     - Includes a generated **cover page** and **table of contents** with category names and page ranges.
   - **One PDF per category**:
     - One PDF per evidence category (or per group, if specified in the template).
     - Each PDF has a simple title page and internal bookmarks or minimal TOC.
   - **Folder / archive output**:
     - Folder tree or zip archive mirroring template categories.
     - Normalized filenames applied according to existing naming rules.

   Each visa template should specify a **default mode** plus allowed alternatives.

2. For each PDF output:
   - Combine selected documents in a deterministic order (e.g. by category, then by date, then by original filename), unless the user overrides ordering.
   - Where possible, insert **separator pages** between documents indicating:
     - Category name.
     - Document display name.
   - Generate an **index file** (Markdown, text, or PDF) listing, for every included document:
     - Category.
     - Original filename and original path.
     - Normalized filename if different.
     - Page count (if practical).

3. Optional **PPT export** (Phase 1 basic, Phase 2 more advanced):
   - For Phase 1, at minimum:
     - Title slide: visa type, applicant name (user-input), date, country.
     - One slide per category summarising:
       - Category description.
       - Count of documents.
       - Optional 1–2 key bullet points auto-generated from content (if safe).
   - Later phases can integrate timelines (e.g. relationship/work history) into slides.

4. All outputs must go into a **new output directory** under the chosen case root, e.g.:

   - `/ImmigrationPacks/[Country]/[VisaName]/[YYYY-MM-DD_HHMM]_Pack/`

### 4.5 Safety, traceability, and rollback

1. **Never** modify or delete original evidence files when building packs.

2. All operations (classification, renaming, copying, PDF merges) must be logged in the existing **operations log**, including:
   - Time.
   - Operation type.
   - Source and destination paths.
   - Template and category involved.

3. Provide the ability to:
   - Delete generated outputs via the UI.
   - Re-run the pack builder with updated classifications or additional documents.

4. For any steps that might be ambiguous or costly (e.g. re-OCR, large file merges), show a **dry-run summary** before execution (number of files, estimated size, destination path).

### 4.6 Disclaimers and legal safety

1. For every visa template, display the **disclaimer snippet** from the template catalog prominently at the start of the wizard.

2. Explicitly require the user to **confirm** before final packaging that:

   - They have checked the latest official guidance for their visa.
   - They understand the app is just helping them organise documents.

3. If research flagged any template as **high volatility** or **high uncertainty**, display additional warnings and encourage manual verification of categories.

---

## 5. Non-Goals

Explicitly out of scope for this feature (do not attempt):

- Logging into or interacting directly with government portals.
- Filling out forms, uploading files, or submitting applications.
- Making eligibility determinations, providing legal advice, or saying a pack is “complete” in any normative sense.
- Guaranteeing that any evidence structure is “correct” for a specific case.

The feature simply **organises, checks, and packages** evidence **locally** according to templates that the user must verify.

---

## 6. Architecture and Implementation Plan

You must produce a dedicated implementation plan and integrate it with the existing build plan.

### 6.1 High-level architecture

Using the project’s current architecture as a baseline, introduce or extend the following components:

1. **VisaTemplateStore**
   - Responsible for loading and validating visa templates from disk (JSON/YAML/etc.).
   - Exposes queries like:
     - `list_countries()`
     - `list_visas_for_country(country_code)`
     - `get_template(template_id)`

2. **VisaClassificationService**
   - Wrapper around the existing classification pipeline.
   - Accepts:
     - `template_id`
     - List of document records (already OCR’d and indexed).
   - Returns category assignments and confidence scores per document.

3. **VisaPackCompiler**
   - Consumes:
     - Template definition.
     - Selected documents with category assignments.
     - Packaging mode.
   - Produces:
     - Generated PDFs and/or PPT.
     - Index file(s).
     - Operations for the operations log.

4. **VisaPackWizard UI**
   - Tauri front-end flow orchestrating:
     - Template selection.
     - Evidence ingestion path selection.
     - Classification review.
     - Checklist view.
     - Packaging options.
     - Final confirmation and execution.

### 6.2 Implementation plan deliverable

Create a new file: **`implementation_plan_immigration_visa_evidence_packs.md`** that includes:

1. **Phase breakdown** (MVP vs Phase 2+), e.g.:
   - Phase 1 (MVP):
     - Template loading (read-only from static files).
     - Wizard UI (country/visa selection → classification → checklist → single-PDF and per-category PDF output).
     - Basic index generation.
     - Operations logging and output directory structure.
   - Phase 2:
     - PPT export.
     - More advanced packaging layouts (e.g., custom order builder, per-category grouping options).
     - More sophisticated classification feedback loops (learning from user corrections).
     - Config auto-update / template sync mechanism (if desired).

2. **Task list** with dependencies:
   - Each task should reference existing modules where reuse is expected (OCR, classification, pack building, DB schema).

3. **Data model updates**:
   - Any new DB tables or fields needed (e.g., `visa_template_id` on pack runs, per-document category assignments).

4. **Testing strategy**:
   - Unit tests for template parsing and validation.
   - Integration tests for end-to-end pack generation on small sample folders.
   - Manual QA scripts for ensuring:
     - Original files are untouched.
     - Outputs are placed correctly and are usable (openable PDFs, readable PPTs).

5. **Risk and mitigation notes**:
   - Performance risks when merging many documents.
   - Platform-specific PDF/PPT tooling differences.
   - UX risks (complexity, user confusion) and how the wizard design mitigates them.

### 6.3 Integration with MASTER_BUILD_PLAN_FILEORGANIZER.md

Once the separate implementation plan is drafted, update **`MASTER_BUILD_PLAN_FILEORGANIZER.md`** to:

- Insert the immigration/visa pack compiler work into the appropriate tier(s) and phases.
- Make explicit which immigration features depend on:
  - Existing tax/legal pack primitives.
  - Generic pack-building and classification modules.
- Mark which tasks are **Phase 1 (must-have)** vs **Phase 2 (defer until after MVP traction)**.

---

## 7. Quality Expectations

- Prefer **reuse** of existing infrastructure (classification, pack-building, logging) over new ad-hoc code paths.
- Bias toward **data-driven templates** rather than hard-coded country/visa logic.
- Keep the **wizard UX** as simple and linear as possible while still exposing necessary controls.
- Make it easy to **turn templates on/off** or update them in future versions without invasive code changes.

When you have completed the implementation plan and any necessary code scaffolding, ensure that the artefacts are clearly named and discoverable so the human strategist (Harry’s GPT assistant) can review them and instruct further iterations.
