#!/usr/bin/env python3
"""
Token Keeper - Background service to keep hotdesk tokens fresh

This service runs in the background and:
1. Monitors token expiration
2. Refreshes tokens proactively (5 minutes before expiration)
3. Falls back to Chrome sync if refresh fails
4. Logs all activity for debugging

Run this as a background service alongside the Flask app.
"""

import os
import json
import time
import logging
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(os.environ.get("DATA_DIR", "./data")) / "token_keeper.log")
    ]
)
logger = logging.getLogger("token_keeper")

# Configuration
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "tokens.json"
REFRESH_BUFFER_SECONDS = 300  # Refresh 5 minutes before expiration
CHECK_INTERVAL_SECONDS = 60  # Check every minute


def load_tokens() -> dict:
    """Load tokens from file."""
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error loading tokens: {e}")
    return {}


def get_token_expiration(access_token: str) -> datetime | None:
    """Extract expiration time from JWT token."""
    try:
        import base64
        payload = access_token.split('.')[1]
        payload += '=' * (4 - len(payload) % 4)
        decoded = json.loads(base64.b64decode(payload))
        exp = decoded.get('exp', 0)
        return datetime.fromtimestamp(exp)
    except Exception as e:
        logger.error(f"Could not decode token: {e}")
        return None


def needs_refresh(access_token: str) -> bool:
    """Check if token needs refresh (expired or expiring soon)."""
    if not access_token:
        return True

    exp_dt = get_token_expiration(access_token)
    if not exp_dt:
        return True

    now = datetime.now()
    seconds_until_expiry = (exp_dt - now).total_seconds()

    if seconds_until_expiry <= 0:
        logger.info("Token has expired")
        return True

    if seconds_until_expiry <= REFRESH_BUFFER_SECONDS:
        logger.info(f"Token expires in {int(seconds_until_expiry)}s, refreshing proactively")
        return True

    return False


def do_refresh() -> bool:
    """Attempt to refresh tokens."""
    try:
        from chrome_token_sync import sync_tokens
        if sync_tokens():
            logger.info("Token refresh successful")
            return True
        logger.error("Token refresh failed")
        return False
    except Exception as e:
        logger.error(f"Refresh error: {e}")
        return False


def run_keeper():
    """Main loop - continuously monitor and refresh tokens."""
    logger.info("Token Keeper started")
    logger.info(f"Token file: {TOKEN_FILE}")
    logger.info(f"Check interval: {CHECK_INTERVAL_SECONDS}s")
    logger.info(f"Refresh buffer: {REFRESH_BUFFER_SECONDS}s before expiry")

    consecutive_failures = 0
    max_failures = 5

    while True:
        try:
            tokens = load_tokens()
            access_token = tokens.get('access_token')

            if needs_refresh(access_token):
                if do_refresh():
                    consecutive_failures = 0
                    # Log new token info
                    tokens = load_tokens()
                    exp = get_token_expiration(tokens.get('access_token', ''))
                    if exp:
                        logger.info(f"New token expires at: {exp}")
                else:
                    consecutive_failures += 1
                    logger.warning(f"Refresh failed ({consecutive_failures}/{max_failures})")

                    if consecutive_failures >= max_failures:
                        logger.error("Max consecutive failures reached - manual intervention needed")
                        # Wait longer before retrying
                        time.sleep(CHECK_INTERVAL_SECONDS * 5)
                        consecutive_failures = 0
            else:
                exp = get_token_expiration(access_token)
                if exp:
                    seconds_left = (exp - datetime.now()).total_seconds()
                    logger.debug(f"Token OK, expires in {int(seconds_left)}s")

        except Exception as e:
            logger.error(f"Keeper loop error: {e}")

        time.sleep(CHECK_INTERVAL_SECONDS)


def main():
    """CLI entry point."""
    global CHECK_INTERVAL_SECONDS
    import argparse

    parser = argparse.ArgumentParser(description="Token Keeper background service")
    parser.add_argument('--once', action='store_true',
                        help="Check and refresh once, then exit")
    parser.add_argument('--interval', type=int, default=CHECK_INTERVAL_SECONDS,
                        help=f"Check interval in seconds (default: {CHECK_INTERVAL_SECONDS})")
    args = parser.parse_args()

    CHECK_INTERVAL_SECONDS = args.interval

    if args.once:
        tokens = load_tokens()
        access_token = tokens.get('access_token')

        if needs_refresh(access_token):
            print("Token needs refresh...")
            if do_refresh():
                print("Refresh successful!")
                tokens = load_tokens()
                exp = get_token_expiration(tokens.get('access_token', ''))
                if exp:
                    print(f"New token expires at: {exp}")
            else:
                print("Refresh failed!")
                exit(1)
        else:
            exp = get_token_expiration(access_token)
            seconds_left = (exp - datetime.now()).total_seconds() if exp else 0
            print(f"Token OK, expires in {int(seconds_left)}s ({exp})")
    else:
        run_keeper()


if __name__ == "__main__":
    main()
