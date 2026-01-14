# Frequently Asked Questions (FAQ)

## General Questions

### What is AutoPack?

AutoPack is an autonomous build system that uses AI to generate code changes based on task specifications. It helps automate routine development tasks while maintaining code quality and consistency.

### How does AutoPack work?

AutoPack:
1. Analyzes your codebase and task specifications
2. Generates code changes using AI models
3. Validates changes against quality criteria
4. Creates commits and branches automatically
5. Provides rollback and recovery mechanisms

### Is AutoPack suitable for production use?

Yes, but with proper safeguards:
- Always review generated code before merging
- Run comprehensive tests
- Use feature branches
- Implement code review processes
- Start with low-risk tasks

### What programming languages does AutoPack support?

Currently, AutoPack has best support for:
- Python (primary)
- JavaScript/TypeScript
- Go
- Rust

Other languages may work but with varying results.

## Installation & Setup

### How do I install AutoPack?

```bash
pip install autopack
```

For development installation:
```bash
git clone https://github.com/yourusername/autopack.git
cd autopack
pip install -e .
```

### What are the system requirements?

- Python 3.8 or higher
- Git 2.20 or higher
- 4GB RAM minimum (8GB recommended)
- Internet connection (for AI model access)

### Do I need an API key?

For basic local use, no. For advanced features using cloud AI models, you may need:
- OpenAI API key (for GPT models)
- Anthropic API key (for Claude models)

Set via environment variables:
```bash
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"
```

### How do I configure AutoPack for my project?

Run `autopack init` to create a default `.autopack.yaml` configuration file, then customize it:

```yaml
project:
  name: my-project
  type: python

autonomous:
  max_iterations: 5
  auto_commit: true

quality:
  min_test_coverage: 80
  linting: true
```

## Usage Questions

### How do I create a task?

Three ways:

1. Command line:
```bash
autopack task create "Add user authentication"
```

2. YAML file:
```yaml
# .autonomous_runs/tasks/auth.yaml
name: Add authentication
description: Implement JWT-based authentication
category: feature
complexity: medium
```

3. Interactive mode:
```bash
autopack task create --interactive
```

### What makes a good task description?

Good task descriptions are:
- **Specific**: "Add a login endpoint" not "improve auth"
- **Measurable**: Include acceptance criteria
- **Scoped**: One clear objective per task
- **Contextual**: Reference existing code when relevant

Example:
```yaml
name: Add user login endpoint
description: |
  Create a POST /auth/login endpoint that:
  - Accepts email and password
  - Returns JWT token on success
  - Returns 401 on invalid credentials
  - Includes rate limiting
acceptance_criteria:
  - Endpoint returns proper status codes
  - JWT token expires after 24 hours
  - Rate limit is 5 attempts per minute
```

### Can I run multiple tasks at once?

Yes, use the `--parallel` flag:

```bash
autopack run --parallel --max-workers 4
```

Note: Parallel execution works best for independent tasks.

### How do I review changes before committing?

Use the `--no-commit` flag:

```bash
autopack run --no-commit
git diff  # Review changes
git commit -m "Your message"  # Commit if satisfied
```

### Can I customize the AI model used?

Yes, in `.autopack.yaml`:

```yaml
ai:
  model: gpt-4  # or claude-3, gpt-3.5-turbo, etc.
  temperature: 0.7
  max_tokens: 4000
```

## Troubleshooting

### AutoPack generates incorrect code

Try:
1. Make task description more specific
2. Add more context files: `autopack run --context-files src/models.py`
3. Use a more capable model: `--model gpt-4`
4. Break task into smaller subtasks
5. Provide examples in the task description

### Changes conflict with my code

```bash
# Let AutoPack help resolve
autopack resolve-conflicts --interactive

# Or manually resolve
git mergetool
```

### AutoPack is slow

Optimizations:
1. Use `--incremental` mode for large codebases
2. Reduce `max_iterations` in config
3. Use faster AI models for simple tasks
4. Limit context with `--context-files`
5. Run on a machine with more RAM

### Task fails validation

Check logs:
```bash
autopack logs --verbose
```

Common issues:
- Test coverage too low: Add more tests
- Linting errors: Run `autopack lint --fix`
- Type errors: Check type hints
- Missing dependencies: Update requirements.txt

### How do I rollback changes?

```bash
# Rollback last task
autopack rollback

# Rollback specific phase
autopack rollback --phase api

# Rollback to commit
autopack rollback --to-commit abc123
```

## Best Practices

### When should I use AutoPack?

Good use cases:
- Boilerplate code generation
- CRUD operations
- Test generation
- Documentation updates
- Routine refactoring
- API endpoint creation

Avoid for:
- Complex algorithms
- Security-critical code (without review)
- Novel architectural decisions
- Code requiring deep domain knowledge

### How do I ensure code quality?

1. **Set quality gates** in `.autopack.yaml`:
```yaml
quality:
  min_test_coverage: 80
  linting: true
  type_checking: true
  security_scan: true
```

2. **Use code review**: Never merge without review
3. **Run tests**: Always run full test suite
4. **Start small**: Begin with low-risk tasks
5. **Iterate**: Use feedback to improve task specs

### Should I commit AutoPack changes directly to main?

No. Best practice:
1. AutoPack creates feature branch
2. Review changes
3. Run tests
4. Create pull request
5. Get team review
6. Merge to main

### How do I integrate with CI/CD?

See [Advanced Example](ADVANCED_EXAMPLE.md) for GitHub Actions integration.

Key points:
- Run AutoPack in scheduled jobs
- Always run tests after generation
- Create PRs for review
- Never auto-merge to main

## Advanced Topics

### Can I extend AutoPack with custom logic?

Yes, using hooks:

```python
# .autopack/hooks/custom.py
def pre_generate(task):
    """Called before code generation."""
    pass

def post_generate(task, changes):
    """Called after code generation."""
    pass

def validate(task, changes):
    """Custom validation logic."""
    return True
```

### How does AutoPack handle secrets?

AutoPack:
- Never includes secrets in generated code
- Uses environment variables for sensitive data
- Respects `.gitignore` patterns
- Can integrate with secret management tools

### Can I use AutoPack offline?

Partially:
- Local models: Yes (with setup)
- Cloud models: No (requires internet)
- Basic features: Yes
- Advanced features: May require internet

### How do I contribute to AutoPack?

See CONTRIBUTING.md in the repository:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## Getting Help

### Where can I get support?

- **Documentation**: Read the full docs
- **GitHub Issues**: Report bugs and request features
- **Discord**: Join the community chat
- **Stack Overflow**: Tag questions with `autopack`

### How do I report a bug?

Create a GitHub issue with:
1. AutoPack version: `autopack --version`
2. Python version: `python --version`
3. Operating system
4. Steps to reproduce
5. Expected vs actual behavior
6. Relevant logs: `autopack logs --verbose`

### Where can I find examples?

- [Simple Example](SIMPLE_EXAMPLE.md)
- [Advanced Example](ADVANCED_EXAMPLE.md)
- GitHub repository examples/ directory
- Community-contributed templates

## License & Legal

### What license is AutoPack under?

Check the LICENSE file in the repository (typically MIT or Apache 2.0).

### Can I use AutoPack commercially?

Yes, subject to the license terms. Note:
- AutoPack itself is open source
- AI model usage may have separate terms
- Review your AI provider's commercial use policy

### Who owns the generated code?

You do. Generated code is owned by you/your organization, subject to:
- Your AI provider's terms of service
- Any applicable open source licenses
- Your organization's policies
