NM_IANA = bytes([0x57, 0x01, 0x00])  # IANA 0x000157 in LE

NM_COMMANDS = {
    0xC0: ("Enable/Disable Node Manager Policy Control",
           "Byte0(after IANA): [1]=Global Policy Enable, [0]=Per-Policy Enable"),
    0xC1: ("Set Node Manager Policy",
           "Policy ID, Domain ID, Policy Trigger Type, Configuration Action, "
           "Policy Target Limit(W), Correction Time(ms), Policy Trigger Limit, "
           "Statistics Reporting Period"),
    0xC2: ("Get Node Manager Policy",
           "回傳 Set 的所有欄位 + Policy State"),
    0xC3: ("Set Node Manager Policy Alert Thresholds",
           "最多 3 組 Alert Threshold Limit"),
    0xC4: ("Get Node Manager Policy Alert Thresholds", ""),
    0xC5: ("Set Node Manager Policy Suspend Periods",
           "最多 5 組 Suspend Period（星期幾 + 時間區間）"),
    0xC6: ("Get Node Manager Policy Suspend Periods", ""),
    0xC7: ("Reset Node Manager Statistics", "Domain ID + 統計類別"),
    0xC8: ("Get Node Manager Statistics",
           "Mode: 0x01=Global Power, 0x02=Per Policy Power, 0x11=Global Inlet Temp, "
           "0x12=Per Policy Inlet Temp, 0x1B=Global Throttling Stats. "
           "回傳: Current, Min, Max, Avg, Timestamp, Reporting Period, Domain ID, Policy State"),
    0xC9: ("Get Node Manager Capabilities",
           "Domain ID + Policy Trigger Type → Max/Min Power Limit, Correction Time range, "
           "Max/Min Statistics Period, Max Concurrent Policies"),
    0xCA: ("Get Node Manager Version",
           "回傳: NM Version, IPMI Interface Version, Patch Version, "
           "Major Firmware Rev, Minor Firmware Rev"),
    0xCB: ("Get NM Self-Test Results", ""),
    0xD3: ("Get Limiting Policy ID",
           "查詢目前正在限制功率的 Policy ID"),
    0xF0: ("Set NM Power Draw Range", "CPU min/max power draw"),
    0xF2: ("Get NM Health Status", "回傳 Domain + 健康狀態 bitmap"),
}

NM_DOMAINS = {
    0x00: "Entire Platform",
    0x01: "CPU Subsystem",
    0x02: "Memory Subsystem",
    0x03: "HW Protection",
    0x04: "High Power I/O Subsystem",
}

NM_TRIGGER_TYPES = {
    0x00: "No Policy Trigger (always active)",
    0x01: "Inlet Temperature Trigger",
    0x02: "Missing Power Reading Timeout",
    0x03: "Time After Platform Reset Trigger",
    0x04: "Boot Time Policy",
}
