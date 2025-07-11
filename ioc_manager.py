# J. Maxwell 2023 - Modified for supervisord
import yaml
from softioc import softioc, builder, asyncio_dispatcher
import asyncio
import re
import time
import os
import xmlrpc.client
import http.client
import socket
import aioca
import datetime
import configparser


class UnixStreamHTTPConnection(http.client.HTTPConnection):
    """HTTP connection over Unix domain socket"""

    def __init__(self, socket_path):
        self.socket_path = socket_path
        super().__init__('localhost')

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.socket_path)


class UnixStreamTransport(xmlrpc.client.Transport):
    """Transport for Unix domain sockets"""

    def __init__(self, socket_path):
        self.socket_path = socket_path
        super().__init__()

    def make_connection(self, host):
        return UnixStreamHTTPConnection(self.socket_path)


async def main():
    """
    IOC to manage IOCS. Sets up PVs for each IOC in settings file to allow starting and stopping.
    Uses supervisord to manage master_ioc for each device IOC.
    """

    with open('settings.yaml') as f:  # Load settings from YAML config file
        settings = yaml.load(f, Loader=yaml.FullLoader)

    os.environ['EPICS_CA_ADDR_LIST'] = settings['general']['epics_addr_list']
    os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'NO'

    dispatcher = asyncio_dispatcher.AsyncioDispatcher()
    device_name = settings['general']['prefix'] + ':MAN'
    builder.SetDeviceName(device_name)

    i = IOCManager(device_name, settings)
    builder.LoadDatabase()
    softioc.iocInit(dispatcher)

    async def loop():
        while True:
            await i.heartbeat()

    dispatcher(loop)  # put functions to loop in here
    softioc.interactive_ioc(globals())


class IOCManager:
    """
    Handles supervisord processes which run iocs. Makes PVs to control each ioc.
    """

    def __init__(self, device_name, settings):
        """
        Make control PVs for each IOC. "pvs" dict is keyed on name (e.g. flow),
        PV is labeled as name + 'control' (e.g. flow_control)
        """
        self.device_name = device_name
        self.settings = settings
        self.delay = settings['general']['delay']
        self.pvs = {}
        self.ioc_pvs = {}  # Dict of lists of all PVs in each instance, keyed by ioc name

        # Connect to supervisord via Unix socket
        self.supervisor = xmlrpc.client.ServerProxy('http://localhost',
                                                    transport=UnixStreamTransport('/tmp/supervisor_ioc.sock'))

        # Ensure supervisor config includes all IOCs
        self._update_supervisor_config()

        for name in settings.keys():  # each IOC has controls to start, stop or reset
            if 'general' in name: continue
            self.pvs[name] = builder.mbbOut(name + '_control',
                                            ("Stop", 'MINOR'),
                                            ("Run", 0),
                                            ("Reset", 'MINOR'),
                                            on_update_name=self.screen_update
                                            )
            self.pvs[name + '_hb'] = builder.mbbOut(name + '_hb')
            self.pvs[name].set(0)

        self.pv_all = builder.mbbOut('all',
                                     ("Stop", 'MINOR'),
                                     ("Run", 0),
                                     ("Reset", 'MINOR'),
                                     on_update=self.all_screen_update
                                     )
        self.pv_all.set(0)

        self.ioc_regex = re.compile(f'{device_name}')

    def _update_supervisor_config(self):
        """Add IOC programs to supervisor config if they don't exist"""
        config_path = 'ioc-supervisor/supervisord.conf'
        config = configparser.ConfigParser()
        config.read(config_path)

        # Add any missing IOC programs
        for name in self.settings.keys():
            if 'general' in name:
                continue

            program_name = f'program:{name}'
            if program_name not in config:
                config[program_name] = {
                    'command': f'python master_ioc.py -i {name}',
                    'directory': '%(here)s/..',
                    'autostart': 'false',
                    'autorestart': 'false',
                    'stdout_logfile': f'%(here)s/logs/{name}.log',
                    'stderr_logfile': f'%(here)s/logs/{name}_error.log',
                    'environment': 'PATH="%(here)s/../venv/bin",PYTHONUNBUFFERED="1"'
                }

        # Write updated config
        with open(config_path, 'w') as f:
            config.write(f)

        # Reload supervisor config
        try:
            self.supervisor.supervisor.reloadConfig()
            # Add any new programs
            added, changed, removed = self.supervisor.supervisor.getConfigChanges()
            for group in added:
                self.supervisor.supervisor.addProcessGroup(group)
        except Exception as e:
            print(f"Error updating supervisor config: {e}")

    def screen_update(self, i, pv):
        """
        Multiple Choice PV has changed for the given control PV. Follow command. 0=Stop, 1=Start, 2=Reset
        """
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name from PV to get bare pv_name
        if i == 0:
            self.stop_ioc(pv_name)
        elif i == 1:
            state = self._get_process_state(pv_name.replace('_control', ''))
            if state and state['statename'] == 'RUNNING':
                self.reset_ioc(pv_name)  # if it already exists, restart it
            else:
                self.start_ioc(pv_name)
        elif i == 2:
            self.reset_ioc(pv_name)

    def all_screen_update(self, i):
        """
        Do update for all iocs in config file with autostart set to True.
        """
        for name in self.settings.keys():
            if 'general' in name: continue
            if self.settings[name]['autostart']:
                self.pvs[name].set(i)

    def _get_process_state(self, name):
        """Get process state from supervisord"""
        try:
            return self.supervisor.supervisor.getProcessInfo(name)
        except:
            return None

    def start_ioc(self, pv_name):
        """
        Start IOC process via supervisord
        """
        name = pv_name.replace('_control', '')  # remove suffix from pv name

        try:
            self.supervisor.supervisor.startProcess(name)
            # Wait a bit for the process to start
            time.sleep(2)

            # Check if log file exists and has content
            log_path = f"{self.settings['general']['log_dir']}/{name}"
            if os.path.exists(log_path) and os.path.getsize(log_path) > 10:
                pvs = []
                with open(log_path) as f:
                    for line in f:
                        match = re.search(f"({self.settings['general']['prefix']}.+)" + r'\s', line)
                        if match:
                            pvs.append(match.group(1))
                self.ioc_pvs[name] = pvs
                self.pvs[name].set(1)
            else:
                print(f"Warning: Log file for {name} not ready yet")
                self.pvs[name].set(1)  # Set to running anyway

        except xmlrpc.client.Fault as e:
            if 'ALREADY_STARTED' in str(e):
                print(f"{name} is already running")
                self.pvs[name].set(1)
            else:
                print(f"Failed to start {name}: {e}")
                self.pvs[name].set(0)

    def stop_ioc(self, pv_name):
        """
        Stop IOC process via supervisord
        """
        name = pv_name.replace('_control', '')  # remove suffix from pv name

        try:
            self.supervisor.supervisor.stopProcess(name)
            self.pvs[name].set(0)
        except xmlrpc.client.Fault as e:
            if 'NOT_RUNNING' in str(e):
                print(f"{name} is not running")
                self.pvs[name].set(0)
            else:
                print(f"Failed to stop {name}: {e}")

    def reset_ioc(self, pv_name):
        """
        Stop and restart IOC process via supervisord
        """
        name = pv_name.replace('_control', '')  # remove suffix from pv name

        self.stop_ioc(pv_name)
        time.sleep(1)
        self.start_ioc(pv_name)

    async def heartbeat(self):
        """Check last time written versus current time for each IOC"""
        group = []
        await asyncio.sleep(self.delay)

        # Get all process states from supervisord
        try:
            all_info = self.supervisor.supervisor.getAllProcessInfo()
            process_states = {info['name']: info for info in all_info}
        except:
            process_states = {}

        for name in self.settings.keys():
            if 'general' in name:
                continue

            # Only check heartbeat for running processes
            if name in process_states and process_states[name]['statename'] == 'RUNNING':
                group.append(self.time_check(name))

        if group:
            await asyncio.gather(*group)

    async def time_check(self, name):
        try:
            t = await aioca.caget(f"{self.device_name}:{name}_time")
            now = datetime.datetime.now().timestamp()
            self.pvs[name + '_hb'].set(int(now - float(t)))
        except aioca.CANothing as e:
            print("Get error:", e, f"{self.device_name}:{name}_time")


if __name__ == "__main__":
    asyncio.run(main())