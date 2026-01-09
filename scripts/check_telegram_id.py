"""Quick script to check which Telegram ID is which.

Usage:
    python scripts/check_telegram_id.py <id_value>

This will check if the ID is a bot token (contains ':') or chat ID (numeric only).
"""

import sys
import requests


def check_if_bot_token(value: str) -> bool:
    """Check if a value is a valid bot token."""
    if ":" not in value:
        print("❌ This doesn't look like a bot token (no ':' found)")
        print("   Bot tokens have format: 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        return False

    try:
        url = f"https://api.telegram.org/bot{value}/getMe"
        response = requests.get(url, timeout=10)
        data = response.json()

        if data.get("ok"):
            bot_info = data.get("result", {})
            print("\n✅ This IS a valid BOT TOKEN!")
            print("\n   Bot Details:")
            print(f"   - Name: {bot_info.get('first_name')}")
            print(f"   - Username: @{bot_info.get('username')}")
            print(f"   - ID: {bot_info.get('id')}")
            print(f"\n   Save this as: TELEGRAM_BOT_TOKEN=\"{value}\"")
            return True
        else:
            print("\n❌ This is NOT a valid bot token")
            print(f"   Error: {data.get('description', 'Unknown error')}")
            return False

    except Exception as e:
        print(f"\n❌ Failed to verify: {e}")
        return False


def check_if_chat_id(value: str) -> bool:
    """Check if a value looks like a chat ID."""
    # Chat IDs are numeric (can have leading minus for groups)
    if not value.lstrip('-').isdigit():
        print("❌ This doesn't look like a chat ID (not numeric)")
        print("   Chat IDs are numeric: 123456789 or -123456789")
        return False

    print("\n✅ This looks like a CHAT ID!")
    print(f"   Format is correct: {value}")
    print(f"\n   Save this as: TELEGRAM_CHAT_ID=\"{value}\"")
    print("\n   ⚠️  To verify it works, you need to test with your bot token.")
    return True


def main():
    if len(sys.argv) < 2:
        print("Usage: python scripts/check_telegram_id.py <id_value>")
        print("\nExample:")
        print("  python scripts/check_telegram_id.py 123456789:ABCdefGHIjklMNOpqrsTUVwxyz")
        print("  python scripts/check_telegram_id.py 123456789")
        sys.exit(1)

    value = sys.argv[1].strip()

    print(f"\n{'='*60}")
    print("CHECKING TELEGRAM ID")
    print(f"{'='*60}")
    print(f"\nValue: {value[:30]}..." if len(value) > 30 else f"\nValue: {value}")

    # Check if it's a bot token (has colon)
    if ":" in value:
        print("\n→ Contains ':' - checking if it's a BOT TOKEN...")
        check_if_bot_token(value)
    else:
        print("\n→ No ':' found - checking if it's a CHAT ID...")
        check_if_chat_id(value)


if __name__ == "__main__":
    main()
