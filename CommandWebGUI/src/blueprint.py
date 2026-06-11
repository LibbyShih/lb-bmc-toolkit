"""
CommandWebGUI — Flask Blueprint
所有 HTTP routes 集中於此，可被 standalone main.py 或 ToolEntry 掛載。
"""
import json
import os
import re
import sqlite3
import tempfile
import time
import threading
import base64
from pathlib import Path
from threading import Timer

from flask import Blueprint, render_template, request, jsonify, Response, session
import paramiko
import socket

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

# ── Blueprint ────────────────────────────────────────────────────────────────
cwg_bp = Blueprint(
    'cwg', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/static',
)

# ── History DB ───────────────────────────────────────────────────────────────
_DB_PATH = Path('profiles.db')

def set_db(path: Path):
    global _DB_PATH
    _DB_PATH = path
    with sqlite3.connect(_DB_PATH) as con:
        con.execute(
            'CREATE TABLE IF NOT EXISTS history '
            '(id INTEGER PRIMARY KEY AUTOINCREMENT, cmd TEXT, stdout TEXT, '
            'exit_code INTEGER, duration_ms INTEGER, ts INTEGER)'
        )

# ── URL prefix (standalone '' vs ToolEntry '/cwg') ─────────────────────────────
_URL_PREFIX = '/cwg'
_shutdown_callback = None


def set_url_prefix(prefix: str):
    """Call before register_blueprint: '' for standalone, '/cwg' under ToolEntry."""
    global _URL_PREFIX
    _URL_PREFIX = (prefix or '').rstrip('/')


def set_shutdown_callback(callback):
    """Register app-level shutdown (tray stop, lock release, os._exit)."""
    global _shutdown_callback
    _shutdown_callback = callback


# ── Context Processor ────────────────────────────────────────────────────────
@cwg_bp.context_processor
def inject_cwg_vars():
    bmc = session.get('bmc')
    return {
        'CWG_BASE':  _URL_PREFIX,
        'hub_creds': bmc,
    }



# ── Basic Auth（選用）────────────────────────────────────────────────────────
_AUTH_USER = os.environ.get('WEBGUI_USER', '')
_AUTH_PASS = os.environ.get('WEBGUI_PASS', '')

def _check_auth(req) -> bool:
    if not _AUTH_USER:
        return True
    auth = req.headers.get('Authorization', '')
    if not auth.startswith('Basic '):
        return False
    try:
        decoded = base64.b64decode(auth[6:]).decode('utf-8')
        u, p = decoded.split(':', 1)
        return u == _AUTH_USER and p == _AUTH_PASS
    except Exception:
        return False

@cwg_bp.before_request
def require_auth():
    if not _check_auth(request):
        return Response(
            'Authentication required', 401,
            {'WWW-Authenticate': 'Basic realm="CommandWebGUI"'}
        )

# ═══════════════════════════════════════════════════════════════
#  SSH Connection Pool
# ═══════════════════════════════════════════════════════════════

_ssh_pool: dict = {}
_pool_lock = threading.Lock()
_POOL_IDLE_TIMEOUT = 600


def _is_client_alive(client: paramiko.SSHClient) -> bool:
    try:
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            return False
        transport.send_ignore()
        return True
    except Exception:
        return False


def _get_pooled_client(host: str, port: int, user: str, password: str) -> paramiko.SSHClient:
    key = (host, port, user)
    with _pool_lock:
        entry = _ssh_pool.get(key)
        if entry and _is_client_alive(entry['client']):
            entry['last_used'] = time.time()
            return entry['client']
        if entry:
            try: entry['client'].close()
            except Exception: pass
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(host, port=port, username=user, password=password, timeout=8)
        _ssh_pool[key] = {'client': client, 'last_used': time.time()}
        return client


def _evict_from_pool(host: str, port: int, user: str):
    key = (host, port, user)
    with _pool_lock:
        entry = _ssh_pool.pop(key, None)
    if entry:
        try: entry['client'].close()
        except Exception: pass


def _cleanup_pool():
    now = time.time()
    with _pool_lock:
        stale = [k for k, v in _ssh_pool.items() if now - v['last_used'] > _POOL_IDLE_TIMEOUT]
        for k in stale:
            try: _ssh_pool[k]['client'].close()
            except Exception: pass
            del _ssh_pool[k]
    if stale:
        print(f'[ssh-pool] Evicted {len(stale)} idle connection(s).')
    t = Timer(120, _cleanup_pool)
    t.daemon = True
    t.start()

_t = Timer(120, _cleanup_pool)
_t.daemon = True
_t.start()


# ═══════════════════════════════════════════════════════════════
#  Serial (COM Port) Session
# ═══════════════════════════════════════════════════════════════

_SERIAL_PROMPT = 'CMDWG_READY> '


class SerialSession:
    def __init__(self, port_name: str, baud: int, user: str, password: str):
        if not HAS_SERIAL:
            raise RuntimeError('pyserial not installed')
        if '://' in port_name:
            self.ser = serial.serial_for_url(port_name, timeout=0.1)
        else:
            self.ser = serial.Serial(port_name, baud, timeout=0.1,
                                      bytesize=8, parity='N', stopbits=1)
        self.alive = False
        self._login(user, password)
        self._setup_prompt()
        self.alive = True

    def is_alive(self) -> bool:
        return self.alive and self.ser.is_open

    def close(self):
        self.alive = False
        try: self.ser.close()
        except Exception: pass

    def _send(self, text: str):
        self.ser.write((text + '\r\n').encode('utf-8', errors='replace'))

    def _read_until(self, patterns: list, timeout: float = 15) -> str:
        buf = b''
        deadline = time.time() + timeout
        while time.time() < deadline:
            chunk = self.ser.read(4096)
            if chunk:
                buf += chunk
                text = buf.decode('utf-8', errors='replace')
                if any(p in text for p in patterns):
                    return text
            else:
                time.sleep(0.05)
        return buf.decode('utf-8', errors='replace')

    def _login(self, user: str, password: str):
        self.ser.write(b'\r\n')
        time.sleep(0.3)
        self.ser.reset_input_buffer()
        self.ser.write(b'\r\n')
        out = self._read_until(['ogin:', '# ', '$ '], timeout=8)
        if 'ogin:' in out.lower():
            self._send(user)
            out = self._read_until(['assword:'], timeout=5)
            self._send(password)
            out = self._read_until(['# ', '$ ', 'incorrect', 'denied', 'failed'], timeout=10)
            if any(x in out.lower() for x in ['incorrect', 'denied', 'failed', 'authentication']):
                raise Exception('Serial login failed: authentication error')

    def _setup_prompt(self):
        self._send(f"export PS1='{_SERIAL_PROMPT}'")
        self._read_until([_SERIAL_PROMPT], timeout=5)
        self.ser.reset_input_buffer()

    def _strip_output(self, raw: str, cmd: str) -> str:
        text = raw.replace('\r\n', '\n').replace('\r', '\n')
        lines = text.split('\n')
        result = []
        skip_echo = True
        for line in lines:
            if skip_echo and cmd.strip() in line:
                skip_echo = False
                continue
            if _SERIAL_PROMPT.strip() in line:
                continue
            result.append(line)
        while result and not result[0].strip():
            result.pop(0)
        while result and not result[-1].strip():
            result.pop()
        return '\n'.join(result)

    def exec_command(self, cmd: str, timeout: float = 15):
        self._send(cmd)
        raw = self._read_until([_SERIAL_PROMPT], timeout=timeout)
        stdout = self._strip_output(raw, cmd)
        self._send('echo $?')
        ec_raw = self._read_until([_SERIAL_PROMPT], timeout=5)
        exit_code = 0
        try:
            ec_text = ec_raw.replace('\r\n', '\n').replace('\r', '\n')
            ec_lines = [l.strip() for l in ec_text.split('\n')
                        if l.strip() and _SERIAL_PROMPT.strip() not in l
                        and l.strip() != 'echo $?']
            if ec_lines:
                exit_code = int(ec_lines[0])
        except (ValueError, IndexError):
            pass
        return stdout, exit_code


_serial_pool: dict = {}
_serial_lock = threading.Lock()


def _get_serial_session(port_name: str, baud: int, user: str, password: str) -> SerialSession:
    key = (port_name, baud, user)
    with _serial_lock:
        sess = _serial_pool.get(key)
        if sess and sess.is_alive():
            return sess
        if sess:
            try: sess.close()
            except Exception: pass
        sess = SerialSession(port_name, baud, user, password)
        _serial_pool[key] = sess
        return sess


def _evict_serial(port_name: str, baud: int, user: str):
    key = (port_name, baud, user)
    with _serial_lock:
        sess = _serial_pool.pop(key, None)
    if sess:
        try: sess.close()
        except Exception: pass


# ═══════════════════════════════════════════════════════════════
#  Shared Discover Logic
# ═══════════════════════════════════════════════════════════════

PROBE_TOOLS = ['obmcutil', 'ipmitool', 'busctl', 'systemctl', 'busybox',
               'phosphor-state-manager', 'journalctl', 'devmem2', 'i2cdetect', 'gpioget']

_DISCOVER_STEPS = [
    ('tools',       '; '.join(f'command -v {t} >/dev/null 2>&1 && echo {t}' for t in PROBE_TOOLS)),
    ('busybox',     'busybox --list 2>/dev/null'),
    ('dbus',        'busctl list --acquired --no-pager 2>/dev/null'),
    ('services',    'systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null'),
    ('os_release',  'cat /etc/os-release 2>/dev/null'),
    ('uname',       'uname -a 2>/dev/null'),
    ('machine',     'cat /etc/machine-info 2>/dev/null; cat /etc/hostname 2>/dev/null'),
    ('df',          'df -h 2>/dev/null'),
    ('free',        'free -m 2>/dev/null'),
    ('ip_addr',     'ip addr 2>/dev/null'),
    ('sensors',     'ipmitool sdr list 2>/dev/null'),
    ('busybox_ver', 'busybox 2>&1 | head -1'),
]


def _exec_step_ssh(client, name, cmd):
    try:
        _, stdout, stderr = client.exec_command(cmd, timeout=12)
        out = stdout.read().decode('utf-8', errors='replace')
        err = stderr.read().decode('utf-8', errors='replace')
        return name, {'output': out or err or '(empty)', 'cmd': cmd}
    except Exception as ex:
        return name, {'output': f'(error: {ex})', 'cmd': cmd}


def _parse_discover_results(raw: dict) -> dict:
    result = {}
    found = set(raw['tools']['output'].split())
    result['tools'] = {t: (t in found) for t in PROBE_TOOLS}
    bb = raw['busybox']['output'].strip()
    result['busybox_applets'] = sorted(bb.split()) if bb and 'error' not in bb else []
    bb_ver = raw['busybox_ver']['output'].strip()
    m = re.search(r'v[\d.]+', bb_ver)
    result['busybox_version'] = m.group(0) if m else ''
    dbus_lines = raw['dbus']['output'].strip().split('\n')
    dbus_svcs = []
    for line in dbus_lines:
        parts = line.split()
        if parts and (parts[0].startswith('xyz.') or parts[0].startswith('org.')):
            dbus_svcs.append(parts[0])
    result['dbus_services'] = sorted(set(dbus_svcs))
    svc_lines = raw['services']['output'].strip().split('\n')
    running = []
    for line in svc_lines:
        parts = line.split(None, 4)
        if len(parts) >= 4 and parts[0].endswith('.service'):
            running.append({'unit': parts[0], 'desc': parts[4] if len(parts) > 4 else ''})
    result['running_services'] = running
    os_info = {}
    for line in raw['os_release']['output'].split('\n'):
        if '=' in line:
            k, v = line.split('=', 1)
            os_info[k.strip()] = v.strip().strip('"')
    result['os_info'] = {
        'os_release': os_info.get('PRETTY_NAME', os_info.get('NAME', '')),
        'machine': os_info.get('OPENBMC_TARGET_MACHINE',
                   raw['machine']['output'].strip().split('\n')[0]
                   if raw['machine']['output'].strip() else ''),
        'kernel':   raw['uname']['output'].strip(),
        'build_id': os_info.get('VERSION_ID', ''),
    }
    result['fs_info']     = raw['df']['output'].strip()
    result['mem_info']    = raw['free']['output'].strip()
    result['net_info']    = raw['ip_addr']['output'].strip()
    result['sensor_info'] = raw['sensors']['output'].strip()
    return result


# ═══════════════════════════════════════════════════════════════
#  Routes — Pages
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/')
@cwg_bp.route('/command')
@cwg_bp.route('/dbus')
def index():
    return render_template('index.html')


# ═══════════════════════════════════════════════════════════════
#  Routes — SSH
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/api/test', methods=['POST'])
def test_connection():
    from bmc_template.connection_test import preflight_connection_test

    data = request.json or {}
    result = preflight_connection_test({
        'conn_type': 'ssh',
        'host': data.get('host'),
        'port': data.get('port'),
        'user': data.get('user'),
        'password': data.get('password', ''),
    })
    status = 200 if result.get('ok') else 400
    return jsonify(result), status


@cwg_bp.route('/api/run', methods=['POST'])
def run_command():
    data = request.json or {}
    host     = data.get('host')
    port     = data.get('port')
    user     = data.get('user')
    password = data.get('password')
    command  = data.get('command')
    if not host or not port or not user or not password:
        return jsonify({'error': 'Missing required parameters'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'Port must be a valid number'}), 400
    if not command:
        return jsonify({'error': 'command required'}), 400
    start = time.time()
    try:
        client = _get_pooled_client(host, port, user, password)
        _, stdout, stderr = client.exec_command(command, timeout=30)
        out      = stdout.read().decode('utf-8', errors='replace')
        err      = stderr.read().decode('utf-8', errors='replace')
        exit_code = stdout.channel.recv_exit_status()
        return jsonify({'stdout': out, 'stderr': err, 'exit_code': exit_code,
                        'duration_ms': int((time.time() - start) * 1000)})
    except Exception as e:
        _evict_from_pool(host, port, user)
        return jsonify({'error': str(e), 'duration_ms': int((time.time() - start) * 1000)}), 500


@cwg_bp.route('/api/discover', methods=['POST'])
def discover():
    data = request.json or {}
    host     = data.get('host')
    port     = data.get('port')
    user     = data.get('user')
    password = data.get('password')
    if not host or not port or not user or not password:
        return jsonify({'error': 'missing connection params'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid port'}), 400
    try:
        client = _get_pooled_client(host, port, user, password)
        raw = {}
        for name, cmd in _DISCOVER_STEPS:
            n, result = _exec_step_ssh(client, name, cmd)
            raw[n] = result
    except Exception as e:
        _evict_from_pool(host, port, user)
        return jsonify({'error': str(e)}), 500
    return jsonify(_parse_discover_results(raw))


# ═══════════════════════════════════════════════════════════════
#  Routes — Serial (COM Port)
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/api/serial/ports', methods=['GET'])
def list_serial_ports():
    if not HAS_SERIAL:
        return jsonify({'ports': [], 'error': 'pyserial not installed'})
    ports = [{'device': p.device, 'description': p.description or p.device}
             for p in serial.tools.list_ports.comports()]
    return jsonify({'ports': ports})


@cwg_bp.route('/api/serial/test', methods=['POST'])
def test_serial():
    from bmc_template.connection_test import preflight_connection_test

    data = request.json or {}
    result = preflight_connection_test({
        'conn_type': 'serial',
        'host': data.get('host', ''),
        'port': data.get('port', 115200),
        'user': data.get('user', 'root'),
        'password': data.get('password', ''),
    })
    status = 200 if result.get('ok') else 400
    return jsonify(result), status


@cwg_bp.route('/api/serial/run', methods=['POST'])
def run_serial_command():
    if not HAS_SERIAL:
        return jsonify({'error': 'pyserial not installed'}), 400
    data = request.json or {}
    port_name = data.get('host', '')
    try:
        baud = int(data.get('port', 115200))
    except (ValueError, TypeError):
        baud = 115200
    user     = data.get('user', 'root')
    password = data.get('password', '')
    command  = data.get('command', '')
    if not command:
        return jsonify({'error': 'command required'}), 400
    start = time.time()
    try:
        sess = _get_serial_session(port_name, baud, user, password)
        stdout, exit_code = sess.exec_command(command, timeout=30)
        return jsonify({'stdout': stdout, 'stderr': '', 'exit_code': exit_code,
                        'duration_ms': int((time.time() - start) * 1000)})
    except Exception as e:
        _evict_serial(port_name, baud, user)
        return jsonify({'error': str(e), 'duration_ms': int((time.time() - start) * 1000)}), 500


@cwg_bp.route('/api/serial/discover', methods=['POST'])
def serial_discover():
    if not HAS_SERIAL:
        return jsonify({'error': 'pyserial not installed'}), 400
    data = request.json or {}
    port_name = data.get('host', '')
    try:
        baud = int(data.get('port', 115200))
    except (ValueError, TypeError):
        baud = 115200
    user     = data.get('user', 'root')
    password = data.get('password', '')
    if not port_name:
        return jsonify({'error': 'COM port name required'}), 400
    try:
        sess = _get_serial_session(port_name, baud, user, password)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    raw = {}
    for name, cmd in _DISCOVER_STEPS:
        try:
            stdout, _ = sess.exec_command(cmd, timeout=12)
            raw[name] = {'output': stdout or '(empty)', 'cmd': cmd}
        except Exception as ex:
            raw[name] = {'output': f'(error: {ex})', 'cmd': cmd}
    return jsonify(_parse_discover_results(raw))


# ═══════════════════════════════════════════════════════════════
#  Routes — Legacy (survey / probe)
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/api/survey', methods=['POST'])
def survey():
    data = request.json or {}
    host     = data.get('host', 'localhost')
    port     = int(data.get('port', 2222))
    user     = data.get('user', 'root')
    password = data.get('password', '0penBmc')
    survey_steps = [
        ('System Info',       'cat /etc/os-release 2>/dev/null | head -12; echo; uname -a'),
        ('Uptime / Memory',   'uptime; echo; free -m'),
        ('Disk Usage',        'df -h 2>/dev/null'),
        ('BMC State',         'obmcutil state 2>/dev/null'),
        ('IPMI MC Info',      'ipmitool mc info 2>/dev/null'),
        ('Network',           'ip addr 2>/dev/null'),
        ('Running Services',  'systemctl list-units --type=service --state=running --no-legend --no-pager 2>/dev/null'),
        ('Binaries (/usr/bin)','ls /usr/bin 2>/dev/null | tr "\\n" "  "'),
        ('BusyBox Applets',   'busybox --list 2>/dev/null | tr "\\n" "  "'),
        ('Failed Services',   'systemctl list-units --type=service --state=failed --no-legend --no-pager 2>/dev/null'),
    ]
    try:
        client = _get_pooled_client(host, port, user, password)
        raw = {}
        for name, cmd in survey_steps:
            n, result = _exec_step_ssh(client, name, cmd)
            raw[n] = result
        return jsonify({'results': raw})
    except Exception as e:
        _evict_from_pool(host, port, user)
        return jsonify({'error': str(e)}), 500


@cwg_bp.route('/api/probe', methods=['POST'])
def probe_tools():
    data = request.json or {}
    host     = data.get('host')
    port     = data.get('port')
    user     = data.get('user')
    password = data.get('password')
    if not host or not port or not user or not password:
        return jsonify({'error': 'missing connection params'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'invalid port'}), 400
    probe_cmd = '; '.join(f'command -v {t} >/dev/null 2>&1 && echo {t}' for t in PROBE_TOOLS)
    try:
        client = _get_pooled_client(host, port, user, password)
        _, stdout, _ = client.exec_command(probe_cmd, timeout=10)
        found = set(stdout.read().decode('utf-8', errors='replace').split())
        return jsonify({'available': {t: (t in found) for t in PROBE_TOOLS}})
    except Exception as e:
        _evict_from_pool(host, port, user)
        return jsonify({'error': str(e)}), 500


# ═══════════════════════════════════════════════════════════════
#  Routes — Profile CRUD
# ═══════════════════════════════════════════════════════════════

def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get('results'):
        try: d['results'] = json.loads(d['results'])
        except Exception: d['results'] = None
    d.setdefault('conn_type', 'ssh')
    return d




# ═══════════════════════════════════════════════════════════════
#  Routes — Command History
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/api/history', methods=['GET'])
def get_history():
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            'SELECT id, cmd, stdout, exit_code, duration_ms, ts '
            'FROM history ORDER BY ts DESC LIMIT 200'
        ).fetchall()
    return jsonify({'history': [dict(r) for r in rows]})


@cwg_bp.route('/api/history', methods=['POST'])
def add_history():
    data = request.json or {}
    cmd         = data.get('cmd', '')
    stdout      = (data.get('stdout', '') or '')[:800]
    exit_code   = data.get('exit_code', -1)
    duration_ms = data.get('duration_ms', 0)
    ts = int(time.time() * 1000)
    with sqlite3.connect(_DB_PATH) as con:
        con.execute(
            'INSERT INTO history (cmd, stdout, exit_code, duration_ms, ts) VALUES (?,?,?,?,?)',
            (cmd, stdout, exit_code, duration_ms, ts)
        )
    return jsonify({'ok': True})


@cwg_bp.route('/api/history', methods=['DELETE'])
def clear_history():
    with sqlite3.connect(_DB_PATH) as con:
        con.execute('DELETE FROM history')
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
#  Routes — Debug + Shutdown
# ═══════════════════════════════════════════════════════════════

@cwg_bp.route('/api/pool/status', methods=['GET'])
def pool_status():
    with _pool_lock:
        entries = [
            {'host': k[0], 'port': k[1], 'user': k[2],
             'alive': _is_client_alive(v['client']),
             'idle_sec': int(time.time() - v['last_used'])}
            for k, v in _ssh_pool.items()
        ]
    return jsonify({'pool': entries, 'count': len(entries)})


@cwg_bp.route('/api/shutdown', methods=['POST'])
def shutdown():
    import os as _os

    def _exit():
        time.sleep(0.2)
        if _shutdown_callback:
            _shutdown_callback()
        else:
            _os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return jsonify({'ok': True})
