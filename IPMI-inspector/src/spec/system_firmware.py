# IPMI 2.0 Table 42-6 / Table 42-7 — System Firmware sensor event data

# Table 42-6: System Firmware Error (POST Error) event data 2 codes
POST_ERROR_CODES = {
    0x00: "Unspecified",
    0x01: "No system memory is physically installed",
    0x02: "No usable system memory, all installed memory has experienced an unrecoverable failure",
    0x03: "Unrecoverable hard-disk/ATAPI/IDE device failure",
    0x04: "Unrecoverable system-board failure",
    0x05: "Unrecoverable diskette subsystem failure",
    0x06: "Unrecoverable hard-disk controller failure",
    0x07: "Unrecoverable PS/2 or USB keyboard failure",
    0x08: "Removable boot media not found",
    0x09: "Unrecoverable video controller failure",
    0x0A: "No video device detected",
    0x0B: "Firmware (BIOS) ROM corruption detected",
    0x0C: "CPU voltage mismatch",
    0x0D: "CPU speed matching failure",
}

# Table 42-7: System Firmware Progress (POST Progress) event data 2 codes
POST_PROGRESS_CODES = {
    0x00: "Unspecified",
    0x01: "Memory initialization",
    0x02: "Hard-disk initialization",
    0x03: "Secondary processor(s) initialization",
    0x04: "User authentication",
    0x05: "User-initiated system setup",
    0x06: "USB resource configuration",
    0x07: "PCI resource configuration",
    0x08: "Option ROM initialization",
    0x09: "Video initialization",
    0x0A: "Cache initialization",
    0x0B: "SM Bus initialization",
    0x0C: "Keyboard controller initialization",
    0x0D: "Embedded controller / management controller initialization",
    0x0E: "Docking station attachment",
    0x0F: "Enabling docking station",
    0x10: "Docking station ejection",
    0x11: "Disabling docking station",
    0x12: "Calling operating system wake-up vector",
    0x13: "Starting operating system boot process",
    0x14: "Baseboard or motherboard initialization",
    0x16: "Floppy initialization",
    0x17: "Keyboard test",
    0x18: "Pointing device test",
    0x19: "Primary processor initialization",
}
