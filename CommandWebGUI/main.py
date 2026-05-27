import atexit
import sys
import os
import signal
import sqlite3
import tempfile
import time
import re
import threading
import base64
from pathlib import Path
from port_manager import get_free_port, write_lock, read_lock, release_lock
from flask import Flask, render_template, request, jsonify, Response
from flask_sock import Sock
import paramiko
import socket
import webbrowser
from threading import Timer

try:
    import serial
    import serial.tools.list_ports
    HAS_SERIAL = True
except ImportError:
    HAS_SERIAL = False

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── PyInstaller frozen path ──────────────────────────────────────
if getattr(sys, 'frozen', False):
    base_path = Path(sys.executable).parent
    template_folder = str(Path(sys._MEIPASS) / 'templates')
    static_folder   = str(Path(sys._MEIPASS) / 'static')
else:
    base_path = Path(__file__).parent
    template_folder = str(base_path / 'templates')
    static_folder   = str(base_path / 'static')

DB_PATH   = base_path / 'profiles.db'
LOCK_FILE = base_path / 'commandwebgui.lock'
_tray_icon = None

# Optional Basic Auth — set WEBGUI_USER + WEBGUI_PASS env vars to enable
_AUTH_USER = os.environ.get('WEBGUI_USER', '')
_AUTH_PASS = os.environ.get('WEBGUI_PASS', '')


# ═══════════════════════════════════════════════════════════════
#  DB Init
# ═══════════════════════════════════════════════════════════════

def init_db():
    with sqlite3.connect(DB_PATH) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS profiles (
            name      TEXT PRIMARY KEY,
            host      TEXT NOT NULL,
            port      INTEGER NOT NULL,
            user      TEXT NOT NULL,
            password  TEXT NOT NULL,
            saved_at  TEXT NOT NULL,
            results   TEXT,
            conn_type TEXT DEFAULT 'ssh'
        )''')
        con.execute('''CREATE TABLE IF NOT EXISTS history (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            cmd         TEXT NOT NULL,
            stdout      TEXT,
            exit_code   INTEGER,
            duration_ms INTEGER,
            ts          INTEGER NOT NULL
        )''')
        cols = [r[1] for r in con.execute("PRAGMA table_info(profiles)").fetchall()]
        if 'results' not in cols:
            con.execute('ALTER TABLE profiles ADD COLUMN results TEXT')
        if 'conn_type' not in cols:
            con.execute("ALTER TABLE profiles ADD COLUMN conn_type TEXT DEFAULT 'ssh'")

init_db()
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)


def open_browser(port):
    webbrowser.open_new(f'http://localhost:{port}')


# ═══════════════════════════════════════════════════════════════
#  Basic Auth
# ═══════════════════════════════════════════════════════════════

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

@app.before_request
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
_POOL_IDLE_TIMEOUT = 600  # 10 min


def _is_client_alive(client: paramiko.SSHClient) -> bool:
    try:
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            return False
        transport.send_ignore()  # Non-blocking keepalive — detects dead transports faster than is_active() alone
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

_t_cleanup = Timer(120, _cleanup_pool)
_t_cleanup.daemon = True
_t_cleanup.start()


# ═══════════════════════════════════════════════════════════════
#  Serial (COM Port) Session
# ═══════════════════════════════════════════════════════════════

_SERIAL_PROMPT = 'CMDWG_READY> '


class SerialSession:
    """Persistent serial console session with auto-login and fixed prompt."""

    def __init__(self, port_name: str, baud: int, user: str, password: str):
        if not HAS_SERIAL:
            raise RuntimeError('pyserial is not installed. Run: pip install pyserial')
        if '://' in port_name:
            # socket://host:port  or  rfc2217://host:port  — no COM driver needed
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
        """Execute command; returns (stdout: str, exit_code: int)."""
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

@app.route('/')
def index():
    return render_template('index.html')


# ═══════════════════════════════════════════════════════════════
#  Routes — SSH
# ═══════════════════════════════════════════════════════════════

@app.route('/api/test', methods=['POST'])
def test_connection():
    data = request.json or {}
    host     = data.get('host')
    port     = data.get('port')
    user     = data.get('user')
    password = data.get('password')
    if not host or not port or not user or not password:
        return jsonify({'error': 'Missing required parameters'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'Port must be a valid number'}), 400

    start = time.time()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(host, port=port, username=user, password=password, timeout=8)
        client.close()
        return jsonify({'ok': True, 'duration_ms': int((time.time() - start) * 1000)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e),
                        'duration_ms': int((time.time() - start) * 1000)}), 400


@app.route('/api/run', methods=['POST'])
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


@app.route('/api/discover', methods=['POST'])
def discover():
    """SSH discover — sequential to avoid relying on undocumented Paramiko threading guarantees."""
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

@app.route('/api/serial/ports', methods=['GET'])
def list_serial_ports():
    if not HAS_SERIAL:
        return jsonify({'ports': [], 'error': 'pyserial not installed'})
    ports = [{'device': p.device, 'description': p.description or p.device}
             for p in serial.tools.list_ports.comports()]
    return jsonify({'ports': ports})


@app.route('/api/serial/test', methods=['POST'])
def test_serial():
    if not HAS_SERIAL:
        return jsonify({'ok': False, 'error': 'pyserial not installed'}), 400
    data = request.json or {}
    port_name = data.get('host', '')
    try:
        baud = int(data.get('port', 115200))
    except (ValueError, TypeError):
        baud = 115200
    user     = data.get('user', 'root')
    password = data.get('password', '')
    if not port_name:
        return jsonify({'ok': False, 'error': 'COM port name required'}), 400

    start = time.time()
    try:
        sess = SerialSession(port_name, baud, user, password)
        sess.close()
        return jsonify({'ok': True, 'duration_ms': int((time.time() - start) * 1000)})
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e),
                        'duration_ms': int((time.time() - start) * 1000)}), 400


@app.route('/api/serial/run', methods=['POST'])
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


@app.route('/api/serial/discover', methods=['POST'])
def serial_discover():
    """Serial discover — inherently sequential (one command at a time on a serial port)."""
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

@app.route('/api/survey', methods=['POST'])
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


@app.route('/api/probe', methods=['POST'])
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
    import json as _json
    d = dict(row)
    if d.get('results'):
        try: d['results'] = _json.loads(d['results'])
        except Exception: d['results'] = None
    d.setdefault('conn_type', 'ssh')
    return d


@app.route('/api/profiles', methods=['GET'])
def list_profiles():
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM profiles ORDER BY saved_at DESC').fetchall()
    return jsonify({'profiles': [_row_to_dict(r) for r in rows]})


@app.route('/api/profiles/save', methods=['POST'])
def save_profile():
    import json as _json
    data = request.json or {}
    name      = data.get('name', '').strip()
    host      = data.get('host', '').strip()
    port      = data.get('port')
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')

    if not name or not host or not port or not user:
        return jsonify({'error': 'name, host, port, and user are required'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'Port must be a valid number'}), 400

    results = data.get('results')
    if results is not None:
        results = _json.dumps(results, ensure_ascii=False)

    saved_at = time.strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            'INSERT OR REPLACE INTO profiles '
            '(name, host, port, user, password, saved_at, results, conn_type) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (name, host, port, user, password, saved_at, results, conn_type)
        )
    return jsonify({'ok': True, 'name': name, 'path': str(DB_PATH.resolve())})


@app.route('/api/profiles/<name>', methods=['GET'])
def load_profile(name):
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
    if row is None:
        return jsonify({'error': 'profile not found'}), 404
    return jsonify(_row_to_dict(row))


@app.route('/api/profiles/<name>', methods=['PUT'])
def update_profile(name):
    data = request.json or {}
    new_name  = data.get('name', '').strip()
    host      = data.get('host', '').strip()
    port      = data.get('port')
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')

    if not new_name or not host or not port or not user:
        return jsonify({'error': 'name, host, port, and user are required'}), 400
    try:
        port = int(port)
    except (ValueError, TypeError):
        return jsonify({'error': 'Port must be a valid number'}), 400

    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
        if row is None:
            return jsonify({'error': 'profile not found'}), 404
        existing = dict(row)
        if name != new_name:
            con.execute('DELETE FROM profiles WHERE name=?', (name,))
        con.execute(
            'INSERT OR REPLACE INTO profiles '
            '(name, host, port, user, password, saved_at, results, conn_type) '
            'VALUES (?,?,?,?,?,?,?,?)',
            (new_name, host, port, user, password,
             existing.get('saved_at', ''), existing.get('results'), conn_type)
        )
    return jsonify({'ok': True, 'name': new_name})


@app.route('/api/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    with sqlite3.connect(DB_PATH) as con:
        cur = con.execute('DELETE FROM profiles WHERE name=?', (name,))
    if cur.rowcount == 0:
        return jsonify({'error': 'profile not found'}), 404
    return jsonify({'ok': True})


@app.route('/api/profiles/export/<name>', methods=['GET'])
def export_profile(name):
    with sqlite3.connect(DB_PATH) as src:
        src.row_factory = sqlite3.Row
        row = src.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
    if row is None:
        return jsonify({'error': 'profile not found'}), 404

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        with sqlite3.connect(tmp.name) as dst:
            dst.execute('''CREATE TABLE profiles (
                name TEXT PRIMARY KEY, host TEXT NOT NULL, port INTEGER NOT NULL,
                user TEXT NOT NULL, password TEXT NOT NULL, saved_at TEXT NOT NULL,
                results TEXT, conn_type TEXT DEFAULT 'ssh'
            )''')
            d = dict(row)
            dst.execute(
                'INSERT INTO profiles (name, host, port, user, password, saved_at, results, conn_type) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (d['name'], d['host'], d['port'], d['user'],
                 d.get('password', ''), d.get('saved_at', ''),
                 d.get('results'), d.get('conn_type', 'ssh'))
            )
        with open(tmp.name, 'rb') as f:
            data = f.read()
        safe = re.sub(r'[^\w\-]', '_', name) or 'profile'
        return Response(data, mimetype='application/x-sqlite3',
                        headers={'Content-Disposition': f'attachment; filename="{safe}.db"'})
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@app.route('/api/profiles/generate', methods=['POST'])
def generate_profile_db():
    import json as _json
    data = request.json or {}
    name      = data.get('name', 'bmc').strip() or 'bmc'
    host      = data.get('host', '').strip()
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')
    try:
        port = int(data.get('port', 22))
    except (ValueError, TypeError):
        port = 22

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        with sqlite3.connect(tmp.name) as dst:
            dst.execute('''CREATE TABLE profiles (
                name TEXT PRIMARY KEY, host TEXT NOT NULL, port INTEGER NOT NULL,
                user TEXT NOT NULL, password TEXT NOT NULL, saved_at TEXT NOT NULL,
                results TEXT, conn_type TEXT DEFAULT 'ssh'
            )''')
            results = data.get('results')
            if results is not None:
                results = _json.dumps(results, ensure_ascii=False)
            saved_at = time.strftime('%Y-%m-%d %H:%M:%S')
            dst.execute(
                'INSERT INTO profiles (name, host, port, user, password, saved_at, results, conn_type) '
                'VALUES (?,?,?,?,?,?,?,?)',
                (name, host, port, user, password, saved_at, results, conn_type)
            )
        with open(tmp.name, 'rb') as f:
            file_data = f.read()
        return Response(file_data, mimetype='application/x-sqlite3')
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@app.route('/api/profiles/import', methods=['POST'])
def import_profiles():
    """Merge imported profiles into local DB — existing profiles with the same name are overwritten,
    but profiles not present in the import file are preserved."""
    f = request.files.get('file')
    if not f:
        return jsonify({'error': 'no file uploaded'}), 400

    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        f.save(tmp.name)
        try:
            with sqlite3.connect(tmp.name) as src:
                src.row_factory = sqlite3.Row
                cols = [r[1] for r in src.execute("PRAGMA table_info(profiles)").fetchall()]
                if not cols:
                    return jsonify({'error': 'invalid DB: no profiles table'}), 400
                rows = src.execute('SELECT * FROM profiles').fetchall()
        except sqlite3.DatabaseError as e:
            return jsonify({'error': f'not a valid SQLite DB: {e}'}), 400

        imported = 0
        with sqlite3.connect(DB_PATH) as dst:
            for r in rows:
                d = dict(r)
                dst.execute(
                    'INSERT OR REPLACE INTO profiles '
                    '(name, host, port, user, password, saved_at, results, conn_type) '
                    'VALUES (?,?,?,?,?,?,?,?)',
                    (d.get('name'), d.get('host'), d.get('port'), d.get('user'),
                     d.get('password', ''), d.get('saved_at', ''),
                     d.get('results'), d.get('conn_type', 'ssh'))
                )
                imported += 1
        return jsonify({'ok': True, 'imported': imported})
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@app.route('/api/profiles/export_all', methods=['GET'])
def export_all_profiles():
    with open(DB_PATH, 'rb') as f:
        data = f.read()
    return Response(data, mimetype='application/x-sqlite3',
                    headers={'Content-Disposition': 'attachment; filename="all_profiles.db"'})


# ═══════════════════════════════════════════════════════════════
#  Routes — Command History
# ═══════════════════════════════════════════════════════════════

@app.route('/api/history', methods=['GET'])
def get_history():
    with sqlite3.connect(DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute(
            'SELECT id, cmd, stdout, exit_code, duration_ms, ts '
            'FROM history ORDER BY ts DESC LIMIT 200'
        ).fetchall()
    return jsonify({'history': [dict(r) for r in rows]})


@app.route('/api/history', methods=['POST'])
def add_history():
    data = request.json or {}
    cmd         = data.get('cmd', '')
    stdout      = (data.get('stdout', '') or '')[:800]
    exit_code   = data.get('exit_code', -1)
    duration_ms = data.get('duration_ms', 0)
    ts = int(time.time() * 1000)
    with sqlite3.connect(DB_PATH) as con:
        con.execute(
            'INSERT INTO history (cmd, stdout, exit_code, duration_ms, ts) VALUES (?,?,?,?,?)',
            (cmd, stdout, exit_code, duration_ms, ts)
        )
    return jsonify({'ok': True})


@app.route('/api/history', methods=['DELETE'])
def clear_history():
    with sqlite3.connect(DB_PATH) as con:
        con.execute('DELETE FROM history')
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
#  Routes — Debug
# ═══════════════════════════════════════════════════════════════

@app.route('/api/pool/status', methods=['GET'])
def pool_status():
    with _pool_lock:
        entries = [
            {'host': k[0], 'port': k[1], 'user': k[2],
             'alive': _is_client_alive(v['client']),
             'idle_sec': int(time.time() - v['last_used'])}
            for k, v in _ssh_pool.items()
        ]
    return jsonify({'pool': entries, 'count': len(entries)})


# ═══════════════════════════════════════════════════════════════
#  Routes — Shutdown
# ═══════════════════════════════════════════════════════════════

@app.route('/api/shutdown', methods=['POST'])
def shutdown():
    def _exit():
        time.sleep(0.3)
        if _tray_icon:
            try: _tray_icon.stop()
            except Exception: pass
        release_lock(LOCK_FILE)
        os._exit(0)
    threading.Thread(target=_exit, daemon=True).start()
    return jsonify({'ok': True})


# ═══════════════════════════════════════════════════════════════
#  Single Instance + System Tray
# ═══════════════════════════════════════════════════════════════

def _check_single_instance() -> bool:
    """Return True if we are the only instance; False if another is already running."""
    existing_port = read_lock(LOCK_FILE)
    if existing_port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(('localhost', existing_port)) == 0:
                webbrowser.open_new(f'http://localhost:{existing_port}')
                return False
    return True


def _make_tray_image():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(11, 25, 40))
    # [ symbol
    draw.line([(16, 16), (16, 48)], fill=(79, 195, 247), width=5)
    draw.line([(16, 16), (26, 16)], fill=(79, 195, 247), width=5)
    draw.line([(16, 48), (26, 48)], fill=(79, 195, 247), width=5)
    # > arrow
    draw.polygon([(34, 20), (34, 44), (52, 32)], fill=(79, 195, 247))
    return img


def _run_tray(port: int):
    global _tray_icon
    if not HAS_TRAY:
        return

    def on_open(icon, item):
        webbrowser.open_new(f'http://localhost:{port}')

    def on_exit(icon, item):
        icon.stop()
        release_lock(LOCK_FILE)
        os._exit(0)

    img = _make_tray_image()
    menu = pystray.Menu(
        pystray.MenuItem('開啟 CommandWebGUI', on_open, default=True),
        pystray.MenuItem('結束', on_exit),
    )
    _tray_icon = pystray.Icon('CommandWebGUI', img, f'CommandWebGUI  http://localhost:{port}', menu)
    _tray_icon.run()  # blocks until icon.stop()


# ═══════════════════════════════════════════════════════════════
#  Entry Point
# ═══════════════════════════════════════════════════════════════

from dbus_engine import register_dbus_routes
sock = Sock(app)
register_dbus_routes(app, sock, _get_pooled_client, _evict_from_pool)

if __name__ == '__main__':
    if not _check_single_instance():
        sys.exit(0)

    available_port = int(os.environ.get("PORT") or get_free_port())
    write_lock(available_port, LOCK_FILE)
    atexit.register(release_lock, LOCK_FILE)

    def _shutdown_handler(sig, frame):
        if _tray_icon:
            try: _tray_icon.stop()
            except Exception: pass
        release_lock(LOCK_FILE)
        os._exit(0)

    signal.signal(signal.SIGINT,  _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    print(f'[CommandWebGUI] http://localhost:{available_port}')
    if _AUTH_USER:
        print(f'[CommandWebGUI] Basic Auth enabled (user: {_AUTH_USER})')
    if not HAS_SERIAL:
        print('[CommandWebGUI] pyserial not found — COM port features disabled (pip install pyserial)')
    if not HAS_TRAY:
        print('[CommandWebGUI] pystray/Pillow not found — system tray disabled (pip install pystray pillow)')

    if HAS_TRAY:
        flask_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=available_port, debug=False),
            daemon=True
        )
        flask_thread.start()
        Timer(1.5, open_browser, args=[available_port]).start()
        _run_tray(available_port)   # blocks in main thread; exits when tray icon stops
    else:
        Timer(1.5, open_browser, args=[available_port]).start()
        app.run(host='0.0.0.0', port=available_port, debug=False)
        release_lock(LOCK_FILE)
