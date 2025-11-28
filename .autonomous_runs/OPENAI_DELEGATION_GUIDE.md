# OpenAI GPT-4o Delegation System

Autopack now has a **real OpenAI GPT-4o delegation system** for complex debugging and analysis tasks!

---

## What This Means

When Cursor (Claude) encounters a complex issue that requires deep analysis, it can **delegate the investigation to OpenAI's GPT-4o** using a simple magic phrase.

**Real API integration - actual analysis from OpenAI GPT-4o!**

---

## How It Works

### Magic Phrase Trigger

When you encounter a complex issue, simply say:

```
DELEGATE TO GPT-4O: [brief issue description]
```

**Examples**:
- `DELEGATE TO GPT-4O: 500 error on /runs/start endpoint with no traceback`
- `DELEGATE TO GPT-4O: Database deadlock during concurrent phase execution`
- `DELEGATE TO GPT-4O: Memory leak in long-running autonomous builds`

### What Happens Automatically

1. **Cursor detects** the magic phrase
2. **Gathers context**: relevant files, error logs, attempted fixes
3. **Runs delegation script** with all context
4. **Calls OpenAI GPT-4o API** for deep code analysis
5. **Returns structured analysis** with root cause and recommended fixes
6. **Cursor applies** the recommendations

---

## Manual Usage

If you want to manually delegate an issue:

```bash
cd /c/dev/Autopack

export OPENAI_API_KEY="your-key-here"

python .autonomous_runs/delegate_to_openai.py \
  --issue "500 Internal Server Error on /runs/start endpoint" \
  --files "src/autopack/main.py,src/autopack/schemas.py,src/autopack/models.py" \
  --context "Error persists after fixing slowapi Request import. No traceback in logs." \
  --logs "Internal Server Error (status code 500)" \
  --attempted-fixes "Added Request import" "Separated request_data from request parameter"
```

---

## Output Files

The delegation system creates structured files in `.autonomous_runs/openai_delegations/`:

### 1. OPENAI_DELEGATION_REQUEST_[timestamp].md

Contains:
- Issue description
- Full context
- Error logs
- All attempted fixes
- Complete file contents for analysis
- Specific questions for GPT-4o

### 2. OPENAI_DELEGATION_RESULT_[timestamp].md

GPT-4o fills this with:
- **Root Cause Analysis**: What's causing the issue
- **Technical Explanation**: Deep dive into why it's happening
- **Recommended Fixes**: Prioritized, actionable solutions
- **Code Examples**: Exact code changes needed
- **Additional Investigation**: What else to check
- **Confidence Level**: high/medium/low

### 3. OPENAI_DELEGATION_RESULT_[timestamp].json

JSON version of the result for programmatic processing.

---

## Integration with Autopack

The delegation system leverages OpenAI's GPT-4o model:

```
┌─────────┐
│ Cursor  │  (Builder - implements code)
│ (Claude)│
└────┬────┘
     │
     │ Encounters complex issue
     │
     ▼
┌─────────────────────────┐
│ delegate_to_openai.py   │
│ (Structures request)    │
└────┬────────────────────┘
     │
     │ Calls OpenAI API
     │
     ▼
┌─────────┐
│ GPT-4o  │  (Deep code analysis)
│   API   │
└────┬────┘
     │
     │ Returns analysis
     │
     ▼
┌─────────┐
│ Cursor  │  (Applies recommendations)
│ (Claude)│
└─────────┘
```

This mirrors Autopack's existing Builder/Auditor pattern but uses OpenAI's GPT-4o for external deep analysis.

---

## When to Delegate to GPT-4o

Use GPT-4o delegation for:

### 1. Silent Failures
- Errors with no traceback
- Issues that don't show up in logs
- Mysterious 500 errors

### 2. Framework/Library Issues
- Complex FastAPI behavior
- SQLAlchemy ORM quirks
- Middleware interactions
- Dependency conflicts

### 3. Concurrency Problems
- Deadlocks
- Race conditions
- Transaction isolation issues

### 4. Performance Issues
- Memory leaks
- Slow queries
- Bottleneck identification

### 5. Security Analysis
- Potential vulnerabilities
- Authentication/authorization bugs
- Input validation issues

### 6. When You're Stuck
- After 3+ failed fix attempts
- When error persists despite correct-looking code
- When you need a fresh perspective

---

## Workflow Example

### Problem

You fix a `NameError` in the Autopack API but still get 500 errors with no logs.

### Step 1: Delegate to GPT-4o

```
DELEGATE TO GPT-4O: 500 error persists after fixing slowapi Request import
```

### Step 2: Cursor Runs Script

```bash
python .autonomous_runs/delegate_to_openai.py \
  --issue "500 Internal Server Error on /builder_result endpoint" \
  --files "src/autopack/main.py,src/autopack/schemas.py,src/autopack/builder_schemas.py,src/autopack/models.py" \
  --context "Fixed schema mapping. Phases execute correctly despite 500 error. Builder results not persisted to database." \
  --logs "WARNING: Failed to post builder result: 500 Server Error" \
  --attempted-fixes "Mapped BuilderResult schema" "Verified payload correctness" "Restarted server"
```

### Step 3: Review Delegation Files

```
.autonomous_runs/openai_delegations/
├── OPENAI_DELEGATION_REQUEST_20251128_133758.md
├── OPENAI_DELEGATION_RESULT_20251128_133813.md
└── OPENAI_DELEGATION_RESULT_20251128_133813.json
```

### Step 4: GPT-4o Analyzes (Automatically)

GPT-4o API returns structured analysis:
- **Root cause**: Unhandled exception in patch application or database commit
- **Confidence**: High
- **Fix 1**: Add global exception handler with full traceback logging
- **Fix 2**: Wrap patch application in try/except with detailed logging
- **Fix 3**: Add transaction error handling around db.commit()

### Step 5: Cursor Applies Fix

Cursor reads GPT-4o's analysis and applies the recommended changes.

---

## Benefits

### 1. Real AI Analysis
- Actual OpenAI GPT-4o API calls
- Deep code understanding
- Pattern recognition across frameworks

### 2. Structured Delegation
- All context preserved
- Clear analysis format
- Actionable recommendations

### 3. Audit Trail
- Every delegation logged
- Easy to review past issues
- Learn from previous solutions

### 4. Time Saving
- No manual gathering of context
- No switching between tools
- Automated handoff and response

---

## Advanced Usage

### Custom File Selection

```bash
python .autonomous_runs/delegate_to_openai.py \
  --issue "Complex database migration fails" \
  --files "src/autopack/models.py,src/autopack/database.py,src/autopack/migrations/*.py"
```

### Include Specific Logs

```bash
python .autonomous_runs/delegate_to_openai.py \
  --issue "Uvicorn crashes after 1000 requests" \
  --files "src/autopack/main.py" \
  --logs "$(tail -100 logs/uvicorn.log)"
```

### Track Multiple Attempted Fixes

```bash
python .autonomous_runs/delegate_to_openai.py \
  --issue "Memory leak in Builder execution" \
  --files "src/autopack/builder.py,src/autopack/llm_service.py" \
  --attempted-fixes \
    "Added explicit garbage collection" \
    "Closed database sessions" \
    "Cleared LLM cache after each phase" \
    "Used WeakValueDictionary for caching"
```

---

## Configuration

### Environment Variables

```bash
# OpenAI API key (required)
export OPENAI_API_KEY=sk-proj-...

# Enable UTF-8 encoding (Windows)
export PYTHONUTF8=1
```

### Workspace Root

By default, the script uses the current directory as workspace root. Override:

```bash
python .autonomous_runs/delegate_to_openai.py \
  --workspace /path/to/Autopack \
  --issue "..." \
  --files "..."
```

---

## Troubleshooting

### "OPENAI_API_KEY environment variable required"

**Cause**: API key not set

**Solution**:
```bash
export OPENAI_API_KEY="sk-proj-your-key-here"
```

### "'charmap' codec can't encode character"

**Cause**: Windows console encoding issue

**Solution**:
```bash
export PYTHONUTF8=1
```

### "File not found" warnings

**Cause**: File paths are relative to workspace root

**Solution**: Use correct relative paths:
```bash
# Correct
--files "src/autopack/main.py"

# Incorrect
--files "/c/dev/Autopack/src/autopack/main.py"
```

---

## Real-World Example: 500 Error Resolution

**Actual delegation that resolved a persistent 500 error:**

```bash
cd /c/dev/Autopack
export OPENAI_API_KEY="sk-proj-..."
export PYTHONUTF8=1

python .autonomous_runs/delegate_to_openai.py \
  --issue "500 Internal Server Error on /builder_result endpoint - persists despite schema fixes" \
  --files "src/autopack/main.py,src/autopack/schemas.py,src/autopack/builder_schemas.py,src/autopack/models.py" \
  --context "Server starts successfully. Health check passes. Fixed schema mapping in autonomous_executor.py to match builder_schemas.BuilderResult format. Phases execute and advance correctly despite 500 error. Error occurs on POST to /runs/{run_id}/phases/{phase_id}/builder_result endpoint. All 9 phases completed successfully but builder results weren't persisted to database." \
  --logs "WARNING: Failed to post builder result: 500 Server Error: Internal Server Error for url: http://localhost:8000/runs/fileorg-phase2-beta/phases/fileorg-p2-test-fixes/builder_result" \
  --attempted-fixes \
    "Mapped llm_client.BuilderResult to builder_schemas.BuilderResult with correct schema" \
    "Ensured all required fields included (phase_id, run_id, status, notes)" \
    "Verified payload matches Pydantic schema exactly" \
    "Restarted server multiple times with new code"
```

**GPT-4o's Response** (High Confidence):
- **Root Cause**: Unhandled exception not being logged (database commit failure or patch application error)
- **Fix 1**: Add global exception handler with full traceback
- **Fix 2**: Wrap patch application in try/except
- **Fix 3**: Add transaction error handling

**Result**: Issue successfully resolved using GPT-4o's recommendations

---

## Comparison: Template vs Real API

### Old: delegate_to_codex.py (Template System)
- Created markdown templates
- Required manual copy/paste to AI assistant
- No actual API calls
- Placeholder for human workflow

### New: delegate_to_openai.py (Real API Integration)
- **Actual OpenAI GPT-4o API calls**
- **Automatic analysis**
- **Structured JSON + Markdown results**
- **Programmatic integration**

---

## Future Enhancements

### Phase 1 (Current)
- ✅ Real OpenAI GPT-4o API integration
- ✅ Structured request/result format
- ✅ File content extraction
- ✅ Logging and audit trail
- ✅ High-confidence analysis

### Phase 2 (Planned)
- [ ] Automatic fix application (with approval)
- [ ] Confidence-based retry logic
- [ ] Multi-model comparison (GPT-4o vs Claude)
- [ ] Integration with autonomous executor

### Phase 3 (Future)
- [ ] Machine learning on past delegations
- [ ] Predictive issue detection
- [ ] Proactive GPT-4o suggestions
- [ ] Integration with CI/CD pipeline

---

## Summary

**You can now delegate complex debugging to OpenAI GPT-4o with a simple phrase!**

Just say:
```
DELEGATE TO GPT-4O: [issue description]
```

GPT-4o will analyze deeply via actual API calls and provide actionable recommendations.

**Real AI-powered debugging assistance!**

---

**Status**: OpenAI GPT-4o delegation system active and tested
**Last Updated**: 2025-11-28
**Script**: `.autonomous_runs/delegate_to_openai.py`
**Results**: `.autonomous_runs/openai_delegations/`
