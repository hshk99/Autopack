#!/usr/bin/env python3
"""
OCR-based Connection Error Handler for Cursor Agent Windows

Detects and handles connection error dialogs using OCR.
Maintains slot history with automatic consolidation to preserve pattern data.

Usage:
    python handle_connection_errors_ocr.py --monitor
    python handle_connection_errors_ocr.py --slot 1 --verbose
    python handle_connection_errors_ocr.py --show-history --slot 1

Requirements:
    pip install easyocr pillow pyautogui mss numpy
"""

import argparse
import json
import logging
import sys
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Import learning memory manager for nudge tracking
try:
    import sys

    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))
    from autopack.learning_memory_manager import LearningMemoryManager

    LEARNING_MEMORY_AVAILABLE = True
except ImportError:
    LEARNING_MEMORY_AVAILABLE = False

logger = logging.getLogger(__name__)

# Constants
SLOT_HISTORY_FILE = Path("slot_history.json")
SLOT_HISTORY_ARCHIVE_FILE = Path("slot_history_archive.json")
MAX_HISTORY_ENTRIES = 100
CONSOLIDATION_THRESHOLD = 100
ENTRIES_TO_KEEP = 50

# Grid configuration for 5120x1440 monitor with 3x3 grid
GRID_POSITIONS = {
    1: {"x": 2560, "y": 0, "width": 853, "height": 463},
    2: {"x": 3413, "y": 0, "width": 853, "height": 463},
    3: {"x": 4266, "y": 0, "width": 854, "height": 463},
    4: {"x": 2560, "y": 463, "width": 853, "height": 463},
    5: {"x": 3413, "y": 463, "width": 853, "height": 463},
    6: {"x": 4266, "y": 463, "width": 854, "height": 463},
    7: {"x": 2560, "y": 926, "width": 853, "height": 464},
    8: {"x": 3413, "y": 926, "width": 853, "height": 464},
    9: {"x": 4266, "y": 926, "width": 854, "height": 464},
}

# Connection error button keywords
ERROR_BUTTON_KEYWORDS = ["resume", "try again", "retry", "reconnect"]

# Permission dialog button keywords
PERMISSION_BUTTON_KEYWORDS = ["allow", "accept", "grant", "permit", "ok", "yes", "continue"]

# Retry-specific keywords (subset of error keywords that indicate retry action)
RETRY_BUTTON_KEYWORDS = ["try again", "retry"]

# Stagnation detection parameters
STAGNATION_CHECK_INTERVAL_SECONDS = 60
STAGNATION_EVENT_THRESHOLD = 3  # Min events in window to detect pattern


@dataclass
class SlotEvent:
    """Represents a single slot event.

    Event types recorded:
    - connection_error: Legacy event for connection error detection
    - connection_error_detected: Connection error dialog found via OCR
    - resume_clicked: Resume button clicked (non-retry keywords)
    - retry_button_click: Retry/try again button clicked
    - permission_button_click: Permission dialog button clicked
    - error_recovery_success: Recovery verified successful after button click
    - stagnation_detected: Slot showing repeated errors without recovery
    - escalation_level_change: Escalation level changed for the slot
    """

    slot: int
    event_type: str
    timestamp: str
    success: bool
    escalation_level: int = 0  # 0=first attempt, 1=retry, 2+=escalated
    details: Optional[dict] = None


@dataclass
class ConsolidatedStats:
    """Summary statistics for archived events."""

    slot: int
    period_start: str
    period_end: str
    total_events: int
    event_type_counts: dict  # {event_type: count}
    success_count: int
    failure_count: int
    avg_escalation_level: float
    max_escalation_level: int


def load_slot_history() -> dict:
    """Load slot history from JSON file."""
    if not SLOT_HISTORY_FILE.exists():
        return {}
    try:
        with open(SLOT_HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load slot history: {e}")
        return {}


def save_slot_history(history: dict) -> None:
    """Save slot history to JSON file."""
    try:
        with open(SLOT_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to save slot history: {e}")


def load_archive() -> dict:
    """Load archive from JSON file."""
    if not SLOT_HISTORY_ARCHIVE_FILE.exists():
        return {"consolidated_summaries": [], "metadata": {"version": 1}}
    try:
        with open(SLOT_HISTORY_ARCHIVE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load archive: {e}")
        return {"consolidated_summaries": [], "metadata": {"version": 1}}


def save_archive(archive: dict) -> None:
    """Save archive to JSON file."""
    archive["metadata"]["last_updated"] = datetime.now(timezone.utc).isoformat()
    try:
        with open(SLOT_HISTORY_ARCHIVE_FILE, "w", encoding="utf-8") as f:
            json.dump(archive, f, indent=2)
    except OSError as e:
        logger.error(f"Failed to save archive: {e}")


def consolidate_events(events: list[dict]) -> ConsolidatedStats:
    """
    Consolidate a list of events into summary statistics.

    Args:
        events: List of event dictionaries to consolidate

    Returns:
        ConsolidatedStats with aggregated metrics
    """
    if not events:
        raise ValueError("Cannot consolidate empty event list")

    slot = events[0].get("slot", 0)
    timestamps = [e.get("timestamp", "") for e in events]
    period_start = min(timestamps) if timestamps else ""
    period_end = max(timestamps) if timestamps else ""

    event_type_counts: dict[str, int] = {}
    success_count = 0
    failure_count = 0
    escalation_levels = []

    for event in events:
        event_type = event.get("event_type", "unknown")
        event_type_counts[event_type] = event_type_counts.get(event_type, 0) + 1

        if event.get("success", False):
            success_count += 1
        else:
            failure_count += 1

        escalation_levels.append(event.get("escalation_level", 0))

    avg_escalation = sum(escalation_levels) / len(escalation_levels) if escalation_levels else 0.0
    max_escalation = max(escalation_levels) if escalation_levels else 0

    return ConsolidatedStats(
        slot=slot,
        period_start=period_start,
        period_end=period_end,
        total_events=len(events),
        event_type_counts=event_type_counts,
        success_count=success_count,
        failure_count=failure_count,
        avg_escalation_level=round(avg_escalation, 2),
        max_escalation_level=max_escalation,
    )


def record_slot_event(
    slot: int,
    event_type: str,
    success: bool,
    escalation_level: int = 0,
    details: Optional[dict] = None,
) -> None:
    """
    Record a slot event to history with automatic consolidation.

    When history exceeds 100 entries per slot:
    - Consolidates oldest 50 into summary stats
    - Archives to slot_history_archive.json
    - Keeps last 50 raw entries for recent pattern detection

    Args:
        slot: Slot number (1-9)
        event_type: Type of event (e.g., "connection_error", "resume_clicked")
        success: Whether the action was successful
        escalation_level: 0=first attempt, higher=more escalated
        details: Optional additional details
    """
    history = load_slot_history()

    slot_key = str(slot)
    if slot_key not in history:
        history[slot_key] = []

    # Create new event
    event = SlotEvent(
        slot=slot,
        event_type=event_type,
        timestamp=datetime.now(timezone.utc).isoformat(),
        success=success,
        escalation_level=escalation_level,
        details=details,
    )

    # Check if consolidation is needed BEFORE adding new entry
    slot_history = history[slot_key]
    if len(slot_history) >= CONSOLIDATION_THRESHOLD:
        # Consolidate oldest entries
        entries_to_consolidate = slot_history[:ENTRIES_TO_KEEP]
        entries_to_keep = slot_history[ENTRIES_TO_KEEP:]

        # Create summary stats
        stats = consolidate_events(entries_to_consolidate)

        # Archive the consolidated stats
        archive = load_archive()
        archive["consolidated_summaries"].append(asdict(stats))
        save_archive(archive)

        # Update history with only recent entries
        history[slot_key] = entries_to_keep

        logger.info(
            f"Consolidated {len(entries_to_consolidate)} entries for slot {slot}, "
            f"kept {len(entries_to_keep)} recent entries"
        )

    # Add new event
    history[slot_key].append(asdict(event))
    save_slot_history(history)


def get_slot_stats(slot: int) -> dict[str, Any]:
    """
    Get combined statistics for a slot from both history and archive.

    Args:
        slot: Slot number (1-9)

    Returns:
        Dictionary with combined stats
    """
    history = load_slot_history()
    archive = load_archive()

    slot_key = str(slot)
    recent_events = history.get(slot_key, [])

    # Get archived summaries for this slot
    archived_summaries = [
        s for s in archive.get("consolidated_summaries", []) if s.get("slot") == slot
    ]

    # Calculate totals
    total_archived_events = sum(s.get("total_events", 0) for s in archived_summaries)
    total_events = len(recent_events) + total_archived_events

    # Aggregate event type counts from archives
    archived_type_counts: dict[str, int] = {}
    for summary in archived_summaries:
        for event_type, count in summary.get("event_type_counts", {}).items():
            archived_type_counts[event_type] = archived_type_counts.get(event_type, 0) + count

    # Add recent event type counts
    recent_type_counts: dict[str, int] = {}
    for event in recent_events:
        event_type = event.get("event_type", "unknown")
        recent_type_counts[event_type] = recent_type_counts.get(event_type, 0) + 1

    # Combine counts
    combined_type_counts = archived_type_counts.copy()
    for event_type, count in recent_type_counts.items():
        combined_type_counts[event_type] = combined_type_counts.get(event_type, 0) + count

    return {
        "slot": slot,
        "total_events": total_events,
        "recent_events_count": len(recent_events),
        "archived_summaries_count": len(archived_summaries),
        "event_type_counts": combined_type_counts,
        "recent_events": recent_events[-10:] if recent_events else [],  # Last 10 for display
    }


# Default nudge templates for different recovery scenarios
NUDGE_TEMPLATES = {
    "template_continue_task": "Please continue with the current task.",
    "template_resume_work": "Resume work on the pending task.",
    "template_retry_action": "Please retry the previous action.",
    "template_connection_recovery": "Connection restored. Please continue.",
}

# Learning memory path for nudge effectiveness tracking
LEARNING_MEMORY_PATH = Path("LEARNING_MEMORY.json")


def send_nudge(
    slot_id: int,
    message: str,
    template_id: str = "template_continue_task",
    phase_id: str | None = None,
) -> None:
    """Send a nudge message and track for effectiveness learning.

    Records the nudge template with context to the learning memory for later
    effectiveness analysis. When the slot recovers, call record_nudge_recovery
    to complete the effectiveness tracking.

    Args:
        slot_id: The slot number receiving the nudge.
        message: The nudge message text.
        template_id: The template identifier for tracking.
        phase_id: Optional phase ID for context.
    """
    if LEARNING_MEMORY_AVAILABLE:
        try:
            memory = LearningMemoryManager(LEARNING_MEMORY_PATH)
            context = {
                "message": message,
                "phase_id": phase_id,
            }
            memory.record_nudge_sent(
                template_id=template_id,
                slot_id=slot_id,
                context=context,
            )
            memory.save()
            logger.info(f"Recorded nudge sent: {template_id} for slot {slot_id}")
        except Exception as e:
            logger.warning(f"Failed to record nudge to learning memory: {e}")
    else:
        logger.debug("Learning memory not available, skipping nudge tracking")

    # Log the nudge action (actual nudge implementation would go here)
    logger.info(f"[NUDGE] Slot {slot_id}: {message}")


def record_nudge_recovery(
    slot_id: int,
    effective: bool,
    recovery_time_seconds: int | None = None,
) -> str | None:
    """Record nudge effectiveness when a slot recovers or times out.

    Should be called when a slot that received a nudge either recovers
    or times out. This completes the nudge tracking cycle.

    Args:
        slot_id: The slot that recovered or timed out.
        effective: True if recovery occurred, False if timeout.
        recovery_time_seconds: Time from nudge to recovery (if effective).

    Returns:
        The template_id that was resolved, or None if no pending nudge.
    """
    if not LEARNING_MEMORY_AVAILABLE:
        logger.debug("Learning memory not available, skipping recovery tracking")
        return None

    try:
        memory = LearningMemoryManager(LEARNING_MEMORY_PATH)
        template_id = memory.resolve_pending_nudge(
            slot_id=slot_id,
            effective=effective,
            recovery_time_seconds=recovery_time_seconds,
        )
        memory.save()
        if template_id:
            logger.info(
                f"Resolved nudge effectiveness: {template_id} "
                f"effective={effective}, recovery_time={recovery_time_seconds}s"
            )
        return template_id
    except Exception as e:
        logger.warning(f"Failed to record nudge recovery: {e}")
        return None


def get_best_nudge_template() -> tuple[str, str]:
    """Get the most effective nudge template based on historical data.

    Returns:
        Tuple of (template_id, message) for the most effective template,
        or the default template if no history is available.
    """
    if not LEARNING_MEMORY_AVAILABLE:
        default_id = "template_continue_task"
        return default_id, NUDGE_TEMPLATES[default_id]

    try:
        memory = LearningMemoryManager(LEARNING_MEMORY_PATH)
        effective_templates = memory.get_effective_templates()

        if effective_templates:
            best = effective_templates[0]
            template_id = best["template_id"]
            # Use known message or fall back to template_id
            message = NUDGE_TEMPLATES.get(template_id, f"[{template_id}] Please continue.")
            return template_id, message

    except Exception as e:
        logger.warning(f"Failed to get effective templates: {e}")

    # Default fallback
    default_id = "template_continue_task"
    return default_id, NUDGE_TEMPLATES[default_id]


def detect_stagnation(slot: int, window_minutes: int = 5) -> bool:
    """
    Detect if a slot is stagnating based on recent event patterns.

    A slot is considered stagnating if it has multiple connection errors
    within the time window without successful recovery.

    Args:
        slot: Slot number (1-9)
        window_minutes: Time window to check for stagnation pattern

    Returns:
        True if stagnation pattern is detected
    """
    from datetime import timedelta

    history = load_slot_history()
    slot_key = str(slot)
    events = history.get(slot_key, [])

    if len(events) < STAGNATION_EVENT_THRESHOLD:
        return False

    # Get events within window
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(minutes=window_minutes)

    recent_events = []
    for event in events[-20:]:  # Check last 20 events max
        try:
            event_time = datetime.fromisoformat(event.get("timestamp", "").replace("Z", "+00:00"))
            if event_time >= window_start:
                recent_events.append(event)
        except (ValueError, TypeError):
            continue

    if len(recent_events) < STAGNATION_EVENT_THRESHOLD:
        return False

    # Check for stagnation pattern: multiple errors without successful recovery
    error_count = sum(
        1
        for e in recent_events
        if e.get("event_type") in ("connection_error", "connection_error_detected")
        and not e.get("success", True)
    )

    recovery_count = sum(
        1 for e in recent_events if e.get("event_type") == "error_recovery_success"
    )

    # Stagnating if errors outnumber recoveries significantly
    return error_count >= STAGNATION_EVENT_THRESHOLD and error_count > recovery_count * 2


class ConnectionErrorHandler:
    """OCR-based connection error handler for Cursor windows."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.reader = None
        self.sct = None
        self._last_escalation_levels: dict[int, int] = {}  # Track escalation per slot

    def initialize_ocr(self) -> bool:
        """Initialize OCR components."""
        try:
            import easyocr
            import mss

            if self.reader is None:
                if self.verbose:
                    print("[INFO] Initializing EasyOCR...")
                self.reader = easyocr.Reader(["en"], gpu=True, verbose=False)
                self.sct = mss.mss()
                if self.verbose:
                    print("[OK] EasyOCR initialized")
            return True
        except ImportError as e:
            print(f"[ERROR] Missing required package: {e}")
            print("\nPlease install required packages:")
            print("  pip install easyocr pillow pyautogui mss numpy")
            return False

    def capture_slot(self, slot: int):
        """Capture screenshot of a specific grid slot."""
        import numpy as np

        pos = GRID_POSITIONS[slot]
        monitor = {
            "left": pos["x"],
            "top": pos["y"],
            "width": pos["width"],
            "height": pos["height"],
        }
        screenshot = self.sct.grab(monitor)
        img = np.array(screenshot)
        img = img[:, :, :3]  # Remove alpha
        img = img[:, :, ::-1]  # BGR to RGB
        return img

    def find_error_button(
        self, image, keywords: list[str]
    ) -> Optional[tuple[tuple[int, int], str]]:
        """Find the center location of an error button matching keywords.

        Returns:
            Tuple of ((x_center, y_center), matched_keyword) or None
        """
        try:
            results = self.reader.readtext(image)

            if self.verbose:
                texts = [text.lower() for (_, text, _) in results]
                print(f"  [OCR] Detected text: {texts[:10]}")

            for bbox, text, confidence in results:
                if confidence < 0.3:
                    continue
                text_lower = text.lower()
                for keyword in keywords:
                    if keyword.lower() in text_lower:
                        x_center = int((bbox[0][0] + bbox[2][0]) / 2)
                        y_center = int((bbox[0][1] + bbox[2][1]) / 2)
                        if self.verbose:
                            print(f"  [FOUND] '{text}' at relative ({x_center}, {y_center})")
                        return ((x_center, y_center), keyword)
        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] OCR failed: {e}")
        return None

    def find_permission_button(self, image) -> Optional[tuple[tuple[int, int], str]]:
        """Find permission dialog buttons in the image.

        Returns:
            Tuple of ((x_center, y_center), matched_keyword) or None
        """
        return self.find_error_button(image, PERMISSION_BUTTON_KEYWORDS)

    def click_at_slot_relative(self, slot: int, rel_x: int, rel_y: int) -> None:
        """Click at a position relative to the slot's top-left corner."""
        import pyautogui

        pos = GRID_POSITIONS[slot]
        abs_x = pos["x"] + rel_x
        abs_y = pos["y"] + rel_y

        if self.verbose:
            print(f"  [CLICK] Absolute position: ({abs_x}, {abs_y})")

        pyautogui.click(abs_x, abs_y)

    def _track_escalation_change(self, slot: int, new_level: int) -> None:
        """Track escalation level changes and record events."""
        old_level = self._last_escalation_levels.get(slot, 0)
        if new_level != old_level:
            record_slot_event(
                slot=slot,
                event_type="escalation_level_change",
                success=True,
                escalation_level=new_level,
                details={
                    "previous_level": old_level,
                    "new_level": new_level,
                    "direction": "up" if new_level > old_level else "down",
                },
            )
            self._last_escalation_levels[slot] = new_level

    def handle_slot_error(
        self, slot: int, escalation_level: int = 0, template_id: str | None = None
    ) -> bool:
        """
        Check and handle connection error for a specific slot.

        Records expanded event types for better pattern analysis:
        - connection_error_detected: When error dialog is found via OCR
        - retry_button_click: When retry/try again button is clicked
        - permission_button_click: When permission dialog button is clicked
        - error_recovery_success: When recovery is verified successful
        - stagnation_detected: When slot shows stagnation pattern
        - escalation_level_change: When escalation level changes

        Args:
            slot: Slot number (1-9)
            escalation_level: Current escalation level
            template_id: Optional nudge template ID for tracking effectiveness

        Returns:
            True if error was found and handled
        """
        print(f"\n[CHECK] Slot {slot}")

        # Track escalation level changes
        self._track_escalation_change(slot, escalation_level)

        # Check for stagnation pattern
        if detect_stagnation(slot):
            record_slot_event(
                slot=slot,
                event_type="stagnation_detected",
                success=False,
                escalation_level=escalation_level,
                details={"detection_method": "event_pattern_analysis"},
            )
            print(f"  [WARN] Stagnation detected for slot {slot}")

        image = self.capture_slot(slot)

        # First check for permission dialogs
        permission_result = self.find_permission_button(image)
        if permission_result:
            button_loc, matched_keyword = permission_result
            print(f"  [FOUND] Permission dialog detected (keyword: {matched_keyword})")

            # Record permission dialog detection
            record_slot_event(
                slot=slot,
                event_type="connection_error_detected",
                success=True,
                escalation_level=escalation_level,
                details={
                    "button_position": button_loc,
                    "matched_keyword": matched_keyword,
                    "dialog_type": "permission",
                },
            )

            # Click the permission button
            self.click_at_slot_relative(slot, button_loc[0], button_loc[1])
            time.sleep(0.5)

            # Record permission button click
            record_slot_event(
                slot=slot,
                event_type="permission_button_click",
                success=True,
                escalation_level=escalation_level,
                details={"matched_keyword": matched_keyword},
            )

            # Record recovery success
            record_slot_event(
                slot=slot,
                event_type="error_recovery_success",
                success=True,
                escalation_level=escalation_level,
                details={"recovery_type": "permission_granted"},
            )

            print("  [OK] Clicked permission button")
            return True

        # Check for error/retry dialogs
        error_result = self.find_error_button(image, ERROR_BUTTON_KEYWORDS)

        if error_result:
            button_loc, matched_keyword = error_result
            print(f"  [FOUND] Connection error dialog detected (keyword: {matched_keyword})")

            # Record connection error detection with more detail
            record_slot_event(
                slot=slot,
                event_type="connection_error_detected",
                success=True,
                escalation_level=escalation_level,
                details={
                    "button_position": button_loc,
                    "matched_keyword": matched_keyword,
                    "dialog_type": "connection_error",
                },
            )

            # Also record legacy event for backwards compatibility
            record_slot_event(
                slot=slot,
                event_type="connection_error",
                success=True,
                escalation_level=escalation_level,
                details={"button_position": button_loc},
            )

            # Select nudge template for tracking (use best if not specified)
            if template_id is None:
                template_id, nudge_message = get_best_nudge_template()
            else:
                nudge_message = NUDGE_TEMPLATES.get(template_id, "Please continue with the task.")

            # Record nudge sent for effectiveness tracking
            send_nudge(
                slot_id=slot,
                message=nudge_message,
                template_id=template_id,
                phase_id=f"slot_{slot}_recovery",
            )

            # Click the button
            self.click_at_slot_relative(slot, button_loc[0], button_loc[1])
            time.sleep(0.5)

            # Determine specific click event type based on matched keyword
            is_retry = matched_keyword.lower() in [k.lower() for k in RETRY_BUTTON_KEYWORDS]
            click_event_type = "retry_button_click" if is_retry else "resume_clicked"

            # Record the specific click event
            record_slot_event(
                slot=slot,
                event_type=click_event_type,
                success=True,
                escalation_level=escalation_level,
                details={
                    "template_id": template_id,
                    "matched_keyword": matched_keyword,
                },
            )

            # Record recovery success
            record_slot_event(
                slot=slot,
                event_type="error_recovery_success",
                success=True,
                escalation_level=escalation_level,
                details={
                    "recovery_type": "button_click",
                    "button_type": click_event_type,
                },
            )

            print("  [OK] Clicked recovery button")
            return True

        # If no error found and there was a pending nudge, mark it as effective
        # (slot recovered without needing manual intervention)
        if LEARNING_MEMORY_AVAILABLE:
            try:
                memory = LearningMemoryManager(LEARNING_MEMORY_PATH)
                pending = memory.get_pending_nudges(slot_id=slot)
                if pending:
                    # Calculate approximate recovery time based on last nudge
                    for nudge in pending:
                        sent_at = nudge.get("sent_at", "")
                        if sent_at:
                            from datetime import datetime

                            sent_time = datetime.fromisoformat(sent_at.replace("Z", "+00:00"))
                            now = datetime.now(timezone.utc)
                            recovery_seconds = int((now - sent_time).total_seconds())
                            record_nudge_recovery(
                                slot, effective=True, recovery_time_seconds=recovery_seconds
                            )
            except Exception as e:
                logger.debug(f"Failed to check pending nudges: {e}")

        if self.verbose:
            print("  [OK] No error dialog detected")
        return False

    def monitor_all_slots(self, duration_seconds: int = 300, check_interval: float = 2.0) -> dict:
        """
        Monitor all slots for connection errors.

        Args:
            duration_seconds: How long to monitor (default 5 minutes)
            check_interval: Seconds between checks

        Returns:
            Summary statistics
        """
        if not self.initialize_ocr():
            return {"error": "Failed to initialize OCR"}

        start_time = time.time()
        errors_handled = {slot: 0 for slot in range(1, 10)}
        total_checks = 0

        print("\n[MONITOR] Starting connection error monitoring")
        print(f"  Duration: {duration_seconds}s | Interval: {check_interval}s")
        print("  Press Ctrl+C to stop\n")

        try:
            while time.time() - start_time < duration_seconds:
                for slot in range(1, 10):
                    if self.handle_slot_error(slot):
                        errors_handled[slot] += 1
                total_checks += 1
                time.sleep(check_interval)
        except KeyboardInterrupt:
            print("\n[STOP] Monitoring stopped by user")

        elapsed = time.time() - start_time
        total_errors = sum(errors_handled.values())

        print("\n========== SUMMARY ==========")
        print(f"Duration: {elapsed:.1f}s | Checks: {total_checks}")
        print(f"Total errors handled: {total_errors}")
        for slot, count in errors_handled.items():
            if count > 0:
                print(f"  Slot {slot}: {count} errors")

        return {
            "duration_seconds": elapsed,
            "total_checks": total_checks,
            "errors_handled": errors_handled,
            "total_errors": total_errors,
        }


def main():
    parser = argparse.ArgumentParser(description="OCR-based connection error handler for Cursor")
    parser.add_argument("--monitor", "-m", action="store_true", help="Monitor all slots for errors")
    parser.add_argument("--slot", "-s", type=int, help="Check specific slot (1-9)")
    parser.add_argument(
        "--duration", "-d", type=int, default=300, help="Monitor duration in seconds"
    )
    parser.add_argument(
        "--interval", "-i", type=float, default=2.0, help="Check interval in seconds"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--show-history", action="store_true", help="Show slot history stats")
    args = parser.parse_args()

    if args.show_history:
        if args.slot:
            stats = get_slot_stats(args.slot)
            print(f"\n=== Slot {args.slot} Statistics ===")
            print(json.dumps(stats, indent=2))
        else:
            print("\n=== All Slot Statistics ===")
            for slot in range(1, 10):
                stats = get_slot_stats(slot)
                if stats["total_events"] > 0:
                    print(f"\nSlot {slot}: {stats['total_events']} total events")
                    print(f"  Recent: {stats['recent_events_count']}")
                    print(f"  Archived summaries: {stats['archived_summaries_count']}")
                    print(f"  Event types: {stats['event_type_counts']}")
        return

    handler = ConnectionErrorHandler(verbose=args.verbose)

    if args.monitor:
        handler.monitor_all_slots(duration_seconds=args.duration, check_interval=args.interval)
    elif args.slot:
        if args.slot < 1 or args.slot > 9:
            print(f"[ERROR] Invalid slot number: {args.slot}. Must be 1-9.")
            sys.exit(1)
        if not handler.initialize_ocr():
            sys.exit(1)
        handler.handle_slot_error(args.slot)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
