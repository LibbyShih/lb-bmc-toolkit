"""Shared SSH / serial / IPMI preflight tests — one code path for UI and server."""

from __future__ import annotations

import time

_serial_session_tester = None


def set_serial_session_tester(fn):
    """Register serial login probe: fn(host, baud, user, password) or raises."""
    global _serial_session_tester
    _serial_session_tester = fn


def _ms_since(start: float) -> int:
    return int((time.time() - start) * 1000)


def _error_result(e: Exception, ms: int, fallback: str = '連線失敗') -> dict:
    msg = str(e).strip()
    if not msg or msg == 'None':
        msg = fallback
    return {'ok': False, 'error': msg, 'exception': type(e).__name__, 'duration_ms': ms}


def test_ssh(host: str, port, user: str, password: str = '', timeout: int = 8) -> dict:
    start = time.time()
    ms = lambda: _ms_since(start)

    if not (host or '').strip():
        return {'ok': False, 'error': 'Host 不能空白', 'duration_ms': ms()}
    if not (user or '').strip():
        return {'ok': False, 'error': 'Username 不能空白', 'duration_ms': ms()}
    try:
        port = int(port)
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Port 必須是數字', 'duration_ms': ms()}

    import paramiko
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host.strip(), port=port, username=user.strip(),
            password=password or '', timeout=timeout,
        )
        client.close()
        return {'ok': True, 'duration_ms': ms()}
    except Exception as e:
        return _error_result(e, ms(), 'SSH 連線失敗')


def test_serial_open(port_name: str, baud, timeout: float = 2.0) -> dict:
    """Open COM port only (no login). Fallback when SerialSession is unavailable."""
    start = time.time()
    ms = lambda: _ms_since(start)

    if not (port_name or '').strip():
        return {'ok': False, 'error': 'COM port name required', 'duration_ms': ms()}
    try:
        baud = int(baud)
    except (ValueError, TypeError):
        baud = 115200

    try:
        import serial
    except ImportError:
        return {'ok': False, 'error': 'pyserial not installed', 'duration_ms': ms()}

    try:
        if '://' in port_name:
            ser = serial.serial_for_url(port_name.strip(), timeout=timeout)
        else:
            ser = serial.Serial(
                port_name.strip(), baud, timeout=timeout,
                bytesize=8, parity='N', stopbits=1,
            )
        if not ser.is_open:
            raise OSError('Cannot open port')
        ser.close()
        return {'ok': True, 'duration_ms': ms()}
    except Exception as e:
        return _error_result(e, ms(), 'COM 連線失敗')


def probe_serial_login(host: str, baud, user: str = '', password: str = '') -> dict:
    """Serial login probe — same check as CWG /api/serial/test and hub COM connect."""
    start = time.time()
    ms = lambda: _ms_since(start)

    if not (host or '').strip():
        return {'ok': False, 'error': 'COM port name required', 'duration_ms': ms()}
    try:
        baud = int(baud)
    except (ValueError, TypeError):
        return {'ok': False, 'error': 'Baud rate 必須是數字', 'duration_ms': ms()}

    if _serial_session_tester:
        try:
            _serial_session_tester(host.strip(), baud, user or '', password or '')
            return {'ok': True, 'duration_ms': ms()}
        except Exception as e:
            return _error_result(e, ms(), 'COM 連線失敗')

    return test_serial_open(host, baud)


def preflight_connection_test(data: dict) -> dict:
    """Unified preflight for SSH / serial (Hub, CWG). IPMI connects via POST /connect."""
    conn_type = data.get('conn_type', 'ssh')
    host = (data.get('host') or '').strip()
    user = (data.get('user') or data.get('username') or '').strip()
    password = data.get('password', '')
    port = data.get('port') or data.get('ssh_port') or (115200 if conn_type == 'serial' else 22)

    if conn_type == 'serial':
        return probe_serial_login(host, port, user, password)

    return test_ssh(host, port, user, password)


def format_fail_message(prefix: str, result: dict) -> str:
    msg = result.get('error') or '連線失敗'
    exc = result.get('exception')
    if exc and exc != 'Error' and exc not in msg:
        return f'{prefix}{msg} — Exception: {exc}'
    return f'{prefix}{msg}'
