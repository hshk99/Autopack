"""Interactive Telegram setup helper for Autopack notifications.

This script guides you through setting up Telegram notifications:
1. Getting your bot token from @BotFather
2. Getting your chat ID
3. Setting environment variables
4. Testing the connection

Usage:
    python scripts/setup_telegram.py
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


def print_header(text):
    """Print a formatted header."""
    print("\n" + "="*60)
    print(text)
    print("="*60)


def get_bot_token():
    """Guide user to get bot token."""
    print_header("Step 1: Get Your Bot Token")

    print("\n1. Open Telegram and message @BotFather")
    print("2. Send /mybots")
    print("3. Select your bot (e.g., @CodeSherpaBot)")
    print("4. Click 'API Token' to reveal your token")
    print("5. Copy the token (format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz)")

    print("\nAlternatively, create a new bot:")
    print("1. Message @BotFather")
    print("2. Send /newbot")
    print("3. Follow the prompts to create your bot")
    print("4. Copy the token from the response")

    token = input("\nEnter your bot token: ").strip()

    if not token or ":" not in token:
        print("❌ Invalid token format. Token should contain ':'")
        return None

    return token


def get_chat_id(bot_token):
    """Guide user to get chat ID."""
    print_header("Step 2: Get Your Chat ID")

    print("\n1. Send any message to your bot on Telegram")
    print("2. We'll fetch your chat ID automatically")

    input("\nPress Enter after sending a message to your bot...")

    try:
        import requests

        url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
        response = requests.get(url, timeout=10)
        data = response.json()

        if not data.get("ok"):
            print(f"❌ API error: {data.get('description', 'Unknown error')}")
            return None

        updates = data.get("result", [])
        if not updates:
            print("❌ No messages found. Please send a message to your bot first.")
            return None

        # Get chat ID from most recent message
        chat_id = updates[-1]["message"]["chat"]["id"]
        print(f"\n✅ Found chat ID: {chat_id}")

        return str(chat_id)

    except Exception as e:
        print(f"❌ Error fetching chat ID: {e}")
        print("\nManual method:")
        print(f"1. Visit: https://api.telegram.org/bot{bot_token}/getUpdates")
        print("2. Look for \"chat\":{\"id\":123456789}")
        print("3. Copy the numeric ID")

        chat_id = input("\nEnter your chat ID manually: ").strip()
        return chat_id if chat_id else None


def test_telegram(bot_token, chat_id):
    """Send test message to verify setup."""
    print_header("Step 3: Test Connection")

    try:
        import requests

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        message = (
            "🎉 *Autopack Telegram Setup Complete!*\n\n"
            "You will now receive:\n"
            "  • Notifications for large deletions (100+ lines)\n"
            "  • Approval requests for critical deletions (200+ lines)\n"
            "  • Alerts when phases fail or get stuck\n\n"
            "✅ Setup successful!"
        )

        response = requests.post(url, json={
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }, timeout=10)

        if response.status_code == 200:
            print("\n✅ Test message sent successfully!")
            print("Check your Telegram - you should see the test message.")
            return True
        else:
            print(f"\n❌ Failed to send message: {response.status_code}")
            print(f"Response: {response.text}")
            return False

    except Exception as e:
        print(f"\n❌ Error sending test message: {e}")
        return False


def save_to_env_file(bot_token, chat_id, ngrok_url):
    """Save credentials to .env file."""
    env_file = Path.cwd() / ".env"

    # Read existing .env if it exists
    existing_vars = {}
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    existing_vars[key] = value

    # Update variables
    existing_vars['TELEGRAM_BOT_TOKEN'] = f'"{bot_token}"'
    existing_vars['TELEGRAM_CHAT_ID'] = f'"{chat_id}"'
    if ngrok_url:
        existing_vars['NGROK_URL'] = f'"{ngrok_url}"'

    # Write back
    with open(env_file, 'w') as f:
        f.write("# Autopack Environment Variables\n\n")
        for key, value in existing_vars.items():
            f.write(f"{key}={value}\n")

    print(f"\n✅ Credentials saved to {env_file}")


def print_env_instructions(bot_token, chat_id, ngrok_url):
    """Print instructions for setting environment variables."""
    print_header("Step 4: Set Environment Variables")

    print("\nOption A: Use .env file (recommended)")
    print("  The credentials have been saved to .env file")
    print("  Make sure to load them when running Autopack:")
    print("    source .env  # Linux/Mac")
    print("    # or use python-dotenv in your code")

    print("\nOption B: Export manually (for this session)")
    print("\nWindows (PowerShell):")
    print(f"  $env:TELEGRAM_BOT_TOKEN=\"{bot_token}\"")
    print(f"  $env:TELEGRAM_CHAT_ID=\"{chat_id}\"")
    if ngrok_url:
        print(f"  $env:NGROK_URL=\"{ngrok_url}\"")

    print("\nLinux/Mac (Bash):")
    print(f"  export TELEGRAM_BOT_TOKEN=\"{bot_token}\"")
    print(f"  export TELEGRAM_CHAT_ID=\"{chat_id}\"")
    if ngrok_url:
        print(f"  export NGROK_URL=\"{ngrok_url}\"")


def main():
    """Main setup flow."""
    print_header("🤖 Autopack Telegram Setup")

    print("\nThis script will help you set up Telegram notifications for Autopack.")
    print("You'll receive mobile alerts for:")
    print("  • Large code deletions (100+ lines)")
    print("  • Critical deletions requiring approval (200+ lines)")
    print("  • Phase failures and execution issues")

    # Check if already configured
    existing_token = os.getenv("TELEGRAM_BOT_TOKEN")
    existing_chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if existing_token and existing_chat_id:
        print("\n⚠️  Existing configuration detected:")
        print(f"  Bot Token: {existing_token[:20]}...")
        print(f"  Chat ID: {existing_chat_id}")

        reconfigure = input("\nReconfigure? (y/N): ").strip().lower()
        if reconfigure != 'y':
            print("\n✅ Keeping existing configuration")
            return

    # Get bot token
    bot_token = get_bot_token()
    if not bot_token:
        print("\n❌ Setup failed. Please try again.")
        return

    # Get chat ID
    chat_id = get_chat_id(bot_token)
    if not chat_id:
        print("\n❌ Setup failed. Please try again.")
        return

    # Optional: ngrok URL for webhooks
    print_header("Step 3 (Optional): ngrok URL")
    print("\nFor webhook-based approvals, you need a public URL.")
    print("If you're using ngrok, enter your ngrok URL.")
    print("Otherwise, press Enter to skip.")

    ngrok_url = input("\nngrok URL (e.g., https://harrybot.ngrok.app): ").strip()
    if not ngrok_url:
        ngrok_url = None

    # Test connection
    success = test_telegram(bot_token, chat_id)

    if success:
        # Save to .env file
        save_to_env_file(bot_token, chat_id, ngrok_url)

        # Print instructions
        print_env_instructions(bot_token, chat_id, ngrok_url)

        print_header("✅ Setup Complete!")
        print("\nYou can now test the notifications:")
        print("  python scripts/test_deletion_safeguards.py --test-telegram")

        if ngrok_url:
            print("\nTo set up webhooks for approval buttons:")
            print("  See docs/TELEGRAM_APPROVAL_SETUP.md")
    else:
        print("\n❌ Setup incomplete. Please check your credentials and try again.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Setup cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        sys.exit(1)
