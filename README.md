# Autopack Framework

**Autonomous AI Code Generation Framework**

Autopack is a framework for orchestrating autonomous AI agents (Builder and Auditor) to plan, build, and verify software projects. It uses a structured approach with phased execution, quality gates, and self-healing capabilities.

---

## 📚 Documentation

Detailed documentation is available in the `archive/` directory:

- **[Archive Index](archive/ARCHIVE_INDEX.md)**: Master index of all documentation.
- **[Autonomous Executor](archive/CONSOLIDATED_REFERENCE.md#autonomous-executor-readme)**: Guide to the orchestration system.
- **[Learned Rules](LEARNED_RULES_README.md)**: System for preventing recurring errors.

## 🏗️ Project Structure

```
C:/dev/Autopack/
├── .autonomous_runs/         # Runtime data and project-specific archives
│   ├── file-organizer-app-v1/# Example Project: File Organizer
│   └── ...
├── archive/                  # Framework documentation archive
├── src/
│   └── autopack/             # Core framework code
│       ├── autonomous_executor.py  # Main orchestration loop
│       ├── archive_consolidator.py # Documentation management
│       ├── debug_journal.py        # Self-healing system wrapper
│       └── ...
├── scripts/                  # Utility scripts
└── tests/                    # Framework tests
```

## 🚀 Key Features

- **Autonomous Orchestration**: Wires Builder and Auditor agents to execute phases automatically.
- **Self-Healing**: Automatically logs errors, fixes, and extracts prevention rules (`archive_consolidator.py`).
- **Quality Gates**: Enforces risk-based checks before code application.
- **Project Separation**: strictly separates runtime data and docs for different projects (e.g., `file-organizer-app-v1`).

## 🛠️ Usage

### Running an Autonomous Build

```bash
python src/autopack/autonomous_executor.py --run-id my-new-run
```

### Consolidating Documentation

To tidy up and consolidate documentation across projects:

```bash
python scripts/consolidate_docs.py
```

This will:
1. Scan all documentation files.
2. Sort them into project-specific archives (`archive/` vs `.autonomous_runs/<project>/archive/`).
3. Create consolidated reference files (`CONSOLIDATED_DEBUG.md`, etc.).
4. Move processed files to `superseded/`.

---

**Version**: 0.1.9
**License**: MIT
