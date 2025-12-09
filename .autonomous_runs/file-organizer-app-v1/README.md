# FileOrganizer v1.0.0 Alpha

**Intelligent Document Organization powered by AI**

FileOrganizer is a desktop application that uses OCR and AI classification to automatically organize your documents into structured packs for tax filing, immigration applications, legal cases, and more.

## Features

[OK] **3 Generic Pack Templates**
- Tax Pack (income, deductions, expenses, etc.)
- Immigration Pack (identity docs, financial evidence, employment, etc.)
- Legal Pack (contracts, court documents, correspondence, etc.)

[OK] **AI-Powered Classification**
- Automatic document classification using GPT-4
- Confidence scoring (0-100%)
- Manual override and approval

[OK] **OCR Text Extraction**
- Tesseract OCR for scanned documents
- Native PDF text extraction
- Multi-page support

[OK] **Triage Board**
- Review and edit classifications
- Search and filter documents
- Approve documents for export

[OK] **Multiple Export Formats**
- PDF reports with categorized sections
- Excel workbooks with multiple sheets
- CSV for data import

[OK] **Cross-Platform Desktop App**
- Built with Electron
- Works on Windows, macOS, Linux

## Documentation

Detailed autonomous run history and documentation can be found in the `archive/` directory:

- **[Archive Index](archive/ARCHIVE_INDEX.md)**: Index of all documentation.
- **[Build History](archive/CONSOLIDATED_BUILD.md)**: Timeline of autonomous build execution.
- **[Debug Journal](archive/CONSOLIDATED_DEBUG.md)**: Record of errors and fixes.
- **[Strategic Analysis](archive/CONSOLIDATED_STRATEGY.md)**: Product and market strategy.
- **[Research](archive/CONSOLIDATED_RESEARCH.md)**: Research briefs and implementation plans.

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Tesseract OCR** (for scanned documents)
  - Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
  - macOS: `brew install tesseract`
  - Linux: `apt-get install tesseract-ocr`
- **OpenAI API Key** (for AI classification)

### Installation

1. **Clone the repository:**
   ```bash
   git clone <repository-url>
   cd fileorganizer
   ```

2. **Install backend dependencies:**
   ```bash
   cd backend
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Configure environment:**
   ```bash
   cp .env.template .env
   # Edit .env and add your OPENAI_API_KEY
   ```

4. **Load pack templates:**
   ```bash
   python load_all_packs.py
   ```

5. **Install frontend dependencies:**
   ```bash
   cd ../frontend
   npm install
   ```

6. **Run the application:**
   ```bash
   npm start
   ```

The app will start:
- Backend API: http://127.0.0.1:8000
- Frontend: Electron desktop app

## Usage

1. **Select a Pack** - Choose Tax, Immigration, or Legal
2. **Upload Documents** - Drag and drop PDFs, images
3. **Review Classifications** - Check AI suggestions in Triage Board
4. **Edit & Approve** - Adjust categories, approve documents
5. **Export** - Download as PDF, Excel, or CSV

See [docs/USER_GUIDE.md](docs/USER_GUIDE.md) for detailed instructions.

## Development

### Run Backend Only
```bash
cd backend
source venv/bin/activate
python main.py
```

### Run Frontend Only
```bash
cd frontend
npm run start:react
```

### Run Tests
```bash
cd backend
pytest tests/ -v
```

## Architecture

```
fileorganizer/
 backend/          # Python FastAPI backend
    app/
       models/       # SQLAlchemy models
       routers/      # API endpoints
       services/     # Business logic
       core/         # Config, logging, errors
    packs/            # YAML pack templates
    tests/            # Pytest test suite

 frontend/         # Electron + React frontend
     electron/         # Electron main process
     src/
        pages/        # React pages
        components/   # React components
     public/           # Static assets
```

## Technology Stack

**Backend:**
- Python 3.11+ / FastAPI
- SQLAlchemy + SQLite
- Tesseract OCR + PyMuPDF
- OpenAI GPT-4 (litellm)
- ReportLab (PDF) / openpyxl (Excel)

**Frontend:**
- Electron 28+
- React 18 + TypeScript
- Tailwind CSS
- Zustand (state management)
- Vite (build tool)

## Configuration

See `.env.template` for all configuration options.

Key settings:
- `OPENAI_API_KEY` - Required for AI classification
- `TESSERACT_CMD` - Path to Tesseract (auto-detected if not set)
- `MAX_FILE_SIZE_MB` - Maximum upload size (default: 50 MB)

## Limitations (v1.0 Alpha)

- [WARNING] **Generic packs only** - No country-specific templates yet
- [WARNING] **English only** - OCR optimized for English documents
- [WARNING] **Single user** - No multi-user support
- [WARNING] **Local only** - No cloud sync

Future versions will address these limitations.

## Contributing

Contributions welcome! Please open an issue first to discuss major changes.

## License

MIT License - See LICENSE file for details

## Support

- **Issues:** https://github.com/<your-org>/fileorganizer/issues
- **Documentation:** docs/USER_GUIDE.md
- **Email:** support@example.com

---

**Built with Autopack** - 100% Autonomous AI Code Generation
**Version:** 1.0.0-alpha
**Released:** 2025-11-28
