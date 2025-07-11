#!/bin/bash
# ioc-supervisor/supervisor_control.sh
# Helper script to manage the supervisor system

cd "$(dirname "$0")"

SUPERVISOR_CONFIG="supervisord.conf"
SUPERVISOR_PID="supervisord.pid"

case "$1" in
    start)
        echo "Starting supervisor IOC manager..."
        ./start_supervisor_manager.sh
        ;;

    stop)
        echo "Stopping all IOCs and supervisor..."
        if [ -f "$SUPERVISOR_CONFIG" ]; then
            supervisorctl -c "$SUPERVISOR_CONFIG" stop all
            supervisorctl -c "$SUPERVISOR_CONFIG" shutdown
        fi

        # Kill any remaining processes
        if [ -f "$SUPERVISOR_PID" ]; then
            kill -TERM $(cat "$SUPERVISOR_PID") 2>/dev/null || true
            rm -f "$SUPERVISOR_PID"
        fi

        # Clean up socket
        rm -f supervisor.sock
        echo "Supervisor system stopped"
        ;;

    restart)
        echo "Restarting supervisor system..."
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        if [ -f "$SUPERVISOR_CONFIG" ]; then
            echo "Supervisor status:"
            supervisorctl -c "$SUPERVISOR_CONFIG" status
        else
            echo "Supervisor not configured"
        fi
        ;;

    logs)
        if [ -n "$2" ]; then
            # Show logs for specific IOC
            tail -f "logs/$2.log"
        else
            echo "Available log files:"
            ls -la logs/
        fi
        ;;

    clean)
        echo "Cleaning supervisor files..."
        $0 stop
        rm -f supervisord.conf supervisor.sock supervisord.pid
        rm -rf logs/*
        echo "Cleaned supervisor files"
        ;;

    *)
        echo "Usage: $0 {start|stop|restart|status|logs [ioc_name]|clean}"
        echo ""
        echo "  start    - Start the supervisor IOC manager"
        echo "  stop     - Stop all IOCs and supervisor"
        echo "  restart  - Restart the supervisor system"
        echo "  status   - Show status of all IOCs"
        echo "  logs     - Show available logs or tail specific IOC log"
        echo "  clean    - Clean all supervisor files and logs"
        exit 1
        ;;
esac