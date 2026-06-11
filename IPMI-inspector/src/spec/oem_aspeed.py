# ASPEED OEM commands (OpenBMC ipmi-oem / ASPEED SDK)

# Group Extension (NetFn 0x2C / PICMG)
PICMG_COMMANDS = {
    0x00: ("Get PICMG Properties", ""),
    0x01: ("Get Address Info", ""),
    0x02: ("Get Shelf Address Info", ""),
    0x03: ("Set Shelf Address Info", ""),
    0x04: ("FRU Control", "reset/reboot/graceful reboot/diagnostic interrupt"),
    0x05: ("Get FRU LED Properties", ""),
    0x06: ("Get LED Color Capabilities", ""),
    0x07: ("Set FRU LED State", "off/blinking/on"),
    0x08: ("Get FRU LED State", ""),
    0x09: ("Set IPMB State", ""),
    0x0A: ("Set FRU Activation Policy", ""),
    0x0B: ("Get FRU Activation Policy", ""),
    0x0C: ("Set FRU Activation", ""),
    0x0D: ("Get Device Locator Record ID", ""),
    0x0E: ("Set Port State", ""),
    0x0F: ("Get Port State", ""),
}

ASPEED_OEM_NETFN = 0x30

ASPEED_OEM_COMMANDS = {
    0x07: ("Set Power Cap", "DCMI-like power capping"),
    0x08: ("Get Power Cap", ""),
    0x1B: ("Get Sensor Info", "raw sensor reading with ASPEED extension"),
    0x39: ("Master Write-Read I2C", "master write-read on ASPEED I2C bus"),
    0x41: ("Get GPIO Value", "讀取 GPIO 腳位值"),
    0x42: ("Set GPIO Value", "設定 GPIO 狀態"),
    0x43: ("Get GPIO Direction", ""),
    0x44: ("Set GPIO Direction", ""),
    0x0D: ("Get IPMI Firmware Version", "ASPEED 延伸韌體資訊"),
    0x70: ("Get Slot Info", "chassis slot 資訊"),
}

ASPEED_OEM_NETFN2 = 0x34
ASPEED_OEM2_COMMANDS = {
    0x01: ("Set NIC Status", ""),
    0x02: ("Get NIC Status", ""),
}

def lookup_oem(netfn: int, cmd: int) -> str | None:
    if netfn in (0x2C, 0x2D):
        entry = PICMG_COMMANDS.get(cmd)
    elif netfn in (ASPEED_OEM_NETFN, ASPEED_OEM_NETFN + 1):
        entry = ASPEED_OEM_COMMANDS.get(cmd)
    elif netfn in (ASPEED_OEM_NETFN2, ASPEED_OEM_NETFN2 + 1):
        entry = ASPEED_OEM2_COMMANDS.get(cmd)
    else:
        return None
    if entry:
        name, desc = entry
        return f"{name}" + (f" — {desc}" if desc else "")
    return None
