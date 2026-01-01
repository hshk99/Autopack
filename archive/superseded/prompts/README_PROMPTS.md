# Cursor Prompt Library - Quick Reference

**Location**: `.cursor/` directory
**Purpose**: Reusable prompts for common Claude ↔ GPT consultation workflows

---

## Available Prompts

### 1. Request GPT Auditor Review
**File**: [PROMPT_REQUEST_GPT_REVIEW.md](PROMPT_REQUEST_GPT_REVIEW.md)

**When to use**: You need GPT's analysis on a bug, design question, or architectural decision

**Quick Copy-Paste**:
```
I need a GPT Auditor review for [DESCRIBE ISSUE].

Please:
1. Create a report at: archive/correspondence/CLAUDE_REPORT_FOR_GPT_[ISSUE_NAME].md
2. Include: executive summary, analysis, questions for GPT
3. Provide me with a ready-to-paste Cursor Agent prompt

Context:
[YOUR CONTEXT HERE]
```

---

### 2. Submit GPT Response Back to Claude
**File**: [PROMPT_SUBMIT_GPT_RESPONSE.md](PROMPT_SUBMIT_GPT_RESPONSE.md)

**When to use**: After GPT Auditor completes analysis and you want Claude to implement or follow up

**Quick Copy-Paste**:
```
GPT Auditor has completed the review and saved the response at:
archive/correspondence/GPT_RESPONSE_[ISSUE_NAME].md

Please:
1. Read the GPT response file
2. Review the analysis and recommendations
3. Identify what we should implement immediately vs defer
4. If ready to implement, create an implementation plan

What do you think of GPT's recommendations?
```

---

## Workflow Example

### Step 1: Discover Issue
You (or Claude) discovers a bug/question that needs deep analysis.

### Step 2: Request GPT Review (Use Prompt #1)
**In Claude chat**, paste:
```
I need a GPT Auditor review for scope path configuration bug.

Please:
1. Create a report at: archive/correspondence/CLAUDE_REPORT_FOR_GPT_SCOPE_PATH_BUG.md
2. Include: executive summary, analysis, questions for GPT
3. Provide me with a ready-to-paste Cursor Agent prompt

Context:
Builder is attempting to modify files outside specified scope.
Phase spec defines scope.paths but Builder logs show "No scope_paths defined".
```

Claude creates report and gives you a Cursor Agent prompt.

### Step 3: Run GPT Auditor
**In Cursor Agent mode**, paste the prompt Claude provided.

GPT analyzes and writes: `archive/correspondence/GPT_RESPONSE_SCOPE_PATH_BUG.md`

### Step 4: Submit GPT Response (Use Prompt #2)
**Back in Claude chat**, paste:
```
GPT Auditor has completed the review and saved the response at:
archive/correspondence/GPT_RESPONSE_SCOPE_PATH_BUG.md

Please:
1. Read the GPT response file
2. Review the analysis and recommendations
3. Identify what we should implement immediately vs defer
4. If ready to implement, create an implementation plan

What do you think of GPT's recommendations?
```

Claude reads GPT's response and either:
- Creates implementation plan → you approve → Claude implements
- Prepares follow-up questions → repeat from Step 3

---

## Tips for Effective Consultations

### ✅ DO:
- Be specific about what you need (root cause? architectural design? code review?)
- Provide concrete context (error messages, file paths, line numbers)
- Let Claude and GPT iterate - don't force consensus if they disagree
- Save all consultation exchanges in `archive/correspondence/`

### ❌ DON'T:
- Ask vague questions like "what do you think?" - be specific
- Skip Claude's analysis - Claude may catch issues before needing GPT
- Implement without review - both agents should agree on approach
- Delete consultation history - it's valuable for future reference

---

## When to Use GPT Consultation

**Use GPT Auditor when:**
- ✅ Bug has unclear root cause after initial investigation
- ✅ Architectural decision with multiple valid approaches
- ✅ Need second opinion on complex design
- ✅ Performance optimization strategy unclear
- ✅ Security implications need review
- ✅ Claude discovers issue but wants validation

**Don't need GPT when:**
- ❌ Simple bug with obvious fix
- ❌ Straightforward feature implementation
- ❌ Documentation/comment updates
- ❌ Test case additions (unless testing strategy is complex)
- ❌ Trivial refactoring

---

## Consultation History

All Claude ↔ GPT exchanges are saved in:
```
archive/correspondence/
├── CLAUDE_REPORT_FOR_GPT_*.md
├── GPT_RESPONSE_*.md
└── CLAUDE_FOLLOWUP_FOR_GPT_*.md (if needed)
```

Referenced in:
- [archive/CONSOLIDATED_CORRESPONDENCE.md](../archive/CONSOLIDATED_CORRESPONDENCE.md)

---

## Quick Links

- **Request GPT Review**: [PROMPT_REQUEST_GPT_REVIEW.md](PROMPT_REQUEST_GPT_REVIEW.md)
- **Submit GPT Response**: [PROMPT_SUBMIT_GPT_RESPONSE.md](PROMPT_SUBMIT_GPT_RESPONSE.md)
- **Consultation Archive**: [../archive/correspondence/](../archive/correspondence/)
- **Consolidated Summary**: [../archive/CONSOLIDATED_CORRESPONDENCE.md](../archive/CONSOLIDATED_CORRESPONDENCE.md)

---

**Last Updated**: 2025-12-03
