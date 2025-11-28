# How to Setup a New Autopack Autonomous Project

This guide explains how to setup a new project so the magic phrase pattern works automatically.

**TL;DR**: You do NOT need to manually revise scripts for each new project. Just run the setup script!

---

## Quick Start (Automated Setup)

### Step 1: Run Setup Script

```bash
cd c:/dev/Autopack/.autonomous_runs
python setup_new_project.py --name "MyApp" --slug "my-app-v1"
```

**That's it!** The magic phrase now works:
```
RUN AUTOPACK END-TO-END for MyApp now.
```

---

## What the Setup Script Does

The `setup_new_project.py` script automatically creates:

```
.autonomous_runs/<project-slug>/
├── scripts/
│   └── autopack_runner.py          # Generic runner (copied from template)
├── WHATS_LEFT_TO_BUILD.md          # Empty task template
├── PROJECT_README.md               # Auto-generated documentation
└── run.sh                          # Wrapper script
```

### Key Points:

1. **`autopack_runner.py` is generic** - No modifications needed!
   - Auto-detects project name from directory structure
   - Works for any phase (Phase 1, 2, 3, etc.)
   - Reads tasks from `WHATS_LEFT_TO_BUILD.md`

2. **Magic phrase works immediately** after setup
   - Pattern: `RUN AUTOPACK END-TO-END for <ProjectName> now.`
   - Cursor executes: `cd <project-dir> && python scripts/autopack_runner.py --non-interactive`

3. **No per-project customization required**
   - Just define tasks in `WHATS_LEFT_TO_BUILD.md`
   - The runner handles everything else automatically

---

## Manual Setup (If Needed)

If you prefer manual setup or the script isn't available:

### Step 1: Create Project Directory

```bash
cd c:/dev/Autopack/.autonomous_runs
mkdir my-new-project-v1
mkdir my-new-project-v1/scripts
```

### Step 2: Copy Generic Runner

```bash
cp file-organizer-app-v1/scripts/autopack_runner.py \
   my-new-project-v1/scripts/autopack_runner.py
```

**Important**: Copy `autopack_runner.py` (generic), NOT `autopack_phase2_runner.py` (FileOrganizer-specific)!

### Step 3: Create WHATS_LEFT_TO_BUILD.md

Create `my-new-project-v1/WHATS_LEFT_TO_BUILD.md`:

```markdown
# MyNewProject - Tasks

## Phase 1: Initial Implementation

### Task 1: Setup Project Structure
**Phase ID**: `my-new-project-task1`
**Category**: backend
**Complexity**: low
**Description**: Create initial project structure

**Acceptance Criteria**:
- [ ] Directory structure created
- [ ] Configuration files setup

**Dependencies**: None
```

### Step 4: Test Magic Phrase

Say to Cursor:
```
RUN AUTOPACK END-TO-END for MyNewProject now.
```

Cursor will execute:
```bash
cd c:/dev/Autopack/.autonomous_runs/my-new-project-v1
python scripts/autopack_runner.py --non-interactive
```

---

## Understanding the Architecture

### Why autopack_phase2_runner.py Has "phase2"

**`autopack_phase2_runner.py`** is **FileOrganizer-specific**:
- Hardcoded with FileOrganizer's Phase 2 task definitions
- Generates run IDs like `fileorganizer-phase2-{timestamp}`
- Only use this for FileOrganizer project
- Kept for backward compatibility

### Why autopack_runner.py is Generic

**`autopack_runner.py`** is **project-agnostic**:
- Auto-detects project name from directory path
- Reads tasks dynamically from `WHATS_LEFT_TO_BUILD.md`
- Generates run IDs like `{project-name}-{timestamp}`
- Works for any project, any phase
- **This is what you should copy to new projects**

---

## Cursor Prompt for New Projects

When starting a new project, give Cursor this prompt:

```
Setup a new Autopack autonomous project:

Project Name: MyApp
Project Slug: my-app-v1

Run the setup script:
python .autonomous_runs/setup_new_project.py --name "MyApp" --slug "my-app-v1"

Then help me define tasks in WHATS_LEFT_TO_BUILD.md for this project.
```

Cursor will:
1. Run the setup script
2. Create all necessary files
3. Help you define project tasks
4. Confirm magic phrase is ready

---

## Examples

### Example 1: E-commerce Platform

```bash
python setup_new_project.py --name "ShopApp" --slug "shop-app-v1"
```

Magic phrase:
```
RUN AUTOPACK END-TO-END for ShopApp now.
```

### Example 2: API Gateway

```bash
python setup_new_project.py --name "APIGateway" --slug "api-gateway-v1"
```

Magic phrase:
```
RUN AUTOPACK END-TO-END for APIGateway now.
```

### Example 3: ChatBot

```bash
python setup_new_project.py --name "ChatBot" --slug "chatbot-v1"
```

Magic phrase:
```
RUN AUTOPACK END-TO-END for ChatBot now.
```

---

## FAQ

### Q1: Do I need to modify autopack_runner.py for each project?

**A: No!** The generic `autopack_runner.py` auto-detects the project name and reads tasks from `WHATS_LEFT_TO_BUILD.md`. Just copy it as-is.

### Q2: What about phase-specific behavior?

**A:** The runner doesn't care about phases. It reads whatever tasks you define in `WHATS_LEFT_TO_BUILD.md`. You can organize tasks into Phase 1, Phase 2, Phase 3, etc., and the runner will execute them all.

### Q3: Can I customize the runner for my project?

**A:** Yes, but usually not needed. If you need project-specific logic, create a new runner like `my_project_runner.py`, but the generic one should work for 95% of cases.

### Q4: What if I want different token budgets or timeouts?

**A:** Edit the run configuration in `autopack_runner.py` or pass environment variables:
```bash
export AUTOPACK_TOKEN_CAP=200000
export AUTOPACK_MAX_DURATION=600
```

### Q5: Should I use autopack_phase2_runner.py for new projects?

**A: No!** That file is FileOrganizer-specific. Use the generic `autopack_runner.py` instead.

---

## Summary

**For New Projects**:
1. Run: `python setup_new_project.py --name "MyApp" --slug "my-app-v1"`
2. Define tasks in `WHATS_LEFT_TO_BUILD.md`
3. Use magic phrase: `RUN AUTOPACK END-TO-END for MyApp now.`

**You do NOT need to**:
- Manually revise scripts for each project
- Create custom runners (unless you have special needs)
- Modify the generic `autopack_runner.py`

The setup script handles everything automatically!
