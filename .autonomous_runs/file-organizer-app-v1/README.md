# FileOrganizer

AI-powered document organization system for immigration visa packs, tax documents, and legal evidence compilation.

## Overview

FileOrganizer automatically processes, classifies, and organizes immigration documentation using AI-powered analysis. It handles multiple visa types (Australia, UK, Canada) and maintains structured pack organization.

## Features

- **Intelligent Classification**: OCR + LLM classification for visa/tax/legal documents
- **Country-Specific Packs**: Templates for AU, UK, CA immigration and tax packs
- **Pack Management**: Organizes documents into structured evidence packs
- **Timeline Generation**: Automatic timeline extraction from documents
- **Batch Processing**: Multi-file upload and background processing
- **Search & Filtering**: Full-text search with FTS5
- **Export Formats**: PDF compilation and spreadsheet export

## Quick Start

```bash
# Setup
docker-compose up -d
pip install -r requirements.txt
uvicorn src.backend.main:app --reload

# Frontend (in frontend/ directory)
npm install && npm run dev
```

See [PROJECT_INDEX.json](docs/PROJECT_INDEX.json) for complete setup instructions and API endpoints.

## Project Structure

```
file-organizer-app-v1/
├── src/
│   ├── backend/          # FastAPI backend
│   └── frontend/         # Electron + React frontend
├── packs/
│   ├── tax/              # Tax pack templates (AU, UK, CA)
│   ├── immigration/      # Immigration pack templates
│   └── legal/            # Legal evidence templates
├── docs/                 # Source of Truth documentation
│   ├── PROJECT_INDEX.json           # Quick reference (start here)
│   ├── BUILD_HISTORY.md             # Implementation history
│   ├── DEBUG_LOG.md                 # Troubleshooting log
│   ├── ARCHITECTURE_DECISIONS.md    # Design decisions
│   ├── FUTURE_PLAN.md               # Roadmap and backlog
│   └── LEARNED_RULES.json           # Auto-updated learned rules
├── tests/                # Test files
└── archive/              # Historical files (plans, reports, research)
```

## Key Documentation

All documentation follows the 6-file SOT structure for fast AI navigation:

1. **[PROJECT_INDEX.json](docs/PROJECT_INDEX.json)** - Complete quick reference (setup, deployment, API endpoints)
2. **[BUILD_HISTORY.md](docs/BUILD_HISTORY.md)** - Implementation history (auto-updated)
3. **[DEBUG_LOG.md](docs/DEBUG_LOG.md)** - Troubleshooting history (auto-updated)
4. **[ARCHITECTURE_DECISIONS.md](docs/ARCHITECTURE_DECISIONS.md)** - Design decisions (auto-updated)
5. **[FUTURE_PLAN.md](docs/FUTURE_PLAN.md)** - Phase 2 roadmap and backlog
6. **[LEARNED_RULES.json](docs/LEARNED_RULES.json)** - Auto-updated learned rules

## Tech Stack

**Backend:**
- FastAPI + PostgreSQL + SQLAlchemy
- Tesseract OCR + OpenAI API
- Qdrant (optional for embeddings)

**Frontend:**
- Electron + React + Material-UI

## Development

```bash
# Run tests
pytest tests/ -v

# Start services
docker-compose up -d              # Database + optional Qdrant
uvicorn src.backend.main:app --reload --port 8000
cd frontend && npm run dev        # Frontend on port 3000
```

## Current Phase

**Phase 2 - Beta Release**

See [FUTURE_PLAN.md](docs/FUTURE_PLAN.md) for priorities:
- Test suite fixes (high priority)
- Frontend build system (high priority)
- Docker deployment (medium priority)
- Country packs UK/CA/AU (medium priority)

## Multi-Project Configuration

This project uses the centralized Autopack tidy system. Configuration is stored in the `tidy_project_config` database table with project_id: `file-organizer-app-v1`.

## Related Projects

This is a subproject within the Autopack autonomous build system workspace.
