# Automatic Task Format Conversion

Autopack now automatically converts narrative-style task files to the structured Autopack format!

---

## What This Means

You can write your implementation plans in **any natural format**, and Autopack will automatically convert them to the required structured format when you run.

**No manual conversion needed!**

---

## How It Works

### When You Run:

```
RUN AUTOPACK END-TO-END for MyProject using MY_PLAN.md now.
```

**Autopack automatically**:
1. Checks if `MY_PLAN.md` is in Autopack format
2. If NOT → Converts it automatically
3. Saves converted version as `MY_PLAN_autopack_<timestamp>.md`
4. Uses converted content for the run
5. Original file remains unchanged

---

## Supported Input Formats

### Format 1: Numbered Sections (Recommended)

```markdown
### 1. Test Suite Fixes
**Status**: Tests fail due to dependency conflicts
**Autonomous Complexity**: LOW (8K tokens)

**What Needs to Be Done**:
- Fix httpx/starlette version conflicts
- Update requirements.txt
- Ensure all tests pass

**Deliverables**:
- All 12 test files passing
- pytest.ini configured
- requirements.txt updated

### 2. Frontend Build System
**Status**: npm install/build skipped
**Autonomous Complexity**: LOW (5K tokens)

**What Needs to Be Done**:
- Run npm install
- Create production build
- Package Electron app

**Deliverables**:
- Production build created
- Electron app packaged
- package-lock.json committed
```

### Format 2: Simple Numbered List

```markdown
1. Fix Test Suite
   Fix dependency conflicts in test suite. Update httpx and starlette versions.
   Ensure all 12 test files pass.

2. Setup Frontend Build
   Run npm install and create production build for Electron app.
   Package app for distribution.

3. Docker Deployment
   Create Dockerfile and docker-compose.yml for multi-container setup.
   Test local deployment.
```

### Format 3: Task Sections

```markdown
## Task 1: Authentication System
Implement user authentication with JWT tokens.
Add user registration and login endpoints.
Create frontend login/register pages.

Deliverables:
- User model created
- JWT authentication working
- Login/register UI complete

## Task 2: Database Setup
Create database schema and migrations.
Setup SQLAlchemy models.
Add indexes for performance.
```

---

## Auto-Converted Output Format

All formats above are automatically converted to:

```markdown
### Task 1: Test Suite Fixes
**Phase ID**: `myproject-task1`
**Category**: testing
**Complexity**: low
**Description**: Fix dependency conflicts in test suite. Update httpx and starlette versions. Ensure all 12 test files pass.

**Acceptance Criteria**:
- [ ] All 12 test files passing
- [ ] pytest.ini configured
- [ ] requirements.txt updated

**Dependencies**: None

---

### Task 2: Frontend Build System
**Phase ID**: `myproject-task2`
**Category**: frontend
**Complexity**: low
**Description**: Run npm install and create production build for Electron app. Package app for distribution.

**Acceptance Criteria**:
- [ ] Production build created
- [ ] Electron app packaged
- [ ] package-lock.json committed

**Dependencies**: `myproject-task1`

---
```

---

## Intelligent Inference

The converter automatically infers:

### Complexity (low/medium/high)

**LOW** indicators:
- Keywords: "fix", "update", "simple", "quick", "minor", "bugfix"
- Token estimates: <8,000 tokens
- Short descriptions

**MEDIUM** indicators:
- Keywords: "add", "create", "implement"
- Token estimates: 8,000-15,000 tokens
- Moderate scope

**HIGH** indicators:
- Keywords: "architecture", "migration", "authentication", "security", "complex", "refactor"
- Token estimates: >15,000 tokens
- Large scope

### Category (backend/frontend/database/api/testing/docs/deployment)

Based on keyword matching:
- **backend**: "backend", "api", "server", "service", "python", "fastapi"
- **frontend**: "frontend", "ui", "react", "component", "electron", "npm", "css"
- **database**: "database", "sql", "migration", "schema", "query"
- **api**: "api", "rest", "endpoint", "request", "response"
- **testing**: "test", "pytest", "unit test", "integration"
- **docs**: "documentation", "readme", "guide", "markdown"
- **deployment**: "docker", "deploy", "container", "production"

### Acceptance Criteria

Extracted from:
- **Deliverables** sections
- Bullet points (-, •, ✅)
- Auto-generated if not found

### Dependencies

Simple heuristic:
- If task mentions "depend", "require", "after", "first" → links to previous task
- Otherwise → "None"

---

## Example: Real FileOrganizer Conversion

### Input (Narrative Format):

```markdown
## Phase 2: Beta Release (Autopack-Ready)

### 1. Test Suite Fixes (High Priority)
**Status**: Tests exist but fail due to dependency conflicts
**Autonomous Complexity**: LOW (2-3 hours, ~8K tokens)

**What Autopack Would Do**:
```bash
# Fix httpx/starlette version conflicts
Edit requirements.txt → resolve version pins
pip install --upgrade httpx starlette
pytest tests/ -v → validate all pass
```

**Deliverables**:
- ✅ All 12 test files passing
- ✅ pytest.ini with proper configuration
- ✅ Updated requirements.txt with compatible versions

**Estimated Autopack Token Usage**: 8,000 tokens
**Confidence**: 95% (straightforward dependency resolution)

### 2. Frontend Build System (High Priority)
**Status**: npm install/build skipped (node_modules not committed)
**Autonomous Complexity**: LOW (1-2 hours, ~5K tokens)

**What Autopack Would Do**:
```bash
cd frontend
npm install → install all dependencies
npm run build → create production build
npm run package → create distributable
```

**Deliverables**:
- ✅ node_modules installed (locally, not committed)
- ✅ Production build created (dist/)
- ✅ Electron app packaged for distribution
- ✅ package-lock.json committed

**Estimated Autopack Token Usage**: 5,000 tokens
**Confidence**: 90% (standard npm workflow)
```

### Output (Autopack Format):

```markdown
### Task 1: Test Suite Fixes
**Phase ID**: `fileorg-p2-test-fixes`
**Category**: testing
**Complexity**: low
**Description**: Fix test suite dependency conflicts (httpx/starlette version issues). Resolve version pins in requirements.txt and ensure all 12 test files pass.

**Acceptance Criteria**:
- [ ] All 12 test files passing
- [ ] pytest.ini with proper configuration
- [ ] Updated requirements.txt with compatible versions
- [ ] No dependency conflicts

**Dependencies**: None

---

### Task 2: Frontend Build System
**Phase ID**: `fileorg-p2-frontend-build`
**Category**: frontend
**Complexity**: low
**Description**: Setup frontend build system. Run npm install, create production build, test Electron packaging, and commit package-lock.json.

**Acceptance Criteria**:
- [ ] node_modules installed (locally)
- [ ] Production build created (dist/)
- [ ] Electron app packaged for distribution
- [ ] package-lock.json committed

**Dependencies**: None

---
```

---

## Manual Conversion (Optional)

If you want to manually convert a file before running:

```bash
cd .autonomous_runs
python task_format_converter.py MY_PLAN.md
```

**Options**:
- `--output FILENAME` - Save to different file
- `--no-backup` - Don't create backup
- `--check-only` - Only check if file is in Autopack format

---

## Benefits

### 1. Write Plans Your Way
- Use whatever format feels natural
- No need to learn structured format upfront
- Focus on planning, not formatting

### 2. Automatic Quality
- Consistent Phase IDs (project-task1, project-task2, etc.)
- Proper categorization (backend, frontend, etc.)
- Accurate complexity inference
- Clean acceptance criteria

### 3. Preserve Flexibility
- Original file never changed
- Converted version saved separately
- Easy to iterate on plans
- Version control friendly

### 4. Works Everywhere
- All future projects get this for free
- No setup needed per project
- Magic phrase works with any file format

---

## Troubleshooting

### "Unable to auto-convert task file"

**Cause**: Converter couldn't find recognizable task sections

**Solution**: Use numbered sections or list format
```markdown
### 1. Task Name
Description...

### 2. Another Task
Description...
```

Or simple list:
```markdown
1. Task Name
   Description...

2. Another Task
   Description...
```

### "File is already in Autopack format"

**Info**: No conversion needed - file is correctly formatted

### Conversion doesn't detect tasks correctly

**Solution**: Make task sections more explicit with numbers:
- Use `### 1. Task Name` not just `### Task Name`
- Or use `## Task 1: Name` format
- Include some keywords (deliverables, description, etc.)

---

## Best Practices

### For Best Auto-Conversion Results:

1. **Use numbered sections** (### 1., ### 2., etc.)
2. **Include complexity hints** ("LOW", "MEDIUM", "HIGH" or token estimates)
3. **Add deliverables section** (bullet points of what's expected)
4. **Mention category keywords** (frontend, backend, test, docker, etc.)
5. **Keep descriptions concise** (1-2 paragraphs max)

### Example Template:

```markdown
### 1. [Task Name]
**Complexity**: [LOW/MEDIUM/HIGH] ([token estimate])

**Description**:
What needs to be built...

**Deliverables**:
- [ ] Deliverable 1
- [ ] Deliverable 2
- [ ] Deliverable 3

### 2. [Next Task]
...
```

---

## Summary

**You can now write implementation plans in ANY format you like!**

Just run:
```
RUN AUTOPACK END-TO-END for MyProject using MY_PLAN.md now.
```

Autopack handles the rest - automatically converting, formatting, and executing your tasks.

**No manual work required!**
