"""
Hub Blueprint — 統一登入入口
- 登入：測試 SSH 連線，成功後存入 session
- Dashboard：工具選擇頁
- 共用 profiles.db（與 CWG 相同格式，新增 ipmi_port 欄位）
"""
from pathlib import Path

from flask import (Blueprint, jsonify, redirect, render_template,
                   request, send_from_directory, session, url_for)

hub_bp = Blueprint(
    'hub', __name__,
    template_folder='templates',
    static_folder='static',
    static_url_path='/hub-static',
)

_DB_PATH: Path = Path('profiles.db')


def set_db(path: Path):
    global _DB_PATH
    _DB_PATH = Path(path)
    # 不再由 Hub 負責建立 profiles 表，而是依賴 CWG 的 init_db_at


# ── Routes ───────────────────────────────────────────────────────────────────

@hub_bp.route('/favicon.ico')
def favicon():
    return send_from_directory(hub_bp.static_folder, 'favicon.ico',
                               mimetype='image/vnd.microsoft.icon')


@hub_bp.route('/')
def index():
    if session.get('bmc'):
        return redirect(url_for('hub.dashboard'))
    return render_template('login.html')


@hub_bp.route('/connect', methods=['POST'])
def connect():
    host      = request.form.get('host', '').strip()
    user      = request.form.get('user', '').strip()
    password  = request.form.get('password', '')
    conn_type = request.form.get('conn_type', 'ssh')

    try:
        ssh_port  = int(request.form.get('ssh_port', 22))
        ipmi_port = int(request.form.get('ipmi_port', 623))
    except (ValueError, TypeError):
        return _login_error('Port 必須是數字', host, user, conn_type)

    if not host or not user:
        return _login_error('Host 和 Username 不能空白', host, user, conn_type)

    from bmc_template.connection_test import preflight_connection_test, format_fail_message

    result = preflight_connection_test({
        'conn_type': conn_type,
        'host': host,
        'port': ssh_port,
        'user': user,
        'password': password,
    })
    if not result['ok']:
        prefix = 'COM 連線失敗：' if conn_type == 'serial' else 'SSH 連線失敗：'
        return _login_error(
            format_fail_message(prefix, result),
            host, user, conn_type, ssh_port, ipmi_port,
        )
    ssh_ok, ssh_err = True, None

    session.permanent = False
    session['bmc'] = {
        'host': host, 'user': user, 'password': password,
        'conn_type': conn_type,
        'ssh_port': ssh_port, 'ipmi_port': ipmi_port,
        'ssh_ok': ssh_ok, 'ssh_err': ssh_err,
    }

    return redirect(url_for('hub.dashboard'))


@hub_bp.route('/dashboard')
def dashboard():
    if not session.get('bmc'):
        return redirect(url_for('hub.index'))
    return render_template('dashboard.html', bmc=session['bmc'])


@hub_bp.route('/disconnect')
def disconnect():
    session.pop('bmc', None)
    return redirect(url_for('hub.index'))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _login_error(msg, host='', user='', conn_type='ssh',
                 ssh_port=22, ipmi_port=623):
    return render_template('login.html',
                           error=msg, form_host=host, form_user=user,
                           form_conn_type=conn_type,
                           form_ssh_port=ssh_port, form_ipmi_port=ipmi_port)


