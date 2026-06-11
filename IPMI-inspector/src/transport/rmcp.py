from pyghmi.ipmi.command import Command


def _ipmi_error_message(exc: Exception) -> str:
    """pyghmi often raises IpmiException with errormsg=None → str 'None'."""
    msg = str(exc).strip()
    if msg and msg != 'None':
        lower = msg.lower()
        if 'session' in lower or 'busy' in lower or 'resource' in lower:
            return f'{msg}（若 ToolEntry 已連線同一台 BMC，請先斷開 IPMI）'
        return msg
    name = type(exc).__name__
    if name == 'IpmiException':
        return 'IPMI 連線失敗（請確認 Host、Port、帳號與密碼；若 ToolEntry 已連線請先斷開）'
    return f'{name}: IPMI 連線失敗'


class BMCConnection:
    def __init__(self, host, username, password, port=623):
        self.host = host
        self.username = username
        self.password = password
        self.port = port
        self._ipmi = None
        
    def connect(self):
        if not self._ipmi:
            self._ipmi = Command(bmc=self.host, userid=self.username, password=self.password, port=self.port)
            
    def get_sensors(self):
        self.connect()
        # Returns list of dicts with sensor data
        # Example pyghmi return format: list of objects with name, value, units, states, health
        sensor_data = []
        try:
            sensors = self._ipmi.get_sensor_data()
            for s in sensors:
                sensor_data.append({
                    "name": s.name,
                    "value": s.value,
                    "units": s.units,
                    "health": s.health,
                    "states": s.states
                })
        except Exception as e:
            print(f"Error getting sensors for {self.host}: {e}")
        return sensor_data
        
    def get_sel(self):
        self.connect()
        try:
            return self._ipmi.get_sel()
        except Exception as e:
            print(f"Error getting SEL for {self.host}: {e}")
            return []
            
    def get_power(self):
        self.connect()
        try:
            return self._ipmi.get_power()
        except Exception as e:
            print(f"Error getting power status for {self.host}: {e}")
            return "unknown"
            
    def set_power(self, state):
        self.connect()
        try:
            return self._ipmi.set_power(state)
        except Exception as e:
            print(f"Error setting power status for {self.host}: {e}")
            return "error"
            
    def raw_command(self, netfn: int, command: int, data=None):
        self.connect()
        if data is None:
            data = ()
        try:
            res = self._ipmi.raw_command(netfn=netfn, command=command, data=data)
            return {"data": list(res.get('data', [])), "error": res.get("error")}
        except Exception as e:
            return {"error": str(e)}
            
    def get_health(self):
        self.connect()
        try:
            return self._ipmi.get_health()
        except Exception as e:
            return {"health": "unknown", "error": str(e)}
            
    def disconnect(self):
        # pyghmi automatically manages keepalives, but we can clear the reference
        self._ipmi = None
