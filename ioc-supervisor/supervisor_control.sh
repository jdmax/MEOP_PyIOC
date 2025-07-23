#!/bin/bash
# Helper script to manage the screen-based supervisor system

cd "$(dirname "$0")"

# Source the virtual environment from parent directory
source ../venv/bin/activate

SUPERVISOR_CONFIG="supervisord.conf"
SCREEN_NAME="ioc-supervisor"

case "$1" in
    start)
        echo "Starting supervisor IOC manager in foreground..."
        ./start_supervisor_manager.sh
        ;;

    start-daemon)
        echo "Starting supervisor IOC manager in screen session..."
        ./start_supervisor_manager.sh --daemon
        ;;

    stop)
        echo "Stopping supervisor system..."

        # Stop the screen session
        ./start_supervisor_manager.sh --stop-daemon

        # Also stop supervisord if it's running
        if [ -f "$SUPERVISOR_CONFIG" ]; then
            echo "Stopping all IOCs..."
            supervisorctl -c "$SUPERVISOR_CONFIG" stop all 2>/dev/null
            echo "Stopping supervisord..."
            supervisorctl -c "$SUPERVISOR_CONFIG" shutdown 2>/dev/null
        fi

        # Clean up any remaining files
        rm -f supervisor.sock supervisord.pid

        echo "Supervisor system stopped"
        ;;

    restart)
        echo "Restarting supervisor system..."
        $0 stop
        sleep 2
        $0 start-daemon
        ;;

    status)
        echo "=== Screen Session Status ==="
        if screen -list | grep -q "$SCREEN_NAME"; then
            echo "Screen session '$SCREEN_NAME' is running"
            echo "Attach with: $0 attach"
        else
            echo "Screen session '$SCREEN_NAME' is not running"
        fi

        echo ""
        echo "=== Supervisord Status ==="
        if [ -f "$SUPERVISOR_CONFIG" ]; then
            supervisorctl -c "$SUPERVISOR_CONFIG" status 2>/dev/null || echo "Supervisord not responding"
        else
            echo "Supervisor not configured"
        fi

        echo ""
        echo "=== Process Status ==="
        echo "Screen sessions:"
        screen -list | grep "$SCREEN_NAME" || echo "  No IOC supervisor screen sessions"
        echo ""
        echo "Python processes:"
        ps aux | grep "[p]ython.*ioc_manager" || echo "  No ioc_manager processes found"
        ;;

    attach)
        echo "Attaching to screen session..."
        ./start_supervisor_manager.sh --attach
        ;;

    logs)
        if [ -n "$2" ]; then
            # Show logs for specific IOC or manager
            if [ "$2" = "manager" ]; then
                echo "=== Supervisor Manager Log ==="
                tail -f "logs/supervisor_manager.log"
            elif [ "$2" = "screen" ]; then
                echo "=== Screen Session Log (same as manager) ==="
                tail -f "logs/supervisor_manager.log"
            else
                echo "=== IOC Log: $2 ==="
                if [ -f "logs/$2.log" ]; then
                    tail -f "logs/$2.log"
                else
                    echo "Log file logs/$2.log not found"
                    echo "Available logs:"
                    ls -la logs/ 2>/dev/null || echo "No logs directory"
                fi
            fi
        else
            echo "Available log files:"
            ls -la logs/ 2>/dev/null || echo "No logs directory found"
            echo ""
            echo "Usage: $0 logs {manager|screen|ioc_name}"
            echo "  manager  - Supervisor manager log"
            echo "  screen   - Screen session log (same as manager)"
            echo "  ioc_name - Specific IOC log"
        fi
        ;;

    screen-list)
        echo "All screen sessions:"
        screen -list
        ;;

    clean)
        echo "Cleaning supervisor files..."
        $0 stop
        rm -f supervisord.conf supervisor.sock supervisord.pid
        echo "Cleaning log files..."
        rm -rf logs/*
        echo "Cleaned supervisor files and logs"
        ;;

    *)
        echo "Usage: $0 {start|start-daemon|stop|restart|status|attach|logs [manager|screen|ioc_name]|install-service|screen-list|clean}"
        echo ""
        echo "Screen-based IOC Supervisor Control:"
        echo "  start         - Start in foreground (for testing)"
        echo "  start-daemon  - Start in background screen session"
        echo "  stop          - Stop screen session and all IOCs"
        echo "  restart       - Restart in background screen session"
        echo "  status        - Show status of screen session and IOCs"
        echo "  attach        - Attach to the background screen session"
        echo "  logs          - Show available logs or tail specific log"
        echo "  screen-list   - List all screen sessions"
        echo "  clean         - Clean all supervisor files and logs"
        echo ""
        echo "Tips:"
        echo "  - Use 'attach' to see the live IOC manager output"
        echo "  - In screen session, press Ctrl-A, D to detach"
        echo "  - Use 'logs manager' to see logged output"
        exit 1
        ;;
esac