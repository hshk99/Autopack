# Implementation Plan: Tax/BAS, Immigration, and Legal Pack System

**Prepared for**: FileOrganizer Application Development
**Date**: 2025-11-27
**Companion Document**: `research_report_tax_immigration_legal_packs.md`
**Status**: Ready for Implementation

---

## Executive Summary

This implementation plan defines the technical architecture, configuration schema, integration approach, and prioritized milestones for FileOrganizer's scenario pack system, based on research into tax/BAS, immigration, and legal evidence formats across AU, UK, US, CA, and NZ.

**CRITICAL: v1.0 Scope Discipline**

Per GPT's strategic review, v1.0 launches with **GENERIC PACKS ONLY**:

```
┌────────────────────────────────────────────────────────────┐
│ v1.0 SCOPE (Milestones 1-2: Weeks 1-6)                    │
│ • Generic tax pack (income/expense, no country forms)     │
│ • Generic immigration pack (relationship evidence, no     │
│   visa-specific)                                           │
│ • Generic legal timeline (event extraction, basic exports)│
│ • NO country-specific packs                               │
│ • NO tax form field mappings (BAS, 1040, Self Assessment) │
│ • NO visa-specific templates (AU 820/801, UK Spouse)      │
│ • NO Immigration Premium Service                          │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ PHASE 2 SCOPE (Milestones 3-5: Weeks 7-18)                │
│ • AU BAS Pack (rideshare driver, form mappings)           │
│ • AU Partner Visa Pack (820/801, 4 pillars)               │
│ • UK Spouse Visa Pack (UKVI guidance)                     │
│ • UK Self Assessment Pack                                 │
│ • Expert verification network                             │
└────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────┐
│ PHASE 2.5 SCOPE (Weeks 19-26)                             │
│ • Immigration Premium Service infrastructure              │
│ • Template update server (REST API, JWT auth)             │
│ • Subscription backend (Stripe/Paddle)                    │
│ • Quarterly template updates                              │
└────────────────────────────────────────────────────────────┘
```

**Core Design Principles**:
1. **Configuration-Driven**: Packs are YAML/JSON templates, not code → Add new packs/countries without recompiling
2. **Local-First**: All processing on-device, privacy-respecting
3. **Explainable**: Users understand and control all categorizations
4. **Non-Advisory**: Packs organize documents, do NOT provide tax/legal/immigration advice

**Key Technical Decisions**:
- **Pack Format**: YAML with metadata, categories, mappings, export recipes, disclaimers
- **Integration Points**: Ingestion (OCR+LLM → category), Triage (user corrections), Export (format-specific outputs)
- **Versioning**: Semantic versioning for packs, user instances frozen at selected version
- **Extensibility**: Community packs supported (with moderation)

**v1.0 Pack Targets** (Generic Only):
1. ✅ **v1.0**: Generic Tax Pack (income/expenses/deductions, no country forms)
2. ✅ **v1.0**: Generic Immigration Pack (identity/financial/relationship, no visa-specific)
3. ✅ **v1.0**: Generic Legal Timeline (event extraction, chronology)
4. ❌ **Phase 2**: Australia BAS - Rideshare Driver (deferred)
5. ❌ **Phase 2**: AU Partner Visa 820/801 (deferred)
6. ❌ **Phase 2**: UK Spouse Visa (deferred)

**Estimated Timeline**:
- ✅ **v1.0** (Milestones 1-2): 4-6 weeks (generic packs only)
- ❌ **Phase 2** (Milestones 3-5): 7-11 weeks (country-specific packs, deferred)

---

## 1. Pack Configuration Schema

### 1.1 Schema Overview

Packs are defined in **YAML** (or JSON) format with the following top-level structure:

```yaml
pack:
  metadata:       # Pack identity and versioning
  disclaimers:    # Legal/safety disclaimers
  categories:     # Hierarchical evidence/document categories
  mappings:       # Category → form field or output mappings
  export_recipes: # Output format specifications
  thresholds:     # Country-specific values (optional)
  validation:     # Completeness checks (optional)
```

### 1.2 Full Schema Specification

#### 1.2.1 Metadata Block

```yaml
pack:
  metadata:
    id: "tax_au_bas_rideshare_v1"           # Unique pack identifier
    name: "Australia BAS - Rideshare Driver" # Display name
    domain: "tax"                            # Domain: tax | immigration | legal | general
    country: "AU"                            # ISO 3166-1 alpha-2 code (AU, UK, US, CA, NZ, GENERIC)
    version: "1.0.0"                         # Semantic versioning (major.minor.patch)
    author: "FileOrganizer Team"             # Pack author (or community contributor)
    created: "2025-11-27"                    # Creation date (YYYY-MM-DD)
    updated: "2025-11-27"                    # Last update date
    description: |
      Organizes quarterly BAS evidence for Australian rideshare drivers (Uber, Ola, etc.).
      Supports GST-registered and non-registered sole traders.
    tags:                                    # Searchable tags
      - "rideshare"
      - "uber"
      - "sole-trader"
      - "quarterly-bas"
    min_app_version: "1.0.0"                 # Minimum FileOrganizer version required
```

**Key Fields**:
- `id`: Unique, immutable identifier (cannot change across versions)
- `country`: "GENERIC" for cross-country packs, or ISO code for country-specific
- `version`: Semantic versioning → Major bump for breaking changes, minor for new features, patch for fixes
- `tags`: For search/filter in pack library

#### 1.2.2 Disclaimers Block

```yaml
  disclaimers:
    primary: |
      This pack organizes your documents and provides category summaries to assist with tax preparation.
      It is NOT tax advice and does NOT determine deductibility or calculate tax liabilities.
      Consult a registered tax agent or accountant for professional guidance.

    additional:
      - "FileOrganizer does not verify document authenticity or accuracy."
      - "You are responsible for reviewing all categorizations and totals before submitting to authorities."
      - "GST/BAS thresholds and rules may change; consult ATO for current requirements."

    display_contexts:
      - "pack_selection"     # Show before user starts pack
      - "export_footer"      # Include in exported PDFs/spreadsheets
      - "summary_header"     # Show at top of summary reports
```

**Key Fields**:
- `primary`: Main disclaimer (shown prominently)
- `additional`: Supplementary disclaimers (bulleted list)
- `display_contexts`: Where disclaimers appear (pack selection screen, exports, summaries)

#### 1.2.3 Categories Block

Categories define the hierarchical structure for organizing documents.

```yaml
  categories:
    - id: "income"                           # Unique category ID
      name: "Income"                         # Display name
      parent: null                           # Top-level category (no parent)
      description: "All income sources"
      icon: "currency-dollar"                # Icon for UI (optional)
      color: "#4CAF50"                       # Color for UI (optional)

    - id: "income_rideshare"
      name: "Rideshare Income"
      parent: "income"                       # Child of "income"
      description: "Uber, Ola, DiDi earnings statements"
      typical_documents:                     # Suggested document types (for user guidance)
        - "Platform weekly/monthly summaries (PDF)"
        - "Bank deposit records showing platform payouts"
        - "Annual tax summaries from Uber/Ola"
      classification_hints:                  # Keywords/patterns for auto-classification
        keywords:
          - "uber"
          - "ola"
          - "didi"
          - "rideshare"
          - "driver earnings"
        sender_domains:
          - "uber.com"
          - "ola.com.au"
        file_patterns:
          - "*uber*earnings*.pdf"
            "*ola*payout*.pdf"
      validation:
        recommended_timeframe: "quarterly"   # User should have docs for last quarter
        min_documents: 1
        warning_if_missing: "Rideshare income is a common category for BAS. Did you forget to upload platform statements?"

    - id: "expenses"
      name: "Expenses"
      parent: null
      description: "All business expenses"

    - id: "expenses_fuel"
      name: "Fuel Expenses"
      parent: "expenses"
      description: "Fuel receipts for business use"
      typical_documents:
        - "Fuel receipts (paper or digital)"
        - "Credit card statements showing fuel purchases"
      classification_hints:
        keywords:
          - "fuel"
          - "petrol"
          - "gasoline"
          - "service station"
          - "bp"
          - "shell"
          - "caltex"
        merchant_names:
          - "BP"
          - "Shell"
          - "Caltex"
          - "7-Eleven"
      deduction_notes: |
        You can claim business use % × total fuel costs. Keep logbook if business km >5,000/year.
      validation:
        recommended_timeframe: "quarterly"
        warning_if_missing: "Fuel is often the largest expense for rideshare drivers. Did you upload fuel receipts?"
```

**Key Fields**:
- `id`: Unique, immutable identifier for category
- `parent`: ID of parent category (null for top-level)
- `typical_documents`: User-facing guidance on what to include
- `classification_hints`: Keywords, sender domains, file patterns for auto-classification
- `validation`: Completeness checks (warn user if category is empty but typically populated)
- `deduction_notes`: Tax-specific guidance (WITHOUT providing tax advice)

**Category Hierarchy Depth**: Support 3+ levels (e.g., Income → Rideshare → Uber → 2024 Q3)

#### 1.2.4 Mappings Block

Mappings link categories to output structures (tax forms, checklists, export sections).

```yaml
  mappings:
    form_fields:                             # For tax domain: category → form field
      - category_id: "income_rideshare"
        fields:
          - field_id: "G1"
            field_name: "Total Sales"
            description: "Gross rideshare income (including GST)"
            calculation: "sum"               # sum | count | average | max | min
            include_gst: true
          - field_id: "1A"
            field_name: "GST on Sales"
            description: "10% of total sales (for GST-registered)"
            calculation: "derived"           # Calculated from G1
            formula: "G1 * 0.10"

      - category_id: "expenses_fuel"
        fields:
          - field_id: "1B"
            field_name: "GST on Purchases"
            description: "GST component of fuel expenses"
            calculation: "sum_gst_component"
            note: "Only claimable if GST-registered"

    checklist_sections:                      # For immigration domain: category → checklist section
      - category_id: "financial_joint_accounts"
        section_id: "financial_pillar"
        section_name: "Financial Aspects"
        evidence_type: "Joint Bank Statements"
        recommended_timeframe: "12+ months"
        strength: "strong"                   # strong | medium | weak (for immigration)

    timeline_categories:                     # For legal domain: event category → timeline label
      - category_id: "legal_incident"
        timeline_label: "Incident"
        color: "#F44336"                     # Red for incidents
      - category_id: "legal_correspondence"
        timeline_label: "Correspondence"
        color: "#2196F3"                     # Blue for correspondence
```

**Key Fields**:
- `form_fields`: Tax-specific mappings (category → form field + calculation method)
- `checklist_sections`: Immigration-specific mappings (category → checklist section + evidence strength)
- `timeline_categories`: Legal-specific mappings (category → timeline label + color)

**Calculation Methods**:
- `sum`: Sum all amounts in category
- `count`: Count number of documents
- `average`: Average amount
- `derived`: Calculate from other fields using formula
- `sum_gst_component`: Extract and sum GST component (10% of total for AU)

#### 1.2.5 Export Recipes Block

Export recipes define output formats and their parameters.

```yaml
  export_recipes:
    - id: "spreadsheet_summary"
      type: "spreadsheet"
      format: "xlsx"                         # xlsx | csv | ods
      name: "BAS Summary Spreadsheet"
      description: "Excel spreadsheet with transaction details and category totals"
      sheets:
        - name: "Income Summary"
          columns:
            - { id: "date", name: "Date", format: "date", source: "document.date" }
            - { id: "description", name: "Description", source: "document.description" }
            - { id: "category", name: "Category", source: "category.name" }
            - { id: "amount_inc_gst", name: "Amount (Inc GST)", format: "currency", source: "document.amount_total" }
            - { id: "gst_component", name: "GST Component", format: "currency", source: "document.gst_amount" }
            - { id: "counterparty", name: "Counterparty", source: "document.counterparty" }
            - { id: "notes", name: "Notes", source: "document.notes" }
          filter:
            category_parent: "income"       # Only include income categories
          sort:
            - { column: "date", order: "desc" }  # Most recent first
          totals:
            - { column: "amount_inc_gst", label: "Total Income (Inc GST)" }
            - { column: "gst_component", label: "Total GST on Income" }

        - name: "Expense Summary"
          columns: [ same structure as Income Summary ]
          filter:
            category_parent: "expenses"
          sort:
            - { column: "date", order: "desc" }
          totals:
            - { column: "amount_inc_gst", label: "Total Expenses (Inc GST)" }
            - { column: "gst_component", label: "Total GST on Expenses" }

        - name: "Category Totals"
          columns:
            - { id: "category", name: "Category" }
            - { id: "count", name: "# Documents" }
            - { id: "total", name: "Total Amount" }
          aggregation: "by_category"         # Group by category and sum

    - id: "pdf_bundles_per_category"
      type: "pdf_bundle"
      mode: "per_category"                   # per_category | combined_all | by_section
      name: "PDF Evidence Bundles"
      description: "One PDF per category, chronologically ordered"
      include_index: true                    # Generate index/table of contents
      include_cover_page: true
      chronological_order: "desc"            # desc (recent first) | asc (oldest first)
      combine_subcategories: true            # Merge child categories into parent PDF
      max_file_size_mb: 60                   # Split into multiple PDFs if exceeds limit
      filename_template: "{category_name}_{date_range}.pdf"  # e.g., "Fuel_Expenses_2024-Q3.pdf"

    - id: "form_summary_pdf"
      type: "summary_pdf"
      name: "BAS Form Summary"
      description: "PDF showing category totals mapped to BAS form fields"
      template: "bas_summary_template.html"  # HTML template for rendering
      include_disclaimer: true
      sections:
        - title: "Income Summary"
          mappings: [ "G1", "1A" ]           # Form fields to include
        - title: "Expense Summary"
          mappings: [ "1B" ]
        - title: "Net Position"
          formula: "1A - 1B"                 # GST refund or payment
```

**Key Fields**:
- `type`: `spreadsheet` | `pdf_bundle` | `summary_pdf` | `visual_timeline` | `photo_collage`
- `mode` (for PDF bundles): `per_category` (one PDF per category) | `combined_all` (single PDF with all docs) | `by_section` (PDFs per major section)
- `columns`: For spreadsheets, define column sources and formatting
- `filter`: Limit to specific categories or date ranges
- `sort`: Chronological or alphabetical ordering
- `totals`: Auto-calculate sums, counts, averages
- `include_index`: For PDF bundles, generate table of contents
- `template`: HTML/Markdown template for rendering (uses Jinja2 or similar)

#### 1.2.6 Thresholds Block (Optional)

Thresholds capture country-specific values for user guidance.

```yaml
  thresholds:
    - id: "gst_registration"
      name: "GST Registration Threshold"
      value: 75000
      currency: "AUD"
      period: "annual"
      description: "Required to register for GST if annual turnover ≥$75,000"
      info_url: "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/goods-and-services-tax-gst/registering-for-gst"

    - id: "logbook_requirement"
      name: "Logbook Requirement for Vehicle Expenses"
      value: 5000
      unit: "km"
      period: "annual"
      description: "Logbook required if claiming >5,000 business km per year"
```

**Key Fields**:
- `id`: Unique identifier for threshold
- `value`: Numeric value
- `currency` / `unit`: Currency code (AUD, USD, GBP) or unit (km, %)
- `period`: `annual` | `quarterly` | `monthly` | `once`
- `description`: User-facing explanation
- `info_url`: Link to official guidance (optional)

**Use Case**: Display to user during pack setup ("Your estimated annual income is $80K. You may need to register for GST. [Learn More]")

#### 1.2.7 Validation Block (Optional)

Validation rules check pack completeness and warn user of potential gaps.

```yaml
  validation:
    completeness_checks:
      - rule: "at_least_one_income_category"
        message: "You haven't categorized any income documents. BAS requires income reporting."
        severity: "error"                    # error | warning | info

      - rule: "recommended_categories_present"
        categories: [ "income_rideshare", "expenses_fuel" ]
        message: "Common categories for rideshare drivers: Rideshare Income, Fuel Expenses. Did you upload all relevant documents?"
        severity: "warning"

      - rule: "timeframe_coverage"
        category: "income_rideshare"
        min_months: 3                        # For quarterly BAS
        message: "You should have income evidence for the full quarter (3 months). Current coverage: {actual_months} months."
        severity: "warning"
```

**Key Fields**:
- `rule`: Validation rule type (predefined rule IDs or custom logic)
- `message`: User-facing warning/error message
- `severity`: `error` (blocks export) | `warning` (shows alert but allows export) | `info` (informational only)

**Predefined Rules**:
- `at_least_one_income_category`: Ensure user has categorized at least one income document
- `recommended_categories_present`: Check if suggested categories are populated
- `timeframe_coverage`: Ensure documents cover required time period (e.g., 3 months for quarterly BAS)
- `file_size_within_limits`: Check if combined PDF size exceeds submission limits

### 1.3 Schema Example: Full Pack (Australia BAS - Rideshare)

See Appendix A for full YAML example (`tax_au_bas_rideshare_v1.yaml`).

### 1.4 Schema Validation

**JSON Schema Definition**: Define JSON Schema for pack YAML to validate:
- Required fields present
- Data types correct (strings, numbers, dates)
- IDs are unique
- Parent category IDs exist
- Version follows semantic versioning format

**Validation on Pack Load**:
1. FileOrganizer loads pack YAML
2. Validates against JSON Schema
3. If validation fails → show error to user, refuse to load pack
4. If validation passes → parse and activate pack

**Tools**: Use `jsonschema` library (Python) or equivalent for validation.

---

## 2. Initial Pack Templates to Implement

### 2.1 Prioritized Pack List

**Tier 1: MVP Packs** (Implement First)
1. **Generic Tax Pack** (`tax_generic_v1`)
   - Domain: Tax
   - Country: GENERIC (applies to all)
   - Categories: Income (Sales, Fees, Other), Expenses (Vehicle, Office, Phone, Equipment, Other)
   - Export: Spreadsheet summary (Date, Category, Amount, Notes)
   - **Why First**: Validates core pack system, broadly applicable, low complexity

2. **Australia BAS - Rideshare Driver** (`tax_au_bas_rideshare_v1`)
   - Domain: Tax
   - Country: AU
   - Categories: Income (Rideshare, Direct Client), Expenses (Fuel, Vehicle, Phone, Home Office, Equipment)
   - Mappings: Category → BAS fields (G1, 1A, 1B)
   - Export: Spreadsheet + per-category PDFs + BAS summary PDF
   - **Why Second**: High-value archetype, tests country-specific mappings

3. **Generic Immigration - Partner/Spouse** (`immigration_generic_relationship_v1`)
   - Domain: Immigration
   - Country: GENERIC
   - Categories: Financial, Cohabitation, Relationship, Identity
   - Export: PDF bundles per category + checklist
   - **Why Third**: Validates immigration domain structure, tests PDF bundling

4. **Generic Legal Timeline** (`legal_generic_timeline_v1`)
   - Domain: Legal
   - Country: GENERIC
   - Categories: Incident, Correspondence, Filing, Medical, Employment, Financial, Witness
   - Export: Chronology spreadsheet (Date, Event, Source, Category) + evidence bundle PDF
   - **Why Fourth**: Validates legal domain, tests timeline generation

**Tier 2: Country-Specific Expansions** (Implement After Tier 1)
5. **UK Self Assessment - Sole Trader** (`tax_uk_selfassessment_v1`)
6. **US Schedule C - Self-Employed** (`tax_us_schedulec_v1`)
7. **Australia Partner Visa 820/801** (`immigration_au_partner_820_v1`)
8. **UK Spouse Visa** (`immigration_uk_spouse_v1`)
9. **US Marriage Green Card I-130** (`immigration_us_marriage_i130_v1`)

**Tier 3: Advanced Packs** (Future Enhancements)
10. **Canada T2125 - Self-Employed** (`tax_ca_t2125_v1`)
11. **New Zealand IR3 - Self-Employed** (`tax_nz_ir3_v1`)
12. **Canada Spousal Sponsorship** (`immigration_ca_spousal_v1`)
13. **New Zealand Partnership Visa** (`immigration_nz_partnership_v1`)
14. **Legal Evidence Bundle - UK Court** (`legal_uk_court_bundle_v1`)

### 2.2 Pack Template Skeletons

#### 2.2.1 Generic Tax Pack

**Categories** (High-Level):
- Income
  - Sales/Services
  - Fees/Commissions
  - Other Income
- Expenses
  - Vehicle
  - Office
  - Phone/Internet
  - Equipment
  - Travel
  - Other Expenses

**Export**:
- Spreadsheet: Date, Description, Category, Amount, Notes
- Per-Category PDFs: Chronological, recent first

**Mappings**: None (generic, no form-specific mappings)

**Disclaimers**:
> "This pack organizes your documents for tax preparation. It is NOT tax advice. Consult a qualified tax professional for guidance on deductions, reporting requirements, and compliance."

#### 2.2.2 Australia BAS - Rideshare Driver

**Categories**:
- Income
  - Rideshare Income (Uber, Ola, DiDi)
  - Direct Client Income
  - Other Income
- Expenses
  - Fuel
  - Vehicle Maintenance & Repairs
  - Phone & Internet
  - Home Office
  - Equipment (Phone Holders, Chargers, etc.)
  - Other Expenses
- Assets (Optional)
  - Vehicle (for depreciation tracking)

**Mappings**:
- Rideshare Income → G1 (Total Sales), 1A (GST on Sales)
- Direct Client Income → G1, 1A
- Fuel → 1B (GST on Purchases, business use %)
- Equipment → 1B (if >$82.50 inc GST)

**Export**:
- Spreadsheet: Date, Description, Category, Amount (Inc GST), GST Component, Counterparty, Notes
- Per-Category PDFs: Income (one PDF), Expenses (one PDF per subcategory)
- BAS Summary PDF: Category totals mapped to G1, 1A, 1B with disclaimer

**Thresholds**:
- GST Registration: $75,000 annual turnover
- Logbook Requirement: 5,000 business km/year

**Disclaimers**:
> "This pack organizes your documents for BAS preparation. It is NOT tax advice and does NOT calculate GST liabilities or determine deductibility. Consult a registered tax agent for professional guidance. GST registration thresholds and rules may change; see ATO website for current requirements."

#### 2.2.3 Generic Immigration - Partner/Spouse

**Categories**:
- Financial Evidence
  - Joint Bank Accounts
  - Joint Assets (Property, Vehicles)
  - Joint Liabilities (Mortgage, Loans)
  - Beneficiary Designations
- Cohabitation Evidence
  - Joint Lease/Property Title
  - Utility Bills (Both Names)
  - Correspondence to Same Address
- Relationship Evidence
  - Marriage Certificate (or De Facto Declaration)
  - Photos (Chronological)
  - Travel Evidence
  - Communication (Emails, Messages)
  - Statutory Declarations (Friends/Family)
- Identity & Civil Documents
  - Passports
  - Birth Certificates
  - Police Certificates
  - Medical Certificates

**Mappings** (Checklist):
- Financial → "Strong Evidence" (12+ months recommended)
- Cohabitation → "Required for De Facto" (12+ months)
- Photos → "Recommended: 20-40 images, chronological"
- Statutory Declarations → "Recommended: 2-4 from each side"

**Export**:
- PDF Bundles: One per major category (Financial, Cohabitation, Relationship, Identity)
- Index PDF: Table of contents with document names and page numbers
- Checklist PDF: Evidence types included, recommended vs actual

**Disclaimers**:
> "This pack organizes visa evidence based on official immigration guidance. It is NOT immigration advice and does NOT assess eligibility or likelihood of approval. Consult a registered migration agent, immigration attorney, or licensed adviser for case-specific guidance."

#### 2.2.4 Generic Legal Timeline

**Categories** (Event Types):
- Incident
- Correspondence
- Court Filing
- Medical
- Employment
- Financial
- Witness Statement
- Other

**Mappings** (Timeline Columns):
- Date → Timeline X-axis
- Event Description → Timeline label
- Category → Color coding (Incident=Red, Correspondence=Blue, etc.)
- Source → Document reference (Bates number or exhibit ID)

**Export**:
- Chronology Spreadsheet: Date, Time, Event Description, Parties, Source Document, Category, Notes
- Evidence Bundle PDF: All source documents, numbered, with index
- Visual Timeline (Optional): Graphical timeline with events plotted chronologically

**Disclaimers**:
> "This legal timeline and evidence bundle are organizational tools. They are NOT legal advice and do NOT replace attorney review. Verify all entries, citations, and formatting comply with applicable court rules before submission."

---

## 3. Integration with FileOrganizer Core Engine

### 3.1 Core Engine Overview

FileOrganizer's core engine consists of:
1. **Ingestion Pipeline**: OCR + LLM → extract text, metadata, classify documents
2. **Organization Engine**: Rules & Profiles system for folder structure, tagging, naming
3. **Triage UI**: Present unknowns or low-confidence classifications for user review
4. **Export Pipeline**: Generate outputs (PDFs, spreadsheets, summaries)

**Pack Integration Points**:
- **Pack Selection**: User chooses pack from library
- **Category Mapping**: Pack categories extend/override global organization rules
- **Triage**: Pack-specific UI shows category hierarchy, suggested evidence, completeness warnings
- **Export**: Pack export recipes generate domain-appropriate outputs

### 3.2 Pack Lifecycle

#### 3.2.1 Pack Selection and Initialization

**User Flow**:
1. User clicks "Start New Pack" in FileOrganizer
2. Pack Library UI shows available packs (filterable by domain, country, tags)
3. User selects pack (e.g., "Australia BAS - Rideshare Driver")
4. Disclaimer screen shown (from pack `disclaimers.primary` + `additional`)
5. User acknowledges disclaimer (checkbox: "I understand this is not tax advice")
6. Pack instance created:
   - Instance ID: UUID (e.g., `pack_instance_abc123`)
   - Pack template ID + version: `tax_au_bas_rideshare_v1`
   - State: Empty (no documents yet)
   - Created date: Timestamp
7. User proceeds to document upload

**Data Structure** (Pack Instance):
```json
{
  "instance_id": "pack_instance_abc123",
  "pack_template_id": "tax_au_bas_rideshare_v1",
  "pack_version": "1.0.0",
  "user_id": "user_456",
  "created_at": "2025-11-27T10:30:00Z",
  "updated_at": "2025-11-27T11:45:00Z",
  "state": "active",  // active | archived | exported
  "documents": [
    {
      "doc_id": "doc_789",
      "category_id": "income_rideshare",
      "filename": "Uber_Earnings_2024-Q3.pdf",
      "date": "2024-09-30",
      "amount": 5432.10,
      "gst_amount": 493.82,
      "confidence": 0.95,
      "user_reviewed": true
    },
    // ... more documents
  ],
  "user_corrections": [
    {
      "doc_id": "doc_790",
      "original_category": "expenses_other",
      "corrected_category": "expenses_fuel",
      "timestamp": "2025-11-27T11:00:00Z",
      "persist_as_rule": false  // Ephemeral correction (pack-instance only)
    }
  ],
  "validation_warnings": [
    {
      "rule": "timeframe_coverage",
      "category": "income_rideshare",
      "message": "You should have income evidence for the full quarter (3 months). Current coverage: 2 months.",
      "severity": "warning"
    }
  ]
}
```

#### 3.2.2 Document Ingestion with Pack Context

**Flow**:
1. User uploads documents (PDFs, images, receipts) to pack instance
2. Core Ingestion Pipeline:
   - OCR text extraction (if needed)
   - LLM classification:
     - Extract: Date, amount, counterparty/merchant, description
     - Classify: Which pack category? (using `classification_hints` from pack config)
     - Confidence score (0-1)
3. Assign to pack category:
   - If confidence ≥ 0.85 → Auto-assign
   - If 0.60 ≤ confidence < 0.85 → Suggest category, flag for review
   - If confidence < 0.60 → Mark as "Unknown", require user triage
4. Update pack instance state with categorized documents

**LLM Prompt Example** (Pack-Aware Classification):
```
You are classifying a document for a tax pack (Australia BAS - Rideshare Driver).

Available categories:
- income_rideshare: Uber, Ola, DiDi earnings statements (keywords: uber, ola, rideshare, driver earnings)
- income_direct: Direct client invoices
- expenses_fuel: Fuel receipts (keywords: fuel, petrol, BP, Shell, Caltex)
- expenses_vehicle: Vehicle maintenance, repairs
- expenses_phone: Phone and internet bills
- expenses_home_office: Home office expenses
- expenses_equipment: Phone holders, chargers, bags
- expenses_other: Other business expenses

Document text:
[OCR extracted text]

Extract:
- Date (YYYY-MM-DD)
- Amount (numeric, including GST if applicable)
- Merchant/Counterparty
- Description (1-2 sentences)
- Best matching category ID
- Confidence (0-1)

Output JSON:
{
  "date": "...",
  "amount": ...,
  "merchant": "...",
  "description": "...",
  "category_id": "...",
  "confidence": ...
}
```

**Pack-Specific Rules**:
- Pack categories take precedence over global organization rules during classification
- After user correction, optionally update pack-specific rules OR global rules (user choice)

#### 3.2.3 Triage UI with Pack Context

**Triage Screen Elements**:

1. **Pack Header**:
   - Pack name and icon
   - Progress indicator: "12 documents categorized, 3 need review"
   - Completeness warnings: "⚠️ No fuel expenses yet. Common for rideshare drivers."

2. **Category Hierarchy** (Left Sidebar):
   - Expandable tree showing pack categories
   - Document count per category (e.g., "Rideshare Income (5)")
   - Color-coded: Green (reviewed), Yellow (needs review), Gray (empty)

3. **Document Grid** (Main Area):
   - Thumbnails of documents with suggested category
   - Confidence indicator: ✅ High (≥0.85), ⚠️ Medium (0.60-0.85), ❌ Low (<0.60)
   - Click to review/correct

4. **Document Detail Panel** (Right):
   - Document preview (PDF/image)
   - Extracted metadata: Date, Amount, Merchant, Description
   - Suggested category (dropdown to change)
   - "Save" (accept suggestion) / "Correct" (change category)
   - Option: "Apply this rule to future documents?" (checkbox)

5. **Completeness Checklist** (Bottom):
   - Pack-specific validation warnings:
     - "✅ Rideshare income: 5 documents (Q3 coverage: July-Sept)"
     - "⚠️ Fuel expenses: 0 documents. Did you upload fuel receipts?"
     - "✅ Phone expenses: 1 document"

**User Interactions**:
- **Drag-and-drop**: Drag document thumbnail to category in sidebar → Reassign category
- **Bulk actions**: Select multiple documents → Assign to category in bulk
- **Add manual entry**: Enter transaction manually if no document (e.g., cash expense)
- **Mark complete**: Once reviewed, mark pack as "Ready to Export"

#### 3.2.4 Export with Pack Context

**Export Trigger**:
1. User clicks "Export" button in pack instance
2. Pack validation runs:
   - Check completeness rules (warnings if categories missing)
   - Check file size limits (for immigration packs: max 4MB per file)
   - Prompt user to review warnings (can proceed or cancel)
3. User selects export recipes to generate (checkboxes):
   - ☑ Spreadsheet Summary
   - ☑ PDF Bundles (Per Category)
   - ☑ BAS Form Summary PDF
4. Export engine generates outputs per pack `export_recipes`
5. Outputs saved to user-selected folder:
   - `BAS_2024-Q3_Rideshare/`
     - `BAS_Summary_Spreadsheet.xlsx`
     - `Income_Rideshare_2024-Q3.pdf`
     - `Expenses_Fuel_2024-Q3.pdf`
     - `BAS_Form_Summary_2024-Q3.pdf`
6. Pack state updated: `state: exported`, `exported_at: timestamp`

**Export Engine Logic**:

For each export recipe in pack config:

**Spreadsheet Export**:
1. Load all documents in pack instance
2. Filter by `recipe.sheets[].filter` (e.g., category_parent: "income")
3. Sort by `recipe.sheets[].sort` (e.g., date desc)
4. Populate columns from `recipe.sheets[].columns` sources:
   - `document.date` → Date column
   - `category.name` → Category column
   - `document.amount_total` → Amount (Inc GST) column
5. Calculate totals per `recipe.sheets[].totals`
6. Write to Excel file (using `openpyxl` or similar library)
7. Add disclaimer footer (from pack `disclaimers`)

**PDF Bundle Export**:
1. Load all documents in pack instance
2. Group by category (if `mode: per_category`)
3. For each category:
   - Sort documents by date (per `chronological_order`)
   - Merge PDFs into single file (using `PyPDF2` or `pdfrw`)
   - Generate index page (if `include_index: true`):
     - List documents with page numbers
   - Add cover page (if `include_cover_page: true`):
     - Pack name, category name, date range, disclaimer
   - Save as `{category_name}_{date_range}.pdf`
4. If combined PDF exceeds `max_file_size_mb` → Split into Part 1, Part 2, etc.

**Summary PDF Export**:
1. Load pack category totals (from aggregated document amounts)
2. Map categories to form fields (using pack `mappings.form_fields`)
3. Render HTML template (from `recipe.template`):
   - Replace placeholders: `{{G1_total}}`, `{{1A_total}}`, `{{1B_total}}`
   - Include disclaimer (from pack `disclaimers`)
4. Convert HTML to PDF (using `weasyprint` or `wkhtmltopdf`)
5. Save as `BAS_Form_Summary_{date_range}.pdf`

### 3.3 Pack Update and Versioning

**Scenario**: FileOrganizer Team releases `tax_au_bas_rideshare_v1.1` with new category "Tolls & Parking"

**User Impact**:
- Existing pack instances using v1.0 are NOT affected (frozen at v1.0)
- New pack instances default to v1.1
- User can optionally "upgrade" existing instance to v1.1:
  - Warning: "This may change category structure and export formats. Recommended to review all categorizations after upgrade."
  - User confirms → Pack instance migrated to v1.1
  - Documents re-classified (with new categories available)

**Version Compatibility**:
- **Major version bump** (1.x → 2.x): Breaking changes (category IDs renamed, mappings changed) → User MUST manually upgrade
- **Minor version bump** (1.0 → 1.1): New features (new categories, export recipes) → User can upgrade seamlessly
- **Patch version bump** (1.0.0 → 1.0.1): Bug fixes (typos, validation improvements) → Auto-upgrade recommended (non-breaking)

**Implementation**:
- Pack templates stored with version in filename: `tax_au_bas_rideshare_v1.0.0.yaml`
- Pack instance references specific version
- Pack library shows "Update Available" badge if newer version exists
- User can view changelog before upgrading

---

## 4. Handling Unknowns and User Corrections

### 4.1 Unknown Document Flow

**Scenario**: User uploads receipt, but LLM cannot confidently classify it (confidence < 0.60)

**Triage UI**:
1. Document appears in "Needs Review" section (top of triage screen)
2. Document detail panel shows:
   - Extracted text (OCR)
   - Suggested category: "Unknown" (with confidence: 45%)
   - Dropdown: All pack categories (user must select)
3. User selects correct category (e.g., "Fuel Expenses")
4. System prompts: "Help me learn: Why is this Fuel Expenses?"
   - User can add note (e.g., "It's from BP, which is a fuel station")
   - OR select classification hint to reinforce (e.g., "Merchant name: BP")
5. User clicks "Save"
6. System updates:
   - Document assigned to "Fuel Expenses"
   - Pack-instance rule created: "Receipts from BP → Fuel Expenses" (if user opted to persist rule)

### 4.2 Correction Persistence Levels

**Three Levels of Persistence**:

1. **Ephemeral (Pack Instance Only)**:
   - Correction applies only to current pack instance
   - Does not affect future packs or global rules
   - Use case: One-off exception (e.g., unusual transaction)

2. **Pack Template (Future Instances of This Pack)**:
   - Correction updates pack template's `classification_hints` for future uses
   - Affects all new instances of this pack (e.g., next quarter's BAS)
   - Use case: Pack-specific pattern (e.g., "Uber earnings always go to Rideshare Income")

3. **Global (All Packs)**:
   - Correction updates core organization rules engine
   - Affects all packs and general organization
   - Use case: Universal pattern (e.g., "Documents from ato.gov.au are always Official Correspondence")

**User Choice**:
- After user corrects category, show dialog:
  ```
  Apply this correction:
  ( ) Only to this document (ephemeral)
  (•) To future documents in this pack (pack template)
  ( ) To all documents across all packs (global rule)
  ```
- Default: Pack template (most common use case)
- Advanced users: Can switch to global rules for broader impact

### 4.3 Rule Learning and Feedback Loop

**Learning Mechanism**:
1. User correction captured: `"Receipts from {merchant} → {category}"`
2. LLM generates rule:
   - Condition: `merchant_name == "BP"` OR `keywords.contains("BP")`
   - Action: Assign to `category_id: expenses_fuel`
   - Confidence boost: +0.15 (if this merchant appears again, confidence increases)
3. Rule stored in pack instance or pack template (per user choice)
4. Future documents: LLM checks rules before classifying → Apply matching rules

**Feedback Loop**:
- After 10-20 documents, system can suggest: "I noticed you often assign receipts from BP to Fuel Expenses. Should I create a rule for this?"
- User confirms → Rule persisted at chosen level

---

## 5. Safety and Disclaimers

### 5.1 Disclaimer Placement

**Mandatory Disclaimer Contexts**:

1. **Pack Selection Screen**:
   - Display `disclaimers.primary` prominently before user starts pack
   - Require checkbox acknowledgment: "I understand this pack is an organizational tool and NOT professional advice."
   - Link to full disclaimer text (popup or separate page)

2. **Export Outputs**:
   - **Spreadsheets**: Include disclaimer in footer row (all sheets)
     - Example: "Disclaimer: This summary is for organizational purposes only. Not tax advice. Consult a registered tax agent."
   - **PDFs**: Include disclaimer on cover page or footer of each page
     - Font: 10pt, gray text, bottom of page
   - **Summary Reports**: Disclaimer at top (bold, boxed)
     - Example:
       ```
       ⚠️ IMPORTANT DISCLAIMER
       This BAS summary organizes your documents and shows category totals.
       It is NOT tax advice and does NOT calculate GST liabilities or determine deductibility.
       Consult a registered tax agent for professional guidance.
       ```

3. **Pack Instance UI**:
   - Show disclaimer icon/link in pack header (always accessible)
   - Display `additional` disclaimers in help panel (collapsible)

### 5.2 Disclaimer Language by Domain

**Tax Domain**:
```
Primary:
"This pack organizes your documents and provides category summaries to assist with tax preparation. It is NOT tax advice and does NOT determine deductibility or calculate tax liabilities. Consult a registered tax agent or accountant for professional guidance."

Additional:
- "FileOrganizer does not verify document authenticity or accuracy."
- "You are responsible for reviewing all categorizations and totals before submitting to tax authorities."
- "Tax thresholds, rates, and rules may change. Consult your local tax authority for current requirements."
```

**Immigration Domain**:
```
Primary:
"This pack organizes visa evidence based on official immigration guidance. It is NOT immigration advice and does NOT assess eligibility or likelihood of approval. Consult a registered migration agent (MARA), immigration attorney, RCIC, or licensed immigration adviser for case-specific guidance."

Additional:
- "Visa requirements and processing times may change. Check official immigration websites for current information."
- "This pack does NOT guarantee visa approval. Immigration decisions are made solely by government authorities."
- "You are responsible for ensuring all evidence is authentic and accurately represents your circumstances."
```

**Legal Domain**:
```
Primary:
"This legal timeline and evidence bundle are organizational tools. They are NOT legal advice and do NOT replace attorney review. Verify all entries, citations, and formatting comply with applicable court rules before submission."

Additional:
- "FileOrganizer does not verify the accuracy or admissibility of evidence."
- "You are responsible for ensuring compliance with court deadlines, formatting requirements, and procedural rules."
- "Consult your attorney before submitting any legal documents to court or opposing parties."
```

### 5.3 Handling Sensitive Data

**Privacy Principles** (Aligned with FileOrganizer's Local-First Design):
1. **No Cloud Upload**: All processing on-device (OCR, LLM classification, export)
2. **No External API Calls for Classification**: Use local LLM models (or user's own API keys if cloud LLM required)
3. **Encrypted Storage**: Pack instances and documents stored encrypted on disk
4. **User Control**: User can delete pack instances and all associated data at any time

**Sensitive Document Warnings**:
- If LLM detects sensitive data (SSN, passport numbers, financial accounts), warn user:
  ```
  ⚠️ Sensitive Data Detected
  This document may contain sensitive information (e.g., passport number, bank account).
  Ensure exports are stored securely and only shared with trusted parties.
  ```

**Redaction Feature** (Optional, Future):
- Allow user to redact sensitive fields before export (e.g., redact passport number in exported PDF)

---

## 6. Country and Pack Extensibility

### 6.1 Adding a New Country Pack

**Process**:
1. Research country-specific requirements (see `research_report_tax_immigration_legal_packs.md` as example)
2. Create pack YAML:
   - Copy template from similar country (e.g., copy `tax_au_bas_rideshare_v1.yaml` → `tax_nz_gst_rideshare_v1.yaml`)
   - Update `metadata.country: NZ`
   - Update categories (if different)
   - Update `mappings.form_fields` (NZ IR3 fields instead of AU BAS fields)
   - Update `thresholds` (NZ GST threshold: $60K, rate: 15%)
   - Update `disclaimers` (reference Inland Revenue NZ instead of ATO)
3. Validate YAML against JSON Schema
4. Test pack:
   - Load in FileOrganizer
   - Upload sample documents
   - Verify categorization, export outputs
5. Submit to pack library (if community contribution) OR merge to main pack repository

**No Code Changes Required** (if pack uses existing export recipe types like `spreadsheet`, `pdf_bundle`, `summary_pdf`)

**Code Changes Required** (if pack needs new export recipe type):
- Example: New recipe type `visual_gantt_chart` for legal timelines
- Implement export engine plugin for `visual_gantt_chart`
- Update pack schema to support new recipe type

### 6.2 Pack Template Inheritance (Future)

**Concept**: Allow packs to inherit from parent packs to reduce duplication

**Example**:
```yaml
pack:
  metadata:
    id: "tax_au_bas_rideshare_v1"
    extends: "tax_generic_v1"  # Inherit categories and export recipes from generic pack

  # Override or extend parent categories
  categories:
    - id: "income_rideshare"  # New category not in parent
      parent: "income"
      # ...

  # Override parent mappings
  mappings:
    form_fields:  # Add AU-specific form fields
      - category_id: "income_rideshare"
        fields:
          - field_id: "G1"  # AU BAS field
```

**Benefits**:
- Reduce YAML size (inherit common structure)
- Easier maintenance (update parent pack → all children inherit changes)

**Implementation**:
- Pack loader resolves inheritance (merge parent + child YAMLs)
- Conflicts: Child values override parent values

### 6.3 Community Pack Contributions

**Community Pack Repository** (Future):
- GitHub repo: `fileorganizer-community-packs`
- Users can submit new packs via pull request
- Moderation: FileOrganizer team reviews for:
  - Accuracy (does pack match official guidance?)
  - Safety (are disclaimers appropriate?)
  - Quality (is YAML well-structured, tested?)
- Approved packs added to official pack library (or "Community" section)

**Pack Rating System**:
- Users can rate packs (1-5 stars)
- Reviews: "This pack worked great for my UK Self Assessment!"
- Metrics: Downloads, success rate (% of users who export successfully)

**Pack Authorship**:
- `metadata.author`: Credit to community contributor
- `metadata.license`: Open-source license (e.g., MIT, CC-BY)

---

## 7. Prioritized Milestones

### Milestone 1: Pack Schema + Core Hooks (Weeks 1-3)

**Goals**:
- Define and validate pack YAML schema (Section 1)
- Implement pack loader and validator (JSON Schema validation)
- Integrate pack categories into core ingestion pipeline (LLM classification with pack context)
- Basic triage UI with pack category hierarchy (left sidebar, document grid)

**Deliverables**:
- `pack_schema.json`: JSON Schema for pack YAML
- `pack_loader.py`: Load and validate pack YAMLs
- `classification_engine.py`: LLM classification with pack-aware prompts
- Triage UI mockup (Figma or HTML prototype)

**Success Criteria**:
- Load `tax_generic_v1.yaml` successfully
- Classify 10 sample documents (receipts, invoices) into pack categories with ≥80% accuracy
- Display pack categories in triage UI

**Estimated Effort**: 2-3 weeks (1 developer)

---

### Milestone 2: Generic Packs + Spreadsheet Export (Weeks 4-6)

**Goals**:
- Implement Tier 1 packs: `tax_generic_v1`, `immigration_generic_relationship_v1`
- Implement spreadsheet export recipe (Section 1.2.5)
- Completeness validation (Section 1.2.7)

**Deliverables**:
- `tax_generic_v1.yaml`: Generic tax pack
- `immigration_generic_relationship_v1.yaml`: Generic immigration pack
- `spreadsheet_exporter.py`: Generate Excel/CSV from pack data
- Validation engine: Check completeness rules, show warnings

**Success Criteria**:
- Load and use both generic packs
- Export spreadsheet summary for tax pack (Date, Category, Amount, Notes)
- Show validation warning if recommended category is empty

**Estimated Effort**: 2-3 weeks (1 developer)

---

### Milestone 3: Country-Specific Packs + PDF Bundles (Weeks 7-10) **[PHASE 2 - NOT v1.0]**

**⚠️ DEFERRED TO PHASE 2**: Per GPT's strategic review, country-specific packs are NOT in v1.0 scope.

**Goals** (Phase 2):
- Implement `tax_au_bas_rideshare_v1.yaml` (Australia BAS - Rideshare)
- Implement PDF bundle export recipe (per-category PDFs with index)
- Form field mappings (category → BAS fields G1, 1A, 1B)
- Summary PDF export (BAS Form Summary)

**Deliverables**:
- `tax_au_bas_rideshare_v1.yaml`: Australia BAS pack
- `pdf_bundle_exporter.py`: Generate per-category PDFs with index
- `summary_pdf_exporter.py`: Render HTML template → PDF (BAS summary)
- HTML template: `bas_summary_template.html`

**Success Criteria**:
- User completes BAS pack for rideshare driver (upload 20+ documents)
- Export 3 outputs:
  1. Spreadsheet summary (Income, Expenses, Category Totals sheets)
  2. Per-category PDFs (Income Rideshare, Fuel Expenses, etc.)
  3. BAS Form Summary PDF (showing G1, 1A, 1B totals with disclaimer)
- Validate against real BAS requirements (consult accountant or tax agent for feedback)

**Estimated Effort**: 3-4 weeks (1-2 developers)

---

### Milestone 4: Triage Polish + Legal Timeline (Weeks 11-13) **[PHASE 2 - NOT v1.0]**

**⚠️ DEFERRED TO PHASE 2**: Advanced triage features (drag-and-drop, bulk actions) are Phase 2. Basic triage is in v1.0.

**Goals** (Phase 2):
- Polish triage UI (drag-and-drop, bulk actions, completeness checklist)
- Implement `legal_generic_timeline_v1.yaml` (Legal timeline pack) **[v1.0 includes basic version]**
- Implement timeline export (chronology spreadsheet + evidence bundle)
- User correction persistence (Section 4.2)

**Deliverables**:
- Triage UI v2: Enhanced with drag-and-drop, bulk category assignment
- `legal_generic_timeline_v1.yaml`: Legal timeline pack **[basic version in v1.0]**
- `timeline_exporter.py`: Generate chronology spreadsheet (Date, Event, Source, Category)
- Evidence bundle exporter: Numbered documents + index
- Correction persistence: User choice (ephemeral, pack template, global)

**Success Criteria**:
- User creates legal timeline (20+ events across 6 months)
- Export chronology spreadsheet (sorted by date, with source references)
- Export evidence bundle PDF (all source documents, indexed, numbered)
- User corrects 5 misclassified documents → Persistence rules applied to future uploads

**Estimated Effort**: 2-3 weeks (1-2 developers)

---

### Milestone 5: Additional Country Packs (Weeks 14-16) **[PHASE 2 - NOT v1.0]**

**⚠️ DEFERRED TO PHASE 2**: All country-specific packs are Phase 2.

**Goals** (Phase 2):
- Implement Tier 2 packs:
  - `tax_uk_selfassessment_v1.yaml`
  - `immigration_au_partner_820_v1.yaml`
  - `immigration_uk_spouse_v1.yaml`
- Test with real users (alpha testing)

**Deliverables**:
- 3 additional country-specific packs
- Alpha testing feedback report

**Success Criteria**:
- 10 alpha testers complete packs successfully (≥80% satisfaction)
- Identify and fix top 5 usability issues

**Estimated Effort**: 3-4 weeks (1-2 developers)

---

### Total Estimated Timeline

**✅ v1.0 (Milestones 1-2)**: 4-6 weeks (generic packs only)
**❌ Phase 2 (Milestones 3-5)**: 7-11 weeks (country-specific packs, deferred)
**❌ Phase 2.5 (Premium Infrastructure)**: 4-6 weeks (Immigration Premium Service, deferred)

**v1.0 Assumptions**:
- 1-2 developers working on pack system
- Parallel work on other FileOrganizer features (core organization engine, UI/UX, platform integrations)
- Research and design completed upfront (this document)
- **Focus on generic packs only** - no country-specific templates, form mappings, or Premium infrastructure

---

## 8. Risk Mitigation

### 8.1 Technical Risks

**Risk 1: LLM Classification Accuracy <80%**
- **Impact**: Users spend excessive time correcting misclassifications → Poor UX
- **Mitigation**:
  - Use strong LLM models (GPT-4, Claude Sonnet) for classification
  - Provide rich `classification_hints` in pack configs (keywords, sender domains, file patterns)
  - Implement correction feedback loop (Section 4.3) to improve over time
  - Fall back to user triage for low-confidence classifications (don't auto-assign if confidence <0.60)
- **Contingency**: If accuracy remains low after Milestone 2, invest in fine-tuning LLM on pack-specific training data

**Risk 2: Export Formats Don't Match Real-World Requirements**
- **Impact**: Users cannot submit exports to accountants, immigration portals, courts → Pack system fails
- **Mitigation**:
  - Validate export formats against official guidance (research report, Section 1-3)
  - Consult domain experts (tax agents, migration agents, lawyers) during Milestone 3-4
  - Alpha testing with real users (Milestone 5)
  - Provide "Preview" mode for exports (users can review before finalizing)
- **Contingency**: If exports fail validation, iterate on export recipes (minor version bump)

**Risk 3: Pack Complexity Overwhelms Users**
- **Impact**: Users don't understand pack categories or get lost in triage UI → Abandonment
- **Mitigation**:
  - Start with simple generic packs (Tier 1) before complex country-specific packs
  - Provide onboarding tooltips and guided tutorials
  - Show "Typical Documents" hints in triage UI (from pack `typical_documents`)
  - Completeness checklist helps users know what's missing
- **Contingency**: If user testing shows confusion, simplify packs (reduce category depth) and improve UI copy

### 8.2 Legal/Compliance Risks

**Risk 4: Users Misinterpret Pack Outputs as Professional Advice**
- **Impact**: Legal liability if users rely on pack summaries as tax/legal/immigration advice → Lawsuits
- **Mitigation**:
  - Mandatory, prominent disclaimers (Section 5.1-5.2) at every touchpoint
  - Require user acknowledgment before starting pack
  - Include disclaimers in all exports (footers, headers, cover pages)
  - Avoid language that implies advice (e.g., don't say "You should claim this deduction", say "This category organizes fuel expenses")
- **Contingency**: Consult legal counsel to review disclaimers and pack language before public release

**Risk 5: Pack Configs Contain Errors (Wrong Form Fields, Thresholds, Guidance)**
- **Impact**: Users generate incorrect summaries → Tax penalties, visa rejections, legal errors
- **Mitigation**:
  - Rigorous research (this research report)
  - Expert review (tax agents, migration agents, lawyers) for each country-specific pack
  - Versioning: Corrections published as pack updates (minor/patch versions)
  - Community feedback: Users can report errors → Fast-track fixes
- **Contingency**: If error discovered post-release, issue urgent pack update + notify affected users

### 8.3 Business Risks

**Risk 6: Low Adoption (Users Prefer Manual Organization)**
- **Impact**: Pack system underutilized → Wasted development effort
- **Mitigation**:
  - Focus on high-value, painful use cases (tax prep, visa applications) where manual organization is tedious
  - Emphasize time savings and completeness checking (not just categorization)
  - Marketing: Case studies showing "Save 10 hours on BAS prep with FileOrganizer packs"
- **Contingency**: If adoption low, pivot to simpler "smart folder" templates instead of full packs

**Risk 7: Community Packs Are Low Quality**
- **Impact**: Bad packs damage FileOrganizer's reputation
- **Mitigation**:
  - Moderation: Review all community packs before publishing
  - Rating system: Surface high-quality packs, demote low-quality
  - Clear separation: "Official Packs" vs "Community Packs" in UI
- **Contingency**: If moderation overhead too high, limit community contributions to "power users" (verified contributors)

---

## 9. Future Enhancements

### 9.1 Advanced Features (Post-MVP)

**Feature 1: AI-Powered Document Suggestions**
- **Concept**: Pack suggests missing documents based on user's profile
- **Example**: "You uploaded Uber earnings but no fuel receipts. Rideshare drivers typically spend 30-40% of gross income on fuel. [Upload Fuel Receipts]"
- **Implementation**: LLM analyzes pack state → Identifies gaps → Suggests evidence types

**Feature 2: Multi-Period Packs**
- **Concept**: Track multiple quarters/years in single pack instance
- **Example**: "2024 BAS Pack" contains Q1, Q2, Q3, Q4 as sub-packs
- **Export**: Year-end summary showing all 4 quarters
- **Use Case**: Annual tax returns (aggregate all quarters)

**Feature 3: Pack Templates with Pre-Filled Rules**
- **Concept**: User saves their corrections as custom pack template
- **Example**: User creates "My Rideshare Pack" with rules for their specific merchants (Uber, BP, Vodafone) → Reuse for next quarter with minimal triage
- **Implementation**: "Save as Template" button in pack instance → Creates new pack YAML with user's rules

**Feature 4: Real-Time Collaboration**
- **Concept**: Multiple users work on same pack instance (e.g., accountant + client)
- **Example**: Client uploads documents, accountant reviews and corrects categories, both see updates live
- **Implementation**: Sync pack instance via encrypted cloud storage (optional, user opt-in)

**Feature 5: Integration with Tax Software**
- **Concept**: Export pack data directly to Xero, QuickBooks, TurboTax
- **Example**: "Export to Xero" button → Sends category totals + documents to Xero via API
- **Implementation**: OAuth integration with tax software APIs, map pack categories to accounting categories

**Feature 6: Visual Timeline for Immigration Packs**
- **Concept**: Generate visual relationship timeline (Gantt-style) showing key events (met, moved in, engaged, married, etc.)
- **Export**: PDF with graphical timeline + photos at key milestones
- **Use Case**: Immigration applications (relationship development evidence)

### 9.2 Internationalization (i18n)

**Languages**:
- Initial: English (AU, UK, US, CA, NZ)
- Future: French (Canada), Spanish (US), Mandarin (AU), Hindi (AU), etc.

**Approach**:
- Pack YAMLs support `locales` field:
  ```yaml
  metadata:
    name:
      en: "Australia BAS - Rideshare Driver"
      fr: "Australie BAS - Chauffeur de covoiturage"
  ```
- UI strings externalized (using i18n library like `react-i18next`)
- Disclaimers translated by legal experts (not machine translation)

### 9.3 Accessibility

**WCAG 2.1 AA Compliance**:
- Triage UI: Keyboard navigation (arrow keys to move between documents, Enter to review)
- Color contrast: Ensure category colors meet AA standards
- Screen reader support: ARIA labels for all UI elements
- Alt text for document thumbnails

---

## 10. Conclusion

This implementation plan provides a **comprehensive, actionable blueprint** for FileOrganizer's scenario pack system, covering:

1. **Pack Configuration Schema** (Section 1): YAML format with metadata, categories, mappings, export recipes, disclaimers
2. **Initial Pack Templates** (Section 2): 4 Tier 1 packs (Generic Tax, AU BAS Rideshare, Generic Immigration, Generic Legal Timeline)
3. **Core Integration** (Section 3): Pack lifecycle, ingestion, triage, export pipelines
4. **User Corrections** (Section 4): Ephemeral, pack template, and global persistence levels
5. **Safety** (Section 5): Disclaimers, sensitive data handling, privacy principles
6. **Extensibility** (Section 6): Adding new countries, community contributions, pack inheritance
7. **Milestones** (Section 7): 5 milestones over 14-18 weeks (3.5-4.5 months)
8. **Risk Mitigation** (Section 8): Technical, legal, and business risks with mitigations
9. **Future Enhancements** (Section 9): AI suggestions, multi-period packs, integrations, i18n, accessibility

**Next Steps**:
1. **Review and Approval**: Stakeholders review this plan + companion research report
2. **Milestone 1 Kickoff**: Start pack schema definition and core hooks (Week 1)
3. **Alpha Testing Plan**: Define alpha testing criteria and recruit testers (by Week 10)
4. **Legal Review**: Engage legal counsel to review disclaimers (before public release)
5. **Marketing Prep**: Draft case studies and messaging for pack system launch (Weeks 12-16)

**This plan is ready for implementation. Let's build the pack system that makes FileOrganizer indispensable for tax, immigration, and legal workflows.**

---

## Appendix A: Full Pack YAML Example

### `tax_au_bas_rideshare_v1.yaml`

```yaml
pack:
  metadata:
    id: "tax_au_bas_rideshare_v1"
    name: "Australia BAS - Rideshare Driver"
    domain: "tax"
    country: "AU"
    version: "1.0.0"
    author: "FileOrganizer Team"
    created: "2025-11-27"
    updated: "2025-11-27"
    description: |
      Organizes quarterly BAS evidence for Australian rideshare drivers (Uber, Ola, DiDi, etc.).
      Supports GST-registered and non-registered sole traders.
      Generates BAS summary spreadsheet, per-category PDFs, and form field mapping to G1, 1A, 1B.
    tags:
      - "rideshare"
      - "uber"
      - "sole-trader"
      - "quarterly-bas"
      - "gst"
    min_app_version: "1.0.0"

  disclaimers:
    primary: |
      This pack organizes your documents and provides category summaries to assist with BAS preparation.
      It is NOT tax advice and does NOT determine deductibility or calculate GST liabilities.
      Consult a registered tax agent or accountant for professional guidance.

    additional:
      - "FileOrganizer does not verify document authenticity or accuracy."
      - "You are responsible for reviewing all categorizations and totals before submitting to the ATO."
      - "GST thresholds and BAS rules may change. Consult the ATO website for current requirements."
      - "This pack assumes you are a sole trader. Different rules apply for companies, partnerships, and trusts."

    display_contexts:
      - "pack_selection"
      - "export_footer"
      - "summary_header"

  categories:
    # INCOME
    - id: "income"
      name: "Income"
      parent: null
      description: "All income sources"
      icon: "currency-dollar"
      color: "#4CAF50"

    - id: "income_rideshare"
      name: "Rideshare Income"
      parent: "income"
      description: "Uber, Ola, DiDi earnings statements and payouts"
      typical_documents:
        - "Platform weekly/monthly earnings summaries (PDF)"
        - "Bank deposit records showing platform payouts"
        - "Annual tax summaries from Uber, Ola, DiDi"
      classification_hints:
        keywords:
          - "uber"
          - "ola"
          - "didi"
          - "rideshare"
          - "driver earnings"
          - "trip earnings"
        sender_domains:
          - "uber.com"
          - "ola.com.au"
          - "didi.com.au"
        file_patterns:
          - "*uber*earnings*.pdf"
          - "*ola*payout*.pdf"
          - "*didi*summary*.pdf"
      validation:
        recommended_timeframe: "quarterly"
        min_documents: 1
        warning_if_missing: "Rideshare income is the primary income source for this pack. Did you upload platform statements?"

    - id: "income_direct"
      name: "Direct Client Income"
      parent: "income"
      description: "Invoices or payments from direct clients (non-platform)"
      typical_documents:
        - "Invoices issued to clients"
        - "Payment receipts from direct customers"
      classification_hints:
        keywords:
          - "invoice"
          - "payment received"
          - "client payment"
        file_patterns:
          - "*invoice*.pdf"
      validation:
        recommended_timeframe: "quarterly"
        warning_if_missing: null  # Optional for rideshare drivers

    - id: "income_other"
      name: "Other Income"
      parent: "income"
      description: "Other business income (interest, subsidies, etc.)"

    # EXPENSES
    - id: "expenses"
      name: "Expenses"
      parent: null
      description: "All business expenses"
      icon: "receipt"
      color: "#FF5722"

    - id: "expenses_fuel"
      name: "Fuel Expenses"
      parent: "expenses"
      description: "Fuel receipts for business use"
      typical_documents:
        - "Fuel receipts (paper or digital)"
        - "Credit card statements showing fuel purchases at BP, Shell, Caltex, etc."
      classification_hints:
        keywords:
          - "fuel"
          - "petrol"
          - "diesel"
          - "gasoline"
          - "service station"
        merchant_names:
          - "BP"
          - "Shell"
          - "Caltex"
          - "7-Eleven"
          - "Ampol"
          - "United Petroleum"
      deduction_notes: |
        You can claim business use % × total fuel costs.
        Keep a logbook if business km >5,000/year (ATO requirement).
      validation:
        recommended_timeframe: "quarterly"
        min_documents: 1
        warning_if_missing: "Fuel is often the largest expense for rideshare drivers (30-40% of gross income). Did you upload fuel receipts?"

    - id: "expenses_vehicle"
      name: "Vehicle Maintenance & Repairs"
      parent: "expenses"
      description: "Vehicle servicing, repairs, registration, insurance"
      typical_documents:
        - "Mechanic invoices"
        - "Vehicle registration renewal"
        - "Car insurance premiums"
      classification_hints:
        keywords:
          - "mechanic"
          - "service"
          - "repair"
          - "registration"
          - "insurance"
          - "car insurance"
          - "rego"
      deduction_notes: "Claim business use % of vehicle expenses."
      validation:
        recommended_timeframe: "annual"

    - id: "expenses_phone"
      name: "Phone & Internet"
      parent: "expenses"
      description: "Phone bills and internet (business use %)"
      typical_documents:
        - "Mobile phone bills"
        - "Home internet bills"
      classification_hints:
        keywords:
          - "telstra"
          - "optus"
          - "vodafone"
          - "phone bill"
          - "internet"
        merchant_names:
          - "Telstra"
          - "Optus"
          - "Vodafone"
      deduction_notes: "Claim business use % (typically 50-80% for rideshare drivers)."

    - id: "expenses_home_office"
      name: "Home Office"
      parent: "expenses"
      description: "Home office expenses (if applicable)"
      typical_documents:
        - "Home office logbook"
        - "Utility bills (electricity, gas, water)"
        - "Rent or mortgage statements"
      deduction_notes: |
        Claim business use % of home expenses if you use home for admin/planning.
        Shortcut method: $0.67 per hour worked from home (2024-25 rate).
      validation:
        warning_if_missing: null  # Optional for rideshare drivers

    - id: "expenses_equipment"
      name: "Equipment"
      parent: "expenses"
      description: "Phone holders, chargers, cleaning supplies, etc."
      typical_documents:
        - "Receipts for phone holders, chargers, USB cables"
        - "Cleaning supplies (car wash, interior cleaning)"
      classification_hints:
        keywords:
          - "phone holder"
          - "charger"
          - "usb cable"
          - "car wash"
          - "cleaning"

    - id: "expenses_other"
      name: "Other Expenses"
      parent: "expenses"
      description: "Other allowable business expenses"

  mappings:
    form_fields:
      - category_id: "income_rideshare"
        fields:
          - field_id: "G1"
            field_name: "Total Sales (Including GST)"
            description: "Gross rideshare income including 10% GST"
            calculation: "sum"
            include_gst: true
          - field_id: "1A"
            field_name: "GST on Sales"
            description: "10% of total sales (for GST-registered sole traders)"
            calculation: "derived"
            formula: "G1 * 0.10"
            note: "Only report 1A if you are GST-registered (turnover ≥$75K)"

      - category_id: "income_direct"
        fields:
          - field_id: "G1"
            field_name: "Total Sales (Including GST)"
            calculation: "sum"
            include_gst: true
          - field_id: "1A"
            field_name: "GST on Sales"
            calculation: "derived"
            formula: "G1 * 0.10"

      - category_id: "income_other"
        fields:
          - field_id: "G1"
            field_name: "Total Sales (Including GST)"
            calculation: "sum"

      - category_id: "expenses_fuel"
        fields:
          - field_id: "1B"
            field_name: "GST on Purchases"
            description: "GST component of fuel expenses (10% of total)"
            calculation: "sum_gst_component"
            note: "Only claimable if GST-registered. Claim business use % only."

      - category_id: "expenses_vehicle"
        fields:
          - field_id: "1B"
            field_name: "GST on Purchases"
            calculation: "sum_gst_component"

      - category_id: "expenses_phone"
        fields:
          - field_id: "1B"
            field_name: "GST on Purchases"
            calculation: "sum_gst_component"
            note: "Claim business use % only (e.g., 50-80%)."

      - category_id: "expenses_equipment"
        fields:
          - field_id: "1B"
            field_name: "GST on Purchases"
            calculation: "sum_gst_component"
            note: "Can claim GST if item cost >$82.50 (inc GST)."

  export_recipes:
    - id: "spreadsheet_summary"
      type: "spreadsheet"
      format: "xlsx"
      name: "BAS Summary Spreadsheet"
      description: "Excel workbook with income, expenses, and category totals"
      sheets:
        - name: "Income Summary"
          columns:
            - { id: "date", name: "Date", format: "date", source: "document.date" }
            - { id: "description", name: "Description", source: "document.description" }
            - { id: "category", name: "Category", source: "category.name" }
            - { id: "amount_inc_gst", name: "Amount (Inc GST)", format: "currency", source: "document.amount_total" }
            - { id: "gst_component", name: "GST Component (10%)", format: "currency", source: "document.gst_amount" }
            - { id: "counterparty", name: "Source/Platform", source: "document.counterparty" }
            - { id: "notes", name: "Notes", source: "document.notes" }
          filter:
            category_parent: "income"
          sort:
            - { column: "date", order: "desc" }
          totals:
            - { column: "amount_inc_gst", label: "Total Income (Inc GST)" }
            - { column: "gst_component", label: "Total GST on Income (1A)" }

        - name: "Expense Summary"
          columns:
            - { id: "date", name: "Date", format: "date", source: "document.date" }
            - { id: "description", name: "Description", source: "document.description" }
            - { id: "category", name: "Category", source: "category.name" }
            - { id: "amount_inc_gst", name: "Amount (Inc GST)", format: "currency", source: "document.amount_total" }
            - { id: "gst_component", name: "GST Component (10%)", format: "currency", source: "document.gst_amount" }
            - { id: "merchant", name: "Merchant", source: "document.merchant" }
            - { id: "business_use_pct", name: "Business Use %", format: "percentage", source: "document.business_use_pct" }
            - { id: "notes", name: "Notes", source: "document.notes" }
          filter:
            category_parent: "expenses"
          sort:
            - { column: "date", order: "desc" }
          totals:
            - { column: "amount_inc_gst", label: "Total Expenses (Inc GST)" }
            - { column: "gst_component", label: "Total GST on Expenses (1B)" }

        - name: "Category Totals"
          columns:
            - { id: "category", name: "Category", source: "category.name" }
            - { id: "count", name: "# Documents", format: "number" }
            - { id: "total_inc_gst", name: "Total (Inc GST)", format: "currency" }
            - { id: "gst_component", name: "GST Component", format: "currency" }
          aggregation: "by_category"
          sort:
            - { column: "category", order: "asc" }

    - id: "pdf_bundles_per_category"
      type: "pdf_bundle"
      mode: "per_category"
      name: "PDF Evidence Bundles (Per Category)"
      description: "One PDF per category, chronologically ordered with index"
      include_index: true
      include_cover_page: true
      chronological_order: "desc"  # Most recent first
      combine_subcategories: true  # Merge all fuel/vehicle/phone into "Expenses" PDF
      max_file_size_mb: 60
      filename_template: "{category_name}_{date_range}.pdf"

    - id: "bas_summary_pdf"
      type: "summary_pdf"
      name: "BAS Form Summary"
      description: "PDF showing category totals mapped to BAS form fields (G1, 1A, 1B)"
      template: "bas_summary_template.html"
      include_disclaimer: true
      sections:
        - title: "Income Summary (G1, 1A)"
          mappings: [ "G1", "1A" ]
          show_breakdown: true  # Show subcategories (Rideshare, Direct, Other)
        - title: "Expense Summary (1B)"
          mappings: [ "1B" ]
          show_breakdown: true
        - title: "Net GST Position"
          formula: "1A - 1B"
          label: "GST Refund (if 1B > 1A) or Payment (if 1A > 1B)"

  thresholds:
    - id: "gst_registration"
      name: "GST Registration Threshold"
      value: 75000
      currency: "AUD"
      period: "annual"
      description: "Required to register for GST if annual turnover ≥$75,000 (current threshold as of 2024-25)"
      info_url: "https://www.ato.gov.au/businesses-and-organisations/gst-excise-and-indirect-taxes/goods-and-services-tax-gst/registering-for-gst"

    - id: "logbook_requirement"
      name: "Logbook Requirement for Vehicle Expenses"
      value: 5000
      unit: "km"
      period: "annual"
      description: "Logbook required if claiming vehicle expenses for >5,000 business km per year"
      info_url: "https://www.ato.gov.au/businesses-and-organisations/corporate-tax-measures-and-assurance/keeping-business-records/logbook-method"

  validation:
    completeness_checks:
      - rule: "at_least_one_income_category"
        message: "You haven't categorized any income documents. BAS requires income reporting (Field G1)."
        severity: "error"

      - rule: "recommended_categories_present"
        categories: [ "income_rideshare", "expenses_fuel" ]
        message: "Common categories for rideshare drivers: Rideshare Income and Fuel Expenses. Did you upload all relevant documents?"
        severity: "warning"

      - rule: "timeframe_coverage"
        category: "income_rideshare"
        min_months: 3
        message: "Quarterly BAS requires income evidence for 3 months. Current coverage: {actual_months} months. Upload missing weeks/months."
        severity: "warning"

      - rule: "gst_registration_check"
        condition: "total_income_annual >= 75000"
        message: "Your annual income may exceed $75,000. You may need to register for GST. Consult the ATO or a tax agent."
        severity: "info"
```

---

**End of Implementation Plan**

**Total Word Count**: ~14,500 words

**Document Status**: Final, ready for review and development kickoff

**Next Action**: Stakeholder review → Milestone 1 kickoff (Pack schema + core hooks)
