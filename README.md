# Hotdesk Booking Automation

Automatically books a desk at hotdesk.speednet.pl every day at 00:01.

## Quick Start

### 1. Verify your refresh token is configured

The token is already set up in `data/tokens.json`. If you need to update it:

```bash
# Get your refresh token from browser DevTools:
# 1. Go to https://hotdesk.speednet.pl
# 2. Open DevTools > Network
# 3. Look for /auth/refresh request
# 4. Copy the refreshToken from request payload

# Update data/tokens.json with your token
```

### 2. Test the booking script locally

```bash
cd ~/hotdesk-booker

# Install requests
pip3 install requests

# Test run (books for tomorrow)
python3 booker.py

# Book for specific date
python3 booker.py --date 2026-04-20
```

### 3. Run with Docker

```bash
cd ~/hotdesk-booker

# Build and start (simple mode - built-in scheduler)
docker-compose -f docker-compose.simple.yml up -d --build

# View logs
docker logs -f hotdesk-booker

# Stop
docker-compose -f docker-compose.simple.yml down
```

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `PREFERRED_DESKS` | `S05,S15,S10,S14` | Comma-separated desk names in priority order |
| `BOOKING_SUBJECT` | `Tim codziennie w biurze` | Subject line for booking |
| `SCHEDULE_HOUR` | `0` | Hour to run (0-23) |
| `SCHEDULE_MINUTE` | `1` | Minute to run (0-59) |
| `TZ` | `Europe/Warsaw` | Timezone |
| `RUN_ONCE` | `false` | Set to `true` for single execution |

### Desk Priority

The script tries to book desks in this order:
1. First, tries each desk in `PREFERRED_DESKS`
2. If all preferred desks are taken, falls back to any available `S*` desk

Your current preference: **S05 → S15 → S10 → S14**

## Files

```
hotdesk-booker/
├── booker.py              # Main booking script
├── Dockerfile             # Container definition
├── docker-compose.yml     # Full config with ofelia scheduler
├── docker-compose.simple.yml  # Simple config with built-in scheduler
├── entrypoint.sh          # Container entrypoint
├── data/
│   └── tokens.json        # Your auth tokens (gitignored)
└── logs/
    └── booker.log         # Booking logs
```

## Troubleshooting

### Token expired
If you see "Failed to refresh token", your refresh token may have expired. Get a new one:
1. Log in to https://hotdesk.speednet.pl
2. Open DevTools > Network
3. Trigger any action or refresh the page
4. Find the `/auth/refresh` request
5. Copy the `refreshToken` from the response
6. Update `data/tokens.json`

### No available desks
The script only books desks marked as `allowed: true` for your user.
Currently, you're allowed to book `S*` desks (S01-S18).

### Logs
Check `logs/booker.log` or run:
```bash
docker logs hotdesk-booker
```

## Manual Booking

Test the API directly:

```bash
# Refresh token
curl -X POST https://hotdesk.speednet.pl/auth/refresh \
  -H "Content-Type: application/json" \
  -d '{"refreshToken": "YOUR_REFRESH_TOKEN"}'

# Check availability
curl "https://hotdesk.speednet.pl/location/8f78f4e5-1cd6-40b7-a91e-34cab6768732/space/availability?enter=2026-04-20T00:00:00.000Z&leave=2026-04-20T23:59:59.000Z" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```
