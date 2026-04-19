#!/usr/bin/env python3
"""
Extract authentication token from Chrome's localStorage/sessionStorage
by using Chrome DevTools Protocol on the running Chrome instance.
"""

import os
import sys
import json
import subprocess
import requests
import time
from pathlib import Path
from datetime import datetime

DATA_DIR = Path(os.environ.get("DATA_DIR", "./data"))
TOKEN_FILE = DATA_DIR / "tokens.json"
BASE_URL = "https://hotdesk.speednet.pl"


def get_chrome_debug_url():
    """Get Chrome DevTools WebSocket URL if Chrome is running with remote debugging."""
    try:
        response = requests.get("http://localhost:9222/json", timeout=2)
        pages = response.json()
        for page in pages:
            if "hotdesk.speednet.pl" in page.get("url", ""):
                return page.get("webSocketDebuggerUrl")
        # Return first page if hotdesk not found
        if pages:
            return pages[0].get("webSocketDebuggerUrl")
    except:
        return None


def start_chrome_with_debugging():
    """Start Chrome with remote debugging enabled."""
    print("Starting Chrome with remote debugging...")
    print("Please navigate to https://hotdesk.speednet.pl in the browser window")

    chrome_path = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    # Start Chrome with debugging port
    subprocess.Popen([
        chrome_path,
        "--remote-debugging-port=9222",
        "--user-data-dir=/tmp/chrome-debug-profile",
        "https://hotdesk.speednet.pl"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    time.sleep(3)


def extract_token_via_cdp():
    """Extract token using Chrome DevTools Protocol."""
    try:
        import websocket
    except ImportError:
        print("Installing websocket-client...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "websocket-client"])
        import websocket

    ws_url = get_chrome_debug_url()
    if not ws_url:
        print("Chrome not running with remote debugging.")
        print("Starting Chrome with debugging enabled...")
        start_chrome_with_debugging()
        time.sleep(5)
        ws_url = get_chrome_debug_url()

    if not ws_url:
        print("Could not connect to Chrome. Please make sure Chrome is running.")
        return None

    print(f"Connected to Chrome at {ws_url}")

    ws = websocket.create_connection(ws_url)

    # Navigate to hotdesk if not already there
    ws.send(json.dumps({
        "id": 1,
        "method": "Runtime.evaluate",
        "params": {
            "expression": "window.location.href"
        }
    }))
    result = json.loads(ws.recv())
    current_url = result.get("result", {}).get("result", {}).get("value", "")
    print(f"Current page: {current_url}")

    if "hotdesk.speednet.pl" not in current_url:
        print("Navigating to hotdesk...")
        ws.send(json.dumps({
            "id": 2,
            "method": "Page.navigate",
            "params": {"url": "https://hotdesk.speednet.pl"}
        }))
        ws.recv()
        time.sleep(3)

    # Try to get token from localStorage
    ws.send(json.dumps({
        "id": 3,
        "method": "Runtime.evaluate",
        "params": {
            "expression": """
                (function() {
                    var tokens = {};
                    // Check localStorage
                    for (var i = 0; i < localStorage.length; i++) {
                        var key = localStorage.key(i);
                        var value = localStorage.getItem(key);
                        if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                            tokens['localStorage_' + key] = value;
                        }
                        // Also check for JSON objects containing tokens
                        try {
                            var obj = JSON.parse(value);
                            if (obj && typeof obj === 'object') {
                                for (var k in obj) {
                                    if (k.toLowerCase().includes('token') || k.toLowerCase().includes('access')) {
                                        tokens['localStorage_' + key + '_' + k] = obj[k];
                                    }
                                }
                            }
                        } catch(e) {}
                    }
                    // Check sessionStorage
                    for (var i = 0; i < sessionStorage.length; i++) {
                        var key = sessionStorage.key(i);
                        var value = sessionStorage.getItem(key);
                        if (key.toLowerCase().includes('token') || key.toLowerCase().includes('auth')) {
                            tokens['sessionStorage_' + key] = value;
                        }
                    }
                    return JSON.stringify(tokens);
                })()
            """
        }
    }))

    result = json.loads(ws.recv())
    tokens_str = result.get("result", {}).get("result", {}).get("value", "{}")
    tokens = json.loads(tokens_str)

    print(f"Found token keys: {list(tokens.keys())}")

    ws.close()

    # Find the access token
    access_token = None
    for key, value in tokens.items():
        if value and len(str(value)) > 100:
            access_token = value
            print(f"Found token in {key}")
            break

    return {"access_token": access_token} if access_token else None


def extract_token_from_network():
    """
    Alternative: Open Chrome and intercept network requests.
    This requires the user to be on the hotdesk page.
    """
    print("\n" + "=" * 60)
    print("MANUAL TOKEN EXTRACTION")
    print("=" * 60)
    print("""
1. Open Chrome and go to: https://hotdesk.speednet.pl
2. Open DevTools (Cmd+Option+I or right-click -> Inspect)
3. Go to the 'Network' tab
4. Click on any request to hotdesk.speednet.pl
5. Look for 'Authorization: Bearer <token>' in the Headers
6. Copy the token (everything after 'Bearer ')
""")

    token = input("Paste the token here (or press Enter to cancel): ").strip()

    if token:
        return {"access_token": token}
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


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Extract token from Chrome")
    parser.add_argument("--manual", action="store_true", help="Manual token entry")
    parser.add_argument("--cdp", action="store_true", help="Use Chrome DevTools Protocol")
    args = parser.parse_args()

    tokens = None

    if args.manual:
        tokens = extract_token_from_network()
    elif args.cdp:
        tokens = extract_token_via_cdp()
    else:
        # Try CDP first, fall back to manual
        print("Attempting automatic extraction via Chrome DevTools Protocol...")
        tokens = extract_token_via_cdp()

        if not tokens:
            print("\nAutomatic extraction failed. Falling back to manual mode.")
            tokens = extract_token_from_network()

    if tokens and tokens.get("access_token"):
        save_tokens(tokens)
        print(f"\nToken saved to {TOKEN_FILE}")
        print("Authentication successful!")
        return 0
    else:
        print("\nNo token captured.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
