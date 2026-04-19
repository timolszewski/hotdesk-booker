#!/usr/bin/env python3
"""
Hotdesk Booking Automation Agent
Automatically books a desk at hotdesk.speednet.pl every day at 00:01
"""

import os
import sys
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
import requests

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Create formatter
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')

# Console handler
console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)

# File handler (only in Docker)
if os.path.exists('/app/logs'):
    file_handler = logging.FileHandler('/app/logs/booker.log')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# Configuration
BASE_URL = "https://hotdesk.speednet.pl"
LOCATION_ID = "8f78f4e5-1cd6-40b7-a91e-34cab6768732"  # 31 piętro

# Data directory
DATA_DIR = os.environ.get("DATA_DIR", "/app/data")
TOKEN_FILE = os.environ.get("TOKEN_FILE", os.path.join(DATA_DIR, "tokens.json"))
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")


def load_config():
    """Load configuration from file."""
    defaults = {
        "preferred_desks": ["S05", "S15", "S10", "S14"],
        "booking_subject": "Tim codziennie w biurze",
        "schedule_hour": 0,
        "schedule_minute": 1,
        "schedule_days": [1, 2, 3, 4, 5],
        "auto_book_enabled": True
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**defaults, **config}
    except Exception as e:
        logger.warning(f"Could not load config, using defaults: {e}")
    return defaults


# Load config
_config = load_config()
PREFERRED_DESKS = _config.get("preferred_desks", ["S05", "S15", "S10", "S14"])
BOOKING_SUBJECT = _config.get("booking_subject", "Tim codziennie w biurze")


class HotdeskBooker:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "Accept": "*/*",
            "Origin": BASE_URL,
            "User-Agent": "HotdeskBooker/1.0"
        })
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.desk_map: dict = {}  # name -> id mapping

    def load_tokens(self) -> bool:
        """Load tokens from file."""
        try:
            if os.path.exists(TOKEN_FILE):
                with open(TOKEN_FILE, 'r') as f:
                    data = json.load(f)
                    self.access_token = data.get('access_token')
                    self.refresh_token = data.get('refresh_token')
                    logger.info("Tokens loaded from file")
                    return True
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
        return False

    def save_tokens(self):
        """Save tokens to file."""
        try:
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, 'w') as f:
                json.dump({
                    'access_token': self.access_token,
                    'refresh_token': self.refresh_token,
                    'updated_at': datetime.now().isoformat()
                }, f, indent=2)
            logger.info("Tokens saved to file")
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")

    def refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token."""
        if not self.refresh_token:
            logger.error("No refresh token available")
            return False

        try:
            response = self.session.post(
                f"{BASE_URL}/auth/refresh",
                json={"refreshToken": self.refresh_token}
            )

            if response.status_code == 200:
                data = response.json()
                self.access_token = data.get('accessToken')
                new_refresh_token = data.get('refreshToken')
                if new_refresh_token:
                    self.refresh_token = new_refresh_token
                self.save_tokens()
                logger.info("Access token refreshed successfully")
                return True
            else:
                logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            logger.error(f"Token refresh error: {e}")
            return False

    def _make_authenticated_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make an authenticated request, refreshing token if needed."""
        headers = kwargs.pop('headers', {})
        headers['Authorization'] = f"Bearer {self.access_token}"

        response = self.session.request(method, url, headers=headers, **kwargs)

        # If unauthorized, try refreshing token
        if response.status_code == 401:
            logger.info("Token expired, refreshing...")
            if self.refresh_access_token():
                headers['Authorization'] = f"Bearer {self.access_token}"
                response = self.session.request(method, url, headers=headers, **kwargs)

        return response

    def fetch_desk_availability(self, date: datetime) -> list:
        """Fetch desk availability for a specific date."""
        enter = date.strftime("%Y-%m-%dT00:00:00.000Z")
        leave = date.strftime("%Y-%m-%dT23:59:59.000Z")

        url = f"{BASE_URL}/location/{LOCATION_ID}/space/availability"
        params = {"enter": enter, "leave": leave}

        response = self._make_authenticated_request("GET", url, params=params)

        if response.status_code == 200:
            desks = response.json()
            # Build desk map
            self.desk_map = {desk['name']: desk['id'] for desk in desks}
            logger.info(f"Fetched {len(desks)} desks for {date.strftime('%Y-%m-%d')}")
            return desks
        else:
            logger.error(f"Failed to fetch desks: {response.status_code} - {response.text}")
            return []

    def find_available_desk(self, desks: list) -> Optional[dict]:
        """Find the first available desk from priority list."""
        # Create lookup by name
        desk_by_name = {desk['name']: desk for desk in desks}

        # Try preferred desks first
        for desk_name in PREFERRED_DESKS:
            desk_name = desk_name.strip()
            if desk_name in desk_by_name:
                desk = desk_by_name[desk_name]
                if desk.get('available') and desk.get('allowed'):
                    logger.info(f"Found preferred desk: {desk_name}")
                    return desk
                else:
                    reason = []
                    if not desk.get('available'):
                        reason.append("not available")
                    if not desk.get('allowed'):
                        reason.append("not allowed")
                    logger.info(f"Desk {desk_name} skipped: {', '.join(reason)}")

        # Fallback: any available S desk
        logger.info("Preferred desks unavailable, looking for any S desk...")
        for desk in sorted(desks, key=lambda d: d['name']):
            if desk['name'].startswith('S') and desk.get('available') and desk.get('allowed'):
                logger.info(f"Found fallback desk: {desk['name']}")
                return desk

        logger.warning("No available desks found!")
        return None

    def book_desk(self, desk_id: str, date: datetime, subject: str = None) -> bool:
        """Book a specific desk for a date."""
        enter = date.strftime("%Y-%m-%dT00:00:00.000Z")
        leave = date.strftime("%Y-%m-%dT23:59:59.000Z")

        payload = {
            "enter": enter,
            "leave": leave,
            "spaceId": desk_id,
            "subject": subject or BOOKING_SUBJECT,
            "userEmail": ""
        }

        response = self._make_authenticated_request(
            "POST",
            f"{BASE_URL}/booking/",
            json=payload
        )

        if response.status_code == 201:
            logger.info(f"Successfully booked desk for {date.strftime('%Y-%m-%d')}")
            return True
        else:
            error_msg = response.text
            try:
                error_data = response.json()
                error_msg = error_data.get('message', error_data.get('error', str(error_data)))
            except:
                pass
            logger.error(f"Booking failed: {response.status_code} - {error_msg}")
            return False

    def check_existing_booking(self, date: datetime) -> bool:
        """Check if there's already a booking for the given date."""
        # The availability endpoint shows bookings in the response
        desks = self.fetch_desk_availability(date)
        for desk in desks:
            for booking in desk.get('bookings', []):
                # If there's a booking by us, we're already booked
                # The API should indicate this, but we'd need to check user info
                pass

        # Alternative: fetch user's bookings
        response = self._make_authenticated_request("GET", f"{BASE_URL}/booking/")
        if response.status_code == 200:
            bookings = response.json()
            date_str = date.strftime("%Y-%m-%d")
            for booking in bookings:
                enter = booking.get('enter', '')
                if date_str in enter:
                    desk_name = booking.get('spaceName') or booking.get('space', {}).get('name', 'unknown desk')
                    logger.info(f"Already have a booking for {date_str}: {desk_name}")
                    return True
        return False

    def run(self, target_date: datetime = None):
        """Main booking routine."""
        # Load tokens
        if not self.load_tokens():
            # Try environment variables as fallback
            self.access_token = os.environ.get('ACCESS_TOKEN')
            self.refresh_token = os.environ.get('REFRESH_TOKEN')

            if not self.refresh_token:
                logger.error("No tokens available. Please set REFRESH_TOKEN environment variable or provide tokens.json")
                sys.exit(1)

        # Use existing access token if available, otherwise try to refresh
        if not self.access_token:
            logger.info("No access token, attempting refresh...")
            if not self.refresh_access_token():
                logger.error("Failed to obtain valid access token")
                sys.exit(1)
        else:
            logger.info("Using existing access token")

        # Determine target date (tomorrow by default)
        if target_date is None:
            target_date = datetime.now() + timedelta(days=1)

        logger.info(f"Attempting to book desk for: {target_date.strftime('%Y-%m-%d')}")

        # Check if already booked
        if self.check_existing_booking(target_date):
            logger.info("Already have a booking for this date. Skipping.")
            return True

        # Fetch availability
        desks = self.fetch_desk_availability(target_date)
        if not desks:
            logger.error("Could not fetch desk availability")
            return False

        # Find available desk
        desk = self.find_available_desk(desks)
        if not desk:
            logger.error("No available desks matching preferences")
            return False

        # Book the desk
        success = self.book_desk(desk['id'], target_date)

        if success:
            logger.info(f"SUCCESS: Booked desk {desk['name']} for {target_date.strftime('%Y-%m-%d')}")
        else:
            logger.error(f"FAILED: Could not book desk {desk['name']}")

        return success


def main():
    """Entry point."""
    import argparse

    parser = argparse.ArgumentParser(description='Hotdesk Booking Automation')
    parser.add_argument('--date', type=str, help='Target date (YYYY-MM-DD), default: tomorrow')
    parser.add_argument('--init-token', type=str, help='Initialize with refresh token')
    args = parser.parse_args()

    booker = HotdeskBooker()

    # Handle token initialization
    if args.init_token:
        booker.refresh_token = args.init_token
        if booker.refresh_access_token():
            logger.info("Token initialized successfully!")
            sys.exit(0)
        else:
            logger.error("Failed to initialize token")
            sys.exit(1)

    # Parse target date
    target_date = None
    if args.date:
        try:
            target_date = datetime.strptime(args.date, '%Y-%m-%d')
        except ValueError:
            logger.error(f"Invalid date format: {args.date}. Use YYYY-MM-DD")
            sys.exit(1)

    # Run booking
    success = booker.run(target_date)
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
