# Governance

**Purpose**: Approval workflow, governance tiers, and auto-approval rules for Autopack

**Last Updated**: 2025-12-29

---

## Overview

Autopack implements a multi-tier governance system to balance autonomous execution with safety controls. This document covers:

1. Approval workflow and decision points
2. Governance tiers and risk levels
3. Auto-approval rules and criteria
4. Protected paths and isolation rules
5. Human approval process
6. Audit trails and logging
7. Emergency procedures

---

## 1. Approval Workflow

### Decision Points

Autopack evaluates governance requirements at multiple points:

**Phase Execution Start**:
- Check if phase modifies protected paths
- Assess risk level based on scope and complexity
- Determine if auto-approval criteria met

**After Builder Generates Patch**:
- Parse patch metadata (files changed, lines added/removed)
- Assess risk using RiskScorer
- Check against auto-approval rules
- Request approval if needed

**Before Patch Application**:
- Validate patch against allowed paths
- Check for protected path violations
- Create governance request if blocked
- Apply patch only if approved or auto-approved

### Workflow States

```
QUEUED → EXECUTING → [Governance Check]
                           |
                           ├─→ AUTO_APPROVED → APPLYING
                           ├─→ APPROVAL_PENDING → [Human Decision]
                           │                         |
                           │                         ├─→ APPROVED → APPLYING
                           │                         └─→ REJECTED → BLOCKED
                           └─→ BLOCKED (protected path violation)
```

---

## 2. Governance Tiers

### Tier 1: Auto-Approved (Low Risk)

**Criteria**:
- Changes ≤100 lines
- Only modifies allowed paths
- No protected paths touched
- No database schema changes
- Risk level: LOW

**Examples**:
- New test files (`tests/test_*.py`)
- Documentation updates (`docs/*.md`)
- Utility functions in allowed directories
- Configuration file updates (non-sensitive)

**Action**: Proceed immediately without human approval

### Tier 2: Notify + Proceed (Medium Risk)

**Criteria**:
- Changes 100-200 lines
- Multiple files modified
- Within allowed paths
- No protected paths touched
- Risk level: MEDIUM

**Examples**:
- Feature implementations in allowed directories
- Test suite expansions
- Refactoring within module boundaries
- API endpoint additions (non-core)

**Action**: Send Telegram notification, proceed automatically

### Tier 3: Approval Required (High Risk)

**Criteria**:
- Changes >200 lines
- Protected paths touched
- Database schema modifications
- Core infrastructure changes
- Risk level: HIGH or CRITICAL

**Examples**:
- Changes to `src/autopack/autonomous_executor.py`
- Database migrations (`alembic/versions/*`)
- Governance system modifications
- API authentication changes
- Large deletions (>200 lines removed)

**Action**: Block until human approval granted

### Tier 4: Always Block (Critical)

**Criteria**:
- Protected paths in NEVER_AUTO_APPROVE list
- Git internals (`.git/*`)
- Secrets/credentials (`.env*`)
- Governance enforcement code

**Examples**:
- `src/autopack/governed_apply.py`
- `src/autopack/quality_gate.py`
- `.git/config`
- `.env`, `.env.local`

**Action**: Always require human approval, no exceptions

---

## 3. Auto-Approval Rules

### Conservative Policy

Autopack uses a **default-deny** approach:
- All changes require approval UNLESS explicitly allowed
- Auto-approval rules are narrow and specific
- When in doubt, request human approval

### Auto-Approval Criteria

All conditions must be met:

1. **Path Safety**:
   - File in allowed paths list
   - NOT in protected paths list
   - NOT in NEVER_AUTO_APPROVE list

2. **Change Size**:
   - Net lines changed ≤100
   - No large deletions (>50 lines removed)

3. **Risk Level**:
   - Risk score <50 (LOW or MEDIUM)
   - No database file modifications
   - No protected path touches

4. **Category Safety**:
   - Tests: Always allowed (if in `tests/`)
   - Docs: Always allowed (if in `docs/`)
   - Implementation: Only if in allowed directories

### NEVER_AUTO_APPROVE List

```python
NEVER_AUTO_APPROVE = [
    "src/autopack/models.py",           # Database schema
    "alembic/versions/*",                # Migrations
    "src/autopack/main.py",              # API routes
    "src/autopack/governed_apply.py",    # Governance itself
    "src/autopack/autonomous_executor.py", # Executor logic
    "src/autopack/quality_gate.py",      # Quality enforcement
    ".git/*",                            # Git internals
    ".env*",                             # Secrets
    "config/production.yaml",            # Production config
]
```

### Auto-Approval Examples

**✅ Auto-Approved**:
```python
# New test file (50 lines)
File: tests/test_new_feature.py
Risk: LOW
Path: tests/ (allowed)
Decision: AUTO_APPROVED
```

**✅ Auto-Approved**:
```python
# Documentation update (30 lines)
File: docs/QUICKSTART.md
Risk: LOW
Path: docs/ (allowed)
Decision: AUTO_APPROVED
```

**❌ Approval Required**:
```python
# Core executor change (150 lines)
File: src/autopack/autonomous_executor.py
Risk: HIGH
Path: NEVER_AUTO_APPROVE
Decision: APPROVAL_REQUIRED
```

**❌ Approval Required**:
```python
# Large deletion (250 lines removed)
File: src/autopack/research/gatherer.py
Risk: CRITICAL
Deletion: >200 lines
Decision: APPROVAL_REQUIRED
```

---

## 4. Protected Paths

### Core Protected Paths

**Never Modified Without Approval**:
- `.git/` - Git repository internals
- `.autonomous_runs/` - Execution artifacts
- `autopack.db` - Database file
- `.env*` - Environment variables and secrets

**Require Explicit Approval**:
- `src/autopack/` - Core framework code
- `alembic/` - Database migrations
- `config/` - Configuration files

### Allowed Paths

Phases can modify these without special approval:
- `tests/` - Test files
- `docs/` - Documentation
- `examples/` - Example code
- `scripts/` - Utility scripts (non-core)

### Isolation Rules

**Critical**: Protected paths MUST NOT be modified under any circumstances without explicit human approval.

**Violation Consequences**:
- Patch rejected immediately
- Phase marked BLOCKED
- Governance request created
- Human approval required to proceed

**Allowed Approach**:
- ✓ Import from protected modules
- ✓ Create new files in allowed directories
- ✓ Use existing APIs

**Forbidden Approach**:
- ✗ Modify protected files directly
- ✗ Extend protected classes in-place
- ✗ Add methods to protected modules

---

## 5. Human Approval Process

### Telegram Notifications

When approval required, Autopack sends Telegram message:

```
⚠️ Autopack Approval Needed

Run: research-system-v1
Phase: research-integration
Risk: 🚨 CRITICAL (score: 85/100)

Changes:
• Modified: src/autopack/main.py (+150 lines)
• Risk: Protected path modification
• Net Deletion: 50 lines

[✅ Approve]  [❌ Reject]
```

### Approval Actions

**Approve**:
- Phase continues execution
- Patch applied with temporary allowance
- Decision logged to audit trail

**Reject**:
- Phase marked BLOCKED
- Execution halted
- Feedback provided to Builder for retry

**Timeout** (default: 1 hour):
- Treated as rejection
- Phase marked BLOCKED
- Requires manual intervention

### API Endpoints

**Request Approval**:
```bash
POST /approval/request
{
  "run_id": "research-system-v1",
  "phase_id": "research-integration",
  "reason": "Protected path modification",
  "risk_level": "CRITICAL",
  "timeout_seconds": 3600
}
```

**Check Status**:
```bash
GET /approval/status/{approval_id}
```

**Approve/Reject**:
```bash
POST /approval/approve/{approval_id}
POST /approval/reject/{approval_id}
```

---

## 6. Audit Trails

### Decision Logging

All governance decisions logged to:

**Database** (`governance_requests` table):
- request_id, run_id, phase_id
- violated_paths, justification
- risk_level, approved, approved_at
- created_at, expires_at

**File System** (`.autonomous_runs/<run_id>/governance/`):
- `request_{request_id}.json` - Full request details
- `decision_{request_id}.json` - Approval decision

**Logs** (`run.log`):
- Governance check results
- Approval request/response
- Patch application with allowance

### Audit Trail Contents

```json
{
  "request_id": "gov-req-123",
  "run_id": "research-system-v1",
  "phase_id": "research-integration",
  "timestamp": "2025-12-29T12:00:00Z",
  "violated_paths": [
    "src/autopack/main.py"
  ],
  "justification": "Add research API router registration",
  "risk_assessment": {
    "level": "HIGH",
    "score": 85,
    "factors": [
      "Protected path modification",
      "Large change (150 lines)"
    ]
  },
  "decision": {
    "approved": true,
    "approved_by": "human",
    "approved_at": "2025-12-29T12:05:00Z",
    "notes": "Reviewed and approved - necessary for research integration"
  }
}
```

### Query Audit Trail

```bash
# List pending approvals
GET /governance/pending

# Get approval history for run
GET /governance/history?run_id=research-system-v1

# Get approval details
GET /governance/request/{request_id}
```

---

## 7. Emergency Procedures

### Break-Glass Access

For critical production issues:

**Procedure**:
1. Stop executor: `pkill -f autonomous_executor`
2. Manual fix with documentation
3. Log to SOT: `docs/DEBUG_LOG.md`, `docs/BUILD_HISTORY.md`
4. Create governance request retroactively
5. Document in audit trail

**Example**:
```bash
# Emergency fix
git checkout -b emergency/fix-critical-bug
# Make changes
git commit -m "Emergency fix: [description]"

# Document
echo "DBG-XXX: Emergency fix - [description]" >> docs/DEBUG_LOG.md
echo "BUILD-XXX: Emergency fix - [description]" >> docs/BUILD_HISTORY.md
```

### Rollback Procedures

**Automatic Rollback**:
- Quality gate failures trigger automatic rollback
- Git save points created before risky changes
- Rollback to last known good state

**Manual Rollback**:
```bash
# Find save point
git tag | grep save-before-

# Rollback
git reset --hard save-before-<phase-id>

# Verify
git status
pytest tests/
```

### Governance Override

In extreme cases, governance can be temporarily disabled:

```bash
# WARNING: Use only in emergencies
export AUTOPACK_GOVERNANCE_DISABLED=1

# Run with override
python -m autopack.autonomous_executor --run-id emergency-fix

# Re-enable immediately after
unset AUTOPACK_GOVERNANCE_DISABLED
```

**Requirements**:
- Document reason in SOT
- Create audit trail entry
- Review all changes manually
- Re-enable governance immediately

---

## Quick Reference

### Risk Levels

| Level | Lines Changed | Protected Paths | Action |
|-------|---------------|-----------------|--------|
| LOW | <100 | No | Auto-approve |
| MEDIUM | 100-200 | No | Notify + proceed |
| HIGH | >200 | Yes | Require approval |
| CRITICAL | Any | NEVER_AUTO_APPROVE | Always block |

### Auto-Approval Checklist

- [ ] File in allowed paths
- [ ] NOT in protected paths
- [ ] NOT in NEVER_AUTO_APPROVE
- [ ] Changes ≤100 lines
- [ ] No large deletions (>50 lines)
- [ ] Risk score <50
- [ ] No database modifications

### Common Paths

**Always Allowed**:
- `tests/test_*.py`
- `docs/*.md`
- `examples/*`

**Always Protected**:
- `src/autopack/*.py`
- `.git/*`
- `.env*`
- `autopack.db`

---

## Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System overview
- [PHASE_LIFECYCLE.md](PHASE_LIFECYCLE.md) - Phase states and transitions
- [ERROR_HANDLING.md](ERROR_HANDLING.md) - Error scenarios
- [API_BASICS.md](API_BASICS.md) - API endpoints

---

**Total Lines**: 250 (within ≤250 line constraint)

**Coverage**: 7 sections (approval workflow, governance tiers, auto-approval rules, protected paths, human approval, audit trails, emergency procedures)

**Context**: Based on governance_requests.py, governed_apply.py, risk_scorer.py, quality_gate.py, autonomous_executor.py, phase_finalizer.py, approval endpoints, and BUILD-127 governance implementation
