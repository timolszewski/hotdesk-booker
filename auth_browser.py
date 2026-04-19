#!/usr/bin/env python3
"""
Browser-based authentication for Hotdesk Booker
Uses Playwright to maintain a persistent browser session and extract tokens
"""

import os
import sys
import json
import asyncio
import logging
from pathlib import Path
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration
DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "tokens.json"
SESSION_DIR = DATA_DIR / "browser_session"
BASE_URL = "https://hotdesk.speednet.pl"


async def extract_tokens_from_browser(headless: bool = True, force_login: bool = False, use_real_chrome: bool = True):
    """
    Open browser, authenticate if needed, and extract tokens.
    Session is saved so you only need to log in once.
    """
    from playwright.async_api import async_playwright

    SESSION_DIR.mkdir(parents=True, exist_ok=True)

    async with async_playwright() as p:
        if use_real_chrome:
            # Use the actual Chrome installation with user's profile
            chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            user_data_dir = os.path.expanduser("~/Library/Application Support/Google/Chrome")

            # Check if Chrome path exists
            if not os.path.exists(chrome_path):
                logger.warning("Chrome not found, falling back to Playwright browser")
                use_real_chrome = False

        if use_real_chrome:
            # Launch with real Chrome and user profile
            # We need to use a copy of the profile to avoid conflicts with running Chrome
            logger.info("Using your actual Chrome browser with existing session...")

            context = await p.chromium.launch_persistent_context(
                str(SESSION_DIR),  # Use our session dir, but we'll copy cookies
                headless=headless,
                channel="chrome",  # Use installed Chrome
                viewport={"width": 1280, "height": 720},
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-first-run',
                    '--no-default-browser-check'
                ],
                slow_mo=100
            )
        else:
            # Use persistent context to save session
            context = await p.chromium.launch_persistent_context(
                str(SESSION_DIR),
                headless=headless,
                viewport={"width": 1280, "height": 720},
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--start-maximized',
                    '--no-first-run',
                    '--no-default-browser-check'
                ],
                slow_mo=100  # Slow down actions to be more visible
            )

        if not headless:
            # Bring browser to front
            print("\n" + "=" * 60)
            print("  BROWSER WINDOW OPENING")
            print("=" * 60 + "\n")

        page = await context.new_page()

        # Variable to capture token
        captured_token = {"access_token": None, "refresh_token": None}

        # Intercept API requests to capture tokens
        async def handle_request(request):
            url = request.url
            # Log API requests for debugging
            if "hotdesk.speednet.pl" in url and "/api/" not in url and "/static/" not in url:
                logger.debug(f"Request to: {url}")

            auth_header = request.headers.get("authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header.replace("Bearer ", "")
                if token and len(token) > 100:  # JWT tokens are long
                    captured_token["access_token"] = token
                    logger.info(f"Captured access token from request to {url}")

        async def handle_response(response):
            url = response.url
            # Capture tokens from various auth-related responses
            if "/auth" in url or "/token" in url or "/login" in url:
                logger.info(f"Auth-related response from: {url} (status: {response.status})")
                try:
                    content_type = response.headers.get("content-type", "")
                    if "json" in content_type:
                        data = await response.json()
                        logger.info(f"Response data keys: {list(data.keys()) if isinstance(data, dict) else 'not a dict'}")
                        if isinstance(data, dict):
                            # Look for various token field names
                            for key in ["accessToken", "access_token", "token", "id_token", "idToken"]:
                                if data.get(key) and len(str(data[key])) > 100:
                                    captured_token["access_token"] = data[key]
                                    logger.info(f"Captured access token from response field: {key}")
                            for key in ["refreshToken", "refresh_token"]:
                                if data.get(key):
                                    captured_token["refresh_token"] = data[key]
                                    logger.info(f"Captured refresh token from response field: {key}")
                except Exception as e:
                    logger.debug(f"Could not parse response: {e}")

        page.on("request", handle_request)
        page.on("response", handle_response)

        # Navigate to the app
        logger.info(f"Navigating to {BASE_URL}")
        await page.goto(BASE_URL, wait_until="networkidle")

        # Check if we're logged in by looking for specific elements
        await asyncio.sleep(2)

        # Check URL - if redirected to login, we need authentication
        current_url = page.url
        logger.info(f"Current URL: {current_url}")

        # Check if already logged in (URL doesn't contain login)
        is_logged_in = "hotdesk.speednet.pl" in current_url and "login" not in current_url.lower()

        if is_logged_in:
            logger.info("Already logged in! Capturing tokens...")
            # We're already authenticated, just need to capture the token
            # Wait a moment for any pending requests
            await asyncio.sleep(2)

        needs_login = not is_logged_in and ("login" in current_url.lower() or "microsoftonline" in current_url.lower() or force_login)

        if needs_login:
            if headless:
                logger.info("Login required. Restarting in visible mode...")
                await context.close()
                return await extract_tokens_from_browser(headless=False, force_login=False)

            print("\n" + "=" * 50)
            print("Browser should be opening...")
            print("Please log in using the browser window.")
            print("The browser will stay open until you're logged in.")
            print("=" * 50 + "\n")

            logger.info("=" * 50)
            logger.info("Please log in using the browser window.")
            logger.info("The browser will stay open until you're logged in.")
            logger.info("=" * 50)

            # Wait for navigation away from login page (max 300 seconds = 5 min)
            max_wait = 300
            waited = 0
            while waited < max_wait:
                current = page.url.lower()
                # Check if we're past login - look for main app URL patterns
                # After Azure SSO, URL should be something like hotdesk.speednet.pl/ui/ (not /ui/login/)
                is_login_page = "login" in current or "microsoftonline" in current or "login.live" in current
                is_main_app = "hotdesk.speednet.pl" in current and not is_login_page

                if is_main_app:
                    logger.info(f"Login successful! Redirected to: {current}")
                    break

                await asyncio.sleep(1)
                waited += 1
                if waited % 10 == 0:
                    logger.info(f"Still waiting for login... ({waited}s) - Current: {page.url}")

            if waited >= max_wait:
                logger.warning("Login timeout - continuing anyway")
            else:
                logger.info("Login detected! Waiting for page to fully load...")

            await asyncio.sleep(5)  # Give more time for page to load and make API calls

        # Trigger an API call to capture the token
        logger.info("Triggering API calls to capture token...")

        # Navigate to the main UI to trigger API calls
        try:
            await page.goto(f"{BASE_URL}/ui/", wait_until="networkidle", timeout=30000)
        except Exception as e:
            logger.warning(f"Navigation timeout (this is often OK): {e}")

        await asyncio.sleep(3)

        # Try to trigger more API calls by navigating to different pages
        try:
            # Try clicking on date picker or navigation elements to trigger API calls
            await page.evaluate("""
                // Dispatch events to trigger potential API calls
                document.body.click();
            """)
            await asyncio.sleep(2)
        except Exception as e:
            logger.debug(f"Click trigger failed: {e}")

        # Try accessing booking page
        try:
            await page.goto(f"{BASE_URL}/ui/booking", wait_until="networkidle", timeout=15000)
            await asyncio.sleep(2)
        except:
            pass

        # Check localStorage and sessionStorage for tokens
        logger.info("Checking localStorage and sessionStorage for tokens...")

        storage_data = await page.evaluate("""
            () => {
                const data = {localStorage: {}, sessionStorage: {}};
                // localStorage
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    data.localStorage[key] = localStorage.getItem(key);
                }
                // sessionStorage
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    data.sessionStorage[key] = sessionStorage.getItem(key);
                }
                return data;
            }
        """)

        # Search for tokens in localStorage
        local_storage = storage_data.get("localStorage", {})
        session_storage = storage_data.get("sessionStorage", {})

        # Log all storage keys for debugging
        logger.info(f"localStorage keys: {list(local_storage.keys())}")
        logger.info(f"sessionStorage keys: {list(session_storage.keys())}")

        # Search both storages for tokens
        for storage_name, storage in [("localStorage", local_storage), ("sessionStorage", session_storage)]:
            for key, value in storage.items():
                if value and ("token" in key.lower() or "auth" in key.lower() or "jwt" in key.lower() or "access" in key.lower()):
                    logger.info(f"Found {storage_name} key: {key} (length: {len(value) if value else 0})")
                    # JWT tokens are typically 100+ characters
                    if value and len(value) > 100 and not captured_token["access_token"]:
                        captured_token["access_token"] = value
                        logger.info(f"Captured token from {storage_name}[{key}]")

                # Also check for JSON objects that might contain tokens
                if value and value.startswith("{"):
                    try:
                        obj = json.loads(value)
                        if isinstance(obj, dict):
                            for k, v in obj.items():
                                if "token" in k.lower() or "access" in k.lower():
                                    if isinstance(v, str) and len(v) > 100:
                                        captured_token["access_token"] = v
                                        logger.info(f"Captured token from {storage_name}[{key}].{k}")
                    except:
                        pass

        # Also try to get from cookies
        cookies = await context.cookies()
        logger.info(f"Found {len(cookies)} cookies")
        for cookie in cookies:
            if "token" in cookie["name"].lower() or "auth" in cookie["name"].lower() or "jwt" in cookie["name"].lower():
                logger.info(f"Found relevant cookie: {cookie['name']} (length: {len(cookie.get('value', ''))})")
                if cookie.get("value") and len(cookie["value"]) > 100 and not captured_token["access_token"]:
                    captured_token["access_token"] = cookie["value"]
                    logger.info(f"Captured token from cookie: {cookie['name']}")

        await context.close()

        if captured_token["access_token"]:
            # Save tokens
            save_tokens(captured_token)
            logger.info("Tokens saved successfully!")
            return captured_token
        else:
            logger.warning("Could not capture tokens. Try running with --visible flag.")
            return None


def save_tokens(tokens):
    """Save tokens to file."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    existing = {}
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            existing = json.load(f)

    existing.update({k: v for k, v in tokens.items() if v})
    existing["updated_at"] = datetime.now().isoformat()

    with open(TOKEN_FILE, "w") as f:
        json.dump(existing, f, indent=2)


def load_tokens():
    """Load existing tokens."""
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE) as f:
            return json.load(f)
    return {}


async def refresh_token_if_needed():
    """Check if token needs refresh and refresh it."""
    import requests

    tokens = load_tokens()
    access_token = tokens.get("access_token")

    if not access_token:
        logger.info("No access token, starting browser auth...")
        return await extract_tokens_from_browser(headless=True)

    # Try to use the token
    response = requests.get(
        f"{BASE_URL}/booking/",
        headers={"Authorization": f"Bearer {access_token}"}
    )

    if response.status_code == 401:
        logger.info("Token expired, refreshing via browser...")
        return await extract_tokens_from_browser(headless=True)

    logger.info("Token is still valid")
    return tokens


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Browser-based token authentication")
    parser.add_argument("--visible", action="store_true", help="Run browser in visible mode")
    parser.add_argument("--force", action="store_true", help="Force new login")
    parser.add_argument("--check", action="store_true", help="Just check if token is valid")
    args = parser.parse_args()

    if args.check:
        tokens = load_tokens()
        if tokens.get("access_token"):
            import requests
            response = requests.get(
                f"{BASE_URL}/booking/",
                headers={"Authorization": f"Bearer {tokens['access_token']}"}
            )
            if response.status_code == 200:
                print("Token is valid")
                sys.exit(0)
            else:
                print(f"Token invalid (status {response.status_code})")
                sys.exit(1)
        else:
            print("No token found")
            sys.exit(1)

    result = asyncio.run(extract_tokens_from_browser(
        headless=not args.visible,
        force_login=args.force
    ))

    if result:
        print("Authentication successful!")
        print(f"Token saved to {TOKEN_FILE}")
        sys.exit(0)
    else:
        print("Authentication failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
