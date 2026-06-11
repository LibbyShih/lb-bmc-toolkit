/**
 * Preflight for ToolEntry Hub and CWG connect (SSH / COM).
 * IPMI Inspector connects directly via POST /connect — no preflight.
 */

function formatConnectError(source) {
  if (!source) return '';
  if (typeof source === 'string') return source;

  const detail = source.detail;
  const apiErr = source.error;
  const apiExc = source.exception;

  if (apiErr || apiExc || detail) {
    const parts = [];
    if (apiErr) parts.push(apiErr);
    if (apiExc && apiExc !== 'Error' && !(apiErr || '').includes(apiExc)) {
      parts.push(`Exception: ${apiExc}`);
    }
    if (detail && detail !== apiErr) parts.push(detail);
    return parts.join(' — ') || '連線失敗';
  }

  const msg = source.message || String(source);
  const name = source.name;
  if (name && name !== 'Error' && !msg.includes(name)) {
    return `${name}: ${msg}`;
  }
  return msg;
}

async function testConnection(cfg, options = {}) {
  const connType = cfg.conn_type || cfg.type || 'ssh';
  const apiBase = (options.apiBase || '/api').replace(/\/$/, '');
  const timeoutMs = options.timeoutMs || 15000;
  let url;
  let body;

  if (connType === 'serial') {
    url = options.serialTestUrl || '/cwg/api/serial/test';
    body = {
      host: (cfg.host || '').trim(),
      port: cfg.port || cfg.ssh_port || 115200,
      user: (cfg.user || '').trim(),
      password: cfg.password || '',
    };
  } else {
    url = `${apiBase}/connection/test`;
    body = {
      host: (cfg.host || '').trim(),
      port: cfg.port || cfg.ssh_port || 22,
      user: (cfg.user || '').trim(),
      password: cfg.password || '',
      conn_type: 'ssh',
    };
  }

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let res;
  try {
    res = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error(`連線逾時（>${Math.round(timeoutMs / 1000)}s）`);
    }
    throw e;
  } finally {
    clearTimeout(timer);
  }

  let data = {};
  let raw = '';
  try {
    raw = await res.text();
    data = raw ? JSON.parse(raw) : {};
  } catch (_) {
    if (raw) data = { detail: raw.slice(0, 500) };
  }
  if (!res.ok || !data.ok) {
    throw new Error(formatConnectError(data) || `連線失敗 (${res.status})`);
  }
  return data;
}

function showConnectError(msgOrErr) {
  const box = document.getElementById('connectError');
  if (!box) return;
  const text = formatConnectError(msgOrErr);
  if (!text) {
    box.textContent = '';
    box.style.display = 'none';
    return;
  }
  box.textContent = text;
  box.style.display = '';
  box.title = text;
}

function spSetProfileName(name) {
  const el = document.getElementById('cpProfileName');
  if (el) el.value = name || '';
}

window.testConnection = testConnection;
window.formatConnectError = formatConnectError;
window.showConnectError = showConnectError;
window.spSetProfileName = spSetProfileName;
