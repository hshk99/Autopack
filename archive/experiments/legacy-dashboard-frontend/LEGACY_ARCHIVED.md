# Legacy Dashboard Frontend (Archived)

**Archived Date**: 2026-01-10
**Reason**: Superseded by canonical frontend at `src/frontend/`

## Overview

This directory contains the original JSX-based React dashboard UI that was located at `src/autopack/dashboard/frontend/`.

## Why Archived

Per P2.1 of COMPREHENSIVE_IMPROVEMENT_SCAN_2026-01-10.md:

> A legacy UI exists under `src/` and contains TODOs/hardcoded URLs. This conflicts with the workspace spec principle "`src/` is code only" and creates "two truths" for UI.

The canonical frontend is:
- Located at: `src/frontend/` (TypeScript React)
- Built by: `Dockerfile.frontend`
- Documented in: `docs/DEPLOYMENT.md`

## Contents

- `src/` - React components (JSX)
- `dist/` - Built artifacts
- `package.json` - npm dependencies
- Other Vite/React configuration files

## Do Not Use

This code is archived for historical reference only. Do not copy or build from this directory.

Use the canonical frontend at `src/frontend/` instead.
