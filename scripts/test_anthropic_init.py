
import os
try:
    from anthropic import Anthropic
    print("Anthropic imported")
    try:
        client = Anthropic(api_key=None)
        print("Anthropic init SUCCESS (unexpected)")
    except Exception as e:
        print(f"Anthropic init FAILED: {e}")
except ImportError:
    print("Anthropic not installed")

