# Branch Naming Standard

**Version**: 1.0
**Date**: 2026-02-03
**Status**: Canonical (Single Source of Truth)

## Purpose

This document defines the **authoritative** branch naming standard for the Autopack V2 autonomous loop project. All branches must follow this format to ensure:

- PR monitor can correctly detect and track branches
- Automation can match branch names to phases
- Consistent organization across the project
- Easy identification of work context

## Standard Format

All branches must follow this exact pattern:

```
c{CYCLE}/wave{WAVE}/{phaseId}-{description}
```

### Components

- **CYCLE**: The cycle identifier (e.g., `1`, `2`, `3`)
- **WAVE**: The wave number within the cycle (e.g., `1`, `2`, `3`, `4`, `5`, `6`)
- **phaseId**: The phase identifier (e.g., `setup001`, `config001`, `branch001`)
- **description**: A short, kebab-case description of the work

### Examples

Valid branch names:
```
c1/wave1/setup001-project-structure
c1/wave1/deps001-requirements
c1/wave1/config001-config-loader
c1/wave2/state001-state-manager
c1/wave2/resource001-resource-monitor
c1/wave2/branch001-branch-validator
c1/wave3/orch001-phase-orchestrator
c1/wave3/ramsafe001-ram-safety
c1/wave4/scheduler001-agent-scheduler
c1/wave5/mainloop001-main-loop
c2/wave1/setup001-project-structure
```

Invalid branch names:
```
feature/setup-project          # Missing cycle and wave prefix
setup001                     # Missing cycle/wave/phase structure
c1-wave1-setup001           # Incorrect separator (should be /)
c1/wave1/setup001           # Missing description
c1/wave1/setup001/project    # Description should be kebab-case
```

## Validation Rules

### 1. Pattern Match
Branch must match regex:
```regex
^c\d+/wave\d+/\w+-[\w-]+$
```

### 2. Cycle Validation
- Cycle must be a positive integer (1, 2, 3, ...)
- Must match current project cycle (from configuration)

### 3. Wave Validation
- Wave must be a valid wave number (1-6)
- Valid waves for V2 project:
  - Wave 1: Foundation & Project Setup
  - Wave 2: Core Infrastructure
  - Wave 3: Secondary Components & Managers
  - Wave 4: Agent Management & Integration
  - Wave 5: Advanced Features & Main Loop
  - Wave 6: Final Integration & Tests

### 4. Phase ID Format
- Must match pattern: `{type}{number}` (e.g., `setup001`, `config001`, `branch001`)
- Common prefixes:
  - `setup`: Setup phases
  - `deps`: Dependency phases
  - `config`: Configuration phases
  - `state`: State management phases
  - `resource`: Resource monitoring phases
  - `webhook`: Webhook handling phases
  - `credit`: Credit management phases
  - `glm`: GLM-related phases
  - `network`: Network monitoring phases
  - `telegram`: Telegram notification phases
  - `prompts`: Prompts parsing phases
  - `worktree`: Worktree management phases
  - `branch`: Branch validation phases
  - `telemetry`: Telemetry logging phases
  - `orch`: Orchestration phases
  - `ramsafe`: RAM safety phases
  - `agentstate`: Agent state phases
  - `prmanager`: PR management phases
  - `ciclass`: CI classification phases
  - `poller`: API polling phases
  - `router`: Model routing phases
  - `webhookhealth`: Webhook health phases
  - `wavemetrics`: Wave metrics phases
  - `ramrecord`: RAM recording phases
  - `unresolved`: Unresolved issues phases
  - `queue`: Queue management phases
  - `planning`: Planning monitoring phases
  - `humanqueue`: Human intervention queue phases
  - `test`: Testing phases
  - `scheduler`: Agent scheduling phases
  - `thinking`: Thinking detection phases
  - `nudgetrack`: Nudge tracking phases
  - `cianalyze`: CI analysis phases
  - `dashboard`: Dashboard phases
  - `pausemon`: Pause monitoring phases
  - `recurring`: Recurring issue detection phases
  - `archiver`: Project archiving phases
  - `headless`: Headless agent phases
  - `nudgegen`: Nudge generation phases
  - `deepinv`: Deep investigation phases
  - `cascade`: Cascading failure detection phases
  - `escalate`: Escalation management phases
  - `mainloop`: Main loop controller phases
  - `cleanup`: Wave cleanup phases

### 5. Description Rules
- Must be kebab-case (lowercase with hyphens)
- Must not contain spaces
- Should be descriptive but concise
- Should relate to the phase work

## Usage

### When Creating Branches

Always use the branch validator before creating a branch:

```python
from src.orchestration.branch_validator import validate_branch_name

try:
    validate_branch_name("c1/wave2/branch001-branch-validator")
    print("Branch name is valid!")
except ValueError as e:
    print(f"Invalid branch name: {e}")
```

### In Automation

The PR monitor and worktree manager should validate branch names before:
- Creating a new branch
- Checking out a worktree
- Creating a pull request

## Enforcement

Branch validation should be enforced at:
1. **Branch Creation**: Before `git checkout -b` command
2. **Worktree Creation**: Before `git worktree add` command
3. **PR Creation**: Before `gh pr create` command
4. **Automation**: Before any automated branch/PR operations

## Related Files

- `src/orchestration/branch_validator.py`: Implementation of validation logic
- `config/v2_config.json`: Configuration including current cycle
- `V2_WORKFLOW.md`: Workflow document with all phases

## Version History

- **1.0** (2026-02-03): Initial version with V2 autonomous loop standard
