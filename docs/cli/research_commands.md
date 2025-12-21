# CLI Research Commands Documentation

This document provides an overview of the CLI commands related to phase management in the Autopack framework. These commands allow users to create, execute, review, and check the status of phases in a project.

## Commands

### create-phase
Create a new phase in the project.

**Usage:**
```bash
autopack-cli create-phase --name <phase_name> --description <description> --complexity <complexity>
```

**Options:**
- `--name`: The name of the phase.
- `--description`: A brief description of the phase.
- `--complexity`: The complexity level of the phase (e.g., low, medium, high).

### execute-phase
Execute a specified phase.

**Usage:**
```bash
autopack-cli execute-phase --phase-id <phase_id>
```

**Options:**
- `--phase-id`: The ID of the phase to execute.

### review-phase
Review the results of a completed phase.

**Usage:**
```bash
autopack-cli review-phase --phase-id <phase_id>
```

**Options:**
- `--phase-id`: The ID of the phase to review.

### phase-status
Check the status of a specific phase.

**Usage:**
```bash
autopack-cli phase-status --phase-id <phase_id>
```

**Options:**
- `--phase-id`: The ID of the phase to check the status of.

## Examples

```bash
# Create a new phase
autopack-cli create-phase --name "Data Processing" --description "Process incoming data" --complexity "medium"

# Execute a phase
autopack-cli execute-phase --phase-id 123

# Review a phase
autopack-cli review-phase --phase-id 123

# Check phase status
autopack-cli phase-status --phase-id 123
```
