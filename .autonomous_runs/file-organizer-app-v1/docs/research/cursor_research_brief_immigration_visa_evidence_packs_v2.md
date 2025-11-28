# Cursor Research Brief: Immigration / Visa Evidence Packs (Multi-Country, Multi-Visa)

## 1. Background and Goal

The FileOrganizer desktop application already aims to support “tax / immigration / legal packs” as opinionated workflows on top of its core AI file-organization engine (OCR + LLM, timelines, pack builders).

This brief refines the **immigration / visa** part of that vision.

You must design the *research layer* for **immigration evidence packs** so that, later, the app can:

- Let a user choose a **country** and **visa type**.
- Let them drop all of their evidence into one or more folders.
- Automatically **categorize** those documents according to official evidence categories.
- Show them **coverage vs gaps** against those categories.
- **Compile** the selected evidence into a small number of final **uploadable files** (PDFs and optionally PPT decks) that map cleanly to typical upload sections in official portals.

This is an **organizational assistant**, not a legal advisor. All outputs must be framed as **helper templates** that the user must verify against the latest official instructions.

---

## 2. Countries and Initial Scope

### 2.1 Target countries

Focus on these **five popular immigration destinations**:

1. **Australia**
2. **Canada**
3. **United States**
4. **United Kingdom**
5. **New Zealand**

The aim is to build a **re-usable research and template model** that can later be extended to more countries.

### 2.2 Visa scope strategy

Each country has a very large number of visa subclasses (for example, Australia has dozens of subclasses across visitor, work, family, humanitarian, bridging, etc.). It is **not realistic** to support every subclass in depth from day one.

You must therefore:

1. For each country, identify a **priority set of visa families** where:
   - Individuals are likely to do significant **document gathering themselves** (rather than everything being handled by a large corporate immigration provider).
   - Evidence requirements are **complex and multi-document**.
   - The process involves **online upload of documents** to some kind of portal.

2. For each country, select an **initial set of concrete visa types** (subclasses/programs) inside those families.

Guidelines (examples, not exhaustive or prescriptive):

- **Australia (AU)** – prioritise families such as:
  - Student visa (e.g. subclass 500).
  - Skilled / work visas (e.g. TSS 482 / Skills in Demand, Skilled Independent 189, Skilled Nominated 190, Skilled Work Regional 491).
  - Partner / family visas (e.g. 309/100, 820/801, Prospective Marriage 300).
  - Visitor (600) as a lower-complexity example.
- **Canada (CA)** – e.g.:
  - Express Entry / Federal Skilled Worker / Canadian Experience Class.
  - Family sponsorship (spouse/common-law).
  - Study permit.
  - Work permits commonly used by individuals.
- **United States (US)** – e.g.:
  - Family-based immigrant visas (IR/CR classes).
  - Employment-based immigrant categories (e.g. EB-2/EB-3) at a high level.
  - Common non-immigrant categories for individuals (F-1, certain work visas) at a high-level “evidence category” layer only.
- **United Kingdom (UK)** – e.g.:
  - Skilled Worker.
  - Student.
  - Family/Partner routes.
  - Graduate / post-study.
- **New Zealand (NZ)** – e.g.:
  - Skilled migrant / accredited employer.
  - Partner / family.
  - Common study / work routes.

3. For visas **outside** these initial sets, define **generic templates** per-country (e.g. “Generic AU visa evidence pack”) that use broad categories like identity, character, health, finances, relationship, work/study history. These generic templates give the user some structure even if their precise visa is not deeply modelled.

Design the research so that **adding new visa templates later** is straightforward.

---

## 3. Research Tasks

You are doing **desk research only**. You are not making up rules. You must rely on **official public information** and clearly authoritative sources.

For each target **country** and each **priority visa type** you select:

### 3.1 Sources

1. Prefer **official government** sites, e.g.:
   - Australia: homeaffairs.gov.au, immi.homeaffairs.gov.au
   - Canada: cic.gc.ca, canada.ca (IRCC)
   - United States: uscis.gov, travel.state.gov
   - United Kingdom: gov.uk (Home Office / UKVI)
   - New Zealand: immigration.govt.nz

2. Only use secondary sources (law firms, consultants, blogs) when they are:
   - Used to cross-check or clarify official statements.
   - Clearly labelled as **secondary** in your notes.

Never base requirements solely on third-party marketing pages.

### 3.2 Extracting evidence categories

For each visa type:

1. Identify and record the **main evidence categories** mentioned in official guidance. Examples (not exhaustive):
   - Identity / passport.
   - Relationship / partner proof.
   - Financial capacity / proof of funds.
   - Employment / job offer / work history.
   - Education / enrolment / qualifications.
   - Health / medicals.
   - Character / police certificates.
   - English language ability.
   - Other visa-specific categories (e.g., sponsorship, business ownership, humanitarian circumstances).

2. For each category, extract:
   - A **clear label** (user-facing name).
   - A **short description**.
   - **Example document types** (e.g., “bank statements”, “employment contracts”, “photos together”, “rental agreements”).
   - Any indication of **minimum coverage** (e.g., “evidence of cohabitation for 12 months”). Do not interpret; just restate as written.

### 3.3 Upload / packaging behaviour

Where documentation exists for the **online application portal** (e.g. ImmiAccount, IRCC portals, USCIS online account, UKVI online application, NZ Immigration Online), determine:

1. How evidence is **grouped** in the portal:
   - Names of upload sections or categories.
   - Whether certain categories correspond to a single upload slot or multiple slots.
2. Whether guidance suggests:
   - Uploading **one combined PDF per category**.
   - Uploading **individual documents** separately.
   - Any hints about the **expected structure** of combined documents (e.g., “combine your payslips into one document”).
3. **Technical constraints**, if stated:
   - Accepted file formats.
   - Per-file maximum sizes.
   - Per-application total file count or total size limits.
4. Any **warnings** or advice about document quality, certification, translation, or labelling.

If upload-slot behaviour or file structure is **not clearly documented**, explicitly state “not specified / unclear” instead of guessing.

### 3.4 Design normalized templates

Based on the above, design a set of **internal, app-friendly templates**.

Define a conceptual structure like:

```jsonc
VisaPackTemplate {
  country_code: "AU" | "CA" | "US" | "UK" | "NZ",
  visa_family: "Skilled" | "Student" | "Partner" | "Visitor" | "Humanitarian" | "Other",
  visa_code_or_program: "subclass 500" | "Express Entry – FSW" | "Skilled Worker" | ...,
  human_name: "Australia – Student visa (subclass 500)",
  description: "High-level summary of what this visa is for",
  volatility_level: "low" | "medium" | "high",   // how often requirements change (roughly)
  categories: [
    {
      id: "identity_documents",
      label: "Identity documents",
      description: "Passport, birth certificate, national ID, etc.",
      example_documents: [
        "Current passport",
        "Birth certificate",
        "..."
      ],
      typical_portal_section_label: "Passport/ID" | null,
      recommended_packaging: "one_pdf_per_category" | "single_application_pdf" | "per_document",
      priority: "required" | "strongly_recommended" | "optional" | "visa_stream_specific",
      notes: "Summarise any subtlety, e.g. certain documents only for some streams"
    },
    // ...
  ],
  disclaimer_snippet: "Short text to show in the UI reminding users to verify against official guidance."
}
```

You do **not** need to produce code; just define and use a consistent schema throughout your report. If you propose a different structure, make sure it is clearly documented and easy to consume by an implementation agent later.

### 3.5 Volatility and maintenance

For each visa template:

1. Comment on how **stable** the requirements appear:
   - “Requirements page shows last major update in [year].”
   - “Program is currently under review / recent reforms.”
2. Suggest how often that template should be **re-validated** (e.g., annually, on major policy announcements, etc.).
3. Suggest how the app should be architected so that templates can be **updated externally** (e.g., loaded from JSON in a config directory or remote source) without needing an application recompile.

---

## 4. Non-Goals and Legal/Safety Constraints

You must **not**:

- Provide legal advice, visa eligibility assessment, or guarantee that satisfying these evidence categories leads to approval.
- Re-interpret the law or policy; stay close to how official checklists describe evidence categories.
- Invent undocumented requirements or simplify them into misleading rules.

Instead:

- Treat everything as **“organisation templates”** and **“example structures”**.
- Where official guidance is ambiguous or varies substantially between streams or case types, label that clearly as **“uncertain / variable”**.

For each country and visa template, design a **short disclaimer string** that a UI can show, for example:

> “This pack is a general organisational template based on public guidance. Immigration rules change often. Always check the latest official instructions for your visa, and treat this pack as a helper only, not legal advice.”

---

## 5. Deliverables

You must produce at least the following artefacts for the human strategist and for the later implementation agent.

### 5.1 Research report

File: **`research_report_immigration_visa_evidence_packs.md`**

Content requirements:

1. **Overview section** per country:
   - Brief description of the main immigration system structure.
   - List of visa families you selected and why (e.g., “high individual demand”, “complex evidence”).

2. **Visa template catalog**:
   - For each template, a short subsection with:
     - Country, visa family, visa code/program name, human-readable name.
     - Rationale for including this template in Phase 1 vs Phase 2.

3. **Per-template tables**:
   - For each visa template, a table with at least:
     - Category ID.
     - Category label (user-facing).
     - Example documents.
     - Typical portal upload label/section (if known).
     - Recommended packaging strategy (one PDF per category / one application PDF / per document).
     - Priority level.
     - Notes (including uncertainty and caveats).

4. **Packaging guidance summary**:
   - For each country, summarize patterns:
     - Where portals clearly encourage combined PDFs per category.
     - Where they seem to expect per-document uploads.
     - Any key limits (e.g., file size) that should shape our compile strategies.

5. **Volatility and maintenance plan**:
   - Identify which visas are relatively stable vs frequently changing.
   - Recommend a re-validation cadence (e.g., review AU/CA/UK high-volume visas at least annually).

6. **Risk & UX implications**:
   - List main risks (e.g., outdated templates, over-reliance by users).
   - Suggest UX mitigations (e.g., explicit “last updated” dates, prompts to confirm the user has checked current official instructions).

### 5.2 Template schema proposal

Within the report (or as a short appendix), define a **concrete schema** for a `VisaPackTemplate` catalog (e.g., JSON or YAML shape). Include at least one fully worked example per country.

Later build agents will use this schema to:

- Store templates on disk.
- Let the app load them dynamically.
- Drive the classification and packaging UI.

### 5.3 Implementation handover section

At the end of the report, add a distinct section titled:

> “Implementation Handover: Immigration / Visa Evidence Packs”

In this section, summarise for the future implementation agent:

1. Which visa templates you recommend for **Phase 1** (initial release).
2. Which templates should be **Phase 2 or later** due to complexity or volatility.
3. Any **strong packaging preferences** revealed by research (e.g., “For AU Partner visas, strongly recommend one combined PDF per category X/Y/Z because portals have only a small number of slots”).

---

## 6. Quality Expectations

- **Completeness over breadth**: it is better to do a solid job on a **smaller set of high-value visa families** than to shallowly skim every possible subclass.
- **Traceability**: when you state something important (e.g., “this category is required”), you should either quote or clearly paraphrase official language and note the source page.
- **Clarity**: write so that a non-lawyer engineer can implement templates and a UX designer can understand how to present categories and packs to users.
- **Explicit uncertainty**: when you are unsure, say so and explain why (e.g., conflicting guidance, portal not documented, etc.).

This brief is solely about **research and template design**. Actual implementation of the pack builder will be handled by a separate build prompt once this research is complete.
