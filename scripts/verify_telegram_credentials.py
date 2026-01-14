"""Verify Telegram credentials and help identify bot token vs chat ID.

This script helps you verify your Telegram bot configuration by testing
both the bot token and chat ID.

Usage:
    python scripts/verify_telegram_credentials.py
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def verify_bot_token(token: str) -> bool:
    """Verify that a bot token is valid by calling getMe API."""
    import requests

    print(f"\n{'='*60}")
    print("VERIFYING BOT TOKEN")
    print(f"{'='*60}")

    if not token:
        print("❌ No bot token provided")
        return False

    # Bot tokens should contain a colon
    if ":" not in token:
        print("⚠️  Bot token format looks incorrect (should contain ':')")
        print("   Format should be: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        print(f"   Your value: {token[:20]}..." if len(token) > 20 else f"   Your value: {token}")

    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        print(f"\nTesting bot token: {token[:20]}...")

        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("ok"):
            bot_info = data.get("result", {})
            print("\n✅ Bot token is VALID!")
            print("\n   Bot Details:")
            print(f"   - Name: {bot_info.get('first_name')}")
            print(f"   - Username: @{bot_info.get('username')}")
            print(f"   - ID: {bot_info.get('id')}")
            return True
        else:
            print("\n❌ Bot token is INVALID")
            print(f"   Error: {data.get('description', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"\n❌ Failed to verify bot token: {e}")
        return False


def verify_chat_id(bot_token: str, chat_id: str) -> bool:
    """Verify that a chat ID exists by sending a test message."""
    import requests

    print(f"\n{'='*60}")
    print("VERIFYING CHAT ID")
    print(f"{'='*60}")

    if not chat_id:
        print("❌ No chat ID provided")
        return False

    # Chat IDs should be numeric only
    if not chat_id.lstrip("-").isdigit():
        print("⚠️  Chat ID format looks incorrect (should be numeric only)")
        print("   Format should be: 123456789 or -123456789")
        print(f"   Your value: {chat_id}")

    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        message = (
            "🔍 *Telegram Configuration Test*\n\n"
            "This is a test message from Autopack to verify your chat ID.\n\n"
            "✅ If you see this message, your configuration is correct!\n\n"
            "_You can safely ignore this message._"
        )

        print(f"\nTesting chat ID: {chat_id}")
        print("Sending test message...")

        response = requests.post(
            url, json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}, timeout=10
        )

        data = response.json()

        if data.get("ok"):
            print("\n✅ Chat ID is VALID!")
            print("\n   Message sent successfully!")
            print("   Check your Telegram - you should see the test message.")
            return True
        else:
            print("\n❌ Chat ID is INVALID")
            print(f"   Error: {data.get('description', 'Unknown error')}")

            if "chat not found" in data.get("description", "").lower():
                print(
                    f"\n   💡 Tip: Make sure you've sent at least one message to @{get_bot_username(bot_token)} first"
                )

            return False

    except Exception as e:
        print(f"\n❌ Failed to verify chat ID: {e}")
        return False


def get_bot_username(bot_token: str) -> str:
    """Get bot username from token."""
    try:
        import requests

        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("ok"):
            return data.get("result", {}).get("username", "your_bot")
    except:
        pass
    return "your_bot"


def get_chat_id_from_bot(bot_token: str) -> str:
    """Attempt to get chat ID from recent messages."""
    import requests

    try:
        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("ok"):
            updates = data.get("result", [])
            if updates:
                # Get chat ID from most recent message
                chat_id = updates[-1]["message"]["chat"]["id"]
                return str(chat_id)
    except:
        pass

    return None


def main():
    """Main verification flow."""
    import os

    print(f"\n{'='*60}")
    print("🔍 TELEGRAM CREDENTIALS VERIFICATION")
    print(f"{'='*60}")

    print("\nThis script will help you verify your Telegram bot configuration.")
    print("\nYou need two things:")
    print("  1. TELEGRAM_BOT_TOKEN - from @BotFather (contains ':')")
    print("  2. TELEGRAM_CHAT_ID - your personal chat ID (numeric only)")

    # Get bot token
    print(f"\n{'='*60}")
    print("STEP 1: Enter Bot Token")
    print(f"{'='*60}")

    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if bot_token:
        print(f"\n✓ Found TELEGRAM_BOT_TOKEN in environment: {bot_token[:20]}...")
        use_env = input("Use this token? (Y/n): ").strip().lower()
        if use_env == "n":
            bot_token = None

    if not bot_token:
        print("\nGet your bot token from @BotFather:")
        print("  1. Open Telegram, message @BotFather")
        print("  2. Send /mybots")
        print("  3. Select your bot (e.g., @CodeSherpaBot)")
        print("  4. Click 'API Token'")
        bot_token = input("\nEnter bot token: ").strip()

    # Verify bot token
    if not verify_bot_token(bot_token):
        print("\n❌ Bot token verification failed. Please check your token and try again.")
        return

    # Get chat ID
    print(f"\n{'='*60}")
    print("STEP 2: Enter Chat ID")
    print(f"{'='*60}")

    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if chat_id:
        print(f"\n✓ Found TELEGRAM_CHAT_ID in environment: {chat_id}")
        use_env = input("Use this chat ID? (Y/n): ").strip().lower()
        if use_env == "n":
            chat_id = None

    if not chat_id:
        # Try to fetch from bot
        print("\nAttempting to fetch your chat ID automatically...")
        auto_chat_id = get_chat_id_from_bot(bot_token)

        if auto_chat_id:
            print(f"✓ Found chat ID from recent messages: {auto_chat_id}")
            use_auto = input("Use this chat ID? (Y/n): ").strip().lower()
            if use_auto != "n":
                chat_id = auto_chat_id

        if not chat_id:
            print("\nManual chat ID entry:")
            print("  1. Send any message to your bot on Telegram")
            print("  2. Visit: https://api.telegram.org/bot<YOUR_BOT_TOKEN>/getUpdates")
            print('  3. Look for "chat":{"id":123456789}')
            chat_id = input("\nEnter chat ID: ").strip()

    # Verify chat ID
    if not verify_chat_id(bot_token, chat_id):
        print("\n❌ Chat ID verification failed. Please check your chat ID and try again.")
        return

    # Success! Show .env format
    print(f"\n{'='*60}")
    print("✅ ALL VERIFICATIONS PASSED!")
    print(f"{'='*60}")

    print("\n📝 Add these to your .env file:")
    print(f"\n{'='*60}")
    print(f'TELEGRAM_BOT_TOKEN="{bot_token}"')
    print(f'TELEGRAM_CHAT_ID="{chat_id}"')
    print('NGROK_URL="https://harrybot.ngrok.app"')
    print(f"{'='*60}")

    print("\n✅ Your Telegram bot is configured correctly!")
    print("\nNext steps:")
    print("  1. Save the above variables to your .env file")
    print("  2. Set up webhook: python scripts/setup_telegram.py")
    print("  3. Test notifications: python scripts/test_deletion_safeguards.py --test-telegram")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Verification cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
