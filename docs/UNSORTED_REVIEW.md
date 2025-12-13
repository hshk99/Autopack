# Unsorted Content - Manual Review Required

Files below confidence threshold (0.6) need manual classification.

**Total Items**: 2
**Generated**: 2025-12-13T15:08:49.013805

**Status Codes**:
- IMPLEMENTED: Appears to be completed (check if in BUILD_HISTORY)
- REJECTED: Explicitly rejected decision
- REFERENCE: Research/reference material (permanent value)
- STALE: Old content (>180 days, not implemented)
- UNKNOWN: Could not determine status

## `archive\superseded\reports\SOT_CONSOLIDATION_PROPOSAL.md`

**Status**: UNKNOWN
**Best Match**: build (0.43)
**Confidence Scores**:
- BUILD_HISTORY: 0.43
- DEBUG_LOG: 0.14
- ARCHITECTURE_DECISIONS: 0.22

**Recommendation**: Manual review required

**Preview**:
```
# SOT File Consolidation Proposal

**Date**: 2025-12-13
**Purpose**: Reduce SOT file count from 10 to 5 core files for better AI navigation

## Problem

Current setup has 10 SOT files in docs/ which makes it difficult for AI (Cursor/Autopack) to quickly scan and understand project state. Many files contain overlapping or static information that doesn't need to be separate.

## Proposed Structure (5 Core Files)

### 1. PROJECT_INDEX.json (NEW)
**Purpose**: Single source of truth for AI navigation...
```

**Action Required**: [ ] Move to appropriate category

---

## `archive\superseded\research\QUOTA_AWARE_ROUTING.md`

**Status**: UNKNOWN
**Best Match**: decision (0.24)
**Confidence Scores**:
- BUILD_HISTORY: 0.15
- DEBUG_LOG: 0.19
- ARCHITECTURE_DECISIONS: 0.24

**Recommendation**: Manual review required

**Preview**:
```
# Quota-Aware Multi-Provider Routing

**Status**: ✅ Configuration Complete | ⏭️ Implementation Pending
**Date**: 2025-11-25 (Updated: 2025-12-01)
**Based On**: GPT's quota management strategy + Claude Max/Code limit updates

> **Note (2025-12-01)**: Model stack has been updated for optimal cost/performance. Current production stack is:
> - **Low complexity**: GLM-4.6 (glm-4.6) - Zhipu AI
> - **Medium complexity**: Claude Sonnet 4.5 (claude-sonnet-4-5) - Anthropic
> - **High complexity**: Claude ...
```

**Action Required**: [ ] Move to appropriate category

---

