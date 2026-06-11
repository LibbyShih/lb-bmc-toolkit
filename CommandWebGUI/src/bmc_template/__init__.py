import os
import sys
from pathlib import Path
from .profile_api import (
    profile_bp, init_db_at, set_shutdown_callback,
)
from .connection_test import set_serial_session_tester, preflight_connection_test


def get_default_db_path() -> Path:
    """All tools point to ToolEntry's DB so profiles are shared across tools."""
    env = os.environ.get('PROFILE_DB')
    if env:
        return Path(env)
    if getattr(sys, 'frozen', False):
        # Frozen EXE: DB next to the executable
        return Path(sys.executable).parent / 'profiles.db'
    repo = Path(__file__).resolve().parents[3]  # <repo>/<tool>/src/bmc_template/
    return repo / 'ToolEntry' / 'profiles.db'


def register_jinja_templates(app):
    """Expose bmc_template templates to all blueprints (cross-include support)."""
    from .conn_format import format_conn_host, conn_type_badge, tool_display_name

    tpl_dir = str(Path(__file__).parent / 'templates')
    searchpath = list(app.jinja_loader.searchpath)
    if tpl_dir not in searchpath:
        app.jinja_loader.searchpath.insert(0, tpl_dir)

    app.jinja_env.filters['format_conn_host'] = format_conn_host
    app.jinja_env.filters['conn_type_badge'] = conn_type_badge
    app.jinja_env.globals['tool_display_name'] = tool_display_name


__all__ = [
    'profile_bp', 'init_db_at', 'get_default_db_path',
    'register_jinja_templates', 'set_shutdown_callback',
    'set_serial_session_tester',
    'preflight_connection_test',
]
