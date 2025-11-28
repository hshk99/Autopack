# Reference: User Requirements & Lessons from Prior Implementation

**Compiled by**: Claude (Autopack)
**Date**: 2025-11-26
**Purpose**: User needs + lessons learned from FILE_ORGANIZER project

---

## Part 1: User Requirements

### Core Problem Statement

Build a desktop application that can:
1. **Automatically create/organize** files and folder structures
2. **Rename files** according to user's need (contextual, not literal)
3. **Allocate files** into folders based on user's purpose
4. **Understand context** by reading file contents
5. **Adapt to use case** (legal, personal, business, etc.)

### Key Use Case: Legal Case Management

**Reference Implementation**: `C:\Users\hshk9\OneDrive\Personal\CASE_BUNDLE_v5`

**Legal Case Organization Pattern**:
```
CASE_BUNDLE_v5/
├── 0_INDEX_SUMMARY/
│   ├── A1_CASE_OVERVIEW.txt
│   ├── A2_EVIDENCE_INDEX.xlsx
│   └── A3_CASE_SUMMARY.docx
├── 1_INCIDENT/
│   ├── A1_ed-triage-correction_02.04.2025.pdf
│   ├── A2_chat-boss-told-to-lie_02.04.2025.png
│   ├── A3_site-fall-photos_02.04.2025.jpg
│   └── A4_incident-note_02.04.2025.txt
├── 2_EMPLOYMENT/
│   ├── B1_roster-no-supervisor_02.04.2025.pdf
│   └── B2_sps-extract_..._....pdf
├── 3_MEDICAL/
│   ├── C1_gp-specialist-reports_...pdf
│   └── C2_psychology-referral_...pdf
├── 4_CERTIFICATES/
│   └── D1_certificates-of-capacity_...pdf
├── 5_INSURER/
│   ├── E1_approvals-declines_...pdf
│   └── E2_piawe-stepdown_...pdf
├── 6_EMPLOYMENT_POST/
│   ├── F1_termination-letter_...pdf
│   └── F2_rtw-plan_...pdf
└── 7_FINANCIAL/
    ├── G1_payslips-csv_...csv
    └── G2_weekly-payment-schedule_...pdf
```

**File Naming Pattern**: `[Evidence_ID]_[contextual-description]_[dd.mm.yyyy].[ext]`

**Critical Insight**:
> JPG files containing text messages between user and "Jaden" need descriptions like "chat-boss-told-to-lie" (context) NOT "text message conversation" (literal).

**Why Context Matters**:
- For legal case: Files are EVIDENCE (need strategic descriptions)
- For personal use: Files are MEMORIES (need emotional/event descriptions)
- For business: Files are RECORDS (need compliance/audit descriptions)

### Cross-Platform Requirements

**Platforms**: Windows, macOS, (Linux if feasible)

**Justification**: User mentioned "either windows or mac os (if you can think of other popular operating systems other than these two please suggest)"

### Accessibility Requirements

**Target User**: Elderly/non-technical users

**Problem Statement**:
> "Because if user had to input prompt precisely what they want would be bit difficult for older people users when typing is difficult."

**Solution Approach**:
- Dropdown menus for use case selection
- Button-based navigation (not text input)
- Wizard-style flow (one question at a time)
- Avoid overly complicated prompts

### Privacy Requirements

**Sensitivity**: Legal cases often contain:
- Medical records
- Employment disputes
- Personal communications
- Financial information

**Implication**: Local-first processing preferred (cloud opt-in only)

---

## Part 2: Specific Features Required

### Feature 1: Content Understanding (Not Just Metadata)

**Requirement**: Read file contents to understand context

**Example**:
- Text message screenshot (JPG)
- User: "Jaden"
- Boss: "Tell worker to report as off-duty injury"
- **AI Must Understand**: This is evidence of employer misconduct
- **Rename to**: `A2_chat-boss-told-to-lie_02.04.2025.png`
- **NOT**: `text-message_02.04.2025.png`

**Technologies Needed**:
- OCR for images (Tesseract, cloud OCR, or LLM vision)
- Text extraction from PDFs
- NLP for context understanding

### Feature 2: Timeline Awareness

**Requirement**: Timestamps matter for legal cases

**From user**:
> "Also, the time stamp on each files in this case is useful as it sort of shows the timeline of each events, incidents, etc."

**Implementation**:
- Extract dates from document content (OCR + NLP)
- Fall back to file modification date if no embedded date
- Sort evidence chronologically
- Generate timeline view (for legal cases)

### Feature 3: Use Case Adaptation

**User's Words**:
> "if it's for a legal case, for example, it should organize the files in evidence based way. if it's for personal usage, the files and folders should be organize to fit the purpose of that personal preference."

**Adaptations Needed**:

| Use Case | Folder Structure | Naming Pattern | Summary Type |
|----------|------------------|----------------|--------------|
| Legal Case | By evidence type (Incident, Medical, Employment) | `[ID]_[context]_[date]` | Case narrative with timeline |
| Personal Archive | By event/year (Trips, Family, Projects) | `[event]-[location]_[date]` | Memory summaries |
| Business Docs | By client/project/fiscal period | `[client]-[doctype]_[period]` | Compliance/audit log |

### Feature 4: Context-Aware Descriptions

**User's Requirement**:
> "the description in the summary should reflect the context, and user's need instead of the literal meaning of each files contents."

**Example**:
- **Bad** (literal): "JPG image containing text messages dated April 2, 2025"
- **Good** (contextual): "Text message evidence showing boss instructing worker to misreport injury as off-duty"

**For Legal Case**:
- Focus on evidentiary value
- Identify parties, dates, key facts
- Explain relevance to case

**For Personal Archive**:
- Focus on emotional significance
- Identify who, when, what memory
- Explain why it matters

### Feature 5: Smart Categorization

**User's Concern**:
> "we could potentially implement the dropdown bars or selection buttons to narrow down to what they want but for this we would have to brainstorm every possible senario how each user might want their file system to be organised"

**Hybrid Approach Needed**:
1. **Preset Templates**: Legal case, Personal archive, Business docs
2. **AI Detection**: Analyze files, suggest categories
3. **User Refinement**: Dropdowns to adjust AI suggestions
4. **Learn from Corrections**: Remember user preferences

### Feature 6: Efficient Processing

**User's Concern**:
> "this seems like a lot of token usage and might not be as efficient"

**Optimization Needed**:
- Don't re-analyze every file individually (batch)
- Build summary of file set first
- Then contextualize within summary
- Avoid redundant LLM calls

---

## Part 3: Lessons Learned from Prior Implementation

**Source**: `C:\Users\hshk9\OneDrive\Personal\FILE_ORGANIZER\CURRENT_LIMITATIONS_AND_IMPROVEMENTS.md`

### Critical Failure 1: Lack of Holistic Review

**What Happened**: AI performed operations without analyzing full structure first

**Result**:
- Duplicate headings in consolidated documents
- Categorization errors (Uber receipts under "ED reports")
- Pattern breaks after renaming

**Fix Required**:
```
Multi-Pass Architecture:
1. Discovery: Scan ALL files, build structure map
2. Analysis: Detect patterns, duplicates, relationships
3. Proposal: Generate organization plan
4. User Review: MANDATORY checkpoint
5. Execution: Apply changes
6. Validation: Check integrity
```

### Critical Failure 2: Semantic Understanding Gaps

**What Happened**: Files named literally instead of contextually

**Example**:
- Named: `README_FOR_GREG.txt`
- Content: Case overview narrative
- Should be: `CASE_OVERVIEW.txt`

**Root Cause**: AI accepted naming without questioning semantic fit

**Fix Required**:
- After generating filename, ask: "Does this name match content purpose?"
- Validate: Overview vs Index vs Summary vs Narrative
- Challenge requirements if nonsensical

### Critical Failure 3: Category Logic Errors

**What Happened**: Uber receipts placed under "Emergency Department reports"

**Why**: AI grouped chronologically (took Uber TO ED) not categorically (transport evidence)

**Fix Required**:
```python
# Explicit category definitions
CATEGORIES = {
    'Medical': ['doctor', 'hospital', 'prescription', 'medical report'],
    'Transport': ['uber', 'taxi', 'mileage', 'parking', 'transport'],
    'Employment': ['timesheet', 'contract', 'payslip', 'employment'],
    'Incident': ['photo', 'witness', 'accident report', 'incident']
}

# Rule: Categorize by TYPE, not chronology
```

### Critical Failure 4: Incomplete Cross-Reference Updates

**What Happened**: Renamed files but missed:
- Internal document references
- Evidence ID prefixes removed
- Orphaned index entries

**Fix Required**:
```
After any rename:
1. Build dependency graph (what references what)
2. Update ALL cross-references automatically
3. Validate pattern conformity (e.g., Evidence_ID prefix)
4. Check for orphaned index entries
5. Generate change log for rollback
```

### Critical Failure 5: Duplicate Detection Gaps

**What Happened**: Merged documents still had duplicate sections

**Fix Required**:
```
When consolidating documents:
1. Extract ALL headings from both docs
2. Create structural maps (hierarchy)
3. Identify overlapping sections
4. Merge intelligently (not concatenate):
   - Identical sections → keep one
   - Different details → consolidate
5. Final scan for duplicate headings
```

### Critical Failure 6: Over-Detailed Communication

**What Happened**: Generated verbose summaries repeating information already in files

**Fix Required**:
- Don't repeat what's in detailed docs
- Point to existing documentation
- Keep communications concise and actionable

### Critical Failure 7: Pattern Conformity Blind Spots

**What Happened**: Renamed files but broke naming pattern (removed Evidence IDs)

**Fix Required**:
```python
class NamingPatternValidator:
    pattern = r"^[A-Z]\d+_[a-z_-]+_\d{2}\.\d{2}\.\d{4}\.[a-z]+$"

    def validate_after_rename(self, files):
        for file in files:
            if not re.match(self.pattern, file):
                raise PatternViolation(f"{file} doesn't match pattern")
```

### Critical Failure 8: No Preview for Bulk Operations

**What Happened**: Renamed 34 files without showing user impact first

**Fix Required**:
```
Before bulk operation:
1. Count affected files
2. Show preview: "Will rename 34 files: file-name.pdf → file_name.pdf"
3. Ask user: "Proceed? (y/n)"
4. Create rollback log
5. Execute
6. Report: "Successfully renamed 34 files"
```

### Critical Failure 9: Unicode Handling (Windows)

**What Happened**: Used unicode checkmarks (✓) that broke Windows console

**Fix Required**:
```python
# ASCII-safe output
SYMBOLS = {
    'success': '[OK]',   # not ✓
    'error': '[ERROR]',  # not ❌
    'arrow': '->',       # not →
}
```

---

## Part 4: User's Existing Organization Rules

**Source**: `C:\Users\hshk9\OneDrive\Personal\FILE_ORGANIZER\00_POLICY\`

### Evidence Taxonomy (Legal Case)

**Categories**:
- A: Incident Evidence
- B: Employment Evidence
- C: Medical Evidence
- D: Certificates
- E: Insurer Correspondence
- F: Post-Employment
- G: Financial

**Inclusion Rules**:
- Include: A*, B1, C*, D1, E*, F*, G*
- Exclude: CT images, Sleep study, Expense receipts, Generic admin scans

**File Types**: .png, .jpg, .jpeg, .heic, .pdf, .txt, .csv

### Renaming Rules

**Pattern**: `<ID>_<short-slug>_<dd.mm.yyyy>.<ext>`

**Date Source**:
1. Embedded text (if reliable)
2. File modified date (fallback)

**Slug Rules**:
- kebab-case
- 3-6 words max
- Contextual, not literal

**Examples**:
- `A2_chat-boss-told-to-lie_02.04.2025.png`
- `B1_roster-02apr-no-supervisor_02.04.2025.png`
- `D1_certificate-of-capacity_02.10.2025.pdf`

### Case Context

**Brief**:
> "Ladder fall 02/04/2025. Two apprentices only. No licensed supervisor on site. Boss told apprentice to tell worker to report injury as off-duty. Day1 ED triage notes reflect off-duty; Day2 corrected to work-related. Surgery 15/09/2025; ongoing capacity limits. Insurer delays on psychology (referral 21/07; approval 05/11). Employer terminated July with backdating issue. PIAWE step-down then increased to $971 from 01/10/2025."

**This Context Drives**:
- File categorization (incident vs medical vs employment)
- Renaming (evidence of misconduct vs simple correspondence)
- Summary generation (legal strategy narrative)

---

## Part 5: Key Architectural Principles

### Principle 1: Explicit > Implicit

**Rule**: Define all rules explicitly, don't rely on AI "figuring it out"

**Example**:
```python
# Bad (implicit)
categorize_files(files)  # How does it know categories?

# Good (explicit)
LEGAL_CATEGORIES = {
    'Incident': {'keywords': ['fall', 'accident', 'injury', 'incident']},
    'Medical': {'keywords': ['doctor', 'hospital', 'treatment', 'medical']},
    'Employment': {'keywords': ['roster', 'timesheet', 'employment', 'work']}
}
categorize_files(files, categories=LEGAL_CATEGORIES, use_case='legal')
```

### Principle 2: Validate Early, Validate Often

**Rule**: After every operation, validate before proceeding

**Checkpoints**:
- After scan: Validate all files found
- After categorization: Validate category assignments
- After renaming: Validate pattern conformity
- After moving: Validate no broken references
- Before finalizing: Validate end-to-end

### Principle 3: Human Checkpoints are Mandatory

**Rule**: Never assume AI output is perfect

**Required Checkpoints**:
1. After Discovery: "Found 150 files. Is this correct?"
2. After Categorization: "Proposed organization [preview]. Approve?"
3. After Renaming: "Will rename [examples]. Proceed?"
4. Before Finalize: "Review final structure. Confirm?"

### Principle 4: Rollback Capability

**Rule**: Every change must be reversible

**Implementation**:
```python
class OperationLog:
    def log_rename(self, old, new):
        self.changes.append({'op': 'rename', 'old': old, 'new': new})

    def rollback(self):
        for change in reversed(self.changes):
            if change['op'] == 'rename':
                os.rename(change['new'], change['old'])
```

### Principle 5: Semantic > Technical Correctness

**Rule**: "Does this make sense?" > "Does this execute without errors?"

**Example**:
- Technical: File renamed successfully ✓
- Semantic: But does the name match the content? Did we break the pattern?

---

## Part 6: Requirements Summary

### Must-Have (Phase 1)

1. **Multi-pass analysis** (Discovery → Analysis → Review → Execution)
2. **OCR for images** (screenshots of text messages, documents)
3. **Context understanding** (not literal descriptions)
4. **Use case detection** (legal vs personal vs business)
5. **Context-aware renaming** (based on content + use case)
6. **Folder structure generation** (adaptive to use case)
7. **Index/summary generation** (Excel + Text + Word)
8. **Timeline extraction** (for legal cases)
9. **Cross-reference validation** (no broken links)
10. **Rollback capability** (undo changes)
11. **Human checkpoints** (review before apply)
12. **Cross-platform** (Windows + macOS minimum)

### Should-Have (Phase 1 or 2)

1. **Duplicate detection** (same content, different names)
2. **Bulk operation preview** (show impact before execution)
3. **Learning from corrections** (remember user preferences)
4. **Confidence scores** (flag low-confidence classifications)

### Nice-to-Have (Phase 2+)

1. **Semantic search** (across organized files)
2. **Continuous monitoring** (auto-organize new files)
3. **Cloud storage integration** (Dropbox, OneDrive)
4. **Mobile companion app**

---

**End of User Requirements & Lessons**
