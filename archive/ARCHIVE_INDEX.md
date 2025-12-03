# Documentation Archive Index

**Last Updated**: 2025-12-03
**Purpose**: Quick reference guide to all archived documentation

---

## Autopack Framework Documentation Archive

### Consolidated Documentation

| Category | File | Description | Sources |
|----------|------|-------------|---------|
| **Correspondence** | [CONSOLIDATED_CORRESPONDENCE.md](CONSOLIDATED_CORRESPONDENCE.md) | Claude-GPT consultation index and summary | 52 individual exchanges |
| **Build** | [CONSOLIDATED_BUILD.md](CONSOLIDATED_BUILD.md) | Build system, deployment, and setup guides | 3 files |
| **Debug** | [CONSOLIDATED_DEBUG.md](CONSOLIDATED_DEBUG.md) | Debugging guides and troubleshooting | 2 files |
| **Reference** | [CONSOLIDATED_REFERENCE.md](CONSOLIDATED_REFERENCE.md) | Technical reference materials | 3 files |
| **Strategy** | [CONSOLIDATED_STRATEGY.md](CONSOLIDATED_STRATEGY.md) | Strategic decisions and architectural plans | 5 files |
| **Research** | [CONSOLIDATED_RESEARCH.md](CONSOLIDATED_RESEARCH.md) | Research notes and explorations | 4 files |
| **Misc** | [CONSOLIDATED_MISC.md](CONSOLIDATED_MISC.md) | Miscellaneous documentation | 18 files |

---

## Key Documents

### 1. Claude-GPT Consultation Archive

**📁 Location**: [correspondence/](correspondence/)

**Summary Document**: [GPT_CLAUDE_CONSULTATION_SUMMARY.md](GPT_CLAUDE_CONSULTATION_SUMMARY.md)

**Index**: [CONSOLIDATED_CORRESPONDENCE.md](CONSOLIDATED_CORRESPONDENCE.md)

**Contents**:
- 27 GPT response files (GPT_RESPONSE4-27)
- 24 Claude response files (CLAUDE_RESPONSE4-27)
- 4 Claude reports for GPT review
- 1 implementation summary

**Topics Covered**:
- Diff mode failure analysis and elimination
- Token soft caps implementation
- Symbol preservation validation
- Goal anchoring system design
- API server bug fixes
- Configuration structure improvements

**Status**:
- ✅ Phase 1 implementation complete (Dec 1-3, 2025)
- 📋 Phase 2 items documented for future implementation

---

### 2. Planning and Strategy Documents

| Document | Purpose | Status |
|----------|---------|--------|
| [AUTOPACK_SELF_HEALING_PLAN.md](AUTOPACK_SELF_HEALING_PLAN.md) | Self-healing system design | Reference |
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | Original implementation plan | Historical |
| [ref1.md](ref1.md) | Early reference document | Historical |
| [ref2.md](ref2.md) | Early reference document | Historical |

---

## Directory Structure

```
archive/
├── ARCHIVE_INDEX.md (this file)
├── CONSOLIDATED_*.md (7 consolidated documents)
├── GPT_CLAUDE_CONSULTATION_SUMMARY.md
├── DOC_CONSOLIDATION_GUIDE.md
├── correspondence/ (52 individual Claude-GPT exchanges)
│   ├── GPT_RESPONSE*.md
│   ├── CLAUDE_RESPONSE*.md
│   └── CLAUDE_REPORT*.md
└── [Other historical documents]
```

---

## How to Use This Archive

### Finding Information

1. **For Claude-GPT consultation history**:
   - Start with [CONSOLIDATED_CORRESPONDENCE.md](CONSOLIDATED_CORRESPONDENCE.md)
   - Read [GPT_CLAUDE_CONSULTATION_SUMMARY.md](GPT_CLAUDE_CONSULTATION_SUMMARY.md) for decisions
   - Check [correspondence/](correspondence/) for individual exchanges

2. **For specific topics**:
   - Use the Consolidated Documentation table above
   - Open the relevant CONSOLIDATED_*.md file
   - Use Ctrl+F to search for keywords

3. **For implementation status**:
   - See "Implementation Status Overview" in CONSOLIDATED_CORRESPONDENCE.md
   - Check "Code Changes Summary" in GPT_CLAUDE_CONSULTATION_SUMMARY.md

### Document Categories

- **CONSOLIDATED_CORRESPONDENCE.md**: All Claude-GPT exchanges indexed with summary
- **CONSOLIDATED_BUILD.md**: Deployment, CI/CD, Docker, build processes
- **CONSOLIDATED_DEBUG.md**: Troubleshooting, debugging techniques, error analysis
- **CONSOLIDATED_REFERENCE.md**: API references, data structures, configuration guides
- **CONSOLIDATED_STRATEGY.md**: Architectural decisions, strategic planning, roadmaps
- **CONSOLIDATED_RESEARCH.md**: Research notes, exploration, experiments
- **CONSOLIDATED_MISC.md**: Everything else not fitting above categories

---

## Recent Changes (Dec 2025)

### Dec 3, 2025
- ✅ Organized 52 correspondence files into `correspondence/` subdirectory
- ✅ Created CONSOLIDATED_CORRESPONDENCE.md as main index
- ✅ Updated ARCHIVE_INDEX.md with new structure
- ✅ All test suite passing (83 passed, 161 skipped, 0 failed)
- ✅ Created `tests-passing-v1.0` git tag for milestone

### Dec 1-2, 2025
- ✅ Completed Phase 1 implementation of GPT recommendations
- ✅ Fixed structured edit mode bug
- ✅ Implemented token soft caps
- ✅ Fixed all pre-existing test failures

---

## Maintenance

### To Add New Content

1. **New correspondence**: Add to `correspondence/` and update CONSOLIDATED_CORRESPONDENCE.md
2. **New consolidated docs**: Create CONSOLIDATED_[CATEGORY].md and update this index
3. **Updates to existing**: Edit the consolidated file, add source reference

### To Update This Index

```bash
# After making changes, update the "Last Updated" date above
git add archive/
git commit -m "docs: Update archive index"
```

---

## Related Documentation

- **Root README**: [../README.md](../README.md)
- **Implementation Guides**: [../docs/](../docs/)
- **Learned Rules**: [../LEARNED_RULES_README.md](../LEARNED_RULES_README.md)

---

*Auto-maintained by Autopack Documentation System*
*For consolidation algorithm, see [DOC_CONSOLIDATION_GUIDE.md](DOC_CONSOLIDATION_GUIDE.md)*
