# Contributing to Autopack

Thank you for your interest in contributing to Autopack! This guide will help you get started with development, testing, and submitting pull requests.

---

## Table of Contents

1. [Development Setup](#development-setup)
2. [Running Tests](#running-tests)
3. [Code Style](#code-style)
4. [Pull Request Process](#pull-request-process)
5. [Project Structure](#project-structure)
6. [Common Tasks](#common-tasks)
7. [Debugging Tips](#debugging-tips)
8. [Getting Help](#getting-help)

---

## Development Setup

### Prerequisites

- Python 3.11+
- Git
- SQLite (included with Python)

### Installation

```bash
# Clone the repository
git clone https://github.com/yourusername/autopack.git
cd autopack

# Install dependencies
pip install -e .

# Initialize database
PYTHONPATH=src python -c "from autopack.database import init_db; init_db()"
```

### Environment Variables

Create a `.env` file in the project root:

```bash
PYTHONPATH=src
DATABASE_URL=sqlite:///autopack.db
ANTHROPIC_API_KEY=your_key_here  # Required for LLM calls
TELEMETRY_DB_ENABLED=0  # Optional: enable telemetry persistence
```

### Verify Installation

```bash
# Check database
PYTHONPATH=src python scripts/db_identity_check.py

# Start API server (Terminal 1)
PYTHONPATH=src uvicorn autopack.main:app --host 127.0.0.1 --port 8000

# Test executor (Terminal 2)
PYTHONPATH=src python -m autopack.autonomous_executor --help
```

---

## Running Tests

### Full Test Suite

```bash
PYTHONPATH=src pytest tests/
```

### Specific Test Files

```bash
# Unit tests
PYTHONPATH=src pytest tests/test_token_estimator.py

# Integration tests
PYTHONPATH=src pytest tests/test_autonomous_executor_import.py
```

### Test Coverage

```bash
PYTHONPATH=src pytest --cov=src/autopack --cov-report=html tests/
# Open htmlcov/index.html to view coverage report
```

### Smoke Tests

For quick validation of core functionality:

```bash
# Test imports
PYTHONPATH=src python -c "from autopack.autonomous_executor import AutonomousExecutor"

# Test database
PYTHONPATH=src python -c "from autopack.database import SessionLocal; SessionLocal().execute('SELECT 1')"
```

---

## Code Style

### Python Style Guide

- Follow [PEP 8](https://pep8.org/)
- Use type hints for function signatures
- Maximum line length: 120 characters
- Use docstrings for all public functions/classes

### Example

```python
from typing import List, Optional

def estimate_tokens(
    deliverables: List[str],
    category: str,
    complexity: str = "medium"
) -> int:
    """Estimate token budget for a phase.
    
    Args:
        deliverables: List of file paths to create/modify
        category: Phase category (e.g., 'implementation', 'docs')
        complexity: Phase complexity ('low', 'medium', 'high')
    
    Returns:
        Estimated output tokens needed
    """
    # Implementation here
    pass
```

### Formatting

We recommend using `black` for automatic formatting:

```bash
pip install black
black src/ tests/
```

---

## Pull Request Process

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
# or
git checkout -b fix/issue-description
```

### 2. Make Changes

- Write clear, focused commits
- Add tests for new functionality
- Update documentation as needed
- Ensure all tests pass

### 3. Commit Guidelines

```bash
# Good commit messages:
git commit -m "Add token estimation for documentation phases"
git commit -m "Fix deliverables normalization for nested dicts"
git commit -m "Update CONTRIBUTING.md with testing section"

# Include issue references:
git commit -m "Fix #123: Resolve API schema validation error"
```

### 4. Push and Create PR

```bash
git push origin feature/your-feature-name
```

Then create a pull request on GitHub with:

- **Title**: Clear, concise description
- **Description**: What changed and why
- **Testing**: How you tested the changes
- **Related Issues**: Link to relevant issues

### 5. PR Review Checklist

- [ ] All tests pass
- [ ] Code follows style guidelines
- [ ] Documentation updated
- [ ] No merge conflicts
- [ ] Commit messages are clear

---

## Project Structure

```
autopack/
├── src/autopack/          # Core application code
│   ├── autonomous_executor.py  # Main execution engine
│   ├── token_estimator.py      # Token budget estimation
│   ├── quality_gate.py         # Quality validation
│   └── diagnostics/            # Diagnostic tools
├── tests/                 # Test suite
├── scripts/               # Utility scripts
├── docs/                  # Documentation
│   ├── BUILD_HISTORY.md   # Build changelog
│   ├── DEBUG_LOG.md       # Debug history
│   └── guides/            # User guides
└── migrations/            # Database migrations
```

### Key Modules

- **autonomous_executor.py**: Orchestrates phase execution
- **token_estimator.py**: Predicts token budgets
- **quality_gate.py**: Validates phase outputs
- **anthropic_clients.py**: LLM API integration
- **database.py**: Database models and session management

---

## Common Tasks

### Add a New Feature

1. Create feature branch
2. Implement in `src/autopack/`
3. Add tests in `tests/`
4. Update `docs/BUILD_HISTORY.md`
5. Submit PR

### Fix a Bug

1. Create fix branch
2. Add regression test
3. Implement fix
4. Update `docs/DEBUG_LOG.md` if systemic
5. Submit PR

### Update Documentation

1. Edit relevant `.md` files in `docs/`
2. Keep line count ≤200 for guides
3. Use clear section headers
4. Submit PR

---

## Debugging Tips

### Enable Verbose Logging

```bash
export LOG_LEVEL=DEBUG
PYTHONPATH=src python -m autopack.autonomous_executor --run-id test-run
```

### Check Database State

```bash
PYTHONPATH=src python scripts/db_identity_check.py
```

### Inspect Run Artifacts

```bash
# View executor logs
tail -f .autonomous_runs/autopack/runs/<family>/<run_id>/run.log

# Check phase summaries
cat .autonomous_runs/autopack/runs/<family>/<run_id>/phases/phase_*.md
```

### Common Issues

**"No module named autopack"**
- Solution: Set `PYTHONPATH=src`

**"Database locked"**
- Solution: Only one executor per database. Stop other executors.

**"API server not responding"**
- Solution: Ensure API server is running on port 8000

---

## Getting Help

### Documentation

- [README.md](../README.md) - Project overview
- [QUICKSTART.md](QUICKSTART.md) - Quick start guide
- [BUILD_HISTORY.md](BUILD_HISTORY.md) - Build changelog
- [DEBUG_LOG.md](DEBUG_LOG.md) - Debug history

### Community

- **Issues**: Report bugs or request features on GitHub Issues
- **Discussions**: Ask questions in GitHub Discussions
- **Pull Requests**: Contribute code via pull requests

### Before Asking

1. Check existing documentation
2. Search closed issues
3. Review DEBUG_LOG.md for similar problems
4. Try the troubleshooting steps above

---

**Thank you for contributing to Autopack!** 🚀
