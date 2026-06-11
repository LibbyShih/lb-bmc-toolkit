# DCMI Commands (DCMI v1.5, NetFn 0x2C with Group Extension byte 0xDC)
DCMI_IANA = 0xDC

DCMI_COMMANDS = {
    0x01: ("Get DCMI Capabilities Info",
           "子參數：0x01=Supported Capabilities, 0x02=Mandatory Platform Attrs, "
           "0x03=Optional Platform Attrs, 0x04=Manageability Access Attrs, "
           "0x05=Enhanced System Power Statistics Attrs"),
    0x02: ("Get Power Reading",
           "Mode: 0x01=System Power Statistics, 0x02=Enhanced System Power Statistics. "
           "回傳: Current Power(W), Min Power, Max Power, Avg Power, Timestamp, "
           "Sampling Duration, Power Reading State"),
    0x03: ("Get Power Limit",
           "回傳: Exception Actions, Power Limit(W), Correction Time(ms), "
           "Sampling Period(s), Activate/Deactivate state"),
    0x04: ("Set Power Limit",
           "設定: Exception Actions[0]=硬關機, [1]=記錄 SEL, "
           "Power Limit(W) LE16, Correction Time(ms) LE32, Sampling Period(s) LE16"),
    0x05: ("Activate / Deactivate Power Limit",
           "Byte1: 0x00=Deactivate, 0x01=Activate"),
    0x06: ("Get Asset Tag", "讀取 DCMI Asset Tag（最多 16 bytes）"),
    0x08: ("Get DCMI Sensor Info",
           "列出特定 Entity ID 的 IPMI sensor（用於 DCMI inlet temp 等）"),
    0x09: ("Set Asset Tag", ""),
    0x0A: ("Get Management Controller Identifier String", ""),
    0x0B: ("Set Management Controller Identifier String", ""),
    0x10: ("Set DCMI Configuration Parameters", ""),
    0x11: ("Get DCMI Configuration Parameters", ""),
    0x12: ("Get Temperature Reading",
           "Inlet/Outlet/CPU/Memory 溫度，一次最多回傳 8 個"),
}

POWER_READING_FIELDS = {
    "current_power":  "目前瞬間功率（Watts）",
    "min_power":      "統計期間最小值",
    "max_power":      "統計期間最大值",
    "avg_power":      "統計期間平均值",
    "timestamp":      "最後統計時間（Unix epoch）",
    "stat_period":    "統計時間長度（ms）",
    "reading_state":  "Bit[6]=Active Power Measurement, Bit[5]=Pre-Init Power Measurement",
}
