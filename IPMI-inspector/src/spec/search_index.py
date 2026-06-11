from dataclasses import dataclass, field as dc_field

@dataclass
class SearchEntry:
    netfn: int
    cmd: int
    name: str
    keywords: list[str]
    desc: str = ""

def search_commands(query: str, limit: int = 10) -> list[dict]:
    """Return commands matching query, sorted by relevance."""
    q = query.lower().strip()
    if not q:
        return []
    results = []
    for entry in SEARCH_INDEX:
        score = 0
        if q in entry.name.lower():
            score += 10
        for kw in entry.keywords:
            if q in kw:
                score += 3
            elif kw in q:
                score += 1
        if score > 0:
            results.append((score, entry))
    results.sort(key=lambda x: -x[0])
    return [
        {"netfn": e.netfn, "cmd": e.cmd, "name": e.name, "desc": e.desc,
         "netfn_hex": f"0x{e.netfn:02X}", "cmd_hex": f"0x{e.cmd:02X}"}
        for _, e in results[:limit]
    ]

SEARCH_INDEX: list[SearchEntry] = [
    SearchEntry(0x06, 0x01, "Get Device ID",
                ["device", "id", "firmware", "version", "manufacturer", "product", "bmc", "info"],
                "BMC firmware version, IPMI version, manufacturer/product ID"),
    SearchEntry(0x06, 0x02, "Cold Reset",
                ["cold", "reset", "bmc", "restart", "reboot", "reinit"],
                "BMC cold reset — re-initialises firmware"),
    SearchEntry(0x06, 0x03, "Warm Reset",
                ["warm", "reset", "bmc", "restart", "session"],
                "BMC warm reset — preserves active sessions"),
    SearchEntry(0x06, 0x04, "Get Self Test Results",
                ["self", "test", "health", "diagnostic", "pass", "fail"],
                "BMC self-test: 0x55=pass, 0x56=fail"),
    SearchEntry(0x06, 0x08, "Get Device GUID",
                ["guid", "uuid", "identity", "unique"],
                "128-bit GUID identifying this BMC"),
    SearchEntry(0x06, 0x24, "Get Watchdog Timer",
                ["watchdog", "timer", "wdt", "timeout"],
                "Read watchdog timer configuration and countdown"),
    SearchEntry(0x00, 0x00, "Get Chassis Capabilities",
                ["chassis", "capabilities", "features", "fru", "sdr", "sel"],
                "Chassis support flags and component addresses"),
    SearchEntry(0x00, 0x01, "Get Chassis Status",
                ["chassis", "status", "power", "state", "fault"],
                "Power state, fault flags, restore policy"),
    SearchEntry(0x00, 0x02, "Chassis Control",
                ["power", "on", "off", "cycle", "reset", "reboot", "shutdown", "chassis"],
                "Control chassis power: on/off/cycle/reset/soft-shutdown"),
    SearchEntry(0x00, 0x07, "Get System Restart Cause",
                ["restart", "cause", "reason", "boot", "why"],
                "Why the system last restarted"),
    SearchEntry(0x00, 0x09, "Get System Boot Options",
                ["boot", "options", "bios", "flags", "next", "device"],
                "Read BIOS boot flags and next boot device"),
    SearchEntry(0x04, 0x2D, "Get Sensor Reading",
                ["sensor", "reading", "value", "temperature", "fan", "voltage", "power", "temp"],
                "Read current value of a single sensor by number"),
    SearchEntry(0x04, 0x2B, "Get Sensor Threshold",
                ["threshold", "sensor", "unr", "ucr", "unc", "lnr", "lcr", "limit"],
                "Read threshold values for a sensor (UNR/UCR/UNC/LNC/LCR/LNR)"),
    SearchEntry(0x04, 0x2F, "Get Sensor Type",
                ["sensor", "type", "category", "kind"],
                "Get the sensor type and event/reading type code"),
    SearchEntry(0x0A, 0x48, "Get SEL Info",
                ["sel", "event", "log", "info", "count", "free", "space"],
                "SEL record count, free space, last modification timestamps"),
    SearchEntry(0x0A, 0x4A, "Reserve SEL",
                ["sel", "reserve", "reservation"],
                "Reserve the SEL for sequential access"),
    SearchEntry(0x0A, 0x4B, "Get SEL Entry",
                ["sel", "entry", "record", "event", "read", "log"],
                "Read a single SEL record by ID"),
    SearchEntry(0x0A, 0x47, "Add SEL Entry",
                ["sel", "add", "write", "inject", "test"],
                "Inject a SEL entry (useful for testing)"),
    SearchEntry(0x0A, 0x20, "Get SDR Repository Info",
                ["sdr", "repository", "info", "count", "sensor"],
                "SDR record count, free space, timestamps"),
    SearchEntry(0x0A, 0x22, "Reserve SDR Repository",
                ["sdr", "reserve"],
                "Reserve SDR repository for sequential read"),
    SearchEntry(0x0A, 0x23, "Get SDR",
                ["sdr", "sensor", "record", "definition", "get"],
                "Read an SDR record by ID"),
    SearchEntry(0x0A, 0x10, "Get FRU Inventory Area Info",
                ["fru", "inventory", "size", "info"],
                "FRU device size and access type"),
    SearchEntry(0x0C, 0x02, "Get LAN Configuration Parameters",
                ["lan", "network", "ip", "mac", "address", "subnet", "config"],
                "Read LAN configuration: IP, MAC, subnet, VLAN"),
]
