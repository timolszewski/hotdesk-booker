#!/usr/bin/env python3
"""
Hotdesk Booking Script for GitHub Actions

This script runs in GitHub Actions to book a desk for tomorrow.
It handles token refresh and automatic secret rotation.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# Configuration from environment
BASE_URL = os.environ.get('HOTDESK_BASE_URL', 'https://hotdesk.speednet.pl')
LOCATION_ID = os.environ.get('LOCATION_ID', '8f78f4e5-1cd6-40b7-a91e-34cab6768732')
PREFERRED_DESKS = os.environ.get('PREFERRED_DESKS', 'S05,S15,S10,S14').split(',')
BOOKING_SUBJECT = os.environ.get('BOOKING_SUBJECT', 'Tim codziennie w biurze')
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN')
DRY_RUN = os.environ.get('DRY_RUN', 'false').lower() == 'true'

# Fallback: try to read from committed file if env var token fails
TOKEN_FILE = '.github/data/refresh_token.txt'


def log(message: str):
    """Log with timestamp."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")


def refresh_access_token(refresh_token: str) -> tuple[str, str] | None:
    """
    Get new access token using refresh token.
    Returns (access_token, new_refresh_token) or None on failure.
    """
    log("Refreshing access token...")

    try:
        response = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refreshToken": refresh_token},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            access_token = data.get('accessToken')
            new_refresh_token = data.get('refreshToken')
            log(f"Token refresh successful")
            return access_token, new_refresh_token
        else:
            log(f"Token refresh failed: {response.status_code}")
            log(f"Response: {response.text[:200]}")
            return None

    except Exception as e:
        log(f"Token refresh error: {e}")
        return None


def get_available_desks(access_token: str, date: datetime) -> list:
    """Get available desks for a specific date."""
    enter = date.strftime("%Y-%m-%dT00:00:00.000Z")
    leave = date.strftime("%Y-%m-%dT23:59:59.000Z")

    log(f"Fetching desk availability for {date.strftime('%Y-%m-%d')}...")

    response = requests.get(
        f"{BASE_URL}/location/{LOCATION_ID}/space/availability",
        params={"enter": enter, "leave": leave},
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30
    )

    if response.status_code != 200:
        log(f"Failed to get desks: {response.status_code}")
        return []

    desks = response.json()
    available = [d for d in desks if d.get('available', False)]
    log(f"Found {len(available)} available desks out of {len(desks)} total")

    return available


def get_my_bookings(access_token: str) -> list:
    """Get current user's bookings."""
    response = requests.get(
        f"{BASE_URL}/booking/",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30
    )

    if response.status_code == 200:
        return response.json()
    return []


def book_desk(access_token: str, space_id: str, date: datetime) -> bool:
    """Book a specific desk for a date."""
    payload = {
        "enter": date.strftime("%Y-%m-%dT00:00:00.000Z"),
        "leave": date.strftime("%Y-%m-%dT23:59:59.000Z"),
        "spaceId": space_id,
        "subject": BOOKING_SUBJECT,
        "userEmail": ""
    }

    if DRY_RUN:
        log(f"DRY RUN: Would book desk with payload: {json.dumps(payload)}")
        return True

    response = requests.post(
        f"{BASE_URL}/booking/",
        json=payload,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        timeout=30
    )

    if response.status_code == 201:
        try:
            booking = response.json()
            log(f"Booking created successfully: {booking.get('id')}")
        except Exception:
            log("Booking created successfully (no response body)")
        return True
    else:
        log(f"Booking failed: {response.status_code}")
        log(f"Response: {response.text[:500]}")
        return False


def select_best_desk(available_desks: list) -> dict | None:
    """Select the best available desk based on preference order."""
    desk_map = {d['name']: d for d in available_desks}

    for preferred in PREFERRED_DESKS:
        if preferred in desk_map:
            log(f"Selected preferred desk: {preferred}")
            return desk_map[preferred]

    # If no preferred desk available, take any available
    if available_desks:
        desk = available_desks[0]
        log(f"No preferred desk available, selecting: {desk['name']}")
        return desk

    return None


def has_booking_for_date(bookings: list, date: datetime) -> bool:
    """Check if user already has a booking for the given date."""
    date_str = date.strftime("%Y-%m-%d")

    for booking in bookings:
        enter = booking.get('enter', '')
        if date_str in enter:
            log(f"Already have booking for {date_str}: {booking.get('space', {}).get('name', 'unknown')}")
            return True

    return False


def set_github_output(name: str, value: str):
    """Set GitHub Actions output variable."""
    github_output = os.environ.get('GITHUB_OUTPUT')
    if github_output:
        with open(github_output, 'a') as f:
            f.write(f"{name}={value}\n")
    # Also set as environment variable for subsequent steps
    github_env = os.environ.get('GITHUB_ENV')
    if github_env:
        with open(github_env, 'a') as f:
            f.write(f"{name}={value}\n")


def main():
    log("=" * 50)
    log("Hotdesk Booking Script")
    log("=" * 50)

    if DRY_RUN:
        log("*** DRY RUN MODE - No actual booking will be made ***")

    # Try to get refresh token from env or fallback to file
    refresh_token = REFRESH_TOKEN
    if not refresh_token and os.path.exists(TOKEN_FILE):
        log(f"Reading refresh token from {TOKEN_FILE}")
        with open(TOKEN_FILE) as f:
            refresh_token = f.read().strip()

    if not refresh_token:
        log("ERROR: REFRESH_TOKEN not set and no token file found")
        sys.exit(1)

    log(f"Base URL: {BASE_URL}")
    log(f"Location ID: {LOCATION_ID}")
    log(f"Preferred desks: {PREFERRED_DESKS}")

    # Step 1: Refresh token
    result = refresh_access_token(refresh_token)
    if not result:
        log("FATAL: Could not refresh access token")
        sys.exit(1)

    access_token, new_refresh_token = result

    # Export new refresh token for GitHub Action to update
    if new_refresh_token and new_refresh_token != refresh_token:
        log(f"Refresh token rotated: {new_refresh_token[:8]}...")
        set_github_output('NEW_REFRESH_TOKEN', new_refresh_token)

    # Step 2: Calculate tomorrow's date
    tomorrow = datetime.now(tz=None) + timedelta(days=1)
    log(f"Booking for: {tomorrow.strftime('%Y-%m-%d')} ({tomorrow.strftime('%A')})")

    # Step 3: Check if already booked
    bookings = get_my_bookings(access_token)
    if has_booking_for_date(bookings, tomorrow):
        log("Already have a booking for tomorrow - skipping")
        sys.exit(0)

    # Step 4: Get available desks
    available = get_available_desks(access_token, tomorrow)
    if not available:
        log("No desks available for tomorrow")
        sys.exit(1)

    # Step 5: Select best desk
    desk = select_best_desk(available)
    if not desk:
        log("Could not select a desk")
        sys.exit(1)

    log(f"Booking desk: {desk['name']} (ID: {desk['id']})")

    # Step 6: Make booking
    if book_desk(access_token, desk['id'], tomorrow):
        log("SUCCESS: Desk booked!")
        sys.exit(0)
    else:
        log("FAILED: Could not book desk")
        sys.exit(1)


if __name__ == "__main__":
    main()
