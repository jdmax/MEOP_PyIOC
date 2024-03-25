import telnetlib
import re
import time
from softioc import builder, alarm


class Device():
    '''Makes library of PVs needed for Cryomagnetics CS-4 power supply and provides methods connect them to the device

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

        for channel in settings['channels']:  # set up PVs for each channel
            if "None" in channel: continue
            self.pvs[channel+"_VI"] = builder.aIn(channel+"_VI", **sevr)   # Voltage
            self.pvs[channel+"_CI"] = builder.aIn(channel+"_CI", **sevr)   # Current

            self.pvs[channel + "_CC"] = builder.aOut(channel + "_CC", on_update_name=self.do_sets, **sevr)
            self.pvs[channel + "_VC"] = builder.aOut(channel + "_VC", on_update_name=self.do_sets, **sevr)

            self.pvs[channel + "_Mode"] = builder.boolOut(channel + "_Mode", on_update_name=self.do_sets)


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
            try:
                values = self.t.read_sp(str(i+1))
                self.pvs[pv_name + '_VC'].set(values[0])  # set returned voltage
                self.pvs[pv_name + '_CC'].set(values[1])  # set returned current
                value = self.t.set_state(str(i+1), self.pvs[pv_name].get())
                self.pvs[pv_name + '_Mode'].set(int(value))  # set returned value
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
        chan = self.channels.index(p) + 1  # determine what channel we are on
        # figure out what type of PV this is, and send it to the right method
        try:
            if 'CC' in pv_name or 'VC' in pv_name:  # is this a current set? Voltage set from settings file
                values = self.t.set(chan, self.pvs[p + '_VC'].get(), self.pvs[p + '_CC'].get())
                self.pvs[p + '_VC'].set(values[0])  # set returned voltage
                self.pvs[p + '_CC'].set(values[1])  # set returned current
            elif 'Mode' in pv_name:
                value = self.t.set_state(chan, new_value)
                self.pvs[pv_name].set(int(value))  # set returned value
            else:
                print('Error, control PV not categorized.', pv_name)
        except OSError:
            self.reconnect()
        return

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        new_reads = {}
        ok = True
        for i, channel in enumerate(self.channels):
            if "None" in channel: continue
            try:
                new_reads[channel+'_VI'], new_reads[channel+'_CI'], power = self.t.read(i+1)
                new_reads[channel+'_VC'], new_reads[channel+'_CC'] = self.t.read_sp(i+1)
                new_reads[channel+'_Mode'] = self.t.read_state(i+1)
            except OSError:
                self.set_alarm(channel + "_VI")
                self.reconnect()
                ok = False
            else:
                self.remove_alarm(channel + "_VI")
        for channel, value in new_reads.items():
            self.pvs[channel].set(value)
        return ok

    def set_alarm(self, channel):
        """Set alarm and severity for channel"""
        self.pvs[channel].set_alarm(severity=1, alarm=alarm.READ_ALARM)

    def remove_alarm(self, channel):
        """Remove alarm and severity for channel"""
        self.pvs[channel].set_alarm(severity=0, alarm=alarm.NO_ALARM)


class DeviceConnection():
    '''Handle connection to Cryomagnetics CS-4 via Telnet.
    '''

    def __init__(self, host, port, timeout):
        '''Open connection to Cryomagnetics CS-4, required LAN option unlocked.
        Arguments:
            host: IP address
        port: Port of device
        '''
        self.host = host
        self.port = port
        self.timeout = timeout

        try:
            self.tn = telnetlib.Telnet(self.host, port=self.port, timeout=self.timeout)
        except Exception as e:
            print(f"CS-4 connection failed on {self.host}: {e}")

        self.current_regex = re.compile(b'(\d+.\d+)\sA')
        self.voltage_regex = re.compile(b'(-?\d+.\d+)\sV')
        self.on_off_regex = re.compile(b'(0|1)')
        self.sweep_regex = re.compile(b'SWEEP\?\r\n(.+)\r\n')

    def read_current(self):
        '''Read magnet current.'''
        try:
            command = f"IMAG?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read current failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_out(self):
        '''Read power supply current.'''
        try:
            command = f"IOUT?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read out failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_voltage(self):
        '''Read magnet voltage.'''
        try:
            command = f"VMAG?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.voltage_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read volt failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_ulim(self):
        '''Read upper limit.'''
        try:
            command = f"ULIM?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read ulim failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_llim(self):
        '''Read lower limit.'''
        try:
            command = f"LLIM?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read llim failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_heater(self):
        '''Read heater status.'''
        try:
            command = f"PSHTR?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.on_off_regex], timeout=self.timeout)
            if b'1' in match.groups()[0]:
                return True
            else:
                return False
        except Exception as e:
            print(f"CS-4 read heater failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')

    def read_sweep(self):
        '''Read sweep status. Returns index of status list [up, down, paused, zero] and fast status (True or False).'''
        try:
            command = f"SWEEP?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            i, match, data = self.tn.expect([self.sweep_regex], timeout=self.timeout)
            stat = match.groups()[0]
            fast = True if b'fast' in stat else False
            if b'sweep up' in stat:
                return 0, fast
            elif b'sweep down' in stat:
                return 1, fast
            elif b'sweep paused' in stat:
                return 2, fast
            elif b'zeroing' in stat:
                return 3, fast

        except Exception as e:
            print(f"CS-4 read status failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read sweep')

    def set_ulim(self):
        '''Set upper limit. NOT DONE'''
        try:
            command = f"ULIM\n"
            self.tn.write(bytes(command, 'ascii'))
            i, match, data = self.tn.expect([self.current_regex], timeout=self.timeout)
            return float(match.groups()[0])
        except Exception as e:
            print(f"CS-4 read ulim failed on {self.host}: {e},{command},{data}")
            raise OSError('CS-4 read')


        # self.status.update({'current': {'value': '0', 'query': "IMAG?", 'text': 'Magnet Current (A)'}})
        # self.status.update({'ps_current': {'value': '0', 'query': "IOUT?", 'text': 'Power Supply Current (A)'}})
        # self.status.update({'v_mag': {'value': '0', 'query': "VMAG?", 'text': 'Voltage (V)'}})
        # self.status.update({'up_lim': {'value': '0', 'query': "ULIM?", 'text': 'Upper Limit (A)'}})
        # self.status.update({'low_lim': {'value': '0', 'query': "LLIM?", 'text': 'Lower Limit (A)'}})
        # self.status.update({'sweep': {'value': '0', 'query': "SWEEP?", 'text': 'Sweep Status'}})
        # self.status.update({'switch': {'value': '0', 'query': "PSHTR?", 'text': 'Switch Heater Status'}})
        # # self.status.update({ 'id' :         { 'value' : '0', 'query' : "*IDN?",     'text' : 'Device ID'}})
        #
        # self.commands = {  # command strings
        #     'low_lim': "LLIM ",
        #     'up_lim': "ULIM ",
        #     'ps_on': "PSHTR ON",
        #     'ps_off': "PSHTR OFF",
        #     'sw_up': "SWEEP UP",
        #     'sw_down': "SWEEP DOWN",
        #     'sw_pause': "SWEEP PAUSE",
        #     'sw_zero': "SWEEP ZERO",
        #     'complete': "OPC?"
        # }
