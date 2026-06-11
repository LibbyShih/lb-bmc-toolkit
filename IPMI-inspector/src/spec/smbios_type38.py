# SMBIOS Type 38: IPMI Device Information (SMBIOS v3.6.0, Section 7.39)

SMBIOS_TYPE38_FIELDS = {
    0x04: ("Interface Type", {
        0x00: "Unknown",
        0x01: "KCS (Keyboard Controller Style)",
        0x02: "SMIC (Server Management Interface Chip)",
        0x03: "BT (Block Transfer)",
        0x04: "SSIF (SMBus System Interface)",
    }),
    0x05: ("IPMI Specification Version", "BCD: upper nibble=major, lower nibble=minor"),
    0x06: ("I2C Slave Address",
           "7-bit BMC I2C slave address (shift right 1 = actual addr, typically 0x10 → 0x20)"),
    0x07: ("NV Storage Device Address", "0xFF if not present"),
    0x08: ("Base Address",
           "64-bit LE: [0]=0 for Memory-mapped, 1 for I/O port"),
    0x10: ("Interrupt Number", "IRQ number, 0=not used"),
}

def decode_smbios_type38(raw: bytes) -> dict:
    """
    Decode SMBIOS Type 38 record.
    Returns: {interface_type, ipmi_version, i2c_addr, base_addr, irq}
    """
    if len(raw) < 0x11:
        return {}
    
    interface_type_code = raw[0x04]
    interface_type = SMBIOS_TYPE38_FIELDS[0x04][1].get(interface_type_code, f"Reserved (0x{interface_type_code:02X})")
    
    ipmi_version_raw = raw[0x05]
    ipmi_version = f"{ipmi_version_raw >> 4}.{ipmi_version_raw & 0x0F}"
    
    i2c_addr = raw[0x06]
    
    nv_storage = raw[0x07]
    
    base_addr = int.from_bytes(raw[0x08:0x10], byteorder='little')
    
    irq = raw[0x10]
    
    return {
        "interface_type": interface_type,
        "ipmi_version": ipmi_version,
        "i2c_addr": f"0x{i2c_addr:02X}",
        "nv_storage_addr": f"0x{nv_storage:02X}",
        "base_addr": f"0x{base_addr:016X}",
        "irq": irq
    }
