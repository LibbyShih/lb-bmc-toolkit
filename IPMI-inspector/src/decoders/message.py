from spec.netfn import NETFN_NAMES, COMMANDS
from spec.completion_codes import decode_cc
from spec.oem_aspeed import lookup_oem

def _checksum(data: bytes) -> bool:
    if not data:
        return False
    return sum(data) % 256 == 0

def decode_ipmi_message(raw: bytes) -> dict:
    # Basic IPMI v1.5/2.0 message parsing
    # Byte 0: rsAddr
    # Byte 1: NetFn/rsLUN
    # Byte 2: Checksum1
    # Byte 3: rqAddr
    # Byte 4: rqSeq/rqLUN
    # Byte 5: Command
    # Byte 6+: Data
    # Last: Checksum2
    
    if len(raw) < 7:
        return {"error": "Message too short"}
        
    rs_addr = raw[0]
    netfn = (raw[1] & 0xFC) >> 2
    rs_lun = raw[1] & 0x03
    
    # Checksum 1
    if not _checksum(raw[0:3]):
        return {"error": "Checksum 1 invalid"}
        
    rq_addr = raw[3]
    rq_seq = (raw[4] & 0xFC) >> 2
    rq_lun = raw[4] & 0x03
    
    cmd = raw[5]
    
    # Checksum 2
    if not _checksum(raw[3:]):
        return {"error": "Checksum 2 invalid"}
        
    # Is Response?
    # By IPMI spec, NetFn for response is odd (Request NetFn + 1)
    is_response = (netfn % 2) != 0
    base_netfn = netfn - 1 if is_response else netfn
    
    result = {
        "rs_addr": f"0x{rs_addr:02X}",
        "netfn": netfn,
        "netfn_name": NETFN_NAMES.get(base_netfn, f"Unknown (0x{base_netfn:02X})"),
        "rs_lun": rs_lun,
        "rq_addr": f"0x{rq_addr:02X}",
        "rq_seq": f"0x{rq_seq:02X}",
        "rq_lun": rq_lun,
        "cmd": cmd,
        "is_response": is_response,
        "raw_hex": raw.hex().upper()
    }
    
    # Find cmd name
    cmd_name = "Unknown"
    cmd_desc = ""
    
    if base_netfn in (0x2C, 0x2E, 0x30, 0x34):
        oem_desc = lookup_oem(base_netfn, cmd)
        if oem_desc:
            parts = oem_desc.split(" — ")
            cmd_name = parts[0]
            if len(parts) > 1:
                cmd_desc = parts[1]
    else:
        cmd_info = COMMANDS.get(base_netfn, {}).get(cmd)
        if cmd_info:
            cmd_name = cmd_info[0]
            cmd_desc = cmd_info[1]
            
    result["cmd_name"] = cmd_name
    if cmd_desc:
        result["cmd_desc"] = cmd_desc
        
    data_bytes = raw[6:-1]
    
    if is_response and len(data_bytes) > 0:
        cc = data_bytes[0]
        result["completion_code"] = cc
        result["completion_code_desc"] = decode_cc(cc)
        result["data_hex"] = data_bytes[1:].hex().upper()
    else:
        result["data_hex"] = data_bytes.hex().upper()
        
    return result
