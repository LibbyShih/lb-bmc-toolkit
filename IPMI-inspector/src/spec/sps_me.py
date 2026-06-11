# NetFn 0x2E, IANA 0x000157 (shared with Node Manager; commands distinguish function)
# Reference: Intel SPS 6.0 Integration Guide / ME BIOS Specification

SPS_ME_COMMANDS = {
    0x21: ("Get SPS FW Version",
           "回傳: Operation Image ver, Recovery Image ver, Boot State"),
    0x22: ("Get SPS FW Parameters", ""),
    0x29: ("Set SPS FW Parameters", ""),
    0xB8: ("ME Debug Level", "取得/設定 ME debug log level"),
    0xDF: ("Update ME Firmware", "ME firmware update initiation"),
    0xF0: ("Get ME Firmware Health Status",
           "ME firmware state: Normal, Recovery, Update, Disabled"),
}

ME_FW_STATES = {
    0x00: "ME Normal Operation",
    0x01: "ME Recovery",
    0x02: "ME Unknown",
    0x03: "ME Disabled",
    0x04: "ME Firmware update in progress",
    0x05: "ME Shutdown",
}
