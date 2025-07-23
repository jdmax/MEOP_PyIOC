#!/bin/bash

# Change to the script directory
cd "$(dirname "$0")"

# Source the virtual environment from parent directory
source ../venv/bin/activate

# Create logs directory if it doesn't exist
mkdir -p logs

SCREEN_NAME="ioc-supervisor"

case "$1" in
    --daemon|-d)
        echo "Starting Supervisor IOC Manager in screen session..."

        # Check if screen session already exists
        if screen -list | grep -q "$SCREEN_NAME"; then
            echo "Screen session '$SCREEN_NAME' already exists"
            echo "Use --stop-daemon to stop it first"
            exit 1
        fi

        # Start in screen session with logging
        screen -dmS "$SCREEN_NAME" bash -c "
            source ../venv/bin/activate
            echo 'Starting IOC Manager in screen session at \$(date)' | tee logs/supervisor_manager.log
            python ioc_manager.py 2>&1 | tee -a logs/supervisor_manager.log
        "

        echo "Started in screen session '$SCREEN_NAME'"
        echo "View with: screen -r $SCREEN_NAME"
        echo "Detach with: Ctrl-A, D"
        echo "Log: $(pwd)/logs/supervisor_manager.log"

        # Wait a moment and check if the session is running
        sleep 2
        if screen -list | grep -q "$SCREEN_NAME"; then
            echo "Screen session is running successfully"
        else
            echo "Warning: Screen session may have failed to start"
        fi
        ;;

    --stop-daemon)
        echo "Stopping screen session '$SCREEN_NAME'..."
        if screen -list | grep -q "$SCREEN_NAME"; then
            screen -S "$SCREEN_NAME" -X quit
            echo "Screen session stopped"
        else
            echo "No screen session '$SCREEN_NAME' found"
        fi
        ;;

    --attach)
        echo "Attaching to screen session '$SCREEN_NAME'..."
        if screen -list | grep -q "$SCREEN_NAME"; then
            screen -r "$SCREEN_NAME"
        else
            echo "No screen session '$SCREEN_NAME' found"
            echo "Start one with: $0 --daemon"
        fi
        ;;

    --status)
        echo "Screen sessions:"
        screen -list | grep "$SCREEN_NAME" || echo "No IOC supervisor screen session found"
        ;;

    *)
        echo "Starting Supervisor IOC Manager in foreground..."
        echo ""
        echo "Options:"
        echo "  --daemon      Start in background screen session"
        echo "  --stop-daemon Stop background screen session"
        echo "  --attach      Attach to background session"
        echo "  --status      Show screen session status"
        echo ""
        python ioc_manager.py
        ;;
esac