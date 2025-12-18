"""BUILD-050 Phase 2: Update all references from attempts_used/max_attempts to new decoupled counters

This script updates autonomous_executor.py to use the new decoupled attempt counters:
- retry_attempt: replaces attempts_used
- MAX_RETRY_ATTEMPTS constant: replaces max_attempts field references
"""

import re
from pathlib import Path

def update_autonomous_executor():
    """Update autonomous_executor.py with new counter names"""

    file_path = Path(__file__).parent.parent.parent / "src" / "autopack" / "autonomous_executor.py"

    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Track changes
    changes = []

    # 1. Add MAX_RETRY_ATTEMPTS constant after MAX_EXECUTE_FIX_PER_PHASE
    if "MAX_RETRY_ATTEMPTS" not in content:
        old_pattern = r"(MAX_EXECUTE_FIX_PER_PHASE = 1  # Maximum execute_fix attempts per phase\n)"
        new_text = r"\1\n# BUILD-050 Phase 2: Maximum retry attempts per phase\nMAX_RETRY_ATTEMPTS = 5  # Maximum Builder retry attempts before phase fails\n"
        content, n = re.subn(old_pattern, new_text, content)
        if n > 0:
            changes.append(f"Added MAX_RETRY_ATTEMPTS constant ({n} replacements)")

    # 2. Update database load log message
    old_pattern = r'f"\[{phase_id}\] Loaded from DB: attempts_used={phase\.attempts_used}/{phase\.max_attempts}, "'
    new_text = r'f"[{phase_id}] Loaded from DB: retry_attempt={phase.retry_attempt}, revision_epoch={phase.revision_epoch}, escalation_level={phase.escalation_level}, "'
    content, n = re.subn(old_pattern, new_text, content)
    if n > 0:
        changes.append(f"Updated DB load log message ({n} replacements)")

    # 3. Update _update_phase_attempts_in_db signature - already done in previous session

    # 4. Update DB update log message
    old_pattern = r'f"\[{phase_id}\] Updated attempts in DB: {attempts_used}/{phase\.max_attempts} "'
    new_text = r'f"[{phase_id}] Updated attempts in DB: retry={retry_attempt}, epoch={revision_epoch}, escalation={escalation_level} "'
    content, n = re.subn(old_pattern, new_text, content)
    if n > 0:
        changes.append(f"Updated DB update log message ({n} replacements)")

    # 5. Update phase.max_attempts references to MAX_RETRY_ATTEMPTS
    content, n = re.subn(r'phase_db\.max_attempts', 'MAX_RETRY_ATTEMPTS', content)
    if n > 0:
        changes.append(f"Replaced phase_db.max_attempts with MAX_RETRY_ATTEMPTS ({n} replacements)")

    # 6. Update phase.attempts_used references to phase.retry_attempt
    content, n = re.subn(r'phase_db\.attempts_used', 'phase_db.retry_attempt', content)
    if n > 0:
        changes.append(f"Replaced phase_db.attempts_used with phase_db.retry_attempt ({n} replacements)")

    # 7. Update phase.max_attempts references (without _db prefix)
    content, n = re.subn(r'phase\.max_attempts', 'MAX_RETRY_ATTEMPTS', content)
    if n > 0:
        changes.append(f"Replaced phase.max_attempts with MAX_RETRY_ATTEMPTS ({n} replacements)")

    # 8. Update local variable max_attempts = ... to MAX_RETRY_ATTEMPTS
    content, n = re.subn(r'max_attempts = phase_db\.max_attempts', 'max_attempts = MAX_RETRY_ATTEMPTS', content)
    if n > 0:
        changes.append(f"Updated max_attempts variable assignment ({n} replacements)")

    # 9. Update attempt_index = phase_db.attempts_used
    content, n = re.subn(r'attempt_index = phase_db\.attempts_used', 'attempt_index = phase_db.retry_attempt', content)
    if n > 0:
        changes.append(f"Updated attempt_index assignment ({n} replacements)")

    # 10. Update new_attempts calculation - replace attempts_used + 1
    content, n = re.subn(r'new_attempts = phase_db\.attempts_used \+ 1', 'new_attempts = phase_db.retry_attempt + 1', content)
    if n > 0:
        changes.append(f"Updated new_attempts calculation ({n} replacements)")

    # 11. Update attempts_used parameter in _update_phase_attempts_in_db calls to retry_attempt
    content, n = re.subn(r'attempts_used=new_attempts', 'retry_attempt=new_attempts', content)
    if n > 0:
        changes.append(f"Updated attempts_used parameter to retry_attempt ({n} replacements)")

    # 12. Update comments mentioning attempts_used
    content, n = re.subn(r'attempts_used < max_attempts', 'retry_attempt < MAX_RETRY_ATTEMPTS', content)
    if n > 0:
        changes.append(f"Updated comments ({n} replacements)")

    # 13. Update documentation strings
    content, n = re.subn(r'Database tracks: attempts_used, max_attempts', 'Database tracks: retry_attempt, revision_epoch, escalation_level', content)
    if n > 0:
        changes.append(f"Updated documentation ({n} replacements)")

    # 14. Update max_attempts references in doctor context
    content, n = re.subn(r'"max_attempts": max_attempts', '"max_retry_attempts": MAX_RETRY_ATTEMPTS', content)
    if n > 0:
        changes.append(f"Updated doctor context ({n} replacements)")

    # Write updated content
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(content)

    print("BUILD-050 Phase 2: Updated autonomous_executor.py")
    for change in changes:
        print(f"  ✓ {change}")

    return len(changes) > 0

if __name__ == "__main__":
    if update_autonomous_executor():
        print("\n✅ Successfully updated all attempt references")
    else:
        print("\n⚠️  No changes made (may already be updated)")
