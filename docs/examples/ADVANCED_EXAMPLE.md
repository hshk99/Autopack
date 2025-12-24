# Advanced Example: Multi-Phase Development

This guide demonstrates advanced AutoPack features including multi-phase builds, custom configurations, and integration with CI/CD.

## Scenario: Building a REST API

We'll build a complete REST API with authentication, database models, and tests.

## Project Setup

### 1. Initialize with Custom Configuration

```bash
mkdir api-project
cd api-project
autopack init --template fastapi
```

Customize `.autopack.yaml`:

```yaml
project:
  name: my-api
  type: fastapi
  python_version: "3.11"

autonomous:
  max_iterations: 10
  auto_commit: true
  branch_prefix: "autopack/"
  
phases:
  - name: setup
    description: Initialize project structure
    dependencies: []
  - name: models
    description: Create database models
    dependencies: [setup]
  - name: api
    description: Implement API endpoints
    dependencies: [models]
  - name: tests
    description: Add comprehensive tests
    dependencies: [api]
  - name: docs
    description: Generate API documentation
    dependencies: [api]

quality:
  min_test_coverage: 80
  linting: true
  type_checking: true
```

### 2. Define Multi-Phase Tasks

Create a comprehensive task specification:

```yaml
# .autonomous_runs/tasks/user_management.yaml
name: User Management API
description: |
  Build a complete user management system with:
  - User model with authentication
  - CRUD endpoints
  - JWT token authentication
  - Password hashing
  - Input validation
  - Comprehensive tests

phases:
  - phase: setup
    tasks:
      - Create project structure
      - Set up dependencies (FastAPI, SQLAlchemy, etc.)
      - Configure database connection
      
  - phase: models
    tasks:
      - Create User model with fields: id, email, password_hash, created_at
      - Add password hashing utilities
      - Create database migration
      
  - phase: api
    tasks:
      - Implement POST /users (registration)
      - Implement POST /auth/login (authentication)
      - Implement GET /users/me (get current user)
      - Implement PUT /users/me (update user)
      - Add JWT token generation and validation
      - Add authentication middleware
      
  - phase: tests
    tasks:
      - Unit tests for User model
      - Unit tests for password hashing
      - Integration tests for all endpoints
      - Test authentication flow
      - Test error cases
      
  - phase: docs
    tasks:
      - Generate OpenAPI documentation
      - Add endpoint descriptions
      - Add example requests/responses

category: feature
complexity: high
priority: high

acceptance_criteria:
  - All endpoints return proper status codes
  - Passwords are never stored in plain text
  - JWT tokens expire after 24 hours
  - Test coverage >= 80%
  - All endpoints documented in OpenAPI spec
```

### 3. Run with Phase Control

Execute specific phases:

```bash
# Run only setup and models phases
autopack run --phases setup,models

# Review the changes
git diff

# Continue with API phase
autopack run --phases api

# Run remaining phases
autopack run --phases tests,docs
```

Or run all phases:

```bash
autopack run --all-phases
```

### 4. Monitor Progress

Check phase status:

```bash
autopack status
```

Output:
```
Phase Status:
✓ setup    - Complete (2 tasks, 5 files changed)
✓ models   - Complete (3 tasks, 4 files changed)
✓ api      - Complete (6 tasks, 8 files changed)
⧗ tests    - In Progress (2/5 tasks complete)
○ docs     - Pending

Overall Progress: 60%
Estimated Time Remaining: 15 minutes
```

## Advanced Features

### Custom Code Review

Integrate with your code review process:

```bash
# Generate changes but don't commit
autopack run --no-commit

# Review changes
git diff > review.patch

# Apply after review
git apply review.patch
git commit -m "Applied AutoPack changes after review"
```

### Rollback and Recovery

If something goes wrong:

```bash
# Rollback last phase
autopack rollback --phase api

# Rollback to specific commit
autopack rollback --to-commit abc123

# View rollback history
autopack history
```

### Integration with CI/CD

GitHub Actions example:

```yaml
# .github/workflows/autopack.yml
name: AutoPack Build

on:
  schedule:
    - cron: '0 2 * * *'  # Run nightly
  workflow_dispatch:

jobs:
  autopack:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
          
      - name: Install AutoPack
        run: pip install autopack
        
      - name: Run AutoPack
        run: autopack run --all-phases
        env:
          AUTOPACK_API_KEY: ${{ secrets.AUTOPACK_API_KEY }}
          
      - name: Run Tests
        run: pytest
        
      - name: Create Pull Request
        if: success()
        uses: peter-evans/create-pull-request@v5
        with:
          title: 'AutoPack: Automated Build'
          body: 'Automated changes from AutoPack'
          branch: autopack/automated-build
```

### Custom Validation

Add custom validation hooks:

```python
# .autopack/hooks/validate.py
def validate_phase(phase_name: str, changes: dict) -> bool:
    """Custom validation logic."""
    if phase_name == "api":
        # Ensure all endpoints have tests
        return check_test_coverage(changes)
    return True

def check_test_coverage(changes: dict) -> bool:
    # Custom logic here
    return True
```

## Best Practices

1. **Phase Dependencies**: Always define clear dependencies between phases
2. **Incremental Development**: Run and review one phase at a time for complex projects
3. **Acceptance Criteria**: Define specific, measurable criteria for each phase
4. **Rollback Strategy**: Test rollback procedures before production use
5. **CI/CD Integration**: Automate routine builds but keep human review for critical changes
6. **Version Control**: Use feature branches for autonomous builds
7. **Documentation**: Keep task specifications up-to-date as requirements change

## Troubleshooting

### Phase Fails to Complete

```bash
# View detailed logs
autopack logs --phase api --verbose

# Retry with more context
autopack run --phase api --retry --context-files src/models.py
```

### Merge Conflicts

```bash
# AutoPack can help resolve conflicts
autopack resolve-conflicts --interactive
```

### Performance Issues

```bash
# Run with reduced parallelism
autopack run --max-workers 2

# Use incremental mode
autopack run --incremental
```

## Next Steps

- Explore the [FAQ](FAQ.md) for common questions
- Check out the API reference documentation
- Join the community Discord for support
- Contribute your own examples and templates
