"""IPMI Inspector — standalone Flask app (registers blueprint)."""
import os
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent
_ROOT = _SRC.parent
_MODULE = _ROOT.parent.parent.parent / 'Module'  # repo root Module/

for p in (_SRC, _ROOT, _MODULE):
    p_str = str(p)
    if p_str not in sys.path:
        sys.path.insert(0, p_str)

from flask import Flask
from blueprint import ipmi_bp, init_ipmi, set_url_prefix
from bmc_template import (
    profile_bp, init_db_at, register_jinja_templates,
    get_default_db_path,
)

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'ipmi-inspector-dev-key')
_initialized = False


def init_app(db_path: str = 'profiles.db'):
    """Wire blueprints once before serving (called from src/main.py)."""
    global _initialized
    if _initialized:
        return
    set_url_prefix('')
    init_ipmi(db_path)
    init_db_at(get_default_db_path())
    app.register_blueprint(ipmi_bp)
    app.register_blueprint(profile_bp, url_prefix='/api')
    register_jinja_templates(app)
    _initialized = True
