#!/bin/bash
# Helper script to manage the supervisor system

cd "$(dirname "$0")"

SUPERVISOR_CONFIG="supervisord.conf"
SUPERVISOR_PID="supervisord.pid"
MANAGER_PID="supervisor_manager.pid"

case "$1" in
    start)
        echo "Starting supervisor IOC manager..."
        ./start_supervisor_manager.sh
        ;;

    start-daemon)
        echo "Starting supervisor IOC manager as daemon..."
        ./start_supervisor_manager.sh --daemon
        ;;

    stop)
        echo "Stopping all IOCs and supervisor..."

        # Stop the supervisor manager daemon if running
        if [ -f "$MANAGER_PID" ]; then
            echo "Stopping supervisor manager daemon..."
            ./start_supervisor_manager.sh --stop-daemon
        fi

        # Stop all IOCs and supervisord
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
        $0 start-daemon
        ;;

    status)
        echo "=== Supervisor Manager Status ==="
        if [ -f "$MANAGER_PID" ]; then
            PID=$(cat "$MANAGER_PID")
            if kill -0 "$PID" 2>/dev/null; then
                echo "Supervisor manager daemon running (PID: $PID)"
            else
                echo "Supervisor manager daemon not running (stale PID file)"
                rm -f "$MANAGER_PID"
            fi
        else
            echo "Supervisor manager daemon not running"
        fi

        echo ""
        echo "=== Supervisord Status ==="
        if [ -f "$SUPERVISOR_CONFIG" ]; then
            supervisorctl -c "$SUPERVISOR_CONFIG" status
        else
            echo "Supervisor not configured"
        fi
        ;;

    logs)
        if [ -n "$2" ]; then
            # Show logs for specific IOC
            if [ "$2" = "manager" ]; then
                tail -f "logs/supervisor_manager.log"
            else
                tail -f "logs/$2.log"
            fi
        else
            echo "Available log files:"
            ls -la logs/
            echo ""
            echo "Usage: $0 logs {manager|ioc_name}"
        fi
        ;;

    install-service)
        echo "Installing systemd service..."
        ./install_systemd_service.sh
        ;;

    clean)
        echo "Cleaning supervisor files..."
        $0 stop
        rm -f supervisord.conf supervisor.sock supervisord.pid supervisor_manager.pid
        rm -rf logs/*
        echo "Cleaned supervisor files"
        ;;

    *)
        echo "Usage: $0 {start|start-daemon|stop|restart|status|logs [manager|ioc_name]|install-service|clean}"
        echo ""
        echo "  start         - Start in foreground (for testing)"
        echo "  start-daemon  - Start as background daemon"
        echo "  stop          - Stop all IOCs and supervisor"
        echo "  restart       - Restart as daemon"
        echo "  status        - Show status of manager and all IOCs"
        echo "  logs          - Show available logs or tail specific log"
        echo "  install-service - Install systemd service"
        echo "  clean         - Clean all supervisor files and logs"
        exit 1
        ;;
esac