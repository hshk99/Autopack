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

# Monitor interval in seconds
MONITOR_INTERVAL = 2.0

# Grid configuration for 5120x1440 monitor with 3x3 grid
GRID_POSITIONS = {
    1: {"x": 0, "y": 0, "width": 1707, "height": 480},
    2: {"x": 1707, "y": 0, "width": 1707, "height": 480},
    3: {"x": 3414, "y": 0, "width": 1707, "height": 480},
    4: {"x": 0, "y": 480, "width": 1707, "height": 480},
    5: {"x": 1707, "y": 480, "width": 1707, "height": 480},
    6: {"x": 3414, "y": 480, "width": 1707, "height": 480},
    7: {"x": 0, "y": 960, "width": 1707, "height": 480},
    8: {"x": 1707, "y": 960, "width": 1707, "height": 480},
    9: {"x": 3414, "y": 960, "width": 1707, "height": 480},
}

# Resume button coordinates (absolute screen positions) - provided by user
RESUME_BUTTON_COORDS = {
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


state = MonitorState()


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
    ocr: OCREngine, capture: ScreenCapture, slot: int, keywords: List[str], verbose: bool = False
) -> bool:
    """
    Find and click a button with text matching keywords in the given slot.

    This is an alternative to using pre-mapped coordinates - it dynamically
    finds the button location using OCR.

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
        abs_y = pos["y"] + location[1]

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
    print("  [+] Takes screenshots of 9 grid windows")
    print("  [+] Uses OCR to detect error/approval text")
    print("  [+] Clicks Resume/Approve buttons automatically")
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
    print(f"  Session Duration: {hours}h {minutes}m {seconds}s")
    print(f"  Errors Detected:  {state.error_count}")
    print(f"  Errors Handled:   {state.handled_count}")
    print()
    print("Monitor stopped.")
    print()


def monitor_loop(ocr: OCREngine, capture: ScreenCapture, verbose: bool = False):
    """Main monitoring loop."""
    print("Ready. Monitoring grid for connection errors...")
    print(f"  Checking every {MONITOR_INTERVAL} seconds")
    print()

    while state.running:
        try:
            # Check each grid slot
            for slot in range(1, 10):
                if not state.running:
                    break

                # Check for error dialogs
                if detect_error_in_slot(ocr, capture, slot, verbose):
                    handle_error(ocr, capture, slot, verbose)
                    continue

                # Check for approval dialogs
                if detect_approval_in_slot(ocr, capture, slot, verbose):
                    handle_approval(ocr, capture, slot, verbose)

            # Wait before next scan
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
