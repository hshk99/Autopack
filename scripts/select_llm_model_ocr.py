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

import sys
import time
import argparse
from typing import Optional, Tuple, List

try:
    import easyocr
    import numpy as np
    import mss
    import pyautogui
except ImportError as e:
    print(f"Missing required package: {e}")
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


class OCRModelSelector:
    """OCR-based model selector for Cursor chat."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.reader = None
        self.sct = mss.mss()

    def initialize_ocr(self):
        """Initialize EasyOCR reader."""
        if self.reader is None:
            if self.verbose:
                print("[INFO] Initializing EasyOCR...")
            self.reader = easyocr.Reader(["en"], gpu=True, verbose=False)
            if self.verbose:
                print("[OK] EasyOCR initialized")

    def capture_slot(self, slot: int) -> np.ndarray:
        """Capture screenshot of a specific grid slot."""
        pos = GRID_POSITIONS[slot]
        monitor = {"left": pos["x"], "top": pos["y"], "width": pos["width"], "height": pos["height"]}
        screenshot = self.sct.grab(monitor)
        img = np.array(screenshot)
        img = img[:, :, :3]  # Remove alpha
        img = img[:, :, ::-1]  # BGR to RGB
        return img

    def find_text_location(self, image: np.ndarray, keywords: List[str]) -> Optional[Tuple[int, int]]:
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

        pyautogui.click(abs_x, abs_y)

    def select_model(self, slot: int, target_model: str = "glm-4.7", max_attempts: int = 3) -> bool:
        """
        Select a model in the chat dropdown for the given slot.

        Strategy:
        1. Capture slot screenshot
        2. Find the model dropdown button (shows current model like "GPT-5.2")
        3. Click to open dropdown
        4. Find and click the target model (e.g., "GLM-4.7")

        Returns:
            True if model was selected successfully
        """
        print(f"\n[SELECT MODEL] Slot {slot} -> {target_model}")

        for attempt in range(1, max_attempts + 1):
            if self.verbose:
                print(f"\n  Attempt {attempt}/{max_attempts}")

            # Step 1: Capture current state
            image = self.capture_slot(slot)

            # Step 2: Check if target model is already selected (or visible)
            # First check if GLM is already there - might already be selected or dropdown is open
            target_keywords = GLM_KEYWORDS if "glm" in target_model.lower() else [target_model.lower()]
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
    args = parser.parse_args()

    if args.slot < 1 or args.slot > 9:
        print(f"[ERROR] Invalid slot number: {args.slot}. Must be 1-9.")
        sys.exit(1)

    selector = OCRModelSelector(verbose=args.verbose)
    success = selector.select_model(args.slot, args.model)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
