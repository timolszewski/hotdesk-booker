# Hotdesk Auto-Booker

Automatically books your preferred desk at hotdesk.speednet.pl every day at 00:01 Warsaw time using GitHub Actions.

## Features

- Books desk for next workday (Mon-Fri) automatically
- Configurable desk preferences (tries in order until one is available)
- Automatic token rotation - no manual token refresh needed
- Skips weekends but keeps auth token alive
- Skips if you already have a booking

## Setup (5 minutes)

### 1. Create your own copy

Click **"Use this template"** → **"Create a new repository"** (make it **private**)

Or fork this repo.

### 2. Get your refresh token

1. Open https://hotdesk.speednet.pl in Chrome and **log in**
2. Open DevTools (F12) → **Application** → **Local Storage** → `https://hotdesk.speednet.pl`
3. Copy the value of `refreshToken` (looks like `xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)

### 3. Configure GitHub secret

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **"New repository secret"**
3. Name: `HOTDESK_REFRESH_TOKEN`
4. Value: paste your refresh token
5. Click **"Add secret"**

### 4. Customize your preferences

Edit `.github/workflows/daily-booking.yml`:

```yaml
env:
  PREFERRED_DESKS: S05,S15,S10,S14  # Change to your preferred desks in priority order
  BOOKING_SUBJECT: "Your name here"  # Change to your booking description
```

Commit and push your changes.

### 5. Test it

1. Go to **Actions** → **"Daily Hotdesk Booking"**
2. Click **"Run workflow"** → Check **"Dry run"** → **"Run workflow"**
3. Check the logs to verify it works

Then run again **without** dry run to actually book.

## How it works

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions (runs daily at 00:01 Warsaw time)           │
├─────────────────────────────────────────────────────────────┤
│  1. Use refresh token to get access token                   │
│  2. Check if tomorrow is weekend → skip if yes              │
│  3. Check if already have booking → skip if yes             │
│  4. Find first available preferred desk                     │
│  5. Book it!                                                │
│  6. Save new rotated refresh token back to repo             │
└─────────────────────────────────────────────────────────────┘
```

The token chain stays alive as long as the workflow runs daily (it runs every day, including weekends, to keep the token fresh).

## Troubleshooting

### Token refresh failed (404)

Your refresh token expired or was already used. This happens if:
- You logged in elsewhere and the token rotated
- The workflow didn't run for several days

**Fix:** Log in to hotdesk.speednet.pl again and update the `HOTDESK_REFRESH_TOKEN` secret with the new token.

### No desks available

All desks are booked for tomorrow. Not an error - the workflow will try again next day.

### Workflow not running

GitHub disables scheduled workflows on inactive repos. Push a commit or manually trigger the workflow to re-enable.

## Available desks

The Speednet office has these desks:
- `S01` - `S18` (standard desks)

Check the floor plan at https://hotdesk.speednet.pl to pick your favorites.

## Local development

```bash
# Clone your repo
git clone git@github.com:YOUR_USERNAME/hotdesk-booker.git
cd hotdesk-booker

# Install dependencies
pip install requests

# Set up token (after logging into hotdesk in Chrome)
python3 chrome_token_sync.py

# Test booking script
REFRESH_TOKEN=$(cat data/tokens.json | python3 -c "import sys,json; print(json.load(sys.stdin)['refresh_token'])") \
DRY_RUN=true \
python3 .github/scripts/book_desk.py
```
