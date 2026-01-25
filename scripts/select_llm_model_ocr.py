#!/usr/bin/env python3
"""
OCR-based LLM Model Selector for Cursor Agent Chat

After opening Agent chat (Ctrl+L), the default model is GPT-5.2.
This script uses OCR to find and click "GLM-4.7" in the model dropdown.

Usage:
    python select_llm_model_ocr.py --slot 1 --model "glm-4.7"
    python select_llm_model_ocr.py --slot 5 --model "glm-4.7" --verbose

Requirements:
    pip install easyocr pillow pyautogui mss numpy
"""

import json
import sys
import time
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple, List

# OCR dependencies are optional - only required for OCRModelSelector class
# This allows telemetry functions to be imported without OCR packages
_OCR_AVAILABLE = False
try:
    import easyocr
    import numpy as np
    import mss
    import pyautogui

    _OCR_AVAILABLE = True
except ImportError:
    easyocr = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    mss = None  # type: ignore[assignment]
    pyautogui = None  # type: ignore[assignment]


def _check_ocr_dependencies() -> None:
    """Check if OCR dependencies are available, exit if not."""
    if not _OCR_AVAILABLE:
        print("Missing required OCR packages.")
        print("\nPlease install required packages:")
        print("  pip install easyocr pillow pyautogui mss numpy")
        sys.exit(1)


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

# Model dropdown button keywords (to click to open dropdown)
MODEL_DROPDOWN_KEYWORDS = [
    "gpt-5.2",
    "gpt5.2",
    "gpt 5.2",
    "glm-4.7",
    "glm4.7",
    "glm 4.7",
    "claude",
    "model",
]

# Target model keywords
GLM_KEYWORDS = [
    "glm-4.7",
    "glm4.7",
    "glm 4.7",
    "glm-4",
]

# Telemetry configuration
MODEL_SWITCH_LOG_FILE = "model_switch_log.json"


def record_model_switch(
    from_model: str,
    to_model: str,
    trigger_reason: str,
    phase_id: Optional[str] = None,
    log_dir: Optional[Path] = None,
) -> dict[str, Any]:
    """Record a model switch event to telemetry.

    Args:
        from_model: The model being switched from
        to_model: The model being switched to
        trigger_reason: Why the switch occurred (e.g., "token_limit", "user_request", "fallback")
        phase_id: Optional phase identifier if switch occurred during a specific phase
        log_dir: Directory to write telemetry to (defaults to current directory)

    Returns:
        The recorded event dictionary
    """
    log_path = (log_dir or Path.cwd()) / MODEL_SWITCH_LOG_FILE

    # Create event record
    event: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "from_model": from_model,
        "to_model": to_model,
        "trigger_reason": trigger_reason,
    }
    if phase_id is not None:
        event["phase_id"] = phase_id

    # Load existing events or initialize empty list
    events: list[dict[str, Any]] = []
    if log_path.exists():
        try:
            with open(log_path, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict) and "events" in data:
                    events = data.get("events", [])
                elif isinstance(data, list):
                    events = data
        except (json.JSONDecodeError, OSError):
            events = []

    # Append new event
    events.append(event)

    # Write back to file
    try:
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump({"events": events, "last_updated": datetime.now().isoformat()}, f, indent=2)
    except OSError as e:
        print(f"[WARN] Failed to write model switch telemetry: {e}")

    return event


class OCRModelSelector:
    """OCR-based model selector for Cursor chat."""

    def __init__(
        self,
        verbose: bool = False,
        telemetry_dir: Optional[Path] = None,
        enable_telemetry: bool = True,
    ):
        _check_ocr_dependencies()
        self.verbose = verbose
        self.reader = None
        self.sct = mss.mss()  # type: ignore[union-attr]
        self.telemetry_dir = telemetry_dir
        self.enable_telemetry = enable_telemetry
        self._current_model: Optional[str] = None

    def initialize_ocr(self):
        """Initialize EasyOCR reader."""
        if self.reader is None:
            if self.verbose:
                print("[INFO] Initializing EasyOCR...")
            self.reader = easyocr.Reader(["en"], gpu=True, verbose=False)  # type: ignore[union-attr]
            if self.verbose:
                print("[OK] EasyOCR initialized")

    def capture_slot(self, slot: int):  # type: ignore[return]
        """Capture screenshot of a specific grid slot."""
        pos = GRID_POSITIONS[slot]
        monitor = {
            "left": pos["x"],
            "top": pos["y"],
            "width": pos["width"],
            "height": pos["height"],
        }
        screenshot = self.sct.grab(monitor)
        img = np.array(screenshot)  # type: ignore[union-attr]
        img = img[:, :, :3]  # Remove alpha
        img = img[:, :, ::-1]  # BGR to RGB
        return img

    def find_text_location(self, image, keywords: List[str]) -> Optional[Tuple[int, int]]:
        """Find the center location of text matching keywords."""
        self.initialize_ocr()

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

    def click_at_slot_relative(self, slot: int, rel_x: int, rel_y: int):
        """Click at a position relative to the slot's top-left corner."""
        pos = GRID_POSITIONS[slot]
        abs_x = pos["x"] + rel_x
        abs_y = pos["y"] + rel_y

        if self.verbose:
            print(f"  [CLICK] Absolute position: ({abs_x}, {abs_y})")

        pyautogui.click(abs_x, abs_y)  # type: ignore[union-attr]

    def _record_switch(
        self,
        from_model: str,
        to_model: str,
        trigger_reason: str,
        phase_id: Optional[str] = None,
    ) -> None:
        """Record a model switch event to telemetry.

        Args:
            from_model: The model being switched from
            to_model: The model being switched to
            trigger_reason: Why the switch occurred
            phase_id: Optional phase identifier
        """
        self._current_model = to_model
        if not self.enable_telemetry:
            return

        event = record_model_switch(
            from_model=from_model,
            to_model=to_model,
            trigger_reason=trigger_reason,
            phase_id=phase_id,
            log_dir=self.telemetry_dir,
        )
        if self.verbose:
            print(f"  [TELEMETRY] Recorded switch: {from_model} -> {to_model} ({trigger_reason})")

    def select_model(
        self,
        slot: int,
        target_model: str = "glm-4.7",
        max_attempts: int = 3,
        trigger_reason: str = "user_request",
        phase_id: Optional[str] = None,
    ) -> bool:
        """
        Select a model in the chat dropdown for the given slot.

        Strategy:
        1. Capture slot screenshot
        2. Find the model dropdown button (shows current model like "GPT-5.2")
        3. Click to open dropdown
        4. Find and click the target model (e.g., "GLM-4.7")

        Args:
            slot: Grid slot number (1-9)
            target_model: Target model to select (e.g., "glm-4.7")
            max_attempts: Maximum number of attempts
            trigger_reason: Why the switch is occurring (for telemetry)
            phase_id: Optional phase identifier (for telemetry)

        Returns:
            True if model was selected successfully
        """
        print(f"\n[SELECT MODEL] Slot {slot} -> {target_model}")
        previous_model = self._current_model or "unknown"

        for attempt in range(1, max_attempts + 1):
            if self.verbose:
                print(f"\n  Attempt {attempt}/{max_attempts}")

            # Step 1: Capture current state
            image = self.capture_slot(slot)

            # Step 2: Check if target model is already selected (or visible)
            # First check if GLM is already there - might already be selected or dropdown is open
            target_keywords = (
                GLM_KEYWORDS if "glm" in target_model.lower() else [target_model.lower()]
            )
            target_loc = self.find_text_location(image, target_keywords)

            if target_loc:
                # Target model found - click it (might be in dropdown or already selected)
                print(f"  [FOUND] Target model '{target_model}' visible")
                self.click_at_slot_relative(slot, target_loc[0], target_loc[1])
                time.sleep(0.5)

                # Verify selection
                time.sleep(0.3)
                verify_image = self.capture_slot(slot)
                if self.find_text_location(verify_image, target_keywords):
                    print(f"  [OK] Model '{target_model}' selected")
                    self._record_switch(previous_model, target_model, trigger_reason, phase_id)
                    return True

            # Step 3: Find and click dropdown button to open it
            dropdown_loc = self.find_text_location(image, MODEL_DROPDOWN_KEYWORDS)

            if dropdown_loc:
                print("  [ACTION] Clicking model dropdown...")
                self.click_at_slot_relative(slot, dropdown_loc[0], dropdown_loc[1])
                time.sleep(0.8)  # Wait for dropdown to open

                # Step 4: Capture again and find target model in dropdown
                image = self.capture_slot(slot)
                target_loc = self.find_text_location(image, target_keywords)

                if target_loc:
                    print(f"  [ACTION] Clicking target model '{target_model}'...")
                    self.click_at_slot_relative(slot, target_loc[0], target_loc[1])
                    time.sleep(0.5)
                    print(f"  [OK] Model '{target_model}' selected")
                    self._record_switch(previous_model, target_model, trigger_reason, phase_id)
                    return True
                else:
                    print("  [WARN] Target model not found in dropdown")
            else:
                print("  [WARN] Could not find model dropdown button")

            # Wait before retry
            if attempt < max_attempts:
                time.sleep(0.5)

        print(f"  [FAIL] Could not select model after {max_attempts} attempts")
        return False


def main():
    parser = argparse.ArgumentParser(description="OCR-based LLM model selector for Cursor")
    parser.add_argument("--slot", "-s", type=int, required=True, help="Grid slot number (1-9)")
    parser.add_argument("--model", "-m", type=str, default="glm-4.7", help="Target model to select")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument(
        "--telemetry-dir", type=Path, default=None, help="Directory to write telemetry logs"
    )
    parser.add_argument("--no-telemetry", action="store_true", help="Disable telemetry recording")
    parser.add_argument(
        "--trigger-reason",
        type=str,
        default="user_request",
        help="Reason for model switch (for telemetry)",
    )
    parser.add_argument("--phase-id", type=str, default=None, help="Phase ID (for telemetry)")
    args = parser.parse_args()

    if args.slot < 1 or args.slot > 9:
        print(f"[ERROR] Invalid slot number: {args.slot}. Must be 1-9.")
        sys.exit(1)

    selector = OCRModelSelector(
        verbose=args.verbose,
        telemetry_dir=args.telemetry_dir,
        enable_telemetry=not args.no_telemetry,
    )
    success = selector.select_model(
        args.slot,
        args.model,
        trigger_reason=args.trigger_reason,
        phase_id=args.phase_id,
    )

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
