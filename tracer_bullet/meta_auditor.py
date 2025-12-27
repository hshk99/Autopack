from __future__ import annotations

import re


def detect_prompt_injection(prompt: str) -> bool:
    """Very small heuristic used by tests."""
    injection_patterns = [
        r"(?i)delete\s+from",
        r"(?i)drop\s+table",
        r"(?i)shutdown",
        r"(?i)exec\s+",
    ]
    return any(re.search(p, prompt or "") for p in injection_patterns)


