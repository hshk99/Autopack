#!/usr/bin/env python3
"""Test script to isolate OpenAI Auditor 400 error"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from autopack.openai_clients import OpenAIAuditorClient


def main():
    # Simple test patch
    patch_content = """diff --git a/test.py b/test.py
index 0000000..1111111 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,5 @@
+import sys
+
 def main():
     print("Hello, world!")
"""

    # Simple phase spec
    phase_spec = {
        "phase_id": "test-phase-1",
        "task_category": "feature_scaffolding",
        "complexity": "low",
        "description": "Add import statement to test.py",
    }

    # Create auditor
    print("[TEST] Creating OpenAI Auditor client...")
    auditor = OpenAIAuditorClient()

    # Call review_patch
    print("[TEST] Calling review_patch...")
    try:
        result = auditor.review_patch(
            patch_content=patch_content, phase_spec=phase_spec, model="gpt-4o"
        )
        print(f"[TEST] SUCCESS: approved={result.approved}")
        print(f"[TEST] Issues found: {len(result.issues_found)}")
        print(f"[TEST] Result: {result}")
    except Exception as e:
        print(f"[TEST] EXCEPTION: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    main()
