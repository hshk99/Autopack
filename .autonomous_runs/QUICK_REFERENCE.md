# Autopack Magic Phrase - Quick Reference

## For FileOrganizer (Current Project)

### Magic Phrase:
```
RUN AUTOPACK END-TO-END for FileOrganizer now.
```

### Or use legacy phrase:
```
RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.
```

Both execute:
```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive
```

---

## For NEW Projects

### Step 1: Setup New Project (One-Time)

```bash
cd c:/dev/Autopack/.autonomous_runs
python setup_new_project.py --name "MyApp" --slug "my-app-v1"
```

### Step 2: Define Tasks

Edit `.autonomous_runs/my-app-v1/WHATS_LEFT_TO_BUILD.md` with your project tasks.

### Step 3: Run with Magic Phrase

```
RUN AUTOPACK END-TO-END for MyApp now.
```

**That's it!** No manual script revision needed.

---

## Important Distinctions

### FileOrganizer-Specific Files (DO NOT COPY)
- ❌ `autopack_phase2_runner.py` - Hardcoded for FileOrganizer Phase 2
- ❌ `WHATS_LEFT_TO_BUILD.md` - FileOrganizer tasks only
- ❌ `HOW_TO_RUN_PHASE2.md` - FileOrganizer documentation

### Generic Files (COPY TO NEW PROJECTS)
- ✅ `autopack_runner.py` - Works for any project/phase
- ✅ Pattern is automatically copied by `setup_new_project.py`

---

## FAQ

**Q: Why does `autopack_phase2_runner.py` have "phase2" in the name?**
A: It's FileOrganizer-specific and hardcoded to Phase 2. For new projects, use the generic `autopack_runner.py`.

**Q: Do I need to manually revise scripts for each new project?**
A: No! Run `setup_new_project.py` and it handles everything automatically.

**Q: Can I use the same magic phrase for all projects?**
A: Yes! The pattern is: `RUN AUTOPACK END-TO-END for <ProjectName> now.`

**Q: What if I want to manually setup a project?**
A: See [NEW_PROJECT_SETUP_GUIDE.md](NEW_PROJECT_SETUP_GUIDE.md) for manual setup instructions.

---

## Prompt for Cursor (New Project Setup)

When starting a new project, give Cursor this prompt:

```
Setup a new Autopack autonomous project:

Project Name: MyApp
Project Slug: my-app-v1

Run:
python .autonomous_runs/setup_new_project.py --name "MyApp" --slug "my-app-v1"

Then help me define tasks in WHATS_LEFT_TO_BUILD.md.
```

---

## Files Created by Setup Script

```
.autonomous_runs/my-app-v1/
├── scripts/
│   └── autopack_runner.py          # Generic runner (auto-copied)
├── WHATS_LEFT_TO_BUILD.md          # Task template
├── PROJECT_README.md               # Auto-generated docs
└── run.sh                          # Wrapper script
```

Magic phrase works immediately after setup!

---

## See Also

- [NEW_PROJECT_SETUP_GUIDE.md](NEW_PROJECT_SETUP_GUIDE.md) - Comprehensive setup guide
- [file-organizer-app-v1/MAGIC_PHRASE.md](file-organizer-app-v1/MAGIC_PHRASE.md) - Full magic phrase documentation
- [file-organizer-app-v1/HOW_TO_RUN_PHASE2.md](file-organizer-app-v1/HOW_TO_RUN_PHASE2.md) - FileOrganizer-specific guide
