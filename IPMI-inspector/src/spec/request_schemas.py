from dataclasses import dataclass, field as dc_field
from typing import Any

@dataclass
class RequestField:
    name: str
    length: int          # bytes
    type: str            # 'hex', 'int', 'sensor_ref', 'enum'
    desc: str = ""
    default: str = ""
    options: dict[int, str] = dc_field(default_factory=dict)  # for enum type

REQUEST_SCHEMAS: dict[tuple[int, int], list[RequestField]] = {
    (0x04, 0x2D): [  # Get Sensor Reading
        RequestField(name="Sensor Number", length=1, type="sensor_ref",
                     desc="目標感測器的 Sensor Number（見 SDR）"),
    ],
    (0x04, 0x2B): [  # Get Sensor Threshold
        RequestField(name="Sensor Number", length=1, type="sensor_ref",
                     desc="目標感測器的 Sensor Number"),
    ],
    (0x04, 0x2F): [  # Get Sensor Type
        RequestField(name="Sensor Number", length=1, type="sensor_ref",
                     desc="目標感測器的 Sensor Number"),
    ],
    (0x0A, 0x4B): [  # Get SEL Entry
        RequestField(name="Reservation ID", length=2, type="hex", default="0x0000",
                     desc="由 Reserve SEL (0x0A/0x4A) 取得；不需要時填 0x0000"),
        RequestField(name="Record ID",      length=2, type="hex", default="0x0000",
                     desc="0x0000 = 第一筆；上筆回傳的 Next Record ID"),
        RequestField(name="Offset",         length=1, type="hex", default="0x00",
                     desc="讀取起始 offset；完整讀取填 0x00"),
        RequestField(name="Bytes to Read",  length=1, type="hex", default="0xFF",
                     desc="0xFF = 全部"),
    ],
    (0x0A, 0x23): [  # Get SDR
        RequestField(name="Reservation ID", length=2, type="hex", default="0x0000",
                     desc="由 Reserve SDR Repository (0x0A/0x22) 取得"),
        RequestField(name="Record ID",      length=2, type="hex", default="0x0000",
                     desc="0x0000 = 第一筆"),
        RequestField(name="Offset",         length=1, type="hex", default="0x00",
                     desc="Record 內起始 offset"),
        RequestField(name="Bytes to Read",  length=1, type="hex", default="0xFF",
                     desc="0xFF = 全部"),
    ],
    (0x0A, 0x10): [  # Get FRU Inventory Area Info
        RequestField(name="FRU Device ID", length=1, type="int", default="0x00",
                     desc="FRU device ID，通常從 0 開始"),
    ],
    (0x0A, 0x11): [  # Read FRU Data
        RequestField(name="FRU Device ID",           length=1, type="int",  default="0x00"),
        RequestField(name="FRU Inventory Offset Lo", length=1, type="hex",  default="0x00"),
        RequestField(name="FRU Inventory Offset Hi", length=1, type="hex",  default="0x00"),
        RequestField(name="Count to Read",           length=1, type="int",  default="0x20",
                     desc="最多 32 bytes；設 0x20"),
    ],
    (0x00, 0x02): [  # Chassis Control
        RequestField(name="Chassis Control", length=1, type="enum",
                     desc="電源控制命令",
                     options={0: "Power Down", 1: "Power Up", 2: "Power Cycle",
                               3: "Hard Reset", 4: "Pulse Diagnostic Interrupt",
                               5: "Soft Shutdown"}),
    ],
    (0x00, 0x09): [  # Get System Boot Options
        RequestField(name="Parameter Selector", length=1, type="enum",
                     desc="Boot options parameter",
                     options={0: "Set In Progress", 1: "Service Partition Selector",
                               5: "Boot Info Acknowledge", 6: "Boot Flags",
                               7: "Boot Initiator Info"}),
        RequestField(name="Set Selector",   length=1, type="hex", default="0x00"),
        RequestField(name="Block Selector", length=1, type="hex", default="0x00"),
    ],
    (0x0C, 0x02): [  # Get LAN Configuration Parameters
        RequestField(name="Channel Number", length=1, type="hex", default="0x01",
                     desc="LAN channel number (usually 0x01)"),
        RequestField(name="Parameter Selector", length=1, type="enum",
                     desc="LAN parameter",
                     options={0: "Set In Progress", 3: "IP Address",
                               4: "IP Address Source", 5: "MAC Address",
                               6: "Subnet Mask", 17: "VLAN ID"}),
        RequestField(name="Set Selector",   length=1, type="hex", default="0x00"),
        RequestField(name="Block Selector", length=1, type="hex", default="0x00"),
    ],
}
