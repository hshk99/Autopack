#!/usr/bin/env python3
"""
OCR-based Connection Error Handler for Cursor Grid Windows

This script monitors 9 Cursor windows arranged in a 3x3 grid and uses OCR
to detect error popups (e.g., "Connection error", "Try again", "Resume").
When detected, it clicks the appropriate button to recover.

Uses EasyOCR for text recognition - much more accurate than Tesseract.

Requirements:
    pip install easyocr pillow pyautogui mss numpy

Usage:
    python handle_connection_errors_ocr.py

    Or with verbose logging:
    python handle_connection_errors_ocr.py --verbose
"""

import sys
import time
import argparse
import subprocess
import os
from datetime import datetime
from typing import Optional, Dict, List, Tuple
import threading
import queue

# Third-party imports
try:
    import easyocr
    import numpy as np
    from PIL import Image
    import mss
    import pyautogui
except ImportError as e:
    print(f"Missing required package: {e}")
    print("\nPlease install required packages:")
    print("  pip install easyocr pillow pyautogui mss numpy")
    sys.exit(1)

# ============================================================================
# CONFIGURATION
# ============================================================================

# Monitor interval in seconds (delay after scanning all slots)
MONITOR_INTERVAL = 1.0

# Delay between checking each slot (in seconds) - keep low for responsiveness
SLOT_CHECK_DELAY = 0.1

# Stagnant detection timing
STAGNANT_INITIAL_SUSPECT_SECONDS = 15  # First observation before starting countdown
STAGNANT_CONFIRMATION_SECONDS = 210    # 3.5 minutes confirmation before nudge

# ============================================================================
# ESCALATION / LOOP DETECTION CONFIGURATION
# ============================================================================
# Failsafe system to detect and handle endless loops in Cursor windows
#
# Escalation Levels:
#   0 = Normal operation (OCR handler manages)
#   1 = Nudge 3+ triggered (main Cursor consulted)
#   2 = Main Cursor intervention failed (comprehensive log analysis)
#   3 = Level 2 failed (kill specific Cursor, refill slot)
#   4 = Multiple Level 3 failures (kill all Cursors, MANUAL investigation required)
#
# Flow: Each level gives the system a chance to self-correct before escalating

# Thresholds for escalation
ESCALATION_MAX_NUDGES_BEFORE_MAIN_CURSOR = 3      # Nudges before consulting main Cursor (Level 1)
ESCALATION_MAX_MAIN_CURSOR_INTERVENTIONS = 2      # Main Cursor attempts before Level 2
ESCALATION_MINUTES_UNCHANGED_FOR_LEVEL2 = 15      # Minutes unchanged after intervention = Level 2
ESCALATION_MAX_LEVEL2_FAILURES = 2                # Level 2 failures before Level 3 (kill slot)
ESCALATION_MAX_LEVEL3_SLOTS = 3                   # Slots at Level 3 = Level 4 (kill all)

# History tracking
SLOT_HISTORY_MAX_ENTRIES = 50  # Max history entries per slot (rolling window)
SLOT_HISTORY_FILE = "slot_history.json"
ESCALATION_REPORT_PREFIX = "escalation_report_slot_"
MAIN_CURSOR_ATTENTION_FILE = "needs_main_cursor_attention.json"

# Patterns that indicate a loop (for detection)
LOOP_PATTERN_MIN_REPETITIONS = 5  # Same state N times = potential loop
LOOP_PATTERN_CYCLE_LENGTH = 3     # Detect cycles of this length (e.g., idle->nudge->idle)

# Nudge message to send to stagnant cursors
CONTINUE_INSTRUCTION = """If there's any option to choose, choose the one that best preserves the intention of
AUTOPACK_WAVE_PLAN.json in C:\\Users\\hshk9\\OneDrive\\Backup\\Desktop or README.md in C:\\dev\\Autopack.

If context overflowed, continue from your last summary.

Resolve any issues and continue until you complete the prompt you were initially given.
When done, create PR and run CI."""

# Grid configuration for 5120x1440 monitor with 3x3 grid + main cursor
# Slot 0 = Main Cursor on left side of grid (supervisory)
# Slots 1-9 = Right half of monitor (X starts at 2560), with verified slot positions
GRID_POSITIONS = {
    0: {"x": 1280, "y": 0, "width": 1280, "height": 926},  # Main Cursor (left of grid)
    1: {"x": 2560, "y": 0, "width": 853, "height": 463},  # Top-Left
    2: {"x": 3413, "y": 0, "width": 853, "height": 463},  # Top-Center
    3: {"x": 4266, "y": 0, "width": 854, "height": 463},  # Top-Right
    4: {"x": 2560, "y": 463, "width": 853, "height": 463},  # Mid-Left
    5: {"x": 3413, "y": 463, "width": 853, "height": 463},  # Mid-Center
    6: {"x": 4266, "y": 463, "width": 854, "height": 463},  # Mid-Right
    7: {"x": 2560, "y": 926, "width": 853, "height": 464},  # Bot-Left
    8: {"x": 3413, "y": 926, "width": 853, "height": 464},  # Bot-Center
    9: {"x": 4266, "y": 926, "width": 854, "height": 464},  # Bot-Right
}

# Resume button coordinates (absolute screen positions) - provided by user
RESUME_BUTTON_COORDS = {
    0: {"x": 1920, "y": 463},  # Slot 0 (main cursor)
    1: {"x": 3121, "y": 337},  # Slot 1 (top-left)
    2: {"x": 3979, "y": 337},  # Slot 2 (top-center)
    3: {"x": 4833, "y": 337},  # Slot 3 (top-right)
    4: {"x": 3121, "y": 801},  # Slot 4 (mid-left)
    5: {"x": 3979, "y": 801},  # Slot 5 (mid-center)
    6: {"x": 4833, "y": 801},  # Slot 6 (mid-right)
    7: {"x": 3121, "y": 1264},  # Slot 7 (bot-left)
    8: {"x": 3979, "y": 1264},  # Slot 8 (bot-center)
    9: {"x": 4833, "y": 1264},  # Slot 9 (bot-right)
}

# Keywords to look for in error dialogs (case-insensitive)
ERROR_KEYWORDS = [
    "connection error",
    "connection lost",
    "network error",
    "failed to connect",
    "try again",
    "retry",
    "resume",
    "reconnect",
    "timed out",
    "timeout",
    "server error",
    "unable to connect",
]

# Action button keywords (what we're looking for to click)
ACTION_KEYWORDS = [
    "resume",
    "try again",
    "retry",
    "reconnect",
    "ok",
    "yes",
]

# Approval dialog keywords
APPROVAL_KEYWORDS = [
    "approve",
    "allow",
    "accept",
    "confirm",
    "grant",
]

# Permission dialog keywords (Cursor's permission request dialogs)
# These match the actual dialog text shown in Cursor:
# - "Allow reading from <file>?"
# - "Allow write to <file>?"
# - "Allow glob search in <path>?"
# - "Allow access to <path>?"
# - "Make this edit to <file>?"
# - "Allow this bash command?"
PERMISSION_DIALOG_KEYWORDS = [
    "allow reading from",
    "allow write to",
    "allow glob search",
    "allow access to",
    "make this edit",
    "allow this bash",
    "allow this command",
    "yes, allow",
]

# Permission button keywords (what to click to approve)
PERMISSION_BUTTON_KEYWORDS = [
    "yes, allow",
    "yes allow",
    "for this session",
    "for this project",
]

# NOTE: Merge detection is handled by check_pr_status.ps1 via GitHub API
# OCR-based merge detection was disabled due to false positives

# WIP (Work In Progress) detection keywords - indicates Claude is actively working
# These words appear in the Cursor status area when Claude is processing
WIP_KEYWORDS = [
    "thinking",
    "pondering",
    "generating",
    "writing",
    "analyzing",
    "reading",
    "searching",
    "working",
    "processing",
    "loading",
]

# Words that indicate Claude has finished and is idle/waiting
IDLE_KEYWORDS = [
    "send a message",
    "type a message",
    "ask claude",
    "ask anything",
]


# ============================================================================
# GLOBAL STATE
# ============================================================================


class MonitorState:
    """Global state for the monitoring session."""

    def __init__(self):
        self.error_count = 0
        self.handled_count = 0
        self.session_start = datetime.now()
        self.last_error_time: Dict[int, datetime] = {}
        self.running = True
        self.verbose = False
        self.active_slots: set = set()  # Slots with active Cursor windows
        self.last_slot_scan: datetime = None  # Last time we scanned for active windows

        # Round-robin slot scanning - remember where we left off
        self.last_scanned_slot: int = 0  # Last slot we fully scanned

        # Stagnant detection state
        self.slot_first_idle: Dict[int, datetime] = {}  # When slot first appeared idle
        self.slot_last_working: Dict[int, datetime] = {}  # When slot was last seen working
        self.slot_nudge_count: Dict[int, int] = {}  # Number of nudges sent to each slot
        self.slot_awaiting_summary: Dict[int, bool] = {}  # Slots waiting for LLM summary response


state = MonitorState()


# ============================================================================
# SHARED STAGNANT STATE FILE (for coordination with check_pr_status.ps1)
# ============================================================================

import json

STAGNANT_STATE_FILE = os.path.join(os.path.dirname(__file__), "stagnant_state.json")


def load_stagnant_state() -> dict:
    """Load the shared stagnant state from file."""
    try:
        if os.path.exists(STAGNANT_STATE_FILE):
            with open(STAGNANT_STATE_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        if state.verbose:
            print(f"[WARN] Could not load stagnant state: {e}")
    return {"slots": {}, "last_updated": None}


def save_stagnant_state(state_data: dict) -> None:
    """Save the shared stagnant state to file."""
    try:
        state_data["last_updated"] = datetime.now().isoformat()
        with open(STAGNANT_STATE_FILE, 'w') as f:
            json.dump(state_data, f, indent=2)
    except Exception as e:
        if state.verbose:
            print(f"[WARN] Could not save stagnant state: {e}")


def get_slot_stagnant_info(slot: int) -> Optional[dict]:
    """Get stagnant info for a specific slot from shared state."""
    data = load_stagnant_state()
    return data.get("slots", {}).get(str(slot))


def update_slot_stagnant_state(slot: int, nudge_count: int = -1,
                                first_suspected: str = "", last_nudge: str = "") -> None:
    """Update the shared stagnant state for a slot."""
    data = load_stagnant_state()
    if "slots" not in data:
        data["slots"] = {}

    slot_key = str(slot)
    if slot_key not in data["slots"]:
        data["slots"][slot_key] = {}

    if nudge_count >= 0:
        data["slots"][slot_key]["nudge_count"] = nudge_count
    if first_suspected:
        data["slots"][slot_key]["first_suspected"] = first_suspected
    if last_nudge:
        data["slots"][slot_key]["last_nudge"] = last_nudge

    save_stagnant_state(data)


def increment_slot_nudge_count(slot: int) -> int:
    """Increment nudge count for a slot and return the new count."""
    data = load_stagnant_state()
    slot_key = str(slot)

    if "slots" not in data:
        data["slots"] = {}
    if slot_key not in data["slots"]:
        data["slots"][slot_key] = {"nudge_count": 0}

    current = data["slots"][slot_key].get("nudge_count", 0)
    new_count = current + 1
    data["slots"][slot_key]["nudge_count"] = new_count
    data["slots"][slot_key]["last_nudge"] = datetime.now().isoformat()

    save_stagnant_state(data)
    return new_count


def get_slot_nudge_count(slot: int) -> int:
    """Get the current nudge count for a slot."""
    info = get_slot_stagnant_info(slot)
    return info.get("nudge_count", 0) if info else 0


def clear_slot_stagnant_state(slot: int) -> None:
    """Clear stagnant state for a slot (when it becomes active or PR created)."""
    data = load_stagnant_state()
    slot_key = str(slot)
    if "slots" in data and slot_key in data["slots"]:
        del data["slots"][slot_key]
        save_stagnant_state(data)


def reset_slot_nudge_count(slot: int) -> None:
    """Reset the nudge count for a slot (called when PR is created or task completes)."""
    if slot in state.slot_nudge_count:
        del state.slot_nudge_count[slot]
    if slot in state.slot_awaiting_summary:
        del state.slot_awaiting_summary[slot]
    if slot in state.slot_first_idle:
        del state.slot_first_idle[slot]
    # Also clear the shared stagnant state file so check_pr_status.ps1 sees reset
    clear_slot_stagnant_state(slot)


# ============================================================================
# LOOP DETECTION AND ESCALATION SYSTEM
# ============================================================================
# Failsafe to detect endless loops and escalate appropriately
# Uses accumulated pattern history rather than single-point detection


def load_slot_history() -> dict:
    """Load slot history from JSON file."""
    script_dir = os.path.dirname(__file__)
    history_file = os.path.join(script_dir, SLOT_HISTORY_FILE)
    try:
        if os.path.exists(history_file):
            with open(history_file, "r") as f:
                return json.load(f)
    except Exception as e:
        print(f"[WARN] Failed to load slot history: {e}")
    return {"slots": {}, "global": {"level4_triggered": False}}


def save_slot_history(data: dict) -> None:
    """Save slot history to JSON file."""
    script_dir = os.path.dirname(__file__)
    history_file = os.path.join(script_dir, SLOT_HISTORY_FILE)
    try:
        data["last_updated"] = datetime.now().isoformat()
        with open(history_file, "w") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"[ERROR] Failed to save slot history: {e}")


def record_slot_event(slot: int, state_name: str, action: str, details: str = "") -> None:
    """
    Record an event in slot history for loop detection.

    Args:
        slot: Slot number (1-9)
        state_name: Current state (e.g., "idle_no_pr", "working", "permission_dialog")
        action: Action taken (e.g., "nudge_1", "main_cursor_consulted", "permission_clicked")
        details: Optional details for debugging
    """
    data = load_slot_history()
    slot_key = str(slot)

    if slot_key not in data["slots"]:
        data["slots"][slot_key] = {
            "history": [],
            "escalation_level": 0,
            "main_cursor_interventions": 0,
            "last_state_change": datetime.now().isoformat(),
            "level2_failures": 0,
        }

    slot_data = data["slots"][slot_key]

    # Check if state actually changed
    if slot_data["history"]:
        last_state = slot_data["history"][-1].get("state")
        if last_state != state_name:
            slot_data["last_state_change"] = datetime.now().isoformat()

    # Add new entry
    entry = {
        "timestamp": datetime.now().isoformat(),
        "state": state_name,
        "action": action,
        "details": details,
    }
    slot_data["history"].append(entry)

    # Keep only last N entries (rolling window)
    if len(slot_data["history"]) > SLOT_HISTORY_MAX_ENTRIES:
        slot_data["history"] = slot_data["history"][-SLOT_HISTORY_MAX_ENTRIES:]

    save_slot_history(data)


def detect_loop_pattern(slot: int) -> Optional[str]:
    """
    Analyze slot history to detect loop patterns.

    Returns:
        Pattern name if loop detected, None otherwise
        Patterns: "repeated_state", "nudge_cycle", "intervention_failed"
    """
    data = load_slot_history()
    slot_key = str(slot)

    if slot_key not in data["slots"]:
        return None

    history = data["slots"][slot_key].get("history", [])
    if len(history) < LOOP_PATTERN_MIN_REPETITIONS:
        return None

    recent = history[-LOOP_PATTERN_MIN_REPETITIONS:]

    # Pattern 1: Same state repeated N times
    states = [e["state"] for e in recent]
    if len(set(states)) == 1:
        return "repeated_state"

    # Pattern 2: Cycle detection (e.g., idle->nudge->idle->nudge)
    if len(history) >= LOOP_PATTERN_CYCLE_LENGTH * 2:
        recent_cycle = history[-(LOOP_PATTERN_CYCLE_LENGTH * 2):]
        first_half = [e["state"] for e in recent_cycle[:LOOP_PATTERN_CYCLE_LENGTH]]
        second_half = [e["state"] for e in recent_cycle[LOOP_PATTERN_CYCLE_LENGTH:]]
        if first_half == second_half:
            return "nudge_cycle"

    # Pattern 3: Main cursor intervention didn't help
    slot_data = data["slots"][slot_key]
    if slot_data.get("main_cursor_interventions", 0) >= ESCALATION_MAX_MAIN_CURSOR_INTERVENTIONS:
        # Check if state unchanged for X minutes after intervention
        last_change = slot_data.get("last_state_change")
        if last_change:
            last_change_time = datetime.fromisoformat(last_change)
            minutes_unchanged = (datetime.now() - last_change_time).total_seconds() / 60
            if minutes_unchanged >= ESCALATION_MINUTES_UNCHANGED_FOR_LEVEL2:
                return "intervention_failed"

    return None


def get_slot_escalation_level(slot: int) -> int:
    """Get current escalation level for a slot."""
    data = load_slot_history()
    slot_key = str(slot)
    if slot_key in data["slots"]:
        return data["slots"][slot_key].get("escalation_level", 0)
    return 0


def set_slot_escalation_level(slot: int, level: int) -> None:
    """Set escalation level for a slot."""
    data = load_slot_history()
    slot_key = str(slot)

    if slot_key not in data["slots"]:
        data["slots"][slot_key] = {
            "history": [],
            "escalation_level": level,
            "main_cursor_interventions": 0,
            "last_state_change": datetime.now().isoformat(),
            "level2_failures": 0,
        }
    else:
        data["slots"][slot_key]["escalation_level"] = level

    save_slot_history(data)
    print(f"  [Slot {slot}] Escalation level set to {level}")


def increment_main_cursor_interventions(slot: int) -> int:
    """Increment and return the main cursor intervention count for a slot."""
    data = load_slot_history()
    slot_key = str(slot)

    if slot_key not in data["slots"]:
        data["slots"][slot_key] = {
            "history": [],
            "escalation_level": 0,
            "main_cursor_interventions": 1,
            "last_state_change": datetime.now().isoformat(),
            "level2_failures": 0,
        }
    else:
        data["slots"][slot_key]["main_cursor_interventions"] = \
            data["slots"][slot_key].get("main_cursor_interventions", 0) + 1

    count = data["slots"][slot_key]["main_cursor_interventions"]
    save_slot_history(data)
    return count


def clear_slot_history(slot: int) -> None:
    """Clear history for a slot (when slot becomes healthy)."""
    data = load_slot_history()
    slot_key = str(slot)
    if slot_key in data["slots"]:
        del data["slots"][slot_key]
        save_slot_history(data)


def generate_escalation_report(slot: int, reason: str) -> str:
    """
    Generate a structured escalation report for main Cursor to analyze.

    Returns:
        Path to the generated report file
    """
    data = load_slot_history()
    slot_key = str(slot)
    slot_data = data["slots"].get(slot_key, {})

    # Get recent OCR samples from state if available
    ocr_samples = []

    report = {
        "slot": slot,
        "escalation_time": datetime.now().isoformat(),
        "reason": reason,
        "summary": {
            "total_history_entries": len(slot_data.get("history", [])),
            "main_cursor_interventions": slot_data.get("main_cursor_interventions", 0),
            "current_escalation_level": slot_data.get("escalation_level", 0),
            "level2_failures": slot_data.get("level2_failures", 0),
            "last_state_change": slot_data.get("last_state_change", "unknown"),
            "pattern_detected": detect_loop_pattern(slot),
        },
        "recent_history": slot_data.get("history", [])[-10:],  # Last 10 entries
        "recommended_actions": [],
    }

    # Add recommendations based on escalation level
    level = slot_data.get("escalation_level", 0)
    if level >= 3:
        report["recommended_actions"].append("kill_and_refill_slot")
    elif level >= 2:
        report["recommended_actions"].append("deep_analysis_required")
        report["recommended_actions"].append("consider_killing_slot")
    else:
        report["recommended_actions"].append("continue_monitoring")

    # Save report
    script_dir = os.path.dirname(__file__)
    report_file = os.path.join(script_dir, f"{ESCALATION_REPORT_PREFIX}{slot}.json")
    try:
        with open(report_file, "w") as f:
            json.dump(report, f, indent=2)
        print(f"  [Slot {slot}] Escalation report saved to: {report_file}")
    except Exception as e:
        print(f"[ERROR] Failed to save escalation report: {e}")

    return report_file


def notify_main_cursor_attention(slots: list, reason: str, action_required: str) -> None:
    """
    Write a notification file for main Cursor to read.
    Main Cursor can poll this file to know when attention is needed.
    """
    script_dir = os.path.dirname(__file__)
    attention_file = os.path.join(script_dir, MAIN_CURSOR_ATTENTION_FILE)

    notification = {
        "timestamp": datetime.now().isoformat(),
        "slots_needing_attention": slots,
        "reason": reason,
        "action_required": action_required,
        "escalation_reports": [
            os.path.join(script_dir, f"{ESCALATION_REPORT_PREFIX}{s}.json")
            for s in slots
        ],
        "acknowledged": False,
    }

    try:
        with open(attention_file, "w") as f:
            json.dump(notification, f, indent=2)
        print(f"\n[ESCALATION] Main Cursor attention required!")
        print(f"  Slots: {slots}")
        print(f"  Reason: {reason}")
        print(f"  Action: {action_required}")
        print(f"  Notification file: {attention_file}")
    except Exception as e:
        print(f"[ERROR] Failed to write attention notification: {e}")


def check_level4_trigger() -> bool:
    """
    Check if Level 4 (kill all) should be triggered.
    Returns True if multiple slots are at Level 3.
    """
    data = load_slot_history()
    level3_slots = []

    for slot_key, slot_data in data.get("slots", {}).items():
        if slot_data.get("escalation_level", 0) >= 3:
            level3_slots.append(int(slot_key))

    return len(level3_slots) >= ESCALATION_MAX_LEVEL3_SLOTS


def kill_cursor_slot(slot: int, verbose: bool = False) -> bool:
    """
    Kill the Cursor window for a specific slot.

    Returns:
        True if kill was successful
    """
    try:
        script_dir = os.path.dirname(__file__)
        # Use the existing close script
        close_script = os.path.join(script_dir, "close_cursor_window_slot.ps1")

        if os.path.exists(close_script):
            result = subprocess.run(
                ["powershell", "-ExecutionPolicy", "Bypass", "-File", close_script, str(slot)],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                print(f"  [Slot {slot}] Cursor window killed successfully")
                return True
            else:
                print(f"  [Slot {slot}] Failed to kill: {result.stderr}")
        else:
            # Fallback: try to kill via taskkill with window title matching
            print(f"  [Slot {slot}] close_cursor_window_slot.ps1 not found, using fallback")
            # This is a simplified fallback - may need adjustment

        return False

    except Exception as e:
        print(f"[ERROR] Failed to kill slot {slot}: {e}")
        return False


def kill_all_cursor_slots(verbose: bool = False) -> bool:
    """
    Kill all Cursor windows (Level 4 action).
    Does NOT restart workflow - requires manual investigation.

    Returns:
        True if kill was successful
    """
    try:
        script_dir = os.path.dirname(__file__)
        kill_all_script = os.path.join(script_dir, "kill_all_cursor.bat")

        if os.path.exists(kill_all_script):
            print("\n" + "=" * 60)
            print("[LEVEL 4 ESCALATION] Killing all Cursor windows!")
            print("=" * 60)
            print("MANUAL INVESTIGATION REQUIRED after this action.")
            print("The system detected multiple slots in endless loops.")
            print("Check escalation reports for details.")
            print("=" * 60 + "\n")

            result = subprocess.run(
                [kill_all_script],
                capture_output=True,
                text=True,
                timeout=60,
                shell=True
            )

            # Mark Level 4 as triggered in history
            data = load_slot_history()
            data["global"]["level4_triggered"] = True
            data["global"]["level4_timestamp"] = datetime.now().isoformat()
            data["global"]["level4_reason"] = "Multiple slots reached Level 3"
            save_slot_history(data)

            # TODO: Future enhancement - auto-open main Cursor, navigate to Autopack,
            # paste investigation prompt. For now, just notify and stop.
            # This would require:
            # 1. Opening main Cursor window
            # 2. Navigating to C:\dev\Autopack
            # 3. Pasting a prompt like "Investigate the escalation reports in scripts/"
            # 4. But this is complex and risky - better to require manual intervention

            return result.returncode == 0
        else:
            print(f"[ERROR] kill_all_cursor.bat not found at {kill_all_script}")
            return False

    except Exception as e:
        print(f"[ERROR] Failed to kill all Cursors: {e}")
        return False


def handle_escalation(slot: int, nudge_count: int, verbose: bool = False) -> str:
    """
    Handle escalation based on current state and history.

    Returns:
        Action taken: "nudge", "consult_main_cursor", "kill_slot", "kill_all", "none"
    """
    current_level = get_slot_escalation_level(slot)
    loop_pattern = detect_loop_pattern(slot)

    if verbose:
        print(f"  [Slot {slot}] Escalation check: level={current_level}, nudges={nudge_count}, pattern={loop_pattern}")

    # Check for Level 4 first (multiple Level 3 slots)
    if check_level4_trigger():
        notify_main_cursor_attention(
            list(range(1, 10)),
            "Multiple slots reached Level 3 - system-wide failure",
            "KILL_ALL_MANUAL_INVESTIGATION"
        )
        # Generate reports for all affected slots
        data = load_slot_history()
        for slot_key, slot_data in data.get("slots", {}).items():
            if slot_data.get("escalation_level", 0) >= 3:
                generate_escalation_report(int(slot_key), "level4_trigger")

        kill_all_cursor_slots(verbose)
        return "kill_all"

    # Level 3: Kill specific slot
    if current_level >= 3 or (loop_pattern == "intervention_failed" and current_level >= 2):
        set_slot_escalation_level(slot, 3)
        generate_escalation_report(slot, f"level3_kill_slot_{loop_pattern or 'escalation'}")

        if kill_cursor_slot(slot, verbose):
            record_slot_event(slot, "killed", "level3_kill", f"Pattern: {loop_pattern}")
            # Note: auto_fill_empty_slots will refill this slot on next run
            return "kill_slot"

    # Level 2: Generate comprehensive report for main Cursor
    if current_level >= 2 or loop_pattern in ["intervention_failed", "repeated_state"]:
        set_slot_escalation_level(slot, 2)

        # Increment level2 failures
        data = load_slot_history()
        slot_key = str(slot)
        if slot_key in data["slots"]:
            data["slots"][slot_key]["level2_failures"] = \
                data["slots"][slot_key].get("level2_failures", 0) + 1

            if data["slots"][slot_key]["level2_failures"] >= ESCALATION_MAX_LEVEL2_FAILURES:
                set_slot_escalation_level(slot, 3)
                save_slot_history(data)
                return handle_escalation(slot, nudge_count, verbose)  # Re-check for Level 3

            save_slot_history(data)

        report_path = generate_escalation_report(slot, f"level2_{loop_pattern or 'analysis'}")
        notify_main_cursor_attention(
            [slot],
            f"Slot {slot} needs deep analysis - pattern: {loop_pattern}",
            "READ_ESCALATION_REPORT"
        )
        return "consult_main_cursor"

    # Level 1: Consult main Cursor (nudge 3+)
    if nudge_count >= ESCALATION_MAX_NUDGES_BEFORE_MAIN_CURSOR:
        intervention_count = increment_main_cursor_interventions(slot)
        set_slot_escalation_level(slot, 1)

        if intervention_count >= ESCALATION_MAX_MAIN_CURSOR_INTERVENTIONS:
            # Too many interventions, escalate to Level 2
            set_slot_escalation_level(slot, 2)
            return handle_escalation(slot, nudge_count, verbose)

        record_slot_event(slot, "idle_no_pr", f"main_cursor_intervention_{intervention_count}", "")
        return "consult_main_cursor"

    # Normal nudge
    record_slot_event(slot, "idle_no_pr", f"nudge_{nudge_count}", "")
    return "nudge"


# ============================================================================
# WIP DETECTION AND STAGNANT HANDLING
# ============================================================================


def detect_wip_in_slot(
    ocr: "OCREngine", capture: "ScreenCapture", slot: int, verbose: bool = False
) -> bool:
    """
    Detect if Claude is actively working in the given slot (WIP = Work In Progress).

    Checks the footer/status area of the window for WIP keywords like
    "thinking", "generating", "writing", etc.

    Returns:
        True if slot shows Claude is actively working
    """
    try:
        # Capture the footer area where status text appears
        image = capture.capture_slot_footer(slot, footer_height=100)
        texts = ocr.extract_text(image)

        if verbose and texts:
            text_strs = [t for t, _ in texts[:5]]
            print(f"  [Slot {slot}] WIP check - Footer text: {text_strs}")

        # Check for WIP keywords
        return ocr.contains_keywords(texts, WIP_KEYWORDS)

    except Exception as e:
        if verbose:
            print(f"[ERROR] WIP detection failed for slot {slot}: {e}")
        return False


def detect_idle_in_slot(
    ocr: "OCREngine", capture: "ScreenCapture", slot: int, verbose: bool = False
) -> bool:
    """
    Detect if the slot is idle (showing chat input prompt).

    Returns:
        True if slot appears to be idle/waiting for input
    """
    try:
        image = capture.capture_slot_footer(slot, footer_height=100)
        texts = ocr.extract_text(image)

        if verbose and texts:
            text_strs = [t for t, _ in texts[:5]]
            print(f"  [Slot {slot}] Idle check - Footer text: {text_strs}")

        return ocr.contains_keywords(texts, IDLE_KEYWORDS)

    except Exception as e:
        if verbose:
            print(f"[ERROR] Idle detection failed for slot {slot}: {e}")
        return False


def check_slot_has_pr(slot: int, verbose: bool = False) -> bool:
    """
    Check if a slot has an open PR by calling check_pr_status.ps1.

    Returns:
        True if PR exists for the slot
    """
    try:
        script_dir = os.path.dirname(__file__)
        check_script = os.path.join(script_dir, "check_pr_status.ps1")

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", check_script, "-CheckSlotPR", str(slot)],
            capture_output=True,
            text=True,
            timeout=30
        )

        # Exit code 0 = PR exists, 1 = no PR
        has_pr = result.returncode == 0

        if verbose:
            print(f"  [Slot {slot}] PR check: {'PR exists' if has_pr else 'No PR'}")

        return has_pr

    except Exception as e:
        if verbose:
            print(f"[WARN] PR check failed for slot {slot}: {e}")
        return False


def send_nudge_to_slot(slot: int, message: str, verbose: bool = False) -> bool:
    """
    Send a nudge message to a stagnant slot using send_message_to_cursor_slot.ps1.

    Args:
        slot: Slot number (1-9)
        message: Message to send

    Returns:
        True if nudge was sent successfully
    """
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] SENDING NUDGE TO SLOT {slot}")

        script_dir = os.path.dirname(__file__)
        send_script = os.path.join(script_dir, "send_message_to_cursor_slot.ps1")

        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", send_script,
             "-SlotNumber", str(slot), "-Message", message],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0:
            print(f"  [OK] Nudge sent to slot {slot}")
            return True
        else:
            print(f"  [WARN] Nudge failed for slot {slot}: {result.stderr}")
            return False

    except Exception as e:
        print(f"[ERROR] Nudge to slot {slot} failed: {e}")
        return False


def process_stagnant_slot(
    slot: int, ocr: "OCREngine", capture: "ScreenCapture", verbose: bool = False
) -> None:
    """
    Process a slot that has been confirmed stagnant.

    Implements tiered nudging with escalation failsafe:
    - Nudge 1-2: Send CONTINUE_INSTRUCTION
    - Nudge 3+: Escalation system takes over (Level 1+)

    Escalation Levels:
      Level 0: Normal operation (OCR handler manages via nudges)
      Level 1: Main Cursor consulted (nudge 3+)
      Level 2: Main Cursor intervention failed (comprehensive log analysis)
      Level 3: Level 2 failed (kill specific Cursor, refill slot)
      Level 4: Multiple Level 3 failures (kill all Cursors, MANUAL investigation required)
    """
    # First check if PR exists - if so, stop nudging and let PR monitor handle it
    if check_slot_has_pr(slot, verbose):
        print(f"  [INFO] Slot {slot} has PR - stopping nudge, PR monitor will handle")
        reset_slot_nudge_count(slot)
        # Clear escalation state since PR exists
        set_slot_escalation_level(slot, 0)
        return

    # Increment nudge count
    nudge_count = increment_slot_nudge_count(slot)
    timestamp = datetime.now().strftime("%H:%M:%S")

    # Use escalation system to determine action
    action = handle_escalation(slot, nudge_count, verbose)

    if action == "nudge":
        # Standard nudge (Level 0)
        print(f"[{timestamp}] Slot {slot} stagnant - sending nudge #{nudge_count}")
        send_nudge_to_slot(slot, CONTINUE_INSTRUCTION, verbose)
    elif action == "consult_main_cursor":
        # Level 1 or 2: Flag for main LLM consultation
        print(f"[{timestamp}] Slot {slot} escalated to main Cursor after {nudge_count} nudges")
        state.slot_awaiting_summary[slot] = True
        # Main Cursor will poll needs_main_cursor_attention.json for details
    elif action == "kill_slot":
        # Level 3: Slot was killed, will be refilled by auto_fill_empty_slots
        print(f"[{timestamp}] Slot {slot} killed due to repeated failures - will be refilled")
        state.slot_awaiting_summary[slot] = False
        reset_slot_nudge_count(slot)
    elif action == "kill_all":
        # Level 4: All slots killed, requires MANUAL investigation
        print(f"[{timestamp}] === LEVEL 4 ESCALATION: ALL SLOTS KILLED ===")
        print(f"[{timestamp}] MANUAL INVESTIGATION REQUIRED - Check escalation reports")
        print(f"[{timestamp}] Reports in: C:\\dev\\Autopack\\scripts\\escalation_report_slot_*.json")
        print(f"[{timestamp}] OCR handler stopping - restart manually after investigation")


# ============================================================================
# OCR ENGINE
# ============================================================================


class OCREngine:
    """EasyOCR-based text recognition engine."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.reader = None
        self._init_lock = threading.Lock()

    def initialize(self):
        """Initialize EasyOCR reader (lazy loading - takes a few seconds)."""
        with self._init_lock:
            if self.reader is None:
                print("[INFO] Initializing EasyOCR (this may take a moment)...")
                # Use English only for speed, GPU if available
                self.reader = easyocr.Reader(["en"], gpu=True, verbose=self.verbose)
                print("[INFO] EasyOCR initialized successfully")

    def extract_text(self, image: np.ndarray) -> List[Tuple[str, float]]:
        """
        Extract text from image using OCR.

        Args:
            image: numpy array of the image (RGB)

        Returns:
            List of (text, confidence) tuples
        """
        if self.reader is None:
            self.initialize()

        try:
            # EasyOCR returns list of (bbox, text, confidence)
            results = self.reader.readtext(image)
            return [(text.lower(), conf) for (_, text, conf) in results]
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] OCR extraction failed: {e}")
            return []

    def contains_keywords(
        self, texts: List[Tuple[str, float]], keywords: List[str], min_confidence: float = 0.3
    ) -> bool:
        """Check if any extracted text contains the given keywords."""
        for text, confidence in texts:
            if confidence < min_confidence:
                continue
            for keyword in keywords:
                if keyword.lower() in text:
                    return True
        return False

    def find_keyword_location(
        self, image: np.ndarray, keywords: List[str]
    ) -> Optional[Tuple[int, int]]:
        """
        Find the center location of text matching keywords.

        Returns:
            (x, y) center of the matching text, or None if not found
        """
        if self.reader is None:
            self.initialize()

        try:
            results = self.reader.readtext(image)
            for bbox, text, confidence in results:
                if confidence < 0.3:
                    continue
                text_lower = text.lower()
                for keyword in keywords:
                    if keyword.lower() in text_lower:
                        # bbox is [[x1,y1], [x2,y1], [x2,y2], [x1,y2]]
                        x_center = int((bbox[0][0] + bbox[2][0]) / 2)
                        y_center = int((bbox[0][1] + bbox[2][1]) / 2)
                        return (x_center, y_center)
        except Exception as e:
            if self.verbose:
                print(f"[ERROR] Keyword location failed: {e}")
        return None


# ============================================================================
# SCREEN CAPTURE
# ============================================================================


class ScreenCapture:
    """Screen capture using MSS (faster than PIL.ImageGrab)."""

    def __init__(self):
        self.sct = mss.mss()

    def capture_region(self, x: int, y: int, width: int, height: int) -> np.ndarray:
        """
        Capture a region of the screen.

        Returns:
            numpy array in RGB format suitable for EasyOCR
        """
        monitor = {"left": x, "top": y, "width": width, "height": height}
        screenshot = self.sct.grab(monitor)

        # Convert to numpy array (BGRA -> RGB)
        img = np.array(screenshot)
        img = img[:, :, :3]  # Remove alpha channel
        img = img[:, :, ::-1]  # BGR to RGB

        return img

    def capture_slot(self, slot: int) -> np.ndarray:
        """Capture a specific grid slot."""
        pos = GRID_POSITIONS[slot]
        return self.capture_region(pos["x"], pos["y"], pos["width"], pos["height"])

    def capture_slot_bottom_portion(self, slot: int, portion: float = 0.67) -> np.ndarray:
        """Capture the bottom portion of a grid slot (for dialog detection)."""
        pos = GRID_POSITIONS[slot]
        skip_height = int(pos["height"] * (1 - portion))
        return self.capture_region(
            pos["x"],
            pos["y"] + skip_height,
            pos["width"],
            pos["height"] - skip_height
        )

    def capture_slot_footer(self, slot: int, footer_height: int = 80) -> np.ndarray:
        """Capture just the footer area of a slot (for status bar detection)."""
        pos = GRID_POSITIONS[slot]
        return self.capture_region(
            pos["x"],
            pos["y"] + pos["height"] - footer_height,
            pos["width"],
            footer_height
        )

    def capture_permission_area(self, slot: int) -> np.ndarray:
        """Capture the area where permission dialogs typically appear."""
        # Permission dialogs appear in the bottom 2/3 of the window
        return self.capture_slot_bottom_portion(slot, portion=0.67)


# ============================================================================
# ACTIVE WINDOW DETECTION
# ============================================================================


def get_active_cursor_slots(verbose: bool = False) -> set:
    """
    Detect which grid slots have active Cursor windows.

    Uses PowerShell to enumerate Cursor windows and map them to grid slots
    based on their screen position.

    Returns:
        Set of slot numbers (1-9) that have active Cursor windows
    """
    try:
        ps_script = """
Add-Type @"
using System;
using System.Runtime.InteropServices;
using System.Text;
using System.Collections.Generic;

public class WindowEnumerator {
    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [DllImport("user32.dll")]
    public static extern int GetWindowTextLength(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int GetWindowText(IntPtr hWnd, StringBuilder lpString, int nMaxCount);

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    public delegate bool EnumWindowsProc(IntPtr hWnd, IntPtr lParam);

    [DllImport("user32.dll")]
    public static extern bool EnumWindows(EnumWindowsProc lpEnumFunc, IntPtr lParam);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public static List<int[]> cursorWindows = new List<int[]>();

    public static bool EnumCallback(IntPtr hWnd, IntPtr lParam) {
        if (IsWindowVisible(hWnd)) {
            int length = GetWindowTextLength(hWnd);
            if (length > 0) {
                StringBuilder sb = new StringBuilder(length + 1);
                GetWindowText(hWnd, sb, sb.Capacity);
                string title = sb.ToString();
                if (title.Contains("Cursor") || title.Contains("cursor")) {
                    RECT rect;
                    if (GetWindowRect(hWnd, out rect)) {
                        cursorWindows.Add(new int[] { rect.Left, rect.Top });
                    }
                }
            }
        }
        return true;
    }

    public static void FindCursorWindows() {
        cursorWindows.Clear();
        EnumWindows(EnumCallback, IntPtr.Zero);
    }
}
"@

[WindowEnumerator]::FindCursorWindows()
foreach ($pos in [WindowEnumerator]::cursorWindows) {
    Write-Output "$($pos[0]),$($pos[1])"
}
"""
        result = subprocess.run(
            ["powershell", "-ExecutionPolicy", "Bypass", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=5,
        )

        active_slots = set()
        tolerance = 100

        for line in result.stdout.strip().split("\n"):
            if "," not in line:
                continue
            try:
                x, y = map(int, line.split(","))

                # Map window position to slot number
                for slot, pos in GRID_POSITIONS.items():
                    if abs(x - pos["x"]) < tolerance and abs(y - pos["y"]) < tolerance:
                        active_slots.add(slot)
                        break
            except ValueError:
                continue

        if verbose:
            print(f"  [DEBUG] Active Cursor windows in slots: {sorted(active_slots)}")

        return active_slots

    except Exception as e:
        if verbose:
            print(f"  [ERROR] Failed to detect active windows: {e}")
        # Return all slots as fallback (0-9 includes main cursor)
        return set(range(0, 10))


# ============================================================================
# ERROR DETECTION AND HANDLING
# ============================================================================


def detect_error_in_slot(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> bool:
    """
    Detect if an error dialog is present in the given grid slot.

    Returns:
        True if error dialog detected
    """
    try:
        # Capture the grid slot
        image = capture.capture_slot(slot)

        # Extract text from image
        texts = ocr.extract_text(image)

        if verbose and texts:
            print(f"  [Slot {slot}] Detected text: {[t for t, _ in texts[:5]]}")

        # Check for error keywords
        has_error = ocr.contains_keywords(texts, ERROR_KEYWORDS)

        return has_error

    except Exception as e:
        if verbose:
            print(f"[ERROR] Detection failed for slot {slot}: {e}")
        return False


def detect_approval_in_slot(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> bool:
    """
    Detect if an approval dialog is present in the given grid slot.

    Returns:
        True if approval dialog detected
    """
    try:
        image = capture.capture_slot(slot)
        texts = ocr.extract_text(image)

        if verbose and texts:
            print(f"  [Slot {slot}] Detected text: {[t for t, _ in texts[:5]]}")

        return ocr.contains_keywords(texts, APPROVAL_KEYWORDS)

    except Exception as e:
        if verbose:
            print(f"[ERROR] Approval detection failed for slot {slot}: {e}")
        return False


def click_resume_button(slot: int, verbose: bool = False) -> bool:
    """
    Click the Resume button for the given grid slot using pre-mapped coordinates.

    Returns:
        True if click was successful
    """
    try:
        coords = RESUME_BUTTON_COORDS[slot]
        x, y = coords["x"], coords["y"]

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Clicking Resume button at ({x}, {y}) for slot {slot}")

        # Move and click
        pyautogui.click(x, y)

        if verbose:
            print("  [OK] Click executed successfully")

        return True

    except Exception as e:
        print(f"[ERROR] Click failed for slot {slot}: {e}")
        return False


def click_detected_button(
    ocr: OCREngine,
    capture: ScreenCapture,
    slot: int,
    keywords: List[str],
    verbose: bool = False,
    y_offset: int = 0,
) -> bool:
    """
    Find and click a button with text matching keywords in the given slot.

    This is an alternative to using pre-mapped coordinates - it dynamically
    finds the button location using OCR.

    Args:
        y_offset: Additional Y offset to add (positive = down, negative = up)
                  Useful for buttons where OCR bbox center is slightly off

    Returns:
        True if button found and clicked
    """
    try:
        image = capture.capture_slot(slot)
        location = ocr.find_keyword_location(image, keywords)

        if location is None:
            if verbose:
                print(f"  [Slot {slot}] Could not find button with keywords: {keywords}")
            return False

        # Convert relative position to absolute screen position
        pos = GRID_POSITIONS[slot]
        abs_x = pos["x"] + location[0]
        abs_y = pos["y"] + location[1] + y_offset

        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] Clicking detected button at ({abs_x}, {abs_y}) for slot {slot}")

        pyautogui.click(abs_x, abs_y)
        return True

    except Exception as e:
        print(f"[ERROR] Dynamic click failed for slot {slot}: {e}")
        return False


def handle_error(ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False) -> bool:
    """
    Handle a detected error in the given grid slot.

    Strategy:
    1. First try pre-mapped Resume button coordinates (faster, reliable)
    2. If that doesn't work, try dynamic button detection

    Returns:
        True if error was handled
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] ERROR DETECTED IN GRID SLOT {slot}")

    state.error_count += 1

    # Check cooldown (don't handle same slot within 5 seconds)
    last_time = state.last_error_time.get(slot)
    if last_time and (datetime.now() - last_time).total_seconds() < 5:
        if verbose:
            print(f"  [SKIP] Slot {slot} handled recently, cooling down...")
        return False

    # Try pre-mapped coordinates first (most reliable)
    print("  Attempting click at pre-mapped Resume button coordinates...")
    if click_resume_button(slot, verbose):
        state.handled_count += 1
        state.last_error_time[slot] = datetime.now()
        print("  [OK] Error handled via pre-mapped coordinates")
        return True

    # Fallback to dynamic detection
    print("  Trying dynamic button detection...")
    if click_detected_button(ocr, capture, slot, ACTION_KEYWORDS, verbose):
        state.handled_count += 1
        state.last_error_time[slot] = datetime.now()
        print("  [OK] Error handled via dynamic detection")
        return True

    print(f"  [WARN] Could not handle error in slot {slot}")
    return False


def handle_approval(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> bool:
    """
    Handle an approval dialog in the given grid slot.

    Returns:
        True if approval was handled
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] APPROVAL DIALOG DETECTED IN GRID SLOT {slot}")

    # Try to find and click the Approve/Allow button
    if click_detected_button(ocr, capture, slot, APPROVAL_KEYWORDS, verbose):
        print("  [OK] Approval dialog handled")
        return True

    print(f"  [WARN] Could not find approval button in slot {slot}")
    return False


def detect_permission_dialog_in_slot(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> bool:
    """
    Detect if a permission dialog ("Allow this bash command?") is present.

    Returns:
        True if permission dialog detected
    """
    try:
        image = capture.capture_slot(slot)
        texts = ocr.extract_text(image)

        if verbose and texts:
            print(f"  [Slot {slot}] Permission check - Detected text: {[t for t, _ in texts[:8]]}")

        return ocr.contains_keywords(texts, PERMISSION_DIALOG_KEYWORDS)

    except Exception as e:
        if verbose:
            print(f"[ERROR] Permission detection failed for slot {slot}: {e}")
        return False


def handle_permission_dialog(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> bool:
    """
    Handle a permission dialog ("Allow this bash command?") in the given grid slot.

    Strategy:
    1. Try to find and click "Yes, allow for this session" or similar
    2. Fall back to clicking "Yes" if specific button not found

    Returns:
        True if permission was granted
    """
    timestamp = datetime.now().strftime("%H:%M:%S")
    print(f"\n[{timestamp}] PERMISSION DIALOG DETECTED IN GRID SLOT {slot}")
    print("  Dialog: 'Allow this bash command?'")

    state.error_count += 1  # Track as handled event

    # Check cooldown (don't handle same slot within 3 seconds)
    last_time = state.last_error_time.get(slot)
    if last_time and (datetime.now() - last_time).total_seconds() < 3:
        if verbose:
            print(f"  [SKIP] Slot {slot} handled recently, cooling down...")
        return False

    # Try to find "Yes, allow for this session" or "Yes, allow for this project"
    # Add small Y offset (+5) to click more towards center of button
    print("  Looking for 'Yes, allow for this session' button...")
    if click_detected_button(ocr, capture, slot, PERMISSION_BUTTON_KEYWORDS, verbose, y_offset=5):
        state.handled_count += 1
        state.last_error_time[slot] = datetime.now()
        print("  [OK] Permission granted (session/project scope)")
        return True

    # Fall back to just clicking "Yes"
    print("  Falling back to 'Yes' button...")
    if click_detected_button(ocr, capture, slot, ["yes"], verbose, y_offset=5):
        state.handled_count += 1
        state.last_error_time[slot] = datetime.now()
        print("  [OK] Permission granted (single command)")
        return True

    print(f"  [WARN] Could not find permission button in slot {slot}")
    return False


# ============================================================================
# AUTO-FILL TRIGGER
# ============================================================================
# NOTE: Merge detection was removed - it's handled by check_pr_status.ps1 via GitHub API
# OCR-based merge detection was disabled due to false positives


def trigger_auto_fill(verbose: bool = False) -> bool:
    """
    Trigger the auto-fill script to fill empty slots with next available phases.

    Returns:
        True if auto-fill was triggered successfully
    """
    try:
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"\n[{timestamp}] TRIGGERING AUTO-FILL...")

        script_path = r"C:\dev\Autopack\scripts\auto_fill_empty_slots.ps1"

        if not os.path.exists(script_path):
            print(f"  [ERROR] Auto-fill script not found: {script_path}")
            return False

        # Run auto-fill in background (non-blocking)
        subprocess.Popen(
            ["powershell", "-ExecutionPolicy", "Bypass", "-File", script_path],
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,
        )

        print("  [OK] Auto-fill triggered in new window")
        return True

    except Exception as e:
        print(f"  [ERROR] Failed to trigger auto-fill: {e}")
        return False


# ============================================================================
# MAIN MONITORING LOOP
# ============================================================================


def print_banner():
    """Print startup banner."""
    print()
    print("=" * 60)
    print(" CONNECTION ERROR HANDLER (OCR-BASED)")
    print("=" * 60)
    print()
    print("Status: INITIALIZING")
    print("Method: EasyOCR text recognition + coordinate-based clicking")
    print("Grid: 3x3 (9 Cursor windows)")
    print("Press Ctrl+C to stop")
    print()
    print("This handler:")
    print("  [+] Detects which slots have active Cursor windows")
    print("  [+] Only scans slots with active windows (skips empty slots)")
    print("  [+] Uses OCR to detect error/approval text")
    print("  [+] Clicks Resume/Approve buttons automatically")
    print("  [+] Auto-clicks 'Yes' on permission dialogs")
    print("      ('Allow this bash command?' prompts)")
    print("  [+] Detects stagnant slots and sends nudges")
    print()
    print("NOTE: Merge detection handled by check_pr_status.ps1 via GitHub API")
    print()
    print("=" * 60)
    print()


def print_summary():
    """Print session summary."""
    duration = datetime.now() - state.session_start
    hours = int(duration.total_seconds() // 3600)
    minutes = int((duration.total_seconds() % 3600) // 60)
    seconds = int(duration.total_seconds() % 60)

    print()
    print("=" * 60)
    print(" SESSION SUMMARY")
    print("=" * 60)
    print()
    print(f"  Session Duration:  {hours}h {minutes}m {seconds}s")
    print(f"  Errors Detected:   {state.error_count}")
    print(f"  Errors Handled:    {state.handled_count}")
    print()
    print("Monitor stopped.")
    print()


def get_round_robin_slots(active_slots: set, last_slot: int) -> List[int]:
    """
    Return active slots in round-robin order starting after last_slot.

    This ensures fair attention to all slots instead of always starting from slot 1.
    """
    sorted_slots = sorted(active_slots)
    if not sorted_slots:
        return []

    # Find where to start in the sorted list
    start_idx = 0
    for i, slot in enumerate(sorted_slots):
        if slot > last_slot:
            start_idx = i
            break
    else:
        # All slots are <= last_slot, wrap around to start
        start_idx = 0

    # Return slots in round-robin order
    return sorted_slots[start_idx:] + sorted_slots[:start_idx]


def check_stagnant_status(
    ocr: OCREngine, capture: ScreenCapture, slot: int, verbose: bool = False
) -> None:
    """
    Check and update stagnant status for a slot.

    Stagnant detection flow:
    1. If WIP detected: slot is working, clear any stagnant state
    2. If idle for first time: record first_idle timestamp
    3. If idle for > STAGNANT_INITIAL_SUSPECT_SECONDS: start confirmation countdown
    4. If idle for > STAGNANT_CONFIRMATION_SECONDS: trigger nudge

    Total time before nudge = STAGNANT_INITIAL_SUSPECT_SECONDS + STAGNANT_CONFIRMATION_SECONDS
    """
    now = datetime.now()

    # Check if Claude is actively working (WIP)
    is_working = detect_wip_in_slot(ocr, capture, slot, verbose)

    if is_working:
        # Slot is working - clear any stagnant state
        if slot in state.slot_first_idle:
            if verbose:
                print(f"  [Slot {slot}] Now working - clearing stagnant state")
            del state.slot_first_idle[slot]
        state.slot_last_working[slot] = now
        # Also clear shared state file
        clear_slot_stagnant_state(slot)
        return

    # Slot is not showing WIP - check if idle
    is_idle = detect_idle_in_slot(ocr, capture, slot, verbose)

    if not is_idle:
        # Neither working nor idle - might be in transition, skip
        if verbose:
            print(f"  [Slot {slot}] Neither WIP nor idle - skipping stagnant check")
        return

    # Slot is idle
    if slot not in state.slot_first_idle:
        # First observation of idle
        state.slot_first_idle[slot] = now
        if verbose:
            print(f"  [Slot {slot}] First observation: idle (starting suspect timer)")

        # Update shared state with first suspected time
        update_slot_stagnant_state(slot, first_suspected=now.isoformat())
        return

    # Calculate how long slot has been idle
    idle_duration = (now - state.slot_first_idle[slot]).total_seconds()

    # Phase 1: Initial suspect period (15 seconds)
    if idle_duration < STAGNANT_INITIAL_SUSPECT_SECONDS:
        if verbose:
            remaining = STAGNANT_INITIAL_SUSPECT_SECONDS - idle_duration
            print(f"  [Slot {slot}] Suspect phase: {idle_duration:.0f}s idle ({remaining:.0f}s to confirm)")
        return

    # Phase 2: Confirmation period (210 seconds)
    confirmation_duration = idle_duration - STAGNANT_INITIAL_SUSPECT_SECONDS

    if confirmation_duration < STAGNANT_CONFIRMATION_SECONDS:
        # Still in confirmation period
        remaining = STAGNANT_CONFIRMATION_SECONDS - confirmation_duration
        if verbose or (int(confirmation_duration) % 30 == 0):  # Log every 30s
            print(f"  [Slot {slot}] Confirmation: {confirmation_duration:.0f}s / {STAGNANT_CONFIRMATION_SECONDS}s ({remaining:.0f}s until nudge)")
        return

    # Stagnant confirmed! Time to nudge
    total_idle = idle_duration
    print(f"\n[STAGNANT] Slot {slot} confirmed stagnant after {total_idle:.0f}s idle")

    # Process the stagnant slot (sends nudge or escalates)
    process_stagnant_slot(slot, ocr, capture, verbose)

    # Reset first_idle to start fresh countdown for next nudge
    state.slot_first_idle[slot] = now


def monitor_loop(ocr: OCREngine, capture: ScreenCapture, verbose: bool = False):
    """Main monitoring loop with round-robin scanning and stagnant detection."""
    print("Ready. Monitoring grid for connection errors...")
    print("  Also checking for permission dialogs ('Allow this bash command?')")
    print("  Also checking for stagnant cursors (nudge after 3.5 min idle)")
    print(f"  Checking every {MONITOR_INTERVAL} seconds")
    print("  Using round-robin slot scanning for fairness")
    print("  Only scanning slots with active Cursor windows")
    print()

    # How often to refresh the active window list (seconds)
    WINDOW_SCAN_INTERVAL = 10.0

    while state.running:
        try:
            # Periodically refresh which slots have active Cursor windows
            now = datetime.now()
            if (
                state.last_slot_scan is None
                or (now - state.last_slot_scan).total_seconds() >= WINDOW_SCAN_INTERVAL
            ):
                state.active_slots = get_active_cursor_slots(verbose)
                state.last_slot_scan = now
                if state.active_slots:
                    print(
                        f"[{now.strftime('%H:%M:%S')}] Active slots: {sorted(state.active_slots)}"
                    )
                else:
                    print(f"[{now.strftime('%H:%M:%S')}] No active Cursor windows detected")

            # Get slots in round-robin order (fair scanning)
            slots_to_check = get_round_robin_slots(state.active_slots, state.last_scanned_slot)

            for slot in slots_to_check:
                if not state.running:
                    break

                # Update last scanned slot for round-robin
                state.last_scanned_slot = slot

                # Check for permission dialogs (highest priority - blocks execution)
                if detect_permission_dialog_in_slot(ocr, capture, slot, verbose):
                    handle_permission_dialog(ocr, capture, slot, verbose)
                    # Permission granted = slot is working, clear stagnant state
                    if slot in state.slot_first_idle:
                        del state.slot_first_idle[slot]
                    clear_slot_stagnant_state(slot)
                    time.sleep(SLOT_CHECK_DELAY)
                    continue

                # Check for error dialogs
                if detect_error_in_slot(ocr, capture, slot, verbose):
                    handle_error(ocr, capture, slot, verbose)
                    # Error handled = give slot fresh start
                    if slot in state.slot_first_idle:
                        del state.slot_first_idle[slot]
                    time.sleep(SLOT_CHECK_DELAY)
                    continue

                # Check for approval dialogs
                if detect_approval_in_slot(ocr, capture, slot, verbose):
                    handle_approval(ocr, capture, slot, verbose)
                    # Approval granted = slot is working
                    if slot in state.slot_first_idle:
                        del state.slot_first_idle[slot]
                    clear_slot_stagnant_state(slot)
                    time.sleep(SLOT_CHECK_DELAY)
                    continue

                # Check stagnant status (WIP detection + idle countdown)
                check_stagnant_status(ocr, capture, slot, verbose)

                # Small delay between slots to avoid hammering CPU
                time.sleep(SLOT_CHECK_DELAY)

            # Wait before next full scan cycle
            time.sleep(MONITOR_INTERVAL)

        except KeyboardInterrupt:
            state.running = False
            break
        except Exception as e:
            print(f"[ERROR] Monitor loop error: {e}")
            time.sleep(MONITOR_INTERVAL)


def main():
    """Main entry point."""
    global MONITOR_INTERVAL

    parser = argparse.ArgumentParser(
        description="OCR-based connection error handler for Cursor grid windows"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--interval",
        "-i",
        type=float,
        default=MONITOR_INTERVAL,
        help=f"Monitor interval in seconds (default: {MONITOR_INTERVAL})",
    )
    args = parser.parse_args()

    MONITOR_INTERVAL = args.interval
    state.verbose = args.verbose

    print_banner()

    try:
        # Initialize components
        ocr = OCREngine(verbose=args.verbose)
        capture = ScreenCapture()

        # Pre-initialize OCR (loads model)
        ocr.initialize()

        print()
        print("[INFO] Status: MONITORING ACTIVE")
        print()

        # Start monitoring
        monitor_loop(ocr, capture, args.verbose)

    except KeyboardInterrupt:
        pass
    finally:
        print_summary()


if __name__ == "__main__":
    main()
