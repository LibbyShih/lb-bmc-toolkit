#!/usr/bin/env python3
"""
IPMI Inspector — Web launcher
get_free_port + lock file + pystray + auto-open browser
"""
import atexit
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
    _ROOT   = Path(sys.executable).parent   # next to .exe
    _SRC    = Path(sys._MEIPASS)
    _MODULE = None
else:
    _SRC    = Path(__file__).resolve().parent
    _ROOT   = _SRC.parent
    _MODULE = _ROOT.parent.parent.parent / 'Module'

_LOCK_FILE = _ROOT / 'ipmi_inspector.lock'
LOCK_FILE = _LOCK_FILE
_tray_icon = None

for p in filter(None, (_SRC, _ROOT, _MODULE)):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from port_manager import get_free_port, write_lock, read_lock, release_lock
from web.app import app, init_app
from bmc_template import set_shutdown_callback as set_service_shutdown_callback


# ── Single Instance ───────────────────────────────────────────────────────────

def _check_single_instance() -> bool:
    import socket
    port = read_lock(LOCK_FILE)
    if port:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            if s.connect_ex(('localhost', port)) == 0:
                webbrowser.open_new(f'http://localhost:{port}')
                return False
    return True


# ── Tray Icon ─────────────────────────────────────────────────────────────────

def _make_tray_image():
    size = 64
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([2, 2, size - 2, size - 2], fill=(11, 25, 40))
    cx, cy = size // 2, size // 2
    draw.rectangle([cx - 12, cy - 18, cx + 12, cy - 12], fill=(79, 195, 247))
    draw.rectangle([cx - 4, cy - 12, cx + 4, cy + 12], fill=(79, 195, 247))
    draw.rectangle([cx - 12, cy + 12, cx + 12, cy + 18], fill=(79, 195, 247))
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
        pystray.MenuItem('開啟 IPMI Inspector', on_open, default=True),
        pystray.MenuItem('結束', on_exit),
    )
    _tray_icon = pystray.Icon(
        'IPMIInspector', img,
        f'IPMI Inspector  http://localhost:{port}', menu,
    )
    _tray_icon.run()


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if not _check_single_instance():
        sys.exit(0)

    port = int(os.environ.get('PORT') or get_free_port())
    db_path = str(_ROOT / 'profiles.db')

    write_lock(port, LOCK_FILE)
    init_app(db_path=db_path)
    atexit.register(release_lock, LOCK_FILE)

    set_service_shutdown_callback(_service_shutdown)

    def _shutdown_handler(sig, frame):
        _service_shutdown()

    signal.signal(signal.SIGINT, _shutdown_handler)
    signal.signal(signal.SIGTERM, _shutdown_handler)

    print(f'[IPMI Inspector] http://localhost:{port}')

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
        release_lock(LOCK_FILE)
