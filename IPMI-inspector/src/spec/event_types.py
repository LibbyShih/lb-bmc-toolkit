# Table 42-1: Event/Reading Type Codes
EVENT_TYPE_NAMES = {
    0x00: "Unspecified",
    0x01: "Threshold",
    0x02: "DMI Usage State",
    0x03: "Digital/Discrete — Availability",
    0x04: "Digital/Discrete — Availability (2)",
    0x05: "Digital/Discrete — Predictive Failure",
    0x06: "Digital/Discrete — Limit",
    0x07: "Digital/Discrete — Performance",
    0x08: "Digital/Discrete — Severity",
    0x09: "Digital/Discrete — Presence",
    0x0A: "Digital/Discrete — Availability (3)",
    0x0B: "Digital/Discrete — Redundancy",
    0x0C: "Digital/Discrete — ACPI Device Power State",
    0x6F: "Sensor-specific Discrete (use Sensor Type offset)",
}

# Table 42-2 Threshold events (Event/Reading Type 0x01)
THRESHOLD_EVENTS = {
    0: "Lower Non-critical - going low",
    1: "Lower Non-critical - going high",
    2: "Lower Critical - going low",
    3: "Lower Critical - going high",
    4: "Lower Non-recoverable - going low",
    5: "Lower Non-recoverable - going high",
    6: "Upper Non-critical - going low",
    7: "Upper Non-critical - going high",
    8: "Upper Critical - going low",
    9: "Upper Critical - going high",
    10: "Upper Non-recoverable - going low",
    11: "Upper Non-recoverable - going high",
}
