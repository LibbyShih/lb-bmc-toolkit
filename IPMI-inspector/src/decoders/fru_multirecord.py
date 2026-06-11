def decode_power_supply_info(data: bytes) -> dict:
    if len(data) < 23:
        return {"error": "Power supply info record too short"}
        
    overall_capacity = int.from_bytes(data[0:2], byteorder='little')
    peak_va = int.from_bytes(data[2:4], byteorder='little')
    inrush_current = data[4]
    inrush_interval = data[5]
    low_in_vol_1 = int.from_bytes(data[6:8], byteorder='little') * 10
    high_in_vol_1 = int.from_bytes(data[8:10], byteorder='little') * 10
    
    return {
        "overall_capacity_w": overall_capacity,
        "peak_va": peak_va,
        "inrush_current_a": inrush_current,
        "inrush_interval_ms": inrush_interval,
        "low_in_voltage_1_mv": low_in_vol_1,
        "high_in_voltage_1_mv": high_in_vol_1,
    }

def decode_dc_output(data: bytes) -> dict:
    if len(data) < 13:
        return {"error": "DC Output record too short"}
        
    output_number = data[0] & 0x0F
    # Signed 16-bit
    nominal_voltage = int.from_bytes(data[1:3], byteorder='little', signed=True) * 10
    max_neg_dev = int.from_bytes(data[3:5], byteorder='little', signed=True) * 10
    max_pos_dev = int.from_bytes(data[5:7], byteorder='little', signed=True) * 10
    ripple_noise = int.from_bytes(data[7:9], byteorder='little')
    min_current = int.from_bytes(data[9:11], byteorder='little')
    max_current = int.from_bytes(data[11:13], byteorder='little')
    
    return {
        "output_number": output_number,
        "nominal_voltage_mv": nominal_voltage,
        "max_neg_deviation_mv": max_neg_dev,
        "max_pos_deviation_mv": max_pos_dev,
        "ripple_noise_mv": ripple_noise,
        "min_current_ma": min_current,
        "max_current_ma": max_current,
    }

def decode_mgmt_access(data: bytes) -> dict:
    if len(data) < 1:
        return {"error": "Management access record too short"}
        
    sub_type = data[0]
    sub_type_names = {
        0x01: "System Management URL",
        0x02: "System Name",
        0x03: "System Ping Address",
        0x04: "Component Management URL",
        0x05: "Component Name",
        0x06: "Component Ping Address",
        0x07: "System Unique ID (UUID)",
    }
    
    val_bytes = data[1:]
    val_str = ""
    if sub_type == 0x07:
        val_str = val_bytes.hex()
    else:
        try:
            val_str = val_bytes.decode('ascii', errors='ignore').strip('\x00')
        except:
            val_str = val_bytes.hex()
            
    return {
        "sub_type_code": sub_type,
        "sub_type_name": sub_type_names.get(sub_type, f"Unknown (0x{sub_type:02X})"),
        "value": val_str
    }

def decode_fru_multirecord_area(raw: bytes, offset: int) -> list[dict]:
    if offset == 0 or offset >= len(raw):
        return []
        
    records = []
    current_offset = offset
    
    while current_offset < len(raw):
        if current_offset + 5 > len(raw):
            break
            
        record_type = raw[current_offset]
        eol_version = raw[current_offset+1]
        length = raw[current_offset+2]
        
        is_eol = (eol_version & 0x80) != 0
        
        if current_offset + 5 + length > len(raw):
            break
            
        data = raw[current_offset+5:current_offset+5+length]
        
        record_info = {
            "record_type": record_type,
            "length": length,
            "raw_data_hex": data.hex().upper()
        }
        
        if record_type == 0x00:
            record_info["record_type_name"] = "Power Supply Information"
            record_info["parsed"] = decode_power_supply_info(data)
        elif record_type == 0x01:
            record_info["record_type_name"] = "DC Output"
            record_info["parsed"] = decode_dc_output(data)
        elif record_type == 0x03:
            record_info["record_type_name"] = "Management Access Record"
            record_info["parsed"] = decode_mgmt_access(data)
        else:
            record_info["record_type_name"] = f"Unknown/Other (0x{record_type:02X})"
            
        records.append(record_info)
        
        if is_eol:
            break
            
        current_offset += (5 + length)
        
    return records
