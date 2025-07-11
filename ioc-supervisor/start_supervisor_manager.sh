#!/bin/bash
# ioc-supervisor/start_supervisor_manager.sh

# Change to the script directory
cd "$(dirname "$0")"

# Source the virtual environment from parent directory
source ../venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

echo "Starting Supervisor IOC Manager..."
python supervisor_ioc_manager.py