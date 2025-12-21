"""Test deletion safeguards and Telegram notifications without actual deletions.

Usage:
    # Test deletion detection only
    python scripts/test_deletion_safeguards.py --test-detection

    # Test Telegram notification (requires configured bot)
    python scripts/test_deletion_safeguards.py --test-telegram

    # Test full approval workflow (requires backend + ngrok)
    python scripts/test_deletion_safeguards.py --test-approval

    # Test with custom deletion amount
    python scripts/test_deletion_safeguards.py --test-detection --lines-removed 426 --lines-added 12
"""

import sys
import os
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.risk_scorer import RiskScorer
from autopack.quality_gate import QualityGate
from autopack.notifications.telegram_notifier import TelegramNotifier


def test_deletion_detection(lines_removed=426, lines_added=12):
    """Test deletion detection without actually modifying files."""
    print("\n" + "="*60)
    print("TEST: Deletion Detection")
    print("="*60)

    scorer = RiskScorer()

    # Simulate 426-line deletion from ref6.md
    result = scorer.score_change(
        files_changed=["src/autopack/diagnostics/deep_retrieval.py"],
        loc_added=lines_added,
        loc_removed=lines_removed,
        patch_content=None
    )

    print(f"\nSimulated Change:")
    print(f"  Files: src/autopack/diagnostics/deep_retrieval.py")
    print(f"  Lines Added: {lines_added}")
    print(f"  Lines Removed: {lines_removed}")
    print(f"  Net Deletion: {lines_removed - lines_added}")

    print(f"\nRisk Assessment:")
    print(f"  Risk Score: {result['risk_score']}/100")
    print(f"  Risk Level: {result['risk_level'].upper()}")
    print(f"  Large Deletion Detected: {result['checks']['large_deletion']}")
    print(f"  Deletion Threshold Exceeded: {result['checks']['deletion_threshold_exceeded']}")

    print(f"\nRisk Reasons:")
    for reason in result['reasons']:
        print(f"  • {reason}")

    # Test quality gate blocking
    print(f"\nQuality Gate Assessment:")
    gate = QualityGate(repo_root=Path.cwd())

    quality_level = gate._determine_quality_level(
        is_high_risk=False,
        ci_passed=True,
        has_major_issues=False,
        coverage_regressed=False,
        risk_result=result
    )

    print(f"  Quality Level: {quality_level.upper()}")

    if quality_level == "blocked":
        print(f"  ✅ BLOCKED - Would trigger approval request")
    else:
        print(f"  ❌ NOT BLOCKED - Would proceed without approval")

    return result


def test_telegram_notification(lines_removed=426, lines_added=12):
    """Test Telegram notification without actual approval workflow."""
    print("\n" + "="*60)
    print("TEST: Telegram Notification")
    print("="*60)

    notifier = TelegramNotifier()

    if not notifier.is_configured():
        print("\n❌ Telegram not configured!")
        print("\nTo configure, set these environment variables:")
        print("  export TELEGRAM_BOT_TOKEN='your_bot_token'")
        print("  export TELEGRAM_CHAT_ID='your_chat_id'")
        print("  export NGROK_URL='https://harrybot.ngrok.app'")
        return False

    print(f"\n✅ Telegram configured:")
    print(f"  Bot Token: {notifier.bot_token[:20]}...")
    print(f"  Chat ID: {notifier.chat_id}")
    print(f"  Callback URL: {notifier.callback_url}")

    # Simulate deletion info
    deletion_info = {
        'net_deletion': lines_removed - lines_added,
        'loc_removed': lines_removed,
        'loc_added': lines_added,
        'files': ['src/autopack/diagnostics/deep_retrieval.py'],
        'risk_level': 'critical',
        'risk_score': 85,
    }

    print(f"\nSending test notification...")
    print(f"  Phase: test-deletion-safeguard")
    print(f"  Net Deletion: {deletion_info['net_deletion']} lines")
    print(f"  Risk Level: {deletion_info['risk_level'].upper()}")

    success = notifier.send_approval_request(
        phase_id='test-deletion-safeguard',
        deletion_info=deletion_info,
        run_id='test-run',
        context='troubleshoot'
    )

    if success:
        print(f"\n✅ Notification sent successfully!")
        print(f"\nCheck your phone - you should see:")
        print(f"  ⚠️ Autopack Approval Needed")
        print(f"  Phase: test-deletion-safeguard")
        print(f"  Risk: 🚨 CRITICAL (score: 85/100)")
        print(f"  Net Deletion: {deletion_info['net_deletion']} lines")
        print(f"  [✅ Approve]  [❌ Reject]")
        return True
    else:
        print(f"\n❌ Failed to send notification")
        return False


def test_approval_workflow():
    """Test full approval workflow (requires backend + ngrok)."""
    print("\n" + "="*60)
    print("TEST: Full Approval Workflow")
    print("="*60)

    import requests
    import time

    # Check if backend is running
    api_url = os.getenv("AUTOPACK_API_URL", "http://localhost:8001")

    print(f"\nChecking backend at {api_url}...")

    try:
        response = requests.get(f"{api_url}/docs", timeout=5)
        if response.status_code == 200:
            print(f"✅ Backend is running")
        else:
            print(f"⚠️  Backend responded with status {response.status_code}")
    except Exception as e:
        print(f"❌ Backend not accessible: {e}")
        print(f"\nTo start backend:")
        print(f"  uvicorn backend.main:app --port 8001")
        return False

    # Send approval request
    deletion_info = {
        'net_deletion': 414,
        'loc_removed': 426,
        'loc_added': 12,
        'files': ['src/autopack/diagnostics/deep_retrieval.py'],
        'risk_level': 'critical',
        'risk_score': 85,
    }

    print(f"\nSending approval request to backend...")

    try:
        response = requests.post(
            f"{api_url}/approval/request",
            json={
                "phase_id": "test-approval-workflow",
                "deletion_info": deletion_info,
                "run_id": "test-run",
                "context": "troubleshoot"
            },
            timeout=10
        )

        if response.status_code == 200:
            result = response.json()
            print(f"✅ Approval request sent: {result.get('status')}")

            if result.get('status') == 'pending':
                print(f"\n📱 Check your phone and tap Approve or Reject")
                print(f"\nPolling for approval decision (timeout: 60 seconds)...")

                # Poll for decision
                for i in range(12):  # 12 * 5s = 60s
                    time.sleep(5)

                    status_response = requests.get(
                        f"{api_url}/approval/status/test-approval-workflow",
                        timeout=5
                    )

                    if status_response.status_code == 200:
                        status_data = status_response.json()
                        status = status_data.get('status')

                        print(f"  [{i*5}s] Status: {status}")

                        if status == 'approved':
                            print(f"\n✅ APPROVED - Workflow would proceed")
                            return True
                        elif status == 'rejected':
                            print(f"\n❌ REJECTED - Workflow would halt")
                            return True

                print(f"\n⏱️  Timeout - No decision received")
                return False
        else:
            print(f"❌ Request failed: {response.status_code} {response.text}")
            return False

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_thresholds():
    """Test different deletion amounts against thresholds."""
    print("\n" + "="*60)
    print("TEST: Threshold Sensitivity")
    print("="*60)

    scorer = RiskScorer()
    gate = QualityGate(repo_root=Path.cwd())

    test_cases = [
        (10, 5, "Tiny change (net: 5)"),
        (30, 10, "Small change (net: 20)"),
        (80, 20, "Medium change (net: 60) - Just above TROUBLESHOOT_THRESHOLD (50)"),
        (200, 40, "Large change (net: 160) - Above FEATURE_THRESHOLD (150)"),
        (350, 30, "Very large change (net: 320) - Above REFACTOR_THRESHOLD (300)"),
        (426, 12, "Critical change (net: 414) - The ref6.md incident"),
    ]

    print(f"\nThresholds:")
    print(f"  TROUBLESHOOT: 50 lines (strict)")
    print(f"  FEATURE: 150 lines (moderate)")
    print(f"  REFACTOR: 300 lines (lenient)")

    print(f"\nTest Results:")
    print(f"{'Removed':<10} {'Added':<10} {'Net':<10} {'Risk':<10} {'Blocked?':<10} {'Description'}")
    print("-" * 80)

    for removed, added, desc in test_cases:
        result = scorer.score_change(
            files_changed=["test.py"],
            loc_added=added,
            loc_removed=removed,
            patch_content=None
        )

        quality_level = gate._determine_quality_level(
            is_high_risk=False,
            ci_passed=True,
            has_major_issues=False,
            coverage_regressed=False,
            risk_result=result
        )

        blocked = "✅ YES" if quality_level == "blocked" else "❌ NO"

        print(f"{removed:<10} {added:<10} {removed-added:<10} "
              f"{result['risk_level']:<10} {blocked:<10} {desc}")


def main():
    parser = argparse.ArgumentParser(description="Test deletion safeguards without actual deletions")
    parser.add_argument('--test-detection', action='store_true', help='Test deletion detection')
    parser.add_argument('--test-telegram', action='store_true', help='Test Telegram notification')
    parser.add_argument('--test-approval', action='store_true', help='Test full approval workflow')
    parser.add_argument('--test-thresholds', action='store_true', help='Test threshold sensitivity')
    parser.add_argument('--lines-removed', type=int, default=426, help='Lines removed (default: 426)')
    parser.add_argument('--lines-added', type=int, default=12, help='Lines added (default: 12)')

    args = parser.parse_args()

    # If no specific test selected, run all
    if not any([args.test_detection, args.test_telegram, args.test_approval, args.test_thresholds]):
        args.test_detection = True
        args.test_telegram = True
        args.test_thresholds = True

    results = []

    if args.test_detection:
        test_deletion_detection(args.lines_removed, args.lines_added)
        results.append("Detection")

    if args.test_thresholds:
        test_thresholds()
        results.append("Thresholds")

    if args.test_telegram:
        success = test_telegram_notification(args.lines_removed, args.lines_added)
        results.append("Telegram: " + ("✅" if success else "❌"))

    if args.test_approval:
        success = test_approval_workflow()
        results.append("Approval: " + ("✅" if success else "❌"))

    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    for result in results:
        print(f"  {result}")
    print()


if __name__ == "__main__":
    main()
