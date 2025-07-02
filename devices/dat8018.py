from .modbus_base import ModbusDevice, ModbusConnection
from softioc import builder


class Device(ModbusDevice):
    """Datexel 8018 Thermocouple Reader"""

    def _create_pvs(self):
        """Create temperature input PVs"""
        for channel in self._skip_none_channels():
            self.pvs[channel] = builder.aIn(channel, **self.sevr)

    def _process_reading(self, channel, raw_value):
        """Convert raw value to temperature (divide by 10)"""
        return raw_value / 10


class DeviceConnection(ModbusConnection):
    """DAT8018-specific connection"""

    def read_all(self):
        """Read temperature values and scale them"""
        try:
            values = self.m.read_input_registers(40, 8)
            return [x / 10 for x in values]  # Temperature scaling
        except Exception as e:
            print(f"Datexel 8018 read failed on {self.host}: {e}")
            raise OSError('8018 read')