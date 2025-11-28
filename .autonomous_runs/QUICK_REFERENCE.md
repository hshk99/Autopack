# Autopack Magic Phrases - Quick Reference

## NEW PROJECT SETUP (Magic Phrase)

### Magic Phrase:
```
SET UP NEW AUTOPACK PROJECT: <Project Name>
```

### What It Does:
- **Auto-generates** a slug from your project name
- **Creates** complete project structure in `.autonomous_runs/`
- **Sets up** magic phrase for running the project
- **No manual slug needed!**

### Examples:

**Example 1: File Organizer**
```
User: SET UP NEW AUTOPACK PROJECT: File Organizer

Result:
→ Slug auto-generated: file-organizer-v1
→ Created: .autonomous_runs/file-organizer-v1/
→ Magic phrase ready: "RUN AUTOPACK END-TO-END for File Organizer now."
```

**Example 2: Shopping Cart**
```
User: SET UP NEW AUTOPACK PROJECT: Shopping Cart

Result:
→ Slug auto-generated: shopping-cart-v1
→ Created: .autonomous_runs/shopping-cart-v1/
→ Magic phrase ready: "RUN AUTOPACK END-TO-END for Shopping Cart now."
```

**Example 3: Todo App**
```
User: SET UP NEW AUTOPACK PROJECT: Todo App

Result:
→ Slug auto-generated: todo-app-v1
→ Created: .autonomous_runs/todo-app-v1/
→ Magic phrase ready: "RUN AUTOPACK END-TO-END for Todo App now."
```

**Example 4: My API Gateway**
```
User: SET UP NEW AUTOPACK PROJECT: My API Gateway

Result:
→ Slug auto-generated: my-api-gateway-v1
→ Created: .autonomous_runs/my-api-gateway-v1/
→ Magic phrase ready: "RUN AUTOPACK END-TO-END for My API Gateway now."
```

### What Cursor Does:
1. Runs: `python .autonomous_runs/setup_new_project.py --name "<Project Name>"`
2. Slug is auto-generated (no manual input needed!)
3. Tells you which slug was created
4. Confirms the run magic phrase is ready

---

## RUNNING EXISTING PROJECTS

### For FileOrganizer (Current Project)

**Magic Phrase**:
```
RUN AUTOPACK END-TO-END for FileOrganizer now.
```

**Or use legacy phrase**:
```
RUN AUTOPACK PHASE 2 END-TO-END for FileOrganizer now.
```

**Both execute**:
```bash
cd c:/dev/Autopack/.autonomous_runs/file-organizer-app-v1
python scripts/autopack_phase2_runner.py --non-interactive
```

---

### For NEW Projects

After setup, use this pattern:

**Magic Phrase**:
```
RUN AUTOPACK END-TO-END for <ProjectName> now.
```

**Examples**:
- `RUN AUTOPACK END-TO-END for Shopping Cart now.`
- `RUN AUTOPACK END-TO-END for Todo App now.`
- `RUN AUTOPACK END-TO-END for My API Gateway now.`

---

## IMPORTANT DISTINCTIONS

### FileOrganizer-Specific Files (DO NOT COPY)
- ❌ `autopack_phase2_runner.py` - Hardcoded for FileOrganizer Phase 2
- ❌ `WHATS_LEFT_TO_BUILD.md` - FileOrganizer tasks only
- ❌ `HOW_TO_RUN_PHASE2.md` - FileOrganizer documentation

### Generic Files (AUTOMATICALLY COPIED BY SETUP SCRIPT)
- ✅ `autopack_runner.py` - Works for any project/phase
- ✅ Automatically copied when you use: `SET UP NEW AUTOPACK PROJECT`

---

## WORKFLOW FOR NEW PROJECTS

### Step 1: Setup
```
SET UP NEW AUTOPACK PROJECT: MyApp
```

Cursor will:
- Auto-generate slug (e.g., `my-app-v1`)
- Create project structure
- Copy generic runner
- Tell you the magic phrase to use

### Step 2: Define Tasks
Edit `.autonomous_runs/my-app-v1/WHATS_LEFT_TO_BUILD.md` with your project tasks.

### Step 3: Run
```
RUN AUTOPACK END-TO-END for MyApp now.
```

**That's it!** No manual script revision, no thinking about slugs.

---

## SLUG AUTO-GENERATION

**You don't need to think about slugs anymore!**

The setup script automatically converts your project name to a filesystem-safe slug:

| Project Name | Auto-Generated Slug |
|-------------|---------------------|
| File Organizer | `file-organizer-v1` |
| Shopping Cart | `shopping-cart-v1` |
| Todo App | `todo-app-v1` |
| My API Gateway | `my-api-gateway-v1` |
| ChatBot | `chatbot-v1` |
| E-commerce Platform | `e-commerce-platform-v1` |

**Version Auto-Increment**:
If `my-app-v1` already exists, it creates `my-app-v2` automatically.

---

## FAQ

**Q: Do I need to provide a slug?**
A: **No!** The slug is auto-generated from your project name. Just use the magic phrase.

**Q: Can I use a custom slug?**
A: Yes, but only if you explicitly want to. Most users should just use the magic phrase and let it auto-generate.

**Q: What if I want a specific slug?**
A: You can manually run: `python setup_new_project.py --name "MyApp" --slug "custom-slug-v1"`

**Q: Do I need to manually revise scripts for each new project?**
A: **No!** The setup script handles everything automatically.

**Q: Should I use autopack_phase2_runner.py for new projects?**
A: **No!** That file is FileOrganizer-specific. The setup script copies the generic `autopack_runner.py` automatically.

---

## Complete Example Workflow

```
User: SET UP NEW AUTOPACK PROJECT: Blog CMS

Cursor:
→ Auto-generated slug: blog-cms-v1
→ Created: .autonomous_runs/blog-cms-v1/
→ Copied: autopack_runner.py
→ Created: WHATS_LEFT_TO_BUILD.md (template)
→ Created: PROJECT_README.md
→ Created: run.sh
→ Magic phrase ready: "RUN AUTOPACK END-TO-END for Blog CMS now."

User: [Edits WHATS_LEFT_TO_BUILD.md to define tasks]

User: RUN AUTOPACK END-TO-END for Blog CMS now.

Cursor:
→ Executes: cd .autonomous_runs/blog-cms-v1 && python scripts/autopack_runner.py --non-interactive
→ Auto-starts Autopack service
→ Runs all tasks from WHATS_LEFT_TO_BUILD.md
→ Generates reports
→ Done!
```

---

## See Also

- [NEW_PROJECT_SETUP_GUIDE.md](NEW_PROJECT_SETUP_GUIDE.md) - Detailed setup guide
- [file-organizer-app-v1/MAGIC_PHRASE.md](file-organizer-app-v1/MAGIC_PHRASE.md) - Full magic phrase documentation
- [file-organizer-app-v1/HOW_TO_RUN_PHASE2.md](file-organizer-app-v1/HOW_TO_RUN_PHASE2.md) - FileOrganizer-specific guide

---

## Summary

**For new projects, you only need to remember**:
```
SET UP NEW AUTOPACK PROJECT: <Your Project Name>
```

Cursor handles the rest - no slugs, no manual script editing, fully automated!
