# Immigration / Visa Evidence Packs: Detailed Specification

**Date**: 2025-11-27
**Purpose**: Comprehensive specification for immigration pack templates across AU, UK, US, CA, NZ
**Inputs**:
- `cursor_research_brief_immigration_visa_evidence_packs_v2.md`
- `cursor_build_prompt_immigration_visa_pack_compiler.md`
- `research_report_tax_immigration_legal_packs.md` (Part 2: Immigration Domain)

**Status**: Ready for GPT Strategic Review

---

## Executive Summary

This specification defines the **VisaPackTemplate** system for FileOrganizer's immigration evidence compiler. It provides:

1. **Template Schema**: Concrete YAML/JSON structure for visa pack templates
2. **Country Coverage**: AU, UK, US, CA, NZ with 3-5 priority visa types each
3. **Evidence Categories**: Detailed category structures per visa type with portal alignment
4. **Packaging Guidance**: How to compile evidence into portal-ready uploads
5. **Volatility Assessment**: Maintenance strategy and expert verification requirements
6. **Implementation Handover**: Phase 1 (MVP) vs Phase 2 priority recommendations

**Key Design Principles**:
- ✅ **Template-Driven**: All visa logic in external YAML, not hard-coded
- ✅ **Portal-Aligned**: Categories map to official portal upload sections
- ✅ **Volatility-Aware**: Templates flagged by change frequency (high/medium/low)
- ✅ **Expert-Verified**: All templates reviewed by licensed migration agents/attorneys
- ✅ **Non-Advisory**: Organizational tool only, NOT legal advice

---

## Part 1: VisaPackTemplate Schema

### 1.1 Schema Overview

Each visa pack template is defined as a structured document (YAML or JSON) with the following top-level structure:

```yaml
VisaPackTemplate:
  metadata:           # Template identity and versioning
  evidence_categories: # Hierarchical evidence structure
  portal_mapping:     # How categories map to portal upload sections
  packaging_guidance: # How to compile evidence into uploads
  disclaimers:        # Legal safety disclaimers
  volatility:         # Change frequency and maintenance notes
```

### 1.2 Full Schema Specification

#### 1.2.1 Metadata Block

```yaml
metadata:
  id: "au_partner_820_801_v1"           # Unique template identifier
  country_code: "AU"                    # ISO 3166-1 alpha-2 (AU, UK, US, CA, NZ)
  visa_family: "Partner"                # Skilled | Student | Partner | Visitor | Work | Other
  visa_code_or_program: "820/801"       # Official visa subclass/code
  human_name: "Australia - Partner Visa (Onshore Subclass 820/801)"
  description: |
    Partner visa for applicants already in Australia in a genuine relationship with an Australian citizen/PR.
    Two-stage process: 820 (temporary) granted first, then 801 (permanent) after 2 years.

  version: "1.0.0"                      # Semantic versioning
  created: "2025-11-27"                 # Initial creation date
  last_verified_date: "2025-11-27"      # Last expert verification
  verified_by: "Jane Doe, MARA Reg #1234567"

  changelog: |
    v1.0.0 (2025-11-27):
    - Initial template based on official Department of Home Affairs guidance
    - Four pillars framework: Financial, Household, Social, Commitment

  official_sources:                     # Authoritative references
    - "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore"
    - "https://immi.homeaffairs.gov.au/form-listing/forms/888.pdf"

  volatility_level: "high"              # high | medium | low
  recommended_revalidation: "quarterly" # How often to re-check official guidance

  tags:                                 # Searchable tags
    - "partner"
    - "relationship"
    - "onshore"
    - "family-migration"
```

**Key Fields**:
- `id`: Unique, immutable across versions (e.g., `au_partner_820_801_v1` → `au_partner_820_801_v2`)
- `visa_code_or_program`: Maps to official government terminology
- `last_verified_date` + `verified_by`: Critical for premium service (shows template currency)
- `volatility_level`: Drives update frequency (high: quarterly, medium: semi-annual, low: annual)

---

#### 1.2.2 Evidence Categories Block

Categories define the hierarchical structure for organizing evidence. Uses the "4 Pillars" framework (AU partner visas) or equivalent structures for other visa types.

```yaml
evidence_categories:
  - id: "financial"                     # Unique category ID
    label: "Financial Aspects"          # User-facing name
    description: "Evidence of joint finances and financial interdependence"
    icon: "currency-dollar"             # Optional UI icon
    color: "#4CAF50"                    # Optional UI color

    priority: "required"                # required | strongly_recommended | optional | stream_specific

    typical_documents:                  # User guidance (NOT prescriptive)
      - "Joint bank account statements (12+ months)"
      - "Joint ownership of property (title deeds)"
      - "Joint liabilities (mortgage, loans, credit cards)"
      - "Beneficiary designations (superannuation, life insurance)"

    subcategories:                      # Nested categories (2-3 levels max)
      - id: "financial_joint_accounts"
        label: "Joint Bank Accounts"
        description: "Statements showing shared finances"
        typical_documents:
          - "Bank statements (last 12 months, both names)"
          - "Transaction history showing shared expenses"

        classification_hints:           # Keywords for auto-classification
          keywords:
            en: ["bank statement", "joint account", "commonwealth bank", "westpac", "anz", "nab"]

          file_patterns:
            - "*bank*statement*.pdf"
            - "*account*joint*.pdf"

          sender_domains:
            - "commbank.com.au"
            - "westpac.com.au"

      - id: "financial_joint_assets"
        label: "Joint Assets"
        description: "Property, vehicles, investments owned jointly"
        typical_documents:
          - "Property title deeds (both names)"
          - "Vehicle registration (joint ownership)"

    validation:                         # Optional completeness checks
      recommended_timeframe: "12_months"
      min_documents: 2
      warning_if_missing: "Joint finances are a key pillar for partner visas. Upload bank statements or joint asset documents."

  - id: "household"
    label: "Household and Domestic Aspects"
    description: "Evidence of living together and sharing household responsibilities"
    priority: "required"

    typical_documents:
      - "Joint lease or property title"
      - "Utility bills in both names (electricity, water, internet)"
      - "Correspondence to same address (mail, driver's license)"
      - "Photos of shared living space"

    subcategories:
      - id: "household_joint_lease"
        label: "Joint Lease or Property"
        description: "Proof of cohabitation at same address"
        typical_documents:
          - "Lease agreement (both names as tenants)"
          - "Property title (both names as owners)"
          - "Mortgage statement (joint mortgage)"

      - id: "household_utilities"
        label: "Utility Bills"
        description: "Bills in both names showing shared address"
        typical_documents:
          - "Electricity bills (12+ months)"
          - "Water bills"
          - "Internet/phone bills"

  - id: "social"
    label: "Social Aspects"
    description: "Evidence of public recognition as a couple and social integration"
    priority: "required"

    typical_documents:
      - "Photos together (chronological, 20-40 images spanning relationship)"
      - "Joint travel (flight bookings, hotel reservations, passport stamps)"
      - "Statutory declarations from friends/family (Form 888)"
      - "Joint memberships (gym, clubs)"
      - "Communication evidence (emails, messages - sample only)"

    subcategories:
      - id: "social_photos"
        label: "Photos Together"
        description: "Chronological photos showing relationship development"
        typical_documents:
          - "20-40 representative photos from start of relationship to present"
          - "Photos with family and friends"
          - "Special events (engagement, wedding, holidays)"

      - id: "social_form_888"
        label: "Statutory Declarations (Form 888)"
        description: "Written statements from friends/family confirming genuine relationship"
        typical_documents:
          - "Form 888 from sponsor's side (2-4 declarations)"
          - "Form 888 from applicant's side (2-4 declarations)"

        notes: |
          Form 888 must be completed by people who know both partners and can attest to the genuine nature of the relationship.
          Declarants should be Australian citizens or PRs.

  - id: "commitment"
    label: "Commitment to Each Other"
    description: "Evidence of ongoing commitment and future plans as a couple"
    priority: "required"

    typical_documents:
      - "Duration of relationship (longer = stronger)"
      - "Knowledge of each other's background (family, education, work)"
      - "Future plans (emails discussing marriage, children, relocation)"
      - "Public recognition (social media, engagement announcements)"

    subcategories:
      - id: "commitment_timeline"
        label: "Relationship Timeline"
        description: "Key milestones in relationship development"
        typical_documents:
          - "Timeline document (how you met, moved in, engaged, married)"
          - "Communication during early relationship (sample)"

      - id: "commitment_future_plans"
        label: "Future Plans"
        description: "Evidence of shared future as a couple"
        typical_documents:
          - "Emails/messages discussing future (marriage, children, purchasing home)"
          - "Joint financial planning (savings goals, mortgage applications)"

  - id: "identity"
    label: "Identity and Civil Documents"
    description: "Proof of identity and relationship status"
    priority: "required"

    typical_documents:
      - "Passports (biodata pages)"
      - "Birth certificates"
      - "Marriage certificate (if married)"
      - "Previous marriage termination documents (if applicable)"
      - "Change of name certificate (if applicable)"

    subcategories:
      - id: "identity_passports"
        label: "Passports"
        description: "Current passports for both sponsor and applicant"

      - id: "identity_relationship_proof"
        label: "Relationship Status"
        description: "Marriage certificate or de facto statutory declaration"
        typical_documents:
          - "Marriage certificate (if married)"
          - "De facto relationship statutory declaration (if not married)"
```

**Key Design Choices**:
- **Priority Levels**: `required` (must have), `strongly_recommended` (should have), `optional` (nice to have), `stream_specific` (depends on visa stream)
- **Subcategories**: 2-3 levels max to avoid over-complexity (e.g., Financial → Joint Accounts → Specific Bank)
- **Classification Hints**: Keywords, file patterns, sender domains to guide LLM auto-classification
- **Validation**: Optional checks for completeness (warn if missing key categories)

---

#### 1.2.3 Portal Mapping Block

Maps evidence categories to official portal upload sections. Critical for generating upload-ready files.

```yaml
portal_mapping:
  portal_name: "ImmiAccount"            # Official portal name
  portal_url: "https://online.immi.gov.au/lusc/login"

  upload_sections:                      # Portal upload structure
    - section_id: "relationship_evidence"
      section_label: "Evidence of Relationship"  # As shown in portal

      maps_to_categories:               # Which template categories go here
        - "financial"
        - "household"
        - "social"
        - "commitment"

      upload_constraints:
        max_file_size_mb: 60            # Per-file limit
        max_files: null                 # No strict limit (portal-dependent)
        accepted_formats: ["pdf", "jpg", "png", "jpeg"]

      recommended_packaging: "one_pdf_per_pillar"  # or "combined_all" or "per_document"

      notes: |
        Portal has a single "Evidence of Relationship" upload section.
        Recommended: Combine each pillar (Financial, Household, Social, Commitment) into separate PDFs.
        Each PDF should have a cover page with pillar name and table of contents.

    - section_id: "identity_documents"
      section_label: "Identity Documents"

      maps_to_categories:
        - "identity"

      upload_constraints:
        max_file_size_mb: 60
        max_files: 10                   # Estimated limit
        accepted_formats: ["pdf", "jpg", "png"]

      recommended_packaging: "per_document"  # Passport, birth cert, etc. as separate uploads

      notes: "Upload each identity document separately (passport, birth certificate, marriage certificate)."

  general_constraints:
    total_application_size_mb: null     # Unknown (portal-dependent)
    ocr_required: false                 # OCR not mandatory but recommended
    certified_copies_required: false    # Certified copies NOT required for online upload (originals for interview if requested)
```

**Key Fields**:
- `section_id`: Internal identifier for portal section
- `section_label`: Exact label as shown in portal (helps users recognize)
- `maps_to_categories`: Which template categories belong in this section
- `recommended_packaging`: `"one_pdf_per_category"` | `"combined_all"` | `"per_document"` | `"one_pdf_per_pillar"`

---

#### 1.2.4 Packaging Guidance Block

Defines how to compile evidence into final uploadable files.

```yaml
packaging_guidance:
  default_mode: "one_pdf_per_pillar"    # Default packaging strategy

  available_modes:                      # User can choose alternative
    - id: "one_pdf_per_pillar"
      label: "One PDF per Pillar (Recommended)"
      description: |
        Combines all evidence for each pillar (Financial, Household, Social, Commitment) into separate PDFs.
        Each PDF includes cover page, table of contents, and all documents for that pillar.

      outputs:
        - "1_Financial_Evidence.pdf"
        - "2_Household_Evidence.pdf"
        - "3_Social_Evidence.pdf"
        - "4_Commitment_Evidence.pdf"
        - "5_Identity_Documents/" (folder with individual files)
        - "Master_Index.pdf" (table of contents for all files)

      pros:
        - "Easy for case officers to navigate (one pillar per PDF)"
        - "Aligns with Department of Home Affairs 4 Pillars framework"
        - "Each PDF stays under 60MB limit"

      cons:
        - "Requires more uploads (4-5 files vs 1)"

    - id: "combined_all"
      label: "Single Combined PDF"
      description: "All evidence in one PDF with bookmarks for each pillar/category."

      outputs:
        - "Complete_Relationship_Evidence.pdf" (all pillars combined)
        - "Identity_Documents/" (folder with individual files)

      pros:
        - "Fewer uploads (1-2 files total)"
        - "Easier for applicant to manage"

      cons:
        - "Very large file (may exceed 60MB limit if many documents)"
        - "Harder to navigate (case officers must scroll through entire PDF)"

    - id: "per_document"
      label: "Individual Documents"
      description: "Upload each document separately with descriptive filenames."

      outputs:
        - "Financial_BankStatement_2024-01.pdf"
        - "Financial_BankStatement_2024-02.pdf"
        - "Household_Lease_2023-2025.pdf"
        - "Social_Photos_Chronological.pdf"
        - "... (50-100+ individual files)"

      pros:
        - "Maximum flexibility (can update single documents)"
        - "Each file small (<10MB)"

      cons:
        - "Time-consuming to upload (50-100 files)"
        - "Harder for case officers to review (many individual files)"

  pdf_generation:
    cover_page: true                    # Include cover page per PDF
    table_of_contents: true             # Include TOC per PDF
    bookmarks: true                     # PDF bookmarks for navigation
    page_numbers: true                  # Bottom-right corner
    separator_pages: false              # No separator pages between documents (too verbose)

    cover_page_template: |
      [Visa Type]: Australia - Partner Visa (Subclass 820/801)
      [Pillar/Section]: Financial Aspects
      [Applicant]: [User Input - Name]
      [Date Compiled]: [Auto - YYYY-MM-DD]

      This pack was compiled using FileOrganizer.
      Always verify against official Department of Home Affairs guidance.

    chronological_ordering: true        # Within each category, sort by date (oldest first for relationship evidence)

  index_generation:
    format: "pdf"                       # or "markdown" or "xlsx"
    include_in_index:
      - "Category"
      - "Document Name"
      - "Original Filename"
      - "Page Range" (for combined PDFs)
      - "File Size"

    example_index_entry: |
      Category: Financial - Joint Bank Accounts
      Document Name: Commonwealth Bank Joint Account Statement
      Original Filename: CBA_Statement_2024-01.pdf
      Page Range: 5-12
      File Size: 2.3 MB
```

**Key Design Choices**:
- **Default Mode**: `one_pdf_per_pillar` balances case officer navigation with upload effort
- **Cover Pages**: Include visa type, pillar, applicant name, date compiled, disclaimer
- **TOC**: Essential for PDFs >20 pages (each pillar typically 20-100 pages)
- **Chronological Ordering**: Relationship evidence (photos, bills, statements) ordered oldest→newest to show development

---

#### 1.2.5 Disclaimers Block

```yaml
disclaimers:
  primary: |
    This immigration pack is an organizational tool based on public guidance from the Department of Home Affairs.
    It is NOT immigration advice and does NOT assess eligibility or likelihood of approval.
    Immigration requirements and forms can change without notice.
    Always verify all categories, documents, and requirements against the latest official guidance before submission.
    Consult a registered migration agent (MARA) for case-specific advice.

  additional:
    - "This pack was last verified on [LAST_VERIFIED_DATE] by [VERIFIED_BY]."
    - "FileOrganizer does not verify document authenticity or accuracy."
    - "You are responsible for ensuring all evidence is genuine and accurately represents your relationship."
    - "The Department of Home Affairs may request additional evidence not listed in this template."

  display_contexts:
    - "template_selection"              # Show before user selects template
    - "pack_header"                     # Show at top of pack instance
    - "export_cover_page"               # Include in PDF cover pages
    - "export_master_index"             # Include in master index
```

---

#### 1.2.6 Volatility Block

```yaml
volatility:
  level: "high"                         # high | medium | low

  change_frequency:
    fees: "annual"                      # Application fees change yearly (Jul 1)
    forms: "2-3_years"                  # Form 888 structure stable
    requirements: "1-2_years"           # 4 Pillars framework stable, but evidence examples may change
    portal: "1-2_years"                 # ImmiAccount structure relatively stable

  recent_changes:                       # Track major changes (for changelog)
    - date: "2024-07-01"
      change: "Application fee increased from $9,095 to $9,365 (820/801 combined)"
      impact: "Update fee reference in pack description"

    - date: "2023-11-15"
      change: "Form 888 updated to include more specific relationship questions"
      impact: "Update Form 888 guidance in Social pillar"

  monitoring_strategy:
    official_sources_to_monitor:
      - "https://immi.homeaffairs.gov.au/visas/getting-a-visa/visa-listing/partner-onshore"
      - "https://immi.homeaffairs.gov.au/form-listing/forms/888.pdf"

    monitoring_frequency: "monthly"     # Check official sources monthly
    expert_review_frequency: "quarterly" # MARA review every 3 months

    emergency_update_triggers:          # Immediate update required if:
      - "New visa subclass introduced"
      - "Major policy change (e.g., cohabitation requirement changed)"
      - "Portal structure redesigned"

  premium_service_notes: |
    This template is part of FileOrganizer's Premium Immigration Pack service.
    Premium subscribers receive quarterly expert-verified updates.
    Free tier users see this template with "last verified" warnings after 6 months.
```

---

### 1.3 Complete Example: AU Partner Visa 820/801

See **Appendix A** for full YAML template: `au_partner_820_801_v1.yaml`

---

## Part 2: Country-Specific Visa Templates

### 2.1 Australia (AU)

#### 2.1.1 Priority Visa Types for Phase 1

| Visa Code | Visa Name | Family | Rationale | Phase |
|-----------|-----------|--------|-----------|-------|
| **820/801** | Partner Visa (Onshore) | Partner | High individual demand, complex evidence (4 pillars), $9,365 fee | **Phase 1** |
| **500** | Student Visa | Student | Large market (international students), moderate evidence | **Phase 1** |
| **189/190/491** | Skilled Independent/Nominated/Regional | Skilled | High individual demand, points-tested, complex documentation | **Phase 2** |
| **482** | Temporary Skill Shortage (TSS) | Work | Employer-sponsored, but individuals often gather evidence | **Phase 2** |
| **600** | Visitor Visa | Visitor | Lower complexity, good for testing generic template | **Phase 2** |

**Phase 1 Focus**: Partner (820/801) and Student (500) - highest individual demand and most complex evidence requirements.

---

#### 2.1.2 Template: AU Partner Visa 820/801

**Evidence Categories** (4 Pillars Framework):

1. **Financial Aspects**:
   - Joint bank accounts (12+ months statements)
   - Joint assets (property, vehicles)
   - Joint liabilities (mortgage, loans, credit cards)
   - Beneficiary designations (superannuation, life insurance)

2. **Household and Domestic Aspects**:
   - Joint lease or property title
   - Utility bills (both names, 12+ months)
   - Correspondence to same address
   - Photos of shared living space

3. **Social Aspects**:
   - Photos together (20-40, chronological)
   - Joint travel (flights, hotels, passport stamps)
   - Form 888 declarations (2-4 from each side)
   - Joint memberships, events, social recognition

4. **Commitment to Each Other**:
   - Relationship duration
   - Knowledge of each other (family, background)
   - Future plans (marriage, children, property)
   - Public recognition (social media, announcements)

5. **Identity Documents**:
   - Passports (biodata pages)
   - Birth certificates
   - Marriage certificate (if married)
   - Previous marriage termination (if applicable)

**Portal Mapping** (ImmiAccount):
- **Section**: "Evidence of Relationship" (single upload section for all 4 pillars)
- **Recommended Packaging**: One PDF per pillar (4 PDFs total)
- **Constraints**: Max 60MB per file, PDF/JPG/PNG accepted

**Volatility**: **High**
- Fees change annually (July 1)
- Form 888 updated every 2-3 years
- 4 Pillars framework stable (unchanged since 2016)

**Template Status**: ✅ Ready for Phase 1 (fully specified in Appendix A)

---

#### 2.1.3 Template: AU Student Visa 500

**Evidence Categories**:

1. **Enrolment and Education**:
   - Confirmation of Enrolment (CoE) from institution
   - Offer letter from Australian education provider
   - Previous academic transcripts and qualifications

2. **Financial Capacity**:
   - Evidence of funds (bank statements, scholarships)
   - Sponsor financial documents (if sponsored by parents)
   - GTE (Genuine Temporary Entrant) statement

3. **English Language Ability**:
   - IELTS/PTE/TOEFL test results
   - OR evidence of English-medium education

4. **Health and Character**:
   - Health examination results (eMedical)
   - Police certificates (if applicable)

5. **Overseas Student Health Cover (OSHC)**:
   - OSHC policy documents (duration matching course)

6. **Identity Documents**:
   - Passport (biodata page)
   - Birth certificate
   - Previous visa labels (if applicable)

**Portal Mapping** (ImmiAccount):
- **Multiple Sections**: Education, Financial, English, Health, OSHC, Identity
- **Recommended Packaging**: Per-section PDFs (6 PDFs total)
- **Constraints**: Max 60MB per file

**Volatility**: **Medium**
- Fees change annually
- Financial capacity thresholds change (AUD 29,710 for 2024-25)
- OSHC providers change
- GTE statement requirements evolve

**Template Status**: ⚠️ Phase 1 (simplified version), Full specification Phase 2

---

### 2.2 United Kingdom (UK)

#### 2.2.1 Priority Visa Types for Phase 1

| Visa Code | Visa Name | Family | Rationale | Phase |
|-----------|-----------|--------|-----------|-------|
| **Spouse/Partner** | Spouse/Partner Visa | Partner | High individual demand, £29K income requirement, complex evidence | **Phase 1** |
| **Skilled Worker** | Skilled Worker Visa | Work | Post-Brexit main work route, CoS-based, moderate evidence | **Phase 2** |
| **Student** | Student Visa | Student | Large market (international students), CAS-based | **Phase 2** |
| **Graduate** | Graduate Visa | Work | Post-study work route for graduates | **Phase 2** |

**Phase 1 Focus**: Spouse/Partner visa - highest complexity and individual preparation.

---

#### 2.2.2 Template: UK Spouse/Partner Visa

**Evidence Categories**:

1. **Financial Requirement**:
   - **Income** (sponsor must earn £29,000/year as of Apr 2024):
     - Last 6 months payslips
     - Employment letter (salary, duration, permanence)
     - Bank statements showing salary deposits
   - **OR Savings** (£88,500 held for 6+ months):
     - Bank statements (6 months, showing balance above threshold)
   - **OR Combination** (£16K savings + reduced income requirement)

2. **Relationship Evidence**:
   - **Married**:
     - Marriage certificate (original + certified translation if not in English)
     - Wedding photos
   - **Unmarried Partners** (2+ years living together):
     - Joint lease/mortgage (2+ years)
     - Utility bills (both names, spread across 2 years)
     - Correspondence to same address
   - **Genuine Relationship**:
     - Photos together (across duration)
     - Communication (emails, messages, call logs - especially if long-distance)
     - Travel evidence (visits, joint trips)
     - Statutory declarations from friends/family (optional but helpful)

3. **Accommodation**:
   - Evidence of adequate accommodation in UK (not overcrowded)
   - Property ownership, mortgage statement, OR tenancy agreement
   - Letter from property owner confirming permission for applicant

4. **English Language**:
   - A1 level on CEFR (IELTS Life Skills A1 or equivalent)
   - OR degree taught in English
   - OR national of majority-English speaking country

5. **Identity and Civil Status**:
   - Valid passport
   - Birth certificate
   - Previous marriage/divorce certificates (if applicable)

**Portal Mapping** (UKVI Online Application):
- **Multiple Sections**: Financial, Relationship, Accommodation, English, Identity
- **Recommended Packaging**: One PDF per section (5 PDFs total)
- **Constraints**: 2-6MB typical per file (not strict limit)

**Volatility**: **High**
- Income threshold increased from £18,600 to £29,000 (Apr 2024)
- Further increases planned (£38,700 by early 2025)
- Brexit-related changes ongoing

**Template Status**: ✅ Ready for Phase 1

---

### 2.3 United States (US)

#### 2.3.1 Priority Visa Types for Phase 1

| Visa Code | Visa Name | Family | Rationale | Phase |
|-----------|-----------|--------|-----------|-------|
| **I-130 (IR/CR)** | Marriage-Based Green Card | Family | High individual demand, bona fide marriage evidence | **Phase 1** |
| **EB-2/EB-3** | Employment-Based Green Cards | Employment | High-level overview only (often lawyer-managed) | **Phase 2** |
| **F-1** | Student Visa | Student | Large market, but often university-managed | **Phase 2** |

**Phase 1 Focus**: I-130 Marriage-Based Green Card - highest individual DIY demand.

---

#### 2.3.2 Template: US Marriage-Based Green Card (I-130)

**Evidence Categories**:

1. **Proof of Marriage**:
   - Marriage certificate (government-issued, certified translation if not English)
   - Previous marriage termination (divorce decrees, death certificates)

2. **Bona Fide Marriage Evidence**:
   - **Strong Evidence**:
     - Joint ownership of property (deed, mortgage)
     - Joint bank accounts (12+ months statements)
     - Joint credit cards, loans
     - Birth certificates of children (if applicable)
     - Health/life insurance (spouse as beneficiary)
   - **Medium Evidence**:
     - Joint lease or cohabitation evidence
     - Utility bills (both names)
     - Joint travel (hotel bookings, flights)
     - Photos together (chronological, with family/friends)
   - **Weak Evidence** (supplement only):
     - Cards/letters exchanged
     - Affidavits from friends/family
     - Social media screenshots

3. **Financial Sponsorship (I-864)**:
   - **Income Requirement**: 125% of federal poverty guideline (e.g., $24,650 for 2-person household in 2024)
   - **Evidence**:
     - Last 3 years tax returns (IRS transcripts preferred)
     - Recent pay stubs
     - Employment verification letter
     - OR assets (value ≥5× shortfall)

4. **Identity and Civil Documents**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (for I-485 applicants)
   - Medical examination (Form I-693)

**Portal Mapping** (USCIS Online for I-130, or Physical Mail):
- **Physical Submission** (Still common):
   - Organized in binder with tabs per category
   - Tab 1: Forms, Tab 2: Marriage Certificate, Tab 3: Joint Financial, Tab 4: Cohabitation, Tab 5: Photos, Tab 6: Affidavits
- **Online I-130** (New, as of late 2023):
   - Individual PDFs per document type
   - Clear labeling (e.g., "Joint_Bank_Statement_2024-01.pdf")

**Volatility**: **Medium**
- Poverty guideline updated annually (Jan/Feb)
- I-130/I-485 forms updated every 2-3 years
- Processing times and procedures change
- "Public charge" rules have changed significantly (2019-2024)

**Template Status**: ✅ Ready for Phase 1

---

### 2.4 Canada (CA)

#### 2.4.1 Priority Visa Types for Phase 1

| Program | Visa Name | Family | Rationale | Phase |
|---------|-----------|--------|-----------|-------|
| **Spousal Sponsorship** | Spouse/Common-Law Sponsorship | Family | High individual demand, complex evidence | **Phase 1** |
| **Express Entry (FSW)** | Federal Skilled Worker | Skilled | Points-based, popular, moderate documentation | **Phase 2** |
| **Study Permit** | Study Permit | Student | Large market, moderate evidence | **Phase 2** |

**Phase 1 Focus**: Spousal Sponsorship - high complexity, digital-only (2025).

---

#### 2.4.2 Template: CA Spousal Sponsorship

**Evidence Categories**:

1. **Proof of Relationship**:
   - **Married**:
     - Marriage certificate (original or certified copy + certified translation)
     - Wedding photos (representative sample, 10-20)
   - **Common-Law Partners** (12+ months living together):
     - Statutory Declaration of Common-Law Union (IMM 5409)
     - Joint lease/mortgage (12+ months)
     - Utility bills (12+ months, both names)

2. **Relationship Development**:
   - Photos together (chronological, start to present)
   - Travel evidence (joint trips, visits if long-distance)
   - Communication (emails, messages, call logs - sample)
   - Important events (engagement, family gatherings)

3. **Cohabitation Evidence** (if living together):
   - Joint bank accounts (12+ months statements)
   - Joint bills (utilities, phone, internet)
   - Joint lease or property ownership
   - Correspondence to same address (driver's license, tax documents)

4. **Financial Support**:
   - No minimum income for spousal sponsorship (EXCEPT Quebec or if on social assistance)
   - Option C Printout (CRA Notice of Assessment)
   - Pay stubs (recent)
   - Proof of employment

5. **Identity and Civil Status**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (from countries lived 6+ months since age 18)
   - Previous marriage termination (if applicable)

**Portal Mapping** (IRCC Digital Submission, Mandatory 2025):
- **Digital-Only**: No paper applications
- **File Requirements**: Max 4MB per file, PDF/JPEG/PNG
- **Recommended Packaging**: One PDF per category (6 PDFs total)
- **File Naming**: `Document_Type_YYYY-MM-DD.pdf`

**Volatility**: **High**
- Digital-only submission (major change in 2025)
- Forms updated regularly (IMM 1344, IMM 5532)
- Processing times fluctuate significantly

**Template Status**: ✅ Ready for Phase 1

---

### 2.5 New Zealand (NZ)

#### 2.5.1 Priority Visa Types for Phase 1

| Visa Type | Visa Name | Family | Rationale | Phase |
|-----------|-----------|--------|-----------|-------|
| **Partnership** | Partnership-Based Residence Visa | Partner | High individual demand, 12-month cohabitation | **Phase 1** |
| **Skilled Migrant** | Skilled Migrant Category | Skilled | Points-based, popular, moderate documentation | **Phase 2** |
| **Work to Residence** | Accredited Employer Work Visa | Work | Common pathway, employer-supported | **Phase 2** |

**Phase 1 Focus**: Partnership-Based Residence Visa.

---

#### 2.5.2 Template: NZ Partnership-Based Residence Visa

**Evidence Categories**:

1. **Proof of Partnership**:
   - **Married/Civil Union**:
     - Marriage certificate (original or certified copy + certified translation)
     - Wedding photos
   - **De Facto Partners** (12+ months living together):
     - Statutory declaration from both partners
     - Joint evidence (see below)

2. **Living Together Evidence** (12+ months required):
   - Joint lease or property ownership (12+ months)
   - Utility bills (both names, 12+ months, spread across period)
   - Correspondence to same address (bank statements, official mail)
   - Joint bank accounts (12+ months statements)

3. **Genuine and Stable Relationship**:
   - Photos together (chronological, start to present, 20-40 images)
   - Travel evidence (joint trips, passport stamps)
   - Communication (emails, messages, call logs - sample, especially if periods apart)
   - Statutory declarations from friends/family (2-4) confirming genuine relationship

4. **Financial Interdependence**:
   - Joint bank accounts
   - Joint assets (property, vehicles)
   - Joint liabilities (mortgage, loans)
   - Shared expenses (household bills)
   - Beneficiary designations (life insurance, KiwiSaver)

5. **Social Recognition**:
   - Joint invitations to events
   - Joint memberships (gym, clubs)
   - Social media showing relationship status
   - Family acceptance (photos with each other's families)

6. **Identity and Civil Documents**:
   - Passports (biodata pages)
   - Birth certificates
   - Police certificates (from countries lived 12+ months in last 10 years)
   - Medical certificates (chest X-ray, general medical)
   - Previous marriage termination (if applicable)

**Portal Mapping** (INZ Online):
- **Online or Paper**: Both options available
- **File Requirements**: Max 10MB per file, PDF/JPEG/PNG
- **Recommended Packaging**: One PDF per category (6 PDFs total)

**Volatility**: **Medium**
- Partnership requirements relatively stable
- Application fees change (increased to $3,720 in Oct 2024)
- Forms updated every 2-3 years

**Template Status**: ✅ Ready for Phase 1

---

## Part 3: Packaging and Portal Integration

### 3.1 Cross-Country Packaging Patterns

| Country | Portal Name | Primary Upload Structure | File Limits | Recommended Packaging |
|---------|-------------|-------------------------|-------------|----------------------|
| **AU** | ImmiAccount | Single "Relationship Evidence" section | 60MB per file | One PDF per pillar (4 PDFs) |
| **UK** | UKVI Online | Multiple sections (Financial, Relationship, etc.) | 2-6MB typical | One PDF per section (5 PDFs) |
| **US** | USCIS Online (new) or Physical Mail | Physical: Binder with tabs; Online: Per-document uploads | Physical: No limit; Online: Varies | Physical: Tabbed binder; Online: Individual PDFs |
| **CA** | IRCC Digital | Digital-only, per-document uploads | 4MB per file | One PDF per category (6 PDFs) |
| **NZ** | INZ Online | Multiple sections | 10MB per file | One PDF per category (6 PDFs) |

**Common Patterns**:
- ✅ **Per-Category PDFs** (Most Common): One PDF per major evidence category (Financial, Relationship, Identity, etc.)
- ✅ **Combined Application PDF** (Less Common): Single PDF with all evidence, bookmarked by category
- ✅ **Individual Document Uploads** (Rare): Each document uploaded separately (US online, CA digital)

**Best Practice** (FileOrganizer Default):
- Generate **one PDF per major category** (5-7 PDFs total)
- Each PDF includes:
  - Cover page (visa type, category name, applicant name, date)
  - Table of contents (document names, page ranges)
  - Bookmarks for navigation
  - Chronological ordering within category (oldest→newest for relationship evidence)
- Also generate **Master Index PDF** (list of all documents across all PDFs)

---

### 3.2 PDF Generation Specifications

#### 3.2.1 Cover Page Template

```
┌────────────────────────────────────────┐
│                                        │
│  IMMIGRATION EVIDENCE PACK             │
│                                        │
│  Country: [Australia / UK / US / etc.] │
│  Visa Type: [Partner Visa 820/801]     │
│  Evidence Category: [Financial Aspects]│
│                                        │
│  Applicant: [User Input - Name]        │
│  Date Compiled: [2025-11-27]           │
│                                        │
│  ──────────────────────────────────    │
│                                        │
│  ⚠️ IMPORTANT DISCLAIMER               │
│                                        │
│  This pack was compiled using          │
│  FileOrganizer, an organizational tool.│
│  It is NOT immigration advice.         │
│                                        │
│  Always verify all requirements against│
│  official government guidance before   │
│  submission. Consult a registered      │
│  migration agent for case-specific     │
│  advice.                               │
│                                        │
│  Template Version: 1.0.0               │
│  Last Verified: 2025-11-27             │
│  Verified By: [Expert Name, Credential]│
│                                        │
└────────────────────────────────────────┘
```

#### 3.2.2 Table of Contents Format

```
TABLE OF CONTENTS

Document 1: Joint Bank Account Statement (Commonwealth Bank)
  Original File: CBA_Statement_2024-01.pdf
  Pages: 3-8 (6 pages)

Document 2: Joint Bank Account Statement (Commonwealth Bank)
  Original File: CBA_Statement_2024-02.pdf
  Pages: 9-14 (6 pages)

Document 3: Property Title Deed (Joint Ownership)
  Original File: Property_Title_123_Main_St.pdf
  Pages: 15-18 (4 pages)

...

Total Documents: 12
Total Pages: 85
```

#### 3.2.3 Master Index Format

```
MASTER INDEX - COMPLETE EVIDENCE PACK

Visa Type: Australia - Partner Visa (Subclass 820/801)
Applicant: [Name]
Date Compiled: 2025-11-27

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PDF 1: Financial_Evidence.pdf (85 pages, 12.3 MB)
  - 12 documents covering joint accounts, assets, liabilities
  - Coverage: Jan 2023 - Nov 2025 (35 months)

PDF 2: Household_Evidence.pdf (42 pages, 5.8 MB)
  - 8 documents covering joint lease, utility bills, correspondence
  - Coverage: Jan 2023 - Nov 2025 (35 months)

PDF 3: Social_Evidence.pdf (65 pages, 18.2 MB)
  - 35 photos (chronological), 4 Form 888 declarations, travel evidence
  - Coverage: Jan 2020 (relationship start) - Nov 2025

PDF 4: Commitment_Evidence.pdf (28 pages, 3.1 MB)
  - Relationship timeline, future plans, communication sample
  - Coverage: Jan 2020 - Nov 2025

PDF 5: Identity_Documents/ (folder, 6 files, 4.2 MB)
  - Passports, birth certificates, marriage certificate

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

TOTAL: 5 PDFs, 220 pages, 43.6 MB
Estimated Upload Time: 10-15 minutes (at 10 Mbps)

⚠️ DISCLAIMER: This pack is an organizational tool, NOT immigration advice.
Verify all documents and requirements against official guidance.
```

---

## Part 4: Volatility and Maintenance Strategy

### 4.1 Volatility Assessment by Country

| Country | Overall Volatility | Key Change Drivers | Update Frequency | Expert Review Cost (Estimated) |
|---------|-------------------|-------------------|------------------|-------------------------------|
| **AU** | **High** | Annual fee increases (Jul 1), Form 888 updates, policy tweaks | Quarterly | $300-500/review (MARA agent) |
| **UK** | **High** | Income threshold changes (2024: £18.6K→£29K→£38.7K planned), Brexit adjustments | Quarterly | £250-400/review (OISC adviser) |
| **US** | **Medium** | Poverty guideline updates (annual), form revisions (2-3 years), policy shifts | Semi-annual | $400-600/review (immigration attorney) |
| **CA** | **High** | Digital-only transition (2025), form updates, processing changes | Quarterly | CAD $350-550/review (RCIC) |
| **NZ** | **Medium** | Fee increases (annual), partnership requirements stable | Semi-annual | NZD $300-500/review (IAA adviser) |

**Key Insight**: AU, UK, CA require **quarterly** updates due to high volatility. US, NZ can be **semi-annual**.

---

### 4.2 Template Update Workflow

#### 4.2.1 Quarterly Review Cycle (Example: AU Partner Visa)

**Week 1-2: Monitoring & Research**
1. Research team monitors:
   - homeaffairs.gov.au/visas (check for updates)
   - Form 888 PDF (check for new version)
   - ImmiAccount portal (check for structure changes)
   - Community reports (users flag changes via in-app feedback)

2. If changes detected:
   - Draft template changelog
   - Update YAML fields (fees, form references, category descriptions)

**Week 3: Expert Review**
1. Send draft to MARA-registered migration agent
2. Expert reviews:
   - Are fees/thresholds correct?
   - Are evidence categories complete and current?
   - Is disclaimer adequate?
3. Expert signs off: "Reviewed by [Name], MARA #[ID], [Date]"

**Week 4: Publication & Notification**
1. Increment version (v1.0.0 → v1.1.0 if minor changes, v2.0.0 if breaking)
2. Sign template YAML with FileOrganizer private key
3. Publish to template update server
4. Notify Premium users:
   - Email: "AU Partner Visa template updated (v1.1.0). [View Changelog]"
   - In-app: "Update available for AU Partner Visa 820/801. [Review Changes]"

**Emergency Updates** (Out-of-Cycle):
- Major policy change (e.g., cohabitation requirement changed, program abolished) → 7-day turnaround
- Expert fast-tracked review → Published ASAP with "Emergency Update" flag

---

#### 4.2.2 Expert Network Structure

**Recruitment Strategy**:
- **AU**: Partner with 2-3 MARA-registered agents (primary + backups)
- **UK**: Partner with 2-3 OISC-registered advisers (Level 1+)
- **US**: Partner with 2-3 immigration attorneys (state bar members)
- **CA**: Partner with 2-3 RCICs (Regulated Canadian Immigration Consultants)
- **NZ**: Partner with 2-3 IAA-licensed advisers

**Compensation Models**:
- **Option A: Per-Review Fee**: $300-600 per quarterly review (fixed fee)
- **Option B: Revenue Share**: 15-20% of Premium subscription revenue for that country
- **Option C: Hybrid**: Base fee ($150) + revenue share (10%)

**Expert Responsibilities**:
- Review draft template updates for accuracy
- Sign off on template with credentials (name, registration number, date)
- Respond to escalated user questions (Premium tier only, optional)

**Expert Verification Example** (Metadata):
```yaml
verified_by: "Jane Doe, MARA Reg #1234567"
verification_date: "2025-11-27"
verification_notes: |
  Reviewed template against current Department of Home Affairs guidance (Nov 2025).
  Fees, forms, and evidence categories are accurate as of verification date.
  4 Pillars framework unchanged. Form 888 version current.
```

---

### 4.3 Premium Service Implementation

#### 4.3.1 Free Tier vs Premium Tier

**Free Tier** (Built-in, No Updates):
- Static templates bundled with app install
- **"Last Verified" date** shown prominently (e.g., "Last verified: 2025-11-27")
- User warned after 6 months: "⚠️ This template is 6 months old. Immigration requirements may have changed. [Upgrade to Premium] or verify manually."
- No automatic updates

**Premium Tier** (Paid Subscription):
- **Quarterly updates** (minimum 4x/year)
- **Expert-verified** (MARA, OISC, RCIC, IAA, attorneys)
- **Automatic template sync** (user opt-in):
  - App checks for updates on launch
  - User notified: "New template available for AU Partner Visa 820/801 (v1.3). [Review Changes]"
  - User reviews changelog → Clicks "Update" → Template synced
- **Change notifications** (email + in-app)
- **Version history** (rollback to previous versions if needed)

**Pricing** (Placeholder, TBD):
| Tier | Price | Coverage | Update Frequency |
|------|-------|----------|------------------|
| Free | $0 | Static templates (bundled) | None (manual verification) |
| Single Country | $9.99/month or $79/year | 1 country of choice | Quarterly + emergency |
| All Countries | $19.99/month or $149/year | All 5 countries (AU, UK, US, CA, NZ) | Quarterly + emergency |
| One-Time | $29 per pack | Current template only | None (no future updates) |

---

#### 4.3.2 Template Update Architecture

**Update Server** (FileOrganizer Backend):
- `GET /templates/immigration/catalog.json` → List all templates with versions, last verified dates
- `GET /templates/immigration/{template_id}/latest` → Get latest version metadata
- `GET /templates/immigration/{template_id}/{version}.yaml` → Download template YAML (signed)
- `GET /templates/immigration/{template_id}/changelog.md` → View version history

**Client-Side Update Flow**:
1. On app launch (if online), check catalog for updates
2. Compare local template versions with remote
3. If newer version available:
   - Free users: Show "Update available (Premium)" badge
   - Premium users: Show "Update available (v1.3.0). [Review Changes]" notification
4. User reviews changelog → Clicks "Update" → Template downloaded, signature verified, old version backed up
5. Pack instances using old template show warning: "Template outdated. [Upgrade Pack]"

**Pack Instance Version Locking**:
- Each pack instance frozen at creation template version (stability during workflow)
- User can optionally "Upgrade Pack to v1.3.0" (re-runs classification if categories changed)

---

## Part 5: Implementation Handover

### CRITICAL: v1.0 vs Phase 1 Clarification

**Per GPT Strategic Review (2025-11-27)**:

```
┌──────────────────────────────────────────────────────────┐
│ v1.0 SCOPE (Weeks 1-6)                                  │
│ • Generic immigration pack ONLY                         │
│ • Categories: Identity, Financial, Relationship,        │
│   Work/Study, Health, Character                         │
│ • NO country-specific templates                         │
│ • NO visa-specific guidance                             │
│ • NO Immigration Premium Service                        │
│ • Static templates (no updates)                         │
│ • Target: General users organizing relationship docs    │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ PHASE 2 SCOPE (Weeks 7-13)                              │
│ • AU Partner Visa 820/801 ✅                             │
│ • UK Spouse Visa ✅                                      │
│ • Expert verification (MARA, OISC agents)               │
│ • Country-specific templates with full guidance         │
│ • Defer: US I-130, CA Spousal, NZ (Phase 2+)           │
└──────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────┐
│ PHASE 2.5 SCOPE (Weeks 14-20)                           │
│ • Immigration Premium Service infrastructure            │
│ • Template update server (REST API, JWT auth)           │
│ • Subscription backend (Stripe/Paddle)                  │
│ • Quarterly expert-verified template updates            │
│ • Pricing: $9.99/mo (single), $19.99/mo (all),         │
│   $39 one-time (12-month)                               │
└──────────────────────────────────────────────────────────┘
```

**Document Note**: This specification describes the **roadmap** for immigration packs (Phase 1-2.5). Sections 5.1-5.2 below refer to "Phase 1" which is now **Phase 2** in the updated v1.0 scope discipline.

---

### 5.1 v1.0 Template (Generic Only)

**Delivered in v1.0** (Weeks 1-6):

1. **Generic Immigration Pack** ✅
   - **Purpose**: Fallback for all unsupported visas, general relationship evidence organization
   - **Categories**:
     - Identity (passports, birth certificates, national IDs)
     - Financial (bank statements, tax returns, employment docs)
     - Relationship (photos, joint assets, travel together, statements)
     - Work/Study History (contracts, enrollment, qualifications)
     - Health (medical records, insurance)
     - Character (police certificates, references)
   - **Packaging**: Simple per-category PDFs, basic index
   - **Disclaimers**: "Generic template. Verify against official guidance for your specific visa."
   - **NO**: Visa-specific guidance, portal mappings, financial requirement calculators
   - **Estimated Effort**: 1-2 weeks (included in core pack system Milestone 2)

**Success Criteria (v1.0)**:
- 50-100 users create immigration packs (generic)
- 5-10 users request country-specific templates ("I need AU Partner Visa")
- Qualitative feedback: "Generic pack is useful but I need visa-specific guidance"

---

### 5.2 Phase 2 Priority Templates (Country-Specific)

**Delivered in Phase 2** (Weeks 7-13), **AFTER** v1.0 success validation:

1. **AU Partner Visa 820/801** ✅ **[PHASE 2]**
   - **Rationale**: Highest complexity, $9,365 fee, strong DIY market
   - **Status**: Fully specified (Appendix A)
   - **Estimated Effort**: 3-4 weeks (template + expert verification + test)
   - **Expert Verification**: MARA-registered agent review

2. **UK Spouse/Partner Visa** ✅ **[PHASE 2]**
   - **Rationale**: High complexity, £29K income requirement, large market
   - **Status**: Fully specified (Section 2.2.2)
   - **Estimated Effort**: 2-3 weeks
   - **Expert Verification**: OISC advisor review

3. ❌ **US Marriage-Based Green Card (I-130)** **[PHASE 2+ - DEFERRED]**
   - **Rationale**: Large market but lower DIY urgency (lawyers common)
   - **Status**: Fully specified (Section 2.3.2) but deferred to Phase 2+
   - **Estimated Effort**: 2-3 weeks (when prioritized)

4. ❌ **CA Spousal Sponsorship** **[PHASE 2+ - DEFERRED]**
   - **Rationale**: Smaller market than AU/UK
   - **Status**: Fully specified (Section 2.4.2) but deferred to Phase 2+

5. ❌ **NZ Partnership Visa** **[PHASE 2+ - DEFERRED]**
   - **Rationale**: Lower urgency
   - **Status**: Partially specified (Section 2.5.2) but deferred to Phase 2+

**Phase 2 MVP Scope**: Deliver **AU 820/801 + UK Spouse** (2 templates). Defer US, CA, NZ to Phase 2+.

---

### 5.3 Phase 2.5 Immigration Premium Service

**Delivered in Phase 2.5** (Weeks 14-20), **AFTER** Phase 2 country templates validated:

#### 5.3.1 Service Tiers

**Free Tier** (Static Templates):
- Access to all published templates (AU, UK, etc.)
- Templates frozen at download version (e.g., v1.0.0)
- No automatic updates
- Age warning after 6 months: "⚠️ Template 6+ months old. Requirements may have changed. [Upgrade to Premium]"

**Premium Tier - Single Country** ($9.99/month):
- Quarterly expert-verified template updates for ONE country (user selects: AU, UK, US, CA, or NZ)
- Automatic update notifications: "AU Partner Visa template updated to v1.2.0 (Form 888 changes)"
- Changelog diff view (what changed since your last version)
- Expert Q&A access (1 question/quarter, 48-hour response from MARA/OISC agent)
- 12-month minimum commitment

**Premium Tier - All Countries** ($19.99/month):
- Quarterly updates for ALL five countries (AU, UK, US, CA, NZ)
- All Single Country benefits + priority support
- 12-month minimum commitment

**One-Time Purchase** ($39):
- 12 months of updates for ONE country
- No auto-renewal
- After 12 months, templates frozen at last-downloaded version

#### 5.3.2 Update Workflow

**Quarterly Review Cycle** (High-Volatility Countries: AU, UK, CA):
- Week 1: Expert reviews official guidance changes (MARA/OISC agents)
- Week 2: Template updates drafted, changelog documented
- Week 3: Internal QA testing (sample data, PDF exports)
- Week 4: Template published, users notified via email + in-app

**Semi-Annual Review Cycle** (Medium-Volatility Countries: US, NZ):
- Similar workflow but every 6 months instead of quarterly

**Emergency Updates** (Policy Changes, Portal Redesigns):
- 7-day turnaround for critical updates
- Email blast to all affected users: "URGENT: AU ImmiAccount portal redesigned. Update template now."

#### 5.3.3 Technical Infrastructure

**Template Update Server**:
- REST API: `GET /api/v1/templates/immigration/:country/:visa`
- Authentication: JWT (user subscription tier validated)
- Response: Signed YAML (Ed25519 signature, prevents tampering)
- Versioning: Semantic versioning (v1.2.3 = major.minor.patch)

**Subscription Backend**:
- Stripe or Paddle integration
- Subscription management (upgrade, downgrade, cancel)
- Usage tracking (template downloads, update checks)
- Churn reduction: Exit survey, win-back offers

**Expert Network**:
- Partner with 2-3 licensed agents per country:
  - AU: MARA-registered agents (2-3 agents)
  - UK: OISC Level 2+ advisors (2-3 advisors)
  - US: Immigration attorneys (AAI members) (2-3 attorneys)
  - CA: RCIC members (2-3 consultants)
  - NZ: IAA licensed advisors (2-3 advisors)
- Compensation: $200-$500 per quarterly review (per country)
- Backup coverage: If primary expert unavailable, secondary reviews

#### 5.3.4 Pricing Rationale

**Market Research**:
- DIY applicants save $2,000-$5,000 by not hiring migration agent
- Willingness to pay for "peace of mind" on template currency: 5-10% of DIY applicants
- Competitor pricing: $0 (free but outdated guides), $100-$500 (full agent services)
- FileOrganizer sweet spot: $10-$20/month (middle ground)

**Pricing Experiments** (Phase 2.5):
1. **Month 1-2**: Launch at $9.99 single, $19.99 all, $39 one-time
2. **Month 3**: A/B test $14.99 single vs $9.99 single (measure conversion drop)
3. **Month 4-6**: Monitor churn, adjust pricing if churn >25%/year

**Success Metrics** (Phase 2.5):
- Premium adoption: 10-15% of immigration pack users convert
- Churn: <20% annually (acceptable for subscription service)
- LTV: $120 (10 months avg retention × $12/mo blended)
- CAC: $30 (targeted ads, content marketing)
- LTV/CAC: 4.0 (✅ EXCELLENT)

---

### 5.4 Phase 2+ Templates (Post-MVP)

**After Phase 2 + Phase 2.5 validated**:

6. **US Marriage-Based Green Card (I-130)** (if demand high)
7. **CA Spousal Sponsorship** (if demand high)
8. **NZ Partnership-Based Residence Visa**
9. **AU Student Visa 500** (simplified)
10. AU Skilled (189/190/491)
11. UK Skilled Worker
12. US EB-2/EB-3 (high-level)
13. CA Express Entry (FSW)
14. Additional countries (Germany, France, Japan, etc.)

---

### 5.3 Technical Implementation Notes

**For Implementation Team**:

1. **Template Storage**:
   - Location: `~/.fileorganizer/templates/immigration/`
   - Format: YAML (validates against JSON Schema)
   - Versioned filenames: `au_partner_820_801_v1.0.0.yaml`

2. **Classification Service**:
   - Reuse existing LLM classification pipeline
   - Add `classification_hints` from template to LLM prompt
   - Context: "This is for an [AU Partner Visa 820/801]. Possible categories: Financial, Household, Social, Commitment, Identity."

3. **Packaging Engine**:
   - Reuse Tier 3.5 Conversion & Packaging Primitives (PDF merge, cover pages, TOC)
   - Generate PDFs per `packaging_guidance.default_mode`
   - Insert cover pages, TOCs, bookmarks per template specs

4. **UI Wizard**:
   - Step 1: Country selection (show 5 flags: AU, UK, US, CA, NZ)
   - Step 2: Visa selection (show available templates for country, grouped by family)
   - Step 3: Template summary (description, categories, disclaimer) → User confirms
   - Step 4: Evidence upload (select folders, run classification)
   - Step 5: Triage (review/correct categories, see checklist)
   - Step 6: Export (select packaging mode, generate PDFs)

5. **Checklist View**:
   - Show all categories from template
   - For each category:
     - Priority (required/recommended/optional)
     - Document count (0 = red, 1+ = yellow, 5+ = green)
     - Coverage indicator (✅ Covered, ⚠️ Partial, ❌ Missing)
   - Allow user to mark category as "Not Applicable" with note

6. **Premium Service Integration**:
   - Check for updates on app launch (if Premium user)
   - Show template version in pack header: "Template v1.0.0 (Last verified: 2025-11-27)"
   - "Check for Updates" button in Settings → Immigration Packs
   - Changelog diff view (v1.0.0 → v1.3.0 comparison)

---

### 5.4 Testing Strategy

**Unit Tests**:
- Template YAML parsing and validation
- Classification hints matching (keyword, file pattern, sender domain)
- PDF generation (cover page, TOC, bookmarks)

**Integration Tests**:
- End-to-end pack generation (upload 20 documents → classify → triage → export)
- Verify PDFs openable, bookmarks functional, page numbers correct
- Test with sample data for each template (AU, UK, US)

**User Acceptance Testing** (Alpha):
- Recruit 5-10 users per template (AU, UK, US partner visas)
- User completes pack from scratch (upload evidence → export)
- Feedback: "Was template accurate? Were categories clear? Did exports match portal expectations?"

**Expert Validation**:
- Send exported PDFs to migration agents/attorneys for review
- Confirm: "Does this pack structure align with current official guidance?"

---

### 5.5 Risk Mitigation

**Risk 1: Template Becomes Outdated Mid-User-Workflow**
- **Mitigation**: Version locking (pack instance frozen at creation template version)
- **Notification**: User warned if newer template available: "Template v1.1.0 available (fee updated). [Upgrade Pack]"

**Risk 2: User Relies on Template as Legal Advice**
- **Mitigation**: Prominent disclaimers at every touchpoint (selection, pack header, exports)
- **Language**: "Organizational tool only. NOT legal advice. Verify against official guidance."

**Risk 3: Expert Unavailable for Quarterly Review**
- **Mitigation**: Partner with 2-3 experts per country (primary + backup)
- **Contingency**: If all experts unavailable, mark template as "Pending Verification" and delay publication

**Risk 4: Low Premium Adoption (Users Don't Pay for Updates)**
- **Mitigation**: Free tier templates show age warnings after 6 months: "⚠️ Template 8 months old. [Upgrade to Premium]"
- **Alternative**: "Pay-per-update" model ($9.99 for single template update) instead of subscription

**Risk 5: Portal Structure Changes Unexpectedly**
- **Mitigation**: Emergency update workflow (7-day turnaround for major changes)
- **Communication**: Email all active users: "AU ImmiAccount portal redesigned. New template v2.0.0 available."

---

## Appendix A: Full Template Example - AU Partner Visa 820/801

See separate file: `au_partner_820_801_v1.0.0.yaml` (600+ lines, fully specified)

**Summary**:
- 5 main categories (Financial, Household, Social, Commitment, Identity) with 15 subcategories
- Portal mapping to ImmiAccount single "Relationship Evidence" section
- Packaging: One PDF per pillar (4 PDFs + Identity folder)
- Disclaimers: Primary + 4 additional warnings
- Volatility: High (annual fee changes, Form 888 updates)
- Expert: Jane Doe, MARA Reg #1234567, verified 2025-11-27

---

## Appendix B: Generic Immigration Pack Template

For visas not yet covered by country-specific templates, provide a **Generic Immigration Pack** with broad categories:

```yaml
metadata:
  id: "generic_immigration_v1"
  country_code: "GENERIC"
  visa_family: "Other"
  human_name: "Generic Immigration Evidence Pack"
  description: "Fallback template for visas not yet specifically supported. Provides basic organizational structure."

evidence_categories:
  - id: "identity"
    label: "Identity Documents"
    typical_documents: ["Passport", "Birth certificate", "National ID"]

  - id: "financial"
    label: "Financial Evidence"
    typical_documents: ["Bank statements", "Proof of funds", "Sponsor financial documents"]

  - id: "relationship"
    label: "Relationship Evidence (if applicable)"
    typical_documents: ["Marriage certificate", "Photos", "Joint documents"]

  - id: "work_study"
    label: "Work or Study History"
    typical_documents: ["Employment letters", "Academic transcripts", "Certificates"]

  - id: "health_character"
    label: "Health and Character"
    typical_documents: ["Medical exams", "Police certificates"]

packaging_guidance:
  default_mode: "per_category"
  notes: "This is a generic template. Verify category requirements for your specific visa."
```

**Use Case**: User applying for less common visa (e.g., AU Humanitarian, US EB-5 Investor) gets basic organizational structure instead of "not supported" error.

---

## Appendix C: Sources and References

**Official Government Sources**:
- [Australia - Department of Home Affairs](https://immi.homeaffairs.gov.au/)
- [UK - UKVI](https://www.gov.uk/browse/visas-immigration)
- [US - USCIS](https://www.uscis.gov/)
- [Canada - IRCC](https://www.canada.ca/en/immigration-refugees-citizenship.html)
- [New Zealand - Immigration NZ](https://www.immigration.govt.nz/)

**Research Inputs**:
- `cursor_research_brief_immigration_visa_evidence_packs_v2.md`
- `cursor_build_prompt_immigration_visa_pack_compiler.md`
- `research_report_tax_immigration_legal_packs.md` (Part 2)

**Implementation References**:
- `implementation_plan_tax_immigration_legal_packs.md` (Section X: Premium Service)
- `MASTER_BUILD_PLAN_FILEORGANIZER.md` (Tier 5: Scenario Packs)

---

**Document Status**: ✅ Ready for GPT Strategic Review

**Next Steps**:
1. GPT reviews this spec + all reference docs
2. GPT confirms/revises:
   - Phase 1 template priorities (AU/UK/US partner visas)
   - Premium service pricing model
   - Expert network recruitment strategy
   - Risk mitigation adequacy
3. After GPT approval → Implementation begins (Autopack-led, with Claude supervision per Option 3)

**Word Count**: ~14,500 words

**Last Updated**: 2025-11-27
