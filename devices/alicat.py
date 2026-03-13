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
            self.pvs[channel + "_TI"] = builder.aIn(channel + "_TI", **self.sevr)  # Temperature (C)
            self.pvs[channel + "_CI"] = builder.aIn(channel + "_CI", **self.sevr)  # Control (flow or pressure)

            self.pvs[channel + "_SP"] = builder.aOut(channel + "_SP", **self.sevr)  # Setpoint


    def _create_connection(self):
        return DeviceConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout'],
            self.settings['gas_type']
        )

    async def do_reads(self):
        """Read from Alicat"""
        try:
            dict = await self.t.read_all()
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                self.pvs[channel+"_FI"].set(dict['mass_flow'])
                self.pvs[channel+"_PI"].set(dict['pressure'])
                self.pvs[channel+"_TI"].set(dict['temperature'])
                self.pvs[channel+"_CI"].set(dict['control_point'])
            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False

    async def read_outs(self):
        """Read and set OUT PVs at the start of the IOC"""
        for pv_name in self._skip_none_channels():
            try:
                dict = await self.t.read_all()
                self.pvs[pv_name + '_SP'].set(dict['setpoint'])
            except OSError:
                print("Read out error on", pv_name)
                self.reconnect()

    def do_sets(self, new_value, pv):
        """Set PV values to device"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name
        p = pv_name.split("_")[0]  # pv_name root

        try:
            if '_SP' in pv_name:
                value = self.t.set_flow_rate(self.pvs[p + '_SP'].get())
                self.pvs[pv_name].set(float(value))
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()


class DeviceConnection():
    """Handle connection to Alicat MCW Flow Controller through 'alicat' Python interface"""

    def __init__(self, host, port, timeout, gas_type):

        try:
            self.fc = FlowController(address = host)
            self.fc.set_gas(gas_type)
        except Exception as e:
            print(f"Alicat Connection failed on {self.host}: {e}")

    async def read_all(self):
        """Read from device"""
        try:
            dict = await self.fc.get()
            return dict
        except Exception as e:
            print(f"Alicat read failed on {self.host}: {e}")
            raise OSError('Alicat read')


    async def set_flow_rate(self, rate):
        """Set flow rate set point"""
        await self.fc.set_flow_rate(rate)