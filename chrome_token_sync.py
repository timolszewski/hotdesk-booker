#!/usr/bin/env python3
"""
Chrome Token Sync for Hotdesk Booker

Automatically extracts refresh tokens from Chrome's localStorage
and maintains persistent authentication with the hotdesk API.
"""

import os
import json
import subprocess
import logging
from pathlib import Path
from datetime import datetime
import requests

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "tokens.json"
BASE_URL = "https://hotdesk.speednet.pl"

# Chrome localStorage path (macOS)
CHROME_LOCALSTORAGE_DIR = Path.home() / "Library/Application Support/Google/Chrome/Default/Local Storage/leveldb"


def extract_refresh_token_from_chrome() -> str | None:
    """
    Extract the latest refresh token from Chrome's localStorage LevelDB.
    Returns the most recent refresh token found, or None if not found.
    """
    if not CHROME_LOCALSTORAGE_DIR.exists():
        logger.error(f"Chrome localStorage directory not found: {CHROME_LOCALSTORAGE_DIR}")
        return None

    refresh_tokens = []

    # Search all LevelDB files (both .ldb and .log files)
    for filepath in CHROME_LOCALSTORAGE_DIR.iterdir():
        if filepath.suffix in ['.ldb', '.log']:
            try:
                # Use strings command to extract readable text
                result = subprocess.run(
                    ['strings', str(filepath)],
                    capture_output=True,
                    text=True,
                    timeout=10
                )

                lines = result.stdout.split('\n')
                for i, line in enumerate(lines):
                    # Look for hotdesk refreshToken entries
                    if 'hotdesk.speednet.pl' in line and 'refreshToken' in line:
                        # The token value is typically on the next line or nearby
                        for j in range(i, min(i + 5, len(lines))):
                            potential_token = lines[j].strip()
                            # Refresh tokens are UUIDs: 8-4-4-4-12 format
                            if _is_uuid(potential_token):
                                refresh_tokens.append(potential_token)
                    elif 'refreshToken' in line:
                        # Also check the same line and nearby for UUID
                        for j in range(max(0, i - 1), min(i + 3, len(lines))):
                            potential_token = lines[j].strip()
                            if _is_uuid(potential_token):
                                # Verify it's associated with hotdesk
                                context = '\n'.join(lines[max(0, j-5):min(j+5, len(lines))])
                                if 'hotdesk' in context.lower():
                                    refresh_tokens.append(potential_token)

            except Exception as e:
                logger.debug(f"Error reading {filepath}: {e}")
                continue

    if refresh_tokens:
        # Return the last (most recent) token found
        latest_token = refresh_tokens[-1]
        logger.info(f"Found {len(refresh_tokens)} refresh token(s), using latest: {latest_token[:8]}...")
        return latest_token

    logger.warning("No refresh tokens found in Chrome localStorage")
    return None


def _is_uuid(s: str) -> bool:
    """Check if string is a valid UUID format."""
    import re
    uuid_pattern = r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    return bool(re.match(uuid_pattern, s.lower()))


def load_tokens() -> dict:
    """Load existing tokens from file."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
    return {}


def save_tokens(tokens: dict) -> bool:
    """Save tokens to file."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tokens['updated_at'] = datetime.now().isoformat()
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Error saving tokens: {e}")
        return False


def refresh_access_token(refresh_token: str) -> dict | None:
    """
    Use refresh token to get new access token.
    Returns dict with new tokens or None on failure.
    """
    try:
        response = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refreshToken": refresh_token},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            return {
                'access_token': data.get('accessToken'),
                'refresh_token': data.get('refreshToken'),  # New rotating refresh token
            }
        else:
            logger.error(f"Refresh failed with status {response.status_code}")
            return None

    except Exception as e:
        logger.error(f"Refresh request error: {e}")
        return None


def verify_token(access_token: str) -> bool:
    """Verify if an access token is still valid."""
    try:
        response = requests.get(
            f"{BASE_URL}/booking/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Token verification error: {e}")
        return False


def sync_tokens() -> bool:
    """
    Main sync function:
    1. Check if current token is valid
    2. If not, try to refresh using stored refresh token
    3. If that fails, extract fresh refresh token from Chrome
    4. Return True if we have a valid access token
    """
    tokens = load_tokens()
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')

    # Step 1: Check if current access token works
    if access_token and verify_token(access_token):
        logger.info("Current access token is valid")
        return True

    logger.info("Access token expired or missing, attempting refresh...")

    # Step 2: Try to refresh using stored refresh token
    if refresh_token:
        logger.info("Trying stored refresh token...")
        new_tokens = refresh_access_token(refresh_token)
        if new_tokens and new_tokens.get('access_token'):
            tokens.update(new_tokens)
            save_tokens(tokens)
            logger.info("Successfully refreshed using stored token")
            return True
        else:
            logger.warning("Stored refresh token failed")

    # Step 3: Extract fresh refresh token from Chrome
    logger.info("Extracting refresh token from Chrome localStorage...")
    chrome_refresh_token = extract_refresh_token_from_chrome()

    if chrome_refresh_token:
        logger.info(f"Found Chrome refresh token: {chrome_refresh_token[:8]}...")
        new_tokens = refresh_access_token(chrome_refresh_token)
        if new_tokens and new_tokens.get('access_token'):
            tokens.update(new_tokens)
            save_tokens(tokens)
            logger.info("Successfully refreshed using Chrome token")
            return True
        else:
            logger.error("Chrome refresh token also failed - you may need to log in again")
            return False

    logger.error("No valid refresh token found - please log in to hotdesk.speednet.pl in Chrome")
    return False


def get_valid_access_token() -> str | None:
    """
    Get a valid access token, refreshing if necessary.
    This is the main entry point for other scripts.
    """
    if sync_tokens():
        tokens = load_tokens()
        return tokens.get('access_token')
    return None


def main():
    """CLI interface for token sync."""
    import argparse

    parser = argparse.ArgumentParser(description="Sync hotdesk tokens from Chrome")
    parser.add_argument('--extract-only', action='store_true',
                        help="Only extract refresh token from Chrome, don't refresh")
    parser.add_argument('--force-refresh', action='store_true',
                        help="Force refresh even if current token is valid")
    parser.add_argument('--status', action='store_true',
                        help="Show current token status")
    args = parser.parse_args()

    if args.status:
        tokens = load_tokens()
        access_token = tokens.get('access_token')
        refresh_token = tokens.get('refresh_token')
        updated = tokens.get('updated_at', 'unknown')

        print(f"Token file: {TOKEN_FILE}")
        print(f"Last updated: {updated}")
        print(f"Access token: {'Present' if access_token else 'Missing'}")
        print(f"Refresh token: {'Present' if refresh_token else 'Missing'}")

        if access_token:
            is_valid = verify_token(access_token)
            print(f"Access token valid: {is_valid}")

            # Decode JWT to show expiration
            try:
                import base64
                payload = access_token.split('.')[1]
                payload += '=' * (4 - len(payload) % 4)
                decoded = json.loads(base64.b64decode(payload))
                exp = datetime.fromtimestamp(decoded.get('exp', 0))
                print(f"Expires: {exp}")
            except:
                pass
        return

    if args.extract_only:
        token = extract_refresh_token_from_chrome()
        if token:
            print(f"Found refresh token: {token}")
        else:
            print("No refresh token found")
        return

    if args.force_refresh:
        # Clear access token to force refresh
        tokens = load_tokens()
        tokens['access_token'] = None
        save_tokens(tokens)

    if sync_tokens():
        print("Token sync successful!")
        tokens = load_tokens()
        print(f"Access token: {tokens.get('access_token', '')[:50]}...")
    else:
        print("Token sync failed - please log in to Chrome")
        exit(1)


if __name__ == "__main__":
    main()
