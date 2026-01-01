# ✅ IMPLEMENTED: Large Deletion Safeguard

**Status**: IMPLEMENTED in BUILD-107

**Problem**: Autopack previously lacked hard protection against accidental large code deletions (like the 426-line deletion incident in ref6.md that required human intervention).

**Solution**: Implemented context-aware deletion thresholds with Telegram mobile approval workflow.

---

## Implementation Summary (BUILD-107)

### What Was Implemented

**1. Context-Aware Deletion Thresholds** ([risk_scorer.py:105-138](../src/autopack/risk_scorer.py#L105-L138))
   - **Troubleshooting threshold**: > 50 net lines deleted → BLOCKED
   - **Feature work threshold**: > 150 net lines deleted → BLOCKED
   - **Refactoring threshold**: > 300 net lines deleted → BLOCKED
   - Adds 20-40 risk points based on severity
   - Flags `deletion_threshold_exceeded` check

**2. Quality Gate Blocking** ([quality_gate.py:243-253](../src/autopack/quality_gate.py#L243-L253))
   - Blocks phases with `deletion_threshold_exceeded = True`
   - Blocks phases with `risk_level = "critical"`
   - Returns `quality_level = "blocked"` to trigger approval workflow

**3. Telegram Approval Workflow** ([autonomous_executor.py:4135-4148](../src/autopack/autonomous_executor.py#L4135-L4148))
   - Detects blocked phases via `quality_report.is_blocked()`
   - Calls `_request_human_approval()` with 1-hour timeout
   - Polls approval status every 10 seconds
   - Proceeds if approved, halts if rejected/timeout
   - Sends mobile notification with inline Approve/Reject buttons

**4. Failed Phase Notifications** ([autonomous_executor.py:6937-6982](../src/autopack/autonomous_executor.py#L6937-L6982))
   - Sends Telegram alert when phases fail (MAX_ATTEMPTS_EXHAUSTED, etc.)
   - Includes run ID, phase ID, failure reason, timestamp
   - Emoji-coded by failure type (🔁 retry exhausted, ⏱️ timeout, ❌ failed)

### How It Works

```
1. Builder creates patch with large deletion (e.g., 426 lines removed, 12 added)
   └─> net_deletion = 414 lines

2. Risk Scorer analyzes deletion
   └─> net_deletion (414) > REFACTOR_THRESHOLD (300)
   └─> Adds 40 risk points → risk_level = "critical"
   └─> Sets deletion_threshold_exceeded = True

3. Quality Gate checks risk
   └─> Sees deletion_threshold_exceeded = True
   └─> Returns quality_level = "blocked"

4. Executor detects blocked phase
   └─> Calls _request_human_approval()
   └─> Sends POST /approval/request to backend
       └─> TelegramNotifier.send_approval_request()
           └─> Sends message to your phone with inline buttons

5. You receive notification:
   ⚠️ Autopack Approval Needed
   Phase: diagnostics-deep-retrieval
   Risk: 🚨 CRITICAL (score: 85/100)
   Net Deletion: 414 lines
   [✅ Approve]  [❌ Reject]

6. You tap Approve or Reject
   └─> Telegram webhook → Backend API
   └─> Executor polling detects decision
   └─> Proceeds or halts accordingly
```

### Files Modified
- [src/autopack/risk_scorer.py](../src/autopack/risk_scorer.py) - Added deletion detection
- [src/autopack/quality_gate.py](../src/autopack/quality_gate.py) - Added blocking rules
- [src/autopack/autonomous_executor.py](../src/autopack/autonomous_executor.py) - Added approval workflow
- [src/autopack/notifications/telegram_notifier.py](../src/autopack/notifications/telegram_notifier.py) - Telegram integration
- [src/backend/api/approvals.py](../src/backend/api/approvals.py) - Approval API endpoints
- [docs/TELEGRAM_APPROVAL_SETUP.md](TELEGRAM_APPROVAL_SETUP.md) - Setup guide

---

## Original Recommendation (Now Implemented)

### Existing Protections ✅
1. **Risk Scorer** (src/autopack/risk_scorer.py)
   - Flags LOC delta > 500 as "high risk"
   - 426 lines would trigger risk score ≥ 50
   - Sets quality_level = "needs_review"

2. **Quality Gate** (src/autopack/quality_gate.py)
   - Captures needs_review flag
   - **BUT**: Advisory only - doesn't block apply

### Gaps ❌
1. No hard block on large deletions
2. No distinction between additions vs deletions
3. No human approval workflow for high-risk changes
4. `needs_review` flag doesn't pause execution

---

## Proposed Solution

### Option 1: Hard Block on Large Deletions (Recommended)

**Implementation**:

1. **Add deletion-specific threshold** in `risk_scorer.py`:
   ```python
   # After line 104 in _generate_index()

   # 6. Large deletion detection (max 30 points)
   LARGE_DELETION_THRESHOLD = 200  # lines
   if loc_removed > LARGE_DELETION_THRESHOLD:
       checks["large_deletion"] = True
       deletion_severity = min(30, (loc_removed // 100) * 10)
       score += deletion_severity
       reasons.append(f"LARGE DELETION: Removes {loc_removed} lines (threshold: {LARGE_DELETION_THRESHOLD})")
   else:
       checks["large_deletion"] = False
   ```

2. **Add approval gate** in `quality_gate.py`:
   ```python
   # After line 180

   # Block large deletions requiring approval
   if risk_result and risk_result.get("checks", {}).get("large_deletion"):
       quality_level = "blocked"
       issues.append(
           f"BLOCKED: Large deletion ({risk_result['metadata']['loc_removed']} lines). "
           "Requires human approval before apply."
       )
   ```

3. **Pause executor** in `autonomous_executor.py`:
   ```python
   # After line 4135 (quality gate check)

   if quality_report.is_blocked():
       logger.warning(f"[{phase_id}] BLOCKED by quality gate: {quality_report.issues}")

       # Write approval request
       approval_file = self.run_dir / f"approval_needed_{phase_id}.txt"
       approval_file.write_text(
           f"Phase {phase_id} requires approval:\n\n"
           f"Issues:\n" + "\n".join(f"  - {i}" for i in quality_report.issues) + "\n\n"
           f"Risk Assessment:\n{self.quality_gate.risk_scorer.format_report(quality_report.risk_assessment)}\n\n"
           f"To approve: Create file 'approval_granted_{phase_id}.txt'\n"
           f"To reject: Create file 'approval_rejected_{phase_id}.txt'\n"
       )

       # Wait for approval (poll every 10s, max 1 hour)
       approval_granted = self._wait_for_approval(phase_id, timeout_seconds=3600)

       if not approval_granted:
           return (False, "Phase blocked: approval timeout or rejected")
   ```

4. **Add approval polling**:
   ```python
   def _wait_for_approval(self, phase_id: str, timeout_seconds: int = 3600) -> bool:
       """Poll for approval file, return True if granted."""
       import time
       elapsed = 0

       while elapsed < timeout_seconds:
           granted_file = self.run_dir / f"approval_granted_{phase_id}.txt"
           rejected_file = self.run_dir / f"approval_rejected_{phase_id}.txt"

           if granted_file.exists():
               logger.info(f"[{phase_id}] Approval granted")
               return True

           if rejected_file.exists():
               logger.warning(f"[{phase_id}] Approval rejected")
               return False

           time.sleep(10)
           elapsed += 10

       logger.warning(f"[{phase_id}] Approval timeout after {timeout_seconds}s")
       return False
   ```

**Benefits**:
- ✅ Hard block prevents accidental large deletions
- ✅ Human-in-the-loop for high-risk changes
- ✅ Clear approval workflow via file creation
- ✅ Timeout prevents infinite hangs

**Drawbacks**:
- ⚠️ Requires human monitoring (not fully autonomous)
- ⚠️ Could block legitimate refactoring

---

### Option 2: Soft Warning + Dashboard Alert

**Implementation**:
1. Keep current risk scoring
2. Add prominent dashboard alert for `needs_review` phases
3. Provide "Approve" / "Reject" buttons in dashboard
4. Continue execution but mark commit with warning

**Benefits**:
- ✅ Maintains autonomy
- ✅ Post-hoc review possible

**Drawbacks**:
- ❌ Doesn't prevent the deletion (just alerts)
- ❌ Damage already done if wrong

---

### Option 3: Hybrid Approach (Best of Both)

**Rules**:
1. **Hard block** if:
   - `loc_removed > 300` AND `loc_added < 50` (net deletion)
   - OR risk_level == "critical" (score ≥ 70)

2. **Soft warning** (needs_review) if:
   - `200 < loc_removed < 300`
   - OR risk_level == "high" (50 ≤ score < 70)

3. **Auto-proceed** if:
   - `loc_removed < 200`
   - AND risk_level in ["low", "medium"]

**Benefits**:
- ✅ Balances autonomy and safety
- ✅ Only blocks truly risky deletions
- ✅ Allows legitimate refactoring to proceed

---

## Recommended Action

Implement **Option 3 (Hybrid)** with these thresholds:

| Scenario | loc_removed | loc_added | Action |
|----------|-------------|-----------|--------|
| Net deletion | > 300 | < 100 | **HARD BLOCK** (requires approval) |
| Large refactor | > 300 | > 200 | **SOFT WARNING** (needs_review flag) |
| Medium deletion | 100-300 | any | **SOFT WARNING** |
| Small deletion | < 100 | any | **AUTO-PROCEED** |

**Implementation Priority**: HIGH (prevents potentially catastrophic autonomous deletions)

**Estimated Effort**: 4-6 hours (including tests)

**Files to Modify**:
1. `src/autopack/risk_scorer.py` - Add deletion-specific logic
2. `src/autopack/quality_gate.py` - Add blocking rules
3. `src/autopack/autonomous_executor.py` - Add approval workflow
4. `tests/autopack/test_risk_scorer.py` - Add deletion tests
5. `tests/autopack/test_quality_gate.py` - Add blocking tests

---

## Example: 426-Line Deletion Scenario

With proposed safeguards:

```
[Phase diagnostics-deep-retrieval] Building patch...
[RiskScorer] Analyzing change: 12 lines added, 426 lines removed
[RiskScorer] ⚠️  LARGE DELETION detected (426 > 300 threshold)
[RiskScorer] Risk Level: CRITICAL (score: 85/100)
[QualityGate] BLOCKED: Net deletion of 414 lines requires approval

Approval file created: .autonomous_runs/<run_id>/approval_needed_diagnostics-deep-retrieval.txt

Waiting for human approval... (timeout: 60 minutes)
```

**Operator sees**:
```
Phase diagnostics-deep-retrieval requires approval:

Issues:
  - BLOCKED: Large deletion (426 lines). Requires human approval before apply.

Risk Assessment:
============================================================
RISK ASSESSMENT: 🚨 CRITICAL (score: 85/100)
============================================================

Risk Factors:
  • LARGE DELETION: Removes 426 lines (threshold: 200)
  • Very large change (438 LOC)

To approve: Create file 'approval_granted_diagnostics-deep-retrieval.txt'
To reject: Create file 'approval_rejected_diagnostics-deep-retrieval.txt'
```

**Result**: Human prevented from accidentally applying, just like in ref6.md.
