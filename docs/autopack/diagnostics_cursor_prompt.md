# Diagnostics Cursor Prompt Generator

## Overview

The Diagnostics Cursor Prompt Generator is designed to create a single, copy-paste-ready prompt that references the handoff bundle. This prompt includes details about what happened, the current failure, a list of files to attach or open, and any constraints such as protected or allowed paths and deliverables.

## Features

- **Handoff Bundle Reference**: The prompt includes a reference to the handoff bundle, which contains all necessary artifacts from the diagnostics phase.
- **Failure Details**: Clearly outlines the current failure and any relevant error messages.
- **File List**: Provides a list of files that should be attached or opened for further investigation.
- **Constraints**: Lists any constraints such as protected paths, allowed paths, and deliverables.

## Usage

The prompt generator is intended to be used in scenarios where diagnostics information needs to be handed off to another team or individual for further analysis. The generated prompt ensures that all relevant information is included in a concise and easy-to-understand format.

## Example

An example of a generated prompt might look like this:

```
Diagnostics Handoff Bundle Reference: /path/to/handoff/bundle

Current Failure:
- Error: Cannot import name 'format_rules_for_prompt' from 'autopack.learned_rules'

Files to Attach/Open:
- src/autopack/diagnostics/cursor_prompt_generator.py
- src/autopack/dashboard/server.py

Constraints:
- Protected Paths: /src/autopack/protected/
- Allowed Paths: /src/autopack/diagnostics/
- Deliverables: If available, include the generated summary.md
```

This prompt can be copied and pasted into an email or a ticketing system to facilitate quick and effective communication.
