import psutil
from softioc import builder
from .base_device import BaseDevice


class Device(BaseDevice):
    """
    Monitor total resource intensity specifically for master_ioc.py instances.
    Calculates aggregate CPU and Memory for all IOCs managed in screens.
    """

    def _create_pvs(self):
        """Create aggregate monitoring PVs"""
        # Aggregate CPU usage of all master_ioc instances
        self.pvs['TOTAL_IOC_CPU'] = builder.aIn(
            f'{self.device_name}:TOTAL_IOC_CPU',
            initial_value=0,
            EGU='%',
            PREC=2,
            **self.sevr
        )

        # Aggregate Memory usage of all master_ioc instances
        self.pvs['TOTAL_IOC_MEM'] = builder.aIn(
            f'{self.device_name}:TOTAL_IOC_MEM',
            initial_value=0,
            EGU='MB',
            PREC=1,
            **self.sevr
        )

        # Count of running master_ioc processes found
        self.pvs['IOC_COUNT'] = builder.longIn(
            f'{self.device_name}:IOC_COUNT',
            initial_value=0,
            **self.sevr
        )

    def _create_connection(self):
        """No hardware connection; returns a list of target keywords for filtering"""
        return ['python', 'master_ioc.py']

    async def do_reads(self):
        """Filter process tree and sum usage for master_ioc.py instances"""
        total_cpu = 0.0
        total_mem_rss = 0.0
        ioc_count = 0

        try:
            # Iterate through all processes on the server
            for proc in psutil.process_iter(['name', 'cmdline', 'cpu_percent', 'memory_info']):
                try:
                    # 1. Check if the process is Python
                    if 'python' in (proc.info['name'] or '').lower():
                        cmdline = proc.info['cmdline'] or []

                        # 2. Check if 'master_ioc.py' is in the arguments
                        if any('master_ioc.py' in arg for arg in cmdline):
                            # interval=None returns usage since last call non-blockingly
                            total_cpu += proc.cpu_percent(interval=None)
                            total_mem_rss += proc.info['memory_info'].rss / (1024 * 1024)
                            ioc_count += 1

                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue

            # Update PVs with the sum of all found IOCs
            self.pvs['TOTAL_IOC_CPU'].set(total_cpu)
            self.pvs['TOTAL_IOC_MEM'].set(total_mem_rss)
            self.pvs['IOC_COUNT'].set(ioc_count)

            self._handle_read_success(['TOTAL_IOC_CPU', 'TOTAL_IOC_MEM', 'IOC_COUNT'])

        except Exception as e:
            print(f"Error aggregating IOC group health: {e}")
            self._handle_read_error(['TOTAL_IOC_CPU', 'TOTAL_IOC_MEM', 'IOC_COUNT'])