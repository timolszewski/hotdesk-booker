#!/bin/bash
# Local test script for hotdesk booker

cd "$(dirname "$0")"

# Activate venv if exists, otherwise create it
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    source venv/bin/activate
    pip install requests
else
    source venv/bin/activate
fi

# Run the booker
TOKEN_FILE=./data/tokens.json python3 booker.py "$@"
