#!/bin/bash
# ioc-supervisor/start_supervisor_manager.sh

# Change to the script directory
cd "$(dirname "$0")"

# Source the virtual environment from parent directory
source ../venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

# Check for daemon flag
if [ "$1" = "--daemon" ] || [ "$1" = "-d" ]; then
    echo "Starting Supervisor IOC Manager as daemon..."
    nohup python supervisor_ioc_manager.py > logs/supervisor_manager.log 2>&1 &
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
    python supervisor_ioc_manager.py
fi