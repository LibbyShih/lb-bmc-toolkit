import datetime
from scapy.all import rdpcap, UDP, IP, IPv6
from decoders.message import decode_ipmi_message

def decode_pcap_file(path: str) -> list[dict]:
    """
    Read .pcap or .pcapng, filter for UDP port 623 (RMCP).
    Returns list of decoded packet info.
    """
    try:
        packets = rdpcap(path)
    except Exception as e:
        return [{"error": f"Failed to read pcap: {str(e)}"}]
        
    results = []
    packet_no = 1
    
    for pkt in packets:
        if not (pkt.haslayer(UDP) and (pkt[UDP].sport == 623 or pkt[UDP].dport == 623)):
            packet_no += 1
            continue
            
        timestamp = float(pkt.time)
        ts_str = datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc).isoformat()
        
        src_ip = pkt[IP].src if pkt.haslayer(IP) else (pkt[IPv6].src if pkt.haslayer(IPv6) else "Unknown")
        dst_ip = pkt[IP].dst if pkt.haslayer(IP) else (pkt[IPv6].dst if pkt.haslayer(IPv6) else "Unknown")
        src = f"{src_ip}:{pkt[UDP].sport}"
        dst = f"{dst_ip}:{pkt[UDP].dport}"
        direction = "Request" if pkt[UDP].dport == 623 else "Response"
        
        raw_data = bytes(pkt[UDP].payload)
        
        info = {
            "packet_no": packet_no,
            "timestamp": ts_str,
            "src": src,
            "dst": dst,
            "direction": direction,
            "raw_len": len(raw_data)
        }
        
        # Decode RMCP Header (4 bytes)
        if len(raw_data) >= 4:
            rmcp_ver = raw_data[0]
            rmcp_class = raw_data[3] & 0x1F
            is_ack = (raw_data[3] & 0x80) != 0
            
            info["rmcp_version"] = f"0x{rmcp_ver:02X}"
            info["rmcp_class"] = "IPMI" if rmcp_class == 0x07 else f"Unknown (0x{rmcp_class:02X})"
            info["rmcp_ack"] = is_ack
            
            if rmcp_class == 0x07 and len(raw_data) > 4:
                # IPMI Session Wrapper
                auth_type = raw_data[4]
                info["auth_type"] = f"0x{auth_type:02X}"
                
                if auth_type == 0x06: # RMCP+ (IPMI 2.0)
                    # IPMI 2.0 Table 13-8: RMCP+ Session Header
                    # Byte 5:    Payload Type (1 byte)
                    # Byte 6-9:  OEM IANA + OEM Payload ID (only if payload type = OEM)
                    # Byte 5:    Payload Type flags [7]=Encrypted, [6]=Authenticated, [5:0]=type
                    # Byte 6-9:  Session ID (LE32)
                    # Byte 10-13: Session Seq Num (LE32)
                    # Byte 14-15: IPMI Payload Length (LE16)
                    if len(raw_data) >= 16:
                        payload_type_byte = raw_data[5]
                        payload_type = payload_type_byte & 0x3F
                        
                        pt_map = {0x00: "IPMI", 0x10: "RAKP1", 0x11: "RAKP2",
                                  0x12: "RAKP3", 0x13: "RAKP4", 0x20: "SOL"}
                        info["payload_type"] = pt_map.get(payload_type, f"0x{payload_type:02X}")
                        info["encrypted"] = (payload_type_byte & 0x80) != 0
                        info["authenticated"] = (payload_type_byte & 0x40) != 0
                        
                        # Session ID at bytes 6-9 (LE32)
                        session_id = int.from_bytes(raw_data[6:10], byteorder='little')
                        info["session_id"] = f"0x{session_id:08X}"
                        
                        # Payload length at bytes 14-15 (LE16)
                        payload_len = int.from_bytes(raw_data[14:16], byteorder='little')
                        info["payload_len"] = payload_len
                        
                        # Decode plaintext IPMI payload (unencrypted, type 0x00 only)
                        if payload_type == 0x00 and not info["encrypted"]:
                            # IPMI payload starts at byte 16
                            ipmi_msg_bytes = raw_data[16:16 + payload_len]
                            ipmi_decoded = decode_ipmi_message(ipmi_msg_bytes)
                            info.update({f"ipmi_{k}": v for k, v in ipmi_decoded.items()})
                else: # IPMI 1.5
                    # Auth Type 0 (None): Session ID at byte 5, Seq at 9, MsgLen at 13, Msg at 14
                    # Auth Type != 0   : Auth Code 16 bytes at 5-20, Session ID at 21, Seq at 25, MsgLen at 29, Msg at 30
                    auth_code_len = 16 if auth_type != 0x00 else 0
                    sid_off = 5 + auth_code_len
                    msglen_off = sid_off + 8  # +4 session_id +4 seq_num
                    msg_off = msglen_off + 1
                    if len(raw_data) >= msg_off:
                        session_id = int.from_bytes(raw_data[sid_off:sid_off+4], byteorder='little')
                        info["session_id"] = f"0x{session_id:08X}"
                        msg_len = raw_data[msglen_off]
                        if len(raw_data) >= msg_off + msg_len:
                            ipmi_msg_bytes = raw_data[msg_off:msg_off+msg_len]
                            ipmi_decoded = decode_ipmi_message(ipmi_msg_bytes)
                            info.update({f"ipmi_{k}": v for k, v in ipmi_decoded.items()})
        
        results.append(info)
        packet_no += 1
        
    return results
