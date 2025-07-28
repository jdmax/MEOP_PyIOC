# devices/archiver.py
import asyncio
import aioca
from datetime import datetime
import csv
import os
from pathlib import Path
from softioc import builder
from .base_device import BaseDevice
import yaml


class Device(BaseDevice):
    """EPICS Archiver - Archives PV values to CSV files with deadband logic"""

    def __init__(self, device_name, settings):
        self.archive_path = Path(settings.get('archive_path', 'archive'))
        self.deadband = settings.get('deadband', 0.01)  # Default 1% change
        self.time_increment = settings.get('time_increment', 60)  # Default 60 seconds
        self.pv_patterns = settings.get('pv_patterns', [])
        self.exclude_patterns = settings.get('exclude_patterns', [])

        # Storage for PV state
        self.monitored_pvs = {}  # {pv_name: {'value': x, 'timestamp': t, 'file': f}}
        self.monitors = []  # Store monitor references

        # Create archive directory
        self.archive_path.mkdir(parents=True, exist_ok=True)

        # Load full settings for PV discovery
        self._load_full_settings()

        super().__init__(device_name, settings)

    def _load_full_settings(self):
        """Load the complete settings.yaml file for PV discovery"""
        try:
            # Check if settings file path is specified
            settings_file = self.settings.get('settings_file', None)

            if settings_file and Path(settings_file).exists():
                settings_paths = [settings_file]
            else:
                # Try common locations for settings.yaml
                settings_paths = [
                    'settings.yaml',
                    '../settings.yaml',
                    './settings.yaml',
                    Path(__file__).parent.parent / 'settings.yaml'
                ]

            self.full_settings = None
            for path in settings_paths:
                if Path(path).exists():
                    with open(path, 'r') as f:
                        self.full_settings = yaml.load(f, Loader=yaml.FullLoader)
                    print(f"Archiver loaded full settings from {path}")
                    break

            if not self.full_settings:
                print("Warning: Could not load full settings.yaml for archiver")
                self.full_settings = {'general': {'prefix': 'TGT:MEOP'}}
        except Exception as e:
            print(f"Error loading full settings: {e}")
            self.full_settings = {'general': {'prefix': 'TGT:MEOP'}}

    def _create_pvs(self):
        """Create archiver control PVs"""
        # Status PVs
        self.pvs['Archive_Status'] = builder.mbbIn('Archive_Status',
                                           'Stopped', 'Running', 'Error')
        self.pvs['Archive_PV_Count'] = builder.longIn('Archive_PV_Count')
        self.pvs['Archive_Write_Rate'] = builder.aIn('Archive_Write_Rate')  # Writes per minute

        # Control PVs
        self.pvs['Archive_Enable'] = builder.boolOut('Archive_Enable',
                                             on_update=self.toggle_archiving)
        self.pvs['Archive_Deadband'] = builder.aOut('Archive_Deadband',
                                            on_update=self.update_deadband)
        self.pvs['Archive_Time_Increment'] = builder.aOut('Archive_Time_Increment',
                                                  on_update=self.update_time_increment)

        # Initialize values
        self.pvs['Archive_Status'].set(0)  # Stopped
        self.pvs['Archive_PV_Count'].set(0)
        self.pvs['Archive_Write_Rate'].set(0)
        self.pvs['Archive_Deadband'].set(self.deadband)
        self.pvs['Archive_Time_Increment'].set(self.time_increment)
        self.pvs['Archive_Enable'].set(False)

    def _create_connection(self):
        """No physical connection needed for archiver"""
        return ArchiverConnection()

    def connect(self):
        """Override connect - no physical device to connect to"""
        self.t = self._create_connection()
        # Start write rate calculator
        asyncio.create_task(self._calculate_write_rate())

    async def do_reads(self):
        """Archiver doesn't do periodic reads - it uses monitors"""
        # This is called by the main loop but we don't need it
        # Just update status
        if self.pvs['Archive_Enable'].get():
            self.pvs['Archive_Status'].set(1)  # Running
        else:
            self.pvs['Archive_Status'].set(0)  # Stopped
        return True

    def toggle_archiving(self, value):
        """Start or stop archiving based on Enable PV"""
        if value:
            asyncio.create_task(self.start_archiving())
        else:
            asyncio.create_task(self.stop_archiving())

    def update_deadband(self, value):
        """Update deadband value"""
        self.deadband = value
        print(f"Archiver deadband updated to {value}")

    def update_time_increment(self, value):
        """Update time increment value"""
        self.time_increment = value
        print(f"Archiver time increment updated to {value} seconds")

    async def start_archiving(self):
        """Start monitoring and archiving PVs"""
        try:
            print("Starting archiver...")

            # Wait a bit to ensure other IOCs are up
            await asyncio.sleep(2)

            # Get list of PVs to monitor
            pv_list = await self._discover_pvs()

            if not pv_list:
                print("Warning: No PVs discovered. Will retry in 30 seconds...")
                await asyncio.sleep(30)
                pv_list = await self._discover_pvs()

            # Clear any existing monitors
            await self.stop_archiving()

            # Set up monitors for each PV
            for pv in pv_list:
                if self._should_archive(pv):
                    try:
                        # Initialize PV state
                        self.monitored_pvs[pv] = {
                            'value': None,
                            'timestamp': None,
                            'last_write': datetime.now(),
                            'writer': self._get_csv_writer(pv)
                        }

                        # Create monitor
                        monitor = aioca.camonitor(
                            pv,
                            self._create_monitor_callback(pv),
                            notify_disconnect=True
                        )
                        self.monitors.append(monitor)

                    except Exception as e:
                        print(f"Failed to monitor {pv}: {e}")

            self.pvs['Archive_PV_Count'].set(len(self.monitored_pvs))
            self.pvs['Archive_Status'].set(1)  # Running
            print(f"Archiver started - monitoring {len(self.monitored_pvs)} PVs")
            if len(self.monitored_pvs) > 0:
                print(f"First few PVs: {', '.join(list(self.monitored_pvs.keys())[:5])}")

        except Exception as e:
            print(f"Failed to start archiver: {e}")
            self.pvs['Archive_Status'].set(2)  # Error

    async def stop_archiving(self):
        """Stop monitoring and close files"""
        print("Stopping archiver...")

        # Cancel all monitors
        for monitor in self.monitors:
            monitor.close()
        self.monitors.clear()

        # Close all file handles
        for pv_data in self.monitored_pvs.values():
            if 'file_handle' in pv_data and pv_data['file_handle']:
                pv_data['file_handle'].close()

        self.monitored_pvs.clear()
        self.pvs['Archive_PV_Count'].set(0)
        self.pvs['Archive_Status'].set(0)  # Stopped
        print("Archiver stopped")

    async def _discover_pvs(self):
        """Discover PVs from running IOCs"""
        pv_list = []

        # Get all PVs from the IOC manager
        try:
            # Use full settings to get all IOCs
            if not self.full_settings:
                print("Warning: No full settings available for PV discovery")
                return []

            # List all IOCs that are running
            ioc_list = []
            prefix = self.full_settings['general']['prefix']

            for name in self.full_settings.keys():
                if name in ['general', 'archiver']:
                    continue
                try:
                    status = await aioca.caget(f"{prefix}:MAN:{name}_control")
                    if status == 1:  # Running
                        ioc_list.append(name)
                except:
                    pass

            # For each running IOC, get its PVs
            print(f"Archiver found {len(ioc_list)} running IOCs: {', '.join(ioc_list)}")

            for ioc in ioc_list:
                # Based on the settings, construct PV names
                if ioc in self.full_settings:
                    ioc_settings = self.full_settings[ioc]
                    if 'channels' in ioc_settings:
                        for channel in ioc_settings['channels']:
                            if channel and "None" not in channel:
                                # Construct full PV name
                                base_pv = f"{prefix}:{channel}"
                                pv_list.append(base_pv)

                                # Check for associated PVs based on device types
                                suffixes = [
                                    '_TI', '_PI', '_CI', '_VI', '_LI',  # Basic indicators
                                    '_SP', '_Heater', '_Mode', '_Range',  # Temperature controllers
                                    '_VC', '_CC',  # Power supplies
                                    '_Manual', '_kP', '_kI', '_kD',  # PID controls
                                    '_Coil_CI', '_Lead_CI', '_ULIM', '_LLIM', '_Sweep'  # Magnet supplies
                                ]
                                for suffix in suffixes:
                                    pv_list.append(f"{base_pv}{suffix}")

        except Exception as e:
            print(f"Error discovering PVs: {e}")

        # Remove duplicates and filter by patterns
        pv_list = list(set(pv_list))
        filtered_pvs = []

        for pv in pv_list:
            if self._should_archive(pv):
                # Test if PV exists
                try:
                    await aioca.caget(pv, timeout=1.0)
                    filtered_pvs.append(pv)
                except:
                    pass

        print(f"Archiver discovered {len(filtered_pvs)} valid PVs to monitor")
        return filtered_pvs

    def _should_archive(self, pv_name):
        """Check if PV should be archived based on patterns"""
        # Check exclude patterns first
        for pattern in self.exclude_patterns:
            if pattern in pv_name:
                return False

        # If no include patterns specified, archive everything
        if not self.pv_patterns:
            return True

        # Check include patterns
        for pattern in self.pv_patterns:
            if pattern in pv_name:
                return True

        return False

    def _create_monitor_callback(self, pv_name):
        """Create a callback function for a specific PV"""

        def callback(value):
            asyncio.create_task(self._handle_pv_update(pv_name, value))

        return callback

    async def _handle_pv_update(self, pv_name, value):
        """Handle PV value update with deadband logic"""
        try:
            if value is None:
                return

            pv_data = self.monitored_pvs.get(pv_name)
            if not pv_data:
                return

            current_time = datetime.now()

            # Check if we should write this value
            should_write = False

            # First value
            if pv_data['value'] is None:
                should_write = True
            else:
                # Check deadband
                try:
                    old_val = float(pv_data['value'])
                    new_val = float(value)

                    # Calculate relative change
                    if old_val != 0:
                        rel_change = abs((new_val - old_val) / old_val)
                    else:
                        rel_change = abs(new_val)

                    if rel_change >= self.deadband:
                        should_write = True
                except (ValueError, TypeError):
                    # Non-numeric value, check if changed
                    if str(value) != str(pv_data['value']):
                        should_write = True

                # Check time increment
                time_diff = (current_time - pv_data['last_write']).total_seconds()
                if time_diff >= self.time_increment:
                    should_write = True

            # Write if needed
            if should_write:
                self._write_value(pv_name, value, current_time)
                pv_data['value'] = value
                pv_data['timestamp'] = current_time
                pv_data['last_write'] = current_time

        except Exception as e:
            print(f"Error handling update for {pv_name}: {e}")

    def _get_csv_writer(self, pv_name):
        """Get or create CSV writer for a PV"""
        # Create filename based on PV name and date
        safe_pv_name = pv_name.replace(':', '_').replace('/', '_')
        date_str = datetime.now().strftime('%Y-%m-%d')
        filename = self.archive_path / f"{safe_pv_name}_{date_str}.csv"

        # Check if file exists
        file_exists = filename.exists()

        # Open file and create writer
        file_handle = open(filename, 'a', newline='')
        writer = csv.writer(file_handle)

        # Write header if new file
        if not file_exists:
            writer.writerow(['Timestamp', 'Value'])

        # Store file handle for cleanup
        if pv_name in self.monitored_pvs:
            self.monitored_pvs[pv_name]['file_handle'] = file_handle

        return writer

    def _write_value(self, pv_name, value, timestamp):
        """Write value to CSV file"""
        try:
            pv_data = self.monitored_pvs.get(pv_name)
            if not pv_data or 'writer' not in pv_data:
                return

            # Check if we need a new file (date changed)
            date_str = timestamp.strftime('%Y-%m-%d')
            if 'file_handle' in pv_data:
                current_file = pv_data['file_handle'].name
                if date_str not in current_file:
                    # Close old file and create new one
                    pv_data['file_handle'].close()
                    pv_data['writer'] = self._get_csv_writer(pv_name)

            # Write data
            pv_data['writer'].writerow([
                timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3],  # milliseconds
                value
            ])

            # Flush to ensure data is written
            if 'file_handle' in pv_data:
                pv_data['file_handle'].flush()

            # Update write counter
            if hasattr(self, '_write_count'):
                self._write_count += 1
            else:
                self._write_count = 1

        except Exception as e:
            print(f"Error writing {pv_name}: {e}")

    async def _calculate_write_rate(self):
        """Calculate and update write rate PV"""
        last_count = 0

        while True:
            await asyncio.sleep(60)  # Calculate every minute

            current_count = getattr(self, '_write_count', 0)
            rate = current_count - last_count
            last_count = current_count

            self.pvs['Archive_Write_Rate'].set(rate)


class ArchiverConnection:
    """Dummy connection class for archiver"""

    def __init__(self):
        pass