import sys
import requests
import json
import time

API_URL = "http://localhost:8000"
RUN_ID = "fileorg-test-verification-2025-11-29"


def check_status():
    try:
        response = requests.get(f"{API_URL}/runs/{RUN_ID}")
        if response.status_code == 200:
            data = response.json()
            print(f"Run: {data['id']}")
            print(f"State: {data['state']}")
            print(f"Tokens Used: {data.get('tokens_used', 0)}")
            print("-" * 40)
            for tier in data.get("tiers", []):
                print(f"Tier {tier['tier_index']}: {tier['name']} [{tier['state']}]")
                for phase in tier.get("phases", []):
                    icon = {
                        "QUEUED": "[WAIT]",
                        "EXECUTING": "[EXEC]",
                        "COMPLETE": "[DONE]",
                        "FAILED": "[FAIL]",
                        "BLOCKED": "[BLOCKED]",
                    }.get(phase["state"], "[?]")
                    print(f"  {icon} {phase['name']} ({phase['state']})")
        else:
            print(f"Error: {response.status_code} - {response.text}")
    except Exception as e:
        print(f"Connection error: {e}")


if __name__ == "__main__":
    check_status()
