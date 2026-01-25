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


@dataclass
class SlotEvent:
    """Represents a single slot event."""

    slot: int
    event_type: str  # "connection_error", "resume_clicked", "retry_clicked"
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


class ConnectionErrorHandler:
    """OCR-based connection error handler for Cursor windows."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.reader = None
        self.sct = None

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

    def find_error_button(self, image, keywords: list[str]) -> Optional[tuple[int, int]]:
        """Find the center location of an error button matching keywords."""
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
                        return (x_center, y_center)
        except Exception as e:
            if self.verbose:
                print(f"  [ERROR] OCR failed: {e}")
        return None

    def click_at_slot_relative(self, slot: int, rel_x: int, rel_y: int) -> None:
        """Click at a position relative to the slot's top-left corner."""
        import pyautogui

        pos = GRID_POSITIONS[slot]
        abs_x = pos["x"] + rel_x
        abs_y = pos["y"] + rel_y

        if self.verbose:
            print(f"  [CLICK] Absolute position: ({abs_x}, {abs_y})")

        pyautogui.click(abs_x, abs_y)

    def handle_slot_error(self, slot: int, escalation_level: int = 0) -> bool:
        """
        Check and handle connection error for a specific slot.

        Args:
            slot: Slot number (1-9)
            escalation_level: Current escalation level

        Returns:
            True if error was found and handled
        """
        print(f"\n[CHECK] Slot {slot}")

        image = self.capture_slot(slot)
        button_loc = self.find_error_button(image, ERROR_BUTTON_KEYWORDS)

        if button_loc:
            print("  [FOUND] Connection error dialog detected")

            # Record the error event
            record_slot_event(
                slot=slot,
                event_type="connection_error",
                success=True,
                escalation_level=escalation_level,
                details={"button_position": button_loc},
            )

            # Click the button
            self.click_at_slot_relative(slot, button_loc[0], button_loc[1])
            time.sleep(0.5)

            # Record the click event
            record_slot_event(
                slot=slot,
                event_type="resume_clicked",
                success=True,
                escalation_level=escalation_level,
            )

            print("  [OK] Clicked recovery button")
            return True

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
