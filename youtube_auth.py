#!/usr/bin/env python3
"""
One-time YouTube OAuth2 authentication script.

Run this ONCE on a machine with a browser to get a refresh token:
    python youtube_auth.py

It will:
1. Open your browser to Google's consent screen
2. You log in and grant permission
3. Save the refresh token to data/youtube_token.json

After that, the bot can upload videos using the saved token.
The token auto-refreshes, so you only need to run this once.

For VPS deployment:
1. Run this script on your local machine (with browser)
2. Copy the generated data/youtube_token.json to the VPS
"""

import logging
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

from apis.youtube_upload import authenticate_interactive, is_available, CLIENT_SECRET_FILE, TOKEN_FILE


def main():
    print("\n=== YouTube OAuth2 Setup ===\n")

    if not os.path.exists(CLIENT_SECRET_FILE):
        print(f"ERROR: Client secret file not found at:\n  {CLIENT_SECRET_FILE}")
        print(f"\nPlease copy your OAuth client secret JSON to:\n  {CLIENT_SECRET_FILE}")
        sys.exit(1)

    if is_available():
        print(f"A token already exists at: {TOKEN_FILE}")
        answer = input("Re-authenticate? (y/N): ").strip().lower()
        if answer != "y":
            print("Keeping existing token.")
            return

    print("Opening browser for Google OAuth consent...")
    print("(If it doesn't open, check the terminal for a URL)\n")

    success = authenticate_interactive()

    if success:
        print(f"\nAuthentication successful!")
        print(f"Token saved to: {TOKEN_FILE}")
        print(f"\nFor VPS deployment, copy this file to the same path on your VPS:")
        print(f"  scp {TOKEN_FILE} root@YOUR_VPS:{TOKEN_FILE}")
    else:
        print("\nAuthentication failed. Check the logs above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
