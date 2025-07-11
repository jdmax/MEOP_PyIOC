# ioc-supervisor/supervisor_ioc_manager.py
# J. Maxwell 2023 - Modified for supervisord
import os
import sys
import yaml
import time
import datetime
import asyncio
import subprocess
from pathlib import Path
import xmlrpc.client

from softioc import softioc, builder, asyncio_dispatcher
import aioca


async def main():
    """
    IOC to manage IOCs using supervisord. Sets up PVs for each IOC in settings file
    to allow starting and stopping. Uses supervisord to run master_ioc for each device IOC.
    """

    # Load settings from parent directory
    settings_path = Path(__file__).parent.parent / 'settings.yaml'
    with open(settings_path) as f:
        settings = yaml.load(f, Loader=yaml.FullLoader)

    os.environ['EPICS_CA_ADDR_LIST'] = settings['general']['epics_addr_list']
    os.environ['EPICS_CA_AUTO_ADDR_LIST'] = 'NO'

    dispatcher = asyncio_dispatcher.AsyncioDispatcher()
    device_name = settings['general']['prefix'] + ':MAN'
    builder.SetDeviceName(device_name)

    i = SupervisorIOCManager(device_name, settings)
    builder.LoadDatabase()
    softioc.iocInit(dispatcher)

    async def loop():
        while True:
            await i.heartbeat()

    dispatcher(loop)
    softioc.interactive_ioc(globals())


class SupervisorIOCManager:
    """
    Manages IOCs using supervisord. Makes PVs to control each IOC.
    """

    def __init__(self, device_name, settings):
        """
        Make control PVs for each IOC and set up supervisord
        """
        self.device_name = device_name
        self.settings = settings
        self.delay = settings['general']['delay']
        self.pvs = {}
        self.supervisor_dir = Path(__file__).parent
        self.project_dir = self.supervisor_dir.parent

        # Create supervisor directory structure
        self.log_dir = self.supervisor_dir / 'logs'
        self.log_dir.mkdir(exist_ok=True)

        # Generate supervisord configuration
        self._generate_supervisor_config()

        # Start supervisord
        self._start_supervisord()

        # Connect to supervisor XML-RPC
        self.server = xmlrpc.client.Server('http://localhost:9001/RPC2')

        # Wait for supervisord to start
        time.sleep(2)

        # Create control PVs for each IOC
        for name in settings.keys():
            if 'general' in name:
                continue

            self.pvs[name] = builder.mbbOut(
                name + '_control',
                ("Stop", 'MINOR'),
                ("Run", 0),
                ("Reset", 'MINOR'),
                on_update_name=self.ioc_update
            )
            self.pvs[name + '_hb'] = builder.mbbOut(name + '_hb')
            self.pvs[name].set(0)

        # Create "all" control PV
        self.pv_all = builder.mbbOut(
            'all',
            ("Stop", 'MINOR'),
            ("Run", 0),
            ("Reset", 'MINOR'),
            on_update=self.all_ioc_update
        )
        self.pv_all.set(0)

    def _generate_supervisor_config(self):
        """Generate supervisord.conf file dynamically"""
        config_path = self.supervisor_dir / 'supervisord.conf'

        config_content = f"""[unix_http_server]
file={self.supervisor_dir}/supervisor.sock

[supervisord]
logfile={self.log_dir}/supervisord.log
logfile_maxbytes=50MB
logfile_backups=10
loglevel=info
pidfile={self.supervisor_dir}/supervisord.pid
nodaemon=false
minfds=1024
minprocs=200

[rpcinterface:supervisor]
supervisor.rpcinterface_factory = supervisor.rpcinterface:make_main_rpcinterface

[supervisorctl]
serverurl=unix://{self.supervisor_dir}/supervisor.sock

[inet_http_server]
port=127.0.0.1:9001

"""

        # Add program sections for each IOC
        for name in self.settings.keys():
            if 'general' in name:
                continue

            config_content += f"""[program:{name}]
command=python {self.project_dir}/master_ioc.py -i {name}
directory={self.project_dir}
autostart=false
autorestart=false
startsecs=3
startretries=3
stdout_logfile={self.log_dir}/{name}.log
stderr_logfile={self.log_dir}/{name}_error.log
environment=PYTHONPATH="{self.project_dir}"

"""

        with open(config_path, 'w') as f:
            f.write(config_content)

        print(f"Generated supervisord config: {config_path}")

    def _start_supervisord(self):
        """Start supervisord daemon"""
        config_path = self.supervisor_dir / 'supervisord.conf'

        # Kill any existing supervisord
        try:
            subprocess.run(['supervisorctl', '-c', str(config_path), 'shutdown'],
                           check=False, capture_output=True)
            time.sleep(1)
        except:
            pass

        # Start supervisord
        cmd = ['supervisord', '-c', str(config_path)]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
            print("Started supervisord")
        except subprocess.CalledProcessError as e:
            print(f"Failed to start supervisord: {e}")
            sys.exit(1)

    def ioc_update(self, i, pv):
        """
        Handle IOC control PV changes. 0=Stop, 1=Start, 2=Reset
        """
        pv_name = pv.replace(self.device_name + ':', '')
        name = pv_name.replace('_control', '')

        try:
            if i == 0:  # Stop
                self._stop_ioc(name)
            elif i == 1:  # Start
                self._start_ioc(name)
            elif i == 2:  # Reset
                self._restart_ioc(name)
        except Exception as e:
            print(f"Error controlling IOC {name}: {e}")

    def all_ioc_update(self, i):
        """
        Apply update to all IOCs with autostart=True
        """
        for name in self.settings.keys():
            if 'general' in name:
                continue
            if self.settings[name].get('autostart', False):
                self.pvs[name].set(i)

    def _start_ioc(self, name):
        """Start an IOC using supervisor"""
        try:
            info = self.server.supervisor.getProcessInfo(name)
            if info['state'] == 20:  # RUNNING
                print(f"IOC {name} already running")
                self.pvs[name].set(1)
                return

            result = self.server.supervisor.startProcess(name)
            if result:
                print(f"Started IOC {name}")
                self.pvs[name].set(1)
            else:
                print(f"Failed to start IOC {name}")
                self.pvs[name].set(0)

        except Exception as e:
            print(f"Error starting IOC {name}: {e}")
            self.pvs[name].set(0)

    def _stop_ioc(self, name):
        """Stop an IOC using supervisor"""
        try:
            info = self.server.supervisor.getProcessInfo(name)
            if info['state'] != 20:  # Not RUNNING
                print(f"IOC {name} not running")
                self.pvs[name].set(0)
                return

            result = self.server.supervisor.stopProcess(name)
            if result:
                print(f"Stopped IOC {name}")
                self.pvs[name].set(0)
            else:
                print(f"Failed to stop IOC {name}")

        except Exception as e:
            print(f"Error stopping IOC {name}: {e}")

    def _restart_ioc(self, name):
        """Restart an IOC using supervisor"""
        try:
            # Try to stop first
            try:
                self.server.supervisor.stopProcess(name)
                time.sleep(1)
            except:
                pass  # Process might not be running

            # Start the process
            result = self.server.supervisor.startProcess(name)
            if result:
                print(f"Restarted IOC {name}")
                self.pvs[name].set(1)
            else:
                print(f"Failed to restart IOC {name}")
                self.pvs[name].set(0)

        except Exception as e:
            print(f"Error restarting IOC {name}: {e}")
            self.pvs[name].set(0)

    async def heartbeat(self):
        """Check IOC heartbeats and update status"""
        await asyncio.sleep(self.delay)

        tasks = []
        for name in self.settings.keys():
            if 'general' in name:
                continue
            tasks.append(self._check_ioc_heartbeat(name))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def _check_ioc_heartbeat(self, name):
        """Check heartbeat for a specific IOC"""
        try:
            # Check supervisor status
            info = self.server.supervisor.getProcessInfo(name)
            is_running = info['state'] == 20  # RUNNING state

            if not is_running:
                self.pvs[name + '_hb'].set(999)  # Indicate not running
                if self.pvs[name].get() == 1:  # PV says it should be running
                    self.pvs[name].set(0)  # Update to reflect actual state
                return

            # Check EPICS heartbeat
            try:
                t = await aioca.caget(f"{self.device_name}:{name}_time")
                now = datetime.datetime.now().timestamp()
                heartbeat_age = int(now - float(t))
                self.pvs[name + '_hb'].set(heartbeat_age)

                # Update control PV status based on actual running state
                if self.pvs[name].get() == 0 and is_running:
                    self.pvs[name].set(1)

            except aioca.CANothing:
                # IOC running but EPICS not responding - set high heartbeat
                self.pvs[name + '_hb'].set(120)

        except Exception as e:
            print(f"Heartbeat check error for {name}: {e}")
            self.pvs[name + '_hb'].set(999)


if __name__ == "__main__":
    asyncio.run(main())