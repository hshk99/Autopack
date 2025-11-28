# FileOrganizer v1.0 - User Guide

## Overview

FileOrganizer is an intelligent document organization tool that uses AI to automatically classify and organize your documents into structured packs.

## Getting Started

### 1. Select a Document Pack

Choose from one of the available scenario packs:

- **Tax Pack**: Organize tax-related documents (income, deductions, bank statements, etc.)
- **Immigration Pack**: Organize immigration documents (identity docs, financial evidence, employment, etc.)
- **Legal Pack**: Organize legal documents (contracts, court documents, correspondence, etc.)

### 2. Upload Documents

Upload your documents (PDF, PNG, JPG) using the file upload interface:

- Click "Select Files" or drag and drop
- Supported formats: .pdf, .png, .jpg, .jpeg
- Maximum file size: 50 MB per file
- Multiple files can be uploaded at once

### 3. Automatic Processing

FileOrganizer will automatically:

1. **Extract text** using OCR (for scanned documents)
2. **Classify documents** into appropriate categories using AI
3. **Assign confidence scores** (0-100%) to each classification

### 4. Review and Triage

Use the **Triage Board** to review classifications:

- **Green (80-100%)**: High confidence - likely correct
- **Yellow (60-79%)**: Medium confidence - review recommended
- **Red (<60%)**: Low confidence - review required

**Actions:**
- Click category name to change classification
- Click "Approve" to mark as reviewed (sets confidence to 100%)
- Use search bar to find specific files
- Filter by status: All, Needs Review, Approved

### 5. Export Your Pack

Once satisfied with classifications, export your organized pack:

**PDF Format:**
- Professional report with categorized document lists
- Ideal for printing or sharing

**Excel Format:**
- Multi-sheet workbook with summary and category sheets
- Ideal for further analysis or record-keeping

**CSV Format:**
- Simple flat file for data import
- Ideal for integration with other tools

## Pack Templates

### Tax Pack Categories
- Income
- Deductions
- Business Expenses
- Investment Income
- Bank Statements
- Other

### Immigration Pack Categories
- Identity Documents
- Financial Evidence
- Employment Documents
- Educational Credentials
- Medical Records
- Travel History
- Sponsor Documents
- Other

### Legal Pack Categories
- Contracts & Agreements
- Court Documents
- Correspondence
- Evidence
- Identity & Verification
- Property Documents
- Financial Records
- Other

## Tips for Best Results

1. **Upload clear, high-quality scans** - Better image quality = better OCR results
2. **Review low-confidence classifications** - AI isn't perfect; manual review improves accuracy
3. **Use descriptive filenames** - Helps you identify documents quickly
4. **Approve documents after review** - Marks them as verified and sets 100% confidence
5. **Export regularly** - Save your organized packs periodically

## Keyboard Shortcuts

- **Search**: Focus on search bar (click search field)
- **Filter**: Click filter buttons (All, Needs Review, Approved)
- **Navigate**: Use browser back/forward buttons

## Troubleshooting

**Documents not uploading?**
- Check file size (max 50 MB)
- Verify file format (.pdf, .png, .jpg, .jpeg)

**Classification seems wrong?**
- Click category name to change it manually
- Manual changes override AI with 100% confidence

**Export not working?**
- Ensure at least one document is classified
- Check browser's download settings

## Technical Requirements

- **Platform**: Windows, macOS, Linux
- **Browser**: Modern browser (Chrome, Firefox, Edge, Safari)
- **Internet**: Required for AI classification
- **Disk Space**: Depends on document size

## Privacy & Security

- Documents processed locally on your machine
- AI classification uses OpenAI API (data sent to cloud)
- No documents stored on external servers
- All data remains on your computer

## Support

For issues or questions, please refer to:
- GitHub Issues: [Report a bug]
- Documentation: [Full documentation]

---

**Version**: 1.0.0
**Last Updated**: Week 6 Implementation
**License**: MIT
