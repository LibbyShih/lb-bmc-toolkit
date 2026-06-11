from spec.sdr_types import SDR_RECORD_TYPES, UNIT_CODES, ENTITY_IDS
from spec.sensor_types import SENSOR_TYPES
from spec.event_types import EVENT_TYPE_NAMES

def decode_sdr_record(raw: bytes) -> dict:
    if len(raw) < 5:
        return {"error": "Record too short"}
        
    record_id = int.from_bytes(raw[0:2], byteorder='little')
    sdr_version = raw[2]
    record_type = raw[3]
    record_length = raw[4]
    
    result = {
        "record_id": record_id,
        "sdr_version": f"0x{sdr_version:02X}",
        "record_type": record_type,
        "record_type_name": SDR_RECORD_TYPES.get(record_type, f"Unknown (0x{record_type:02X})"),
        "record_length": record_length,
        "raw_hex": raw.hex().upper()
    }
    
    if record_type == 0x01: # Full Sensor Record
        if len(raw) < 48:
            result["error"] = "Full sensor record too short"
            return result
            
        result["sensor_owner_id"] = raw[5]
        result["sensor_owner_lun"] = raw[6]
        result["sensor_number"] = raw[7]
        entity_id = raw[8]
        result["entity_id"] = entity_id
        result["entity_name"] = ENTITY_IDS.get(entity_id, f"Unknown (0x{entity_id:02X})")
        result["entity_instance"] = raw[9]
        
        sensor_type_code = raw[12]
        result["sensor_type_code"] = sensor_type_code
        result["sensor_type_name"] = SENSOR_TYPES.get(sensor_type_code, {}).get("name", f"Unknown (0x{sensor_type_code:02X})")
        
        event_type_code = raw[13]
        result["event_type_code"] = event_type_code
        result["event_type_name"] = EVENT_TYPE_NAMES.get(event_type_code, f"Unknown (0x{event_type_code:02X})")
        
        base_unit_code = raw[21]
        result["base_unit"] = UNIT_CODES.get(base_unit_code, f"Unknown (0x{base_unit_code:02X})")
        
        # M, B, Rexp, Bexp extraction
        # M = M[7:0] + (M[9:8] << 8) from byte 24 and 25
        m_lsb = raw[24]
        m_msb = (raw[25] & 0xC0) >> 6
        m_val = (m_msb << 8) | m_lsb
        # Two's complement for 10-bit M
        if m_val & 0x0200:
            m_val -= 0x0400
        result["M"] = m_val
        
        # B = B[7:0] + (B[9:8] << 8) from byte 26 and 27
        b_lsb = raw[26]
        b_msb = (raw[27] & 0xC0) >> 6
        b_val = (b_msb << 8) | b_lsb
        if b_val & 0x0200:
            b_val -= 0x0400
        result["B"] = b_val
        
        # Bexp, Rexp from byte 29
        # R exp (2s complement 4-bit) in [7:4]
        # B exp (2s complement 4-bit) in [3:0]
        r_exp = (raw[29] & 0xF0) >> 4
        if r_exp & 0x08:
            r_exp -= 0x10
        result["Rexp"] = r_exp
        
        b_exp = raw[29] & 0x0F
        if b_exp & 0x08:
            b_exp -= 0x10
        result["Bexp"] = b_exp
        
        # Sensor ID string parsing
        id_string_type_len = raw[47]
        id_string_len = id_string_type_len & 0x1F
        if len(raw) >= 48 + id_string_len:
            id_string_bytes = raw[48:48+id_string_len]
            try:
                result["sensor_id_string"] = id_string_bytes.decode('ascii', errors='ignore').strip('\x00')
            except Exception:
                result["sensor_id_string"] = id_string_bytes.hex()
        else:
            result["sensor_id_string"] = ""
            
    return result

def sdr_to_annotation(raw: bytes, decoded: dict) -> dict:
    if len(raw) < 5:
        return {}
        
    fields = [
        {"name": "Record ID", "offset": 0, "length": 2, "color": 0, "decoded": f"0x{int.from_bytes(raw[0:2], 'little'):04X}"},
        {"name": "SDR Version", "offset": 2, "length": 1, "color": 2, "decoded": decoded.get("sdr_version", "")},
        {"name": "Record Type", "offset": 3, "length": 1, "color": 1, "decoded": f"0x{raw[3]:02X} ({decoded.get('record_type_name', '')})"},
        {"name": "Record Length", "offset": 4, "length": 1, "color": 6, "decoded": str(raw[4])},
    ]
    
    if raw[3] == 0x01 and len(raw) >= 48:
        fields.extend([
            {"name": "Owner ID", "offset": 5, "length": 1, "color": 5, "decoded": f"0x{raw[5]:02X}"},
            {"name": "Owner LUN", "offset": 6, "length": 1, "color": 3, "decoded": f"0x{raw[6]:02X}"},
            {"name": "Sensor Number", "offset": 7, "length": 1, "color": 0, "decoded": str(raw[7])},
            {"name": "Entity ID", "offset": 8, "length": 1, "color": 1, "decoded": decoded.get("entity_name", "")},
            {"name": "Entity Instance", "offset": 9, "length": 1, "color": 1, "decoded": str(raw[9])},
            {"name": "Sensor Type", "offset": 12, "length": 1, "color": 0, "decoded": decoded.get("sensor_type_name", "")},
            {"name": "Event/Reading Type", "offset": 13, "length": 1, "color": 4, "decoded": decoded.get("event_type_name", "")},
            {"name": "Base Unit", "offset": 21, "length": 1, "color": 1, "decoded": decoded.get("base_unit", "")},
            {"name": "M", "offset": 24, "length": 2, "color": 6, "decoded": str(decoded.get("M", ""))},
            {"name": "B", "offset": 26, "length": 2, "color": 6, "decoded": str(decoded.get("B", ""))},
            {"name": "Accuracy", "offset": 28, "length": 1, "color": 6, "decoded": f"0x{raw[28]:02X}"},
            {"name": "Rexp / Bexp", "offset": 29, "length": 1, "color": 6, "decoded": f"Rexp: {decoded.get('Rexp')}, Bexp: {decoded.get('Bexp')}"},
            {"name": "Sensor ID String", "offset": 48, "length": len(raw)-48, "color": 2, "decoded": decoded.get("sensor_id_string", "")},
        ])
        
    for f in fields:
        # Prevent out-of-bounds
        if f["offset"] + f["length"] <= len(raw):
            f["bytes_hex"] = " ".join(f"{b:02X}" for b in raw[f["offset"]:f["offset"]+f["length"]])
        else:
            f["bytes_hex"] = "..."
        f["note"] = ""
        
    return {
        "raw_hex": " ".join(f"{b:02X}" for b in raw),
        "fields": fields,
        "unmatched_bytes": ""
    }
