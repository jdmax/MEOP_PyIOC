#!/bin/bash

# Change to the script directory
cd "$(dirname "$0")"

# Source the virtual environment from parent directory
source ../venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

# Load settings to get EPICS configuration
SETTINGS_FILE="../settings.yaml"

# Extract EPICS_CA_ADDR_LIST from settings.yaml
EPICS_CA_ADDR_LIST=$(python3 -c "
import yaml
with open('$SETTINGS_FILE') as f:
    settings = yaml.safe_load(f)
    print(settings['general']['epics_addr_list'])
" 2>/dev/null || echo "127.255.255.255")

# Set up EPICS environment variables for daemon mode
export EPICS_CA_ADDR_LIST="$EPICS_CA_ADDR_LIST"
export EPICS_CA_AUTO_ADDR_LIST="NO"
export EPICS_CA_SERVER_PORT="5064"
export EPICS_CA_REPEATER_PORT="5065"
export EPICS_CA_MAX_ARRAY_BYTES="16384"

# Check for daemon flag
if [ "$1" = "--daemon" ] || [ "$1" = "-d" ]; then
    echo "Starting Supervisor IOC Manager as daemon..."
    echo "EPICS_CA_ADDR_LIST: $EPICS_CA_ADDR_LIST"

    # Start with explicit environment preservation
    nohup env \
        EPICS_CA_ADDR_LIST="$EPICS_CA_ADDR_LIST" \
        EPICS_CA_AUTO_ADDR_LIST="NO" \
        EPICS_CA_SERVER_PORT="5064" \
        EPICS_CA_REPEATER_PORT="5065" \
        EPICS_CA_MAX_ARRAY_BYTES="16384" \
        python ioc_manager.py > logs/supervisor_manager.log 2>&1 &

    echo $! > supervisor_manager.pid
    echo "Started with PID $(cat supervisor_manager.pid)"
    echo "Log: $(pwd)/logs/supervisor_manager.log"

elif [ "$1" = "--stop-daemon" ]; then
    if [ -f supervisor_manager.pid ]; then
        PID=$(cat supervisor_manager.pid)
        echo "Stopping daemon with PID $PID..."
        kill $PID 2>/dev/null
        rm -f supervisor_manager.pid
        echo "Daemon stopped"
    else
        echo "No daemon PID file found"
    fi
else
    echo "Starting Supervisor IOC Manager in foreground..."
    echo "Use --daemon or -d to run as background daemon"
    echo "Use --stop-daemon to stop background daemon"
    echo "EPICS_CA_ADDR_LIST: $EPICS_CA_ADDR_LIST"
    python ioc_manager.py
fi