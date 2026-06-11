import datetime
from spec.sensor_types import SENSOR_TYPES
from spec.event_types import EVENT_TYPE_NAMES
from spec.system_firmware import POST_ERROR_CODES, POST_PROGRESS_CODES

GENERATOR_SOFTWARE_IDS = {
    0x20: "BMC",
    0x21: "SMI Handler",
    0x33: "System Management Software",
    0x40: "BIOS/EFI",
    0x41: "BIOS/EFI POST",
    0x42: "BIOS/EFI POST Error",
    0x43: "BIOS/EFI SMI Handler",
}

def decode_sel_record(raw: bytes) -> dict:
    if len(raw) != 16:
        return {"error": "Invalid SEL record length"}

    record_id = int.from_bytes(raw[0:2], byteorder='little')
    record_type = raw[2]
    
    result = {
        "record_id": record_id,
        "record_type": record_type,
        "raw_hex": raw.hex().upper(),
    }

    if record_type == 0x02:
        result["record_type_name"] = "System Event"
        timestamp = int.from_bytes(raw[3:7], byteorder='little')
        result["timestamp"] = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).isoformat()
        
        gen_id = int.from_bytes(raw[7:9], byteorder='little')
        result["generator_id"] = gen_id
        if (gen_id & 1) == 0:  # bit-0=1 → Software ID; bit-0=0 → IPMB
            result["generator_type"] = "IPMB"
            result["generator_addr"] = f"0x{(gen_id >> 1):02X}"
        else:
            result["generator_type"] = "Software"
            result["generator_addr"] = GENERATOR_SOFTWARE_IDS.get(gen_id >> 1, f"0x{(gen_id >> 1):02X}")
        
        result["evm_rev"] = raw[9]
        sensor_type_code = raw[10]
        result["sensor_type_code"] = sensor_type_code
        result["sensor_type_name"] = SENSOR_TYPES.get(sensor_type_code, {}).get("name", f"Unknown (0x{sensor_type_code:02X})")
        
        result["sensor_number"] = raw[11]
        
        event_dir_type = raw[12]
        result["event_direction"] = "Deassert" if event_dir_type & 0x80 else "Assert"
        event_type_code = event_dir_type & 0x7F
        result["event_type_code"] = event_type_code
        result["event_type_name"] = EVENT_TYPE_NAMES.get(event_type_code, f"Unknown (0x{event_type_code:02X})")
        
        event_data_1 = raw[13]
        event_data_2 = raw[14]
        event_data_3 = raw[15]
        result["event_data"] = [event_data_1, event_data_2, event_data_3]
        
        event_offset = event_data_1 & 0x0F
        result["event_offset"] = event_offset
        
        event_info = SENSOR_TYPES.get(sensor_type_code, {}).get("events", {}).get(event_offset)
        if event_info:
            result["event_name"] = event_info[0]
        else:
            result["event_name"] = f"Offset 0x{event_offset:02X}"
            
        # Specific decoding for System Firmware Progress
        if sensor_type_code == 0x0F:
            if event_offset == 0x00:
                result["event_data2_desc"] = POST_ERROR_CODES.get(event_data_2, f"0x{event_data_2:02X}")
            elif event_offset == 0x02:
                result["event_data2_desc"] = POST_PROGRESS_CODES.get(event_data_2, f"0x{event_data_2:02X}")
            else:
                result["event_data2_desc"] = f"0x{event_data_2:02X}"
        else:
            result["event_data2_desc"] = f"0x{event_data_2:02X}"
            
        result["event_data3_desc"] = f"0x{event_data_3:02X}"
        
    elif 0xC0 <= record_type <= 0xDF:
        result["record_type_name"] = "OEM Timestamped"
        timestamp = int.from_bytes(raw[3:7], byteorder='little')
        result["timestamp"] = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).isoformat()
    elif 0xE0 <= record_type <= 0xFF:
        result["record_type_name"] = "OEM Non-timestamped"
    else:
        result["record_type_name"] = f"Unknown (0x{record_type:02X})"
        
    return result

def sel_to_annotation(raw: bytes, decoded: dict) -> dict:
    if len(raw) != 16:
        return {}
    
    fields = [
        {"name": "Record ID", "offset": 0, "length": 2, "color": 0, "decoded": f"0x{int.from_bytes(raw[0:2], 'little'):04X}"},
        {"name": "Record Type", "offset": 2, "length": 1, "color": 1, "decoded": f"0x{raw[2]:02X} ({decoded.get('record_type_name', '')})"},
    ]
    if raw[2] == 0x02:
        fields.extend([
            {"name": "Timestamp", "offset": 3, "length": 4, "color": 2, "decoded": decoded.get("timestamp", "")},
            {"name": "Generator ID", "offset": 7, "length": 2, "color": 5, "decoded": f"0x{int.from_bytes(raw[7:9], 'little'):04X}"},
            {"name": "EVM Rev", "offset": 9, "length": 1, "color": 3, "decoded": f"0x{raw[9]:02X}"},
            {"name": "Sensor Type", "offset": 10, "length": 1, "color": 0, "decoded": decoded.get("sensor_type_name", "")},
            {"name": "Sensor Number", "offset": 11, "length": 1, "color": 0, "decoded": str(raw[11])},
            {"name": "Event Dir/Type", "offset": 12, "length": 1, "color": 4, "decoded": f"{decoded.get('event_direction', '')} {decoded.get('event_type_name', '')}"},
            {"name": "Event Data 1", "offset": 13, "length": 1, "color": 6, "decoded": f"0x{raw[13]:02X}"},
            {"name": "Event Data 2", "offset": 14, "length": 1, "color": 6, "decoded": f"0x{raw[14]:02X}"},
            {"name": "Event Data 3", "offset": 15, "length": 1, "color": 6, "decoded": f"0x{raw[15]:02X}"},
        ])
    
    for f in fields:
        f["bytes_hex"] = " ".join(f"{b:02X}" for b in raw[f["offset"]:f["offset"]+f["length"]])
        f["note"] = ""
        
    return {
        "raw_hex": " ".join(f"{b:02X}" for b in raw),
        "fields": fields,
        "unmatched_bytes": ""
    }
