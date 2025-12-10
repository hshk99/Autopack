# Unsorted Inbox (File Organizer Project)

This directory serves as an inbox for File Organizer project files that could not be automatically classified.

## Purpose

When Cursor creates files related to the File Organizer project and the tidy script cannot confidently determine their destination, they are moved here for manual review.

## What to Do

1. **Review files** in this directory periodically
2. **Move them** to the appropriate location:
   - Plans → `archive/plans/`
   - Analysis → `archive/analysis/`
   - Reports → `archive/reports/`
   - Prompts → `archive/prompts/`
   - Diagnostics → `archive/diagnostics/`

3. **Delete** files that are no longer needed

## Automatic Cleanup

Files older than 30 days in this directory may be automatically archived to `archive/superseded/` during tidy runs with the `--purge` flag.
