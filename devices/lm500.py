# J. Maxwell 2024
import telnetlib
import re
from softioc import builder, alarm


class Device():
    '''Makes library of PVs needed for Cryomagnetics LM-500 and provides methods connect them to the device

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
            self.pvs[channel] = builder.aIn(channel, **sevr)

    def connect(self):
        '''Open connection to device'''
        try:
            self.t = DeviceConnection(self.settings['ip'], self.settings['port'], self.settings['timeout'])
        except Exception as e:
            print(f"Failed connection on {self.settings['ip']}, {e}")

    def reconnect(self):
        del self.t
        print("Connection failed. Attempting reconnect.")
        self.connect()

    def do_sets(self, new_value, pv):
        """LS218 has no sets"""
        pass

    async def do_reads(self):
        '''Match variables to methods in device driver and get reads from device'''
        try:
            levels = self.t.read_all()
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                self.pvs[channel].set(levels[i])
                self.remove_alarm(channel)
        except OSError:
            for i, channel in enumerate(self.channels):
                if "None" in channel: continue
                self.set_alarm(channel)
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
    '''Handle connection to Lakeshore Model 218 via serial over ethernet. 
    '''
    def __init__(self, host, port, timeout):        
        '''Open connection to Lakeshore 218
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
            print(f"LM-500 connection failed on {self.host}: {e}")

        self.read_regex = re.compile(b'.+\r\n(-?\d*\.\d)\s')
         
    def read_all(self):
        '''Read level.'''
        values = []
        try: 
            self.tn.write(bytes(f"MEAS?\n",'ascii'))     # 0 means it will return all channels
            i, match, data = self.tn.expect([self.read_regex], timeout=self.timeout)
            #print(data)
            return [float(x) for x in match.groups()]
            
        except Exception as e:
            print(f"LM-500 read failed on {self.host}: {e}, {data}")
            raise OSError('LM-500 read')
        