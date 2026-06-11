import atexit
import os
import signal
import sys
import threading
import webbrowser
from pathlib import Path
from threading import Timer

from flask import Flask
from flask_sock import Sock

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_TRAY = True
except ImportError:
    HAS_TRAY = False

# ── Paths ─────────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    base_path = Path(sys.executable).parent
    _src_path = Path(sys._MEIPASS)
    template_folder = str(_src_path / 'templates')
    static_folder = str(_src_path / 'static')
else:
    _src_path = Path(__file__).resolve().parent
    base_path = _src_path.parent
    template_folder = str(_src_path / 'templates')
    static_folder = str(_src_path / 'static')

_MODULE = base_path.parent.parent.parent / 'Module'  # repo root Module/
for p in (_src_path, _MODULE):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

LOCK_FILE = base_path / 'commandwebgui.lock'
_tray_icon = None

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder=template_folder, static_folder=static_folder)

from port_manager import get_free_port, write_lock, read_lock, release_lock
from blueprint import (
    cwg_bp, set_db, set_url_prefix,
    set_shutdown_callback as set_cwg_shutdown_callback,
    _get_pooled_client, _evict_from_pool, SerialSession, HAS_SERIAL,
)
from bmc_template import (
    profile_bp, init_db_at, get_default_db_path,
    register_jinja_templates, set_shutdown_callback as set_service_shutdown_callback,
    set_serial_session_tester,
)

init_db_at(get_default_db_path())
if HAS_SERIAL:
    def _probe_serial(host, baud, user, password):
        sess = SerialSession(host, baud, user, password)
        sess.close()
    set_serial_session_tester(_probe_serial)
set_db(get_default_db_path())
set_url_prefix('')
app.register_blueprint(cwg_bp)
app.register_blueprint(profile_bp, url_prefix='/api')
register_jinja_templates(app)

from dbus_engine import register_dbus_routes

sock = Sock(app)
register_dbus_routes(app, sock, _get_pooled_client, _evict_from_pool)


# ── Helpers ──────────────────────────────────────────────────────────────────

def open_browser(port):
    webbrowser.open_new(f'http://localhost:{port}')


def _check_single_instance() -> bool:
    import socket
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
    draw.line([(16, 16), (16, 48)], fill=(79, 195, 247), width=5)
    draw.line([(16, 16), (26, 16)], fill=(79, 195, 247), width=5)
    draw.line([(16, 48), (26, 48)], fill=(79, 195, 247), width=5)
    draw.polygon([(34, 20), (34, 44), (52, 32)], fill=(79, 195, 247))
    return img


def _service_shutdown():
    global _tray_icon
    if _tray_icon:
        try:
            _tray_icon.stop()
        except Exception:
            pass
    release_lock(LOCK_FILE)
    os._exit(0)


set_cwg_shutdown_callback(_service_shutdown)
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
        pystray.MenuItem('開啟 CommandWebGUI', on_open, default=True),
        pystray.MenuItem('結束', on_exit),
    )
    _tray_icon = pystray.Icon('CommandWebGUI', img, f'CommandWebGUI  http://localhost:{port}', menu)
    _tray_icon.run()


# ── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not _check_single_instance():
        sys.exit(0)

    available_port = int(os.environ.get('PORT') or get_free_port())
    write_lock(available_port, LOCK_FILE)
    atexit.register(release_lock, LOCK_FILE)

    def _shutdown_handler(sig, frame):
        _service_shutdown()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    print(f'[CommandWebGUI] http://localhost:{available_port}')

    if HAS_TRAY:
        flask_thread = threading.Thread(
            target=lambda: app.run(host='0.0.0.0', port=available_port, debug=False),
            daemon=True,
        )
        flask_thread.start()
        Timer(1.5, open_browser, args=[available_port]).start()
        _run_tray(available_port)
    else:
        Timer(1.5, open_browser, args=[available_port]).start()
        app.run(host='0.0.0.0', port=available_port, debug=False)
        release_lock(LOCK_FILE)
