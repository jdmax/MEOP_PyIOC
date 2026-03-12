import re

from .base_device import BaseDevice
from alicat import FlowController
from softioc import builder
import asyncio


class Device(BaseDevice):
    """ALICAT mcw Flow controller"""

    def _create_pvs(self):
        """Create level input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel + "_FI"] = builder.aIn(channel + "_FI", **self.sevr)  # Mass flow
            self.pvs[channel + "_PI"] = builder.aIn(channel + "_PI", **self.sevr)  # Pressure
            self.pvs[channel + "_CI"] = builder.aIn(channel + "_CI", **self.sevr)  # Control (flow or pressure)
            self.pvs[channel + "_TI"] = builder.aIn(channel + "_TI", **self.sevr)  # Temperature (C)

            self.pvs[channel + "_SP"] = builder.aOut(channel + "_SP", **self.sevr)  # Setpoint


    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    async def do_reads(self):
        """Read from Alicat"""
        await self.t.read_all()

    def do_sets(self, new_value, pv):
        """Set PV values to device"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name
        p = pv_name.split("_")[0]  # pv_name root

        try:
            if '_ULIM' in pv_name:
                value = self.t.set_ulim(self.pvs[p + '_ULIM'].get())
                self.pvs[pv_name].set(float(value))
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()


class DeviceConnection():
    """Handle connection to Alicat MCW Flow Controller through 'alicat' Python interface"""

    def __init__(self, host, port, timeout):
        super().__init__(host, port, timeout)
        
        try:
            self.fc = FlowController(address = host)
        except Exception as e:
            print(f"Alicat Connection failed on {self.host}: {e}")

    async def read_all(self):
        """Read from device"""
        try:
            dict = await self.fc.get()
            values = [float(m) for m in ms]
            if not values:
                raise OSError('AMI136 read')
            return values
        except Exception as e:
            print(f"AMI136 read failed on {self.host}: {e}")
            raise OSError('AMI136 read')