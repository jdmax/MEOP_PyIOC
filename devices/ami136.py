import re
from .telnet_device import TelnetDevice
from softioc import builder


class Device(TelnetDevice):
    """AMI Model 136 Level Monitor"""

    def _create_pvs(self):
        """Create level input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)


class DeviceConnection(TelnetConnection):
    """Handle connection to AMI Model 136 via serial over ethernet"""

    def __init__(self):

        self.read_regex = re.compile('(\d+.\d+)')

    def read_all(self):
        """Read level from device"""
        try:
            self.tn.write(bytes(f"LEVEL\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')
            ms = self.read_regex.findall(data)
            values = [float(m) for m in ms]
            if not values:
                raise OSError('AMI136 read')
            return values
        except Exception as e:
            print(f"AMI136 read failed on {self.host}: {e}")
            raise OSError('AMI136 read')