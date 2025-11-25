Run the documentation organization script to clean up and organize all markdown files in the project.

Execute: python scripts/tidy_docs.py --verbose

This will:
- Keep only essential files (README.md, LEARNED_RULES_README.md) at root
- Move implementation guides to docs/
- Move historical documents to archive/
- Delete obsolete backup files
- Show verbose output of all actions taken
