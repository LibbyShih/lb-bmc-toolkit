"""
BMC ToolEntry — 統一入口（單一 port）
Hub (/) → CommandWebGUI (/cwg/) → IPMI Inspector (/ipmi/)
"""
import importlib.util
import math
import os
import signal
import sys
import threading
import webbrowser
from pathlib import Path
from threading import Timer

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Paths ─────────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    _ROOT    = Path(sys.executable).parent
    _MEIPASS = Path(sys._MEIPASS)
    _cwg_bp  = _MEIPASS / 'cwg_src'  / 'blueprint.py'
    _ipmi_bp = _MEIPASS / 'ipmi_src' / 'blueprint.py'
    _extra_paths: list[Path] = []
else:
    _SRC     = Path(__file__).resolve().parent
    _ROOT    = _SRC.parent
    _BMC     = _ROOT.parent          # (siblings: CommandWebGUI, IPMI-inspector)
    _cwg_bp  = _BMC / 'CommandWebGUI'   / 'src' / 'blueprint.py'
    _ipmi_bp = _BMC / 'IPMI-inspector' / 'src' / 'blueprint.py'
    _extra_paths = [
        _SRC, _BMC / 'CommandWebGUI' / 'src',
        _BMC / 'IPMI-inspector', _BMC / 'IPMI-inspector' / 'src',
    ]

_LOCK_FILE = _ROOT / 'toolentry.lock'
_tray_icon = None

for p in _extra_paths:
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _load(alias: str, path: Path):
    """用 importlib 精確載入同名 blueprint.py，避免 sys.modules 衝突。"""
    spec = importlib.util.spec_from_file_location(alias, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


_cwg_mod  = _load('cwg_blueprint', _cwg_bp)
_ipmi_mod = _load('ipmi_blueprint', _ipmi_bp)

cwg_bp  = _cwg_mod.cwg_bp
ipmi_bp = _ipmi_mod.ipmi_bp

from bmc_template import (
    profile_bp, init_db_at, register_jinja_templates,
    set_shutdown_callback as set_service_shutdown_callback,
    set_serial_session_tester,
)

init_db_at(_ROOT / 'profiles.db')
_cwg_mod.set_db(_ROOT / 'profiles.db')
_cwg_mod.set_url_prefix('/cwg')
_ipmi_mod.set_url_prefix('/ipmi')
_ipmi_mod.init_ipmi(str(_ROOT / 'profiles.db'))
if getattr(_cwg_mod, 'HAS_SERIAL', False):
    def _probe_serial(host, baud, user, password):
        sess = _cwg_mod.SerialSession(host, baud, user, password)
        sess.close()
    set_serial_session_tester(_probe_serial)

# ── Hub Blueprint ─────────────────────────────────────────────────────────────
from hub import hub_bp, set_db as hub_set_db

hub_set_db(_ROOT / 'profiles.db')

# ── Flask App ─────────────────────────────────────────────────────────────────
from flask import Flask
from flask_sock import Sock

app = Flask(__name__, static_folder=None)
app.secret_key = os.environ.get('SECRET_KEY', 'bmc-toolentry-dev-key-change-in-prod')

app.register_blueprint(hub_bp)
app.register_blueprint(cwg_bp, url_prefix='/cwg')
app.register_blueprint(ipmi_bp, url_prefix='/ipmi')
app.register_blueprint(profile_bp, url_prefix='/api')
register_jinja_templates(app)

# ── D-Bus WebSocket（必須在主 app，不能在 Blueprint）────────────────────────
import dbus_engine

sock = Sock(app)
dbus_engine.register_dbus_routes(app, sock,
                                 _cwg_mod._get_pooled_client,
                                 _cwg_mod._evict_from_pool)


# ── Shell Bar Context Processor ───────────────────────────────────────────────
@app.context_processor
def _inject_shell_bar():
    from flask import request, session
    bmc = session.get('bmc')
    if not bmc:
        return {}
    from bmc_template.conn_format import tool_display_name, format_conn_host, conn_type_badge
    tool_key = request.blueprint
    if tool_key not in ('cwg', 'ipmi'):
        return {}
    return {'shell_bar_ctx': {
        'tool_name':  tool_display_name(tool_key),
        'conn_host':  format_conn_host(bmc),
        'conn_badge': conn_type_badge(bmc),
        'ssh_ok':     bmc.get('ssh_ok', True),
    }}


# ── System Tray Icon ──────────────────────────────────────────────────────────

def _write_lock(port: int):
    _LOCK_FILE.write_text(str(port))


def _read_lock() -> int | None:
    try:
        return int(_LOCK_FILE.read_text().strip())
    except Exception:
        return None


def _release_lock():
    try:
        _LOCK_FILE.unlink(missing_ok=True)
    except Exception:
        pass


def _check_single_instance() -> bool:
    import socket
    port = _read_lock()
    if port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(('localhost', port)) == 0:
                webbrowser.open_new(f'http://localhost:{port}')
                return False
    return True


def _make_tray_image():
    """Hub 輻射圖示：中心節點 + 三根輻射 + 外圍節點，代表統一入口。"""
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(11, 25, 40))
    cx, cy = size // 2, size // 2
    draw.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(79, 195, 247))
    for deg in [90, 210, 330]:
        rad = math.radians(deg)
        ox = int(cx + 18 * math.cos(rad))
        oy = int(cy - 18 * math.sin(rad))
        draw.line([(cx, cy), (ox, oy)], fill=(79, 195, 247), width=3)
        draw.ellipse([ox - 5, oy - 5, ox + 5, oy + 5], fill=(79, 195, 247))
    return img


def _service_shutdown():
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass
    _release_lock()
    os._exit(0)


_cwg_mod.set_shutdown_callback(_service_shutdown)
set_service_shutdown_callback(_service_shutdown)


def _run_tray(port: int):
    global _tray_icon
    if not HAS_TRAY:
        return

    def on_open(icon, item):
        webbrowser.open_new(f'http://localhost:{port}')

    def on_exit(icon, item):
        _service_shutdown()

    img = _make_tray_image()
    menu = pystray.Menu(
        pystray.MenuItem('開啟 BMC ToolEntry', on_open, default=True),
        pystray.MenuItem('結束', on_exit),
    )
    _tray_icon = pystray.Icon(
        'BMCToolEntry', img,
        f'BMC ToolEntry  http://localhost:{port}', menu,
    )
    _tray_icon.run()


# ── Entry Point ───────────────────────────────────────────────────────────────
if __name__ == '__main__':
    if not _check_single_instance():
        sys.exit(0)

    from port_manager import get_free_port

    port = int(os.environ.get('PORT') or get_free_port(preferred=7000))
    _write_lock(port)

    import atexit
    atexit.register(_release_lock)

    def _shutdown_handler(sig, frame):
        _service_shutdown()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    print(f'[ToolEntry] http://localhost:{port}')
    print(f'  Hub            → http://localhost:{port}/')
    print(f'  CommandWebGUI  → http://localhost:{port}/cwg/')
    print(f'  IPMI Inspector → http://localhost:{port}/ipmi/')

    if HAS_TRAY:
        flask_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=port, debug=False),
            daemon=True,
        )
        flask_thread.start()
        Timer(1.5, webbrowser.open_new, args=[f'http://localhost:{port}']).start()
        _run_tray(port)
    else:
        Timer(1.5, webbrowser.open_new, args=[f'http://localhost:{port}']).start()
        app.run(host='0.0.0.0', port=port, debug=False)
        _release_lock()
