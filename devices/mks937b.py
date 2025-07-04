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
    """Handle connection to Lakeshore Model 218 via serial over ethernet"""

    def __init__(self):
        self.read_regex = re.compile('ACK(.*)\s(.*)\s(.*)\s(.*)\s(.*)\s(.*);FF')

    def read_all(self):
        '''Read pressures for all channels.'''
        try:
            command = "@" + self.address + "PRZ?;FF"  # @003PRZ?;FF
            self.tn.write(bytes(command, 'ascii'))
            data = self.tn.read_until(b';FF', timeout=self.timeout).decode('ascii')
            m = self.read_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values

        except Exception as e:
            print(f"MKS 937B read failed on {self.host}: {e}")
            raise OSError('MKS 937B read')
