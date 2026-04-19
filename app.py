#!/usr/bin/env python3
"""
Hotdesk Booker Web UI
A mobile-friendly web interface for managing hotdesk bookings
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional
from flask import Flask, render_template, jsonify, request, redirect, url_for
from flask_cors import CORS
import requests

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Configuration
BASE_URL = "https://hotdesk.speednet.pl"
LOCATION_ID = "8f78f4e5-1cd6-40b7-a91e-34cab6768732"
DATA_DIR = os.environ.get("DATA_DIR", "./data")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")
TOKEN_FILE = os.path.join(DATA_DIR, "tokens.json")


def load_config():
    """Load configuration from file."""
    defaults = {
        "preferred_desks": ["S05", "S15", "S10", "S14"],
        "booking_subject": "Tim codziennie w biurze",
        "schedule_hour": 0,
        "schedule_minute": 1,
        "schedule_days": [1, 2, 3, 4, 5],  # Monday to Friday
        "auto_book_enabled": True
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                config = json.load(f)
                return {**defaults, **config}
    except Exception as e:
        logger.error(f"Failed to load config: {e}")
    return defaults


def save_config(config):
    """Save configuration to file."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(config, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save config: {e}")
        return False


def load_tokens():
    """Load tokens from file."""
    try:
        if os.path.exists(TOKEN_FILE):
            with open(TOKEN_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load tokens: {e}")
    return {}


def save_tokens(tokens):
    """Save tokens to file."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        tokens['updated_at'] = datetime.now().isoformat()
        with open(TOKEN_FILE, 'w') as f:
            json.dump(tokens, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Failed to save tokens: {e}")
        return False


def get_access_token():
    """Get current access token, refreshing if needed."""
    tokens = load_tokens()
    return tokens.get('access_token')


def refresh_access_token():
    """Refresh the access token using stored refresh token."""
    tokens = load_tokens()
    refresh_token = tokens.get('refresh_token')

    if not refresh_token:
        logger.warning("No refresh token stored, trying Chrome sync...")
        return sync_from_chrome()

    try:
        response = requests.post(
            f"{BASE_URL}/auth/refresh",
            json={"refreshToken": refresh_token},
            headers={"Content-Type": "application/json"},
            timeout=30
        )

        if response.status_code == 200:
            data = response.json()
            tokens['access_token'] = data.get('accessToken')
            if data.get('refreshToken'):
                tokens['refresh_token'] = data.get('refreshToken')
            save_tokens(tokens)
            logger.info("Token refreshed successfully")
            return tokens['access_token']
        else:
            logger.warning(f"Refresh failed (status {response.status_code}), trying Chrome sync...")
            return sync_from_chrome()
    except Exception as e:
        logger.error(f"Token refresh error: {e}")
        return sync_from_chrome()


def sync_from_chrome():
    """Try to sync tokens from Chrome localStorage as fallback."""
    try:
        from chrome_token_sync import sync_tokens, load_tokens as load_sync_tokens
        if sync_tokens():
            tokens = load_sync_tokens()
            return tokens.get('access_token')
    except ImportError:
        logger.warning("chrome_token_sync module not available")
    except Exception as e:
        logger.error(f"Chrome sync error: {e}")
    return None


def api_request(method, endpoint, **kwargs):
    """Make authenticated API request."""
    access_token = get_access_token()

    headers = kwargs.pop('headers', {})
    headers['Authorization'] = f"Bearer {access_token}"
    headers['Content-Type'] = 'application/json'

    url = f"{BASE_URL}{endpoint}"
    response = requests.request(method, url, headers=headers, **kwargs)

    # Try refresh if unauthorized
    if response.status_code == 401:
        new_token = refresh_access_token()
        if new_token:
            headers['Authorization'] = f"Bearer {new_token}"
            response = requests.request(method, url, headers=headers, **kwargs)

    return response


# ============== API Routes ==============

@app.route('/api/config', methods=['GET'])
def get_config():
    """Get current configuration."""
    return jsonify(load_config())


@app.route('/api/config', methods=['POST'])
def update_config():
    """Update configuration."""
    config = load_config()
    data = request.json

    if 'preferred_desks' in data:
        config['preferred_desks'] = data['preferred_desks']
    if 'booking_subject' in data:
        config['booking_subject'] = data['booking_subject']
    if 'schedule_hour' in data:
        config['schedule_hour'] = int(data['schedule_hour'])
    if 'schedule_minute' in data:
        config['schedule_minute'] = int(data['schedule_minute'])
    if 'schedule_days' in data:
        config['schedule_days'] = data['schedule_days']
    if 'auto_book_enabled' in data:
        config['auto_book_enabled'] = data['auto_book_enabled']

    if save_config(config):
        return jsonify({"success": True, "config": config})
    return jsonify({"success": False, "error": "Failed to save config"}), 500


@app.route('/api/auth/status', methods=['GET'])
def auth_status():
    """Check authentication status."""
    tokens = load_tokens()
    access_token = tokens.get('access_token')

    if not access_token:
        return jsonify({"authenticated": False})

    # Try to get bookings to verify token works
    response = api_request('GET', '/booking/')

    if response.status_code == 200:
        # Extract user info from JWT token
        user_data = {}
        try:
            import base64
            # Decode JWT payload (middle part)
            payload = access_token.split('.')[1]
            # Add padding if needed
            payload += '=' * (4 - len(payload) % 4)
            decoded = base64.b64decode(payload)
            import json
            user_data = json.loads(decoded)
        except Exception as e:
            logger.warning(f"Could not decode JWT: {e}")

        return jsonify({
            "authenticated": True,
            "user": {
                "id": user_data.get('userID'),
                "email": user_data.get('email'),
                "role": user_data.get('role')
            },
            "token_updated": tokens.get('updated_at')
        })

    return jsonify({"authenticated": False})


@app.route('/api/auth/tokens', methods=['POST'])
def set_tokens():
    """Set authentication tokens manually."""
    data = request.json
    tokens = load_tokens()

    if 'access_token' in data:
        tokens['access_token'] = data['access_token']
    if 'refresh_token' in data:
        tokens['refresh_token'] = data['refresh_token']

    if save_tokens(tokens):
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Failed to save tokens"}), 500


@app.route('/api/auth/refresh', methods=['POST'])
def do_refresh():
    """Force token refresh."""
    new_token = refresh_access_token()
    if new_token:
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Failed to refresh token"}), 401


@app.route('/api/auth/sync', methods=['POST'])
def do_sync():
    """Sync tokens from Chrome localStorage."""
    try:
        from chrome_token_sync import sync_tokens
        if sync_tokens():
            return jsonify({"success": True, "message": "Tokens synced from Chrome"})
        return jsonify({"success": False, "error": "Sync failed - please log in to Chrome"}), 401
    except ImportError:
        return jsonify({"success": False, "error": "Chrome sync not available"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route('/api/auth/token-info', methods=['GET'])
def token_info():
    """Get detailed token information including expiration."""
    tokens = load_tokens()
    access_token = tokens.get('access_token')
    refresh_token = tokens.get('refresh_token')

    info = {
        "has_access_token": bool(access_token),
        "has_refresh_token": bool(refresh_token),
        "updated_at": tokens.get('updated_at')
    }

    if access_token:
        try:
            import base64
            payload = access_token.split('.')[1]
            payload += '=' * (4 - len(payload) % 4)
            decoded = json.loads(base64.b64decode(payload))

            exp = decoded.get('exp', 0)
            exp_dt = datetime.fromtimestamp(exp)
            now = datetime.now()

            info['expires_at'] = exp_dt.isoformat()
            info['expires_in_seconds'] = int((exp_dt - now).total_seconds())
            info['is_expired'] = now > exp_dt
            info['email'] = decoded.get('email')
        except Exception as e:
            logger.warning(f"Could not decode token: {e}")
            info['decode_error'] = str(e)

    return jsonify(info)


@app.route('/api/location', methods=['GET'])
def get_location():
    """Get location info including map."""
    response = api_request('GET', '/location/')
    if response.status_code == 200:
        locations = response.json()
        for loc in locations:
            if loc['id'] == LOCATION_ID:
                return jsonify(loc)
        if locations:
            return jsonify(locations[0])
    return jsonify({"error": "Failed to fetch location"}), 500


@app.route('/api/location/map', methods=['GET'])
def get_location_map():
    """Get location map image."""
    response = api_request('GET', f'/location/{LOCATION_ID}/map')
    if response.status_code == 200:
        from flask import Response
        import base64

        # API returns JSON with base64-encoded image
        try:
            data = response.json()
            img_data = base64.b64decode(data['data'])
            return Response(
                img_data,
                mimetype=f"image/{data.get('mimeType', 'png')}"
            )
        except:
            # Fallback to raw content
            return Response(
                response.content,
                mimetype=response.headers.get('content-type', 'image/png')
            )
    return jsonify({"error": "Failed to fetch map"}), 500


@app.route('/api/desks', methods=['GET'])
def get_desks():
    """Get desk availability for a specific date."""
    date_str = request.args.get('date', datetime.now().strftime('%Y-%m-%d'))

    try:
        date = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    enter = date.strftime("%Y-%m-%dT00:00:00.000Z")
    leave = date.strftime("%Y-%m-%dT23:59:59.000Z")

    response = api_request(
        'GET',
        f'/location/{LOCATION_ID}/space/availability',
        params={"enter": enter, "leave": leave}
    )

    if response.status_code == 200:
        desks = response.json()
        config = load_config()
        preferred = config.get('preferred_desks', [])

        # Add preference ranking
        for desk in desks:
            desk['preference_rank'] = preferred.index(desk['name']) if desk['name'] in preferred else 999

        return jsonify({
            "date": date_str,
            "desks": desks,
            "preferred_desks": preferred
        })

    return jsonify({"error": "Failed to fetch desks"}), 500


@app.route('/api/bookings', methods=['GET'])
def get_bookings():
    """Get user's bookings."""
    response = api_request('GET', '/booking/')

    if response.status_code == 200:
        return jsonify(response.json())

    return jsonify({"error": "Failed to fetch bookings"}), 500


@app.route('/api/bookings', methods=['POST'])
def create_booking():
    """Create a new booking."""
    data = request.json

    if not data.get('spaceId') or not data.get('date'):
        return jsonify({"error": "Missing spaceId or date"}), 400

    try:
        date = datetime.strptime(data['date'], '%Y-%m-%d')
    except ValueError:
        return jsonify({"error": "Invalid date format"}), 400

    config = load_config()

    payload = {
        "enter": date.strftime("%Y-%m-%dT00:00:00.000Z"),
        "leave": date.strftime("%Y-%m-%dT23:59:59.000Z"),
        "spaceId": data['spaceId'],
        "subject": data.get('subject', config.get('booking_subject', '')),
        "userEmail": ""
    }

    response = api_request('POST', '/booking/', json=payload)

    if response.status_code == 201:
        return jsonify({"success": True, "booking": response.json()})

    error_msg = "Failed to create booking"
    try:
        error_data = response.json()
        error_msg = error_data.get('message', error_msg)
    except:
        pass

    return jsonify({"error": error_msg}), response.status_code


@app.route('/api/bookings/<booking_id>', methods=['DELETE'])
def delete_booking(booking_id):
    """Delete a booking."""
    response = api_request('DELETE', f'/booking/{booking_id}')

    if response.status_code in [200, 204]:
        return jsonify({"success": True})

    return jsonify({"error": "Failed to delete booking"}), response.status_code


@app.route('/api/book-now', methods=['POST'])
def book_now():
    """Trigger immediate booking for tomorrow."""
    from booker import HotdeskBooker

    os.environ['TOKEN_FILE'] = TOKEN_FILE
    config = load_config()
    os.environ['PREFERRED_DESKS'] = ','.join(config.get('preferred_desks', []))
    os.environ['BOOKING_SUBJECT'] = config.get('booking_subject', '')

    booker = HotdeskBooker()
    success = booker.run()

    return jsonify({"success": success})


# ============== Web Routes ==============

@app.route('/')
def index():
    """Main page."""
    return render_template('index.html')


@app.route('/settings')
def settings():
    """Settings page."""
    return render_template('settings.html')


@app.route('/auth')
def auth():
    """Auth page."""
    return render_template('auth.html')


@app.route('/auth/extract')
def auth_extract():
    """Token extraction helper page."""
    return render_template('extract.html')


if __name__ == '__main__':
    os.makedirs(DATA_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=os.environ.get('DEBUG', False))
