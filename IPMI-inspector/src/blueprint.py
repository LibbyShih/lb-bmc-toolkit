"""
IPMI Inspector — Flask Blueprint
可被 standalone main.py 或 ToolEntry 掛載。
"""
import json
import os
import sys
import tempfile
import threading

from flask import Blueprint, render_template, jsonify, request, Response, redirect, url_for, session

# ── resolve src/ on sys.path so relative imports work ───────────────────────
_SRC = os.path.dirname(os.path.abspath(__file__))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from transport.rmcp import BMCConnection
from storage.db import init_db
from spec.response_schemas import RESPONSE_SCHEMAS, decode_with_schema
from decoders.sel import decode_sel_record, sel_to_annotation
from decoders.sdr import decode_sdr_record, sdr_to_annotation
from decoders.fru import decode_fru_data, fru_to_annotation
from decoders.fru_multirecord import decode_fru_multirecord_area
from decoders.pcap import decode_pcap_file
from spec.netfn import NETFN_NAMES, COMMANDS
from spec.completion_codes import decode_cc
from spec.search_index import search_commands
from spec.request_schemas import REQUEST_SCHEMAS

# ── URL prefix (standalone '' vs ToolEntry '/ipmi') ───────────────────────────
_URL_PREFIX = '/ipmi'


def set_url_prefix(prefix: str):
    """Call before register_blueprint: '' for standalone, '/ipmi' under ToolEntry."""
    global _URL_PREFIX
    _URL_PREFIX = (prefix or '').rstrip('/')


# ── Blueprint ────────────────────────────────────────────────────────────────
ipmi_bp = Blueprint(
    'ipmi', __name__,
    template_folder='web/templates',
    static_folder='web/static',
    static_url_path='/ipmi-static',
)

# ── Single global BMC connection ─────────────────────────────────────────────
_bmc: BMCConnection | None = None
_bmc_lock = threading.Lock()
_initialized = False


def _get_bmc() -> BMCConnection | None:
    with _bmc_lock:
        return _bmc


def _set_bmc(conn: BMCConnection | None):
    global _bmc
    with _bmc_lock:
        _bmc = conn


@ipmi_bp.context_processor
def inject_vars():
    return {
        'IPMI_BASE': _URL_PREFIX,
        '_ep_prefix': 'ipmi.',
        '_static_ep': 'ipmi.static',
    }


def init_ipmi(db_path: str = "profiles.db"):
    global _initialized
    if not _initialized:
        init_db(db_path)
        _initialized = True


# ── Auth guard decorator ─────────────────────────────────────────────────────

def _require_bmc(view_fn):
    from functools import wraps
    @wraps(view_fn)
    def wrapper(*args, **kwargs):
        if not _get_bmc():
            if '/api/' in request.path:
                return jsonify({"ok": False, "error": "Not connected to BMC"}), 403
            return redirect(url_for('ipmi.index'))
        return view_fn(*args, **kwargs)
    return wrapper


# ═══════════════════════════════════════════════════════════════
#  Routes — Connection
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/')
@ipmi_bp.route('/connect')
def index():
    conn = _get_bmc()
    if conn:
        if not request.path.endswith('/connect'):
            return redirect(url_for('ipmi.overview_page'))
    else:
        # Hub 模式：session 有憑證就自動連線
        bmc_sess = session.get('bmc')
        if bmc_sess:
            # ToolEntry hub：沿用 session 直接 connect（與 dashboard 進入預期一致）
            try:
                new_conn = BMCConnection(
                    host=bmc_sess['host'],
                    username=bmc_sess['user'],
                    password=bmc_sess.get('password', ''),
                    port=bmc_sess.get('ipmi_port', 623),
                )
                new_conn.connect()
                _set_bmc(new_conn)
                return redirect(url_for('ipmi.overview_page'))
            except Exception as e:
                from transport.rmcp import _ipmi_error_message
                return render_template(
                    'connect.html',
                    error=(
                        f'IPMI 自動連線失敗：{_ipmi_error_message(e)}'
                        f' — Exception: {type(e).__name__}'
                    ),
                )
    return render_template('connect.html')


@ipmi_bp.route('/connect', methods=['POST'])
def connect():
    host     = request.form.get('host', '').strip()
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    try:
        port = int(request.form.get('port', 623))
    except (ValueError, TypeError):
        return render_template('connect.html', error="Port must be a number.")

    if not host or not username:
        return render_template('connect.html', error="Host and username are required.")

    conn = BMCConnection(host=host, username=username, password=password, port=port)
    try:
        conn.connect()
    except Exception as e:
        from transport.rmcp import _ipmi_error_message
        return render_template(
            'connect.html',
            error=f"Connection failed: {_ipmi_error_message(e)} — Exception: {type(e).__name__}",
        )
    _set_bmc(conn)
    return redirect(url_for('ipmi.overview_page'))


@ipmi_bp.route('/disconnect')
def disconnect():
    conn = _get_bmc()
    if conn:
        conn.disconnect()
    _set_bmc(None)
    return redirect(url_for('ipmi.index'))


# ═══════════════════════════════════════════════════════════════
#  Routes — Overview
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/overview')
@_require_bmc
def overview_page():
    conn = _get_bmc()
    return render_template('overview.html', bmc=conn)


@ipmi_bp.route('/api/overview')
@_require_bmc
def api_overview():
    conn = _get_bmc()
    try:
        results = {}
        cmds = {
            "device_id":      (0x06, 0x01),
            "chassis_status": (0x00, 0x01),
            "self_test":      (0x06, 0x04),
        }
        for key, (netfn, cmd) in cmds.items():
            res = conn.raw_command(netfn, cmd)
            if not res.get('error') and res.get('data'):
                data = res['data']
                if data and data[0] == 0x00:
                    data = data[1:]
                schema     = RESPONSE_SCHEMAS.get((netfn, cmd))
                annotation = decode_with_schema(data, schema) if schema else None
                results[key] = {"ok": True, "data": data, "annotation": annotation}
            else:
                results[key] = {"ok": False, "error": res.get('error', 'Unknown error')}
        return jsonify({"ok": True, "overview": results})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
#  Routes — Sensors
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/sensors')
@_require_bmc
def sensors():
    return render_template('sensors.html', bmc=_get_bmc())


@ipmi_bp.route('/api/sensors')
@_require_bmc
def api_sensors():
    conn = _get_bmc()
    try:
        data = conn.get_sensors()
        return jsonify({"ok": True, "sensors": data})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
#  Routes — SEL
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/sel')
@_require_bmc
def sel_page():
    return render_template('sel.html', bmc=_get_bmc())


@ipmi_bp.route('/api/sel')
@_require_bmc
def api_sel():
    conn = _get_bmc()
    try:
        rsv = conn.raw_command(0x0A, 0x4A)
        reservation = 0
        if not rsv.get('error') and rsv.get('data') and len(rsv['data']) >= 2:
            reservation = int.from_bytes(bytes(rsv['data'][0:2]), 'little')

        records = []
        next_id = 0x0000
        visited = set()
        while next_id != 0xFFFF:
            if next_id in visited:
                break
            visited.add(next_id)
            cmd_data = [reservation & 0xFF, (reservation >> 8) & 0xFF,
                        next_id & 0xFF, (next_id >> 8) & 0xFF, 0x00, 0xFF]
            res = conn.raw_command(0x0A, 0x4B, data=cmd_data)
            if res.get('error') or not res.get('data') or len(res['data']) < 18:
                break
            data = res['data']
            next_id = int.from_bytes(bytes(data[0:2]), 'little')
            raw_record = bytes(data[2:18])
            decoded    = decode_sel_record(raw_record)
            annotation = sel_to_annotation(raw_record, decoded)
            records.append({**decoded, "annotation": annotation})
            if next_id == 0xFFFF:
                break
        return jsonify({"ok": True, "records": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
#  Routes — SDR
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/sdr')
@_require_bmc
def sdr_page():
    return render_template('sdr.html', bmc=_get_bmc())


@ipmi_bp.route('/api/sdr')
@_require_bmc
def api_sdr():
    conn = _get_bmc()
    try:
        rsv = conn.raw_command(0x0A, 0x22)
        reservation = 0
        if not rsv.get('error') and rsv.get('data') and len(rsv['data']) >= 2:
            reservation = int.from_bytes(bytes(rsv['data'][0:2]), 'little')
        records = []
        next_id = 0x0000
        visited = set()
        while next_id != 0xFFFF:
            if next_id in visited:
                break
            visited.add(next_id)
            cmd_data = [reservation & 0xFF, (reservation >> 8) & 0xFF,
                        next_id & 0xFF, (next_id >> 8) & 0xFF, 0x00, 0xFF]
            res = conn.raw_command(0x0A, 0x23, data=cmd_data)
            if res.get('error') or not res.get('data') or len(res['data']) < 2:
                break
            data       = res['data']
            next_id    = int.from_bytes(bytes(data[0:2]), 'little')
            raw_record = bytes(data[2:])
            decoded    = decode_sdr_record(raw_record)
            annotation = sdr_to_annotation(raw_record, decoded)
            records.append({**decoded, "annotation": annotation})
            if next_id == 0xFFFF:
                break
        return jsonify({"ok": True, "records": records})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
#  Routes — FRU
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/fru')
@_require_bmc
def fru_page():
    return render_template('fru.html', bmc=_get_bmc())


@ipmi_bp.route('/api/fru')
@_require_bmc
def api_fru():
    conn  = _get_bmc()
    fru_id = int(request.args.get('id', 0))
    try:
        area_res = conn.raw_command(0x0A, 0x10, data=[fru_id])
        if area_res.get('error') or not area_res.get('data') or len(area_res['data']) < 3:
            return jsonify({"ok": False, "error": "Cannot get FRU area info"})
        fru_size = int.from_bytes(bytes(area_res['data'][0:2]), 'little')
        raw = bytearray()
        offset = 0
        while offset < fru_size:
            chunk    = min(32, fru_size - offset)
            read_res = conn.raw_command(0x0A, 0x11,
                                        data=[fru_id, offset & 0xFF, (offset >> 8) & 0xFF, chunk])
            if read_res.get('error') or not read_res.get('data'):
                break
            raw.extend(read_res['data'][1:])
            offset += chunk
        parsed     = decode_fru_data(bytes(raw))
        annotation = fru_to_annotation(bytes(raw), parsed)
        multi_offset = parsed.get('header', {}).get('multi_record_offset', 0)
        if multi_offset:
            parsed['multirecord'] = decode_fru_multirecord_area(bytes(raw), multi_offset)
        return jsonify({"ok": True, "fru_id": fru_id, "size": fru_size,
                        "parsed": parsed, "annotation": annotation})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


# ═══════════════════════════════════════════════════════════════
#  Routes — Raw Command
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/raw')
@_require_bmc
def raw_page():
    conn = _get_bmc()
    cmd_ref = {}
    for netfn, cmds in COMMANDS.items():
        cmd_ref[netfn] = {
            "name": NETFN_NAMES.get(netfn, f"0x{netfn:02X}"),
            "commands": {cmd: {"name": name, "desc": desc}
                         for cmd, (name, desc) in cmds.items()}
        }
    return render_template('raw.html', bmc=conn, netfns=NETFN_NAMES,
                           cmd_ref=json.dumps(cmd_ref))


@ipmi_bp.route('/api/raw', methods=['POST'])
@_require_bmc
def api_raw():
    conn = _get_bmc()
    body = request.get_json()
    try:
        netfn        = int(body.get('netfn', 0), 16) if isinstance(body.get('netfn'), str) else int(body['netfn'])
        cmd          = int(body.get('cmd', 0),   16) if isinstance(body.get('cmd'),   str) else int(body['cmd'])
        raw_data_str = body.get('data', '').replace(' ', '')
        data         = list(bytes.fromhex(raw_data_str)) if raw_data_str else []
    except Exception as e:
        return jsonify({"ok": False, "error": f"Parse error: {e}"})

    res         = conn.raw_command(netfn, cmd, data=data)
    netfn_name  = NETFN_NAMES.get(netfn & 0xFE, f"0x{netfn:02X}")
    cmd_name    = "Unknown"
    cmd_info    = COMMANDS.get(netfn & 0xFE, {}).get(cmd)
    if cmd_info:
        cmd_name = cmd_info[0]

    resp_data = res.get('data', [])
    error     = res.get('error')
    cc        = resp_data[0] if resp_data else None
    cc_desc   = decode_cc(cc) if cc is not None else ""
    payload   = resp_data[1:] if (resp_data and cc == 0x00) else resp_data
    schema    = RESPONSE_SCHEMAS.get((netfn & 0xFE, cmd))
    annotation = decode_with_schema(payload, schema) if schema and not error else None

    return jsonify({
        "ok": not bool(error),
        "error": error,
        "netfn": netfn, "netfn_name": netfn_name,
        "cmd":   cmd,   "cmd_name":   cmd_name,
        "completion_code":      cc,
        "completion_code_desc": cc_desc,
        "raw_hex":   " ".join(f"{b:02X}" for b in resp_data),
        "annotation": annotation,
    })


# ═══════════════════════════════════════════════════════════════
#  Routes — PCAP
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/pcap')
@_require_bmc
def pcap_page():
    return render_template('pcap.html', bmc=_get_bmc())


@ipmi_bp.route('/api/pcap', methods=['POST'])
@_require_bmc
def api_pcap():
    if 'file' not in request.files:
        return jsonify({"ok": False, "error": "No file uploaded"})
    f = request.files['file']
    if not f.filename:
        return jsonify({"ok": False, "error": "Empty filename"})
    suffix = '.pcapng' if f.filename.endswith('.pcapng') else '.pcap'
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        f.save(tmp.name)
        tmp_path = tmp.name
    try:
        results = decode_pcap_file(tmp_path)
        return jsonify({"ok": True, "packets": results, "count": len(results)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})
    finally:
        os.unlink(tmp_path)


# ═══════════════════════════════════════════════════════════════
#  Routes — Device ID
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/api/device-id')
@_require_bmc
def api_device_id():
    conn = _get_bmc()
    res = conn.raw_command(0x06, 0x01)
    if res.get('error') or not res.get('data') or len(res['data']) < 12:
        return jsonify({"ok": False, "error": res.get('error', 'Insufficient data')})
    d = res['data']
    fw_major = d[2] & 0x7F
    fw_minor = d[3]
    return jsonify({
        "ok":              True,
        "device_id":       d[0],
        "device_revision": d[1] & 0x0F,
        "fw_major":        fw_major,
        "fw_minor":        fw_minor,
        "fw_version":      f"{fw_major}.{fw_minor:02X}",
        "ipmi_version":    f"{(d[4] & 0xF0) >> 4}.{d[4] & 0x0F}",
        "manufacturer_id": int.from_bytes(bytes(d[6:9]),  'little'),
        "product_id":      int.from_bytes(bytes(d[9:11]), 'little'),
        "data_hex":        ' '.join(f"{b:02X}" for b in d),
    })


# ═══════════════════════════════════════════════════════════════
#  Routes — Spec Ref
# ═══════════════════════════════════════════════════════════════

@ipmi_bp.route('/spec')
def spec_ref_page():
    return render_template('specref.html', bmc=_get_bmc())


@ipmi_bp.route('/api/search/commands')
def api_search_commands():
    q = request.args.get('q', '').strip()
    results = search_commands(q, limit=12)
    return jsonify({"ok": True, "results": results})


@ipmi_bp.route('/api/spec/request-schema')
def api_request_schema():
    try:
        netfn = int(request.args.get('netfn', '0'), 16)
        cmd   = int(request.args.get('cmd',   '0'), 16)
    except ValueError:
        return jsonify({"ok": False, "error": "Invalid netfn/cmd"})
    schema = REQUEST_SCHEMAS.get((netfn, cmd), [])
    return jsonify({"ok": True, "fields": [
        {"name": f.name, "length": f.length, "type": f.type,
         "desc": f.desc, "default": f.default, "options": f.options}
        for f in schema
    ]})


@ipmi_bp.route('/api/spec/all')
def api_spec_all():
    groups = {}
    for netfn, name in NETFN_NAMES.items():
        cmds_for_netfn = COMMANDS.get(netfn, {})
        group_cmds = []
        for cmd, (cmd_name, desc) in cmds_for_netfn.items():
            rschema = RESPONSE_SCHEMAS.get((netfn, cmd))
            qschema = REQUEST_SCHEMAS.get((netfn, cmd), [])
            group_cmds.append({
                "netfn": netfn, "cmd": cmd,
                "netfn_hex": f"0x{netfn:02X}", "cmd_hex": f"0x{cmd:02X}",
                "name": cmd_name, "desc": desc,
                "request_fields":  [{"name": f.name, "length": f.length, "desc": f.desc}
                                     for f in qschema],
                "response_fields": [{"name": f.name, "offset": f.offset,
                                     "length": f.length, "decode": f.decode,
                                     "note": f.note or ""}
                                    for f in (rschema.fields if rschema else [])],
            })
        groups[f"0x{netfn:02X}"] = {"name": name, "commands": group_cmds}
    return jsonify({"ok": True, "groups": groups})
