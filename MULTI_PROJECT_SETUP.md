# Multi-Project Setup Guide

## Problem

Currently, Autopack builds code in its own directory, which means:
- ❌ All projects share the same workspace
- ❌ Code from different projects gets mixed together
- ❌ No project isolation

## Solution

Point Autopack to build in **separate project directories** outside of Autopack itself.

---

## Option 1: Simple - One Project at a Time

### Setup:

1. **Create your project directory:**
   ```bash
   mkdir c:\Projects\my-app
   cd c:\Projects\my-app
   git init
   ```

2. **Update Supervisor to target that directory:**

   Edit `integrations/supervisor.py`:
   ```python
   class Supervisor:
       def __init__(
           self,
           api_url: str = "http://localhost:8000",
           openai_api_key: Optional[str] = None,
           target_repo_path: str = "c:\\Projects\\my-app"  # ← Add this
       ):
           self.target_repo_path = target_repo_path
           # ... rest of init
   ```

3. **Pass target path to GitAdapter:**

   When calling Builder/Auditor endpoints, include the target path so GitAdapter knows where to apply patches.

---

## Option 2: Multi-Project Management (Recommended)

### Directory Structure:

```
c:\Projects\
├── my-web-app\
│   ├── .autonomous_runs\     # Runs for this project
│   ├── .git\
│   └── src\
│
├── my-api-service\
│   ├── .autonomous_runs\
│   ├── .git\
│   └── src\
│
└── my-data-pipeline\
    ├── .autonomous_runs\
    ├── .git\
    └── src\

c:\dev\Autopack\               # Orchestrator (separate)
├── config\
├── integrations\
└── src\autopack\
```

### Usage:

```python
from integrations.supervisor import Supervisor

# Build project A
supervisor_a = Supervisor(
    target_repo_path="c:\\Projects\\my-web-app"
)
supervisor_a.run_autonomous_build(...)

# Build project B (completely isolated)
supervisor_b = Supervisor(
    target_repo_path="c:\\Projects\\my-api-service"
)
supervisor_b.run_autonomous_build(...)
```

---

## Option 3: Environment Variable (Most Flexible)

### Setup:

1. **Add to .env:**
   ```
   TARGET_REPO_PATH=c:\Projects\current-project
   ```

2. **Supervisor reads it:**
   ```python
   target_repo = os.getenv("TARGET_REPO_PATH", os.getcwd())
   ```

3. **Switch projects by changing .env**

---

## What Needs to Be Updated

To properly support isolated projects, these files need changes:

### 1. **Supervisor** (integrations/supervisor.py)
- Add `target_repo_path` parameter
- Pass to Builder/Auditor

### 2. **GitAdapter** (src/autopack/git_adapter.py)
- Use target_repo_path instead of hardcoded /workspace
- Apply patches to target repository

### 3. **Builder** (src/autopack/openai_clients.py)
- Read file context from target repository
- Generate patches relative to target

### 4. **File Layout** (src/autopack/file_layout.py)
- Create `.autonomous_runs/` in target repository
- Not in Autopack directory

---

## Quick Implementation

### For Now (Manual Workaround):

1. **Create project directory:**
   ```bash
   mkdir c:\Projects\test-app
   cd c:\Projects\test-app
   git init
   echo "# Test App" > README.md
   git add README.md
   git commit -m "Initial commit"
   ```

2. **Tell Docker to mount it:**

   Update `docker-compose.yml`:
   ```yaml
   volumes:
     - c:\Projects\test-app:/workspace  # Mount your project
     - ./.autonomous_runs:/app/.autonomous_runs
   ```

3. **Restart Docker:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

4. **Run build:**
   ```bash
   python integrations/supervisor.py
   ```

Now patches get applied to `/workspace` which is your project, not Autopack!

---

## Full Implementation (Needed)

To properly support multiple projects, I can implement:

**Would you like me to:**
1. ✅ Add `target_repo_path` parameter to Supervisor
2. ✅ Update GitAdapter to use target path
3. ✅ Make Builder read from target repository
4. ✅ Create isolated `.autonomous_runs/` per project

This would take ~30 minutes and give you full project isolation.

---

## Current State

**Right now:**
- ❌ Projects are NOT isolated
- ❌ Everything builds in Autopack directory
- ⚠️ Need to manually mount different projects in Docker

**After implementation:**
- ✅ Each project has its own directory
- ✅ Multiple projects can be managed simultaneously
- ✅ Clean separation between orchestrator and projects
- ✅ Just pass `target_repo_path="c:\\Projects\\my-app"`

---

## Which Option Do You Want?

1. **Quick workaround** - Manually change Docker mount
2. **Full implementation** - I'll add proper multi-project support now
3. **Later** - Focus on testing single project first

Let me know!
