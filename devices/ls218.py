import re
from .telnet_device import TelnetDevice
from softioc import builder


class Device(TelnetDevice):
    """Lakeshore 218 Temperature Monitor"""

    def _create_pvs(self):
        """Create temperature input PVs for each channel"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    async def do_reads(self):
        """Read temperatures and update PVs"""
        try:
            temps = self.t.read_all()
            for i, channel in enumerate(self._skip_none_channels()):
                self.pvs[channel].set(temps[i])
            self._handle_read_success()
            return True
        except OSError:
            self._handle_read_error()
            return False


class DeviceConnection(TelnetConnection):
    """Handle connection to Lakeshore Model 218 via serial over ethernet"""

    def __init__(self):

        self.read_regex = re.compile('([+-]\d+.\d+)')

    def read_all(self):
        """Read temperatures for all channels"""
        try:
            self.tn.write(bytes(f"KRDG? 0\n", 'ascii'))  # 0 means all channels
            data = self.tn.read_until(b'\n', timeout=2).decode('ascii')
            ms = self.read_regex.findall(data)
            return [float(m) for m in ms]
        except Exception as e:
            print(f"LS218 read failed on {self.host}: {e}")
            raise OSError('LS218 read')
