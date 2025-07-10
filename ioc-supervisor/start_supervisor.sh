#!/bin/bash

# Start supervisord for IOC management

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$SCRIPT_DIR/supervisord.conf"

# Create logs directory if it doesn't exist
mkdir -p "$SCRIPT_DIR/logs"

# Check if supervisord is already running
if pgrep -f "supervisord.*$CONFIG_FILE" > /dev/null; then
    echo "Supervisord is already running with this config"
    exit 1
fi

# Start supervisord
echo "Starting supervisord..."
supervisord -c "$CONFIG_FILE"

if [ $? -eq 0 ]; then
    echo "Supervisord started successfully"
    echo "Use 'supervisorctl -c $CONFIG_FILE' to interact with processes"
else
    echo "Failed to start supervisord"
    exit 1
fi