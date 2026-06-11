"""Unified connection label formatting for headers, cards, and dashboards."""

from __future__ import annotations

TOOL_DISPLAY = {
    'cwg': 'Command<strong>WebGUI</strong>',
    'ipmi': 'IPMI <strong>Inspector</strong>',
    'hub': 'BMC <strong>ToolEntry</strong>',
}


def tool_display_name(tool_key: str) -> str:
    return TOOL_DISPLAY.get(tool_key, tool_key)


def conn_type_badge(data: dict | None) -> str:
    if not data:
        return ''
    if data.get('ipmi_only'):
        return 'IPMI'
    conn_type = data.get('conn_type') or data.get('type') or 'ssh'
    return 'COM' if conn_type == 'serial' else 'SSH'


def format_conn_host(data: dict | None) -> str:
    """host:port · user (SSH/IPMI) or host · baud · user (COM)."""
    if not data:
        return '未連線'

    user = (data.get('user') or data.get('username') or '').strip()
    conn_type = data.get('conn_type') or data.get('type') or 'ssh'

    if conn_type == 'serial':
        host = (data.get('host') or '').strip()
        baud = data.get('ssh_port') or data.get('port') or 115200
        line = f'{host} · {baud}' if host else str(baud)
    elif data.get('ipmi_only'):
        host = (data.get('host') or '').strip()
        port = data.get('port') or data.get('ipmi_port') or 623
        line = f'{host}:{port}' if host else f':{port}'
    else:
        host = (data.get('host') or '').strip()
        port = data.get('ssh_port') or data.get('port') or 22
        if host and ':' in host:
            line = host
        elif host:
            line = f'{host}:{port}'
        else:
            line = f':{port}'

    if user:
        line += f' · {user}'
    return line
