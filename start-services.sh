#!/bin/bash
# Hotdesk Booker - Start all services
# This script ensures Docker container and ngrok are running

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_DIR/startup.log"
}

log "Starting Hotdesk Booker services..."

# Wait for Docker to be ready
wait_for_docker() {
    local max_attempts=30
    local attempt=1

    while ! docker info > /dev/null 2>&1; do
        if [ $attempt -ge $max_attempts ]; then
            log "ERROR: Docker not available after $max_attempts attempts"
            return 1
        fi
        log "Waiting for Docker... (attempt $attempt/$max_attempts)"
        sleep 2
        ((attempt++))
    done
    log "Docker is ready"
    return 0
}

# Start Docker container
start_container() {
    cd "$SCRIPT_DIR"

    # Check if container exists and is running
    if docker ps --format '{{.Names}}' | grep -q '^hotdesk-booker$'; then
        log "Container already running"
        return 0
    fi

    # Check if container exists but stopped
    if docker ps -a --format '{{.Names}}' | grep -q '^hotdesk-booker$'; then
        log "Starting existing container..."
        docker start hotdesk-booker
    else
        log "Creating and starting container..."
        docker-compose up -d --build
    fi

    # Wait for container to be healthy
    local max_wait=30
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -s http://localhost:5000/api/config > /dev/null 2>&1; then
            log "Container is healthy"
            return 0
        fi
        sleep 1
        ((waited++))
    done

    log "WARNING: Container may not be fully ready"
    return 0
}

# Sync tokens from Chrome before starting
sync_tokens() {
    log "Syncing tokens from Chrome..."
    cd "$SCRIPT_DIR"

    # Use the local Python environment if available
    if [ -d "$SCRIPT_DIR/venv" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
    fi

    python3 "$SCRIPT_DIR/chrome_token_sync.py" 2>&1 | while read line; do
        log "TokenSync: $line"
    done

    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        log "Token sync successful"
        return 0
    else
        log "WARNING: Token sync failed - may need to re-authenticate"
        return 1
    fi
}

# Start token keeper background service
start_token_keeper() {
    # Kill any existing token keeper
    pkill -f "token_keeper.py" 2>/dev/null
    sleep 1

    log "Starting Token Keeper service..."
    cd "$SCRIPT_DIR"

    if [ -d "$SCRIPT_DIR/venv" ]; then
        source "$SCRIPT_DIR/venv/bin/activate"
    fi

    nohup python3 "$SCRIPT_DIR/token_keeper.py" --interval 60 > "$LOG_DIR/token_keeper.log" 2>&1 &
    log "Token Keeper started (PID: $!)"
}

# Start ngrok
start_ngrok() {
    # Kill any existing ngrok
    pkill -f "ngrok http 5000" 2>/dev/null
    sleep 1

    log "Starting ngrok tunnel..."
    nohup /opt/homebrew/bin/ngrok http 5000 > "$LOG_DIR/ngrok.log" 2>&1 &

    # Wait for tunnel to be established
    sleep 5

    # Get and log the public URL
    local url=$(curl -s http://localhost:4040/api/tunnels 2>/dev/null | python3 -c "import json,sys; d=json.load(sys.stdin); print(d['tunnels'][0]['public_url'] if d.get('tunnels') else '')" 2>/dev/null)

    if [ -n "$url" ]; then
        log "Tunnel established: $url"
        echo "$url" > "$SCRIPT_DIR/data/ngrok_url.txt"
        return 0
    else
        log "WARNING: Could not get tunnel URL"
        return 1
    fi
}

# Main
sync_tokens  # Try to sync tokens first (non-fatal if fails)
wait_for_docker || exit 1
start_container || exit 1
start_ngrok
start_token_keeper  # Start background token keeper

log "All services started successfully"
