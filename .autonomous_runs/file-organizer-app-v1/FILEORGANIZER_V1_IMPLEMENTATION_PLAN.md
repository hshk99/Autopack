# FileOrganizer v1.0 Implementation Plan: Parallel Backend + UI Development

**Date**: 2025-11-28
**Approach**: **Autopack builds EVERYTHING** (backend + minimal functional UI in parallel)
**Timeline**: 9-13 weeks
**Developer**: Autopack (autonomous, minimal human intervention)

---

## Executive Summary

**Key Decision**: Build **backend + minimal functional UI in parallel** to:
1. **Reduce risk**: Validate UX early (Week 2-3) before backend is locked in
2. **Faster feedback**: Test with real workflows by Week 4-5
3. **Better architecture**: Backend APIs shaped by actual UI needs
4. **Demoable progress**: Working prototype for user validation

**What "Minimal Functional UI" Means**:
- ✅ **Functional**: Core workflows work (import → triage → export)
- ✅ **Testable**: User can complete end-to-end tasks
- ❌ **NOT polished**: Basic styling, no animations, no themes
- ❌ **NOT feature-complete**: Skip nice-to-haves (drag-and-drop in v1.0, add in Phase 2)

**Division of Work**:
- **Autopack builds**: Backend (100%) + UI (100%)
- **User provides**: Feedback on demos, clarifications on requirements
- **Human intervention**: Minimal (only when Autopack asks for clarification)

---

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Database**: SQLite (with optional PostgreSQL for production)
- **OCR**: Tesseract OCR + PyMuPDF (PDF text extraction)
- **LLM**: OpenAI GPT-4 (via litellm for model abstraction)
- **Embeddings**: OpenAI text-embedding-3-small (for semantic search)
- **File Processing**: Pillow, PyMuPDF, python-docx, openpyxl
- **Export**: ReportLab (PDF), openpyxl (Excel), csv (CSV)

### Frontend (Minimal Functional UI)
- **Framework**: Electron 28+ (cross-platform desktop app)
- **UI Library**: React 18+ with TypeScript
- **Component Library**: **shadcn/ui** (headless, customizable, modern)
  - Rationale: Lightweight, TypeScript-native, copy-paste components (no npm bloat)
  - Components needed: Button, Dialog, Table, Select, Input, Card
- **State Management**: Zustand (lightweight, simple API)
  - Rationale: No Redux boilerplate, perfect for small-to-medium apps
- **Styling**: Tailwind CSS (utility-first, fast iteration)
- **IPC**: Electron IPC (main ↔ renderer communication)
- **File Operations**: Node.js fs module + electron dialog API

### Architecture Pattern
- **Backend**: REST-like Python process (runs as subprocess from Electron main process)
- **Frontend**: Electron renderer process (React app)
- **Communication**: HTTP localhost API (backend exposes endpoints on `http://localhost:8765`)
- **Data Flow**:
  1. User action in React UI →
  2. Zustand action →
  3. Fetch API call to backend →
  4. Python backend processes →
  5. JSON response →
  6. Zustand state update →
  7. React re-renders

---

## Minimal Functional UI Specification

### Screen 1: Home / Dashboard
**Purpose**: Entry point, file import, recent packs

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  FileOrganizer                          [Settings] [Help] │
├──────────────────────────────────────────────────────────┤
│                                                           │
│         📁 Drop files here or click to browse            │
│                                                           │
│         [Select Folder] [Select Files]                   │
│                                                           │
│  Recent Packs:                                            │
│  - Tax Pack (Dec 2024) - 45 files                        │
│  - Immigration Evidence (Nov 2024) - 123 files           │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- File/folder picker (via Electron dialog API)
- Drag-and-drop file import
- List of recent packs (SQLite query)
- Click pack → Open triage board

**Skipped in v1.0**:
- ❌ Fancy animations
- ❌ Themes (light/dark mode)
- ❌ Onboarding tutorial

---

### Screen 2: Pack Selection
**Purpose**: Choose which scenario pack to use

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  Choose Pack Type                                         │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  ◉ Tax Pack (Generic)                                    │
│    Organize income, expenses, deductions                 │
│                                                           │
│  ○ Immigration Pack (Generic)                            │
│    Organize relationship evidence, identity docs         │
│                                                           │
│  ○ Legal Timeline Pack (Generic)                         │
│    Extract events, build chronology                      │
│                                                           │
│                         [Next] [Cancel]                   │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- Radio button selection (shadcn/ui RadioGroup)
- Load pack YAML from `~/.fileorganizer/templates/`
- Show pack description
- Next → Start processing files

**Skipped in v1.0**:
- ❌ Pack preview/details
- ❌ Custom pack creation UI

---

### Screen 3: Processing / Loading
**Purpose**: Show progress while backend processes files

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  Processing Files...                                      │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  [████████████░░░░░░░░] 65% (45/70 files)                │
│                                                           │
│  Current: invoice_2024_03.pdf                            │
│  Status: Extracting text via OCR...                      │
│                                                           │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- Progress bar (shadcn/ui Progress)
- Real-time updates via backend websocket or polling
- Show current file being processed
- Transition to Triage Board when done

**Skipped in v1.0**:
- ❌ Pause/resume processing
- ❌ Detailed logs (just basic status)

---

### Screen 4: Triage Board (CORE SCREEN)
**Purpose**: Review AI classifications, correct errors

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  Triage Board - Tax Pack                    [Export Pack]│
├──────────────────────────────────────────────────────────┤
│ Filter: [All] [Needs Review] [Approved]                  │
│ Sort: [Confidence ▼]                                      │
├──────────────────────────────────────────────────────────┤
│ File Name          │ Category       │ Confidence │ Action │
├────────────────────┼────────────────┼────────────┼────────┤
│ invoice_2024_03.pdf│ Income         │ 95%        │ [✓][✎] │
│ receipt_uber.jpg   │ Fuel Expenses  │ 78% ⚠️     │ [✓][✎] │
│ bank_statement.pdf │ (Uncategorized)│ 45% ⚠️     │ [✓][✎] │
│ tax_return_2023.pdf│ Deductions     │ 88%        │ [✓][✎] │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- **Table view** (shadcn/ui Table):
  - File name (click to preview)
  - AI-assigned category
  - Confidence score (⚠️ if <80%)
  - Actions: ✓ Approve, ✎ Edit category
- **Edit category**:
  - Click ✎ → Dropdown to change category (shadcn/ui Select)
  - Save → Backend updates DB
- **File preview** (right panel):
  - PDF thumbnail or text excerpt
  - Skip in v1.0: Full PDF viewer (just show first page as image)
- **Filters**:
  - All, Needs Review (<80%), Approved (user-confirmed)
- **Export button**:
  - Disabled until user reviews all "Needs Review" files

**Skipped in v1.0**:
- ❌ Drag-and-drop to reassign category (add in Phase 2)
- ❌ Bulk actions (select multiple files)
- ❌ Completeness checklist ("You're missing documents in X category")
- ❌ Keyboard shortcuts (Ctrl+E to edit)

---

### Screen 5: Export Dialog
**Purpose**: Choose export format and destination

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  Export Tax Pack                                          │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  Export Format:                                           │
│  ◉ Per-category PDFs + Index (Recommended)               │
│  ○ Excel Spreadsheet (Summary only)                      │
│  ○ CSV (Date, Category, Amount, Notes)                   │
│                                                           │
│  Destination:                                             │
│  📁 C:\Users\...\Documents\Tax_Pack_2024                 │
│                         [Browse]                          │
│                                                           │
│                    [Export] [Cancel]                      │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- Radio selection for export format
- Folder picker for destination
- Export button → Backend generates files
- Success notification → Open folder

**Skipped in v1.0**:
- ❌ Advanced export options (customize PDF layout)
- ❌ Preview export before generating

---

### Screen 6: Settings
**Purpose**: Configure API keys, OCR settings, model selection

**Layout**:
```
┌──────────────────────────────────────────────────────────┐
│  Settings                                                 │
├──────────────────────────────────────────────────────────┤
│                                                           │
│  LLM Configuration:                                       │
│  Model: [GPT-4 ▼]                                         │
│  API Key: [••••••••••••••] [Test Connection]             │
│                                                           │
│  OCR Settings:                                            │
│  Language: [English ▼]                                    │
│  ☑ Enable OCR for images                                 │
│                                                           │
│  Privacy:                                                 │
│  ☑ Process files locally (do not send to cloud)          │
│                                                           │
│                   [Save] [Cancel]                         │
│                                                           │
└──────────────────────────────────────────────────────────┘
```

**Functionality**:
- API key input (shadcn/ui Input with password type)
- Model dropdown (litellm supports multiple providers)
- Test connection button
- Save to config file (`~/.fileorganizer/config.json`)

**Skipped in v1.0**:
- ❌ Advanced settings (temperature, max tokens)
- ❌ Custom prompts for classification

---

## Week-by-Week Implementation Plan (9-13 Weeks)

### Week 1: Project Setup + Backend Foundation
**Autopack builds:**

**Backend** (Days 1-3):
- [x] Project scaffolding (Python virtual env, folder structure)
- [x] SQLite schema (documents, packs, categories, embeddings)
- [x] File scanner (recursive directory traversal, file type detection)
- [x] Document ingestion pipeline (PDF, images, DOCX, XLSX → text)
- [x] Basic REST API (`/api/scan`, `/api/documents`)

**Frontend** (Days 4-5):
- [x] Electron + React + TypeScript project setup
- [x] shadcn/ui integration (install Tailwind, configure components)
- [x] Zustand store setup (initial state: `files`, `currentPack`, `settings`)
- [x] Home screen UI (file picker, drag-and-drop)
- [x] IPC bridge (Electron main ↔ renderer ↔ Python backend)

**Deliverable**: User can drop folder → Backend scans files → UI shows list of files detected

---

### Week 2: OCR + Text Extraction + Pack Selection UI
**Autopack builds:**

**Backend** (Days 1-3):
- [x] Tesseract OCR integration (extract text from images/scanned PDFs)
- [x] PDF text extraction (PyMuPDF native text vs OCR fallback)
- [x] Document preprocessing (text cleaning, normalization)
- [x] YAML pack loader (read `tax_generic_v1.yaml`, parse schema)
- [x] API endpoint: `/api/packs/list`, `/api/packs/load`

**Frontend** (Days 4-5):
- [x] Pack Selection screen (radio buttons, pack descriptions)
- [x] Processing/Loading screen (progress bar, real-time updates)
- [x] API integration (fetch pack list, load pack)

**Deliverable**: User selects pack type → Backend loads YAML template → UI shows processing progress

---

### Week 3: LLM Classification + Embeddings
**Autopack builds:**

**Backend** (Days 1-4):
- [x] litellm integration (GPT-4 API wrapper)
- [x] Classification prompt engineering (few-shot examples, JSON output)
- [x] Category classifier (LLM assigns category + confidence score)
- [x] Embedding generation (OpenAI embeddings for semantic search)
- [x] Store results in SQLite (document_id, category, confidence, embedding)
- [x] API endpoint: `/api/classify`, `/api/documents/:id/category`

**Frontend** (Day 5):
- [x] Triage Board skeleton (table layout, no data yet)
- [x] Fetch classified documents from backend
- [x] Display in table (file name, category, confidence)

**Deliverable**: Backend classifies documents → UI shows results in Triage Board table

---

### Week 4: Triage Board Polish + Edit Functionality
**Autopack builds:**

**Backend** (Days 1-2):
- [x] Update category API: `PATCH /api/documents/:id/category`
- [x] User feedback loop (store corrections in `user_corrections` table)
- [x] Confidence scoring refinement (adjust based on user corrections)

**Frontend** (Days 3-5):
- [x] Edit category dropdown (shadcn/ui Select with pack categories)
- [x] Approve button (mark document as reviewed)
- [x] Filter by status (All, Needs Review, Approved)
- [x] Sort by confidence (ascending/descending)
- [x] File preview panel (PDF first page as image)
- [x] Zustand actions (updateCategory, approveDocument, setFilter)

**Deliverable**: User can review AI classifications → Edit wrong ones → Approve correct ones

---

### Week 5: Export Engine (Per-Category PDFs)
**Autopack builds:**

**Backend** (Days 1-4):
- [x] PDF bundle exporter (per-category PDFs with index)
  - Generate PDF for each category (ReportLab)
  - Index PDF with file list, page references
- [x] Excel exporter (spreadsheet with Date, Category, Amount, Notes)
- [x] CSV exporter (simple text format)
- [x] API endpoint: `POST /api/export` (format, destination)

**Frontend** (Day 5):
- [x] Export Dialog screen (format selection, folder picker)
- [x] Trigger export via API
- [x] Show success notification + open folder

**Deliverable**: User clicks Export → Backend generates files → User sees organized output

---

### Week 6: Pack System + 3 Generic Templates
**Autopack builds:**

**Backend** (Days 1-5):
- [x] Finalize YAML schema validation (JSON Schema)
- [x] Write 3 generic pack templates:
  1. `tax_generic_v1.yaml`: Income, Expenses, Deductions
  2. `immigration_generic_relationship_v1.yaml`: Identity, Financial, Relationship, Work/Study, Health, Character
  3. `legal_generic_timeline_v1.yaml`: Contracts, Correspondence, Court Docs, Evidence, Timeline Events
- [x] Pack versioning logic (semantic versioning, user instances frozen)
- [x] Test end-to-end with each pack

**Deliverable**: All 3 generic packs working (import → classify → triage → export)

---

### Week 7: Settings + Configuration + Error Handling
**Autopack builds:**

**Backend** (Days 1-3):
- [x] Config file management (`~/.fileorganizer/config.json`)
- [x] API key validation (test LLM connection)
- [x] Error handling (file read errors, API failures, OCR errors)
- [x] Logging (structured logs for debugging)

**Frontend** (Days 4-5):
- [x] Settings screen (API key, model selection, OCR language)
- [x] Test connection button (call `/api/test-connection`)
- [x] Error notifications (toast messages for failed operations)
- [x] Loading states (spinners, disabled buttons)

**Deliverable**: User can configure settings → Backend validates → Errors are gracefully handled

---

### Week 8: Polish + Bug Fixes + Testing
**Autopack builds:**

**Backend** (Days 1-3):
- [x] Performance optimization (batch processing, async operations)
- [x] Edge case handling (empty files, corrupted PDFs, unsupported formats)
- [x] Unit tests (classification accuracy, export correctness)

**Frontend** (Days 4-5):
- [x] UI polish (consistent spacing, colors, fonts)
- [x] Accessibility basics (keyboard navigation, focus states)
- [x] Cross-platform testing (Windows + Mac builds)

**Deliverable**: Stable v1.0 build with no critical bugs

---

### Week 9: User Testing + Iteration (Optional Buffer)
**Autopack builds:**

- [x] Alpha testing with 5-10 users (your network)
- [x] Collect feedback (what's confusing? what's broken?)
- [x] Fix top 5 issues
- [x] Prepare release build

**Deliverable**: v1.0 ready for public launch

---

## File Structure

```
fileorganizer/
├── backend/                      # Python backend
│   ├── api/                      # REST API endpoints
│   │   ├── __init__.py
│   │   ├── documents.py          # Document CRUD
│   │   ├── packs.py              # Pack management
│   │   ├── export.py             # Export handlers
│   │   └── settings.py           # Config management
│   ├── core/                     # Core business logic
│   │   ├── __init__.py
│   │   ├── scanner.py            # File system scanner
│   │   ├── ingestion.py          # OCR + text extraction
│   │   ├── classifier.py         # LLM classification
│   │   ├── embeddings.py         # Vector embeddings
│   │   └── exporter.py           # Export engines
│   ├── models/                   # Database models (SQLAlchemy)
│   │   ├── __init__.py
│   │   ├── document.py
│   │   ├── pack.py
│   │   └── category.py
│   ├── templates/                # Pack YAML templates
│   │   ├── tax_generic_v1.yaml
│   │   ├── immigration_generic_relationship_v1.yaml
│   │   └── legal_generic_timeline_v1.yaml
│   ├── main.py                   # FastAPI app entrypoint
│   └── requirements.txt
├── frontend/                     # Electron + React frontend
│   ├── public/                   # Static assets
│   ├── src/
│   │   ├── components/           # React components
│   │   │   ├── Home.tsx
│   │   │   ├── PackSelection.tsx
│   │   │   ├── Processing.tsx
│   │   │   ├── TriageBoard.tsx
│   │   │   ├── ExportDialog.tsx
│   │   │   └── Settings.tsx
│   │   ├── store/                # Zustand state management
│   │   │   └── appStore.ts
│   │   ├── api/                  # Backend API client
│   │   │   └── client.ts
│   │   ├── App.tsx               # Main app component
│   │   └── main.tsx              # React entrypoint
│   ├── electron/                 # Electron main process
│   │   ├── main.ts               # Main process
│   │   ├── preload.ts            # Preload script (IPC bridge)
│   │   └── backend-manager.ts    # Spawn Python backend
│   ├── package.json
│   └── tsconfig.json
├── tests/                        # Integration tests
│   ├── test_classification.py
│   ├── test_export.py
│   └── test_e2e.py
├── .autopack/                    # Autopack config (for autonomous build)
│   └── fileorganizer_build_config.yaml
└── README.md
```

---

## Success Criteria (v1.0 Launch Gate)

**Functional Requirements**:
- ✅ User can import files (folder or file picker)
- ✅ Backend extracts text from PDFs, images, DOCX
- ✅ LLM classifies documents with 80%+ accuracy (validated by user)
- ✅ UI shows classifications in Triage Board table
- ✅ User can edit wrong categories
- ✅ User can export in 3 formats (PDF bundles, Excel, CSV)
- ✅ All 3 generic packs work end-to-end

**Non-Functional Requirements**:
- ✅ Runs on Windows 10+ and macOS 12+
- ✅ No internet required after model API calls (local-first processing)
- ✅ No critical bugs (no crashes, data loss, or broken exports)
- ✅ 80%+ classification accuracy (measured by user corrections)

**Launch Checklist**:
- ✅ Legal review (disclaimers, privacy policy, terms of service)
- ✅ Alpha testing with 5-10 users
- ✅ Documentation (README, user guide)
- ✅ GitHub repository (public or private)
- ✅ Release build (Windows .exe, macOS .dmg)

---

## What We're NOT Building in v1.0

To maintain scope discipline, these features are **explicitly deferred** to Phase 2+:

### Deferred to Phase 2 (Weeks 14-21):
- ❌ Country-specific pack templates (AU BAS, UK Self Assessment)
- ❌ Visa-specific templates (AU Partner 820/801, UK Spouse)
- ❌ Tax form field mappings (BAS G1, 1040 Schedule C)
- ❌ Advanced triage UI (drag-and-drop, bulk actions, completeness checklist)
- ❌ Keyboard shortcuts (Ctrl+E to edit)

### Deferred to Phase 2.5 (Weeks 22-29):
- ❌ Immigration Premium Service (template updates, subscriptions)
- ❌ Template update server (REST API, JWT auth)
- ❌ Subscription backend (Stripe/Paddle)
- ❌ Expert verification network

### Deferred to Phase 3+:
- ❌ Themes (light/dark mode)
- ❌ Advanced exports (PPT, custom PDF layouts)
- ❌ Duplicate detection (content hash, semantic)
- ❌ Semantic search UI (Q&A, entity views)
- ❌ Team features (shared rules, collaborative packs)
- ❌ Enterprise tier

---

## Risk Mitigation

### Risk 1: LLM Classification Accuracy <80%
**Mitigation**:
- Week 3-4: Extensive prompt engineering with few-shot examples
- Week 6: Test with real user data (tax receipts, immigration docs)
- Fallback: If accuracy <70%, add manual categorization workflow (user assigns categories upfront)

### Risk 2: Electron App Performance (Slow UI)
**Mitigation**:
- Week 1-2: Profile early (React DevTools, Electron DevTools)
- Use virtualized tables for large file lists (react-window)
- Lazy load file previews (only render when visible)

### Risk 3: Backend Crashes on Edge Cases (Corrupted Files)
**Mitigation**:
- Week 7: Robust error handling (try/catch all file operations)
- Graceful degradation (skip corrupted files, log errors, continue processing)
- User notification (show which files failed)

### Risk 4: Scope Creep (Adding Features Mid-Build)
**Mitigation**:
- **Hard backlog rule**: If feature not in this plan → defer to Phase 2
- Weekly scope review (Autopack checks if implementation aligns with plan)
- User feedback gate: Only add features if 3+ alpha testers request the same thing

---

## Next Steps

**Autopack will now**:
1. Update [MASTER_BUILD_PLAN_FILEORGANIZER.md](.autonomous_runs/file-organizer-app-v1/MASTER_BUILD_PLAN_FILEORGANIZER.md) with this parallel development approach
2. Update [IMPLEMENTATION_KICKOFF_FILEORGANIZER.md](.autonomous_runs/file-organizer-app-v1/IMPLEMENTATION_KICKOFF_FILEORGANIZER.md) with UI/UX specifications
3. Commit all planning updates
4. **Begin Week 1 implementation** (project setup + backend foundation + home screen UI)

**User approval required before starting**: Please confirm you're happy with this plan, then Autopack will begin autonomous execution.

---

**Last Updated**: 2025-11-28
**Next Review**: After Week 2 (validate parallel approach is working)
