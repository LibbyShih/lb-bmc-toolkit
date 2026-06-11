SDR_RECORD_TYPES = {
    0x01: "Full Sensor Record (Type 01)",
    0x02: "Compact Sensor Record (Type 02)",
    0x03: "Event-Only Record",
    0x08: "Entity Association Record",
    0x09: "Device-relative Entity Association Record",
    0x10: "Generic Device Locator Record",
    0x11: "FRU Device Locator Record",
    0x12: "Management Controller Device Locator Record",
    0x13: "Management Controller Confirmation Record",
    0x14: "BMC Message Channel Info Record",
    0xC0: "OEM Record",
}

# Sensor Unit Base Codes (Table 43-15)
UNIT_CODES = {
    0: "unspecified", 1: "degrees C", 2: "degrees F", 3: "degrees K",
    4: "Volts", 5: "Amps", 6: "Watts", 7: "Joules", 8: "Coulombs",
    9: "VA", 18: "RPM", 19: "Hz", 20: "microsecond", 21: "millisecond",
    22: "second", 23: "minute", 24: "hour", 32: "mm", 33: "cm", 34: "m",
    66: "bit", 70: "byte", 71: "kilobyte", 72: "megabyte", 73: "gigabyte",
    88: "error", 89: "correctable error", 90: "uncorrectable error",
}

ENTITY_IDS = {
    0x01: "Unspecified", 0x02: "Other", 0x03: "Unknown",
    0x04: "Processor", 0x05: "Disk or Disk Bay", 0x06: "Peripheral Bay",
    0x07: "System Management Module", 0x08: "System Board",
    0x09: "Memory Module", 0x0A: "Processor Module",
    0x0B: "Power Supply", 0x0C: "Add-in Card",
    0x0D: "Front Panel Board", 0x0E: "Back Panel Board",
    0x0F: "Power System Board", 0x10: "Drive Backplane",
    0x11: "System Internal Expansion Board", 0x12: "Other System Board",
    0x13: "Processor Board", 0x14: "Power Unit",
    0x15: "Power Module", 0x16: "Power Management",
    0x17: "Chassis Back Panel Board", 0x18: "System Chassis",
    0x1D: "Fan", 0x1E: "Cooling Unit", 0x20: "Cable / Interconnect",
    0x22: "System Management Controller", 0x23: "BIOS",
    0x24: "Intel ME", 0x25: "System Bus",
    0x28: "System Target Board", 0x29: "Processor / IO Module",
    0x2A: "Processor / Memory Module", 0x2B: "I/O Module",
}
