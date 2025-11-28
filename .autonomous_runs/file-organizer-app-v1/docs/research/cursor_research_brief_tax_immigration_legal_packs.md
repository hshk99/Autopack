# Cursor Research Brief – Tax/BAS, Immigration, and Legal Pack Formats

This document defines a research task for Cursor (or a similar autonomous agent) to perform **before** implementing the pack-related features of FileOrganizer.

Its goals are to:
- Gather structured information about how tax/BAS, immigration, and legal evidence are typically formatted and submitted in different jurisdictions.
- Turn that into **configuration-ready schemas** for FileOrganizer’s pack system.
- Produce a concrete **implementation plan** that aligns with the product intent in the companion document:

> `fileorganizer_product_intent_and_features.md`

Cursor should carefully read that companion document first.

---

## 1. Context and Priorities

### 1.1 Product context (short summary)

FileOrganizer is a local-first desktop application that:

- Understands document content (OCR + LLM) to organize and package files.
- Provides **scenario packs** for:
  - Tax/BAS (with focus on sole traders and low-margin workers like rideshare drivers).
  - Immigration/visa applications.
  - Legal evidence timelines and court-ready bundles.
  - Other life-admin packs (rental, job application, insurance).

The pack system should be **configuration-driven**, so adding a new pack or country variant is primarily a matter of adding/changing templates, not rewriting core code.

### 1.2 Scope of this research brief

Cursor’s job here is **not** to implement the features yet, but to:

1. Research typical **document and upload formats, checklists, and field structures** for tax/BAS, immigration, and legal evidence in a few target countries.
2. Translate that research into **abstract schemas and mapping rules** that FileOrganizer can use as pack templates.
3. Produce a **research report** and a **technical implementation plan** that other agents (and humans) can follow.

---

## 2. Domains and Jurisdictions to Research

### 2.1 Tax and BAS / VAT

Initial priority:

- **Australia** – BAS for sole traders (e.g., rideshare drivers, delivery couriers, cleaners, freelancers).
- **United Kingdom** – Self Assessment / VAT for sole traders.
- **United States** – Self-employed / sole proprietors (Schedule C concepts, even though official forms can be complex).
- **Canada** – Self-employed tax concepts and HST/GST where applicable.

For each of these, focus on:

- What **fields and summaries** are typically needed to fill quarterly/annual forms.
- How accountants prefer to receive client data (common spreadsheet layouts, document bundles).
- What **evidence categories** matter for audits (income, expenses by category, assets, etc.).

### 2.2 Immigration / visa evidence

Initial priority countries and program types (examples, can be adjusted):

- **Australia** – Partner visa, skilled migration, student visa (at least one family-based and one economic-based program).
- **United Kingdom** – Partner visa, Skilled Worker visa.
- **Canada** – PR programs (e.g., Express Entry/family sponsorship) at a high conceptual level.
- **United States** – Example family- or employment-based categories (at least at a high level).

For each country/program sample, identify:

- Typical evidence categories (relationship, identity, financial, residence, employment, education, etc.).
- How evidence is typically **submitted/uploaded** (per category PDFs, individual uploads, size limits, file types).
- Common checklists and guidance that can safely be represented in a **non-legal-advice checklist**.

### 2.3 Legal evidence and timelines

Research at a **conceptual** level (not jurisdiction-specific legal advice) how legal timelines and evidence bundles are usually structured, with emphasis on:

- Common event categories (incident, correspondence, filings, medical visits, employment events, etc.).
- Preferred structure for case chronologies (columns like date, time, description, source reference, parties, category).
- How evidence bundles are often organized for court or arbitration (numbered documents, indexes, sections).

The goal is to understand the **data structures and packaging conventions**, not to replicate any one jurisdiction’s formal civil procedure rules.

---

## 3. Research Objectives and Questions

Cursor should answer the following questions in each domain.

### 3.1 For tax/BAS and VAT packs

For each target country:

1. **What are the main tax/BAS/VAT forms and periods** relevant for sole traders?
   - E.g., Australian BAS quarterly forms and fields like G1, 1A, 1B, etc.
   - For the UK, main Self Assessment components / VAT return fields.
   - For US/Canada, high-level categories for income and deductible expenses.

2. **What evidence categories** should a sole trader organize?
   - Income:
     - Platform payouts (Uber, rideshare, delivery apps).
     - Direct invoices to clients.
   - Expenses:
     - Fuel/vehicle, phone, internet, equipment, home office, etc.
   - For each category:
     - Typical types of documents (invoices, receipts, bank statements).
     - Recommended timeframes (last year, last quarter).

3. **How do accountants typically want data delivered?**
   - Example spreadsheet layouts:
     - Date, description, category, amount, tax component, counterparty, currency.
   - How evidence is grouped:
     - One folder per category with appropriately named PDFs.
     - One combined PDF per category for easier viewing.

4. **What mappings exist from document categories → form fields?**
   - High-level rules like:
     - “Rideshare income” → “Sales/Services” field.
     - “Fuel expense for business use” → “GST on purchases” bucket.
   - Cursor should **not** try to encode all tax rules, but should identify **typical patterns** suitable for configuration.

5. **Submission/portal constraints**:
   - Common file type and size expectations (PDF vs images; max file size per upload, if publicly documented).
   - Whether portals prefer **one document per category** or multiple uploads per category.

6. **Variations by profession / archetype**:
   - Are there official or commonly used templates for:
     - Rideshare drivers.
     - Delivery couriers.
     - Cleaners.
     - Freelance professionals.

Cursor should focus on **reproducible facts** (e.g., official form structures, example checklists) and **widely used conventions**, not individual accountant opinions.

### 3.2 For immigration/visa evidence packs

For each sample country and visa archetype:

1. **What evidence categories do official guides highlight?**
   - Identity.
   - Relationship (for partner/family visas).
   - Financial support / income.
   - Cohabitation / residence.
   - Employment or study.
   - Other supporting evidence (photos, messages, travel history, etc.).

2. **What are typical **subcategories** within each?**
   - For example, relationship evidence:
     - Joint leases, joint bills, shared bank accounts, photos over time, travel itineraries.
   - Financial evidence:
     - Payslips, tax returns, bank statements.

3. **How is evidence commonly packaged for upload?**
   - One PDF per category with multiple documents combined, or a set of individual PDFs?
   - Any publicly documented limits on number of uploads, file size, and file types.

4. **What ordering and structure is recommended for clarity?**
   - E.g., chronological ordering within each category.
   - Table of contents / index page at the start of a bundle.

5. **Non-legal-advice checklist structure**
   - Extract the **checklist-level structure** that FileOrganizer can safely represent as:
     - “Suggested evidence types” per category.
     - “Typical minimum time coverage” (e.g. 12 months of joint bills).
   - Cursor must avoid giving direct legal advice and instead focus on organizing and packaging patterns.

### 3.3 For legal evidence and timelines

1. What are common **columns** in legal chronologies?
   - Date / time.
   - Event description.
   - Parties involved.
   - Source document reference (ID, page, paragraph).
   - Category (incident, communication, filing, medical, etc.).

2. How are **evidence bundles** commonly structured?
   - Numbered documents (Document 1, 2, 3, …) with an index.
   - Sections by type or chronology.
   - Any preferred naming schemes (e.g. `Tab 1 – Incident Reports`, etc.).

3. For cross-jurisdictional use, what is a **minimal common structure** that FileOrganizer can adopt?
   - E.g. generic categories and fields that are meaningful in most jurisdictions.

Cursor should favor **general practices** that are widely applicable, rather than highly jurisdiction-specific rules.

---

## 4. Output Requirements

Cursor must produce **two Markdown files** and place them in a well-defined path (e.g., `docs/research/` in the repository):

1. `docs/research/research_report_tax_immigration_legal_packs.md`
2. `docs/research/implementation_plan_tax_immigration_legal_packs.md`

### 4.1 Research Report – `research_report_tax_immigration_legal_packs.md`

This report should:

1. Summarize findings **per domain and country**, organized like:

   - Tax/BAS & VAT
     - Australia
     - UK
     - US
     - Canada
   - Immigration/visa evidence
     - Australia (programs sampled)
     - UK
     - Canada
     - US
   - Legal evidence and timelines
     - General patterns

2. For each domain/country pair, present:

   - Key forms and concepts.
   - Evidence categories and typical documents.
   - Common or recommended ways to package evidence (folders, PDFs, indexes).
   - Submission constraints (file types/size, if known).
   - Profession/program-specific nuances (e.g. rideshare vs other sole traders).

3. Identify **invariants vs variations**:

   - Invariants: structures that look broadly similar across countries (e.g., having income vs expenses; identity vs relationship evidence).
   - Variations: specific fields, naming, or constraints that differ by jurisdiction.

4. Highlight **design implications** for FileOrganizer:

   - What categories and fields the app should support generically.
   - Which things must be parameterized per country/program.
   - Where the app must show **clear disclaimers** (non-legal, non-tax advice).

5. Provide **appendices or tables** where useful (e.g., mapping categories to tax form fields at a high level, clearly labeled as “for organization only”).

Cursor must cite its sources in a concise way (links and short notes) inside this report, without copying large blocks of text.

### 4.2 Implementation Plan – `implementation_plan_tax_immigration_legal_packs.md`

This plan should be written **for builders** (Cursor/Autopack and human engineers) and should reference the product intent in `fileorganizer_product_intent_and_features.md`.

It should cover at least:

1. **Configuration schema for packs**

   - Propose a concrete format (e.g., YAML or JSON) to define pack templates with fields such as:
     - Pack metadata (name, domain, country, version).
     - Category definitions and hierarchy.
     - Mapping rules:
       - From document/transaction attributes → categories.
       - From categories → form fields or checklist groups.
     - Export recipes (per-category PDFs, index structure, PPT templates).

2. **Initial pack templates to implement**

   - A prioritized list of initial templates, e.g.:
     - `tax_au_bas_sole_trader_rideshare`
     - `tax_generic_individual`
     - `immigration_au_partner`
     - `immigration_generic_relationship`
     - `legal_generic_timeline`
   - For each template, list the categories and export structures at a high level.

3. **Integration with core engine**

   - Describe how packs plug into the existing core:
     - Ingestion and classification pipeline.
     - Rules & Profiles engine (how a pack extends or overrides rules).
     - Triage UI (how unknowns are presented within a pack context).
     - Export pipeline (PDF and PPT generation, “standard” vs “high quality” modes).

4. **Handling unknowns and user corrections**

   - Define how user corrections in the pack flows (e.g., reassigning a receipt to a different category) update:
     - The pack’s ephemeral state (this instance of the pack).
     - Persistent rules or presets (if the user chooses to generalize the fix).

5. **Safety and disclaimers**

   - Guidelines for how the app should present pack results:
     - Clear messages like “This is an organizational summary intended to help you gather and package documents; it is not tax or legal advice.”
   - Where disclaimers should appear (pack wizard, exports, etc.).

6. **Country and pack extensibility**

   - Describe how to:
     - Add a new country template or update an existing one without code changes.
     - Version pack templates so that changes do not silently alter existing user packs.

7. **Prioritized milestones**

   - Propose a sequence of implementation milestones, for example:
     - Milestone 1: Implement pack configuration schema and core engine hooks.
     - Milestone 2: Implement “generic tax pack” (all countries) and “generic immigration pack” using simplified schemas.
     - Milestone 3: Implement one concrete country-specific tax pack (e.g., AU BAS for rideshare) and one concrete immigration pack (e.g., AU partner) as reference implementations.
     - Milestone 4: Refine triage and export flows based on those packs.

The implementation plan must stay aligned with the intent that FileOrganizer is **local-first, privacy-respecting, and focused on organization/packaging rather than giving legal or tax advice**.

---

## 5. Research Methodology and Constraints

Cursor should:

1. Prefer **official and authoritative sources**:
   - Government websites.
   - Official guidance documents.
   - Well-known professional associations (for typical practices).

2. Avoid:
   - Copying large blocks of text.
   - Offering opinions as facts.
   - Providing explicit tax or legal advice in the templates.

3. Make clear what is:
   - Derived from official guidance.
   - A common practice or convention.
   - An assumption or design decision for FileOrganizer (must be clearly labeled).

4. Keep the focus on **formats, structure, categories, and packaging patterns**, not on eligibility or substantive legal/tax rules.

---

## 6. Deliverable Handoff

Once Cursor completes:

1. `research_report_tax_immigration_legal_packs.md`
2. `implementation_plan_tax_immigration_legal_packs.md`

they will be reviewed by another assistant (and/or human). That assistant will:

- Validate the technical feasibility of using the proposed schemas and flow.
- Decide which packs and jurisdictions to implement first.
- Integrate the plan with the broader implementation phases for FileOrganizer.

Cursor should ensure the outputs are **clear, structured, and self-contained**, assuming the reader has access to and has read:

> `fileorganizer_product_intent_and_features.md`

but not necessarily the web sources Cursor used.

This concludes the research brief.
