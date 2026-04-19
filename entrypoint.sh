#!/bin/bash
set -e

# Hotdesk Booker Entrypoint
# Runs the web UI and scheduler

MODE=${MODE:-web}  # web, scheduler, or both

echo "=== Hotdesk Booker ==="
echo "Mode: ${MODE}"
echo "Timezone: $(cat /etc/timezone)"
echo "Current time: $(date)"
echo "======================"

# Function to run the booking
run_booking() {
    echo "[$(date)] Running booking script..."
    cd /app
    python3 booker.py
    echo "[$(date)] Booking script completed"
}

# Function to run scheduler
run_scheduler() {
    SCHEDULE_HOUR=${SCHEDULE_HOUR:-0}
    SCHEDULE_MINUTE=${SCHEDULE_MINUTE:-1}
    echo "Scheduler: Running at ${SCHEDULE_HOUR}:${SCHEDULE_MINUTE} daily"

    while true; do
        CURRENT_HOUR=$(date +%H)
        CURRENT_MINUTE=$(date +%M)

        if [ "$CURRENT_HOUR" -eq "$SCHEDULE_HOUR" ] && [ "$CURRENT_MINUTE" -eq "$SCHEDULE_MINUTE" ]; then
            run_booking
            sleep 60
        fi
        sleep 30
    done
}

# Function to run web UI
run_web() {
    echo "Starting web UI on port 5000..."
    cd /app
    exec gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 app:app
}

# If RUN_ONCE is set, just run the booking and exit
if [ "${RUN_ONCE}" = "true" ]; then
    run_booking
    exit $?
fi

case "$MODE" in
    web)
        run_web
        ;;
    scheduler)
        run_scheduler
        ;;
    both)
        # Run scheduler in background, web in foreground
        run_scheduler &
        run_web
        ;;
    *)
        echo "Unknown mode: $MODE"
        exit 1
        ;;
esac
