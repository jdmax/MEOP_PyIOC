# J. Maxwell 2023
import telnetlib
import re
from softioc import builder, alarm


class Device():
    '''Makes library of PVs needed for Scientific Instruments 9700 and provides methods connect them to the device

    Attributes:
        pvs: dict of Process Variables keyed by name
        channels: channels of device
    '''
    def __init__(self, device_name, settings):
        '''Make PVs needed for this device and put in pvs dict keyed by name
        '''
        self.device_name = device_name
        self.settings = settings
        self.channels = settings['channels']
        self.pvs = {}
        sevr = {'HHSV': 'MAJOR', 'HSV': 'MINOR', 'LSV': 'MINOR', 'LLSV': 'MAJOR', 'DISP': '0'}
        self.mode_choice = ['STOP', 'NORMAL', 'PROGRAM', 'AUTO_TUNE', 'FIXED']

        for channel in settings['channels']:  # set up PVs for each channel
            if "None" in channel: continue
            self.pvs[channel + "_TI"] = builder.aIn(channel + "_TI", **sevr)  # Voltage
            self.pvs[channel + "_Heater"] = builder.aIn(channel + "_Heater", **sevr)  # Voltage

            self.pvs[channel + "_SP"] = builder.aOut(channel + "_SP", on_update_name=self.do_sets, **sevr)
            self.pvs[channel + "_Mode"] = builder.mbbOut(channel + "_Mode", *self.mode_choice, on_update_name=self.do_sets)

    def connect(self):
        '''Open connection to device'''
        try:
            self.t = DeviceConnection(self.settings['ip'], self.settings['port'], self.settings['timeout'])
            self.read_outs()
        except Exception as e:
            print(f"Failed connection on {self.settings['ip']}, {e}")

    def read_outs(self):
        """Read and set OUT PVs at the start of the IOC"""
        for i, pv_name in enumerate(self.channels):
            if "None" in pv_name: continue
            setpoint, heater, mode = self.t.read_status()
            try:
                self.pvs[pv_name + '_SP'].set(setpoint)
                self.pvs[pv_name + '_Mode'].set(mode)
            except OSError:
                print("Read out error on", pv_name)
                self.reconnect()

    def reconnect(self):
        del self.t
        print("Connection failed. Attempting reconnect.")
        self.connect()

    def do_sets(self, new_value, pv):
        """Set PVs values to device"""
        pv_name = pv.replace(self.device_name + ':', '')  # remove device name from PV to get bare pv_name
        p = pv_name.split("_")[0]  # pv_name root
        # figure out what type of PV this is, and send it to the right method
        try:
            if '_SP' in pv_name:
                value = self.t.set_setpoint(self.pvs[pv_name].get())
                self.pvs[pv_name].set(float(value))  # set returned value
            elif '_Mode' in pv_name:
                value = self.t.set_mode(self.pvs[pv_name].get())
                self.pvs[pv_name].set(float(value))  # set returned value
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()
        return

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        try:
            temps = self.t.read_all()
            setpoint, heater, mode = self.t.read_status()
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                self.pvs[channel+"_TI"].set(temps[i])
                self.pvs[channel+"_Heater"].set(heater)
                self.remove_alarm(channel+"_TI")
        except OSError:
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                self.set_alarm(channel+"_TI")
            self.reconnect()
        else:
            return True

    def set_alarm(self, channel):
        """Set alarm and severity for channel"""
        self.pvs[channel].set_alarm(severity=1, alarm=alarm.READ_ALARM)

    def remove_alarm(self, channel):
        """Remove alarm and severity for channel"""
        self.pvs[channel].set_alarm(severity=0, alarm=alarm.NO_ALARM)


class DeviceConnection():
    '''Handle connection to SI9700 via serial over ethernet.
    '''
    def __init__(self, host, port, timeout):        
        '''Open connection to SI9700
        Arguments:
            host: IP address
            port: Port of device
            timeout: Telnet timeout in secs
        '''
        self.host = host
        self.port = port
        self.timeout = timeout
        
        try:
            self.tn = telnetlib.Telnet(self.host, port=self.port, timeout=self.timeout)                  
        except Exception as e:
            print(f"SI9700 connection failed on {self.host}: {e}")

        self.read_regex = re.compile(b'TALL\s(\d+.\d{4}),(\d+.\d{4})')
        self.status_regex = re.compile(b'STA\s(\d+.\d+),(\d+.\d+),(\d),(\d),(\d),(\d),(\d)')
        self.set_regex = re.compile(b'SET\s(\d+.\d+)')

    def read_all(self):
        '''Read temperatures for all channels.'''
        try:
            self.tn.write(bytes(f"TALL?\r", 'ascii'))  # 0 means it will return all channels
            i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            # print(data)
            return [float(x) for x in match.groups()]

        except Exception as e:
            print(f"SI9700 read failed on {self.host}: {e}")
            raise OSError('SI9700 read')

    def read_status(self):
        '''Read status. Returns setpoint, heater percentage and mode.'''
        try:
            self.tn.write(bytes(f"STA?\r",'ascii'))     # 0 means it will return all channels
            i, match, data = self.tn.expect([self.status_regex], timeout=self.timeout)
            print(data)
            setpoint, heater, mode, alarm, gui, control, zone = match.groups()
            print(float(setpoint), float(heater), int(mode))
            return float(setpoint), float(heater), int(mode)

        except Exception as e:
            print(f"SI9700 status read failed on {self.host}: {e}")
            raise OSError('SI9700 status read')

    def set_setpoint(self, value):
        '''Sets setpoint, returns result'''
        try:
            self.tn.write(bytes(f"SET {value}\r",'ascii'))
            setpoint, heater, mode = self.read_status()
            print("sp",setpoint)
            return setpoint

        except Exception as e:
            print(f"SI9700 set failed on {self.host}: {e}")
            raise OSError('SI9700 set')

    def set_mode(self, value):
        '''Sets mode, returns result'''
        try:
            self.tn.write(bytes(f"MODE {value}\r",'ascii'))
            setpoint, heater, mode = self.read_status()
            print("mode",mode)
            return mode

        except Exception as e:
            print(f"SI9700 set failed on {self.host}: {e}")
            raise OSError('SI9700 set')