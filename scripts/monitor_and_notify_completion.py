"""Monitor autonomous phase execution and send Telegram notification on completion.

Continuously monitors the 4 BUILD-145 P1 phases and sends a Telegram notification
when all phases reach a terminal state (COMPLETE or FAILED).
"""
import time
import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from autopack.database import SessionLocal
from autopack.models import Phase, PhaseState
from autopack.notifications.telegram_notifier import TelegramNotifier

RUN_IDS = [
    "autopack-onephase-p11-observability-artifact-first",
    "autopack-onephase-p12-embedding-cache-and-cap",
    "autopack-onephase-p13-expand-artifact-substitution",
    "autopack-onephase-research-import-errors"
]

def check_status():
    """Check current status of all phases."""
    session = SessionLocal()
    try:
        phases = session.query(Phase).filter(Phase.run_id.in_(RUN_IDS)).all()

        phase_statuses = []
        for p in phases:
            phase_statuses.append({
                "phase_id": p.phase_id,
                "run_id": p.run_id,
                "state": p.state,
                "tokens_used": p.tokens_used or 0
            })

        return phase_statuses
    finally:
        session.close()

def is_all_complete(phase_statuses):
    """Check if all phases are in terminal state (COMPLETE or FAILED)."""
    terminal_states = {PhaseState.COMPLETE, PhaseState.FAILED}
    return all(p["state"] in terminal_states for p in phase_statuses)

def format_completion_message(phase_statuses):
    """Format completion message for Telegram."""
    completed = sum(1 for p in phase_statuses if p["state"] == PhaseState.COMPLETE)
    failed = sum(1 for p in phase_statuses if p["state"] == PhaseState.FAILED)
    total_tokens = sum(p["tokens_used"] for p in phase_statuses)

    message = f"🚀 *BUILD-145 P1 Phases Complete*\n\n"
    message += f"*Summary*:\n"
    message += f"  ✅ Completed: {completed}/{len(phase_statuses)}\n"
    message += f"  ❌ Failed: {failed}/{len(phase_statuses)}\n"
    message += f"  🎯 Total Tokens: {total_tokens:,}\n\n"

    message += f"*Phase Results*:\n"
    for p in phase_statuses:
        state_emoji = "✅" if p["state"] == PhaseState.COMPLETE else "❌"
        tokens_str = f" ({p['tokens_used']:,} tokens)" if p['tokens_used'] > 0 else ""
        message += f"  {state_emoji} `{p['phase_id']}`: {p['state'].value}{tokens_str}\n"

    return message

def main():
    """Monitor phases and send notification when all complete."""
    print("🔍 Starting phase completion monitor...")
    print(f"Monitoring {len(RUN_IDS)} autonomous phases")
    print("Press Ctrl+C to stop\n")

    notifier = TelegramNotifier()
    if not notifier.is_configured():
        print("⚠️  WARNING: Telegram not configured (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID missing)")
        print("Continuing to monitor but notifications will be disabled\n")
    else:
        print(f"✅ Telegram configured (chat_id: {notifier.chat_id})\n")

    notification_sent = False
    check_interval = 60  # Check every 60 seconds

    try:
        while True:
            phase_statuses = check_status()

            # Print status
            print(f"[{time.strftime('%H:%M:%S')}] Status:")
            for p in phase_statuses:
                state_emoji = {
                    PhaseState.QUEUED: "⏳",
                    PhaseState.EXECUTING: "🔄",
                    PhaseState.COMPLETE: "✅",
                    PhaseState.FAILED: "❌",
                    PhaseState.GATE: "🚪",
                    PhaseState.CI_RUNNING: "🧪"
                }.get(p["state"], "❓")
                print(f"  {state_emoji} {p['phase_id']}: {p['state'].value}")

            # Check if all complete
            if is_all_complete(phase_statuses) and not notification_sent:
                print("\n🎉 All phases complete!")

                # Send Telegram notification
                if notifier.is_configured():
                    message = format_completion_message(phase_statuses)
                    success = notifier.send_completion_notice(
                        phase_id="BUILD-145-P1",
                        status="complete",
                        message=message
                    )

                    if success:
                        print("✅ Telegram notification sent!")
                        notification_sent = True
                    else:
                        print("❌ Failed to send Telegram notification")
                else:
                    print("⚠️  Telegram not configured - notification skipped")
                    notification_sent = True  # Don't retry if not configured

                # Print summary
                print("\n" + "=" * 70)
                print(format_completion_message(phase_statuses))
                print("=" * 70)

                print("\n✅ Monitoring complete. Exiting.")
                break

            print(f"  Waiting {check_interval}s before next check...\n")
            time.sleep(check_interval)

    except KeyboardInterrupt:
        print("\n\n⚠️  Monitoring stopped by user")
        sys.exit(0)

if __name__ == "__main__":
    main()
