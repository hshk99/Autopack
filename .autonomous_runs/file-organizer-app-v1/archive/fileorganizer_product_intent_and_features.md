# FileOrganizer – Product Intent, Vision, and Differentiating Features

This document captures the current product intent, core design principles, and feature directions for the FileOrganizer desktop application, distilled from prior strategic and product discussions. It is written to guide autonomous builders (e.g., Cursor, Autopack) and should be treated as the source of truth for **what** to build and **why**.

---

## 1. Product Intent

### 1.1 Core Idea

Build a **local-first, cross-platform desktop assistant** that sits on top of a user’s filesystem and acts as a **personal operations layer for files**. It should:

- Understand content in documents and images (via OCR + LLMs), not just filenames.
- Continuously help users **organize, clean, convert, and package** files for real-life workflows.
- Serve both:
  - **Legal professionals** (litigation evidence timelines, case chronologies), and
  - **General / individual users and sole traders** (tax/BAS packs, immigration packs, rental/job/insurance packs, life admin).

The app is **not just a one-time cleanup tool**. It is an ongoing assistant that keeps the file system organized, prepares structured packs for specific purposes, and gives users powerful control over how everything is structured.

### 1.2 Target Users

1. **Solo and small-firm legal professionals**
   - Need an **offline, private, affordable** “evidence cockpit” to turn messy case materials into clear timelines and bundles.

2. **Individuals and sole traders (e.g., rideshare drivers, freelancers)**
   - Need help organizing:
     - Tax/BAS documentation.
     - Receipts and statements.
     - Evidence for immigration/visa applications.
     - Rental applications, job applications, insurance claims.

3. **General power users**
   - Want a smarter, content-aware, customizable organizer that works across Windows and macOS (and eventually Linux).

### 1.3 Why this application should exist

- Existing tools either focus narrowly on **legal** (ChronoVault, Casefleet, CaseChronology) or on **one-shot file cleanup** (Sparkle for Mac) or just provide raw storage/search (Google Drive, OS file manager).
- Many people (especially low-paid sole traders and immigrants) pay recurring fees to accountants or advisors for tasks that are mostly about **collecting, organizing, naming, and packaging documents correctly**.
- There is no mainstream **cross-platform, local-first tool** that:
  - Understands file content in multiple languages.
  - Lets users **define exactly how** their files should be organized.
  - Provides **scenario-based packs** (tax/BAS, immigration, etc.) with ready-made structures and exports.
  - Also includes **legal-quality timelines and evidence handling** at consumer pricing.

The intention is to fill this gap with a product that is opinionated about workflows but deeply customizable, and that respects privacy by default.

---

## 2. High-Level Positioning

### 2.1 One sentence

> A local-first, cross-platform file assistant that understands your documents, keeps your folders organized over time, and builds ready-to-upload packs for legal cases, tax/BAS, immigration, and other life admin — all while giving you fine-grained control over how everything is named, structured, and exported.

### 2.2 Pillars

1. **Local-first legal evidence & timeline cockpit**
   - Turn raw case folders (PDFs, emails, transcripts, photos) into **court-ready timelines** and evidence bundles that are fully traceable back to source pages.

2. **Scenario packs for real-world workflows**
   - For non-lawyers and sole traders, provide **pack builders** for:
     - Tax/BAS (especially for low-margin sole traders like rideshare drivers).
     - Immigration/visa applications.
     - Rental applications, job applications, insurance/claims, etc.
   - Each pack includes:
     - A suggested folder schema.
     - Categorization rules and checklists.
     - Export pipeline (per-category PDFs, master index, optional PPT summary).

3. **Deep customization and ongoing maintenance**
   - Global and per-folder organization profiles.
   - Natural-language rules.
   - Safe automation (preview, staging, rollback).
   - Smart triage workflows for unknown files.

---

## 3. Core Design Principles

1. **Local-first and privacy-respecting by default**
   - All documents, OCR, LLM analysis and embeddings live on the user’s machine by default.
   - Optional cloud calls (OCR/LLM/export) are explicit, meterable, and tied to paid tiers.
   - Telemetry and usage data collection must never upload raw document content or filenames by default (see section 9).

2. **User always in control**
   - No silent mass renames/moves.
   - All operations go through **preview/staging** with clear before/after views.
   - Every change is logged and **reversible** through an operations log.

3. **Rules & Profiles, not black-box magic**
   - Users define global organization preferences and per-folder schemas.
   - AI proposes and assists, but user rules and override preferences are first-class.

4. **Scenario-focused workflows, not generic features**
   - Pack flows for immigration, tax/BAS, etc. are designed as **guided experiences** with checklists, progress indicators, and domain-relevant summaries.
   - Legal timelines and evidence handling are designed for litigation-style usage, not generic file tagging.

5. **Multi-language and multi-locale aware**
   - Handles documents and queries in major languages.
   - Respects locale-specific date formats and naming conventions.
   - Supports cross-language search and grouping where possible.

6. **Explainable outputs**
   - For legal timelines and packs, every event or summarized item links back to the underlying documents/pages.
   - The app should be able to “explain what it did” for any given folder or pack.

---

## 4. Differentiation vs Existing Products

### 4.1 Compared to OS file managers

- OS file explorers provide:
  - Tree navigation, simple search, and manual folder operations.
- FileOrganizer additionally provides:
  - **Content-based understanding** (OCR + LLM) of PDFs, images, scans, and emails.
  - **Semantic search and Q&A** over the user’s archive.
  - **Smart rules** for naming and structuring.
  - **Scenario packs** (tax/immigration/legal) with dedicated exports.

### 4.2 Compared to Sparkle and similar Mac tools

Sparkle is good at an **initial cleanup** pass for Mac users but is limited in:

- Platform (Mac-only).
- Depth of customization.
- Long-term maintenance and scenario-specific workflows.

FileOrganizer differentiates by:

1. **Cross-platform support**
   - Windows and macOS first-class; Linux later.
   - Consistent rule engine across OSes.

2. **Content-aware organization**
   - Uses OCR + LLM to understand the actual content of documents, not just filenames.

3. **Rules & Profiles engine**
   - Global style profile plus per-folder schemas, with natural-language rule building and previews.

4. **Scenario packs for real life admin**
   - Tax/BAS packs, immigration packs, rental/job application packs, insurance packs.
   - Ready-to-upload compliant bundles and summaries.

5. **Ongoing maintenance**
   - Continuous monitoring of key folders (Downloads, Documents, etc.) with periodic batch suggestions.

### 4.3 Compared to legal SaaS tools (ChronoVault, Casefleet, CaseChronology, etc.)

Legal SaaS tools are:

- Cloud-only and relatively expensive (often $50–$300+/user/month).
- Aimed at firms with teams and complex workflows.

FileOrganizer differentiates by:

1. **Local-first, offline-capable legal cockpit**
   - Enables AI timelines and summaries without uploading discovery to third-party clouds (unless user explicitly chooses).

2. **Solo/small-firm focus and pricing**
   - UX and pricing designed for individual lawyers and small practices.

3. **Bridge to general life admin**
   - Same engine can be used for clients’ documents (immigration, tax, etc.) and personal use cases.

The intention is not to out-feature enterprise legal tools, but to deliver **80% of the value** at a fraction of the price, with a privacy-first, desktop-first orientation.

---

## 5. Organization Engine: Rules, Profiles, and Preferences

### 5.1 Global Organization Profile

A single global profile defines the **default** way files and folders should be organized:

- **Date formats** (e.g. `YYYY-MM-DD`, `DD/MM/YYYY`, `MM-DD-YYYY`).
- **Language and labels** for common categories (“Invoices”, “Factures”, “Facturas”).
- **Naming patterns** using tokens, e.g.:
  - `{date:YYYY-MM-DD}_{category}_{short_title}_{counter}`
  - `{year}_{client}_{doc_type}_{counter}`
- **Folder structure templates**, e.g.:
  - Time-based: `/Year/Month/`.
  - Category-based: `/Finance/{Year}/`, `/Immigration/{Country}/{Program}/`.

Onboarding should ask a few simple questions to set an initial global profile that matches user expectations (locale, formality, length of filenames, etc.).

### 5.2 Folder-Level Profiles

Every folder can optionally override any part of the global profile:

- Choose a **profile type** (e.g. “Invoices”, “Photos”, “Immigration Pack”, “Tax/BAS Pack”, “Legal Case”).
- Override:
  - Naming pattern.
  - Date source (file metadata vs content vs EXIF).
  - Subfolder layout.
  - Automation level (suggest-only / ask-before-apply / auto-apply).

UI pattern:

- Right-click folder → “Folder rules…”.  
- Show inherited global settings and local overrides, plus a live preview.

### 5.3 Per-Batch Rules

For each batch of files (e.g. a new folder of receipts or case documents):

- User can apply a **one-time schema** (e.g. “Uber BAS Q1 rule”, “Japan trip photos”).
- Optionally save that schema as a named template for reuse.

### 5.4 Natural-Language Rule Builder

Users can define or adjust rules using natural language (via text or voice), e.g.:

- “In this folder, group files by year and month, then rename them to `YYYY-MM-DD_short-title`.”
- “For invoices in this folder, rename to `[Vendor]_[YYYY-MM]_[Amount]` and move into `Finance/Invoices/YYYY`.”

The system should:

1. Parse the request into a concrete rule.
2. Show a preview table of **Before → After** for a sample of files.
3. Allow user to tweak tokens, separators, and destination paths.
4. Save rule into the appropriate profile/template.

### 5.5 Rule Inheritance, Exceptions, and Safe Zones

- Inheritance chain: **Global profile → Folder profile → Subfolder exception → Individual pin**.
- “Safe zones”:
  - E.g., mark `Evidence/Personal` or `/Archive/Sensitive/` as **never auto-move or rename**.
  - Rules must respect these boundaries unless user overrides explicitly.

### 5.6 Presets and Rule Collections

Ship with a set of presets that users can import and tweak, such as:

- “Minimalist” – shallow hierarchy, concise names.
- “Project-centric” – `/Projects/{Project}/{Year}/{Type}/`.
- “Life admin” – `Taxes`, `Housing`, `Health`, `Work`, `Travel`, etc., each with default rules.
- Later: allow exporting/importing rule sets (community or team sharing).

---

## 6. Automation Safety, Staging, and Triage

### 6.1 Automation Profiles

Global modes, overridable per folder:

- **Preview Only** – never execute automatically; always show suggested changes.
- **Assisted** – automatically group suggestions into batches; user approves per-batch or per-rule.
- **Autopilot for low-risk areas** – for specific folders (e.g. Downloads older than 30 days), auto-apply safe rules (e.g. archive by date/type).

### 6.2 Staging Area and Dry-Run by Default

Before applying any non-trivial change set, the app shows a **Proposed Changes** view:

- Number of files to be renamed/moved/converted.
- **Before and After** paths and names.
- Any risk flags (e.g. overwriting a file, major path changes).

User can:

- Approve all.
- Approve by group/rule/folder.
- Deselect individual items.

### 6.3 Operations Log and Rollback

Every operation (rename/move/convert/delete) is appended to an **operations log** with:

- Timestamp.
- Old path and new path.
- Rule or user action that caused the change.

Users can:

- Undo the last operation.
- Undo all operations from a specific date/time.
- Inspect individual changes and selectively revert.

### 6.4 Handling Unrecognized/Uncategorized Files (Triage)

Since early models and rules will not be perfect, there will be many unknown or low-confidence items. Triage UX should:

1. **Bucket by confidence**:
   - High confidence → can be auto-applied.
   - Medium confidence → show as suggestions in staging.
   - Low confidence / unknown → triage board.

2. **Triage board UI** for unknowns:
   - Card or list view per file:
     - Filename.
     - AI guess: “Maybe: bank statement / insurance / immigration email / random file”.
     - Thumbnail or snippet.
   - Quick action buttons:
     - Category chips (e.g. `[Tax] [Immigration] [Health] [Personal] [Ignore]`).
     - Actions: “Move to folder X”, “Mark Not Important”, “Skip for now”.

3. **Batch operations**:
   - Filter by guessed type (e.g. “show likely bank statements”).  
   - Select many → assign category or destination with one click.

4. **Teach-and-learn loop**:
   - Each correction (e.g. “This is actually `Tax → Fuel expense`”) feeds back into the system:
     - Suggests a new rule based on vendor/format/keywords.
     - Asks permission to apply this rule to similar files and to save it into the appropriate profile.

5. **Triage wizards** for large unknown buckets:
   - Ask the user high-level questions to segment unknowns:
     - Are these mostly tax-related, immigration-related, mixed, or other?
     - Are they mostly from a small number of senders (Uber, a bank, employer)?
   - Group files by sender/keywords/date and allow group-level classification.

The aim is to reduce friction for the user: triage should feel like **swiping through suggestions** rather than manually inspecting every file.

---

## 7. Content Understanding, Search, and Timelines

### 7.1 OCR and Multi-language Support

- Use a **hybrid OCR pipeline**:
  - Local OCR (e.g., Tesseract) as default for cost and privacy.
  - Optional cloud OCR for tricky documents, handwriting, or better quality (for paid tiers).
- Support major languages for text recognition and categorization (priorities: English, Spanish, French, German, Portuguese, Italian, Chinese, Japanese, Korean, etc.).
- Provide a way to configure which languages to prioritize.

### 7.2 Semantic Search and Q&A

Enable semantic search and simple Q&A over the local index, e.g.:

- “Show me the invoice for that Airbnb in Tokyo in March 2023.”
- “List all documents related to my 2024 tax return.”
- “When did I last renew my car insurance and with which company?”

Search results should:

- Combine filename, metadata, and content.
- Show extracted snippets with context.
- Allow filters by date, type, entity, and pack.

### 7.3 Entity- and Topic-Centric Views

Provide higher-level lenses onto the same underlying files:

- **People**: group documents by person names.
- **Organizations**: employers, banks, landlords, agencies.
- **Projects**: detected clusters based on folder structure and content (“House move 2024”, “UK visa 2025”).
- **Packs**: show the files associated with each pack (tax pack, immigration pack, etc.).

### 7.4 Personal and Legal Timelines

Use the same event-extraction engine to support two kinds of timelines:

1. **Legal case timelines**
   - Events: incidents, communications, filings, medical visits, etc.
   - Each event:
     - Date/time (with approximate ranges if necessary).
     - Description.
     - Parties involved.
     - Links to one or more documents/pages.
   - Filters:
     - Parties, time range, category.
   - Export to structured formats (Markdown, Word, PDF, timeline charts).

2. **Personal/life timelines**
   - Events: moves, jobs, travels, major purchases, medical visits, visas, leases.
   - Useful for general users to understand “what happened when” in their life admin.

Every timeline entry must be **traceable back to original sources**.

---

## 8. Scenario Packs and Domain-Specific Workflows

The engine for packs should be **configuration-driven** so new pack types and country variants can be added without rewriting core logic.

### 8.1 Shared Pack Concepts

Each pack type defines:

- A **checklist/schema** of categories and subcategories.
- A **folder layout** for storage and exports.
- **Classification rules** (based on content, metadata, sender, etc.).
- An **export recipe** (PDFs per category, master index, optional PPT).

The app should support multiple pack types concurrently; users may run several packs at once (e.g., an immigration pack and a tax pack in the same tax year).

### 8.2 Immigration / Visa Evidence Packs

For a chosen **country and visa type** (e.g., “Australia Partner Visa”, “Canada PR”, “UK Skilled Worker”):

1. **Template checklist** (non-legal-advice) for common evidence categories:
   - Identity documents.
   - Relationship evidence.
   - Financial support.
   - Residency / cohabitation proof.
   - Employment/education history.

2. **Workflow**:
   - User defines or selects a case folder.
   - Drops all potentially relevant documents into a staging area.
   - App classifies each file into categories; flags missing typical items (e.g. recent bank statements, recent payslips).
   - User reviews and fixes classifications via the triage UI.

3. **Output options**:
   - Structured folder tree: `/Immigration/{Country}_{Program}_{Year}/01_Identity/... 02_Finances/... 03_Relationship/...`.
   - Per-category PDFs with table of contents and numbered evidence entries.
   - Optional master index PDF with cross-category summary.
   - Optional PPT deck summarizing evidence per category with key snippets and thumbnails.

4. **Constraints**:
   - The app does **not** guarantee legal correctness and does **not** give legal advice.
   - It focuses on **organization and packaging**, not on deciding eligibility.

### 8.3 Tax and BAS Packs for Sole Traders and Individuals

Aim: Make it much easier and cheaper for low-margin sole traders (e.g., Uber drivers, delivery couriers, cleaners, freelancers) and individuals to prepare **structured, accountant-ready Tax/BAS packs** for their jurisdiction.

1. **Generic Tax Pack (all countries)**:
   - Ask user:
     - Tax year/period (e.g., “2024–25” or “Q1 2025”).
     - Country.
     - Role (sole trader, employee, mixed).
   - Set up folder schema, e.g.:
     - `/Tax/2024-25/Income/`
     - `/Tax/2024-25/Expenses/Vehicle/`
     - `/Tax/2024-25/Expenses/Phone/`
     - `/Tax/2024-25/Expenses/Office/`
   - Ingest receipts, bank statements, CSV exports from platforms (Uber, banks, etc.).
   - Automatically classify transactions and docs into tax categories using vendor/sender/content and user-confirmed mappings.
   - Generate:
     - A summary spreadsheet (per-category totals, counts, date ranges).
     - Category subfolders and optional merged PDFs for each category.

2. **Country-specific BAS/VAT Packs (e.g., Australian BAS)**:
   - Research and encode templates for common forms like BAS (AU) with fields like G1, 1A, 1B, etc.
   - For specific **profession templates** (rideshare driver, cleaner, freelancer, etc.), define mapping from categories to BAS/VAT fields.
   - Workflow:
     - User specifies country and archetype (e.g., “AU, Sole Trader, Rideshare Driver”).
     - App aggregates relevant transactions for the quarter.
     - App produces a **BAS input sheet** with field-level totals and references to underlying evidence.
   - Positioning:
     - “We prepare structured summaries and evidence folders designed to make BAS/VAT/tax prep easier for you and your accountant. You remain responsible for checking and filing.”

3. **Additional features for tax/BAS packs**:
   - Profession templates.
   - Quarterly reminders (“It’s end of Q2—create a BAS pack now?”).
   - Accountant export mode: ZIP with summary sheet, categorised folders, and a README explaining structure.
   - Later: multi-currency support for international freelancers.

### 8.4 Other Packs

Additional pack types can reuse the same engine:

- **Rental application pack** – ID, payslips, references, rental history.
- **Job application pack** – CV, cover letters, certificates, reference letters, portfolio.
- **Insurance claim pack** – incident reports, photos, invoices, medical reports.
- **Generic evidence pack** for any ad-hoc need.

The pack system should be pluggable so new templates can be defined via configuration (e.g., JSON/YAML) without code changes wherever possible.

---

## 9. Telemetry, Usage Data, and Data Policy (High Level)

The app’s value proposition includes being privacy-respecting. Any data collection must be designed accordingly.

### 9.1 Levels of Data Collection

1. **Level 0 – Minimal analytics (default)**:
   - Collect **only** non-content telemetry by default:
     - Pseudonymous user ID.
     - OS, app version, RAM bucket.
     - Event types (feature usage counts, performance metrics).
     - No file paths, no filenames, no extracted text, no embeddings.

2. **Level 1 – “Help improve the product” (opt-in)**:
   - Additional aggregated, content-adjacent stats, still without raw content:
     - Shape of rules (e.g., many users use `[Date]_[Vendor]_[Amount]` patterns).
     - Error/correction patterns (e.g., miscategorized “Tax vs Immigration”).

3. **Level 2 – Content-based telemetry**:
   - **Avoid by default**, particularly for legal and immigration domains.
   - If ever added, must be on an explicit, high-friction opt-in, with strict constraints and retention policies.

### 9.2 User Controls

- Global “Send anonymous usage data” toggle in Settings for Level 0.
- Separate “Help improve FileOrganizer” toggle for Level 1.
- Clear explanation in plain language.
- Easy way to request removal of telemetry data.

These policies are guiding principles; implementation details can be refined later.

---

## 10. UX & Interaction Notes

### 10.1 Voice and Chat Navigation

- Provide a **command palette** and/or chat interface for natural language commands, such as:
  - “Organize my Downloads using conservative mode.”
  - “Create a BAS pack for Q1 2025 from this folder.”
  - “Find all documents related to my landlord in the last two years.”
- Contemplate voice input for the same commands (especially on desktop platforms with microphone access).

### 10.2 Dark Mode and Theming

- Support at least two themes:
  - Light.
  - Dark.
- Ideally follow OS theme preference by default, with a manual override.

### 10.3 Integration with OS File Explorers (stretch goal)

- Explore options for:
  - Shell/context menu integration (“Organize with FileOrganizer…” right from Windows Explorer / macOS Finder).
  - Optional side-panel integration or quick preview inside OS explorer (if feasible).
- This is a **nice-to-have**; the core requirement is a standalone desktop app with a clean, focused UI.

### 10.4 Wizard Flows

- For complex tasks (e.g., creating a new immigration or BAS pack), provide wizard-style flows:
  - Step-by-step screens.
  - Clear progress indication.
  - Defaults + expert toggles.

---

## 11. Summary for Cursor / Autopack

When building this system, treat this document as the **authoritative expression of intent**:

- Emphasize **local-first, privacy-respecting** architecture, with optional cloud features gated behind paid tiers and explicit user consent.
- Implement a **Rules & Profiles engine** with global preferences, folder-level profiles, and per-batch schemas.
- Provide **safety mechanisms**: staging, previews, operations log, and rollback.
- Deliver **scenario packs** for tax/BAS, immigration, and other life admin uses, built as configuration-driven workflows on top of the core engine.
- Support **legal evidence timelines** suitable for solo practitioners and small firms, with traceability back to source documents.
- Offer **modern interaction methods** (command palette, chat/voice commands, dark mode) and consider optional integration with OS file explorers as a later enhancement.

Future phases can expand packs, add more integrations, and refine multi-language support, but the foundation described here should guide the initial architecture and implementation.
