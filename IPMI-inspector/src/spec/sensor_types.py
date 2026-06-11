# Table 42-3: Sensor Type Codes and Data

SENSOR_TYPES = {
    0x01: {
        "name": "Temperature",
        "events": {
            0: ("Lower Non-critical - going low", "", ""),
            1: ("Lower Non-critical - going high", "", ""),
            2: ("Lower Critical - going low", "", ""),
            3: ("Lower Critical - going high", "", ""),
            4: ("Lower Non-recoverable - going low", "", ""),
            5: ("Lower Non-recoverable - going high", "", ""),
            6: ("Upper Non-critical - going low", "", ""),
            7: ("Upper Non-critical - going high", "", ""),
            8: ("Upper Critical - going low", "", ""),
            9: ("Upper Critical - going high", "", ""),
            10: ("Upper Non-recoverable - going low", "", ""),
            11: ("Upper Non-recoverable - going high", "", ""),
        }
    },
    0x02: {
        "name": "Voltage",
        "events": {
            # Uses standard threshold events (Event/Reading type 0x01)
        }
    },
    0x03: {
        "name": "Current",
        "events": {}
    },
    0x04: {
        "name": "Fan",
        "events": {}
    },
    0x05: {
        "name": "Physical Security",
        "events": {
            0: ("General Chassis Intrusion", "", ""),
            1: ("Drive Bay intrusion", "", ""),
            2: ("I/O Card area intrusion", "", ""),
            3: ("Processor area intrusion", "", ""),
            4: ("System disconnected from LAN", "", ""),
            5: ("Unauthorized dock", "", ""),
            6: ("FAN area intrusion", "", ""),
        }
    },
    0x07: {
        "name": "Processor",
        "events": {
            0: ("IERR", "", ""),
            1: ("Thermal Trip", "", ""),
            2: ("FRB1/BIST failure", "", ""),
            3: ("FRB2/Hang in POST failure", "", ""),
            4: ("FRB3/Processor Startup/Initialization failure", "", ""),
            5: ("Configuration Error", "", ""),
            6: ("SM BIOS 'Uncorrectable CPU-complex Error'", "", ""),
            7: ("Processor Presence detected", "", ""),
            8: ("Processor disabled", "", ""),
            9: ("Terminator Presence Detected", "", ""),
            10: ("Processor Automatically Throttled", "", ""),
            11: ("Machine Check Exception (MCE)", "", ""),
        }
    },
    0x08: {
        "name": "Power Supply",
        "events": {
            0: ("Presence detected", "", ""),
            1: ("Power Supply Failure detected", "", ""),
            2: ("Predictive Failure", "", ""),
            3: ("Power Supply AC lost", "", ""),
            4: ("AC lost or out-of-range", "", ""),
            5: ("AC out-of-range, but present", "", ""),
            6: ("Configuration error", "", ""),
        }
    },
    0x09: {
        "name": "Power Unit",
        "events": {
            0: ("PowerOff / Power Down", "", ""),
            1: ("Power Cycle", "", ""),
            2: ("240VA Power Down", "", ""),
            3: ("Interlock Power Down", "", ""),
            4: ("AC lost", "", ""),
            5: ("Soft Power Control Failure", "", ""),
            6: ("Power Unit Failure detected", "", ""),
            7: ("Predictive Failure", "", ""),
        }
    },
    0x0C: {
        "name": "Memory",
        "events": {
            0: ("Correctable ECC", "", ""),
            1: ("Uncorrectable ECC", "", ""),
            2: ("Parity", "", ""),
            3: ("Memory Scrub Failed", "", ""),
            4: ("Memory Device Disabled", "", ""),
            5: ("Correctable ECC logging limit reached", "", ""),
            6: ("Presence detected", "", ""),
            7: ("Configuration error", "", ""),
            8: ("Spare", "", ""),
            9: ("Memory Automatically Throttled", "", ""),
            10: ("Critical Overtemperature", "", ""),
        }
    },
    0x0D: {
        "name": "Drive Slot",
        "events": {
            0: ("Drive Presence", "", ""),
            1: ("Drive Fault", "", ""),
            2: ("Predictive Failure", "", ""),
            3: ("Hot Spare", "", ""),
            4: ("Consistency Check / Parity Check in progress", "", ""),
            5: ("In-band Network Link Down", "", ""),
            6: ("Critical Array Member Fault", "", ""),
            7: ("Array Member Rebuilding", "", ""),
        }
    },
    0x0F: {
        "name": "System Firmware",
        "events": {
            0: ("System Firmware Error (POST Error)", "See POST_ERROR_CODES", ""),
            1: ("System Firmware Hang", "", ""),
            2: ("System Firmware Progress", "See POST_PROGRESS_CODES", ""),
        }
    },
    0x10: {
        "name": "Event Logging Disabled",
        "events": {
            0: ("Correctable Memory Error Logging Disabled", "", ""),
            1: ("Event Logging Disabled", "", ""),
            2: ("Log Area Reset/Cleared", "", ""),
            3: ("All Event Logging Disabled", "", ""),
            4: ("SEL Full", "", ""),
            5: ("SEL Almost Full", "", ""),
        }
    },
    0x11: {
        "name": "Watchdog 1",
        "events": {
            0: ("BIOS Watchdog Reset", "", ""),
            1: ("OS Watchdog Reset", "", ""),
            2: ("OS Watchdog Shut Down", "", ""),
            3: ("OS Watchdog Power Down", "", ""),
            4: ("OS Watchdog Power Cycle", "", ""),
            5: ("OS Watchdog NMI / Diagnostic Interrupt", "", ""),
            6: ("OS Watchdog Expired, status only", "", ""),
            7: ("OS Watchdog pre-timeout Interrupt", "", ""),
        }
    },
    0x12: {
        "name": "System Event",
        "events": {
            0: ("System Reconfigured", "", ""),
            1: ("OEM System Boot Event", "", ""),
            2: ("Undetermined system hardware failure", "", ""),
            3: ("Entry added to Auxiliary Log", "", ""),
            4: ("PEF Action", "", ""),
            5: ("Timestamp Clock Synch", "", ""),
        }
    },
    0x13: {
        "name": "Critical Interrupt",
        "events": {
            0: ("Front Panel NMI / Diagnostic Interrupt", "", ""),
            1: ("Bus Timeout", "", ""),
            2: ("I/O channel check NMI", "", ""),
            3: ("Software NMI", "", ""),
            4: ("PCI PERR", "", ""),
            5: ("PCI SERR", "", ""),
            6: ("EISA Fail Safe Timeout", "", ""),
            7: ("Bus Correctable Error", "", ""),
            8: ("Bus Uncorrectable Error", "", ""),
            9: ("Fatal NMI", "", ""),
            10: ("Bus Fatal Error", "", ""),
            11: ("Bus Degraded", "", ""),
        }
    },
    0x14: {
        "name": "Button/Switch",
        "events": {
            0: ("Power Button pressed", "", ""),
            1: ("Sleep Button pressed", "", ""),
            2: ("Reset Button pressed", "", ""),
            3: ("FRU Latch open", "", ""),
            4: ("FRU Service Request button", "", ""),
        }
    },
    0x19: {
        "name": "Chip Set",
        "events": {
            0: ("Soft Power Control Failure", "", ""),
            1: ("Thermal Trip", "", ""),
        }
    },
    0x1D: {
        "name": "System Boot Initiated",
        "events": {
            0: ("Initiated by power up", "", ""),
            1: ("Initiated by hard reset", "", ""),
            2: ("Initiated by warm reset", "", ""),
            3: ("User requested PXE boot", "", ""),
            4: ("Automatic boot to diagnostic", "", ""),
            5: ("OS initiated hard reset", "", ""),
            6: ("OS initiated warm reset", "", ""),
            7: ("System Restart", "", ""),
        }
    },
    0x1E: {
        "name": "Boot Error",
        "events": {
            0: ("No bootable media", "", ""),
            1: ("Non-bootable diskette left in drive", "", ""),
            2: ("PXE Server not found", "", ""),
            3: ("Invalid boot sector", "", ""),
            4: ("Timeout waiting for user selection", "", ""),
        }
    },
    0x1F: {
        "name": "OS Boot",
        "events": {
            0: ("A: boot completed", "", ""),
            1: ("C: boot completed", "", ""),
            2: ("PXE boot completed", "", ""),
            3: ("Diagnostic boot completed", "", ""),
            4: ("CD-ROM boot completed", "", ""),
            5: ("ROM boot completed", "", ""),
            6: ("boot completed - boot device not specified", "", ""),
            7: ("OS Installation started", "", ""),
            8: ("OS Installation completed", "", ""),
        }
    },
    0x20: {
        "name": "OS Stop / Shutdown",
        "events": {
            0: ("Critical stop during OS load", "", ""),
            1: ("Runtime Critical Stop", "", ""),
            2: ("OS Graceful Stop", "", ""),
            3: ("OS Graceful Shutdown", "", ""),
            4: ("PEF initiated Soft Shutdown", "", ""),
            5: ("Agent Not Responding", "", ""),
        }
    },
    0x21: {
        "name": "Slot/Connector",
        "events": {
            0: ("Fault Status Asserted", "", ""),
            1: ("Identify Status Asserted", "", ""),
            2: ("Slot / Connector Device installed/attached", "", ""),
            3: ("Slot / Connector Ready for Device Installation", "", ""),
            4: ("Slot/Connector Ready for Device Removal", "", ""),
            5: ("Slot Power is Off", "", ""),
            6: ("Slot / Connector Device Removal Request", "", ""),
            7: ("Interlock Asserted", "", ""),
            8: ("Slot is Disabled", "", ""),
            9: ("Slot holds spare device", "", ""),
        }
    },
    0x22: {
        "name": "System ACPI Power State",
        "events": {
            0: ("S0 / G0 working", "", ""),
            1: ("S1 sleeping with system hw & processor context maintained", "", ""),
            2: ("S2 sleeping, processor context lost", "", ""),
            3: ("S3 sleeping, processor & hw context lost, memory retained", "", ""),
            4: ("S4 non-volatile sleep / suspend-to-disk", "", ""),
            5: ("S5 / G2 soft-off", "", ""),
            6: ("S4 / S5 soft-off", "", ""),
            7: ("G3 / Mechanical Off", "", ""),
            8: ("Sleeping in an S1, S2, or S3 states", "", ""),
            9: ("G1 sleeping", "", ""),
            10: ("S5 entered by override", "", ""),
            11: ("Legacy ON state", "", ""),
            12: ("Legacy OFF state", "", ""),
            14: ("Unknown", "", ""),
        }
    },
    0x23: {
        "name": "Watchdog 2",
        "events": {
            0: ("Timer expired", "", ""),
            1: ("Hard Reset", "", ""),
            2: ("Power Down", "", ""),
            3: ("Power Cycle", "", ""),
            4: ("reserved", "", ""),
            5: ("reserved", "", ""),
            6: ("reserved", "", ""),
            7: ("reserved", "", ""),
            8: ("Timer interrupt", "", ""),
        }
    },
    0x28: {
        "name": "Management Subsystem Health",
        "events": {
            0: ("Sensor access degraded or unavailable", "", ""),
            1: ("Controller access degraded or unavailable", "", ""),
            2: ("Management controller off-line", "", ""),
            3: ("Management controller unavailable", "", ""),
            4: ("Sensor failure", "", ""),
            5: ("FRU failure", "", ""),
        }
    },
    0x29: {
        "name": "Battery",
        "events": {
            0: ("Low", "", ""),
            1: ("Failed", "", ""),
            2: ("Presence Detected", "", ""),
        }
    },
    0x2B: {
        "name": "Version Change",
        "events": {
            0: ("Hardware change detected", "", ""),
            1: ("Firmware or software change detected", "", ""),
            2: ("Hardware incompatibility detected", "", ""),
            3: ("Firmware or software incompatibility detected", "", ""),
            4: ("Entity is of an invalid or unsupported hardware version", "", ""),
            5: ("Entity contains an invalid or unsupported firmware or software version", "", ""),
            6: ("Hardware Change successful", "", ""),
            7: ("Software or F/W Change successful", "", ""),
        }
    },
    0x2C: {
        "name": "FRU State",
        "events": {
            0: ("Not Installed", "", ""),
            1: ("Inactive", "", ""),
            2: ("Activation Requested", "", ""),
            3: ("Activation in Progress", "", ""),
            4: ("Active", "", ""),
            5: ("Deactivation Requested", "", ""),
            6: ("Deactivation in Progress", "", ""),
            7: ("Communication lost", "", ""),
        }
    },
}
