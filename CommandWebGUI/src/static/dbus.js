// BASE is already declared in app.js

// State
let services = [];
let expanded = new Set();
let selectedService = null;
let selectedPath = null;
let ws = null;
let propCells = {};          // { iface: { propName: <td> } }
const pathCache = new Map(); // service → paths[]
let allSigs = [];            // all received signals, capped at 200
const sigPaths = new Set();  // paths seen in signals (dropdown dedup)

// DOM refs
const searchInput   = document.getElementById('dbusSearch');
const treeEl        = document.getElementById('tree');
const detailContent = document.getElementById('detail-content');
const sigFilterEl   = document.getElementById('sig-filter');
const sigClear      = document.getElementById('sig-clear');
const sigList       = document.getElementById('sig-list');
const dividerEl     = document.getElementById('divider');
const sidebarEl     = document.getElementById('sidebar');
const appEl         = document.getElementById('app');

function getAuthParams() {
  const host = document.getElementById('cfgHost') ? document.getElementById('cfgHost').value : '';
  const port = document.getElementById('cfgPort') ? document.getElementById('cfgPort').value : '22';
  const user = document.getElementById('cfgUser') ? document.getElementById('cfgUser').value : '';
  const pass = document.getElementById('cfgPass') ? document.getElementById('cfgPass').value : '';
  return `host=${encodeURIComponent(host)}&port=${encodeURIComponent(port)}&user=${encodeURIComponent(user)}&password=${encodeURIComponent(pass)}`;
}

const sigPayloadEl  = document.getElementById('sig-payload');
const sigControls   = document.getElementById('sig-controls');
const jnlControls   = document.getElementById('jnl-controls');
const jnlClear      = document.getElementById('jnl-clear');
const tabSig        = document.getElementById('tab-sig');
const tabJnl        = document.getElementById('tab-jnl');
const jnlList       = document.getElementById('jnl-list');
const btnSnapshot   = document.getElementById('btn-snapshot');
const btnDiff       = document.getElementById('btn-diff');
const diffModal     = document.getElementById('diff-modal');
const dClose        = document.getElementById('d-close');
const diffFile      = document.getElementById('diff-file');
const diffResult    = document.getElementById('diff-result');

let wsJnl = null;

// Standard D-Bus management interfaces — collapsed by default
const STANDARD_IFACES = new Set([
  'org.freedesktop.DBus.Introspectable',
  'org.freedesktop.DBus.Peer',
  'org.freedesktop.DBus.Properties',
  'org.freedesktop.DBus.ObjectManager',
]);

// ── Init ──────────────────────────────────────────────────────────────────────
async function initDBus() {
  try {
    treeEl.innerHTML = '<div style="padding:10px;color:cyan;">Loading DBus...</div>';
    const res = await fetch(`/api/dbus/services?${getAuthParams()}`);
    const text = await res.text();
    
    let data;
    try {
      data = JSON.parse(text);
    } catch(e) {
      treeEl.innerHTML = `<div class="dbus-error">⚠ Invalid JSON from Server<br><span style="font-size:10px;">HTTP ${res.status}: ${esc(text.substring(0, 100))}</span></div>`;
      return;
    }

    if (data.error) {
      console.error("DBus Init Error:", data.error);
      treeEl.innerHTML = `<div class="dbus-error">⚠ D-Bus 初始化失敗<br><span style="font-size:10px;color:#f87171;">HTTP ${res.status} | ${esc(data.error)}</span></div>`;
      return;
    }
    services = data.map(s => s.name);
    
    if (services.length === 0) {
      treeEl.innerHTML = `<div class="dbus-error" style="margin: 8px;">⚠ 無法取得 D-Bus Services<br><span style="font-size:11px;color:#f87171;line-height:1.4;display:block;margin-top:4px;">目標設備可能不支援 busctl，或尚未安裝 D-Bus，導致清單為空。</span></div>`;
      return;
    }
    
    renderTree('');
    searchInput.addEventListener('input', () =>
      renderTree(searchInput.value.trim().toLowerCase())
    );
    initWatch();
  } catch (e) {
    console.error("DBus Init Error:", e);
    treeEl.innerHTML = `<div class="dbus-error">⚠ D-Bus 連線失敗<br><span style="font-size:10px;color:#f87171;">${esc(String(e))}</span></div>`;
  }
}

async function reconnectDBus() {
  if (ws) { ws.close(); ws = null; }
  pathCache.clear();
  allSigs = [];
  sigPaths.clear();
  sigFilterEl.innerHTML = '<option value="">All paths</option>';
  sigList.innerHTML = '';
  selectedService = null;
  selectedPath = null;
  propCells = {};
  detailContent.innerHTML = '<div id="detail-placeholder">Select a service on the left, then click an object path.</div>';

  initDBus();
}

// ── Tree ──────────────────────────────────────────────────────────────────────
function renderTree(filter) {
  treeEl.innerHTML = '';
  const list = filter ? services.filter(s => s.toLowerCase().includes(filter)) : services;
  list.forEach(name => treeEl.appendChild(renderServiceNode(name)));
}

function renderServiceNode(name) {
  const wrap = document.createElement('div');
  wrap.className = 'svc-wrap';

  const row = document.createElement('div');
  row.className = 'svc-row';

  const caret = document.createElement('span');
  caret.className = 'caret';
  caret.textContent = '▶';

  const label = document.createElement('span');
  label.className = 'svc-name';
  label.textContent = name;
  label.title = name;

  row.append(caret, label);

  const pathsEl = document.createElement('div');
  pathsEl.className = 'svc-paths';
  if (expanded.has(name)) {
    pathsEl.classList.add('open');
    caret.textContent = '▼';
    loadPaths(name, pathsEl);
  }

  wrap.append(row, pathsEl);
  row.addEventListener('click', () => toggleService(name, pathsEl, caret));
  return wrap;
}

async function toggleService(name, pathsEl, caret) {
  if (expanded.has(name)) {
    expanded.delete(name);
    pathsEl.classList.remove('open');
    caret.textContent = '▶';
  } else {
    expanded.add(name);
    pathsEl.classList.add('open');
    caret.textContent = '▼';
    await loadPaths(name, pathsEl);
  }
}

async function loadPaths(service, container) {
  if (pathCache.has(service)) {
    renderPaths(service, container, pathCache.get(service));
    return;
  }
  container.innerHTML = '<div class="tree-loading">Loading…</div>';
  try {
    const res = await fetch(`/api/dbus/tree?${getAuthParams()}&service=${encodeURIComponent(service)}`);
    const paths = await res.json();
    if (paths.error) {
      container.innerHTML = `<div class="tree-loading" style="color:#f87171;">⚠ ${esc(paths.error)}</div>`;
      return;
    }
    if (!Array.isArray(paths) || paths.length === 0) {
      container.innerHTML = '<div class="tree-loading">（無 object path）</div>';
      return;
    }
    pathCache.set(service, paths);
    renderPaths(service, container, paths);
  } catch (e) {
    container.innerHTML = `<div class="tree-loading" style="color:#f87171;">⚠ ${esc(String(e))}</div>`;
  }
}

function renderPaths(service, container, paths) {
  container.innerHTML = '';
  paths.forEach(path => {
    const row = document.createElement('div');
    row.className = 'path-row';
    if (service === selectedService && path === selectedPath) row.classList.add('selected');
    row.textContent = path;
    row.title = path;
    row.addEventListener('click', () => selectPath(service, path, row));
    container.appendChild(row);
  });
}

// ── Select Path ───────────────────────────────────────────────────────────────
async function selectPath(service, path, rowEl) {
  document.querySelectorAll('.path-row.selected').forEach(el => el.classList.remove('selected'));
  rowEl.classList.add('selected');
  selectedService = service;
  selectedPath = path;

  detailContent.innerHTML = '<div style="color:#555;padding:12px;font-size:12px">Loading…</div>';

  // Auto-filter signals to this path
  addPathToFilter(path);
  sigFilterEl.value = path;
  renderSigList();

  try {
    const [objRes, propRes] = await Promise.all([
      fetch(`/api/dbus/object?${getAuthParams()}&service=${encodeURIComponent(service)}&path=${encodeURIComponent(path)}`),
      fetch(`/api/dbus/properties?${getAuthParams()}&service=${encodeURIComponent(service)}&path=${encodeURIComponent(path)}`),
    ]);

    const data = await objRes.json();
    const propVals = await propRes.json().catch(() => ({}));

    // Check for error responses
    if (data.error) {
      detailContent.innerHTML =
        `<div id="detail-path"><span class="d-service">${esc(service)}</span> <span class="d-path">${esc(path)}</span></div>` +
        `<div class="dbus-error">⚠ introspect 失敗<br><span style="font-size:11px;color:#f87171;">${esc(data.error)}</span></div>`;
      return;
    }

    renderDetail(service, path, data, propVals);
  } catch (e) {
    detailContent.innerHTML =
      `<div id="detail-path"><span class="d-service">${esc(service)}</span> <span class="d-path">${esc(path)}</span></div>` +
      `<div class="dbus-error">⚠ 取得 D-Bus 資訊失敗<br><span style="font-size:11px;color:#f87171;">${esc(String(e))}</span></div>`;
  }
}

// ── Detail Panel ──────────────────────────────────────────────────────────────
function renderDetail(service, path, data, propVals) {
  propCells = {};
  detailContent.innerHTML = '';

  const pathEl = document.createElement('div');
  pathEl.id = 'detail-path';
  pathEl.innerHTML =
    `<span class="d-service">${esc(service)}</span> ` +
    `<span class="d-path">${esc(path)}</span>`;
  detailContent.appendChild(pathEl);

  // Filter out non-interface entries (e.g. error responses)
  const ifaces = Object.entries(data).filter(([, info]) => info && typeof info === 'object' && info.members);

  if (ifaces.length === 0) {
    const emptyEl = document.createElement('div');
    emptyEl.className = 'dbus-empty';
    emptyEl.textContent = '此路徑無可顯示的 Interface';
    detailContent.appendChild(emptyEl);
    return;
  }

  for (const [iface, info] of ifaces) {
    const ifaceVals = (propVals && !propVals.error && propVals[iface]) ? propVals[iface] : {};
    propCells[iface] = {};

    const det = document.createElement('details');
    det.open = !STANDARD_IFACES.has(iface);

    const summary = document.createElement('summary');
    summary.textContent = iface;
    det.appendChild(summary);

    const members = Object.entries(info.members || {});
    if (members.length === 0) {
      const emptyRow = document.createElement('div');
      emptyRow.style.cssText = 'padding:4px 8px;font-size:11px;color:#6a8fab;';
      emptyRow.textContent = '(no members)';
      det.appendChild(emptyRow);
    } else {
      const table = document.createElement('table');
      for (const [name, m] of members) {
        const tr = document.createElement('tr');

        const valTd = document.createElement('td');
        valTd.className = 'm-val';
        if (m.type === 'property') {
          const rv = renderValue(ifaceVals[name]);
          if (typeof rv === 'string') valTd.textContent = rv;
          else valTd.appendChild(rv);
        }

        tr.innerHTML =
          `<td class="m-name">.${esc(name)}</td>` +
          `<td class="m-type">${esc(m.type)}</td>` +
          `<td class="m-sig">${esc(m.signature)}</td>`;
        tr.appendChild(valTd);
        table.appendChild(tr);

        if (m.type === 'property') propCells[iface][name] = valTd;
      }
      det.appendChild(table);
    }

    detailContent.appendChild(det);
  }
}

// ── Signal Filter Dropdown ────────────────────────────────────────────────────
function addPathToFilter(path) {
  if (!path || sigPaths.has(path)) return;
  sigPaths.add(path);
  const opt = document.createElement('option');
  opt.value = path;
  opt.textContent = path;
  // Insert alphabetically after "All paths" (index 0)
  let inserted = false;
  for (let i = 1; i < sigFilterEl.options.length; i++) {
    if (sigFilterEl.options[i].value > path) {
      sigFilterEl.insertBefore(opt, sigFilterEl.options[i]);
      inserted = true;
      break;
    }
  }
  if (!inserted) sigFilterEl.appendChild(opt);
}

// ── WebSocket Signal Stream ───────────────────────────────────────────────────
function initWatch() {
  if (ws) { ws.close(); ws = null; }
  ws = new WebSocket(`ws://${location.host}/ws/dbus/watch?${getAuthParams()}`); // no filter = all signals

  ws.onmessage = e => {
    const { event: ev } = JSON.parse(e.data);
    if (!ev) return;

    // In-place property update (only for currently displayed path)
    if (ev.member === 'PropertiesChanged' && ev.iface_changed && ev.prop_changed) {
      if (ev.path === selectedPath) {
        const cell = propCells[ev.iface_changed]?.[ev.prop_changed];
        if (cell) {
          const rv = renderValue(ev.val_changed);
          cell.innerHTML = '';
          if (typeof rv === 'string') cell.textContent = rv;
          else cell.appendChild(rv);
          cell.classList.remove('live-update');
          void cell.offsetWidth;
          cell.classList.add('live-update');
          cell.addEventListener('animationend', () => cell.classList.remove('live-update'), { once: true });
        }
      }
    }

    addSigEntry(ev);
  };

  ws.onclose = () => { ws = null; };
}

// ── Signal List ───────────────────────────────────────────────────────────────
function addSigEntry(ev) {
  allSigs.unshift(ev);
  if (allSigs.length > 200) allSigs.pop();
  addPathToFilter(ev.path);

  const filter = sigFilterEl.value;
  const payloadRegex = sigPayloadEl.value.trim();
  let re = null;
  if (payloadRegex) {
    try { re = new RegExp(payloadRegex, 'i'); } catch(e){}
  }

  if (filter && ev.path !== filter) return;
  if (re && !re.test(ev.brief)) return;

  sigList.insertBefore(makeSigEntry(ev), sigList.firstChild);
  while (sigList.children.length > 200) sigList.removeChild(sigList.lastChild);
}

function renderSigList() {
  const filter = sigFilterEl.value;
  const payloadRegex = sigPayloadEl.value.trim();
  let re = null;
  if (payloadRegex) {
    try { re = new RegExp(payloadRegex, 'i'); } catch(e){}
  }
  const filtered = allSigs.filter(ev => {
    if (filter && ev.path !== filter) return false;
    if (re && !re.test(ev.brief)) return false;
    return true;
  });
  sigList.innerHTML = '';
  filtered.forEach(ev => sigList.appendChild(makeSigEntry(ev)));
}

function makeSigEntry(ev) {
  const entry = document.createElement('div');
  entry.className = 'sig-entry';

  const timeSp = document.createElement('span');
  timeSp.className = 'sig-time';
  timeSp.textContent = ev.time;

  const pathSp = document.createElement('span');
  pathSp.className = 'sig-path';
  pathSp.title = ev.path + ' — click to filter';
  pathSp.textContent = ev.path;
  pathSp.addEventListener('click', () => {
    addPathToFilter(ev.path);
    sigFilterEl.value = ev.path;
    renderSigList();
  });

  const memberSp = document.createElement('span');
  memberSp.className = 'sig-member';
  memberSp.textContent = '.' + ev.member;

  const ifaceSp = document.createElement('span');
  ifaceSp.className = 'sig-iface';
  if (ev.iface_changed) {
    const parts = ev.iface_changed.split('.');
    ifaceSp.textContent = parts.slice(-2).join('.');
    ifaceSp.title = ev.iface_changed;
  }

  const briefSp = document.createElement('span');
  briefSp.className = 'sig-brief';
  briefSp.textContent = ev.brief;

  entry.append(timeSp, pathSp, memberSp, ifaceSp, briefSp);
  return entry;
}

// ── Utility ───────────────────────────────────────────────────────────────────
function esc(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function renderValue(val) {
  if (val === null || val === undefined) return '';
  if (Array.isArray(val)) {
    if (val.length > 0 && val.every(v => typeof v === 'string' && v.startsWith('/'))) {
      const div = document.createElement('div');
      val.forEach(v => {
        const a = document.createElement('a');
        a.href = '#';
        a.textContent = v;
        a.style.color = '#4ec9b0';
        a.style.textDecoration = 'underline';
        a.onclick = (e) => { e.preventDefault(); gotoPath(v); };
        div.appendChild(a);
        div.appendChild(document.createElement('br'));
      });
      return div;
    }
    return JSON.stringify(val, null, 2);
  } else if (typeof val === 'object') {
    const pre = document.createElement('pre');
    pre.style.margin = '0';
    pre.textContent = JSON.stringify(val, null, 2);
    return pre;
  }
  if (typeof val === 'string' && val.startsWith('/xyz/')) {
    const a = document.createElement('a');
    a.href = '#';
    a.textContent = val;
    a.style.color = '#4ec9b0';
    a.style.textDecoration = 'underline';
    a.onclick = (e) => { e.preventDefault(); gotoPath(val); };
    return a;
  }
  return String(val);
}

function gotoPath(path) {
  let foundSvc = null;
  for (const [svc, paths] of pathCache.entries()) {
    if (paths.includes(path)) { foundSvc = svc; break; }
  }
  if (foundSvc) {
    let actualRow = null;
    document.querySelectorAll('.path-row').forEach(el => {
      if (el.textContent === path) actualRow = el;
    });
    const dummy = document.createElement('div');
    selectPath(foundSvc, path, actualRow || dummy);
    
    // Ensure the tree expands if it wasn't already (though pathCache means it was)
    const svcs = document.querySelectorAll('.svc-name');
    svcs.forEach(s => {
      if (s.textContent === foundSvc) {
        s.parentElement.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    });
  } else {
    alert(`Service for ${path} not loaded. Please expand its service on the left first.`);
  }
}

function initJournal() {
  if (wsJnl) { wsJnl.close(); wsJnl = null; }
  wsJnl = new WebSocket(`ws://${location.host}/ws/journal`);
  wsJnl.onmessage = e => {
    try {
      const log = JSON.parse(e.data);
      const div = document.createElement('div');
      div.style.padding = '2px 10px';
      div.style.borderBottom = '1px solid #0e0e0e';
      div.style.display = 'flex';
      div.style.gap = '8px';
      const time = log.__REALTIME_TIMESTAMP ? new Date(parseInt(log.__REALTIME_TIMESTAMP)/1000).toISOString().split('T')[1].slice(0,-1) : '';
      div.innerHTML = `<span style="color:#555;width:90px;flex-shrink:0;">${time}</span>` +
                      `<span style="color:#ce9178;width:80px;flex-shrink:0;overflow:hidden;text-overflow:ellipsis;">${log.SYSLOG_IDENTIFIER || log._COMM || ''}</span>` +
                      `<span style="color:#d4d4d4;flex:1;word-break:break-all;">${esc(log.MESSAGE || '')}</span>`;
      jnlList.insertBefore(div, jnlList.firstChild);
      if (jnlList.children.length > 500) jnlList.removeChild(jnlList.lastChild);
    } catch(err) {}
  };
}

// ── Event Listeners ───────────────────────────────────────────────────────────
// ── Sidebar resize ────────────────────────────────────────────────────────────
dividerEl.addEventListener('mousedown', e => {
  e.preventDefault();
  const startX = e.clientX;
  const startW = sidebarEl.offsetWidth;
  dividerEl.classList.add('dragging');

  function onMove(e) {
    const newW = Math.max(150, Math.min(startW + e.clientX - startX, appEl.offsetWidth * 0.65));
    sidebarEl.style.width = newW + 'px';
  }
  function onUp() {
    dividerEl.classList.remove('dragging');
    document.removeEventListener('mousemove', onMove);
    document.removeEventListener('mouseup', onUp);
  }
  document.addEventListener('mousemove', onMove);
  document.addEventListener('mouseup', onUp);
});

sigFilterEl.addEventListener('change', renderSigList);
sigPayloadEl.addEventListener('input', renderSigList);

sigClear.addEventListener('click', () => {
  allSigs = [];
  sigPaths.clear();
  sigFilterEl.innerHTML = '<option value="">All paths</option>';
  sigList.innerHTML = '';
});

tabSig.addEventListener('click', () => {
  tabSig.style.background = '#333'; tabSig.style.color = '#fff';
  tabJnl.style.background = '#222'; tabJnl.style.color = '#888';
  sigControls.style.display = 'flex';
  jnlControls.style.display = 'none';
  sigList.style.display = 'block';
  jnlList.style.display = 'none';
});

tabJnl.addEventListener('click', () => {
  tabJnl.style.background = '#333'; tabJnl.style.color = '#fff';
  tabSig.style.background = '#222'; tabSig.style.color = '#888';
  sigControls.style.display = 'none';
  jnlControls.style.display = 'flex';
  sigList.style.display = 'none';
  jnlList.style.display = 'block';
});

if (jnlClear) {
  jnlClear.addEventListener('click', () => {
    jnlList.innerHTML = '';
  });
}

btnSnapshot.addEventListener('click', async () => {
  if (!selectedService) return alert('Select a service first.');
  btnSnapshot.textContent = 'Wait...';
  try {
    const res = await fetch(`/api/dbus/snapshot?${getAuthParams()}&service=${encodeURIComponent(selectedService)}`);
    const data = await res.json();
    const blob = new Blob([JSON.stringify(data, null, 2)], {type: 'application/json'});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `snapshot_${selectedService}_${new Date().toISOString().replace(/[:.]/g,'-')}.json`;
    a.click();
    URL.revokeObjectURL(url);
  } catch(e) { alert(e); }
  btnSnapshot.textContent = 'Snapshot';
});

btnDiff.addEventListener('click', () => {
  if (!selectedService) return alert('Select a service first.');
  diffModal.classList.remove('hidden');
});
dClose.addEventListener('click', () => { diffModal.classList.add('hidden'); diffFile.value=''; diffResult.innerHTML=''; });

diffFile.addEventListener('change', async (e) => {
  if (!e.target.files.length) return;
  const file = e.target.files[0];
  const text = await file.text();
  try {
    const oldSnap = JSON.parse(text);
    diffResult.textContent = 'Fetching current state...';
    const res = await fetch(`/api/dbus/snapshot?${getAuthParams()}&service=${encodeURIComponent(selectedService)}`);
    const newSnap = await res.json();
    
    let diffStr = '';
    const allPaths = new Set([...Object.keys(oldSnap), ...Object.keys(newSnap)]);
    for (const p of Array.from(allPaths).sort()) {
      const oPath = oldSnap[p] || {};
      const nPath = newSnap[p] || {};
      const allIfaces = new Set([...Object.keys(oPath), ...Object.keys(nPath)]);
      for (const i of Array.from(allIfaces).sort()) {
        const oIf = oPath[i] || {};
        const nIf = nPath[i] || {};
        const allProps = new Set([...Object.keys(oIf), ...Object.keys(nIf)]);
        for (const pr of Array.from(allProps).sort()) {
          const ov = oIf[pr] !== undefined ? JSON.stringify(oIf[pr]) : undefined;
          const nv = nIf[pr] !== undefined ? JSON.stringify(nIf[pr]) : undefined;
          if (ov !== nv) {
            diffStr += `<b>Path:</b> ${p}\n<b>Iface:</b> ${i}\n<b>Prop:</b>  ${pr}\n`;
            if (ov !== undefined) diffStr += `<span style="color:#f44747">- ${esc(ov)}</span>\n`;
            if (nv !== undefined) diffStr += `<span style="color:#b5cea8">+ ${esc(nv)}</span>\n`;
            diffStr += '\n';
          }
        }
      }
    }
    diffResult.innerHTML = diffStr || '<span style="color:#888">No differences found.</span>';
  } catch(err) {
    diffResult.textContent = 'Error: ' + err;
  }
});
// DBus module ready

