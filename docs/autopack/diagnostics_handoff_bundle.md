# Diagnostics Handoff Bundle

## Overview

The Diagnostics Handoff Bundle is a stable, reproducible package generated from a run directory. It is designed to provide a high-signal narrative of the run's outcome, including a manifest of artifacts, a summary of key events, and relevant excerpts.

## Structure

The handoff bundle consists of the following components:

1. **index.json**: A manifest of artifacts included in the bundle.
2. **summary.md**: A markdown file providing a narrative summary of the run.
3. **excerpts/**: A directory containing tailed logs or snippets of interest.

## Components

### index.json

This JSON file lists all artifacts included in the handoff bundle. It serves as a manifest to ensure all relevant files are accounted for and can be easily accessed.

### summary.md

The summary file provides a high-level overview of the run, highlighting significant events, outcomes, and any anomalies detected during execution. It is intended to give a quick understanding of what transpired during the run.

### excerpts/

This directory contains specific log excerpts or code snippets that are deemed important for understanding the run's context or diagnosing issues. These are typically tailed logs or selected portions of larger files.

## Usage

The handoff bundle is automatically generated at the end of a run and is intended for use by developers, auditors, or automated systems that need to quickly assess the state and outcome of a run.

## Example

An example handoff bundle might include:

- `index.json`: Lists `summary.md`, `excerpts/log_tail.txt`, etc.
- `summary.md`: Describes the run's success, any errors, and key metrics.
- `excerpts/log_tail.txt`: Contains the last 100 lines of the main log file.

## Conclusion

The Diagnostics Handoff Bundle is a critical tool for ensuring transparency and traceability in automated runs, providing a concise and comprehensive package of information for post-run analysis.
