/**
 * Client-side mirror of bmc_template.conn_format (headers + profile cards + CWG).
 */
function formatConnHost(data) {
  if (!data) return '未連線';
  const user = (data.user || data.username || '').trim();
  const connType = data.conn_type || data.type || 'ssh';

  let line;
  if (connType === 'serial') {
    const host = (data.host || '').trim();
    const baud = data.ssh_port || data.port || 115200;
    line = host ? `${host} · ${baud}` : String(baud);
  } else if (data.ipmi_only) {
    const host = (data.host || '').trim();
    const port = data.ipmi_port || data.port || 623;
    line = host ? `${host}:${port}` : `:${port}`;
  } else {
    const host = (data.host || '').trim();
    const port = data.ssh_port || data.port || 22;
    if (host && host.includes(':')) line = host;
    else if (host) line = `${host}:${port}`;
    else line = `:${port}`;
  }

  if (user) line += ` · ${user}`;
  return line;
}

function connTypeBadge(data) {
  if (!data) return '';
  if (data.ipmi_only) return 'IPMI';
  return (data.conn_type || data.type) === 'serial' ? 'COM' : 'SSH';
}

window.formatConnHost = formatConnHost;
window.connTypeBadge = connTypeBadge;
