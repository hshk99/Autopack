# Codex Delegation System

Autopack now has a Codex delegation system for complex debugging and analysis tasks!

---

## What This Means

When Cursor (Claude) encounters a complex issue that requires deep analysis, it can **delegate the investigation to Codex** using a simple magic phrase.

**No manual work needed!**

---

## How It Works

### Magic Phrase Trigger

When you encounter a complex issue, simply say:

```
DELEGATE TO CODEX: [brief issue description]
```

**Examples**:
- `DELEGATE TO CODEX: 500 error on /runs/start endpoint with no traceback`
- `DELEGATE TO CODEX: Database deadlock during concurrent phase execution`
- `DELEGATE TO CODEX: Memory leak in long-running autonomous builds`

### What Happens Automatically

1. **Cursor detects** the magic phrase
2. **Gathers context**: relevant files, error logs, attempted fixes
3. **Runs delegation script** with all context
4. **Creates delegation request** for Codex analysis
5. **Codex analyzes** the issue in depth
6. **Cursor reads** Codex's analysis and applies recommendations

---

## Manual Usage

If you want to manually delegate an issue:

```bash
cd .autonomous_runs

python delegate_to_codex.py \
  --issue "500 Internal Server Error on /runs/start endpoint" \
  --files "src/autopack/main.py,src/autopack/schemas.py,src/autopack/models.py" \
  --context "Error persists after fixing slowapi Request import. No traceback in logs." \
  --logs "Internal Server Error (status code 500)" \
  --attempted-fixes "Added Request import" "Separated request_data from request parameter"
```

---

## Output Files

The delegation system creates structured files in `.autonomous_runs/codex_delegations/`:

### 1. CODEX_DELEGATION_REQUEST_[timestamp].md

Contains:
- Issue description
- Full context
- Error logs
- All attempted fixes
- Complete file contents for analysis
- Specific questions for Codex

### 2. CODEX_DELEGATION_RESULT_[timestamp].md

Codex fills this with:
- **Root Cause Analysis**: What's causing the issue
- **Technical Explanation**: Deep dive into why it's happening
- **Recommended Fixes**: Prioritized, actionable solutions
- **Code Examples**: Exact code changes needed
- **Additional Investigation**: What else to check
- **Confidence Level**: high/medium/low

### 3. CODEX_DELEGATION_RESULT_[timestamp].json

JSON version of the result for programmatic processing.

---

## Integration with Autopack

The delegation system follows Autopack's Builder/Auditor pattern:

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
│ Delegation Script       │
│ (Structures request)    │
└────┬────────────────────┘
     │
     │ Creates request document
     │
     ▼
┌─────────┐
│  Codex  │  (Auditor - analyzes deeply)
│   AI    │
└────┬────┘
     │
     │ Provides analysis
     │
     ▼
┌─────────┐
│ Cursor  │  (Applies recommendations)
│ (Claude)│
└─────────┘
```

This mirrors Autopack's existing `/auditor_request` and `/auditor_result` endpoints.

---

## When to Delegate to Codex

Use Codex delegation for:

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

---

## Workflow Example

### Problem

You fix a `NameError` in the Autopack API but still get 500 errors with no logs.

### Step 1: Delegate to Codex

```
DELEGATE TO CODEX: 500 error persists after fixing slowapi Request import
```

### Step 2: Cursor Runs Script

```bash
python delegate_to_codex.py \
  --issue "500 Internal Server Error on /runs/start endpoint" \
  --files "src/autopack/main.py,src/autopack/schemas.py" \
  --context "Fixed NameError for Request import. Server starts successfully. Health check passes. But /runs/start still returns 500 with no traceback." \
  --logs "Internal Server Error" \
  --attempted-fixes "Added 'from fastapi import Request'" "Renamed request param to request_data"
```

### Step 3: Review Delegation Files

```
.autonomous_runs/codex_delegations/
├── CODEX_DELEGATION_REQUEST_20251128_143022.md
├── CODEX_DELEGATION_RESULT_20251128_143022.md
└── CODEX_DELEGATION_RESULT_20251128_143022.json
```

### Step 4: Codex Analyzes

Codex reads the request file and fills in the result file with:
- Root cause (e.g., "slowapi decorator placed before function param changes")
- Technical explanation
- Exact fix (e.g., "move @limiter.limit() after route decorator")
- Confidence level

### Step 5: Cursor Applies Fix

Cursor reads Codex's analysis and applies the recommended changes.

---

## Benefits

### 1. Leverage Specialized Intelligence
- Cursor: Great at implementation and coding
- Codex: Excellent at deep analysis and debugging

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
- Automated handoff

---

## Advanced Usage

### Custom File Selection

```bash
python delegate_to_codex.py \
  --issue "Complex database migration fails" \
  --files "src/autopack/models.py,src/autopack/database.py,alembic/versions/*.py"
```

### Include Specific Logs

```bash
python delegate_to_codex.py \
  --issue "Uvicorn crashes after 1000 requests" \
  --files "src/autopack/main.py" \
  --logs "$(tail -100 /var/log/uvicorn.log)"
```

### Track Multiple Attempted Fixes

```bash
python delegate_to_codex.py \
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
# Codex API endpoint (if using remote Codex)
export CODEX_API_URL=https://codex.example.com

# Codex API key (if authentication required)
export CODEX_API_KEY=your-codex-api-key
```

### Workspace Root

By default, the script uses the current directory as workspace root. Override:

```bash
python delegate_to_codex.py \
  --workspace /path/to/Autopack \
  --issue "..." \
  --files "..."
```

---

## Integration with Cursor

### Cursor Slash Command (Future)

Add to `.cursor/commands/delegate.md`:

```markdown
# Delegate to Codex

When I say "DELEGATE TO CODEX: [issue]", automatically:

1. Extract issue description
2. Identify relevant files based on recent work
3. Gather error logs from recent bash outputs
4. List attempted fixes from conversation history
5. Run: python .autonomous_runs/delegate_to_codex.py with all context
6. Wait for Codex analysis
7. Present Codex's recommendations
8. Ask if I want to apply the recommended fixes
```

---

## Troubleshooting

### "File not found" warnings

**Cause**: File paths are relative to workspace root

**Solution**: Use correct relative paths:
```bash
# Correct
--files "src/autopack/main.py"

# Incorrect
--files "/c/dev/Autopack/src/autopack/main.py"
```

### Delegation request created but no result

**Info**: Codex needs to fill in the result template

**Solution**:
1. Open `CODEX_DELEGATION_RESULT_[timestamp].md`
2. Wait for Codex to populate the file
3. Or manually request Codex analysis of the request file

### Cannot parse Codex result

**Cause**: Result file not in expected format

**Solution**: Check the JSON file for structured data:
```bash
cat codex_delegations/CODEX_DELEGATION_RESULT_*.json
```

---

## Real-World Example: Current 500 Error

Let's use the delegation system for the current issue:

```bash
cd .autonomous_runs

python delegate_to_codex.py \
  --issue "500 Internal Server Error on /runs/start endpoint with no traceback" \
  --files "src/autopack/main.py,src/autopack/schemas.py,src/autopack/models.py" \
  --context "Server starts successfully. Health check passes. Fixed slowapi Request import (was NameError). Changed function signature from 'request: schemas.RunStartRequest' to 'request_data: schemas.RunStartRequest, request: Request'. Updated all function body references. Error persists with no logs." \
  --logs "Internal Server Error" \
  --attempted-fixes \
    "Added 'from fastapi import Request'" \
    "Renamed request parameter to request_data" \
    "Added request: Request parameter for slowapi" \
    "Restarted server multiple times" \
    "Cleared Python bytecode cache"
```

This will create a comprehensive delegation request that Codex can analyze.

---

## Future Enhancements

### Phase 1 (Current)
- ✅ Script-based delegation
- ✅ Structured request/result format
- ✅ File content extraction
- ✅ Logging and audit trail

### Phase 2 (Planned)
- [ ] Direct Codex API integration
- [ ] Real-time analysis (no manual handoff)
- [ ] Automatic fix application
- [ ] Confidence-based retry logic

### Phase 3 (Future)
- [ ] Machine learning on past delegations
- [ ] Predictive issue detection
- [ ] Proactive Codex suggestions
- [ ] Integration with CI/CD pipeline

---

## Summary

**You can now delegate complex debugging to Codex with a simple phrase!**

Just say:
```
DELEGATE TO CODEX: [issue description]
```

Codex will analyze deeply and provide actionable recommendations.

**No manual investigation required!**

---

**Status**: Codex delegation system ready for use
**Last Updated**: 2025-11-28
