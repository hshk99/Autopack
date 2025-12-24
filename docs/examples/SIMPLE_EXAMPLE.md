# Simple Example: Getting Started with AutoPack

This guide walks you through a basic AutoPack workflow from start to finish.

## Prerequisites

- Python 3.8 or higher
- Git installed and configured
- A GitHub account (for remote repository features)

## Installation

```bash
pip install autopack
```

## Basic Workflow

### 1. Initialize a New Project

Create a new directory and initialize AutoPack:

```bash
mkdir my-project
cd my-project
autopack init
```

This creates the necessary configuration files and directory structure.

### 2. Define Your First Task

Create a simple task specification:

```bash
autopack task create "Add a hello world function to utils.py"
```

Or create a task file manually in `.autonomous_runs/tasks/`:

```yaml
# .autonomous_runs/tasks/hello_world.yaml
name: Add hello world function
description: Create a simple hello world function in utils.py
category: feature
complexity: low
priority: medium
```

### 3. Run the Task

Execute the autonomous build:

```bash
autopack run
```

AutoPack will:
- Analyze your codebase
- Generate the necessary code changes
- Create a branch for the changes
- Apply the changes and commit them

### 4. Review the Changes

Check the generated code:

```bash
git diff main
```

Review the commit log:

```bash
git log --oneline
```

### 5. Test and Merge

Run your tests:

```bash
pytest
```

If everything looks good, merge the changes:

```bash
git checkout main
git merge autopack/hello-world
```

## Example Output

After running the task, you might see a new file `utils.py`:

```python
def hello_world(name: str = "World") -> str:
    """Return a friendly greeting.
    
    Args:
        name: The name to greet (default: "World")
        
    Returns:
        A greeting string
    """
    return f"Hello, {name}!"
```

## Next Steps

- Try creating more complex tasks
- Explore the [Advanced Example](ADVANCED_EXAMPLE.md)
- Check out the [FAQ](FAQ.md) for common questions
- Read the full documentation at the project repository

## Tips for Success

1. **Start Small**: Begin with simple, well-defined tasks
2. **Be Specific**: Clear task descriptions lead to better results
3. **Review Carefully**: Always review generated code before merging
4. **Iterate**: Use feedback from one run to improve the next
5. **Test Thoroughly**: Run your test suite after each autonomous build
