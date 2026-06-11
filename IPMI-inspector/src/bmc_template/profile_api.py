"""
Shared Profile API — Flask Blueprint
"""
import json
import os
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from flask import Blueprint, request, jsonify, Response

_shutdown_callback = None


def set_shutdown_callback(callback):
    """Register app-level shutdown (tray stop, lock release, os._exit)."""
    global _shutdown_callback
    _shutdown_callback = callback


profile_bp = Blueprint(
    'bmc_template', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/bmc_template/static'
)

_DB_PATH: Path = Path('profiles.db')


def init_db_at(path: Path):
    global _DB_PATH
    _DB_PATH = Path(path)
    _run_init_db()


def _run_init_db():
    with sqlite3.connect(_DB_PATH) as con:
        con.execute('''CREATE TABLE IF NOT EXISTS profiles (
            name      TEXT PRIMARY KEY,
            host      TEXT NOT NULL,
            ssh_port  INTEGER NOT NULL DEFAULT 22,
            user      TEXT NOT NULL,
            password  TEXT NOT NULL,
            saved_at  TEXT NOT NULL,
            results   TEXT,
            conn_type TEXT DEFAULT 'ssh',
            ipmi_port INTEGER DEFAULT 623
        )''')
        cols = [r[1] for r in con.execute("PRAGMA table_info(profiles)").fetchall()]
        # Migration: rename legacy 'port' column to 'ssh_port'
        if 'port' in cols and 'ssh_port' not in cols:
            con.execute('ALTER TABLE profiles RENAME COLUMN port TO ssh_port')
            cols = [r[1] for r in con.execute("PRAGMA table_info(profiles)").fetchall()]
        if 'results' not in cols:
            con.execute('ALTER TABLE profiles ADD COLUMN results TEXT')
        if 'conn_type' not in cols:
            con.execute("ALTER TABLE profiles ADD COLUMN conn_type TEXT DEFAULT 'ssh'")
        if 'ipmi_port' not in cols:
            con.execute("ALTER TABLE profiles ADD COLUMN ipmi_port INTEGER DEFAULT 623")
        if 'ssh_port' not in cols:
            con.execute("ALTER TABLE profiles ADD COLUMN ssh_port INTEGER DEFAULT 22")


def _row_to_dict(row):
    d = dict(row)
    if 'results' in d and d['results']:
        try:
            d['results'] = json.loads(d['results'])
        except Exception:
            pass
    return d


def _get_ssh_port(data: dict) -> int:
    """Accept ssh_port or legacy port field."""
    v = data.get('ssh_port') or data.get('port')
    try:
        return int(v)
    except (TypeError, ValueError):
        return 22


@profile_bp.route('/profiles/meta', methods=['GET'])
def profiles_meta():
    return jsonify({
        'db_path': str(_DB_PATH.resolve()),
        'db_name': _DB_PATH.name,
    })


@profile_bp.route('/profiles', methods=['GET'])
def list_profiles():
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute('SELECT * FROM profiles ORDER BY saved_at DESC').fetchall()
    return jsonify({'profiles': [_row_to_dict(r) for r in rows]})


@profile_bp.route('/profiles/save', methods=['POST'])
def save_profile():
    data = request.json or {}
    name      = data.get('name', '').strip()
    host      = data.get('host', '').strip()
    ssh_port  = _get_ssh_port(data)
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')
    try:
        ipmi_port = int(data.get('ipmi_port', 623))
    except (ValueError, TypeError):
        ipmi_port = 623

    if not name or not host or not user:
        return jsonify({'error': 'name, host, and user are required'}), 400

    results = data.get('results')
    if results is not None:
        results = json.dumps(results, ensure_ascii=False)
    saved_at = time.strftime('%Y-%m-%d %H:%M:%S')
    with sqlite3.connect(_DB_PATH) as con:
        con.execute(
            'INSERT OR REPLACE INTO profiles '
            '(name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port)
        )
    return jsonify({'ok': True, 'name': name, 'path': str(_DB_PATH.resolve())})


@profile_bp.route('/profiles/<name>', methods=['GET'])
def load_profile(name):
    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
    if row is None:
        return jsonify({'error': 'profile not found'}), 404
    return jsonify(_row_to_dict(row))


@profile_bp.route('/profiles/<name>', methods=['PUT'])
def update_profile(name):
    data = request.json or {}
    new_name  = data.get('name', '').strip()
    host      = data.get('host', '').strip()
    ssh_port  = _get_ssh_port(data)
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')
    try:
        ipmi_port = int(data.get('ipmi_port', 623))
    except (ValueError, TypeError):
        ipmi_port = 623

    if not new_name or not host or not user:
        return jsonify({'error': 'name, host, and user are required'}), 400

    with sqlite3.connect(_DB_PATH) as con:
        con.row_factory = sqlite3.Row
        row = con.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
        if row is None:
            return jsonify({'error': 'profile not found'}), 404
        existing = dict(row)
        if name != new_name:
            con.execute('DELETE FROM profiles WHERE name=?', (name,))
        con.execute(
            'INSERT OR REPLACE INTO profiles '
            '(name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (new_name, host, ssh_port, user, password,
             existing.get('saved_at', ''), existing.get('results'), conn_type, ipmi_port)
        )
    return jsonify({'ok': True, 'name': new_name})


@profile_bp.route('/profiles/<name>', methods=['DELETE'])
def delete_profile(name):
    with sqlite3.connect(_DB_PATH) as con:
        cur = con.execute('DELETE FROM profiles WHERE name=?', (name,))
    if cur.rowcount == 0:
        return jsonify({'error': 'profile not found'}), 404
    return jsonify({'ok': True})


@profile_bp.route('/profiles/export/<name>', methods=['GET'])
def export_profile(name):
    with sqlite3.connect(_DB_PATH) as src:
        src.row_factory = sqlite3.Row
        row = src.execute('SELECT * FROM profiles WHERE name=?', (name,)).fetchone()
    if row is None:
        return jsonify({'error': 'profile not found'}), 404
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        with sqlite3.connect(tmp.name) as dst:
            dst.execute('''CREATE TABLE profiles (
                name TEXT PRIMARY KEY, host TEXT NOT NULL,
                ssh_port INTEGER NOT NULL DEFAULT 22,
                user TEXT NOT NULL, password TEXT NOT NULL, saved_at TEXT NOT NULL,
                results TEXT, conn_type TEXT DEFAULT 'ssh', ipmi_port INTEGER DEFAULT 623
            )''')
            d = dict(row)
            dst.execute(
                'INSERT INTO profiles '
                '(name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (d['name'], d['host'],
                 d.get('ssh_port', d.get('port', 22)),
                 d['user'], d.get('password', ''), d.get('saved_at', ''),
                 d.get('results'), d.get('conn_type', 'ssh'), d.get('ipmi_port', 623))
            )
        with open(tmp.name, 'rb') as f:
            data = f.read()
        safe = re.sub(r'[^\w\-]', '_', name) or 'profile'
        return Response(data, mimetype='application/x-sqlite3',
                        headers={'Content-Disposition': f'attachment; filename="{safe}.db"'})
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@profile_bp.route('/profiles/generate', methods=['POST'])
def generate_profile_db():
    data = request.json or {}
    name      = data.get('name', 'bmc').strip() or 'bmc'
    host      = data.get('host', '').strip()
    user      = data.get('user', '').strip()
    password  = data.get('password', '')
    conn_type = data.get('conn_type', 'ssh')
    ssh_port  = _get_ssh_port(data)
    try:
        ipmi_port = int(data.get('ipmi_port', 623))
    except (ValueError, TypeError):
        ipmi_port = 623
    tmp = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    tmp.close()
    try:
        with sqlite3.connect(tmp.name) as dst:
            dst.execute('''CREATE TABLE profiles (
                name TEXT PRIMARY KEY, host TEXT NOT NULL,
                ssh_port INTEGER NOT NULL DEFAULT 22,
                user TEXT NOT NULL, password TEXT NOT NULL, saved_at TEXT NOT NULL,
                results TEXT, conn_type TEXT DEFAULT 'ssh', ipmi_port INTEGER DEFAULT 623
            )''')
            results = data.get('results')
            if results is not None:
                results = json.dumps(results, ensure_ascii=False)
            saved_at = time.strftime('%Y-%m-%d %H:%M:%S')
            dst.execute(
                'INSERT INTO profiles '
                '(name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port) '
                'VALUES (?,?,?,?,?,?,?,?,?)',
                (name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port)
            )
        with open(tmp.name, 'rb') as f:
            file_data = f.read()
        return Response(file_data, mimetype='application/x-sqlite3')
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@profile_bp.route('/profiles/import', methods=['POST'])
def import_profiles():
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
        replace = request.args.get('replace') in ('1', 'true', 'yes')
        imported = 0
        with sqlite3.connect(_DB_PATH) as dst:
            if replace:
                dst.execute('DELETE FROM profiles')
            for r in rows:
                d = dict(r)
                sp = d.get('ssh_port') or d.get('port') or 22
                dst.execute(
                    'INSERT OR REPLACE INTO profiles '
                    '(name, host, ssh_port, user, password, saved_at, results, conn_type, ipmi_port) '
                    'VALUES (?,?,?,?,?,?,?,?,?)',
                    (d.get('name'), d.get('host'), sp, d.get('user'),
                     d.get('password', ''), d.get('saved_at', ''),
                     d.get('results'), d.get('conn_type', 'ssh'), d.get('ipmi_port', 623))
                )
                imported += 1
        return jsonify({'ok': True, 'imported': imported})
    finally:
        try: os.unlink(tmp.name)
        except OSError: pass


@profile_bp.route('/profiles/export_all', methods=['GET'])
def export_all_profiles():
    with open(_DB_PATH, 'rb') as f:
        data = f.read()
    return Response(data, mimetype='application/x-sqlite3',
                    headers={'Content-Disposition': 'attachment; filename="all_profiles.db"'})


@profile_bp.route('/connection/test', methods=['POST'])
def connection_test():
    """Pre-flight SSH or serial check (Hub / CWG). IPMI uses POST /connect directly."""
    from .connection_test import preflight_connection_test

    data = request.json or {}
    if data.get('mode') == 'ipmi' or data.get('conn_type') == 'ipmi':
        return jsonify({'ok': False, 'error': 'IPMI 不走預檢，請直接 Connect'}), 400

    return jsonify(preflight_connection_test(data))


@profile_bp.route('/service/shutdown', methods=['POST'])
def service_shutdown():
    def _exit():
        time.sleep(0.2)
        if _shutdown_callback:
            _shutdown_callback()
        else:
            os._exit(0)

    threading.Thread(target=_exit, daemon=True).start()
    return jsonify({'ok': True})
