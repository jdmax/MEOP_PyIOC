import re
from .telnet_device import TelnetDevice
from softioc import builder


class Device(TelnetDevice):
    """Makes library of PVs needed for MKS937b and provides methods connect them to the device

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
    """

    def _create_pvs(self):
        """Create temperature input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)


class DeviceConnection(TelnetConnection):
    """Handle connection to LM500 level probe"""

    def __init__(self):
        self.read_regex = re.compile(b'.+\r\n(-?\d*\.\d)\s')

    def read_all(self):
        '''Read level.'''
        try:
            self.tn.write(bytes(f"MEAS?\n", 'ascii'))  # 0 means it will return all channels
            i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            return [float(x) for x in match.groups()]

        except Exception as e:
            print(f"LM-500 read failed on {self.host}: {e}, {data}")
            raise OSError('LM-500 read')
