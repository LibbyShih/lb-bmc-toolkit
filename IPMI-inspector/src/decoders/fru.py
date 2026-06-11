def _decode_6bit_ascii(data: bytes) -> str:
    """Decode 6-bit ASCII per IPMI FRU spec: 3 bytes → 4 chars."""
    result = []
    for i in range(0, len(data), 3):
        chunk = data[i:i+3]
        packed = chunk[0] | (chunk[1] << 8 if len(chunk) > 1 else 0) | (chunk[2] << 16 if len(chunk) > 2 else 0)
        n_chars = {1: 1, 2: 2, 3: 4}[len(chunk)]  # 1 byte→1 char, 2 bytes→2 chars, 3 bytes→4 chars
        for shift in range(n_chars):
            result.append(chr(((packed >> (shift * 6)) & 0x3F) + 0x20))
    return ''.join(result).rstrip()

def decode_type_length(byte_val: int, data: bytes, offset: int) -> tuple[str, int]:
    """Decode FRU Type/Length byte and extract string"""
    type_code = (byte_val & 0xC0) >> 6
    length = byte_val & 0x3F
    
    if length == 0:
        return "", offset
        
    if offset + length > len(data):
        return "<truncated>", len(data)
        
    field_bytes = data[offset:offset+length]
    result = ""
    
    if type_code == 3: # 8-bit ASCII
        try:
            result = field_bytes.decode('ascii', errors='ignore').strip('\x00')
        except:
            result = field_bytes.hex()
    elif type_code == 0: # Binary
        result = field_bytes.hex()
    elif type_code == 1: # BCD Plus
        result = field_bytes.hex() # Simplified
    elif type_code == 2: # 6-bit ASCII (IPMI FRU spec: 3 bytes → 4 printable chars)
        result = _decode_6bit_ascii(field_bytes)
        
    return result, offset + length

def decode_fru_board_area(data: bytes, offset: int) -> dict:
    if offset == 0 or offset + 1 >= len(data):
        return {}

    area_len_bytes = data[offset+1] * 8
    if area_len_bytes == 0:
        return {}
        
    area_data = data[offset:offset+area_len_bytes]
    if len(area_data) < 6:
        return {"error": "Board area too short"}
        
    # Byte 3 is Mfg Date / Time
    # Byte 6 starts fields
    current_offset = 6
    
    fields = ["manufacturer", "product_name", "serial_number", "part_number", "fru_file_id"]
    result = {}
    
    for field in fields:
        if current_offset >= len(area_data):
            break
        tl_byte = area_data[current_offset]
        if tl_byte == 0xC1:
            break
        current_offset += 1
        val, current_offset = decode_type_length(tl_byte, area_data, current_offset)
        result[field] = val
        
    return result

def decode_fru_product_area(data: bytes, offset: int) -> dict:
    if offset == 0 or offset + 1 >= len(data):
        return {}

    area_len_bytes = data[offset+1] * 8
    if area_len_bytes == 0:
        return {}
        
    area_data = data[offset:offset+area_len_bytes]
    if len(area_data) < 3:
        return {"error": "Product area too short"}
        
    current_offset = 3
    
    fields = ["manufacturer", "product_name", "part_model_number", "product_version", "serial_number", "asset_tag", "fru_file_id"]
    result = {}
    
    for field in fields:
        if current_offset >= len(area_data):
            break
        tl_byte = area_data[current_offset]
        if tl_byte == 0xC1:
            break
        current_offset += 1
        val, current_offset = decode_type_length(tl_byte, area_data, current_offset)
        result[field] = val
        
    return result

def decode_fru_data(raw: bytes) -> dict:
    if len(raw) < 8:
        return {"error": "FRU data too short (need 8 bytes header)"}
        
    if raw[0] != 0x01:
        return {"error": f"Invalid FRU version (0x{raw[0]:02X})"}
        
    internal_offset = raw[1] * 8
    chassis_offset = raw[2] * 8
    board_offset = raw[3] * 8
    product_offset = raw[4] * 8
    multi_offset = raw[5] * 8
    
    result = {
        "header": {
            "version": raw[0],
            "internal_use_offset": internal_offset,
            "chassis_info_offset": chassis_offset,
            "board_info_offset": board_offset,
            "product_info_offset": product_offset,
            "multi_record_offset": multi_offset
        },
        "board": decode_fru_board_area(raw, board_offset),
        "product": decode_fru_product_area(raw, product_offset)
    }
    
    return result

def fru_to_annotation(raw: bytes, decoded: dict) -> dict:
    if len(raw) < 8:
        return {}
    
    fields = [
        {"name": "Format Version", "offset": 0, "length": 1, "color": 0, "decoded": f"0x{raw[0]:02X}"},
        {"name": "Internal Offset", "offset": 1, "length": 1, "color": 1, "decoded": f"0x{raw[1]:02X} (*8 = {raw[1]*8})"},
        {"name": "Chassis Offset", "offset": 2, "length": 1, "color": 1, "decoded": f"0x{raw[2]:02X} (*8 = {raw[2]*8})"},
        {"name": "Board Offset", "offset": 3, "length": 1, "color": 1, "decoded": f"0x{raw[3]:02X} (*8 = {raw[3]*8})"},
        {"name": "Product Offset", "offset": 4, "length": 1, "color": 1, "decoded": f"0x{raw[4]:02X} (*8 = {raw[4]*8})"},
        {"name": "MultiRecord Offset", "offset": 5, "length": 1, "color": 1, "decoded": f"0x{raw[5]:02X} (*8 = {raw[5]*8})"},
        {"name": "PAD", "offset": 6, "length": 1, "color": 7, "decoded": "0x00"},
        {"name": "Checksum", "offset": 7, "length": 1, "color": 6, "decoded": f"0x{raw[7]:02X}"},
    ]
    
    for f in fields:
        if f["offset"] + f["length"] <= len(raw):
            f["bytes_hex"] = " ".join(f"{b:02X}" for b in raw[f["offset"]:f["offset"]+f["length"]])
        else:
            f["bytes_hex"] = "..."
        f["note"] = ""
        
    return {
        "raw_hex": " ".join(f"{b:02X}" for b in raw),
        "fields": fields,
        "unmatched_bytes": " ".join(f"{b:02X}" for b in raw[8:]) if len(raw) > 8 else ""
    }
