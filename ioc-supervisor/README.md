# Supervisor IOC Manager

This directory contains the supervisor-based IOC management system, which replaces the Unix screen-based approach for better process control and monitoring.

## Features

- **Better Process Management**: Uses supervisord for robust process control
- **Same EPICS Interface**: Maintains the same PV-based control interface
- **Automatic Restart**: Can be configured for automatic process restart on failure
- **Better Logging**: Centralized logging with rotation
- **Status Monitoring**: Real-time process status monitoring
- **Clean Shutdown**: Graceful shutdown of all processes
- **Persistent Operation**: Multiple options for running as a persistent service

## Installation

1. Install supervisor in your virtual environment:
   ```bash
   pip install -r ioc-supervisor/requirements.txt
   ```

2. Make scripts executable:
   ```bash
   chmod +x ioc-supervisor/*.sh
   ```

## Running the System

### Option 1: Systemd Service (Recommended for Linux)

This is the best option for production use - the service will start automatically on boot and restart if it crashes.

```bash
cd ioc-supervisor
./install_systemd_service.sh
```

Then manage with systemctl:
```bash
sudo systemctl start ioc-supervisor     # Start
sudo systemctl stop ioc-supervisor      # Stop
sudo systemctl enable ioc-supervisor    # Auto-start on boot
sudo systemctl status ioc-supervisor    # Check status
journalctl -u ioc-supervisor -f         # Follow logs
```

### Option 2: Daemon Mode

Run as a background daemon that persists when you log out:

```bash
cd ioc-supervisor
./supervisor_control.sh start-daemon    # Start as daemon
./supervisor_control.sh status          # Check status
./supervisor_control.sh stop            # Stop daemon
```

### Option 3: Foreground (Testing)

For testing or development:
```bash
cd ioc-supervisor
./supervisor_control.sh start           # Runs in foreground
```

## Controlling IOCs

The EPICS PV interface remains exactly the same:
- `{PREFIX}:MAN:{ioc_name}_control` - Control PV (0=Stop, 1=Run, 2=Reset)
- `{PREFIX}:MAN:{ioc_name}_hb` - Heartbeat PV (seconds since last update)
- `{PREFIX}:MAN:all` - Control all IOCs with autostart=True

## System Management

```bash
# Check status of all IOCs and the manager
./supervisor_control.sh status

# Stop everything (daemon and all IOCs)
./supervisor_control.sh stop

# Restart as daemon
./supervisor_control.sh restart

# View logs
./supervisor_control.sh logs                # List available logs
./supervisor_control.sh logs manager        # Supervisor manager log
./supervisor_control.sh logs pfeiffer-26x_1 # Specific IOC log

# Clean all files (stops system first)
./supervisor_control.sh clean

# Install systemd service
./supervisor_control.sh install-service
```

## File Structure

```
ioc-supervisor/
├── supervisor_ioc_manager.py      # Main supervisor-based manager
├── start_supervisor_manager.sh    # Startup script with daemon options
├── supervisor_control.sh          # Management script
├── install_systemd_service.sh     # Systemd service installer
├── ioc-supervisor.service         # Systemd service template
├── requirements.txt               # Additional dependencies
├── README.md                      # This file
├── supervisord.conf               # Generated supervisor config
├── supervisor.sock                # Supervisor unix socket
├── supervisord.pid               # Supervisor PID file
├── supervisor_manager.pid        # Manager daemon PID file
└── logs/                         # Log directory
    ├── supervisord.log           # Supervisor daemon log
    ├── supervisor_manager.log    # Manager daemon log
    ├── {ioc_name}.log           # Individual IOC stdout logs
    └── {ioc_name}_error.log     # Individual IOC stderr logs
```

## Differences from Screen-Based System

### Advantages
- **Better process isolation**: Each IOC runs in its own supervised process
- **Automatic restart options**: Can be configured for auto-restart on failure
- **Better logging**: Separate stdout/stderr logs with rotation
- **Web interface**: Supervisor provides a web interface at http://localhost:9001
- **More reliable**: Better handling of process crashes and cleanup
- **Standards-based**: Uses industry-standard process manager
- **Persistent operation**: Multiple options for running persistently
- **System integration**: Can be managed as a proper system service

### Configuration
- The `supervisord.conf` file is generated automatically from `settings.yaml`
- All IOCs are configured with `autostart=false` by default
- Processes are controlled through EPICS PVs, not supervisor directly
- Logs are stored in `ioc-supervisor/logs/`

## Persistent Operation Options

### 1. Systemd Service (Best for production)
- **Pros**: Automatic startup on boot, restart on failure, integrated with system logging
- **Cons**: Linux-only, requires sudo for installation
- **Use when**: Production deployment, want automatic startup/restart

### 2. Daemon Mode
- **Pros**: Works on any Unix system, no sudo required
- **Cons**: Manual startup after reboot, basic process management
- **Use when**: Development, testing, or systems without systemd

### 3. Screen/Tmux (Alternative)
You can also run the daemon mode inside a screen or tmux session:
```bash
screen -S ioc-supervisor
cd ioc-supervisor
./supervisor_control.sh start-daemon
# Ctrl-A, D to detach
```

## Troubleshooting

### IOC won't start
1. Check supervisor status: `./supervisor_control.sh status`
2. Check IOC-specific logs: `./supervisor_control.sh logs {ioc_name}`
3. Check supervisor daemon log: `cat logs/supervisord.log`

### Supervisor won't start
1. Check if port 9001 is available: `netstat -ln | grep 9001`
2. Check supervisor daemon log: `cat logs/supervisord.log`
3. Clean and restart: `./supervisor_control.sh clean && ./supervisor_control.sh start-daemon`

### EPICS PVs not responding
1. Verify supervisor IOC manager is running: `./supervisor_control.sh status`
2. Check manager logs: `./supervisor_control.sh logs manager`
3. Restart the system: `./supervisor_control.sh restart`

### Systemd service issues
1. Check service status: `sudo systemctl status ioc-supervisor`
2. Check service logs: `journalctl -u ioc-supervisor -f`
3. Reload service: `sudo systemctl daemon-reload && sudo systemctl restart ioc-supervisor`

## Migration from Screen-Based System

1. Stop the old screen-based IOC manager
2. Install supervisor dependencies
3. Choose your preferred running mode (systemd recommended)
4. Start the new supervisor system
5. EPICS PV interface remains the same - no changes needed to clients

The supervisor system provides the same external interface but with better internal process management and persistent operation options.