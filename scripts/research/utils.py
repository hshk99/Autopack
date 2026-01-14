"""
Utility functions for research analysis
"""

import json
import re


def extract_json_from_response(text: str) -> dict:
    """
    Extract JSON from LLM response that may have extra text.

    Tries multiple strategies:
    1. Direct JSON parse
    2. Extract JSON object {...}
    3. Extract JSON array [...]
    """
    # Try direct JSON parse first
    try:
        return json.loads(text)
    except:
        pass

    # Look for JSON object in the text
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except:
            pass

    # Look for JSON array in the text
    array_match = re.search(r"\[.*\]", text, re.DOTALL)
    if array_match:
        try:
            return json.loads(array_match.group())
        except:
            pass

    raise ValueError(f"Could not extract JSON from response: {text[:200]}...")
