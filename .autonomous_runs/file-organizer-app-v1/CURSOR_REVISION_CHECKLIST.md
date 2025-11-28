# Cursor Revision Checklist: FileOrganizer Documentation Updates

**Date**: 2025-11-27
**Updated**: 2025-11-27 (Post-GPT Strategic Review)
**Purpose**: Address scope creep, missing details, and alignment issues across the three core planning documents
**Priority**: CRITICAL - Must implement before v1.0 development kickoff
**Status**: ✅ **ALL ITEMS MARKED AS MUST-IMPLEMENT FOR v1.0**

---

## ⚠️ v1.0 SCOPE DISCIPLINE APPLIED

**Per GPT Strategic Review (2025-11-27)**:
- ✅ All checklist items below are **REQUIRED for v1.0**
- ✅ Country-specific packs, Premium infrastructure → **DEFERRED to Phase 2/2.5**
- ✅ Core pack system (generic templates), triage UI, export engines → **v1.0 MUST-HAVE**

**This checklist focuses on v1.0 foundations. Phase 2/2.5 features are documented in MASTER_BUILD_PLAN Section 14.**

---

## Document 1: MASTER_BUILD_PLAN_FILEORGANIZER.md

### 1.1 Scope Correction: v1 vs Phase 2 Packs

**Issue**: Tier 5 currently includes both generic packs AND country-specific packs, which is too ambitious for 1-2 developers alongside Tiers 1-4.

**Action**:
```markdown
- [ ] In Tier 5 "Scenario Pack System", explicitly scope v1 to:
      - Generic Tax Pack (no country thresholds)
      - Generic Immigration Pack (identity/relationship/finances only)
      - Generic Legal Timeline Pack (chronology + evidence bundle)
- [ ] Create new section "Phase 2: Country-Specific Packs" after Tier 6
      - Move AU BAS Rideshare, AU/UK immigration packs here
      - Reference implementation_plan_tax_immigration_legal_packs.md as blueprint
      - Note: "Phase 2 begins after v1.0 launch and user feedback"
```

**Location**: Section "Tier 5: Scenario Pack System (Phases 35-43)"

---

### 1.2 Hardware Constraints & Resource Management

**Issue**: LLM/OCR strategy mentions local models (Qwen2-7B, Tesseract) but doesn't address 8-16GB RAM constraints or async processing.

**Action**:
```markdown
- [ ] Add subsection "2.X Hardware Assumptions & Resource Modes" under Tier 2:

      ### Hardware Assumptions & Resource Modes

      **Target Specs**:
      - Optimized for: 16GB RAM, modern CPU (2020+)
      - Minimum viable: 8GB RAM (requires "Reduced Resource Mode")

      **Processing Modes**:
      1. **Full Local Mode** (16GB+):
         - Tesseract OCR + Qwen2-7B classification
         - Embeddings + local vector search
         - Fully offline capable

      2. **Reduced Resource Mode** (8-12GB):
         - Tesseract OCR (lighter models)
         - Cloud-assisted classification (GPT-4o Mini or Claude Haiku)
         - Cached embeddings, limited local vector DB

      3. **Cloud-First Mode** (Any RAM):
         - Cloud OCR (Azure Document Intelligence or Google Vision)
         - Cloud classification (GPT-4o or Claude Sonnet)
         - User data encrypted in transit, deleted after processing

      **Asynchronous Processing**:
      - All OCR/classification runs in background job queue
      - Progress indicators: "Processing 45/120 documents (37%)..."
      - Pause/resume support (state saved to disk)
      - User can continue using app while processing runs

      **Settings UI Integration**:
      - Tier 1 Settings includes: Processing Mode dropdown
      - "Accuracy vs Privacy" slider (cross-reference fileorganizer_product_intent_and_features.md)
      - Estimated RAM usage displayed per mode

      **Risk Mitigation**: See Risk Matrix section 8.1 "Technical Risks"

- [ ] Cross-reference this with:
      - Risk Matrix section on "LLM Classification Accuracy <80%"
      - Strategic doc's "Accuracy vs Privacy" settings
      - Telemetry section (log processing times, not content)
```

**Location**: After "Tier 2: AI & OCR Processing Pipeline (Phases 10-16)"

---

### 1.3 Telemetry Architecture (Level 0/1/2)

**Issue**: Tier 1 mentions telemetry settings but doesn't document the Level 0/1/2 design from product intent doc.

**Action**:
```markdown
- [ ] Add subsection "1.X Telemetry Architecture" under Tier 1:

      ### Telemetry Architecture

      FileOrganizer uses a **privacy-first, opt-in telemetry system** with three levels:

      **Level 0: Minimal (Default)**
      - Anonymous usage ping (app launched, version, OS)
      - Crash reports (stack traces, NO file paths or content)
      - NO file names, paths, document text, or user data

      **Level 1: Aggregated Stats (Opt-In)**
      - File type counts (e.g., "Processed 50 PDFs, 30 JPGs")
      - Feature usage (e.g., "Used OCR 45 times, scenario pack 2 times")
      - Performance metrics (e.g., "Avg classification time: 2.3s per doc")
      - Pack usage (e.g., "Tax pack started 1 time, completed 0 times")
      - Error rates (e.g., "OCR failed on 3/100 documents")
      - Still NO content, file names, or paths

      **Level 2: Enriched (Discouraged for Sensitive Domains)**
      - NOT implemented in v1.0
      - May include anonymized error context in future (with explicit opt-in)
      - Never for tax, immigration, or legal packs

      **Implementation**:
      - Tier 1: Telemetry client initialized, Level 0 by default
      - Tier 4: Settings UI for telemetry preferences (Level 0/1 toggle)
      - Tier 6: Performance and pack-usage metrics added (Level 1 only)

      **Privacy Guarantee**:
      - NO file names, file paths, document text, or OCR content EVER sent
      - User can review exact telemetry payload before opt-in (Settings → View Telemetry Data)
      - Open-source telemetry client code for audit

      **Reference**: See fileorganizer_product_intent_and_features.md Section 7 "Privacy & Telemetry"

- [ ] In Tier 1 Step 5 (Settings UI), change:
      FROM: "Preferences dialog (theme, telemetry opt-in)"
      TO: "Preferences dialog (theme, telemetry level [0/1], processing mode, accuracy vs privacy slider)"

- [ ] In Tier 6 (Testing & Polish), add bullet:
      - "Implement Level 1 telemetry hooks for performance and pack-usage metrics (NO CONTENT)"
```

**Location**: After "Tier 1: Core Infrastructure & Foundation (Phases 1-9)"

---

### 1.4 Conversion & Packaging Primitives

**Issue**: MASTER_BUILD_PLAN mentions exports and packs but not the underlying generic conversion subsystem.

**Action**:
```markdown
- [ ] Add new phase "Tier 3.5: Conversion & Packaging Primitives (Phases 25-28)" BEFORE Tier 4:

      ## Tier 3.5: Conversion & Packaging Primitives (Phases 25-28)

      Generic document transformation layer used by both general-purpose exports and scenario packs.

      ### Phase 25: Image → PDF Conversion
      - Convert JPG/PNG/HEIC to PDF (using PIL/Pillow or img2pdf)
      - Preserve EXIF metadata (date, location if enabled)
      - Batch conversion with progress indicator
      - Quality presets: Standard (72 DPI, compressed) vs Premium (300 DPI, lossless)

      ### Phase 26: Office → PDF Conversion
      - Convert DOCX/XLSX/PPTX to PDF
      - Local conversion: LibreOffice headless (free, slower)
      - Cloud conversion: Azure/Google APIs (premium tier, faster, requires opt-in)
      - Fallback: Prompt user to manually export if conversion fails

      ### Phase 27: PDF Operations
      - Merge multiple PDFs into single file (using PyPDF2 or pdfrw)
      - Split PDF by page range or bookmark
      - Add bookmarks/table of contents (for evidence bundles)
      - Add page numbers and headers/footers
      - OCR non-searchable PDFs (make text-searchable)

      ### Phase 28: Text/Markdown → PDF
      - Render plain text or Markdown to PDF (using weasyprint or wkhtmltopdf)
      - Support templates (header, footer, styling)
      - Used for summary reports, cover pages, disclaimers

      **Export Engine Abstraction**:
      - Standard Engine (Local): Free, uses open-source libs (PIL, PyPDF2, weasyprint)
      - Premium Engine (Cloud-Assisted): Pro/Business tiers, uses commercial APIs for speed/quality
      - User choice per export operation (if on premium tier)

      **Integration Points**:
      - Tier 4 (General Export): Use primitives for ad-hoc "Export → PDF Bundle"
      - Tier 5 (Scenario Packs): Pack export recipes call these primitives
      - Tier 6 (Polish): Add quality presets UI (Standard vs Premium dropdown)

      **Deliverables**:
      - conversion_engine.py (image, office, PDF, text conversion classes)
      - export_engine.py (orchestrates conversions per export recipe)
      - Unit tests for each conversion type

- [ ] Update Tier 4 (UI/UX) and Tier 5 (Packs) references:
      - Change "Implement PDF bundle export" to "Wire PDF bundle export to Conversion Primitives (Tier 3.5)"
      - Change "Implement spreadsheet export" to "Wire spreadsheet export to Conversion Primitives"
```

**Location**: Insert new section between Tier 3 and Tier 4, renumber subsequent tiers

---

### 1.5 Multi-Language / i18n Integration

**Issue**: Global profile supports language labels but i18n strategy isn't explicitly called out in build plan.

**Action**:
```markdown
- [ ] In Tier 4 (UI/UX), add bullet to Phase 30 (Organization Management UI):
      - "Integrate i18n library (react-i18next or similar) for all UI strings"
      - "Support locale selection in Settings (English, French, Spanish, Mandarin, Hindi as initial targets)"
      - "Ensure pack metadata and categories support multi-locale labels from day one (even if only English populated initially)"

- [ ] In Tier 5 (Scenario Packs), add note to Pack Schema phase:
      - "Pack YAML schema MUST include `locales` field for all user-facing strings (name, description, category labels)"
      - "Classification hints SHOULD include keywords in all supported locales (e.g., 'bank statement' + 'relevé bancaire' + 'estado de cuenta')"
      - "Example: See implementation_plan Section 1.2.1 metadata.name locales"
```

**Location**: Tier 4 Phase 30, Tier 5 Pack Schema phase

---

### 1.6 Product Vision Clarity: General-First, Legal-Later

**Issue**: MASTER_BUILD_PLAN adopts the pivot to general-purpose + scenario packs, but should be more explicit about legal features being Phase 2+.

**Action**:
```markdown
- [ ] In "Product Vision" section (before Tier 1), add paragraph:

      ### v1.0 Success Criteria: General-Purpose Foundation

      FileOrganizer v1.0 targets **general-purpose file organization** with scenario packs as premium features:

      **v1.0 Core Success Metrics**:
      - General users successfully organize 100+ documents using rules, staging, and conversions
      - 3 generic scenario packs (tax, immigration, legal timeline) used by early adopters
      - Multi-platform support (Windows, macOS, Linux)
      - Local-first privacy with opt-in cloud assistance

      **Phase 2+ (Post-v1.0)**:
      - Deep legal features (firm workflows, advanced courtroom timelines, multi-case management)
      - Country-specific scenario packs (AU BAS, UK Self Assessment, US I-130, etc.)
      - Advanced pack features (multi-period, AI suggestions, integrations with tax software)
      - Enterprise features (team sync, audit logs, admin controls)

      **Architecture Principle**:
      While v1.0 focuses on general users, the architecture MUST remain flexible for future legal/professional workflows. Avoid premature optimization for heavy legal features, but ensure core primitives (conversion, packs, triage) are robust enough to extend.

      **Reference**: See RIGOROUS V2 strategic analysis (Section 2: Strategic Imperatives) and risk matrix warning against segment dilution.
```

**Location**: Insert before "Tier 1: Core Infrastructure & Foundation"

---

## Document 2: research_report_tax_immigration_legal_packs.md

### 2.1 Assumptions & Unknowns Appendix

**Issue**: Report notes common packaging patterns but lacks explicit "verified vs unknown" constraints per domain/country.

**Action**:
```markdown
- [ ] Add new appendix "Appendix E: Assumptions & Unknowns per Domain/Country" with table format:

      ## Appendix E: Assumptions & Unknowns per Domain/Country

      This appendix lists **verified facts** vs **unknowns/assumptions** for each jurisdiction's submission portals and evidence requirements. Pack authors should treat unknowns conservatively (e.g., split large files) or prompt users for manual confirmation.

      ### Tax/BAS Domain

      | Country | Portal/Method | Verified Constraints | Unknowns/Assumptions | Conservative Approach |
      |---------|---------------|---------------------|---------------------|----------------------|
      | AU | myGov portal | PDF preferred, likely 5MB limit per attachment | Exact file size limit not documented publicly | Split PDFs >4MB, test with smaller batches |
      | UK | HMRC MTD (from 2026) | Digital records required, direct software submission | File size limits for non-MTD submissions | Use MTD-compatible software, keep PDFs <5MB |
      | US | IRS e-file (via tax software) | Most tax software handles PDF attachments for audits | Portal limits vary by software provider | Check TurboTax/TaxAct limits, keep <10MB per category |
      | CA | CRA My Account | Online filing, PDF attachments for audits | File size limits not documented | Keep PDFs <5MB, test with CRA portal |
      | NZ | myIR | Digital filing, PDF attachments | File size limits not documented | Keep PDFs <5MB |

      ### Immigration Domain

      | Country | Portal/Method | Verified Constraints | Unknowns/Assumptions | Conservative Approach |
      |---------|---------------|---------------------|---------------------|----------------------|
      | AU | ImmiAccount | Max 60MB per file (verified), PDF/JPEG/PNG | Number of files limit unclear | Aim for <50 files total, <50MB per file |
      | UK | UKVI online | 2-6MB typical per file (not strict limit) | Exact file size and count limits | Keep <5MB per file, <30 files total |
      | US | USCIS online (I-130 only) | Physical mail still common, digital limits vary | Online portal file size/count limits | Physical submission: no limits; Online: <10MB per file |
      | CA | IRCC digital (2025+) | Max 4MB per file (verified), OCR required | Total upload size limit unclear | Aim for <100 files, <4MB each |
      | NZ | INZ online | Max 10MB per file (verified), PDF/JPEG | Number of files limit unclear | Aim for <50 files, <10MB each |

      ### Legal Domain

      | Jurisdiction | Court Type | Verified Constraints | Unknowns/Assumptions | Conservative Approach |
      |--------------|-----------|---------------------|---------------------|----------------------|
      | UK | Civil/Family Courts | CPR 32 PD 27.8 (pagination, indexing, OCR required) | File size limits vary by court | Follow court-specific practice directions, keep <20MB per PDF |
      | US | Federal/State | Varies by court; some require physical, some allow electronic | Electronic filing limits vary widely | Check local court rules, keep <10MB per file |
      | AU/CA/NZ | Common-law courts | Similar to UK (indexing, OCR), but specific rules vary | Court-specific electronic filing limits | Follow local practice directions, keep <20MB |

      **Note for Pack Authors**:
      - When constraints are **verified**, encode them in pack `export_recipes` (e.g., `max_file_size_mb: 4` for CA immigration).
      - When constraints are **unknown**, use conservative defaults and optionally warn user: "Check [portal name] for current file size limits."
      - As users report issues or successes, update this appendix and corresponding pack configs.
```

**Location**: After existing appendices (A, B, C, D), before "Conclusion"

---

### 2.2 Profession-Specific Evidence Tables

**Issue**: Report describes generic categories but lacks grounded profession-level detail for low-margin sole traders (rideshare, delivery, cleaners, etc.).

**Action**:
```markdown
- [ ] In each Tax/BAS country section (1.1 AU, 1.2 UK, 1.3 US, 1.4 CA, 1.5 NZ), add subsection:

      #### [Country] - Priority Profession Templates for Low-Margin Sole Traders

      The following table maps 3-5 high-priority professions to typical evidence categories, grounded in platform/industry norms. These will feed directly into profession-specific pack templates.

      **[Country] Profession Evidence Matrix**:

      | Profession | Typical Income Docs | Typical Expense Categories | Profession-Specific Notes |
      |------------|---------------------|---------------------------|--------------------------|
      | **Rideshare Driver** (Uber, Ola, DiDi) | Platform weekly/monthly statements, annual tax summaries, bank deposits | Fuel (30-40% of gross), vehicle maintenance, phone (50-80% business use), home office (optional) | Platform statements often include GST/tax breakdown; logbook required if claiming >5,000 km (AU/NZ) or using actual expenses (US/UK) |
      | **Delivery Courier** (DoorDash, Menulog, Uber Eats) | Platform payout summaries, bank deposits | Fuel (35-45% of gross), vehicle/bike maintenance, insulated bags, phone, equipment (helmets, locks) | Higher km/dollar ratio than rideshare; may use bike/e-bike (different depreciation rules) |
      | **Cleaner** (Domestic, Commercial) | Direct client invoices, cash receipts | Cleaning supplies, equipment (vacuum, mop), vehicle (if traveling to clients), phone | Lower transaction volume (20-50 clients/month); invoice-based income; equipment costs significant |
      | **Tutor / Freelance Teacher** | Direct client payments, platform fees (Wyzant, Tutor.com) | Home office (often 50-100% business use), internet, books/materials, software subscriptions | Mostly invoice-based; lower vehicle use; home office deduction common |
      | **Handyman / Tradie** | Direct invoices, cash/check payments | Tools and equipment, vehicle (high business use %), materials/supplies, insurance | Capital equipment (tools) may be depreciated; vehicle is major expense (40-60% business use) |

      **Pack Template Implications**:
      - Create profession-specific tax pack variants (e.g., `tax_au_bas_rideshare_v1`, `tax_au_bas_delivery_v1`, `tax_au_bas_cleaner_v1`)
      - Each variant pre-populates `classification_hints` with profession-specific keywords (platform names, merchant patterns)
      - Typical expense ratios shown in pack guidance (e.g., "Rideshare drivers typically spend 30-40% of gross income on fuel")

- [ ] Repeat this table structure for UK, US, CA, NZ sections with country-specific platforms and rules
      - Example: UK rideshare drivers use Uber UK, Bolt; simplified mileage rate often more beneficial
      - Example: US delivery drivers must distinguish between employee (W-2) vs contractor (1099-NEC) status
```

**Location**: Add to sections 1.1.5 (AU), 1.2.5 (UK), 1.3.5 (US), 1.4.5 (CA), 1.5.5 (NZ) under "Profession-Specific Templates"

---

### 2.3 Clear Scope Boundary: No Advice, No Eligibility

**Issue**: Report distinguishes structures from rules but should state this more forcefully.

**Action**:
```markdown
- [ ] In "Executive Summary" → "Design Implications for FileOrganizer", add bullet:

      **Scope Boundary (Critical)**:
      - Pack templates organize and package evidence based on official guidance and common practices.
      - Packs do NOT compute eligibility, recommended deduction amounts, visa likelihood, or legal conclusions.
      - Any feature that crosses into advice (e.g., "You should claim $X deduction" or "Your visa application is likely to succeed") is explicitly OUT OF SCOPE.
      - Disclaimers must reinforce this at every touchpoint (pack selection, triage, exports).

- [ ] In "Part 4: Cross-Domain Design Implications" → Section 4.5 "Safety and Disclaimers", add paragraph:

      **Explicit Non-Advice Policy**:

      FileOrganizer packs are **organizational tools**, not advisory tools. The following are explicitly prohibited in pack logic:

      ❌ **Prohibited**:
      - Calculating tax liabilities or deduction amounts
      - Assessing visa eligibility or likelihood of approval
      - Providing legal opinions or case strength assessments
      - Recommending specific actions (e.g., "You should register for GST")

      ✅ **Permitted**:
      - Organizing documents by category (Income, Expenses, Relationship Evidence, etc.)
      - Displaying category totals (e.g., "Total Fuel Expenses: $5,432.10")
      - Showing thresholds as reference (e.g., "GST registration required if turnover ≥$75K")
      - Flagging missing evidence (e.g., "No fuel receipts uploaded yet")
      - Exporting structured summaries (spreadsheet, PDF bundles, timelines)

      **Implementation Guidance**:
      - Use passive, neutral language in all pack UI and exports (e.g., "Category total" NOT "Deduction amount")
      - Never display green checkmarks or "Approved" language suggesting official validation
      - Always include disclaimers in prominent locations (see Section 5.2)
```

**Location**: Executive Summary + Part 4 Section 4.5

---

### 2.4 Multi-Period & Audit-Readiness Context

**Issue**: Implementation plan mentions multi-period as future enhancement, but research report doesn't ground this in real-world examples.

**Action**:
```markdown
- [ ] In "Part 1: Tax/BAS Domain Summary" → Section 1.6 "Invariants vs Variations", add subsection:

      #### Multi-Period and Audit-Readiness Considerations

      **Real-World Use Cases**:

      1. **Quarterly BAS Aggregation (AU)**:
         - Sole traders file quarterly BAS (Q1, Q2, Q3, Q4)
         - Annual tax return requires year-end summary of all 4 quarters
         - Audit request from ATO may ask for "all BAS evidence for 2024-25 financial year"
         - **Pack Implication**: Support "2024-25 BAS Pack" with 4 sub-packs (Q1-Q4), with year-end aggregation export

      2. **Multi-Year Cohabitation Evidence (Immigration)**:
         - De facto / common-law partner visas require 12-24 months of cohabitation proof
         - Stronger applications show 2-3+ years of evidence
         - **Pack Implication**: Support date-range filtering (e.g., "Show evidence from Jan 2023 - Dec 2025") and chronological timeline exports spanning multiple years

      3. **Litigation Document Discovery (Legal)**:
         - Civil cases may span 2-5 years from incident to trial
         - Evidence bundles must include all relevant documents across entire period
         - **Pack Implication**: Legal timeline pack should support multi-year chronologies with date filtering and period-based sections

      **v1 vs v2 Scope**:
      - **v1 Packs**: Single-period only (e.g., "2024 Q3 BAS", "2025 Immigration Application", "Case 12345")
      - **v2 Enhancement**: Multi-period packs with:
        - Period selector (Q1/Q2/Q3/Q4 or custom date range)
        - Aggregated exports (year-end summary, multi-year timeline)
        - Period-based validation (e.g., "Q1 complete, Q2 missing, Q3 in progress, Q4 not started")

      **Design Consideration**:
      Pack schema should allow for future multi-period extension without breaking v1 packs. Consider `period` metadata field (optional in v1, required in v2).
```

**Location**: Part 1 Section 1.6, after "Variations" subsection

---

## Document 3: implementation_plan_tax_immigration_legal_packs.md

### 3.1 Schema Simplification: Core v1 vs Advanced v2

**Issue**: Full schema (thresholds, validation, form mappings) is heavy for v1 and carries liability risk if values drift out-of-date.

**Action**:
```markdown
- [ ] In Section 1.2 "Full Schema Specification", add intro paragraph:

      ### Schema Versioning: Core v1 vs Advanced v2 Fields

      The pack schema is designed for long-term extensibility but will be **implemented incrementally** to reduce v1 complexity and liability risk:

      **Core v1 Fields** (Required for first 4 packs):
      - `metadata` (id, name, domain, country, version, description, tags)
      - `disclaimers` (primary, additional, display_contexts)
      - `categories` (id, name, parent, description, typical_documents, classification_hints)
      - `mappings` (export sections only, NOT detailed form fields)
      - `export_recipes` (per-category PDFs, spreadsheet summary, index)

      **Advanced v2 Fields** (Deferred to Phase 2):
      - `thresholds` (country-specific values like GST registration)
      - Detailed `mappings.form_fields` (category → tax form field G1/1A/1B)
      - Complex `validation` rules (timeframe coverage, completeness checks)
      - Multi-period pack logic
      - AI suggestion hooks

      **Rationale**:
      - **v1 Risk Mitigation**: Avoid encoding country-specific thresholds or form fields that may change, causing liability if users rely on outdated values.
      - **v1 Simplicity**: Focus on core organization and packaging, not form-filling or eligibility checks.
      - **v2 Enhancement**: After v1 launch and user feedback, selectively add Advanced fields with expert review and explicit versioning.

      **Implementation Guidance**:
      - Pack YAML validator should mark Advanced v2 fields as OPTIONAL in v1
      - If Advanced field present, log warning: "Field `thresholds` is marked Advanced v2; use with caution"
      - First 4 packs (Generic Tax, AU BAS Rideshare, Generic Immigration, Generic Legal Timeline) use ONLY Core v1 fields

- [ ] Update Section 1.2.4 "Mappings Block":
      - Add note at top: "v1 Implementation: Only export section mappings required (e.g., category → PDF bundle section). Detailed form field mappings (G1, 1A, 1B) deferred to v2."
      - Mark `form_fields` example with comment: `# ADVANCED v2 - NOT REQUIRED FOR v1`

- [ ] Update Section 1.2.6 "Thresholds Block":
      - Add note at top: "v2 Feature - NOT REQUIRED FOR v1. Thresholds carry liability risk if outdated; defer until after user feedback and expert review."

- [ ] Update Section 1.2.7 "Validation Block":
      - Add note: "v2 Feature - SIMPLIFIED IN v1. v1 validation limited to: 'at_least_one_document' per category. Complex timeframe/coverage checks deferred to v2."

- [ ] Update Section 2.1 "Prioritized Pack List" → Tier 1 pack descriptions:
      - Add note for each pack: "Uses Core v1 schema only (no thresholds, no form field mappings, simplified validation)"
```

**Location**: Section 1.2 intro, 1.2.4, 1.2.6, 1.2.7, Section 2.1

---

### 3.2 Export Engine Abstraction: Standard vs Premium

**Issue**: Earlier design called for quality tiers (free local vs premium cloud), but implementation plan doesn't expose this as first-class abstraction.

**Action**:
```markdown
- [ ] Add new Section 3.X "Export Engine Abstraction" after Section 3.2:

      ## 3.X Export Engine Abstraction

      FileOrganizer supports **two export quality tiers** to balance cost, performance, and quality:

      ### Standard Engine (Free, Local)

      **Capabilities**:
      - Image → PDF: PIL/Pillow or img2pdf (72 DPI, compressed)
      - Office → PDF: LibreOffice headless (slower, basic formatting)
      - PDF Operations: PyPDF2 or pdfrw (merge, split, bookmark)
      - Text/Markdown → PDF: weasyprint or wkhtmltopdf (basic styling)
      - OCR: Tesseract (local, slower, ~85-90% accuracy)

      **Performance**:
      - Conversion time: ~1-3 seconds per document (local CPU)
      - Quality: Good for most use cases, acceptable for tax/legal packs

      **Privacy**:
      - Fully local, no cloud uploads
      - Works offline

      **Pricing**: Free (all tiers)

      ---

      ### Premium Engine (Cloud-Assisted, Pro/Business Tiers)

      **Capabilities**:
      - Image → PDF: High-resolution (300 DPI, lossless), cloud-optimized compression
      - Office → PDF: Azure Document Conversion or Google Drive API (faster, better formatting)
      - PDF Operations: Commercial libs (e.g., PDFtk Server) for advanced features (encryption, digital signatures)
      - Text/Markdown → PDF: High-quality rendering (custom fonts, advanced layouts)
      - OCR: Azure Document Intelligence or Google Vision (cloud, faster, ~95%+ accuracy)

      **Performance**:
      - Conversion time: ~0.5-1 second per document (cloud APIs, parallel processing)
      - Quality: Excellent, suitable for high-stakes immigration applications or court submissions

      **Privacy**:
      - User data encrypted in transit (TLS 1.3)
      - Deleted immediately after processing (no retention)
      - Requires explicit user consent (checkbox: "I consent to cloud processing for higher quality exports")

      **Pricing**: Pro tier ($9.99/mo) or Business tier ($49.99/mo)

      ---

      ### Export Recipe Integration

      Pack `export_recipes` should be **engine-agnostic**. The user or app-level settings select the engine at runtime:

      ```yaml
      export_recipes:
        - id: "pdf_bundle"
          type: "pdf_bundle"
          # NO engine specified in pack config
          # Engine selected by user preference or tier at export time
      ```

      **UI Flow**:
      1. User clicks "Export" in pack instance
      2. If user is on Free tier → Standard Engine (no choice)
      3. If user is on Pro/Business tier → Show dialog:
         - "Choose export quality: Standard (Free, Local) or Premium (Cloud-Assisted, Faster, Higher Quality)"
         - Explain privacy implications (cloud upload with encryption and deletion)
         - User selects → Engine applied to all export recipes

      **Settings Integration**:
      - Global preference: "Default Export Engine: Standard | Premium (if available)"
      - Per-export override: "Use Premium for this export only" (checkbox)

      **Telemetry** (Level 1, Opt-In):
      - Log export engine used (Standard vs Premium) and export type (PDF bundle, spreadsheet, etc.)
      - Do NOT log file names, content, or user data

      ---

      ### Implementation Plan

      **Milestone 1 (Weeks 1-3)**:
      - Implement Standard Engine (local libs only)
      - Export engine abstraction interface (abstract class or protocol)

      **Milestone 3 (Weeks 7-10)**:
      - Wire Standard Engine to pack export recipes
      - Test with AU BAS Rideshare pack

      **Phase 2 (Post-v1.0)**:
      - Implement Premium Engine (cloud APIs)
      - Add tier-gating logic and consent UI
      - Performance benchmarks (Standard vs Premium)

- [ ] Update Section 1.2.5 "Export Recipes Block":
      - Add note: "Export recipes are engine-agnostic. User tier and preferences select Standard (local) or Premium (cloud-assisted) engine at runtime."
      - Remove any engine-specific parameters from recipe examples

- [ ] Update Section 7 "Prioritized Milestones" → Milestone 3:
      - Change "Implement PDF bundle export recipe" to "Wire PDF bundle export to Standard Engine (local)"
      - Add Milestone 3 deliverable: "Export engine abstraction interface (standard_engine.py)"
```

**Location**: New Section 3.X after Section 3.2, updates to 1.2.5 and Section 7

---

### 3.3 PPTX Exports as First-Class Type

**Issue**: Earlier spec called for optional PPT decks for immigration packs, but implementation plan only mentions PDFs and timelines.

**Action**:
```markdown
- [ ] In Section 1.2.5 "Export Recipes Block", add PPTX export type after `summary_pdf`:

      #### Export Recipe Type: `presentation` (PPTX)

      **Purpose**: Generate PowerPoint presentation for visual evidence summaries (immigration, legal, general portfolios).

      **v1 Scope** (Simple slide-per-category):
      ```yaml
      - id: "immigration_pptx_summary"
        type: "presentation"
        format: "pptx"  # Microsoft PowerPoint
        name: "Immigration Evidence Presentation"
        description: "One slide per evidence category with key documents listed"
        template: "immigration_summary_template.pptx"  # Optional template file
        slides:
          - title: "Financial Evidence"
            category_filter: "financial"
            content:
              - type: "category_summary"  # Auto-generated text
                text: "{category_name}: {document_count} documents, covering {date_range}"
              - type: "document_list"  # Bulleted list of key documents
                max_items: 10
                format: "• {document_name} ({date})"

          - title: "Relationship Timeline"
            category_filter: "relationship"
            content:
              - type: "timeline_visualization"  # Simple timeline graphic
                events: [ "Met: Jan 2023", "Moved in: June 2023", "Engaged: Dec 2023", "Married: June 2024" ]
              - type: "photo_grid"  # 4-6 representative photos
                max_photos: 6
                layout: "2x3"
      ```

      **v2 Scope** (Advanced features, Phase 2):
      - Document thumbnails on slides
      - Statistics and charts (e.g., "Cohabitation evidence: 18 documents across 24 months")
      - Custom slide templates (user-uploaded or themed)
      - Speaker notes with document details

      **Export Engine**:
      - Standard Engine: `python-pptx` library (free, basic layouts)
      - Premium Engine: Cloud rendering for advanced layouts (Phase 2)

      **Use Cases**:
      - Immigration: Visual summary of relationship evidence for case presentation
      - Legal: Case overview for client meetings or mediation
      - General: Portfolio presentations (e.g., "My 2024 Tax Prep Summary")

      **Implementation**:
      - Milestone 4 (Weeks 11-13): Add `presentation` export type to schema
      - Phase 2: Implement full PPTX generation using `python-pptx`

- [ ] Update Section 2.2.3 "Generic Immigration - Partner/Spouse" → Export section:
      - Add: "- Presentation (Optional): PPTX with one slide per category (Financial, Relationship, Cohabitation, Identity) and photo timeline"

- [ ] Update Section 7 "Prioritized Milestones" → Milestone 4:
      - Add deliverable: "presentation_exporter.py (PPTX generation using python-pptx, Phase 2 if time permits)"
```

**Location**: Section 1.2.5, Section 2.2.3, Section 7 Milestone 4

---

### 3.4 Pack-Specific Triage UX

**Issue**: Implementation plan discusses unknowns/corrections but doesn't align with master plan's rich staging/triage UI (before/after table, bulk actions, ops log).

**Action**:
```markdown
- [ ] Add new Section 4.X "Triage UX for Packs" after Section 4.2:

      ## 4.X Triage UX for Packs

      Pack-specific triage integrates with FileOrganizer's global staging/triage system (see MASTER_BUILD_PLAN Tier 3) while adding pack-aware features for efficiency.

      ### 4.X.1 Triage Screen Layout (Pack Context)

      **Left Sidebar: Pack Category Hierarchy**
      - Expandable tree showing all pack categories (Income → Rideshare, Expenses → Fuel, etc.)
      - Document count per category (e.g., "Rideshare Income (5)")
      - Visual indicators:
        - 🟢 Green: All documents reviewed and confirmed
        - 🟡 Yellow: Contains low-confidence or unreviewed documents
        - ⚪ Gray: Empty (no documents yet)
      - Click category → Filter main grid to show only that category's documents

      **Main Area: Document Grid**
      - Compact table view (optimized for 50-200 documents):
        - Thumbnail (small preview)
        - Filename (truncated)
        - Suggested Category (dropdown)
        - Confidence (✅ High ≥85%, ⚠️ Medium 60-85%, ❌ Low <60%)
        - Date (extracted)
        - Amount (extracted, if applicable)
        - Merchant/Counterparty (extracted)
        - Actions: ✏️ Edit, 🗑️ Delete
      - Sort by: Date (desc/asc), Confidence (low first), Category
      - Filter by: Category, Date range, Confidence threshold, "Unreviewed only"

      **Right Panel: Document Detail (on row click)**
      - Full document preview (PDF/image viewer)
      - Extracted metadata (editable):
        - Date, Amount, Merchant, Description
      - Category reassignment dropdown
      - "Save" button (green, prominent)
      - "Apply rule for future docs?" checkbox (see Section 4.2)

      **Bottom Bar: Completeness Checklist**
      - Pack-specific validation warnings:
        - "✅ Rideshare income: 5 documents (Q3 coverage: July-Sept)"
        - "⚠️ Fuel expenses: 0 documents. Did you upload fuel receipts? [Upload More]"
        - "✅ Phone expenses: 1 document"
      - "Ready to Export" button (disabled until critical warnings resolved)

      ---

      ### 4.X.2 Bulk Assignment Flows

      **Problem**: Reviewing 100+ documents one-by-one is painful. Pack triage MUST support efficient batch operations.

      **Bulk Actions**:

      1. **Select Multiple Rows** (Checkbox or Shift+Click)
         - Select all Uber statements from Q1 2025 → Assign to "Income → Rideshare" in bulk

      2. **Smart Grouping**:
         - Automatically group documents by:
           - Source vendor (all "Uber" docs together)
           - Date range (all "Jan 2025" docs together)
           - Probable category (all low-confidence "Fuel?" docs together)
         - Show grouped view: "15 Uber statements (Jan-Mar 2025) → Suggested: Rideshare Income [Assign All]"

      3. **Keyboard Shortcuts** (Power User Mode):
         - `↑/↓`: Navigate rows
         - `Enter`: Open detail panel
         - `C`: Change category (dropdown appears)
         - `S`: Save and move to next
         - `Ctrl+A`: Select all (in current filter)
         - `Ctrl+Shift+C`: Bulk assign selected to category

      4. **Automation Profiles** (from global staging system):
         - User creates rule: "All docs from uber.com → Rideshare Income"
         - Rule applied on next batch upload → Fewer manual corrections needed

      ---

      ### 4.X.3 Before/After Comparison (Ops Log Integration)

      Pack triage should inherit the global staging system's "before/after" view (MASTER_BUILD_PLAN Tier 3):

      **Before Approval** (Staging View):
      - All categorizations shown as "proposed" with confidence scores
      - User reviews and corrects
      - Changes tracked in ops log: "Changed doc_789 from 'Expenses → Other' to 'Expenses → Fuel'"

      **After Approval** (Committed View):
      - Pack state updated with final categories
      - Ops log preserved: "2025-11-27 11:00: User corrected 5 documents in Fuel category"
      - Rollback option: "Undo last batch of corrections" (if within 24 hours)

      ---

      ### 4.X.4 Mobile/Tablet Considerations (Phase 2)

      v1 prioritizes desktop (Windows/macOS/Linux), but pack triage UI should be designed for future mobile support:

      - **Touch-friendly**: Large tap targets for category selection
      - **Swipe gestures**: Swipe left/right to navigate documents, swipe up/down to change category
      - **Simplified grid**: Show fewer columns on small screens (thumbnail + category + confidence)

      ---

      ### Implementation

      **Milestone 2 (Weeks 4-6)**:
      - Basic triage grid with category sidebar and document detail panel
      - Single-document assignment (dropdown + save)

      **Milestone 4 (Weeks 11-13)**:
      - Bulk actions (multi-select, smart grouping)
      - Keyboard shortcuts
      - Before/after comparison (ops log integration)

      **Phase 2 (Post-v1.0)**:
      - Mobile-optimized triage UI
      - Advanced automation profiles (learned rules from corrections)
```

**Location**: New Section 4.X after Section 4.2

---

### 3.5 i18n Expectations for Packs

**Issue**: Implementation plan mentions `locales` but doesn't specify multi-language classification hints or pack selection behavior.

**Action**:
```markdown
- [ ] In Section 1.2.1 "Metadata Block", update `locales` example:

      ```yaml
      metadata:
        name:
          en: "Australia BAS - Rideshare Driver"
          fr: "Australie BAS - Chauffeur de covoiturage"
          es: "Australia BAS - Conductor de transporte compartido"
        description:
          en: "Organizes quarterly BAS evidence for Australian rideshare drivers..."
          fr: "Organise les preuves BAS trimestrielles pour les chauffeurs de covoiturage australiens..."
      ```

      **i18n Requirements**:
      - ALL user-facing strings (name, description, category labels, disclaimer text) MUST support multi-locale format
      - Minimum locales for v1: English (en), French (fr), Spanish (es), Mandarin (zh), Hindi (hi)
      - Packs can be partially localized (e.g., only `en` populated initially, other locales added later)

- [ ] In Section 1.2.3 "Categories Block", update `classification_hints` with multi-locale example:

      ```yaml
      classification_hints:
        keywords:
          en: [ "uber", "rideshare", "driver earnings", "trip earnings" ]
          fr: [ "uber", "covoiturage", "gains conducteur", "revenus trajets" ]
          es: [ "uber", "viaje compartido", "ganancias conductor", "ingresos viajes" ]
          zh: [ "uber", "共乘", "司机收入", "行程收入" ]
        # LLM classification uses ALL locale keywords for matching, not just user's selected language
      ```

      **Classification Logic**:
      - LLM should match against keywords in ALL supported locales, not just user's selected language
      - This improves accuracy for multilingual users (e.g., French-speaking user with English bank statements)

- [ ] Add new subsection "6.X i18n and Pack Selection":

      ## 6.X i18n and Pack Selection

      ### Pack Discovery and Locale Filtering

      **Pack Library UI**:
      - Show packs in user's selected language (from global Settings)
      - If pack lacks user's locale, fall back to English
      - Display badge: "🌐 Available in: English, French, Spanish"

      **Locale-Aware Pack Prioritization**:
      - Packs with user's locale are sorted higher in library
      - Example: French-speaking user sees French-localized packs first
      - Advanced users can toggle "Show all packs" to see untranslated options

      **Search and Filtering**:
      - Pack search matches against names/descriptions in ALL locales
      - User searching "covoiturage" (French) finds "Rideshare" pack even if UI is in English

      ### Classification Hints and Multi-Locale Matching

      **Best Practice for Pack Authors**:
      - Include keywords in ALL target locales where practical
      - Priority: Country's official language(s) + English
      - Example: AU BAS Rideshare pack should include:
        - English: "uber", "ola", "rideshare"
        - No other locales strictly needed (AU is English-speaking)
      - Example: Canada Spousal Sponsorship pack should include:
        - English: "bank statement", "joint account", "cohabitation"
        - French: "relevé bancaire", "compte joint", "cohabitation"

      **LLM Prompt Integration**:
      - Classification prompt includes: "Match against these keywords in any language: [en: uber, fr: covoiturage, es: viaje compartido]"
      - This allows multilingual users to classify mixed-language documents

      ### Future: Community Translations

      Phase 2 may allow community contributors to submit translations for existing packs:
      - Pack author creates pack in English
      - Community contributor adds French locale → Reviewed and merged
      - Pack version bumped (minor version: 1.0.0 → 1.1.0)
```

**Location**: Section 1.2.1, Section 1.2.3, new Section 6.X after Section 6.2

---

### 3.6 Non-Content Telemetry Hooks for Packs

**Issue**: Implementation plan mentions correction tracking but doesn't tie this to Level 0/1 telemetry design.

**Action**:
```markdown
- [ ] Add new subsection "5.X Telemetry for Packs (Level 0/1, Non-Content)" after Section 5.3:

      ## 5.X Telemetry for Packs (Level 0/1, Non-Content)

      FileOrganizer's telemetry system (see MASTER_BUILD_PLAN Section 1.X) applies to scenario packs with strict non-content guarantees.

      ### Level 0 Telemetry (Default, All Users)

      **Pack Usage Metrics** (Anonymous):
      - Pack started: `pack_id` (e.g., `tax_au_bas_rideshare_v1`), timestamp
      - Pack completed/exported: `pack_id`, timestamp, export types used (e.g., `["spreadsheet", "pdf_bundle"]`)
      - Pack abandoned: `pack_id`, timestamp, reason (if provided by user in exit survey)
      - Crash during pack processing: Stack trace, `pack_id`, phase (ingestion/triage/export), NO file names or content

      **Explicitly NOT Collected**:
      - ❌ File names, file paths, document text
      - ❌ Category names or document counts (could infer sensitive info)
      - ❌ User corrections or classification details

      ---

      ### Level 1 Telemetry (Opt-In, Aggregated)

      **Pack Performance Metrics** (Non-Content):
      - Classification accuracy proxy: `correction_rate` (% of documents manually reassigned, NO category details)
      - Processing time: `avg_classification_time_per_doc`, `total_pack_processing_time`
      - Export performance: `export_time_per_recipe`, `export_file_size_mb` (NO file names)
      - Validation warnings triggered: `warning_type` (e.g., `"timeframe_coverage_warning"`), `pack_id` (NO actual data)

      **Pack Adoption Metrics**:
      - Pack popularity: Number of times `pack_id` started/completed (aggregated across all users)
      - Export recipe usage: Which export types are most/least used (e.g., `pdf_bundle: 85%`, `pptx: 15%`)
      - Pack version distribution: `pack_id:version` usage (helps prioritize updates)

      **User Correction Patterns** (Aggregated, NO Content):
      - Correction frequency: `corrections_per_100_docs` (averaged across all users)
      - Most corrected categories: `category_id` with highest correction rate (e.g., `expenses_other` often miscategorized)
      - This helps improve `classification_hints` in pack updates, but NO individual user corrections or document details are sent

      **Explicitly NOT Collected**:
      - ❌ Individual user's document counts or category distributions
      - ❌ Specific corrections (e.g., "User changed doc_789 from Fuel to Vehicle")
      - ❌ Actual document metadata (dates, amounts, merchants)

      ---

      ### Privacy Guarantees

      **What Is Sent**:
      ✅ Pack ID and version (e.g., `tax_au_bas_rideshare_v1`)
      ✅ Export types used (e.g., `["spreadsheet", "pdf_bundle"]`)
      ✅ Aggregated metrics (e.g., `avg_classification_time: 2.3s`)
      ✅ Correction rate (e.g., `15% of docs required manual reassignment`)

      **What Is NEVER Sent**:
      ❌ File names, paths, or extensions
      ❌ Document text, OCR output, or extracted metadata
      ❌ Category names, counts, or distributions for individual users
      ❌ Specific user corrections or classification details

      **User Control**:
      - Settings → Telemetry: "Level 0 (Minimal, Default)" or "Level 1 (Aggregated Stats, Opt-In)"
      - "View Telemetry Data" button shows exact JSON payload before opt-in
      - User can disable telemetry entirely (opt-out of Level 0) in privacy-critical scenarios

      ---

      ### Implementation

      **Milestone 1 (Weeks 1-3)**:
      - Implement telemetry client with Level 0 hooks (pack started/completed/abandoned)

      **Milestone 4 (Weeks 11-13)**:
      - Add Level 1 hooks (correction rate, processing time, export metrics)
      - Settings UI for telemetry level selection and payload preview

      **Validation**:
      - Open-source telemetry client code for community audit
      - Third-party privacy audit (Phase 2, pre-launch)
```

**Location**: New Section 5.X after Section 5.3

---

### 3.7 Simple Tax Pack Variant (Lowest-Risk Fallback)

**Issue**: Current packs include form mappings and thresholds, which carry liability risk. Need explicitly documented "simple" variant.

**Action**:
```markdown
- [ ] In Section 2.1 "Prioritized Pack List" → Tier 1, add new pack:

      **1.5 Simple Tax Pack - Category-Based Only** (`tax_simple_generic_v1`)
      - Domain: Tax
      - Country: GENERIC (all countries)
      - Categories: Income (Sales, Fees, Other), Expenses (Vehicle, Office, Phone, Supplies, Other)
      - Mappings: NONE (no form fields, no thresholds)
      - Export: Per-category PDFs + master index ONLY (no spreadsheet with totals, no form summary)
      - Disclaimers: Extra-strong wording emphasizing no advice, no calculations
      - **Why This Pack**: Lowest-risk option for users in countries without specific packs, or users who want minimal features
      - **Use Case**: User wants to organize receipts by category for accountant handoff, but does NOT want any form mappings or totals (accountant will do all calculations)

- [ ] Add subsection "2.X Simple Tax Pack (Lowest-Risk Variant)" after Section 2.2.1:

      ## 2.X Simple Tax Pack (Lowest-Risk Variant)

      ### Rationale

      The Generic Tax Pack (Section 2.2.1) includes category totals in spreadsheet exports, which some users may interpret as "deduction amounts" or "tax calculations." To mitigate liability risk, FileOrganizer offers a **Simple Tax Pack** with:

      - ✅ Category organization (Income, Expenses by type)
      - ✅ Per-category PDF bundles (receipts grouped by category)
      - ❌ NO spreadsheet totals (no "Total Fuel Expenses: $5,432.10")
      - ❌ NO form field mappings (no G1, 1A, 1B references)
      - ❌ NO thresholds (no GST registration guidance)

      This pack is suitable for:
      - Users in countries without specific packs (e.g., Germany, France, Japan)
      - Users who want minimal features and will hand off raw categorized documents to accountant/tax agent
      - Users in regulated professions (e.g., legal, medical) who need strict no-advice guarantee

      ### Pack Structure

      **Categories** (Flat, Minimal Depth):
      - Income
        - Sales/Services
        - Fees/Commissions
        - Other Income
      - Expenses
        - Vehicle
        - Office
        - Phone/Internet
        - Supplies
        - Other Expenses

      **Export**:
      - Per-category PDF bundles (chronological, most recent first)
      - Master index (list of all documents with category labels, NO amounts)
      - NO spreadsheet, NO summary PDF, NO totals

      **Disclaimers**:
      ```
      Primary:
      "This pack organizes your documents by category only. It does NOT calculate totals, deductions, or tax liabilities. It is NOT tax advice. You must provide these categorized documents to a qualified tax professional who will perform all calculations and compliance checks."

      Additional:
      - "FileOrganizer does not verify accuracy, authenticity, or tax compliance of your documents."
      - "Category labels are for organization only and do not imply tax treatment or deductibility."
      - "Consult a registered tax agent, CPA, or accountant for professional guidance."
      ```

      ### Implementation

      **Milestone 2 (Weeks 4-6)**:
      - Create `tax_simple_generic_v1.yaml` with Core v1 fields only
      - Test with 20-30 sample documents (mixed categories)
      - Export per-category PDFs + index, verify NO totals displayed anywhere

      **User Testing**:
      - Alpha test with 5 users in non-covered countries (e.g., Germany, Japan)
      - Confirm: Users understand pack limitations ("no totals, hand off to accountant")
      - Feedback: "This is perfect for my German tax advisor who wants organized receipts but does their own math"
```

**Location**: Section 2.1 Tier 1 packs, new Section 2.X after Section 2.2.1

---

### 3.8 Non-Core Pack Example: Rental Application

**Issue**: Implementation plan is scoped tightly to tax/immigration/legal, but schema should support other domains (rental, job, insurance).

**Action**:
```markdown
- [ ] Add new Section "2.X Non-Core Pack Example: Rental Application" after Section 2.2.4:

      ## 2.X Non-Core Pack Example: Rental Application

      To validate that the pack schema remains general and doesn't bake in tax/legal-specific assumptions, here is a simple rental application pack:

      ### `rental_application_generic_v1.yaml`

      **Domain**: `general` (not tax, immigration, or legal)

      **Categories**:
      - Identity Documents
        - Photo ID (Driver's License, Passport)
        - Proof of Age
      - Income Verification
        - Payslips (Last 3 Months)
        - Employment Letter
        - Bank Statements
      - Rental History
        - Previous Lease Agreements
        - Rental References (Letters from Landlords)
        - Rent Payment Records
      - References
        - Personal References (Letters)
        - Character References
      - Additional Documents
        - Pet Information (if applicable)
        - Vehicle Registration (if parking required)

      **Export**:
      - PDF Bundle: All categories merged into single PDF with table of contents
      - Cover Page: "Rental Application for [Property Address]" with applicant name and date
      - Index: List of all documents with page numbers

      **Disclaimers**:
      ```
      Primary:
      "This pack organizes your rental application documents for submission to a landlord or property manager. It is NOT legal advice and does NOT guarantee rental approval. Verify all requirements with the landlord or leasing agent."

      Additional:
      - "Ensure all documents are current and accurate before submission."
      - "Some landlords may require additional documents not listed here."
      ```

      **Mappings**: None (no form fields, just categories → PDF sections)

      **Validation**: Simple completeness check (warn if Identity or Income Verification is empty)

      ### Why This Example Matters

      This pack demonstrates:
      - ✅ Schema works for non-tax/legal domains
      - ✅ Simpler packs (fewer categories, no complex mappings) are easy to create
      - ✅ Export recipes (PDF bundle with TOC) reusable across domains
      - ✅ Disclaimers adapt to domain (rental, not tax/immigration)

      ### Implementation

      **Phase 2 (Post-v1.0)**:
      - Create `rental_application_generic_v1.yaml`
      - Test with 10 sample rental applications (real-world user data, anonymized)
      - Publish as community pack example for pack authors
```

**Location**: New Section 2.X after Section 2.2.4

---

### 3.9 Performance and Resource Usage Guidance

**Issue**: Pack classification relies on heavy LLMs; implementation plan acknowledges accuracy risk but not performance/resource risk.

**Action**:
```markdown
- [ ] Add new subsection "3.X.X Performance and Resource Management" after Section 3.2.4:

      ### 3.X.X Performance and Resource Management

      Pack classification can be resource-intensive (OCR + LLM on 50-200 documents). FileOrganizer MUST handle this gracefully without blocking the UI or exhausting system resources.

      #### Asynchronous, Resumable Processing

      **Architecture**:
      - All OCR and classification runs in **background job queue** (separate thread or process)
      - Main UI remains responsive (user can browse other folders, adjust settings, etc.)
      - Progress indicator: "Processing 45/120 documents (37%)... Estimated time remaining: 8 minutes"
      - **Pause/Resume support**: User can pause processing (state saved to disk), close app, reopen later, and resume
      - **Incremental processing**: New documents added to pack instance are queued and processed when user returns to pack

      **State Persistence**:
      - Pack instance state saved to disk after each document processed (or every 10 documents for efficiency)
      - If app crashes during processing, user can resume from last saved state (no re-processing of already-classified docs)

      ---

      #### Processing Modes (Cross-Reference: MASTER_BUILD_PLAN Section 1.X)

      **1. Offline-Only Mode** (Local LLMs):
      - Tesseract OCR + Qwen2-7B classification (local)
      - Slowest (1-3 seconds per document)
      - Works offline, fully private
      - Recommended for: 16GB+ RAM, privacy-critical use cases (tax, legal, immigration)

      **2. Cloud-Assisted Mode** (Hybrid):
      - Tesseract OCR (local) + GPT-4o Mini or Claude Haiku (cloud classification)
      - Faster (0.5-1 second per document)
      - Requires internet, user consent, encryption in transit
      - Recommended for: 8-16GB RAM, users prioritizing speed over full local privacy

      **3. Cloud-First Mode** (Premium Tier):
      - Azure Document Intelligence or Google Vision (cloud OCR)
      - GPT-4o or Claude Sonnet (cloud classification)
      - Fastest (0.3-0.5 seconds per document, parallel processing)
      - Requires Pro/Business tier, explicit user consent
      - Recommended for: Pro users with 50+ documents, need fast turnaround

      **Settings Integration**:
      - Global Settings → Processing Mode: Dropdown (Offline-Only, Cloud-Assisted, Cloud-First)
      - Pack-specific override: "Use Cloud-Assisted for this pack only" (checkbox in pack settings)
      - RAM usage estimate displayed: "Offline-Only mode: ~8GB RAM required for pack with 100 documents"

      ---

      #### Telemetry (Level 1, Opt-In)

      To guide optimization, log non-content performance metrics:
      - Processing time per document: `avg_ocr_time`, `avg_classification_time`
      - Processing mode used: `"offline_only"`, `"cloud_assisted"`, `"cloud_first"`
      - Pack size: `document_count` (e.g., 50, 100, 200)
      - Hardware: `ram_gb`, `cpu_cores` (for correlation with performance)

      **Explicitly NOT Logged**:
      - ❌ File names, document content, classification results

      ---

      #### Error Handling and Retries

      **Transient Failures** (e.g., network timeout, cloud API rate limit):
      - Retry up to 3 times with exponential backoff (1s, 2s, 4s)
      - If all retries fail, mark document as "Classification failed" and continue with next document
      - User can manually retry failed documents later (button: "Retry Failed (5)")

      **Permanent Failures** (e.g., corrupted PDF, unsupported format):
      - Mark document as "Error: Unsupported format" and skip
      - User notified via triage UI: "3 documents could not be processed (unsupported format or corrupted)"

      ---

      #### Estimated Processing Times (Benchmarks)

      Assuming mid-range hardware (16GB RAM, Intel i5/Ryzen 5):

      | Pack Size | Offline-Only Mode | Cloud-Assisted Mode | Cloud-First Mode (Premium) |
      |-----------|------------------|---------------------|---------------------------|
      | 50 docs   | ~2-5 minutes     | ~1-2 minutes        | ~30-60 seconds            |
      | 100 docs  | ~5-10 minutes    | ~2-4 minutes        | ~1-2 minutes              |
      | 200 docs  | ~10-20 minutes   | ~4-8 minutes        | ~2-4 minutes              |

      **Note**: Times assume mix of PDFs (50%) and images (50%). PDF-only packs faster, image-only packs slower.
```

**Location**: New Section 3.X.X after Section 3.2.4

---

## Final Checklist for Cursor

Paste this consolidated checklist to Cursor as a single prompt (or break into 3 separate prompts per document):

```
# Cursor: Please revise the three FileOrganizer planning documents per this checklist.

## MASTER_BUILD_PLAN_FILEORGANIZER.md

1. Scope v1 packs to generic only (tax, immigration, legal timeline). Move country-specific packs to Phase 2 section.
2. Add "2.X Hardware Assumptions & Resource Modes" subsection under Tier 2 (16GB optimized, 8GB reduced mode, cloud-first mode, async processing, settings integration).
3. Add "1.X Telemetry Architecture" subsection under Tier 1 (Level 0 default, Level 1 opt-in, NO content/filenames/paths ever sent).
4. Add new "Tier 3.5: Conversion & Packaging Primitives" (image→PDF, Office→PDF, PDF ops, text→PDF, Standard vs Premium engines).
5. In Tier 4 and Tier 5, add i18n integration notes (react-i18next, pack locales support from day one).
6. Add "Product Vision" paragraph clarifying v1.0 success criteria (general-purpose + generic packs) vs Phase 2+ (deep legal, country-specific).

## research_report_tax_immigration_legal_packs.md

1. Add "Appendix E: Assumptions & Unknowns per Domain/Country" with table showing verified constraints vs unknowns (file size limits, portal constraints).
2. In each Tax/BAS country section (AU, UK, US, CA, NZ), add "[Country] - Priority Profession Templates" table (rideshare, delivery, cleaners, tutors, handyman with typical evidence).
3. In "Executive Summary" and Part 4 Section 4.5, add explicit "Scope Boundary" statement (packs organize, NOT calculate eligibility/advice).
4. In Part 1 Section 1.6, add "Multi-Period and Audit-Readiness Considerations" subsection with real-world examples (quarterly BAS aggregation, multi-year cohabitation).

## implementation_plan_tax_immigration_legal_packs.md

1. In Section 1.2 intro, add "Schema Versioning: Core v1 vs Advanced v2" paragraph. Mark thresholds, detailed form mappings, complex validation as v2 (deferred).
2. Add new "Section 3.X Export Engine Abstraction" after Section 3.2 (Standard free local vs Premium cloud-assisted, engine-agnostic recipes, tier gating, consent UI).
3. In Section 1.2.5, add PPTX export recipe type (simple slide-per-category for v1, advanced thumbnails/charts for v2).
4. Add new "Section 4.X Triage UX for Packs" (category sidebar, compact grid, bulk actions, smart grouping, keyboard shortcuts, before/after ops log).
5. In Sections 1.2.1 and 1.2.3, update locales and classification_hints examples with multi-language support. Add new "Section 6.X i18n and Pack Selection" (locale-aware prioritization, multi-locale keywords).
6. Add new "Section 5.X Telemetry for Packs" (Level 0/1 metrics, correction rate, processing time, NO content/categories/corrections sent, user control).
7. In Section 2.1 Tier 1, add "1.5 Simple Tax Pack" (category-only, NO totals, NO mappings, lowest-risk fallback). Add new "Section 2.X Simple Tax Pack" with rationale and disclaimers.
8. Add new "Section 2.X Non-Core Pack Example: Rental Application" (rental_application_generic_v1.yaml) to validate schema generality.
9. Add new "Section 3.X.X Performance and Resource Management" (async processing, pause/resume, offline/cloud-assisted/cloud-first modes, benchmarks, error handling).

---

For each revision, maintain existing section numbering where possible. If inserting new sections, renumber subsequent sections. Preserve all existing content unless explicitly superseded by this checklist.
```

---

## ADDENDUM: Immigration Pack Premium Service (User Requirement)

**User Request**: "As immigration requirements keep changes, it should reflect the changed requirements. This will be a paid optional premium service. We'll come up with price later on."

### Context

Immigration visa requirements are **highly volatile** (fees, thresholds, forms change 2-4+ times/year), unlike tax (stable) or legal (jurisdiction-stable) packs. This requires an ongoing premium service for expert-verified template updates.

### Additional Revisions Required

1. **Create new detailed specification document**:
   - File: `docs/research/immigration_visa_evidence_packs_detailed_spec.md`
   - Synthesize `cursor_research_brief_immigration_visa_evidence_packs_v2.md` + `cursor_build_prompt_immigration_visa_pack_compiler.md`
   - Define VisaPackTemplate schema with examples per country (AU, UK, US, CA, NZ)
   - Document priority visa types per country (Student, Skilled, Partner, Work)
   - Packaging guidance (portal structures, file limits)
   - Volatility assessment + maintenance strategy
   - Implementation handover (Phase 1 vs Phase 2 visas)

2. **Update `research_report_tax_immigration_legal_packs.md`**:
   - Add Section "2.7 Template Volatility and Maintenance Strategy":
     - Document change frequency by country (AU/UK/CA: high, US/NZ: medium)
     - Define Free Tier (static, no updates, "last verified" warnings) vs Premium Tier (quarterly updates, expert-verified)
     - Architecture: External YAML templates, update server, version locking for pack instances
     - Expert network: Licensed agents per country (MARA for AU, OISC for UK, attorneys for US, RCIC for CA, IAA for NZ)
     - Pricing options (TBD): Per-country ($9.99/month) vs All-country ($19.99/month) vs One-time ($29)

3. **Update `implementation_plan_tax_immigration_legal_packs.md`**:
   - Add Section "X. Immigration Pack Premium Service Architecture":
     - Template update server (API endpoints for catalog, download, changelog)
     - Client-side update check + installation flow (with rollback)
     - Pack instance version locking (mid-pack stability)
     - Expert verification workflow (quarterly + emergency updates)
     - Subscription backend (Stripe/Paddle integration)
     - Telemetry (Level 1: download counts, success rates, NO user visa details)
     - Risk mitigation (expert availability, breaking changes, legal liability)
     - Implementation phases: Phase 1 (static templates), Phase 2 (premium service, Weeks 5-12)

4. **Update `MASTER_BUILD_PLAN_FILEORGANIZER.md`**:
   - In Tier 5 (Scenario Packs), note that immigration packs have special update requirements
   - Add Phase 2 milestone: "Immigration Pack Premium Service (template update infrastructure, subscription backend)"
   - Cross-reference new immigration detailed spec

### Key Technical Requirements

- **Template Storage**: External YAML files (`~/.fileorganizer/templates/immigration/`), versioned
- **Update Server**: REST API for catalog, downloads, changelogs (JWT auth for Premium)
- **Version Locking**: Pack instances frozen at creation template version (user can upgrade manually)
- **Signature Verification**: Templates signed with Ed25519/RSA to prevent tampering
- **Rollback**: Keep 3 most recent versions as backups
- **Expert SLA**: Quarterly reviews (minimum), 7-day turnaround for emergency updates

### Pricing Strategy (Placeholder, TBD)

| Tier | Price | Coverage | Updates |
|------|-------|----------|---------|
| Free | $0 | Static templates (bundled) | None (user verifies manually) |
| Single Country | $9.99/month or $79/year | 1 country | Quarterly + emergency |
| All Countries | $19.99/month or $149/year | All 5 countries | Quarterly + emergency |
| One-Time | $29 per pack | Current template only | None |

### Disclaimer Updates

**Free Tier**: "⚠️ Last verified [DATE]. Immigration requirements change frequently. Verify against official sources. [Upgrade to Premium]"

**Premium Tier**: "✅ Verified [DATE] by [Expert Name], [Credentials]. Requirements can change without notice. Always verify critical details."

---

**End of revision checklist. All issues flagged in your review are now mapped to specific, actionable changes. Ready for Cursor to execute.**
