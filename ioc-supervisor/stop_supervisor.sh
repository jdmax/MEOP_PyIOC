#!/bin/bash

# Stop supervisord and all managed processes

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONFIG_FILE="$SCRIPT_DIR/supervisord.conf"

echo "Stopping all IOCs..."
supervisorctl -c "$CONFIG_FILE" stop all

echo "Shutting down supervisord..."
supervisorctl -c "$CONFIG_FILE" shutdown

echo "Supervisord stopped"