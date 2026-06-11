# Table 5-2, IPMI 2.0 spec
GLOBAL_CC = {
    0x00: ("Normal", "成功"),
    0xC0: ("Node Busy", "節點忙碌，稍後重試"),
    0xC1: ("Invalid Command", "NetFn+Cmd 不合法於此 channel/LUN"),
    0xC2: ("Invalid Command for LUN", ""),
    0xC3: ("Timeout", "等待回應逾時"),
    0xC4: ("Out of Space", "內部空間不足，SEL/SDR 已滿"),
    0xC5: ("Reservation Cancelled or Invalid", "Reservation ID 已失效，需重新 Reserve"),
    0xC6: ("Request Data Truncated", ""),
    0xC7: ("Request Data Length Invalid", ""),
    0xC8: ("Request Data Field Length Limit Exceeded", ""),
    0xC9: ("Parameter Out of Range", "資料欄位值超出允許範圍"),
    0xCA: ("Cannot Return Requested Number of Data Bytes", ""),
    0xCB: ("Requested Sensor/Data/Record Not Present", "sensor number 或 record ID 不存在"),
    0xCC: ("Invalid Data Field in Request", ""),
    0xCD: ("Command Illegal for Specified Sensor/Record Type", ""),
    0xCE: ("Command Response Could Not Be Provided", ""),
    0xCF: ("Cannot Execute Duplicate Request", ""),
    0xD0: ("SDR Repository in Update Mode", ""),
    0xD1: ("Device Firmware Update Mode", ""),
    0xD2: ("BMC Initialization or Warm-up in Progress", "BMC 正在初始化，稍後重試"),
    0xD3: ("Destination Unavailable", ""),
    0xD4: ("Insufficient Privilege Level", "當前 privilege 等級不足"),
    0xD5: ("Command Not Supported in Present State", ""),
    0xD6: ("Sub-function Disabled", ""),
    0xFF: ("Unspecified Error", ""),
}

def decode_cc(code: int) -> str:
    if code in GLOBAL_CC:
        name, desc = GLOBAL_CC[code]
        return f"0x{code:02X} {name}" + (f" — {desc}" if desc else "")
    if 0x01 <= code <= 0x7E:
        return f"0x{code:02X} Device-specific OEM error"
    if 0x80 <= code <= 0xBE:
        return f"0x{code:02X} Command-specific error (see spec Table for this command)"
    return f"0x{code:02X} Unknown"
