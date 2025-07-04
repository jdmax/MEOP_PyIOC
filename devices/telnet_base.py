import telnetlib
from .base_device import BaseDevice


class TelnetDevice(BaseDevice):
    """Base class for Telnet devices"""

    def _create_connection(self):
        """Create Telnet connection"""
        return TelnetConnection(
            self.settings['ip'],
            self.settings['port'],
            self.settings['timeout']
        )

    def _process_reading(self, channel, raw_value):
        """Process raw reading value. Override in child classes if needed."""
        return raw_value


class TelnetConnection:
    """Generic Telnet connection handler"""

    def __init__(self, host, port, timeout):
        self.host = host
        self.port = port
        self.timeout = timeout

        try:
            self.tn = telnetlib.Telnet(self.host, port=self.port, timeout=self.timeout)
        except Exception as e:
            print(f"Telnet connection failed on {self.host}: {e}")
