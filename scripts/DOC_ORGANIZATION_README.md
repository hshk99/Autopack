# Documentation Organization System

Automated system to keep Autopack documentation clean and organized.

## Quick Usage

### Dry Run (See what would happen)
```bash
python scripts/tidy_docs.py --dry-run --verbose
```

### Actually Organize Files
```bash
python scripts/tidy_docs.py --verbose
```

### Save Report
```bash
python scripts/tidy_docs.py --verbose --report tidy_report.json
```

---

## How It Works

The script automatically categorizes and moves documentation files according to these rules:

### **Root Directory** (Essential Only)
Only these files stay at root:
- `README.md` - Main entry point
- `LEARNED_RULES_README.md` - Technical guide

### **docs/** (Implementation Guides)
Files matching these patterns go here:
- `*IMPLEMENTATION*.md`
- `*GUIDE*.md`
- `*ROUTING*.md`
- `*EFFICIENCY*.md`

Or containing keywords: `implementation`, `guide`, `routing`, `efficiency`, `optimization`

### **archive/** (Historical Reference)
Files matching these patterns go here:
- `*COMPLETE*.md`
- `*HISTORY*.md`
- `*MILESTONE*.md`
- `*ASSESSMENT*.md`
- `*CORRESPONDENCE*.md`
- `*DEPLOYMENT*.md`
- `*SETUP*.md`

Or containing keywords: `complete`, `history`, `milestone`, `assessment`, `gpt`, `phase`, `deployment`

### **Delete** (Obsolete Files)
Files matching these patterns are deleted:
- `*.bak`
- `*_backup.md`
- `*_old.md`
- `*_temp.md`

---

## Customizing Rules

Edit the `DOCUMENTATION_RULES` dictionary in `tidy_docs.py` to customize categorization:

```python
DOCUMENTATION_RULES = {
    "root_essential": {
        "files": ["README.md", "LEARNED_RULES_README.md"],
    },

    "docs_guides": {
        "location": "docs/",
        "patterns": ["*IMPLEMENTATION*.md", "*GUIDE*.md"],
        "keywords": ["implementation", "guide"],
    },

    # ... etc
}
```

---

## Integration with Cursor/Claude

### Slash Command Integration

You can create a custom slash command in `.claude/commands/` to trigger this:

**File**: `.claude/commands/tidy.md`
```markdown
Run the documentation organization script:
python scripts/tidy_docs.py --verbose
```

Then use: `/tidy` in chat to organize files.

### Natural Language Trigger

Simply say any of these phrases in chat:
- "tidy up the files"
- "organize documentation"
- "clean up docs"
- "consolidate files"

Claude will recognize the intent and run:
```bash
python scripts/tidy_docs.py --verbose
```

---

## Example Output

```bash
$ python scripts/tidy_docs.py --verbose

🚀 Starting documentation organization...
ℹ️  Project root: c:\dev\Autopack
ℹ️  Found 15 markdown files

⊘ SKIP: README.md - Already at root
⊘ SKIP: LEARNED_RULES_README.md - Already at root
✓ MOVE to docs/: TOKEN_EFFICIENCY_IMPLEMENTATION.md - Implementation guide pattern matched
✓ MOVE to archive/: AGENT_INTEGRATION_COMPLETE.md - Historical document pattern matched
🗑️ DELETE: README.md.bak - Obsolete file pattern matched

📦 Executing actions...
✓ Moved TOKEN_EFFICIENCY_IMPLEMENTATION.md to docs/
✓ Moved AGENT_INTEGRATION_COMPLETE.md to archive/
✓ Deleted README.md.bak

============================================================
📊 ORGANIZATION SUMMARY
============================================================
Total Files: 15
Kept At Root: 2
Moved To Docs: 3
Moved To Archive: 8
Deleted: 2
No Action: 0
============================================================
```

---

## Safety Features

1. **Dry Run Mode**: Always test first with `--dry-run`
2. **Verbose Output**: See exactly what will happen
3. **Essential Files Protected**: Root essential files never moved
4. **Empty Directory Cleanup**: Automatically removes empty dirs
5. **Report Generation**: Save detailed JSON report of all actions

---

## When to Run

Run this script when:
- After completing a major implementation phase
- When documentation becomes cluttered (5+ new files at root)
- Before releasing a new version
- When onboarding new team members (clean structure helps)
- Periodically (e.g., end of each sprint)

---

## Advanced: Pre-commit Hook

To automatically organize docs before each commit:

**File**: `.git/hooks/pre-commit`
```bash
#!/bin/bash
python scripts/tidy_docs.py
git add .
```

Make executable:
```bash
chmod +x .git/hooks/pre-commit
```

---

## Troubleshooting

### "No files were moved"
- Check file patterns in `DOCUMENTATION_RULES`
- Run with `--verbose` to see categorization decisions
- Some files might already be in correct locations

### "Permission denied"
- Check file permissions
- Run with appropriate user permissions
- On Windows, close files in editors before running

### "Files in wrong category"
- Adjust patterns/keywords in `DOCUMENTATION_RULES`
- Consider adding specific filename overrides
- File an issue if default rules need improvement

---

## Future Enhancements

Potential improvements:
- [ ] AI-powered categorization (use LLM to read file and suggest category)
- [ ] Interactive mode (ask user for confirmation on each move)
- [ ] Backup before organizing (create `.backup/` snapshot)
- [ ] Integration with git (auto-commit organized files)
- [ ] Web dashboard showing documentation structure
- [ ] Duplicate detection and merge suggestions

---

**Last Updated**: 2025-11-25
**Maintainer**: Autopack Team
