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
            print(f"DP832 connection failed on {self.host}: {e}")

        self.read_regex = re.compile('CH\d:\d+V/\dA,(\d+.\d+),(\d+.\d+)')
        self.read_sp_regex = re.compile('(\d+.\d+),(\d+.\d+),(\d+.\d+)')

    def read_current(self, channel):
        '''Read current.'''
        try:
            command = f":IMAG?\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            m = self.read_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values   # return voltage, current as list

        except Exception as e:
            print(f"DP832 read sp failed on {self.host}: {e},{command},{data}")
            raise OSError('DP832 read sp')

    def read(self, channel):
        '''Read voltage, current measured for given channel (1,2,3).'''
        try:
            command = f":MEASURE:ALL? CH{channel}\n"
            self.tn.write(bytes(command, 'ascii'))   # Reading
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            m = self.read_sp_regex.search(data)
            values = [float(x) for x in m.groups()]
            return values   # return voltage, current as list

        except Exception as e:
            print(f"DP832 read failed on {self.host}: {e}, {command},{data}")
            raise OSError('DP832 read')

    def set(self, channel, voltage, current):
        '''Set current and voltage for given channel'''
        try:
            self.tn.write(bytes(f":APPLY CH{channel},{voltage},{current}\n", 'ascii'))
            time.sleep(0.2)
            return self.read_sp(channel)   # return voltage, current as list

        except Exception as e:
            print(f"DP832 set failed on {self.host}: {e}")
            raise OSError('DP832 set')

    def read_state(self, channel):
        '''Read output state for given channel.
        Arguments:
            channel: out put channel (1 to 4)
        '''
        try:
            self.tn.write(bytes(f"OUTPUT? CH{channel}\n", 'ascii'))
            data = self.tn.read_until(b'\n', timeout=self.timeout).decode('ascii')  # read until carriage return
            state = True if 'ON' in data else False
            return state

        except Exception as e:
            print(f"DP832 outmode read failed on {self.host}: {e}")
            raise OSError('DP832 outmode read')

    def set_state(self, channel, state):
        '''Setup output state on (true) or off (false).
        Arguments:
            channel: out put channel (1 to 4)
            state: False=Off, True=On
        '''
        out = 'ON' if state else 'OFF'
        try:
            self.tn.write(bytes(f":OUTPUT CH{channel},{out}\n", 'ascii'))
            time.sleep(0.2)
            return self.read_state(channel)
        except Exception as e:
            print(f"DP832 out set failed on {self.host}: {e}")
            raise OSError('DP832 out set')

        self.status.update({'current': {'value': '0', 'query': "IMAG?", 'text': 'Magnet Current (A)'}})
        self.status.update({'ps_current': {'value': '0', 'query': "IOUT?", 'text': 'Power Supply Current (A)'}})
        self.status.update({'v_mag': {'value': '0', 'query': "VMAG?", 'text': 'Voltage (V)'}})
        self.status.update({'up_lim': {'value': '0', 'query': "ULIM?", 'text': 'Upper Limit (A)'}})
        self.status.update({'low_lim': {'value': '0', 'query': "LLIM?", 'text': 'Lower Limit (A)'}})
        self.status.update({'sweep': {'value': '0', 'query': "SWEEP?", 'text': 'Sweep Status'}})
        self.status.update({'switch': {'value': '0', 'query': "PSHTR?", 'text': 'Switch Heater Status'}})
        # self.status.update({ 'id' :         { 'value' : '0', 'query' : "*IDN?",     'text' : 'Device ID'}})

        self.commands = {  # command strings
            'low_lim': "LLIM ",
            'up_lim': "ULIM ",
            'ps_on': "PSHTR ON",
            'ps_off': "PSHTR OFF",
            'sw_up': "SWEEP UP",
            'sw_down': "SWEEP DOWN",
            'sw_pause': "SWEEP PAUSE",
            'sw_zero': "SWEEP ZERO",
            'complete': "OPC?"
        }
