# Magic Phrase Pattern for Cursor AI - Autopack Autonomous Builds

This document defines the "magic phrase" pattern for triggering fully autonomous Autopack execution via Cursor AI.

**IMPORTANT**: The magic phrase is now **project-agnostic** and works for any phase (Phase 1, Phase 2, Phase 3, etc.)

---

## Recommended (Generic - Works for Any Project/Phase)

### Magic Phrase (Default):
```
RUN AUTOPACK END-TO-END for <ProjectName> now.
```

### What Cursor Should Execute:
```bash
cd c:/dev/Autopack/.autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive
```

### Examples:
- `RUN AUTOPACK END-TO-END for FileOrganizer now.` → Runs tasks from WHATS_LEFT_TO_BUILD.md
- `RUN AUTOPACK END-TO-END for MyNewApp now.` → Runs tasks for MyNewApp (any phase)
- `RUN AUTOPACK END-TO-END for APIGateway now.` → Runs tasks for APIGateway project

### Expected Behavior:
- Zero interactive prompts
- Auto-starts Autopack service if not running
- Auto-detects project name from directory structure
- Executes all tasks from WHATS_LEFT_TO_BUILD.md (regardless of phase)
- Generates comprehensive reports
- Shuts down service gracefully on completion

---

## NEW: Run with Custom Task File

### Magic Phrase (Custom Tasks):
```
RUN AUTOPACK END-TO-END for <ProjectName> using <TaskFile.md> now.
```

### What Cursor Should Execute:
```bash
cd c:/dev/Autopack/.autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive --tasks-file "<TaskFile.md>"
```

### Examples:
```
RUN AUTOPACK END-TO-END for FileOrganizer using REVISED_PLAN_V2.md now.
→ Executes: python scripts/autopack_runner.py --non-interactive --tasks-file "REVISED_PLAN_V2.md"

RUN AUTOPACK END-TO-END for ShoppingCart using SPRINT_3_TASKS.md now.
→ Executes: python scripts/autopack_runner.py --non-interactive --tasks-file "SPRINT_3_TASKS.md"

RUN AUTOPACK END-TO-END for TodoApp using HOTFIX_PLAN.md now.
→ Executes: python scripts/autopack_runner.py --non-interactive --tasks-file "HOTFIX_PLAN.md"
```

### Use Cases for Custom Task Files:
1. **Revised Plans**: When your plan changes, save it as `REVISED_PLAN_V2.md`
2. **Sprint-Specific**: Organize tasks by sprint: `SPRINT_1_TASKS.md`, `SPRINT_2_TASKS.md`
3. **Hotfixes**: Urgent fixes in `HOTFIX_PLAN.md`
4. **Feature Branches**: Feature-specific tasks in `FEATURE_AUTH_TASKS.md`
5. **Experimental**: Test new approaches in `EXPERIMENTAL_PLAN.md`

### Task File Format:
All task files must follow Autopack format:
```markdown
### Task 1: Task Name
**Phase ID**: `unique-task-id`
**Category**: backend|frontend|database|api|testing|docs|deployment
**Complexity**: low|medium|high
**Description**: What needs to be built

**Acceptance Criteria**:
- [ ] Criterion 1
- [ ] Criterion 2

**Dependencies**: None (or `other-task-id`)
```

### Benefits of Custom Task Files:
- ✅ Keep multiple plans without overwriting
- ✅ Easily switch between different execution strategies
- ✅ Version control your plans (git diff shows changes)
- ✅ Run hotfixes without disturbing main plan
- ✅ Test experimental approaches safely

---

## For FileOrganizer (Backward Compatibility)

### Legacy Magic Phrase (Still Works):
```
RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.
```

### What Cursor Should Execute:
```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive
```

**Note**: This uses the phase2-specific runner for backward compatibility with existing documentation. New projects should use the generic `autopack_runner.py` instead.

---

## For Future Projects (Generic Pattern)

### Quick Setup (Automated - Recommended)

**NEW Magic Phrase**:
```
SET UP NEW AUTOPACK PROJECT: <Project Name>
```

**What It Does**:
- **Auto-generates slug** from project name (no manual slug needed!)
- Creates complete project structure
- Copies generic autopack_runner.py
- Sets up magic phrase for running

**Examples**:
```
SET UP NEW AUTOPACK PROJECT: Shopping Cart
→ Auto-generates slug: shopping-cart-v1

SET UP NEW AUTOPACK PROJECT: Todo App
→ Auto-generates slug: todo-app-v1

SET UP NEW AUTOPACK PROJECT: My API Gateway
→ Auto-generates slug: my-api-gateway-v1
```

**Manual Setup** (if you prefer):
```bash
cd c:/dev/Autopack/.autonomous_runs
python setup_new_project.py --name "MyApp"
# Slug auto-generated! Or use: --slug "custom-slug-v1" for custom slug
```

See [QUICK_REFERENCE.md](../QUICK_REFERENCE.md) for complete examples and [NEW_PROJECT_SETUP_GUIDE.md](../NEW_PROJECT_SETUP_GUIDE.md) for details.

### Directory Structure (Created by Setup Script):
```
c:/dev/Autopack/.autonomous_runs/<project-slug>/
├── WHATS_LEFT_TO_BUILD.md          # Task definitions (any phase)
├── scripts/
│   └── autopack_runner.py          # Generic runner (auto-copied)
├── PROJECT_README.md               # Auto-generated docs
└── run.sh                          # Wrapper script (optional)
```

### Generic Command Template:
```bash
cd c:/dev/Autopack/.autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive
```

**Key Difference**:
- ❌ Old: `autopack_phase2_runner.py` (hardcoded to Phase 2, FileOrganizer-specific)
- ✅ New: `autopack_runner.py` (works for any project, any phase)

**No manual script revision needed** - the setup script handles everything!

---

## Requirements for Magic Phrase to Work

### 1. Project Structure
The project must follow the `.autonomous_runs/<project-slug>/` pattern with:
- `WHATS_LEFT_TO_BUILD.md`: Task definitions in Autopack format
- `scripts/autopack_phase2_runner.py`: Runner with auto-service-start
- `.claude/settings.json`: Must include `"Bash(uvicorn:*)"` in allowlist

### 2. Runner Script Features
The `autopack_phase2_runner.py` must have:
- ✅ Auto-service-start capability (`start_autopack_service()` method)
- ✅ Health check with timeout
- ✅ `--non-interactive` flag support
- ✅ Graceful cleanup (atexit handlers)
- ✅ Windows/Unix compatibility

### 3. Cursor Configuration
`.claude/settings.json` must allow:
```json
{
  "permissions": {
    "allow": [
      "Bash(python:*)",
      "Bash(uvicorn:*)"
    ]
  }
}
```

---

## Example Usage in Cursor

### User Message:
```
RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.
```

### Cursor AI Response:
```
I'll trigger the fully autonomous Phase 2 build for FileOrganizer.

[Executes:]
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive

[Output:]
================================================================================
FILEORGANIZER PHASE 2 - AUTOPACK AUTONOMOUS BUILD
================================================================================

[NON-INTERACTIVE MODE] Proceeding with full Phase 2 autonomous build...
[NON-INTERACTIVE MODE] Will auto-start Autopack service if needed...

[Step 1/5] Checking Autopack service...
[INFO] Autopack service not running at http://localhost:8000
[INFO] Auto-starting Autopack service...
[OK] Autopack service started successfully

[Step 2/5] Creating Autopack run...
[OK] Run created: fileorganizer-phase2-20251128-143256

[Step 3/5] Monitoring run progress...
[Polling every 30 seconds...]
[30s] Progress: 11.1% | Phase: Test Suite Fixes | Tokens: 8245/150000
...
```

---

## Advanced: Custom Configuration

### Override API URL:
```bash
export AUTOPACK_API_URL=http://custom-host:8000
python scripts/autopack_phase2_runner.py --non-interactive
```

### Override Token Budget:
Edit `autopack_phase2_runner.py` line 102-107:
```python
"token_cap": 200000,  # Default: 150000
```

### Override Max Duration:
```python
"max_duration_minutes": 600,  # Default: 300 (5 hours)
```

---

## Troubleshooting Magic Phrase Execution

### Issue: Cursor doesn't recognize the magic phrase
**Solution**: Ensure the phrase follows exact pattern:
- ✅ `RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.`
- ❌ `Run autopack phase 2 for FileOrganizer`
- ❌ `Execute Phase 2 for FileOrganizer`

### Issue: Service auto-start fails
**Possible causes**:
1. Port 8000 already in use
2. Missing uvicorn in allowlist
3. Python environment issues

**Solution**: Check `.claude/settings.json` and port availability

### Issue: Non-interactive mode prompts for input
**Possible causes**:
- `--non-interactive` flag not passed
- Old version of runner script

**Solution**: Ensure you're using the latest runner with `--non-interactive` support

---

## Summary

**Magic Phrase**: `RUN AUTOPACK PHASE 2 END-TO-END for <ProjectName> now.`

**Command**: `python scripts/autopack_phase2_runner.py --non-interactive`

**Result**: Fully autonomous Phase 2 execution with zero manual intervention

This pattern enables true "one-click" autonomous builds for any project following the Autopack v7 playbook.
