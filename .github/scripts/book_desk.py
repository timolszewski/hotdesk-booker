#!/usr/bin/env python3
"""
Hotdesk Booking Script for GitHub Actions
Books your preferred desk automatically every day.
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta

# Configuration from environment
BASE_URL = 'https://hotdesk.speednet.pl'
LOCATION_ID = '8f78f4e5-1cd6-40b7-a91e-34cab6768732'
PREFERRED_DESKS = os.environ.get('PREFERRED_DESKS', 'S05,S15,S10,S14').split(',')
BOOKING_SUBJECT = os.environ.get('BOOKING_SUBJECT', 'Auto-booking')
REFRESH_TOKEN = os.environ.get('REFRESH_TOKEN')


def log(message: str):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}")


def refresh_access_token(refresh_token: str) -> tuple[str, str] | None:
    """Get new access token using refresh token."""
    try:
        response = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refreshToken": refresh_token},
            headers={"Content-Type": "application/json"},
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            return data.get('accessToken'), data.get('refreshToken')
        log(f"Token refresh failed: {response.status_code}")
        return None
    except Exception as e:
        log(f"Error: {e}")
        return None


def get_available_desks(access_token: str, date: datetime) -> list:
    """Get available desks for a specific date."""
    response = requests.get(
        f"{BASE_URL}/location/{LOCATION_ID}/space/availability",
        params={
            "enter": date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "leave": date.strftime("%Y-%m-%dT23:59:59.000Z")
        },
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30
    )
    if response.status_code != 200:
        return []
    return [d for d in response.json() if d.get('available', False)]


def get_my_bookings(access_token: str) -> list:
    """Get current user's bookings."""
    response = requests.get(
        f"{BASE_URL}/booking/",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30
    )
    return response.json() if response.status_code == 200 else []


def book_desk(access_token: str, space_id: str, date: datetime) -> bool:
    """Book a specific desk."""
    response = requests.post(
        f"{BASE_URL}/booking/",
        json={
            "enter": date.strftime("%Y-%m-%dT00:00:00.000Z"),
            "leave": date.strftime("%Y-%m-%dT23:59:59.000Z"),
            "spaceId": space_id,
            "subject": BOOKING_SUBJECT,
            "userEmail": ""
        },
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        },
        timeout=30
    )
    return response.status_code == 201


def select_best_desk(available_desks: list) -> dict | None:
    """Select best available desk based on preferences."""
    desk_map = {d['name']: d for d in available_desks}
    for preferred in PREFERRED_DESKS:
        if preferred in desk_map:
            return desk_map[preferred]
    return available_desks[0] if available_desks else None


def has_booking_for_date(bookings: list, date: datetime) -> bool:
    """Check if already booked for date."""
    date_str = date.strftime("%Y-%m-%d")
    return any(date_str in b.get('enter', '') for b in bookings)


def set_output(name: str, value: str):
    """Set GitHub Actions output."""
    output_file = os.environ.get('GITHUB_OUTPUT')
    if output_file:
        with open(output_file, 'a') as f:
            f.write(f"{name}={value}\n")
    # Also set as env for next steps
    env_file = os.environ.get('GITHUB_ENV')
    if env_file:
        with open(env_file, 'a') as f:
            f.write(f"{name}={value}\n")


def main():
    log("=== Hotdesk Auto-Booker ===")

    if not REFRESH_TOKEN:
        log("ERROR: REFRESH_TOKEN not set")
        sys.exit(1)

    # Refresh token
    result = refresh_access_token(REFRESH_TOKEN)
    if not result:
        log("ERROR: Could not refresh token - may need to re-login")
        sys.exit(1)

    access_token, new_refresh_token = result
    log("Token refreshed OK")

    # Save new token for GitHub to commit
    if new_refresh_token and new_refresh_token != REFRESH_TOKEN:
        set_output('NEW_REFRESH_TOKEN', new_refresh_token)

    # Tomorrow's date
    tomorrow = datetime.now() + timedelta(days=1)
    day_name = ['Pon', 'Wt', 'Sr', 'Czw', 'Pt', 'Sob', 'Nd'][tomorrow.weekday()]
    log(f"Data: {tomorrow.strftime('%Y-%m-%d')} ({day_name})")

    # Skip weekends
    if tomorrow.weekday() >= 5:
        log("Weekend - pomijam rezerwację")
        sys.exit(0)

    # Check existing booking
    bookings = get_my_bookings(access_token)
    if has_booking_for_date(bookings, tomorrow):
        log("Już masz rezerwację na jutro")
        sys.exit(0)

    # Find available desks
    available = get_available_desks(access_token, tomorrow)
    log(f"Dostępnych biurek: {len(available)}")

    if not available:
        log("Brak wolnych biurek")
        sys.exit(0)

    # Select and book
    desk = select_best_desk(available)
    if not desk:
        log("Nie można wybrać biurka")
        sys.exit(1)

    log(f"Rezerwuję: {desk['name']}")

    if book_desk(access_token, desk['id'], tomorrow):
        log(f"✅ SUKCES! Zarezerwowano {desk['name']}")
    else:
        log(f"❌ Nie udało się zarezerwować")
        sys.exit(1)


if __name__ == "__main__":
    main()
