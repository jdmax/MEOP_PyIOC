#!/bin/bash
# ioc-supervisor/install_systemd_service.sh
# Script to install the IOC supervisor as a systemd service

cd "$(dirname "$0")"

# Get the current user and group
CURRENT_USER=$(whoami)
CURRENT_GROUP=$(id -gn)

# Get absolute paths
PROJECT_DIR=$(realpath ..)
SUPERVISOR_DIR=$(realpath .)
VENV_PATH="$PROJECT_DIR/venv"

# Check if virtual environment exists
if [ ! -d "$VENV_PATH" ]; then
    echo "Error: Virtual environment not found at $VENV_PATH"
    echo "Please create the virtual environment first"
    exit 1
fi

# Check if running as root (needed for systemd installation)
if [ "$EUID" -eq 0 ]; then
    echo "Error: Don't run this script as root"
    echo "Run as your regular user, script will use sudo when needed"
    exit 1
fi

echo "Installing IOC Supervisor systemd service..."
echo "Project directory: $PROJECT_DIR"
echo "Supervisor directory: $SUPERVISOR_DIR"
echo "User: $CURRENT_USER"
echo "Group: $CURRENT_GROUP"
echo ""

# Create the service file with correct paths
SERVICE_CONTENT="[Unit]
Description=IOC Supervisor Manager
After=network.target
Wants=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_GROUP
WorkingDirectory=$SUPERVISOR_DIR
Environment=PATH=$VENV_PATH/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
ExecStart=$VENV_PATH/bin/python supervisor_ioc_manager.py
ExecStop=$SUPERVISOR_DIR/supervisor_control.sh stop
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=ioc-supervisor

# Security settings
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$PROJECT_DIR

[Install]
WantedBy=multi-user.target"

# Write the service file to a temporary location
TEMP_SERVICE="/tmp/ioc-supervisor.service"
echo "$SERVICE_CONTENT" > "$TEMP_SERVICE"

echo "Service file created. Installing..."

# Copy to systemd directory and enable
sudo cp "$TEMP_SERVICE" /etc/systemd/system/ioc-supervisor.service
sudo systemctl daemon-reload

echo ""
echo "Service installed! Available commands:"
echo ""
echo "  sudo systemctl start ioc-supervisor    # Start the service"
echo "  sudo systemctl stop ioc-supervisor     # Stop the service"
echo "  sudo systemctl enable ioc-supervisor   # Enable auto-start on boot"
echo "  sudo systemctl disable ioc-supervisor  # Disable auto-start"
echo "  sudo systemctl status ioc-supervisor   # Check service status"
echo "  journalctl -u ioc-supervisor -f        # Follow service logs"
echo ""

read -p "Do you want to enable auto-start on boot? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl enable ioc-supervisor
    echo "Auto-start enabled"
fi

read -p "Do you want to start the service now? (y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    sudo systemctl start ioc-supervisor
    echo "Service started"
    echo ""
    echo "Checking status..."
    sudo systemctl status ioc-supervisor --no-pager
fi

# Clean up
rm -f "$TEMP_SERVICE"

echo ""
echo "Installation complete!"
echo "Use 'sudo systemctl status ioc-supervisor' to check the service status"