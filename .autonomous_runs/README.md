# Autopack Autonomous Runs

This directory contains autonomous project builds managed by Autopack v7 using the magic phrase pattern with Cursor AI.

---

## Quick Start

### Setup New Project

**Magic Phrase:**
```
SET UP NEW AUTOPACK PROJECT: <Project Name>
```

**Example:**
```
SET UP NEW AUTOPACK PROJECT: Shopping Cart
```

This automatically:
- Generates a slug (e.g., `shopping-cart-v1`)
- Creates project structure
- Copies generic runner script
- Sets up task template
- Makes the project ready to run

### Run Existing Project

**Default (Uses WHATS_LEFT_TO_BUILD.md):**
```
RUN AUTOPACK END-TO-END for <ProjectName> now.
```

**NEW: Run with Custom Task File:**
```
RUN AUTOPACK END-TO-END for <ProjectName> using <TaskFile.md> now.
```

**Examples:**
```
RUN AUTOPACK END-TO-END for FileOrganizer now.
RUN AUTOPACK END-TO-END for FileOrganizer using REVISED_PLAN_V2.md now.
RUN AUTOPACK END-TO-END for ShoppingCart using SPRINT_3_TASKS.md now.
```

---

## Custom Task File Support (NEW)

The generic `autopack_runner.py` now supports running Autopack with **any markdown task file**, not just WHATS_LEFT_TO_BUILD.md.

### Why Use Custom Task Files?

1. **Revised Plans**: When your plan changes, save it as `REVISED_PLAN_V2.md` and run it without overwriting the original
2. **Sprint Organization**: Organize tasks by sprint: `SPRINT_1_TASKS.md`, `SPRINT_2_TASKS.md`
3. **Hotfixes**: Create `HOTFIX_PLAN.md` for urgent fixes
4. **Feature Branches**: Feature-specific tasks in `FEATURE_AUTH_TASKS.md`
5. **Experimental Work**: Test new approaches in `EXPERIMENTAL_PLAN.md`

### Magic Phrase Syntax

**Pattern:**
```
RUN AUTOPACK END-TO-END for <ProjectName> using <TaskFile.md> now.
```

**What Cursor Executes:**
```bash
cd c:/dev/Autopack/.autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive --tasks-file "<TaskFile.md>"
```

### Task File Format

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

### Task 2: Another Task
**Phase ID**: `another-task-id`
**Category**: frontend
**Complexity**: medium
**Description**: Another description

**Acceptance Criteria**:
- [ ] Criterion 1

**Dependencies**: `unique-task-id`
```

### Benefits

- **Version Control**: Keep multiple plans in git, track changes with `git diff`
- **Safety**: Run experimental plans without disturbing main plan
- **Flexibility**: Switch between different execution strategies easily
- **Organization**: Separate concerns (hotfixes, sprints, features)
- **Rollback**: Easily return to previous plans if needed

---

## Project Structure

Each project follows this structure:

```
.autonomous_runs/<project-slug>/
├── scripts/
│   ├── autopack_runner.py          # Generic runner (works for any project)
│   └── autopack_phase2_runner.py   # Legacy (FileOrganizer-specific)
├── WHATS_LEFT_TO_BUILD.md          # Default task file
├── REVISED_PLAN_V2.md              # Optional: Revised plan
├── SPRINT_1_TASKS.md               # Optional: Sprint tasks
├── HOTFIX_PLAN.md                  # Optional: Hotfix tasks
├── PROJECT_README.md               # Project documentation
└── run.sh                          # Wrapper script (optional)
```

---

## Command-Line Usage

### Default Execution
```bash
cd .autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive
```

### Custom Task File
```bash
cd .autonomous_runs/<project-slug>
python scripts/autopack_runner.py --non-interactive --tasks-file "REVISED_PLAN_V2.md"
```

### Interactive Mode (asks for confirmation)
```bash
cd .autonomous_runs/<project-slug>
python scripts/autopack_runner.py
```

---

## Examples

### Example 1: Revised Plan

Your initial plan had 10 tasks, but after review, you revised it to 8 tasks with different priorities.

**Create revised plan:**
```bash
# Edit .autonomous_runs/my-project-v1/REVISED_PLAN_V2.md with new tasks
```

**Run revised plan:**
```
RUN AUTOPACK END-TO-END for MyProject using REVISED_PLAN_V2.md now.
```

### Example 2: Sprint-Based Development

You're doing agile development with 2-week sprints.

**Create sprint files:**
```bash
# .autonomous_runs/shopping-cart-v1/SPRINT_1_TASKS.md
# .autonomous_runs/shopping-cart-v1/SPRINT_2_TASKS.md
# .autonomous_runs/shopping-cart-v1/SPRINT_3_TASKS.md
```

**Run sprint 1:**
```
RUN AUTOPACK END-TO-END for ShoppingCart using SPRINT_1_TASKS.md now.
```

**Run sprint 2:**
```
RUN AUTOPACK END-TO-END for ShoppingCart using SPRINT_2_TASKS.md now.
```

### Example 3: Hotfix

Production bug requires urgent fix without disturbing main development plan.

**Create hotfix plan:**
```bash
# Edit .autonomous_runs/api-gateway-v1/HOTFIX_PLAN.md with urgent fixes
```

**Run hotfix:**
```
RUN AUTOPACK END-TO-END for APIGateway using HOTFIX_PLAN.md now.
```

### Example 4: Experimental Feature

You want to test a new approach without committing to the main plan.

**Create experimental plan:**
```bash
# Edit .autonomous_runs/chatbot-v1/EXPERIMENTAL_PLAN.md
```

**Run experiment:**
```
RUN AUTOPACK END-TO-END for ChatBot using EXPERIMENTAL_PLAN.md now.
```

---

## Environment Variables

```bash
# Autopack API URL (default: http://localhost:8000)
export AUTOPACK_API_URL=http://localhost:8000

# Autopack API Key (if authentication enabled)
export AUTOPACK_API_KEY=your-api-key-here
```

---

## Existing Projects

### FileOrganizer (file-organizer-app-v1)

FileOrganizer is the reference implementation demonstrating the magic phrase pattern.

**Run FileOrganizer:**
```
RUN AUTOPACK END-TO-END for FileOrganizer now.
```

**Run with custom plan:**
```
RUN AUTOPACK END-TO-END for FileOrganizer using REVISED_PLAN_V2.md now.
```

**Legacy (backward compatibility):**
```
RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.
```

---

## Key Files

- [QUICK_REFERENCE.md](QUICK_REFERENCE.md) - Quick reference for magic phrases
- [NEW_PROJECT_SETUP_GUIDE.md](NEW_PROJECT_SETUP_GUIDE.md) - Detailed setup guide
- [file-organizer-app-v1/MAGIC_PHRASE.md](file-organizer-app-v1/MAGIC_PHRASE.md) - Magic phrase documentation
- [file-organizer-app-v1/HOW_TO_RUN_PHASE2.md](file-organizer-app-v1/HOW_TO_RUN_PHASE2.md) - FileOrganizer-specific guide

---

## Troubleshooting

### Error: "No tasks found in <TaskFile.md>"

**Cause:** The task file is empty or doesn't follow Autopack format.

**Solution:** Ensure the file has tasks in the correct format:
```markdown
### Task 1: Task Name
**Phase ID**: `task-id`
**Category**: backend
**Complexity**: low
**Description**: Description

**Acceptance Criteria**:
- [ ] Criterion 1

**Dependencies**: None
```

### Error: "Tasks file not found: <TaskFile.md>"

**Cause:** The specified file doesn't exist in the project directory.

**Solution:** Create the file or check the filename spelling.

### Error: "Autopack service not available"

**Cause:** Autopack service is not running and auto-start failed.

**Solution:** Check port 8000 availability or manually start the service:
```bash
cd c:/dev/Autopack
uvicorn src.autopack.main:app --reload --host 0.0.0.0 --port 8000
```

---

## Summary

**For New Projects:**
```
SET UP NEW AUTOPACK PROJECT: MyApp
```

**For Running (Default):**
```
RUN AUTOPACK END-TO-END for MyApp now.
```

**For Running (Custom Task File):**
```
RUN AUTOPACK END-TO-END for MyApp using CUSTOM_TASKS.md now.
```

Fully autonomous execution with zero manual setup required!
