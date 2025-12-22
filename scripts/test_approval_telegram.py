"""Test script to send approval request and verify Telegram notification.

This will:
1. Send a test approval request to the backend
2. Should trigger a Telegram message to your phone
3. Poll for approval status
"""

import requests
import time
import os

# Configuration
API_URL = os.getenv("AUTOPACK_API_URL", "http://localhost:8001")
AUTO_APPROVE = os.getenv("AUTO_APPROVE_BUILD113", "false")

print("=" * 80)
print("APPROVAL FLOW TEST WITH TELEGRAM NOTIFICATIONS")
print("=" * 80)
print(f"API URL: {API_URL}")
print(f"Auto-approve mode: {AUTO_APPROVE}")
print(f"Telegram configured: {os.getenv('TELEGRAM_BOT_TOKEN') is not None}")
print(f"Telegram chat ID: {os.getenv('TELEGRAM_CHAT_ID', 'NOT SET')}")
print("=" * 80)

# Test data - simulate a risky patch
test_data = {
    "run_id": "telegram-test-run",
    "phase_id": "telegram-test-phase",
    "context": "build113_risky_decision",
    "decision_info": {
        "type": "RISKY_PATCH",
        "risk_level": "high",
        "confidence": "85%",
        "rationale": "Large refactoring with cross-cutting changes across multiple modules",
        "files_modified": [
            "src/core/engine.py",
            "src/api/handlers.py",
            "src/utils/helpers.py"
        ],
        "files_count": 3,
        "risk_score": 85
    },
    "deletion_info": {
        "net_deletion": 150,
        "loc_removed": 200,
        "loc_added": 50,
        "files": [
            "src/core/engine.py",
            "src/api/handlers.py"
        ],
        "risk_level": "high",
        "risk_score": 85
    }
}

print("\n📤 Sending approval request...")
print(f"Request: POST {API_URL}/approval/request")
print(f"Payload: {test_data['context']}, risk={test_data['decision_info']['risk_level']}")

try:
    response = requests.post(
        f"{API_URL}/approval/request",
        json=test_data,
        timeout=30
    )
    response.raise_for_status()
    result = response.json()

    print(f"\n✅ Response received: {response.status_code}")
    print(f"Status: {result.get('status')}")
    print(f"Reason: {result.get('reason')}")

    if result.get("status") == "approved":
        print("\n✅ AUTO-APPROVED (AUTO_APPROVE_BUILD113=true)")
        print("To test Telegram notifications, set AUTO_APPROVE_BUILD113=false")
        exit(0)

    approval_id = result.get("approval_id")
    telegram_sent = result.get("telegram_sent")
    timeout_at = result.get("timeout_at")

    print(f"Approval ID: {approval_id}")
    print(f"Telegram sent: {telegram_sent}")
    print(f"Timeout at: {timeout_at}")

    if telegram_sent:
        print("\n📱 TELEGRAM NOTIFICATION SENT!")
        print("Check your phone for the approval request message.")
        print("You should see a message with Approve/Reject buttons.")
    else:
        print("\n⚠️  Telegram notification NOT sent")
        print("Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID environment variables")

    print("\n⏳ Polling for approval status...")
    print("(Tap Approve or Reject on your phone)")

    # Poll for 60 seconds
    for i in range(6):
        time.sleep(10)

        status_response = requests.get(
            f"{API_URL}/approval/status/{approval_id}",
            timeout=10
        )
        status_response.raise_for_status()
        status_data = status_response.json()

        current_status = status_data.get("status")
        print(f"  [{i*10}s] Status: {current_status}")

        if current_status == "approved":
            print("\n✅ APPROVED!")
            print(f"Response method: {status_data.get('response_method')}")
            print(f"Approval reason: {status_data.get('approval_reason')}")
            break
        elif current_status == "rejected":
            print("\n❌ REJECTED!")
            print(f"Response method: {status_data.get('response_method')}")
            print(f"Rejection reason: {status_data.get('rejected_reason')}")
            break
        elif current_status == "timeout":
            print("\n⏱️  TIMED OUT!")
            print(f"Default action: {status_data.get('approval_reason') or status_data.get('rejected_reason')}")
            break
    else:
        print("\n⏸️  Still pending after 60 seconds")
        print("The approval will timeout after 15 minutes (configurable)")

except requests.exceptions.ConnectionError:
    print(f"\n❌ ERROR: Cannot connect to {API_URL}")
    print("Make sure the backend server is running:")
    print("  cd c:/dev/Autopack")
    print("  PYTHONUTF8=1 PYTHONPATH=src python -m uvicorn autopack.main:app --host 0.0.0.0 --port 8001")
    exit(1)
except Exception as e:
    print(f"\n❌ ERROR: {e}")
    import traceback
    traceback.print_exc()
    exit(1)

print("\n" + "=" * 80)
print("TEST COMPLETE")
print("=" * 80)
