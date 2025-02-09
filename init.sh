#!/usr/bin/env bash

# Exit on error, unset variables, and pipe failures
set -euo pipefail
# Trap errors and print line number
trap 'echo "Error on line $LINENO"' ERR

# Get script directory and change to it
cd "$(dirname "${BASH_SOURCE[0]}")"

# Ensure uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Start the bot with unbuffered output
echo "Starting TooGoodToGo Bot..."
uv run bot.py
