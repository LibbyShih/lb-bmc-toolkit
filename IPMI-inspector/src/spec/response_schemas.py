from dataclasses import dataclass, field
from typing import Any

@dataclass
class Field:
    name: str
    offset: int
    length: int
    decode: str  # 'hex', 'bits', 'int', 'bcd', 'ipmi_ver', 'le_int', 'sensor_value', 'event_bits'
    bits: dict[str, str] | None = None
    mask: int | None = None
    lookup: dict[int, str] | None = None
    note: str | None = None

@dataclass
class ResponseSchema:
    name: str
    fields: list[Field]

MANUFACTURER_IDS: dict[int, str] = {
    0x000000: "Reserved",
    0x0038A3: "ASPEED Technology",
    0x00000B: "Dell",
    0x00157A: "Supermicro",
    0x000030: "Hewlett-Packard",
    0x002A7C: "Quanta Computer",
    0x0015D9: "Supermicro (alt)",
    0x001C4C: "Inventec",
    0x000075: "Intel",
}

RESPONSE_SCHEMAS: dict[tuple[int, int], ResponseSchema] = {
    (0x06, 0x01): ResponseSchema(
        name="Get Device ID",
        fields=[
            Field(name="Device ID",       offset=0, length=1, decode="hex"),
            Field(name="Dev Revision",    offset=1, length=1, decode="bits",
                  bits={"[3:0]": "Revision", "[7]": "Provides SDRs"}),
            Field(name="FW Major Rev",    offset=2, length=1, decode="int", mask=0x7F),
            Field(name="FW Minor Rev",    offset=3, length=1, decode="bcd"),
            Field(name="IPMI Version",    offset=4, length=1, decode="ipmi_ver"),
            Field(name="Dev Support",     offset=5, length=1, decode="bits",
                  bits={"[0]": "Chassis", "[1]": "Bridge", "[2]": "IPMB Event Gen",
                        "[3]": "IPMB Event Rcv", "[4]": "FRU", "[5]": "SEL",
                        "[6]": "SDR Repository", "[7]": "Sensor"}),
            Field(name="Manufacturer ID", offset=6, length=3, decode="le_int",
                  lookup=MANUFACTURER_IDS),
            Field(name="Product ID",      offset=9, length=2, decode="le_int"),
        ]
    ),
    (0x04, 0x2D): ResponseSchema(
        name="Get Sensor Reading",
        fields=[
            Field(name="Reading Byte",  offset=0, length=1, decode="sensor_value",
                  note="換算需搭配 SDR 的 M/B/Rexp"),
            Field(name="Sensor Status", offset=1, length=1, decode="bits",
                  bits={"[5]": "Reading/State unavailable", "[6]": "Sensor scan disabled",
                        "[7]": "Event Messages disabled"}),
            Field(name="Event Status",  offset=2, length=1, decode="event_bits"),
        ]
    ),
    (0x00, 0x01): ResponseSchema(
        name="Get Chassis Status",
        fields=[
            Field(name="Current Power State", offset=0, length=1, decode="hex"),
            Field(name="Last Power Event", offset=1, length=1, decode="hex"),
            Field(name="Misc. Chassis State", offset=2, length=1, decode="hex"),
            Field(name="Front Panel Button Capabilities", offset=3, length=1, decode="hex"),
        ]
    ),
    (0x06, 0x04): ResponseSchema(
        name="Get Self Test Results",
        fields=[
            Field(name="Self Test Result", offset=0, length=1, decode="hex",
                  note="55h = No error. 56h = Self test function not implemented. 57h = Corrupted or inaccessible data or devices. 58h = Fatal hardware error."),
            Field(name="Self Test Error bitfield", offset=1, length=1, decode="hex"),
        ]
    ),

    # ── Chassis ──────────────────────────────────────────────────────────────
    (0x00, 0x00): ResponseSchema(name="Get Chassis Capabilities", fields=[
        Field(name="Capabilities Flags", offset=0, length=1, decode="bits",
              bits={"[0]": "Intrusion Sensor", "[1]": "Front Panel Lockout",
                    "[2]": "Diagnostic Interrupt", "[3]": "Power Interlock"}),
        Field(name="FRU Info Dev Addr", offset=1, length=1, decode="hex"),
        Field(name="SDR Dev Addr",      offset=2, length=1, decode="hex"),
        Field(name="SEL Dev Addr",      offset=3, length=1, decode="hex"),
        Field(name="SM Dev Addr",       offset=4, length=1, decode="hex"),
    ]),
    (0x00, 0x02): ResponseSchema(name="Chassis Control (no response data)", fields=[]),
    (0x00, 0x07): ResponseSchema(name="Get System Restart Cause", fields=[
        Field(name="Restart Cause", offset=0, length=1, decode="bits",
              bits={"[3:0]": "Cause code (0=unknown,1=chassis ctrl,2=reset pushbtn,3=power pushbtn,4=watchdog,5=OEM,6=auto-power,7=power restore,8=LAN,9=unknown)"}),
        Field(name="Channel Number", offset=1, length=1, decode="hex"),
    ]),
    (0x00, 0x09): ResponseSchema(name="Get System Boot Options", fields=[
        Field(name="Parameter Valid",   offset=0, length=1, decode="bits",
              bits={"[7]": "Parameter invalid/locked", "[5:0]": "Parameter selector"}),
        Field(name="Parameter Data 1", offset=1, length=1, decode="hex"),
        Field(name="Parameter Data 2", offset=2, length=1, decode="hex"),
        Field(name="Parameter Data 3", offset=3, length=1, decode="hex"),
        Field(name="Parameter Data 4", offset=4, length=1, decode="hex"),
        Field(name="Parameter Data 5", offset=5, length=1, decode="hex"),
    ]),

    # ── App / BMC ─────────────────────────────────────────────────────────────
    (0x06, 0x02): ResponseSchema(name="Cold Reset (no response data)", fields=[]),
    (0x06, 0x03): ResponseSchema(name="Warm Reset (no response data)", fields=[]),
    (0x06, 0x08): ResponseSchema(name="Get Device GUID", fields=[
        Field(name="GUID bytes [0:3]",  offset=0,  length=4, decode="hex"),
        Field(name="GUID bytes [4:7]",  offset=4,  length=4, decode="hex"),
        Field(name="GUID bytes [8:11]", offset=8,  length=4, decode="hex"),
        Field(name="GUID bytes [12:15]",offset=12, length=4, decode="hex"),
    ]),
    (0x06, 0x24): ResponseSchema(name="Get Watchdog Timer", fields=[
        Field(name="Timer Use",         offset=0, length=1, decode="bits",
              bits={"[2:0]": "Use (1=BIOS FRB2,2=BIOS/POST,3=OS Load,4=SMS/OS,5=OEM)",
                    "[6]": "Timer running", "[7]": "Timer expired"}),
        Field(name="Timer Actions",     offset=1, length=1, decode="bits",
              bits={"[2:0]": "Timeout action (0=none,1=hard reset,2=power down,3=power cycle)",
                    "[6:4]": "Pre-timeout interrupt (0=none,1=SMI,2=NMI,3=Msg interrupt)"}),
        Field(name="Pre-timeout interval", offset=2, length=1, decode="int",
              note="Seconds before timeout for pre-timeout interrupt"),
        Field(name="Timer expiration flags", offset=3, length=1, decode="bits",
              bits={"[1]": "BIOS FRB2", "[2]": "BIOS/POST", "[3]": "OS Load",
                    "[4]": "SMS/OS", "[5]": "OEM"}),
        Field(name="Initial countdown Lo", offset=4, length=1, decode="int"),
        Field(name="Initial countdown Hi", offset=5, length=1, decode="int",
              note="Initial countdown = Hi*256 + Lo (100ms units)"),
        Field(name="Present countdown Lo", offset=6, length=1, decode="int"),
        Field(name="Present countdown Hi", offset=7, length=1, decode="int"),
    ]),

    # ── Sensor/Event ─────────────────────────────────────────────────────────
    (0x04, 0x2B): ResponseSchema(name="Get Sensor Threshold", fields=[
        Field(name="Readable Thresholds", offset=0, length=1, decode="bits",
              bits={"[0]": "LNR readable", "[1]": "LCR readable", "[2]": "LNC readable",
                    "[3]": "UNC readable", "[4]": "UCR readable", "[5]": "UNR readable"}),
        Field(name="UNR raw", offset=1, length=1, decode="hex", note="Upper Non-Recoverable"),
        Field(name="UCR raw", offset=2, length=1, decode="hex", note="Upper Critical"),
        Field(name="UNC raw", offset=3, length=1, decode="hex", note="Upper Non-Critical"),
        Field(name="LNC raw", offset=4, length=1, decode="hex", note="Lower Non-Critical"),
        Field(name="LCR raw", offset=5, length=1, decode="hex", note="Lower Critical"),
        Field(name="LNR raw", offset=6, length=1, decode="hex", note="Lower Non-Recoverable"),
    ]),
    (0x04, 0x2F): ResponseSchema(name="Get Sensor Type", fields=[
        Field(name="Sensor Type",        offset=0, length=1, decode="hex"),
        Field(name="Event/Reading Type", offset=1, length=1, decode="hex"),
    ]),

    # ── Storage / SEL ─────────────────────────────────────────────────────────
    (0x0A, 0x48): ResponseSchema(name="Get SEL Info", fields=[
        Field(name="SEL Version",       offset=0,  length=1, decode="ipmi_ver"),
        Field(name="Record Count",      offset=1,  length=2, decode="le_int"),
        Field(name="Free Space",        offset=3,  length=2, decode="le_int", note="Bytes free"),
        Field(name="Most Recent Add",   offset=5,  length=4, decode="le_int", note="Unix timestamp or 0xFFFFFFFF"),
        Field(name="Most Recent Erase", offset=9,  length=4, decode="le_int"),
        Field(name="Operation Support", offset=13, length=1, decode="bits",
              bits={"[0]": "Get SEL Alloc Info", "[1]": "Reserve SEL",
                    "[2]": "Partial Add SEL Entry", "[3]": "Delete SEL Entry",
                    "[7]": "Overflow flag"}),
    ]),
    (0x0A, 0x4A): ResponseSchema(name="Reserve SEL", fields=[
        Field(name="Reservation ID", offset=0, length=2, decode="le_int"),
    ]),
    (0x0A, 0x4B): ResponseSchema(name="Get SEL Entry", fields=[
        Field(name="Next Record ID", offset=0, length=2, decode="le_int",
              note="0xFFFF = last entry"),
        Field(name="Record Data",    offset=2, length=16, decode="hex",
              note="16-byte SEL record — use SEL decoder for full parse"),
    ]),
    (0x0A, 0x47): ResponseSchema(name="Add SEL Entry", fields=[
        Field(name="New Record ID", offset=0, length=2, decode="le_int"),
    ]),

    # ── Storage / SDR ─────────────────────────────────────────────────────────
    (0x0A, 0x20): ResponseSchema(name="Get SDR Repository Info", fields=[
        Field(name="SDR Version",       offset=0,  length=1, decode="ipmi_ver"),
        Field(name="Record Count",      offset=1,  length=2, decode="le_int"),
        Field(name="Free Space",        offset=3,  length=2, decode="le_int", note="Bytes"),
        Field(name="Most Recent Add",   offset=5,  length=4, decode="le_int"),
        Field(name="Most Recent Erase", offset=9,  length=4, decode="le_int"),
        Field(name="Operation Support", offset=13, length=1, decode="bits",
              bits={"[0]": "Get SDR Alloc Info", "[1]": "Reserve SDR Repository",
                    "[2]": "Partial Add SDR", "[3]": "Delete SDR", "[7]": "Overflow"}),
    ]),
    (0x0A, 0x22): ResponseSchema(name="Reserve SDR Repository", fields=[
        Field(name="Reservation ID", offset=0, length=2, decode="le_int"),
    ]),
    (0x0A, 0x23): ResponseSchema(name="Get SDR", fields=[
        Field(name="Next Record ID", offset=0, length=2, decode="le_int",
              note="0xFFFF = last entry"),
        Field(name="Record Data",    offset=2, length=5, decode="hex",
              note="Variable length SDR record — use SDR decoder for full parse"),
    ]),

    # ── Storage / FRU ─────────────────────────────────────────────────────────
    (0x0A, 0x10): ResponseSchema(name="Get FRU Inventory Area Info", fields=[
        Field(name="FRU Size",    offset=0, length=2, decode="le_int", note="Bytes"),
        Field(name="Access Type", offset=2, length=1, decode="bits",
              bits={"[0]": "Word (1) or Byte (0) access"}),
    ]),

    # ── Transport / LAN ───────────────────────────────────────────────────────
    (0x0C, 0x02): ResponseSchema(name="Get LAN Configuration Parameters", fields=[
        Field(name="Parameter Rev",  offset=0, length=1, decode="bits",
              bits={"[7:4]": "Present revision", "[3:0]": "Oldest forward-compatible revision"}),
        Field(name="Parameter Data", offset=1, length=1, decode="hex",
              note="Meaning depends on parameter selector used in request"),
    ]),
}

def _decode_field_value(chunk: list[int], f: "Field") -> str:
    if not chunk:
        return "(empty)"
    b0 = chunk[0]

    if f.decode == "hex":
        if len(chunk) == 1:
            return f"0x{chunk[0]:02X}"
        return " ".join(f"0x{b:02X}" for b in chunk)

    elif f.decode == "int":
        val = b0 & (f.mask if f.mask is not None else 0xFF)
        return str(val)

    elif f.decode == "bcd":
        return f"{(b0 >> 4) & 0xF}{b0 & 0xF}"

    elif f.decode == "ipmi_ver":
        return f"{(b0 & 0xF0) >> 4}.{b0 & 0x0F}"

    elif f.decode == "le_int":
        val = int.from_bytes(bytes(chunk), "little")
        if f.lookup and val in f.lookup:
            return f"{f.lookup[val]}"
        return f"{val} (0x{val:0{len(chunk)*2}X})"

    elif f.decode == "bits":
        if not f.bits:
            return f"0x{b0:02X}"
        active = []
        for bit_spec, label in f.bits.items():
            spec = bit_spec.strip("[]")
            if ":" in spec:
                hi, lo = (int(x) for x in spec.split(":"))
                mask = ((1 << (hi - lo + 1)) - 1) << lo
                val = (b0 & mask) >> lo
                if val:
                    active.append(f"{label}={val}")
            else:
                bit = int(spec)
                if b0 & (1 << bit):
                    active.append(label)
        return ", ".join(active) if active else f"0x{b0:02X} (none set)"

    elif f.decode == "sensor_value":
        return f"0x{b0:02X} (raw reading — apply SDR M/B/Rexp to convert)"

    elif f.decode == "event_bits":
        return f"0x{b0:02X}"

    else:
        return " ".join(f"{b:02X}" for b in chunk)


def decode_with_schema(raw: list[int], schema: "ResponseSchema") -> dict:
    covered: set[int] = set()
    fields_out = []

    for i, f in enumerate(schema.fields):
        end = f.offset + f.length
        if end > len(raw):
            continue
        chunk = raw[f.offset:end]
        bytes_hex = " ".join(f"{b:02X}" for b in chunk)
        decoded = _decode_field_value(chunk, f)
        fields_out.append({
            "name": f.name,
            "offset": f.offset,
            "length": f.length,
            "bytes_hex": bytes_hex,
            "decoded": decoded,
            "color": i % 8,
            "note": f.note or "",
        })
        covered.update(range(f.offset, end))

    unmatched = [raw[i] for i in range(len(raw)) if i not in covered]
    return {
        "raw_hex": " ".join(f"{b:02X}" for b in raw),
        "fields": fields_out,
        "unmatched_bytes": " ".join(f"{b:02X}" for b in unmatched),
    }

