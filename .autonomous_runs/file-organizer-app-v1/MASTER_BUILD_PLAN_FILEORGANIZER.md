# FileOrganizer – Master Build Plan & Strategic Blueprint

**Date**: 2025-11-27
**Project**: FileOrganizer Desktop Application
**Status**: Planning Phase – Ready for Implementation
**Branch**: `build/file-organizer-app-v1`

---

## EXECUTIVE SUMMARY

This master plan integrates:
1. **Rigorous business analysis** (GO/NO-GO score: 6.6/10 CONDITIONAL GO)
2. **Product intent and features** (from GPT strategic discussion)
3. **Research brief for domain-specific packs** (tax/BAS, immigration, legal)
4. **Market positioning and competitive strategy**

### Key Decision: CONDITIONAL GO with Strategic Pivot

**Market Analysis Verdict**: 6.6/10 (CONDITIONAL GO ⚠️)
- Market Opportunity: 7.5/10 (Large, growing market)
- Competitive Position: 5.5/10 (WEAK – 12-24 month moat)
- Financial Viability: 6.5/10 (Strong unit economics but high capital requirement)
- Technical Feasibility: 7/10 (Proven tech stack)

**Strategic Pivot from Original Plan**:
- **OLD**: Legal-only niche product (5M users, privacy-first)
- **NEW**: General-purpose file organizer (200M users) WITH legal/tax/immigration **scenario packs** as premium upsell

**Why This Pivot**:
- General market larger (200M vs 5M)
- Lower switching barrier from Sparkle (40-50% vs 30-40% from legal tools)
- Multi-tier pricing captures both mass market (free/pro) AND high-ARPU legal users (business tier)
- Avoids over-narrowing to niche that limits profitability

---

## 1. PRODUCT VISION & POSITIONING

### 1.1 One-Sentence Positioning

> A local-first, cross-platform file assistant that understands your documents, keeps your folders organized over time, and builds ready-to-upload packs for legal cases, tax/BAS, immigration, and other life admin — all while giving you fine-grained control over how everything is named, structured, and exported.

### 1.2 Target Users (Prioritized by Business Analysis)

**Primary Segment (Phase 1)**: General Users (200M pool)
- **Profile**: Freelancers, sole traders, consumers who need smarter file organization
- **Pain Points**: Sparkle is Mac-only, imprecise categorization, one-time cleanup
- **WTP**: $5-$15/mo
- **CAC**: $30-$50 (content marketing)
- **LTV**: $80-$150 (avg 15-20 month retention)
- **LTV/CAC**: 1.6-3.0 (⚠️ MARGINAL but acceptable for mass market freemium)

**Secondary Segment (Premium Upsell)**: Legal Professionals (5M pool)
- **Profile**: Solo practitioners, small law firms, self-represented litigants
- **Pain Points**: ChronoVault/Casefleet expensive ($100-$500/mo), cloud-only, complex
- **WTP**: $50-$150/mo
- **CAC**: $200-$400 (legal content marketing, LinkedIn)
- **LTV**: $1,200-$3,600 (avg 24-36 month retention)
- **LTV/CAC**: 3.0-9.0 (✅ EXCELLENT – justify higher features/pricing)

**Tertiary Segment (Phase 2+)**: Small Businesses / Teams (10M pool)
- **Profile**: Teams of 2-10, accountants, immigration consultants
- **WTP**: $10-$30/user/mo
- **CAC**: $150-$300
- **LTV**: $600-$1,800
- **LTV/CAC**: 2.0-6.0 (✅ GOOD)

### 1.3 Differentiation (10x Better, Not 10%)

**❌ WEAK Differentiation** (avoid these claims):
- "We're cross-platform" (Sparkle could add Windows support)
- "We're privacy-first" (niche concern, many prefer cloud convenience)
- "We're cheaper" (race to bottom)

**✅ STRONG Differentiation** (core positioning):
1. **Content Understanding 10x Better Than Sparkle**
   - Sparkle: "Document1.pdf" → "Documents" (filename-based, imprecise)
   - Us: "Document1.pdf" (OCR reveals "evidence of employer misconduct") → "Evidence/Employer Misconduct/2024-11-27" (content-based, precise)
   - **Metric**: 90%+ categorization accuracy vs Sparkle's 60-70%

2. **Scenario Packs for Real-World Workflows** (UNIQUE)
   - Tax/BAS packs (rideshare drivers, freelancers) → Accountant-ready bundles
   - Immigration packs (partner visa, PR applications) → Upload-ready evidence folders
   - Legal timeline cockpit → Court-ready chronologies with source traceability
   - **None of the competitors offer this breadth**

3. **Rules & Profiles Engine** (Deep Customization)
   - Global organization preferences + per-folder schemas + natural-language rule building
   - **Sparkle**: Simple presets only
   - **ChronoVault**: Legal-specific only
   - **Us**: Fully customizable for any workflow

4. **Ongoing Maintenance, Not One-Time Cleanup**
   - Continuous monitoring of Downloads/Documents with batch suggestions
   - **Sparkle**: One-time cleanup only

**Positioning Statement**:
> "First AI file organizer that understands document CONTENT (not just filenames), works cross-platform, includes professional legal timeline features at 1/5th the price of enterprise tools, AND helps with real-life admin (tax, immigration, rental) — all while keeping your data private and offline."

---

## 2. BUSINESS MODEL & PRICING STRATEGY

### 2.1 Multi-Tier Pricing (Mass Market + Premium Upsell)

#### **Free Tier** (Mass Market Capture)
**Purpose**: Acquire 100K+ users, demonstrate value, convert 5-10% to paid

**Features**:
- 1,000 files/month organization limit
- Basic AI categorization (local LLM only)
- Local OCR only (Tesseract)
- Basic folder structures
- Manual export (no automated pack generation)

**Target Users**: Students, casual users, "try before buy"

---

#### **Pro Tier** ($9.99/mo) (General Power Users)
**Purpose**: Convert freemium users who hit limits or want advanced features

**Features**:
- **Unlimited files/month**
- Advanced AI categorization (cloud LLM fallback for tricky files)
- Hybrid OCR (Tesseract + GPT-4 Vision for complex docs)
- Rules & Profiles engine (global + per-folder schemas)
- Natural-language rule builder
- Semantic search and Q&A
- Basic exports (PDF bundles per category)
- Continuous monitoring and batch suggestions

**Target Users**: Freelancers, sole traders, power users

**Conversion Assumption**: 5-8% of free users

---

#### **Business Tier** ($49.99/mo) (Legal + Tax/Immigration Professionals)
**Purpose**: High-ARPU segment with specialized needs

**Features**:
- **Everything in Pro, PLUS**:
- **Legal Evidence Timeline Cockpit**:
  - Event extraction from documents
  - Court-ready chronologies with source traceability
  - Evidence bundle generation (numbered docs, indexes)
- **Tax/BAS Pack Builder**:
  - Country-specific templates (AU BAS, UK Self Assessment, US Schedule C)
  - Profession templates (rideshare driver, cleaner, freelancer)
  - Automated category → tax field mapping
  - Accountant-ready export (spreadsheet + categorized PDFs)
- **Immigration Pack Builder**:
  - Country/visa-specific checklists (AU partner, Canada PR, UK skilled worker)
  - Evidence categorization (relationship, financial, identity, residence)
  - Upload-ready bundles with indexes and optional PPT summaries
- Priority support (email, chat)
- Advanced OCR with handwriting support

**Target Users**: Solo legal practitioners, accountants, immigration consultants, self-represented litigants, sole traders with tax obligations

**Conversion Assumption**: 30-40% of users who start a pack workflow

---

#### **Enterprise Tier** (Custom Pricing) (Phase 2+)
**Purpose**: Teams, firms, consultancies

**Features**:
- Everything in Business, PLUS:
- Team features (shared rules, collaborative packs)
- API access for integrations
- SSO and user management
- On-premise deployment option
- SLA and dedicated support

**Target Users**: Law firms (5-50 lawyers), accounting firms, immigration consultancies

**Launch**: Defer to Month 18+ (focus on individual users first)

---

### 2.2 Revenue Projections (Revised)

**Assumptions**:
- 50% free tier, 40% Pro tier ($10/mo avg), 10% Business tier ($50/mo avg)
- Conversion rates: Year 1 (5%), Year 3 (8%), Year 5 (10%)
- Churn: 15-20% annual (retention 15-20 months)

| Year | Total Users | Paid Users | Conversion | ARPU | **Revenue** |
|------|-------------|------------|------------|------|-------------|
| 1    | 10,000      | 500        | 5%         | $18  | **$108K**   |
| 3    | 100,000     | 8,000      | 8%         | $20  | **$1.92M**  |
| 5    | 500,000     | 50,000     | 10%        | $20  | **$12M**    |

**Profitability**:
- Year 1: -$292K (break-even not yet)
- Year 3: +$1.22M profit (63% margin)
- Year 5: +$7.8M profit (65% margin)

**Break-even**: 18-24 months (5,000-8,000 paying users)

---

### 2.3 Unit Economics (Weighted Average)

- **CAC**: $80 (weighted: General $30-$50, Legal $200-$400)
- **LTV**: $510 (weighted: General $80-$150, Legal $1,200-$3,600)
- **LTV/CAC Ratio**: 6.4 (✅ EXCELLENT – target >3.0)
- **Payback Period**: 5 months (✅ GOOD – target <12 months)

**Sensitivity Analysis**:
- If General user churn higher (12 months instead of 20): LTV/CAC = 3.8 (still acceptable)
- If CAC higher ($150 instead of $80): LTV/CAC = 3.4 (still acceptable)

---

## 3. COMPETITIVE STRATEGY & MOAT

### 3.1 Switching Cost Analysis (Why Users Will Switch)

#### **From Sparkle** (Mac General Users)
- **Their Strengths**: Automatic, Mac-native, personalized, one-time cleanup
- **Their Weaknesses**: Mac-only, limited control, imprecise categorization, no ongoing maintenance
- **Switching Barrier**: LOW-MEDIUM (<$100 cost, <1 hour time)
- **What We Must Offer**:
  - Cross-platform (Windows + Mac)
  - Content understanding (OCR + LLM) vs filename-based
  - Granular control (rules, profiles, preview)
  - Ongoing maintenance (continuous monitoring)
- **Realistic Switching Likelihood**: **40-50%**

**Strategy**: Target Windows users first (Sparkle doesn't serve them), then Mac users who outgrew Sparkle

---

#### **From ChronoVault/Casefleet** (Legal Professionals)
- **Their Strengths**: Timeline builder, court-ready exports, AI-powered, team features
- **Their Weaknesses**: Expensive ($100-$500/mo), cloud-only, enterprise-focused, steep learning curve
- **Switching Barrier**: HIGH ($3K-$10K sunk cost, 10-40 hours migration time, mission-critical)
- **What We Must Offer**:
  - Affordable ($50-$100/mo = 1/5th price)
  - Local-first (privacy for sensitive discovery)
  - Solo practitioner focus (simple UX, not enterprise complexity)
  - Same core features (timelines, evidence bundles) without cloud lock-in
- **Realistic Switching Likelihood**: **30-40%**

**Strategy**: Target solo practitioners and self-represented litigants (underserved), NOT big law firms

---

### 3.2 Competitive Moat (Defensibility)

**Current Moat**: WEAK (12-24 month lead before copycats)
- **Technology Barrier**: LOW (Tauri, Tesseract, Qwen2-7B are open-source)
- **Data Advantage**: NONE initially (no proprietary training data)
- **Network Effects**: NONE (single-player product)
- **Brand/Trust**: NONE initially (unknown product)

**How to Strengthen Moat** (Strategic Imperatives):

1. **Nail 10x Content Understanding** (Months 1-6)
   - Achieve 90%+ categorization accuracy (vs Sparkle 60-70%)
   - Build reputation for "it just works" categorization
   - **Creates word-of-mouth moat**: Users say "Sparkle was OK, but FileOrganizer is magical"

2. **Execute Fast** (Months 1-18)
   - Ship MVP in 6-9 months
   - Acquire 5,000 paying users in 18 months
   - **Creates first-mover advantage** before Sparkle adds cross-platform or open-source forks add legal features

3. **Build Data Moat via User-Trained Models** (Months 12+)
   - User corrections → improve categorization models
   - 100K users × 1,000 corrections each = 100M training examples
   - **Creates data advantage** competitors can't replicate quickly

4. **Build Brand/Trust in Legal Community** (Months 12+)
   - Partner with legal aid organizations
   - Get certified/endorsed by legal associations
   - **Creates brand moat**: "Solo practitioners use FileOrganizer"

**Reality Check**: Even with these efforts, moat remains MODERATE (not STRONG). Must focus on execution speed and product quality.

---

### 3.3 Risk Mitigation (Top 5 Risks)

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **1. Sparkle adds cross-platform** | HIGH (7/10) | HIGH (8/10) | Execute fast (12-18 month window), build data moat, focus on scenario packs (Sparkle won't have) |
| **2. Differentiation insufficient (not 10x)** | MEDIUM (6/10) | CRITICAL (10/10) | Measure 90%+ categorization accuracy, A/B test vs Sparkle, validate with beta users |
| **3. General user conversion <5%** | MEDIUM (5/10) | HIGH (7/10) | Month 6 decision point: If <5%, pivot to Legal-only (higher ARPU justifies higher CAC) |
| **4. Capital requirement underestimated** | MEDIUM (6/10) | HIGH (8/10) | Scope down MVP to 30-40 phases if needed, bootstrap to $300K instead of $600K |
| **5. Local LLM insufficient for legal inference** | LOW (4/10) | MEDIUM (6/10) | Hybrid approach (local primary, cloud fallback), measure accuracy, offer cloud-only mode for Business tier |

**Contingency Plan**:
- If Sparkle adds cross-platform in Month 12 → Double down on scenario packs (tax/immigration/legal) that Sparkle won't have
- If General conversion <5% at Month 6 → Pivot to Legal-only, raise Business tier price to $99/mo
- If funding runs out at Month 15 → Scope down features, raise bridge round, or shut down gracefully

---

## 4. PRODUCT ARCHITECTURE & CORE PRINCIPLES

### 4.1 Core Design Principles (from GPT Discussion)

1. **Local-first and privacy-respecting by default**
   - All documents, OCR, LLM analysis, embeddings live on user's machine
   - Optional cloud calls (OCR/LLM/export) explicit, meterable, paid tiers only
   - NO telemetry of raw document content or filenames (only feature usage events)

2. **User always in control**
   - No silent mass renames/moves
   - All operations through **preview/staging** with clear before/after views
   - Every change logged and **reversible** through operations log

3. **Rules & Profiles, not black-box magic**
   - Users define global organization preferences and per-folder schemas
   - AI proposes and assists, but user rules and overrides are first-class
   - Natural-language rule builder for accessibility

4. **Scenario-focused workflows, not generic features**
   - Tax/BAS, immigration, legal packs designed as **guided experiences** with checklists, progress, domain-relevant summaries
   - Not generic "file tagging" but purpose-built for real workflows

5. **Multi-language and multi-locale aware**
   - Handles documents in major languages (EN, ES, FR, DE, PT, IT, ZH, JA, KO)
   - Respects locale-specific date formats and naming conventions

6. **Explainable outputs**
   - Legal timelines and packs link every event/summary back to source documents/pages
   - App can "explain what it did" for any folder or pack

---

### 4.2 Technology Stack (Validated)

#### **Desktop Framework**: Tauri 2.0
- **Why**: 3-10MB binaries (vs Electron 50-120MB), 30-40MB RAM (vs 200-300MB), <0.5s startup, smaller attack surface
- **Trade-off**: WebView inconsistencies (CSS rendering, JavaScript API differences) vs UI consistency
- **Decision**: Tauri for Phase 1 (target power users tolerate minor UI differences), Electron fallback if WebView issues too severe
- **Risk Mitigation**: Extensive cross-platform testing (Windows/Mac/Linux), use React for consistent component layer

#### **OCR Strategy**: Hybrid (Privacy + Accuracy)
- **Local OCR (Tesseract 5.x)**: Default for 80% of docs, ~30% accuracy on complex/handwritten, free, fast
- **Cloud OCR (GPT-4 Vision)**: Fallback for 20% complex docs, ~80% accuracy, $0.01-$0.03 per page, paid tiers only
- **Cost**: 1,000 pages × 20% cloud = 200 pages × $0.02 = $4/user/month (acceptable for Pro tier at $10/mo)
- **Why Hybrid**: Balances privacy (local default) with accuracy (cloud fallback)

#### **Local LLM**: Qwen2-7B-Instruct
- **Why**: 3.85/5 human eval on legal tasks, broader capabilities than SaulLM-7B (legal + general + business), 32k context window
- **Hardware**: 16GB RAM minimum (excludes ~40% of consumer PCs, acceptable for target users)
- **Alternative**: SaulLM-7B for legal-specific inference (Phase 2 if Qwen2 insufficient)
- **Cloud Fallback**: GPT-4o for users without 16GB RAM or for Business tier users demanding highest accuracy

#### **Database**: SQLite
- **Why**: Embedded, fast, billions of devices, sufficient for 10k-100k files per user
- **Schema**:
  - `files` (path, hash, metadata, category, confidence, last_updated)
  - `operations_log` (timestamp, old_path, new_path, rule_id, reversible)
  - `cross_references` (file_id, referenced_file_id, page, context)
  - `rules` (profile_id, folder_path, pattern, destination, automation_level)
  - `packs` (pack_id, type, country, status, created_at, exported_at)

#### **Frontend**: React + TypeScript
- **Why**: Mature ecosystem, consistent across Tauri WebViews, type safety
- **UI Library**: Shadcn/ui (accessible, customizable, modern)
- **State Management**: Zustand (simpler than Redux, sufficient for desktop app)

#### **Backend (Rust via Tauri)**:
- **Why**: Performance, safety, Tauri native
- **Modules**:
  - Scanner (directory traversal, file hashing)
  - OCR (Tesseract wrapper, GPT-4 Vision API calls)
  - LLM (Qwen2-7B inference, embeddings generation)
  - Categorizer (rule engine, confidence scoring)
  - Organizer (rename/move operations with logging)
  - Pack Engine (config-driven workflows, export pipelines)

---

### 4.3 Multi-Pass Architecture (Safe Automation)

**Workflow**: Discovery → Analysis → Review → Execution → Validation

1. **Discovery Phase**:
   - User selects folder(s) to organize
   - App scans: file count, types, size, quick metadata
   - **Checkpoint**: User confirms folders

2. **Analysis Phase**:
   - OCR (Tesseract local, GPT-4 Vision cloud for flagged files)
   - LLM content understanding (extract entities, dates, categories)
   - Rule application (global profile, folder profile, user rules)
   - Categorization with confidence scores (high/medium/low)
   - **Checkpoint**: User reviews categories in staging area

3. **Review Phase (Staging)**:
   - **Before → After** preview table (old path, new path, category, confidence)
   - Triage UI for low-confidence files (see section 6.4)
   - User actions: Approve all, approve by group, deselect, edit rules
   - **Checkpoint**: User approves change set

4. **Execution Phase**:
   - Rename/move files per approved change set
   - Log every operation to `operations_log`
   - **Checkpoint**: User reviews results, can rollback if needed

5. **Validation Phase**:
   - Cross-reference check (detect broken internal references)
   - Duplicate detection (content hash, semantic embeddings)
   - Final report: X files organized, Y conflicts resolved, Z unknowns deferred
   - **Checkpoint**: User marks folder as "organized" or continues triage

**Rollback Capability**:
- Undo last operation
- Undo all operations from specific date/time
- Selective revert of individual changes
- **Limitation**: Non-reversible if original file deleted (warn user, keep copy in trash)

---

## 5. ORGANIZATION ENGINE: RULES, PROFILES, PREFERENCES

### 5.1 Global Organization Profile

Defines **default** way files are organized across all folders:

**Settings**:
- **Date formats**: `YYYY-MM-DD`, `DD/MM/YYYY`, `MM-DD-YYYY`
- **Language/labels**: "Invoices"/"Factures"/"Facturas" per locale
- **Naming patterns** (tokenized):
  - `{date:YYYY-MM-DD}_{category}_{short_title}_{counter}`
  - `{year}_{client}_{doc_type}_{counter}`
- **Folder structure templates**:
  - Time-based: `/Year/Month/`
  - Category-based: `/Finance/{Year}/`, `/Immigration/{Country}/{Program}/`

**Onboarding**:
- Ask 3-5 simple questions to set initial global profile:
  - "What date format do you prefer?" (show examples)
  - "How long should filenames be?" (concise/detailed/very detailed)
  - "What's your primary language?" (for category labels)

### 5.2 Folder-Level Profiles

Every folder can override global profile:

**Profile Types**:
- "Invoices" → Auto-detect vendor, amount, date from PDF; rename to `{vendor}_{YYYY-MM}_{amount}`
- "Photos" → Use EXIF date, group by Year/Month, rename to `{YYYY-MM-DD}_{location}_{counter}`
- "Immigration Pack" → Use immigration schema (see section 8.2)
- "Tax/BAS Pack" → Use tax schema (see section 8.3)
- "Legal Case" → Use legal timeline schema (see section 7.4)

**UI Pattern**:
- Right-click folder → "Folder rules…"
- Show inherited global settings and local overrides
- Live preview of Before → After for 5-10 sample files

### 5.3 Natural-Language Rule Builder

**Examples**:
- User: "In this folder, group files by year and month, then rename to YYYY-MM-DD_short-title"
- App:
  1. Parses request → Rule: `folder_structure = "/Year/Month/"`, `naming_pattern = "{date:YYYY-MM-DD}_{short_title}"`
  2. Shows preview table (10 sample files with Before → After)
  3. Allows tweak (separators, tokens, destination paths)
  4. Saves rule to folder profile or named template

**Voice Input** (stretch goal Phase 2):
- Same natural-language parsing but via microphone
- Especially useful for accessibility (elderly users, vision-impaired)

### 5.4 Presets and Rule Collections

**Ship with**:
- "Minimalist" – Shallow hierarchy, concise names (`YYYY-MM-DD_title`)
- "Project-centric" – `/Projects/{Project}/{Year}/{Type}/`
- "Life admin" – `Taxes`, `Housing`, `Health`, `Work`, `Travel` with default rules per category
- "Legal evidence" – See section 7.4
- "Tax/BAS" – See section 8.3
- "Immigration" – See section 8.2

**Import/Export** (Phase 2):
- Allow users to export rule sets as JSON
- Community sharing (FileOrganizer forum, GitHub)
- Team sharing (Enterprise tier)

---

## 6. AUTOMATION SAFETY, STAGING, AND TRIAGE

### 6.1 Automation Profiles (Global + Per-Folder)

**Modes**:
- **Preview Only** – Never execute automatically, always show suggested changes
- **Assisted** – Auto-group suggestions into batches, user approves per-batch
- **Autopilot for low-risk areas** – For specific folders (e.g., Downloads >30 days old), auto-apply safe rules (archive by date/type)

**Per-Folder Override**:
- Mark `Evidence/Personal` as "never auto-move or rename" (safe zone)
- Mark `Downloads` as "Autopilot after 30 days"

### 6.2 Staging Area and Dry-Run

**Proposed Changes View**:
- Number of files to rename/move/convert
- **Before → After** table (old path, new path, category, confidence)
- Risk flags (overwriting file, major path change, cross-reference detected)

**User Actions**:
- Approve all
- Approve by group (e.g., all "Tax → Fuel" renames)
- Deselect individual items
- Edit rule inline (adjust naming pattern)

### 6.3 Operations Log and Rollback

**Schema** (`operations_log` table):
```sql
CREATE TABLE operations_log (
  id INTEGER PRIMARY KEY,
  timestamp DATETIME,
  user_id TEXT,
  operation_type TEXT, -- 'rename', 'move', 'convert', 'delete'
  old_path TEXT,
  new_path TEXT,
  rule_id INTEGER,
  reversible BOOLEAN,
  metadata JSON -- additional context
);
```

**UI**:
- "History" tab showing recent operations
- Filter by date, folder, operation type
- **Undo** button per operation or batch
- **Undo all since [date/time]**

**Limitations**:
- If original file deleted → NOT reversible (warn user, keep copy in OS trash)
- If file moved and then edited → rollback restores original location but not edits (warn user)

### 6.4 Handling Unrecognized Files (Triage)

**Confidence Buckets**:
- **High (>80%)**: Auto-apply (with user approval in staging)
- **Medium (50-80%)**: Show as suggestions in staging
- **Low (<50%)**: Send to triage board

**Triage Board UI**:
- Card/list view per file:
  - Thumbnail or snippet (first page of PDF, image preview)
  - Filename
  - AI guess: "Maybe: bank statement / insurance / immigration email / random file" (with confidence %)
  - Quick action chips: `[Tax] [Immigration] [Health] [Personal] [Legal] [Ignore]`
  - Actions: "Move to folder X", "Mark Not Important", "Skip for now"

**Batch Operations**:
- Filter by guessed type: "Show likely bank statements" (e.g., all PDFs with "Account Summary" in text)
- Select many → assign category with one click
- "Apply same rule to all similar files" (based on sender/vendor/format)

**Teach-and-Learn Loop**:
- User correction: "This is actually Tax → Fuel expense" (not "Tax → General")
- App:
  1. Updates file category
  2. Suggests new rule: "Files from Shell → Fuel expense"
  3. Shows preview of 5 similar files that would be affected
  4. Asks: "Apply this rule to similar files? Save to Tax profile?"
- User approves → rule saved, similar files auto-categorized next time

**Triage Wizards** (for large unknown buckets):
- "I see 200 uncategorized files. Let me ask a few questions to group them:"
  - "Are these mostly tax-related, immigration-related, personal, or mixed?"
  - "Are they mostly from a small number of senders (Uber, bank, employer) or many senders?"
- Group files by sender/keywords/date → allow group-level classification

**Aim**: Triage should feel like **swiping through suggestions** (Tinder-style), not manually inspecting every file

---

## 7. CONTENT UNDERSTANDING, SEARCH, AND TIMELINES

### 7.1 OCR and Multi-Language Support

**OCR Pipeline**:
1. **Local OCR (Tesseract 5.x)**: Default for all files, all tiers
   - Languages: English, Spanish, French, German, Portuguese, Italian, Chinese (Simplified), Japanese, Korean
   - Accuracy: ~30% on complex/handwritten docs, ~70% on clean printed docs
   - Cost: Free (local processing)

2. **Cloud OCR (GPT-4 Vision)**: Fallback for flagged files (Pro/Business tiers)
   - Triggers: Low Tesseract confidence (<50%), handwritten text detected, poor scan quality
   - Accuracy: ~80% on complex docs, ~95% on handwritten
   - Cost: $0.01-$0.03 per page (user pays via subscription)

**Language Configuration**:
- Onboarding: "Which languages do your documents use?" (select up to 3 priority languages)
- Tesseract: Load language packs for selected languages only (smaller binary, faster)
- LLM: Prompt includes language hint for better categorization

### 7.2 Semantic Search and Q&A

**Embeddings Generation**:
- Use lightweight embedding model (e.g., `all-MiniLM-L6-v2`, 384 dimensions, 23MB)
- Generate embeddings for:
  - Full OCR text (chunked to 512 tokens per chunk)
  - Extracted metadata (title, author, sender, recipient)
  - Filename (without extension)
- Store in SQLite with FAISS index for fast similarity search

**Search UX**:
- **Command Palette** (Cmd+K / Ctrl+K):
  - User types: "Show me the invoice for that Airbnb in Tokyo in March 2023"
  - App:
    1. Semantic search: "invoice", "Airbnb", "Tokyo", "March 2023"
    2. Results ranked by similarity score
    3. Show top 10 with snippets and context
- **Filters**: Date range, file type, category, pack, entity (person/org)

**Q&A Examples**:
- "List all documents related to my 2024 tax return"
- "When did I last renew my car insurance and with which company?"
- "Show me all emails from my landlord in the last 2 years"

**Implementation**:
- LLM (Qwen2-7B) for query understanding and response generation
- Embeddings for retrieval (semantic search)
- Combine: Retrieve top 20 docs via embeddings, re-rank via LLM, return top 5 with snippets

### 7.3 Entity- and Topic-Centric Views

**Entity Extraction** (via Qwen2-7B):
- **People**: Names of individuals mentioned in docs
- **Organizations**: Employers, banks, landlords, agencies, vendors
- **Dates**: Key dates (incident dates, filing dates, payment dates)
- **Amounts**: Monetary values (invoices, expenses, income)

**Views**:
- **People Tab**: Group docs by person (e.g., "Show all docs mentioning John Smith")
- **Organizations Tab**: Group docs by org (e.g., "Show all docs from Commonwealth Bank")
- **Timeline Tab**: Chronological view of all events (see 7.4)
- **Packs Tab**: Show files associated with each pack (tax pack, immigration pack, legal case)

### 7.4 Personal and Legal Timelines

**Shared Event Schema** (SQLite table):
```sql
CREATE TABLE timeline_events (
  id INTEGER PRIMARY KEY,
  event_type TEXT, -- 'incident', 'communication', 'filing', 'medical', 'employment', 'travel', 'move', 'purchase'
  date DATE,
  time TIME, -- optional
  date_approximate BOOLEAN, -- true if date is estimated
  description TEXT,
  parties TEXT, -- JSON array of people/orgs involved
  category TEXT, -- 'legal', 'personal', 'tax', 'immigration'
  source_docs TEXT, -- JSON array of {file_id, page, snippet}
  metadata JSON -- additional context
);
```

#### **Legal Case Timelines** (Business Tier)

**Use Case**: Solo practitioners, self-represented litigants preparing chronologies for court

**Workflow**:
1. User creates "Legal Case" pack (select case folder)
2. App scans all files (emails, PDFs, photos, transcripts)
3. Extracts events:
   - Incident: "Workplace injury on 2024-03-15" (from incident report PDF, page 2)
   - Communication: "Email from employer on 2024-03-16" (from email attachment)
   - Medical: "Doctor visit on 2024-03-17" (from medical invoice)
4. User reviews/edits events in timeline UI:
   - Drag to reorder
   - Edit description
   - Add/remove parties
   - Link to additional source docs
5. Export formats:
   - **Markdown**: Table with columns (Date, Event, Parties, Source)
   - **Word**: Formatted table with hyperlinks to source docs
   - **PDF**: Numbered chronology with source footnotes
   - **CSV**: Importable to Excel/Casefleet

**Critical Feature**: Every event links back to source documents/pages (traceability)

#### **Personal/Life Timelines** (All Tiers)

**Use Case**: General users understanding "what happened when" in life admin

**Events**:
- Moves (change of address from utility bills)
- Jobs (employment start/end from contracts, tax docs)
- Travels (from flight bookings, hotel receipts)
- Major purchases (car, house from invoices, contracts)
- Medical visits (from invoices, EOBs)
- Visa/immigration events (applications, approvals from official docs)

**UI**:
- Vertical timeline with cards per event
- Filter by year, category, entity
- Export to PDF or Markdown for personal records

---

## 8. SCENARIO PACKS AND DOMAIN-SPECIFIC WORKFLOWS

**Core Principle**: Pack system is **configuration-driven** so new pack types and country variants can be added via JSON/YAML templates without code changes.

### 8.1 Shared Pack Concepts (Architecture)

**Each Pack Defines** (JSON/YAML config):
```yaml
pack:
  id: "tax_au_bas_sole_trader_rideshare"
  name: "Australian BAS Pack – Rideshare Driver"
  domain: "tax"
  country: "AU"
  version: "1.0"

  checklist:
    - category: "Income – Rideshare"
      subcategories:
        - "Uber/Didi/Ola payouts"
        - "Cash tips (if tracked)"
      required: true
      minimum_docs: 4 # Quarterly statements
      time_coverage: "Q1 2025" # User-specified

    - category: "Expenses – Vehicle"
      subcategories:
        - "Fuel receipts"
        - "Maintenance/repairs"
        - "Registration/insurance"
      required: true
      minimum_docs: 10

    - category: "Expenses – Phone"
      subcategories:
        - "Monthly phone bills (business use %)"
      required: false
      minimum_docs: 3

  folder_layout: "/Tax/2024-25/BAS-Q1/{Category}/"

  classification_rules:
    - rule: "If sender = 'Uber' AND contains 'Weekly Summary' → Income – Rideshare"
    - rule: "If vendor = 'Shell' OR 'BP' OR '7-Eleven' AND contains 'Fuel' → Expenses – Vehicle – Fuel"

  export_recipe:
    - format: "pdf_per_category"
      options:
        - table_of_contents: true
        - numbered_entries: true
    - format: "master_spreadsheet"
      fields: ["Date", "Vendor", "Category", "Amount (excl GST)", "GST", "Total", "Source Doc"]
    - format: "optional_ppt_summary"
      slides:
        - "Total Income by Month"
        - "Total Expenses by Category"
        - "BAS Field Mappings (G1, 1A, 1B)"

  field_mappings: # Tax form fields
    - category: "Income – Rideshare"
      bam_field: "G1" # Total Sales
    - category: "Expenses – Vehicle – Fuel"
      bam_field: "G11" # GST on purchases
```

**App Engine Reads Config**:
- Loads checklist schema
- Applies classification rules
- Generates folder structure
- Exports per recipe (PDFs, spreadsheets, PPT)

**Adding New Pack**:
1. Create new YAML file in `/packs/templates/`
2. Restart app (or hot-reload in dev mode)
3. Pack appears in "Create Pack" wizard

### 8.2 Immigration / Visa Evidence Packs

**Example: Australia Partner Visa (Subclass 820/801)**

**Config** (simplified):
```yaml
pack:
  id: "immigration_au_partner_visa"
  name: "Australia Partner Visa (820/801) Evidence Pack"
  domain: "immigration"
  country: "AU"
  program: "Partner Visa (820/801)"
  version: "1.0"

  disclaimer: |
    This pack helps you organize evidence for your visa application.
    It is NOT legal advice. Consult a migration agent for eligibility and requirements.

  checklist:
    - category: "Identity"
      subcategories:
        - "Passports (all pages)"
        - "Birth certificates"
        - "National ID cards"
      required: true
      minimum_docs: 2

    - category: "Relationship Evidence"
      subcategories:
        - "Joint financial documents (bank accounts, leases, loans)"
        - "Photos together (minimum 20, spanning relationship duration)"
        - "Travel together (boarding passes, hotel bookings)"
        - "Social recognition (family/friends statements, social media)"
      required: true
      minimum_docs: 30
      time_coverage: "12 months minimum, ideally full relationship duration"

    - category: "Financial Support"
      subcategories:
        - "Sponsor's payslips (last 6 months)"
        - "Tax returns (sponsor + applicant)"
        - "Bank statements (joint + individual, last 12 months)"
      required: true
      minimum_docs: 10

    - category: "Cohabitation / Residence"
      subcategories:
        - "Joint lease or property title"
        - "Utility bills (electricity, gas, internet) showing both names"
        - "Mail addressed to both at same address"
      required: true
      minimum_docs: 6
      time_coverage: "12 months"

    - category: "Employment / Study"
      subcategories:
        - "Employment contracts"
        - "Enrollment letters"
        - "Qualification certificates"
      required: false

  folder_layout: "/Immigration/AU_Partner_Visa_2025/{Category_Number}_{Category}/"
  # E.g., "/Immigration/AU_Partner_Visa_2025/01_Identity/", "02_Relationship/", etc.

  classification_rules:
    - rule: "If document_type = 'passport' OR filename contains 'passport' → Identity"
    - rule: "If sender in ['bank', 'landlord'] AND contains both [applicant_name, sponsor_name] → Relationship – Joint Financial"
    - rule: "If document_type = 'photo' AND date in relationship_period → Relationship – Photos"

  export_recipe:
    - format: "pdf_per_category"
      options:
        - table_of_contents: true
        - category_index_pages: true # E.g., "Category 02: Relationship Evidence – 45 documents"
    - format: "master_index_pdf"
      content: |
        Cover page with:
        - Applicant name
        - Sponsor name
        - Application date
        - Table of contents by category
        - Total documents: X
    - format: "optional_ppt_summary"
      slides:
        - "Relationship Timeline (photos, travels, milestones)"
        - "Financial Ties (joint accounts, assets)"
        - "Cohabitation Evidence (leases, bills, addresses)"
```

**Workflow**:
1. User: "Create Immigration Pack" → Select "Australia Partner Visa"
2. App asks:
   - Applicant name
   - Sponsor name
   - Relationship start date
   - Intended application date
3. User drops all docs into staging area (drag & drop folder or files)
4. App classifies per rules:
   - "Passport_John.pdf" → Identity
   - "Joint_Lease_2024.pdf" → Cohabitation
   - "Photo_Tokyo_Trip.jpg" (EXIF date 2023-05) → Relationship – Photos
5. Triage UI for unknowns (see section 6.4)
6. User reviews/fixes classifications
7. App checks checklist:
   - ✅ Identity: 3 docs (minimum 2)
   - ⚠️ Relationship: 25 docs (minimum 30, suggest adding more photos)
   - ✅ Financial: 12 docs (minimum 10)
   - ✅ Cohabitation: 8 docs (minimum 6)
   - ❌ Employment: 0 docs (optional, can skip)
8. User approves
9. Export:
   - Folder structure: `/Immigration/AU_Partner_Visa_2025/01_Identity/`, `02_Relationship/`, etc.
   - Per-category PDFs: `01_Identity.pdf`, `02_Relationship.pdf` (all docs merged, table of contents)
   - Master index PDF: Cover page + category summary + TOC
   - Optional PPT: 5-slide summary with key evidence thumbnails

**Constraints**:
- **No legal advice**: App shows checklist based on public guidance, NOT eligibility assessment
- **User responsibility**: "You must review all documents and ensure they meet visa requirements"

### 8.3 Tax and BAS Packs for Sole Traders

**Use Case**: Rideshare drivers, delivery couriers, cleaners, freelancers preparing tax/BAS

**Example: Australian BAS Pack – Rideshare Driver**

**Config** (simplified):
```yaml
pack:
  id: "tax_au_bas_sole_trader_rideshare"
  name: "Australian BAS Pack – Rideshare Driver (Q1 2025)"
  domain: "tax"
  country: "AU"
  program: "BAS – Sole Trader"
  profession: "Rideshare Driver"
  version: "1.0"

  disclaimer: |
    This pack helps you organize tax documents for your accountant or BAS agent.
    It is NOT tax advice. Consult a registered tax agent for lodgment.

  period:
    - tax_year: "2024-25"
    - quarter: "Q1" # July-Sep 2024

  checklist:
    - category: "Income – Rideshare Platforms"
      subcategories:
        - "Uber driver statements"
        - "Didi driver statements"
        - "Ola driver statements"
      required: true
      minimum_docs: 1 # At least one platform
      expected_format: "Weekly summaries, monthly statements, or annual tax summary"

    - category: "Income – Cash Tips"
      subcategories:
        - "Manual log or spreadsheet"
      required: false
      note: "If you track cash tips, include here"

    - category: "Expenses – Vehicle – Fuel"
      subcategories:
        - "Fuel receipts (Shell, BP, Caltex, 7-Eleven, etc.)"
      required: true
      minimum_docs: 10
      note: "Keep all fuel receipts for business use %. Accountant will calculate deduction."

    - category: "Expenses – Vehicle – Maintenance"
      subcategories:
        - "Service invoices"
        - "Repair invoices"
        - "Car wash receipts"
      required: false

    - category: "Expenses – Vehicle – Registration/Insurance"
      subcategories:
        - "Rego renewal notice"
        - "Car insurance invoice"
      required: true
      minimum_docs: 2

    - category: "Expenses – Phone"
      subcategories:
        - "Monthly phone bills"
      required: false
      note: "If you use phone for business (navigation, customer calls), include last 3 months"

    - category: "Expenses – Other"
      subcategories:
        - "Parking/tolls"
        - "Car accessories (phone mount, charger)"
      required: false

  folder_layout: "/Tax/2024-25/BAS-Q1/{Category}/"

  classification_rules:
    - rule: "If sender = 'Uber' OR filename contains 'Uber' AND contains 'Driver' OR 'Earnings' → Income – Rideshare Platforms"
    - rule: "If vendor = 'Shell' OR 'BP' OR '7-Eleven' OR 'Caltex' AND contains 'Fuel' OR line_item_contains('Unleaded') → Expenses – Vehicle – Fuel"
    - rule: "If vendor contains 'Service' OR 'Tyres' OR 'Auto' AND amount > $50 → Expenses – Vehicle – Maintenance"
    - rule: "If contains 'Registration' OR 'Rego' OR 'Insurance' AND vendor = 'VicRoads' OR insurance_company → Expenses – Vehicle – Registration/Insurance"
    - rule: "If sender = 'Telstra' OR 'Optus' OR 'Vodafone' AND document_type = 'invoice' → Expenses – Phone"

  export_recipe:
    - format: "master_spreadsheet"
      filename: "BAS_Q1_2025_Summary.xlsx"
      sheets:
        - name: "Income Summary"
          columns: ["Date", "Platform", "Gross Earnings", "Fees", "Net Income", "GST Collected", "Source Doc"]
        - name: "Expenses Summary"
          columns: ["Date", "Vendor", "Category", "Amount (excl GST)", "GST", "Total", "Business Use %", "Source Doc"]
        - name: "BAS Field Mappings"
          content: |
            G1 (Total Sales): $X,XXX
            1A (GST on Sales): $XXX
            1B (GST on Purchases): $XXX
            G11 (Non-capital purchases): $X,XXX
            [Additional fields per BAS form]

    - format: "pdf_per_category"
      options:
        - table_of_contents: true
        - numbered_entries: true

    - format: "accountant_export_zip"
      contents:
        - "BAS_Q1_2025_Summary.xlsx"
        - "Income_Rideshare_Platforms/" (all platform statements as PDFs)
        - "Expenses_Vehicle_Fuel/" (all fuel receipts as PDFs)
        - "Expenses_Vehicle_Maintenance/" (all maintenance invoices)
        - "Expenses_Vehicle_Registration_Insurance/" (rego + insurance docs)
        - "Expenses_Phone/" (phone bills)
        - "README.txt" (explains structure, notes business use % assumptions)

  field_mappings: # Map categories to BAS fields
    - category: "Income – Rideshare Platforms"
      bas_field: "G1" # Total Sales
      gst_treatment: "GST-free" # Rideshare platforms handle GST
    - category: "Expenses – Vehicle – Fuel"
      bas_field: "G11" # Non-capital purchases
      gst_field: "1B" # GST on purchases
      business_use_percent: 80 # User-configurable assumption
    - category: "Expenses – Vehicle – Registration/Insurance"
      bas_field: "G11"
      gst_field: "1B"
      business_use_percent: 80
    - category: "Expenses – Phone"
      bas_field: "G11"
      gst_field: "1B"
      business_use_percent: 50 # User-configurable
```

**Workflow**:
1. User: "Create Tax Pack" → Select "AU BAS – Rideshare Driver – Q1 2025"
2. App asks:
   - ABN (Australian Business Number)
   - Primary platform (Uber/Didi/Ola/Mixed)
   - Business use % for vehicle (default 80%, user can adjust)
   - Business use % for phone (default 50%, user can adjust)
3. User drops all docs into staging area:
   - Bank statements
   - Uber weekly summaries
   - Fuel receipts (photos or PDFs)
   - Rego renewal
   - Car insurance invoice
4. App classifies per rules:
   - "Uber_Weekly_Summary_2024-07-15.pdf" → Income – Rideshare
   - "Shell_Fuel_Receipt_2024-07-20.jpg" (OCR'd) → Expenses – Vehicle – Fuel
   - "VicRoads_Rego_2024.pdf" → Expenses – Vehicle – Registration
5. Triage for unknowns
6. User reviews/fixes classifications
7. App aggregates:
   - Total Income (Uber): $12,500 (Q1)
   - Total Fuel Expenses: $1,200 × 80% business use = $960 deductible, GST $96
   - Total Rego/Insurance: $800 × 80% = $640 deductible, GST $64
   - Total Phone: $150 × 50% = $75 deductible, GST $7.50
8. App generates BAS summary spreadsheet:
   - G1 (Total Sales): $12,500
   - 1B (GST on purchases): $167.50
   - G11 (Non-capital purchases): $1,675
9. Export:
   - `BAS_Q1_2025_Summary.xlsx` (spreadsheet with all calculations)
   - Categorized folders with PDFs
   - ZIP for accountant with README explaining assumptions

**Positioning**:
- **NOT tax advice**: "This summary is for organizational purposes. Your accountant will validate and lodge BAS."
- **Target**: Solo traders who currently pay $200-$500/quarter to accountants for basic data entry
- **Value Prop**: "Reduce accountant fees by 50-80% by providing structured, accountant-ready packs"

### 8.4 Other Packs (Phase 2+)

**Rental Application Pack**:
- Categories: ID, payslips (last 3 months), references (landlord, employer), rental history, bank statements
- Export: ZIP with cover letter template, all docs as PDFs

**Job Application Pack**:
- Categories: CV, cover letters, certificates, reference letters, portfolio samples
- Export: Tailored folder per job application

**Insurance Claim Pack**:
- Categories: Incident reports, photos (damage, injuries), invoices (repairs, medical), police reports, witness statements
- Export: Claim-ready bundle with index

**Generic Evidence Pack**:
- User defines custom categories
- Rules & profiles apply
- Standard export (PDFs per category, master index)

---

## 9. MVP SCOPE AND PHASED ROLLOUT

### 9.1 MVP Definition (Phase 1: Months 1-9)

**Goal**: Ship usable product in 6-9 months to start user acquisition before competitors catch up

**Must-Have Features** (30-40 phases):

**Tier 1: Core Infrastructure** (Phases 1-8)
1. Project setup (Tauri 2.0 + React + Rust backend)
2. SQLite database schema (files, operations_log, rules, packs)
3. File scanner (directory traversal, file hashing, metadata extraction)
4. Onboarding wizard (global profile setup: date format, language, naming pattern)
5. Settings UI (automation mode, telemetry, theme)
6. Operations log viewer (history of changes)
7. Rollback functionality (undo operations)
8. Cross-platform build pipeline (Windows/Mac, Linux deferred)

**Tier 2: AI Processing** (Phases 9-16)
9. OCR integration (Tesseract local)
10. LLM integration (Qwen2-7B local inference)
11. Embeddings generation (all-MiniLM-L6-v2)
12. Content extraction pipeline (entities, dates, categories from OCR+LLM)
13. Cloud OCR integration (GPT-4 Vision API for Pro tier)
14. Cloud LLM fallback (GPT-4o API for users without 16GB RAM)
15. Confidence scoring (high/medium/low)
16. Caching and performance optimization (avoid re-processing files)

**Tier 3: Organization Logic** (Phases 17-24)
17. Global profile management (create, edit, import presets)
18. Folder profile management (override global, per-folder schemas)
19. Rule engine (pattern matching, token substitution, destination paths)
20. Categorization engine (apply rules, confidence scoring)
21. Natural-language rule builder (text input, parse to rule, preview)
22. Staging area UI (Before → After table, approve/deselect)
23. Rename/move executor (apply approved changes, log operations)
24. Cross-reference detector (find internal document references, warn before breaking)

**Tier 4: UI/UX** (Phases 25-32)
25. Main window layout (sidebar, content area, command palette)
26. File browser (tree view, list view, thumbnails)
27. Triage board (card view, quick action chips, batch operations)
28. Command palette (Cmd+K, natural language commands)
29. Dark mode and theming (light/dark, follow OS preference)
30. Wizard flows (onboarding, pack creation)
31. Progress indicators (batch processing, export generation)
32. Help/documentation (in-app tooltips, link to docs)

**Tier 5: Scenario Packs (MVP Subset)** (Phases 33-38)
33. Pack configuration schema (JSON/YAML parser)
34. Pack engine (load templates, apply classification rules, export recipes)
35. Generic pack template (user-defined categories, standard exports)
36. Tax pack template (generic, not country-specific) – basic income/expense categorization
37. Immigration pack template (generic, not country-specific) – identity/relationship/financial categories
38. Legal timeline (basic event extraction, chronology export to Markdown/PDF)

**Tier 6: Testing & Polish** (Phases 39-40)
39. Cross-platform testing (Windows 10/11, macOS 12+, automated CI/CD)
40. Beta user testing (recruit 20-50 users, usability feedback, bug fixes)

**Deferred to Phase 2**:
- Country-specific pack templates (AU BAS, UK Self Assessment, AU partner visa)
- Profession templates (rideshare driver, cleaner)
- Duplicate detection (content hash, semantic embeddings)
- Bulk preview (show all operations before execution)
- Semantic search UI (Q&A, entity views)
- Voice input (natural-language commands via microphone)
- OS file explorer integration (context menu, side panel)
- Team features (shared rules, collaborative packs)
- API access
- Linux support (defer to Month 12+)

### 9.2 Phased Rollout Timeline

**Month 1-2: Foundation**
- Phases 1-8 (Core Infrastructure)
- Deliverable: Desktop app shell, database, file scanner, onboarding wizard

**Month 3-4: AI Capabilities**
- Phases 9-16 (AI Processing)
- Deliverable: OCR + LLM working locally, cloud fallback integrated

**Month 5-6: Organization Engine**
- Phases 17-24 (Organization Logic)
- Deliverable: Rules engine, staging area, rename/move operations

**Month 7-8: UI & Scenario Packs**
- Phases 25-38 (UI/UX + Scenario Packs MVP)
- Deliverable: Polished UI, triage board, generic packs (tax, immigration, legal timeline)

**Month 9: Testing & Launch**
- Phases 39-40 (Testing & Polish)
- Beta launch: Recruit 50-100 early adopters (ProductHunt, Reddit, HN)
- Collect feedback, fix critical bugs
- **Public launch**: Month 9 end

**Month 10-12: Iteration & Country-Specific Packs**
- Add AU BAS pack (rideshare driver template)
- Add AU partner visa pack (relationship evidence template)
- Improve categorization accuracy based on user corrections
- **Milestone**: 1,000 users, 50 paying ($5K MRR)

**Month 13-18: Scale & Market Validation**
- Add UK/US/Canada tax packs
- Add duplicate detection, bulk preview
- Semantic search UI
- Marketing ramp-up (content marketing, SEO, paid ads)
- **Milestone**: 5,000 users, 250 paying ($25K MRR)
- **Decision Point Month 18**: If General user conversion <5%, pivot to Legal-only

**Month 19-24: Enterprise Features & Profitability**
- Team features (shared rules, collaborative packs)
- API access for integrations
- Linux support
- Enterprise tier launch
- **Milestone**: 10K users, 800 paying ($80K MRR), approaching break-even

**Year 3+: Scale to 100K Users**
- Community features (rule sharing, public templates)
- Mobile companion app (iOS/Android view-only)
- Expand country coverage (more tax/immigration templates)
- **Milestone**: 100K users, 8K paying ($1.92M ARR), $1.22M profit

---

## 10. GO-TO-MARKET STRATEGY

### 10.1 Customer Acquisition Channels

**Primary Channel (Months 1-12)**: Content Marketing (CAC $30-$50)
- **SEO Blog**:
  - "How to organize files for tax (Uber driver guide)"
  - "Australia partner visa evidence checklist 2025"
  - "Legal evidence timeline template (solo practitioners)"
  - "Sparkle alternative for Windows users"
- **YouTube Tutorials**:
  - "Organize 10,000 files in 10 minutes with AI"
  - "Prepare BAS pack for accountant (rideshare driver)"
  - "Create court-ready timeline from case files"
- **Reddit/HN**:
  - Launch posts: r/productivity, r/freelance, r/LegalAdvice, r/ImmigrationLaw, Hacker News
  - Monthly updates: "We shipped X feature based on your feedback"

**Secondary Channel (Months 6-18)**: Partnerships (CAC $50-$100)
- **Legal Aid Organizations**: Offer free licenses for self-represented litigants
- **Accountant Networks**: "Recommend FileOrganizer to your sole trader clients, we'll give you 20% commission"
- **Immigration Consultants**: Partner to provide organized evidence packs

**Tertiary Channel (Months 12+)**: Paid Ads (CAC $100-$200)
- **Google Ads**: "File organizer", "Tax organizer", "Legal timeline software"
- **LinkedIn Ads**: Target solo legal practitioners, accountants, immigration consultants

### 10.2 Pricing & Conversion Funnel

**Free Tier → Pro Tier** (5-8% conversion):
- Triggers:
  - Hit 1,000 files/month limit (show upgrade prompt)
  - Try to use cloud OCR (Pro feature, show paywall)
  - Try to create pack (show pack wizard, offer Pro trial)
- **Conversion Tactics**:
  - 14-day Pro trial (no credit card required)
  - "Upgrade now, get 20% off first year"
  - Email drip campaign (value education, case studies)

**Pro Tier → Business Tier** (30-40% conversion for pack users):
- Triggers:
  - User creates first pack (show Business tier benefits)
  - User exports pack (show "Business tier includes advanced exports")
- **Conversion Tactics**:
  - "Start legal timeline pack" → Show comparison: Pro (basic exports) vs Business (court-ready chronologies)
  - "Start tax pack" → Show comparison: Pro (generic) vs Business (country-specific BAS templates)

### 10.3 Retention & Churn Mitigation

**Retention Tactics**:
- **Quarterly reminders**: "It's end of Q2—create a BAS pack now?"
- **Annual tax prep**: "Tax season is here—organize your 2024 docs with one click"
- **Immigration application deadlines**: "Your partner visa application is due in 30 days—check your evidence pack"

**Churn Mitigation**:
- Exit survey: "Why are you canceling?" (learn pain points)
- Win-back offer: "Come back for 50% off next 3 months"
- Reactivation campaign: "We shipped [feature you requested]—give us another try"

---

## 11. SUCCESS METRICS & DECISION FRAMEWORKS

### 11.1 Success Metrics by Timeframe

**Month 3** (MVP Alpha):
- 50 alpha testers recruited
- 80%+ usability score (SUS survey)
- <5 critical bugs (data loss, crashes)
- **Validates**: Product is stable and usable

**Month 6** (MVP Launch):
- 1,000 users (500 free, 500 trialing Pro)
- 50 paying users (5% conversion)
- $5K MRR ($108K annual run rate)
- 90%+ categorization accuracy (user feedback)
- **Validates**: Product-market fit for General users
- **Decision Point**: If conversion <5%, consider pivot to Legal-only

**Month 12** (Market Validation):
- 5,000 users (2,500 free, 2,000 Pro, 500 Business)
- 250 paying users (5% overall conversion)
- $25K MRR ($300K ARR)
- 15-20% churn (acceptable for Year 1)
- **Validates**: Pricing and unit economics
- **Decision Point**: If churn >25%, investigate product quality or segment mismatch

**Month 18** (Scale):
- 10,000 users
- 800 paying users (8% conversion)
- $80K MRR ($960K ARR)
- Approaching break-even (5,000-8,000 paying users needed)
- **Validates**: Path to profitability
- **Decision Point**: If not approaching break-even, scope down features or raise funding

**Year 3** (Profitability):
- 100,000 users
- 8,000 paying users (8% conversion)
- $1.92M ARR
- $1.22M profit (63% margin)
- **Validates**: Sustainable, profitable business

### 11.2 Pivot Triggers

**When to Pivot from General to Legal-Only**:
- Month 6: If General user conversion <5% (vs 30-40% for legal pack users)
- Month 12: If General user churn >25% (vs <15% for Business tier)
- Action: Focus all marketing on legal professionals, raise Business tier to $99/mo, discontinue free tier

**When to Pivot from Local-First to Cloud-First**:
- Month 12: If >60% of users prefer cloud OCR/LLM despite privacy concerns
- Month 18: If local LLM accuracy consistently <70% (vs cloud LLM 90%+)
- Action: Offer cloud-only tier at lower price ($5/mo), keep local-first for privacy-conscious users

**When to Shut Down**:
- Month 18: If <2,000 paying users (vs target 5,000 for break-even)
- Month 24: If still not profitable and unable to raise funding
- Action: Offer refunds, open-source codebase, graceful shutdown

### 11.3 Competitive Response Triggers

**If Sparkle Adds Cross-Platform** (expected Month 12-18):
- **Response**: Double down on scenario packs (tax/immigration/legal) that Sparkle won't have
- **Marketing**: Position as "Sparkle for file cleanup, FileOrganizer for life admin and legal work"

**If Open-Source Fork Adds Legal Features** (expected Month 18-24):
- **Response**: Emphasize polish, UX, support, and country-specific templates
- **Marketing**: "FileOrganizer is the polished, supported, user-friendly version"

**If ChronoVault Lowers Prices** (expected Month 24+):
- **Response**: Maintain pricing, emphasize local-first privacy and solo practitioner focus
- **Marketing**: "ChronoVault is for big law firms, FileOrganizer is for solo practitioners and self-represented litigants"

---

## 12. NEXT STEPS FOR AUTOPACK / CURSOR

### 12.1 Immediate Actions (Planning Phase)

**Action 1: Research Brief for Cursor** (Priority: CRITICAL)
- **File**: `cursor_research_brief_tax_immigration_legal_packs.md` (already provided by user)
- **Task**: Cursor researches tax/BAS, immigration, legal pack formats for AU/UK/US/CA
- **Deliverables**:
  1. `docs/research/research_report_tax_immigration_legal_packs.md`
  2. `docs/research/implementation_plan_tax_immigration_legal_packs.md`
- **Timeline**: 3-5 days (Cursor autonomous research)

**Action 2: Validate Business Analysis with GPT**
- **File**: `MARKET_RESEARCH_RIGOROUS_V2.md` + `GPT_STRATEGIC_ANALYSIS_PROMPT_V2.md`
- **Task**: Send to GPT for GO/NO-GO validation, segment prioritization, competitive moat strengthening
- **Timeline**: 1-2 hours (GPT analysis)
- **Expected Output**: Confirmation of 6.6/10 CONDITIONAL GO or revised recommendation

**Action 3: Define Pack Configuration Schema**
- **File**: Create `docs/architecture/pack_configuration_schema.md`
- **Task**: Based on Cursor research + GPT validation, define JSON/YAML schema for pack templates
- **Timeline**: 1-2 days

**Action 4: Create Initial Pack Templates**
- **Files**:
  - `packs/templates/generic_tax_pack.yaml`
  - `packs/templates/generic_immigration_pack.yaml`
  - `packs/templates/legal_timeline_pack.yaml`
- **Task**: Implement MVP pack templates (not country-specific)
- **Timeline**: 2-3 days

### 12.2 Phase 1 Build Plan (Months 1-9)

**Autopack Execution**:
1. Load this master plan (`MASTER_BUILD_PLAN_FILEORGANIZER.md`)
2. Load pack implementation plan from Cursor research
3. Generate detailed 30-40 phase build plan
4. Begin autonomous build:
   - Builder agent: Implement phases
   - Auditor agent: Review code, test, validate
   - Tracker: Update progress in `MANUAL_TRACKING.md`
5. Monthly check-ins: Review progress, adjust plan if needed

**Human Oversight**:
- Week 2: Review architecture (database schema, tech stack)
- Week 4: Review Tier 1 deliverables (core infrastructure)
- Week 8: Review AI processing (OCR, LLM integration)
- Week 12: Review organization engine (rules, staging)
- Week 16: Review UI/UX (triage board, command palette)
- Week 20: Review scenario packs (generic templates)
- Week 24: Beta testing (recruit 50 users)
- Week 36: Public launch

### 12.3 Critical Dependencies

**Before Starting Build**:
1. ✅ Cursor research report (tax/immigration/legal packs)
2. ✅ GPT business validation (GO/NO-GO confirmed)
3. ✅ Pack configuration schema defined
4. ⚠️ Capital secured ($200K-$300K for 9-month build + marketing)

**During Build (Phase Dependencies)**:
- Tier 2 (AI Processing) depends on Tier 1 (Core Infrastructure)
- Tier 3 (Organization Logic) depends on Tier 2 (AI Processing)
- Tier 4 (UI/UX) can partially overlap with Tier 3
- Tier 5 (Scenario Packs) depends on Tier 3 (Organization Logic)
- Tier 6 (Testing) depends on all previous tiers

---

## 13. CONCLUSION

### 13.1 Summary of Strategic Pivot

**OLD Plan** (Before Rigorous Business Analysis):
- Legal-only niche product
- Privacy-first for all users
- $49-$99 one-time purchase or $20/mo subscription
- Target: 5M legal professionals
- Weak differentiation vs ChronoVault/Casefleet

**NEW Plan** (After Rigorous Business Analysis):
- **General-purpose file organizer** (200M market) WITH legal/tax/immigration **scenario packs** as premium upsell
- **Multi-tier pricing**: Free (mass market) → Pro $10/mo (power users) → Business $50/mo (legal/tax professionals)
- **Strategic focus**: Nail 10x content understanding (90%+ accuracy), execute fast (12-18 months), build data moat
- **Segment priority**: Start with General users (freemium), upsell Legal/Tax users (high ARPU)
- **Strong differentiation**: Content understanding + scenario packs + cross-platform + rules engine

### 13.2 Why This Will Succeed (If Executed Well)

1. **Large Market** ($13.7B, 17.9% CAGR)
2. **Strong Unit Economics** (LTV/CAC = 6.4, payback 5 months)
3. **Clear Pain Points** (Sparkle Mac-only, legal tools expensive, no scenario packs exist)
4. **Moderate Switching Likelihood** (40-50% from Sparkle, 30-40% from legal tools)
5. **Proven Tech Stack** (Tauri, Tesseract, Qwen2-7B benchmarked)
6. **Unique Value Prop** (content understanding + scenario packs + cross-platform + privacy)

### 13.3 Why This Might Fail (Risk Awareness)

1. **Weak Competitive Moat** (12-24 month lead, easily replicable)
2. **Differentiation Unclear** (is content understanding truly 10x better?)
3. **Execution Risk** (50 phases in 6-9 months aggressive)
4. **General User Conversion Uncertain** (5-8% conversion assumption untested)
5. **High Capital Requirement** ($400K-$600K with 18-24 month payback)

### 13.4 Final Decision: CONDITIONAL GO

**Recommendation**: **GO** with the following conditions:
1. **Validate 10x differentiation** in Month 3 alpha (90%+ categorization accuracy)
2. **Monitor General user conversion** at Month 6 (if <5%, pivot to Legal-only)
3. **Execute fast** (ship MVP in 6-9 months, not 12)
4. **Build data moat** (user corrections → improve models)
5. **Prepare contingency** (pivot triggers, scope-down options if funding tight)

**If conditions met**: Potential for $12M ARR by Year 5, $7.8M profit, sustainable business

**If conditions NOT met**: Graceful pivot to Legal-only or shutdown with lessons learned

---

## 14. v1.0 SCOPE DISCIPLINE & PHASING

### 14.1 Segment Focus for v1.0

**CRITICAL: v1.0 launches to GENERAL USERS ONLY, not specialists**

```
┌──────────────────────────────────────────────────────────┐
│ v1.0 TARGET SEGMENT (9-13 weeks)                         │
│ • General users (freelancers, sole traders, consumers)   │
│ • Windows/Mac cross-platform                             │
│ • Generic packs ONLY (no country-specific)               │
│ • 3 pack templates: tax_generic, immigration_generic,    │
│   legal_timeline_generic                                 │
│ • Success metric: 50-100 monthly actives, 5-10 paying   │
└──────────────────────────────────────────────────────────┘
```

**What v1.0 IS**:
- General-purpose file organizer with AI classification
- Generic tax pack (income/expense categories, no country forms)
- Generic immigration pack (relationship evidence, no visa-specific)
- Generic legal timeline (event extraction, basic exports)
- Cross-platform (Windows/Mac)
- Privacy-first (local-first processing)

**What v1.0 IS NOT** (deferred to Phase 2+):
- ❌ Country-specific pack templates (AU BAS, UK Self Assessment)
- ❌ Visa-specific templates (AU Partner 820/801, UK Spouse)
- ❌ Profession templates (rideshare driver, cleaner)
- ❌ Tax form field mappings (BAS G1, 1040 Schedule C)
- ❌ Immigration Premium Service (template updates, subscriptions)
- ❌ Advanced exports (PPT, complex PDF layouts)
- ❌ Team features, API access, Enterprise tier

### 14.2 Phase Roadmap (Revised)

#### **v1.0 (Weeks 0-13): Generic Packs for General Users**

**Scope**: [MASTER_BUILD_PLAN_FILEORGANIZER.md](MASTER_BUILD_PLAN_FILEORGANIZER.md) Tiers 1-5 (Phases 1-38)
- Core infrastructure (scanner, DB, OCR, LLM)
- Organization engine (rules, staging, triage)
- UI/UX (command palette, triage board)
- **3 generic pack templates**:
  - `tax_generic_v1.yaml`: Income, expenses, deductions (no country forms)
  - `immigration_generic_relationship_v1.yaml`: Identity, financial, relationship (no visa-specific)
  - `legal_generic_timeline_v1.yaml`: Event extraction, chronology exports

**Development Approach**: **Parallel Backend + UI Development**
- **Autopack builds everything** (backend + minimal functional UI)
- **Parallel development**: UI built alongside backend (Week 1-9)
- **Minimal functional UI**: Functional but not polished (polish in Phase 2)
- **Key screens**: Home, Pack Selection, Triage Board, Export Dialog, Settings
- **Tech stack**: Electron + React + TypeScript + shadcn/ui + Zustand + Tailwind
- **Detailed plan**: See [FILEORGANIZER_V1_IMPLEMENTATION_PLAN.md](FILEORGANIZER_V1_IMPLEMENTATION_PLAN.md)

**Success Criteria**:
- 50-100 monthly active users
- 5-10 paying users ($50-$100 MRR)
- Qualitative feedback: "FileOrganizer is useful, I want more features"
- 80%+ categorization accuracy (user validation)

**Pre-Launch Gate**: Legal Review
- Lawyer reviews all disclaimers, terms of service
- Validates generic pack disclaimers ("not legal/tax advice")
- Signs off on user data handling (privacy policy)

#### **Phase 2 (Weeks 14-21): Country-Specific Packs**

**Trigger**: v1.0 success criteria met + user demand for country templates

**Scope**:
- **AU BAS Pack** (rideshare driver profession):
  - Income/expense categories per ATO guidance
  - BAS field mappings (G1, 1A, 1B, G11)
  - Accountant-ready exports (Excel + categorized PDFs)
- **AU Partner Visa Pack** (820/801):
  - 4 pillars (financial, household, social, commitment)
  - Portal upload structure (ImmiAccount)
  - Expert verification (MARA agent review)
- **UK Spouse Visa Pack**:
  - Evidence categories per UKVI guidance
  - Financial requirement calculations
  - Expert verification (OISC advisor review)

**Success Criteria**:
- 200-300 monthly actives
- 20-30 paying users ($200-$300 MRR)
- Country pack adoption: 30%+ of pack users choose country-specific

#### **Phase 2.5 (Weeks 22-29): Immigration Premium Service**

**Trigger**: Phase 2 success + AU/UK pack validation complete

**Scope**:
- Template update server (REST API, JWT auth, signed YAMLs)
- Subscription backend (Stripe/Paddle integration)
- Expert network (MARA, OISC, RCIC agents)
- Quarterly template updates (AU/UK high volatility)

**Pricing**:
- Free: Static templates (no updates)
- Single Country: $9.99/month (quarterly updates)
- All Countries: $19.99/month (quarterly updates, all 5 countries)
- One-Time: $39 (12-month updates, single country)

**Success Criteria**:
- 10-15% of immigration pack users convert to Premium
- Expert network recruited (2-3 agents per country)
- Template updates delivered on schedule (Q1, Q2, Q3, Q4)

#### **Phase 3+ (Month 7+): Advanced Features**

**Scope**:
- More country packs (US, Canada, NZ tax/immigration)
- Advanced exports (PPT, custom PDF layouts)
- Duplicate detection (content hash, semantic)
- Semantic search UI (Q&A, entity views)
- Team features (shared rules, collaborative packs)
- Enterprise tier

### 14.3 Success Metrics by Phase

**v1.0 Success Metrics**:
- Monthly Active Users: 50-100
- Paying Users: 5-10 ($50-$100 MRR)
- Categorization Accuracy: 80%+ (user validation)
- Qualitative: "I want more features" (not "this is useless")
- NPS: >30 (acceptable for v1.0)

**Phase 2 Success Metrics**:
- Monthly Active Users: 200-300
- Paying Users: 20-30 ($200-$300 MRR)
- Country Pack Adoption: 30%+ of pack users
- Categorization Accuracy: 85%+ (improving with data)
- NPS: >40

**Phase 2.5 Success Metrics**:
- Premium Conversion: 10-15% of immigration pack users
- Premium MRR: $100-$150 (10-15 users × $10-$15 avg)
- Template Update SLA: 100% on-time (quarterly reviews)
- Expert NPS: >50 (agents happy with process)

**Phase 3+ Success Metrics**:
- Monthly Active Users: 500-1,000
- Paying Users: 50-100 ($500-$1,000 MRR)
- LTV/CAC: >3.0 (validating unit economics)
- Churn: <20% annually (retention improving)

---

**This master plan is the authoritative blueprint for FileOrganizer. All implementation decisions should align with this vision.**

**Last Updated**: 2025-11-27
**Next Review**: After Cursor research report + GPT business validation
