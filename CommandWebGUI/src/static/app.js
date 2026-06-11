/**
 * CommandWebGUI — app.js  v3.0
 * Supports SSH + COM Port (serial), commands.json driven,
 * persistent history in SQLite, ANSI colors, disk bars,
 * Firefox-compatible File System Access fallback.
 */
'use strict';
const BASE = (typeof window.CWG_BASE !== 'undefined' ? window.CWG_BASE : '');

// ═══════════════════════════════════════════════════════════════
//  Global state
// ═══════════════════════════════════════════════════════════════
let _registry    = null;   // commands.json
let _discover    = null;   // /api/discover response
let _dbHandle    = null;   // File System Access handle (Chromium only)
let _connType    = 'ssh';  // 'ssh' | 'serial'

// Session command history (backed by SQLite via /api/history)
let _cmdHistory = [];
let _historyIdx = -1;

// Warn modal state
let _warnCallback = null;

// Connection failure counter
let _connFailCount = 0;

const el = (id) => document.getElementById(id);

async function parseJsonResponse(res) {
  const text = await res.text();
  try {
    return JSON.parse(text);
  } catch {
    const hint = text.trimStart().startsWith('<!')
      ? '（伺服器回傳 HTML 頁面，請確認 API 路徑是否正確）'
      : '';
    throw new Error(`HTTP ${res.status} ${res.url}${hint}`);
  }
}

// BusyBox applet categories
const BUSYBOX_CATS = {
  '檔案管理': ['ls','cp','mv','rm','mkdir','rmdir','touch','cat','find','ln','chmod','chown','chgrp','stat','du','df','dd','cpio','tar','unzip','gzip','gunzip','bzip2','bzcat','bunzip2','xzcat','zcat','lzcat','truncate','mktemp','readlink','realpath','dirname','basename','patch','diff','cmp','losetup','fstrim','mkfifo','mknod','chroot','install'],
  '文字處理': ['grep','egrep','fgrep','sed','awk','head','tail','cut','sort','uniq','wc','tr','printf','echo','od','hexdump','strings','md5sum','sha1sum','sha256sum','sha512sum','crc32','rev','expand','seq','shuf','xargs','tee','less','more','vi','expr','dc'],
  '系統/程序': ['ps','top','kill','killall','pgrep','pidof','nohup','nice','ionice','renice','sleep','usleep','timeout','watch','free','uptime','date','uname','arch','dmesg','halt','reboot','poweroff','sync','umount','mount','insmod','rmmod','lsmod','modprobe','modinfo','sysctl','klogd','syslogd','logger','crontab','crond','init','su','login','passwd','id','whoami','groups','env','printenv','which','type','strace'],
  '網路':     ['ping','ping6','traceroute','nslookup','wget','curl','tftp','telnet','nc','netstat','ss','ip','ifconfig','route','arp','brctl','udhcpc','udhcpd','ntpd','ftpd','httpd','dropbear','dropbearkey','sshd','ssh','scp','sftp'],
  '硬體/韌體':['i2cget','i2cset','i2cdetect','i2cdump','devmem','devmem2','gpioget','gpioset','gpiofind','flashcp','flash_erase','flash_eraseall','mtd','hexedit'],
  '儲存':     ['fdisk','gdisk','mkfs','e2fsck','fsck','blkid','lsblk','blockdev','hdparm'],
};


// ═══════════════════════════════════════════════════════════════
//  Utilities
// ═══════════════════════════════════════════════════════════════
function escHtml(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
}

function ansiToHtml(raw) {
  const FG = {
    30:'#555f6e',31:'#f87171',32:'#4ade80',33:'#facc15',
    34:'#60a5fa',35:'#c084fc',36:'#22d3ee',37:'#d4daf0',
    90:'#6b7494',91:'#ff8787',92:'#69db7c',93:'#ffe066',
    94:'#74c0fc',95:'#da77f2',96:'#67e8f9',97:'#f1f3f5',
  };
  const CUBE = (n) => {
    if (n < 16) return FG[n >= 8 ? 90+(n-8) : 30+n] || null;
    if (n >= 232) { const v=((n-232)*10+8).toString(16).padStart(2,'0'); return `#${v}${v}${v}`; }
    const idx=n-16, r=Math.floor(idx/36)*51, g=Math.floor((idx%36)/6)*51, b=(idx%6)*51;
    return `#${r.toString(16).padStart(2,'0')}${g.toString(16).padStart(2,'0')}${b.toString(16).padStart(2,'0')}`;
  };
  raw = raw.replace(/\r\n/g,'\n').replace(/\r/g,'\n');
  const parts = raw.split(/\x1b\[([0-9;]*)m/);
  let html='', openSpans=0, bold=false, italic=false;
  const closeAll = () => { while(openSpans-->0) html+='</span>'; openSpans=0; bold=false; italic=false; };
  for (let i=0; i<parts.length; i++) {
    if (i%2===0) { html += escHtml(parts[i]); }
    else {
      const codes = parts[i]===''?[0]:parts[i].split(';').map(Number);
      let j=0;
      while(j<codes.length) {
        const code=codes[j++];
        if (code===0) { closeAll(); }
        else if (code===1) { bold=true; }
        else if (code===3) { italic=true; }
        else if ((code>=30&&code<=37)||(code>=90&&code<=97)) {
          const colour=FG[code];
          if (colour) { html+=`<span style="color:${colour};${bold?'font-weight:700;':''}${italic?'font-style:italic;':''}">`;openSpans++; }
        } else if (code===38&&codes[j]===5) {
          j++;
          const n=codes[j++], colour=CUBE(n);
          if (colour) { html+=`<span style="color:${colour};">`;openSpans++; }
        }
      }
    }
  }
  closeAll();
  return html;
}

function getFormCfg() {
  const portVal = _connType === 'serial'
    ? (parseInt(el('cfgBaudSel').value) || 115200)
    : (parseInt(el('cfgPort').value) || 22);
  return {
    host:      el('cfgHost').value.trim(),
    port:      portVal,
    ssh_port:  portVal,
    user:      el('cfgUser').value.trim(),
    password:  el('cfgPass').value,
    conn_type: _connType,
  };
}

function hasPlaceholders(cmd) { return /<[^>]+>/.test(cmd); }

function placeBmcBadges() {
  const badges = el('bmcInfoBadges');
  const connBar = el('connBar');
  if (!badges || !connBar) return;

  if (document.body.classList.contains('te-mode')) {
    const shell = document.querySelector('.bt-shell-bar');
    if (!shell) return;
    const actions = shell.querySelector('.bt-header-actions');
    if (actions) shell.insertBefore(badges, actions);
    else shell.appendChild(badges);
  } else if (badges.parentElement !== connBar) {
    connBar.insertBefore(badges, el('conn-actions'));
  }
}

function resetBmcBadgesSlot() {
  const badges = el('bmcInfoBadges');
  const connBar = el('connBar');
  const actions = el('conn-actions');
  if (badges && connBar && actions && badges.parentElement !== connBar) {
    connBar.insertBefore(badges, actions);
  }
}

function lockConnFields() {
  const cfg = getFormCfg();
  el('connFieldsEdit').hidden = true;
  el('connFieldsSummary').hidden = false;
  const typeEl = el('connSummaryType');
  typeEl.textContent = _connType === 'serial' ? 'COM' : 'SSH';
  typeEl.className = 'bt-conn-badge' + (_connType === 'serial' ? ' bt-conn-badge--com' : '');
  el('connSummaryHost').textContent = typeof formatConnHost === 'function'
    ? formatConnHost(cfg)
    : (cfg.user ? `${cfg.host} · ${cfg.user}` : cfg.host);
  el('typeBtnSsh')?.setAttribute('disabled', '');
  el('typeBtnSerial')?.setAttribute('disabled', '');
  el('connBar').classList.add('connected');
  el('connectBtn').style.display = 'none';
}
function unlockConnFields() {
  el('connFieldsEdit').hidden = false;
  el('connFieldsSummary').hidden = true;
  el('typeBtnSsh')?.removeAttribute('disabled');
  el('typeBtnSerial')?.removeAttribute('disabled');
  el('connBar').classList.remove('connected');
  el('connectBtn').style.display = '';
}

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('zh-TW', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

// API endpoint routing based on connection type
function apiRun()      { return BASE + (_connType === 'serial' ? '/api/serial/run'      : '/api/run'); }
function apiTest()     { return BASE + (_connType === 'serial' ? '/api/serial/test'     : '/api/test'); }
function apiDiscover() { return BASE + (_connType === 'serial' ? '/api/serial/discover' : '/api/discover'); }

function cwgHomePath() {
  const b = BASE || '';
  return b ? `${b}/` : '/';
}

function tabFromPath() {
  const p = window.location.pathname.replace(/\/$/, '');
  if (p.endsWith('/dbus')) return 'dbus';
  if (p.endsWith('/command')) return 'cmd';
  return null;
}

function switchAppTab(tab, pushUrl = false) {
  const cmdView  = el('appCmdView');
  const dbusView = el('dbus-app-container');
  const appNav   = el('cwgAppNav');
  if (appNav) appNav.style.display = '';
  if (cmdView)  cmdView.style.display  = tab === 'cmd'  ? 'flex' : 'none';
  if (dbusView) dbusView.style.display = tab === 'dbus' ? 'flex' : 'none';
  el('navCmd')?.classList.toggle('active', tab === 'cmd');
  el('navDbus')?.classList.toggle('active', tab === 'dbus');
  if (pushUrl) {
    const path = (BASE || '') + (tab === 'dbus' ? '/dbus' : '/command');
    if (window.location.pathname.replace(/\/$/, '') !== path.replace(/\/$/, '')) {
      history.pushState({ tab }, '', path);
    }
  }
}

function navigateToTab(tab) {
  switchAppTab(tab, true);
}


// ═══════════════════════════════════════════════════════════════
//  Connection Type Toggle
// ═══════════════════════════════════════════════════════════════
let _cpConnType = 'ssh';

window.pm = new ProfileManager({ apiBase: '/api' });

function cpSetType(type) {
  _cpConnType = type;
  const isSsh = type === 'ssh';
  document.getElementById('cpBtnSsh').className    = isSsh  ? 'active' : '';
  document.getElementById('cpBtnSerial').className = !isSsh ? 'active' : '';
  document.getElementById('cpSshFields').style.display    = isSsh  ? 'block' : 'none';
  document.getElementById('cpSerialFields').style.display = !isSsh ? 'block' : 'none';
}

function cpConnect() {
  const isSsh    = _cpConnType === 'ssh';
  const host     = isSsh ? document.getElementById('cpHost').value.trim()
                         : document.getElementById('cpComPort').value.trim();
  const sshPort  = isSsh ? document.getElementById('cpSshPort').value
                         : document.getElementById('cpBaud').value;
  const ipmiPort = isSsh ? document.getElementById('cpIpmiPort').value
                         : document.getElementById('cpIpmiPortSerial').value;
  const user     = isSsh ? document.getElementById('cpUser').value.trim()
                         : document.getElementById('cpUserSerial').value.trim();
  const pass     = isSsh ? document.getElementById('cpPass').value
                         : document.getElementById('cpPassSerial').value;

  // Copy to connBar
  el('cfgHost').value     = host;
  el('cfgPort').value     = sshPort;
  el('cfgUser').value     = user;
  el('cfgPass').value     = pass;
  setConnType(_cpConnType);

  return connectBMC();
}

function cpCollectProfileData() {
  const isSsh = _cpConnType === 'ssh';
  const sshPort = parseInt(
    isSsh ? document.getElementById('cpSshPort').value : document.getElementById('cpBaud').value,
    10
  ) || (isSsh ? 22 : 115200);
  return {
    host: isSsh ? document.getElementById('cpHost').value.trim()
                : document.getElementById('cpComPort').value.trim(),
    ssh_port: sshPort,
    ipmi_port: parseInt(
      isSsh ? document.getElementById('cpIpmiPort').value
            : document.getElementById('cpIpmiPortSerial').value,
      10
    ) || 623,
    user: isSsh ? document.getElementById('cpUser').value.trim()
                : document.getElementById('cpUserSerial').value.trim(),
    password: isSsh ? document.getElementById('cpPass').value
                    : document.getElementById('cpPassSerial').value,
    conn_type: _cpConnType,
  };
}

function loadProfile(p) {
  const type    = p.conn_type || 'ssh';
  const sshPort = p.ssh_port != null && p.ssh_port !== ''
    ? p.ssh_port : (type === 'serial' ? 115200 : 22);

  cpSetType(type);

  if (type === 'ssh') {
    document.getElementById('cpHost').value    = p.host     || '';
    document.getElementById('cpSshPort').value = sshPort;
    document.getElementById('cpIpmiPort').value= p.ipmi_port || 623;
    document.getElementById('cpUser').value    = p.user     || '';
    document.getElementById('cpPass').value    = p.password || '';
  } else {
    document.getElementById('cpComPort').value         = p.host     || '';
    document.getElementById('cpBaud').value            = sshPort;
    document.getElementById('cpIpmiPortSerial').value  = p.ipmi_port || 623;
    document.getElementById('cpUserSerial').value      = p.user     || '';
    document.getElementById('cpPassSerial').value      = p.password || '';
  }

  // Sync connBar too
  el('cfgHost').value     = p.host     || '';
  el('cfgPort').value     = sshPort;
  el('cfgUser').value     = p.user     || '';
  el('cfgPass').value     = p.password || '';
  setConnType(type);
}

async function connectFromProfile(p) {
  loadProfile(p);
  await cpConnect();
}
pm.onConnect = (p) => connectFromProfile(p);

function setConnType(type, skipPortFetch = false) {
  _connType = type;
  const isSsh = type === 'ssh';
  el('typeBtnSsh').classList.toggle('active', isSsh);
  el('typeBtnSerial').classList.toggle('active', !isSsh);

  el('lblConnHost').textContent  = isSsh ? 'Host' : 'COM Port';
  el('lblConnPort').textContent  = isSsh ? 'Port' : 'Baud Rate';
  el('cfgHost').placeholder      = isSsh ? 'BMC IP' : 'COM3 / /dev/ttyUSB0';
  el('cfgHost').title            = isSsh ? '' : '雙擊可重新掃描並切換回下拉清單';

  el('cfgPort').style.display      = isSsh ? '' : 'none';
  el('cfgBaudSel').style.display   = isSsh ? 'none' : '';
  // Both hidden initially; fetchSerialPorts decides which to show in COM mode
  el('cfgSerialSel').style.display = 'none';
  el('cfgHost').style.display      = isSsh ? '' : 'none';

  if (isSsh) {
    // Clear stale COM port path when switching back to SSH
    const v = el('cfgHost').value;
    if (v.toUpperCase().startsWith('COM') || v.startsWith('/dev/')) el('cfgHost').value = '';
  } else {
    el('cfgBaudSel').value = '115200';
    if (!skipPortFetch) fetchSerialPorts();
  }
}

async function fetchSerialPorts() {
  const sel = el('cfgSerialSel');
  try {
    const res = await fetch(BASE + '/api/serial/ports');
    const d = await res.json();
    const ports = d.ports || [];
    if (ports.length > 0) {
      sel.innerHTML = '<option value="">-- 選擇 COM Port --</option>';
      ports.forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.device;
        opt.textContent = `${p.device}${p.description && p.description !== p.device ? ' — ' + p.description : ''}`;
        sel.appendChild(opt);
      });
      const manual = document.createElement('option');
      manual.value = '__manual__';
      manual.textContent = '✏ 手動輸入...';
      sel.appendChild(manual);
      sel.style.display = '';
      el('cfgHost').style.display = 'none';
    } else {
      // No ports detected — fallback to text input
      sel.style.display = 'none';
      el('cfgHost').style.display = '';
    }
  } catch {
    sel.style.display = 'none';
    el('cfgHost').style.display = '';
  }
}

function serialSelChange(sel) {
  if (sel.value === '__manual__') {
    sel.style.display = 'none';
    el('cfgHost').style.display = '';
    el('cfgHost').placeholder = 'COM3 / /dev/ttyUSB0';
    el('cfgHost').value = '';
    el('cfgHost').focus();
  } else if (sel.value) {
    el('cfgHost').value = sel.value;
  }
}


// ═══════════════════════════════════════════════════════════════
//  Initialization
// ═══════════════════════════════════════════════════════════════
window.onload = async () => {
  try {
    const res = await fetch(BASE + '/static/commands.json');
    _registry = await res.json();
  } catch (e) {
    console.error('Failed to load commands.json', e);
  }

  // Load persistent history from SQLite
  try {
    const res = await fetch(BASE + '/api/history');
    const d = await res.json();
    _cmdHistory = (d.history || []).map(h => ({
      cmd: h.cmd, stdout: h.stdout || '', exitCode: h.exit_code, ms: h.duration_ms, ts: h.ts
    }));
  } catch (e) { _cmdHistory = []; }

  el('chipInput').addEventListener('keydown', e => {
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      if (_historyIdx < _cmdHistory.length - 1) { _historyIdx++; el('chipInput').value = _cmdHistory[_historyIdx].cmd; }
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      if (_historyIdx > 0) { _historyIdx--; el('chipInput').value = _cmdHistory[_historyIdx].cmd; }
      else if (_historyIdx === 0) { _historyIdx = -1; el('chipInput').value = ''; }
    } else if (e.key === 'Enter') {
      runChipCmd();
    }
  });



  el('navCmd')?.addEventListener('click', e => { e.preventDefault(); navigateToTab('cmd'); });
  el('navDbus')?.addEventListener('click', e => { e.preventDefault(); navigateToTab('dbus'); });
  window.addEventListener('popstate', () => {
    const t = tabFromPath();
    if (t && el('mainContent')?.style.display !== 'none') switchAppTab(t);
  });

  pm.initConnectPage({
    cardsId: 'cwgProfileCards',
    onConnect: connectFromProfile,
    collectProfileData: cpCollectProfileData,
  });

  const pathTab = tabFromPath();
  if (pathTab && el('mainContent')?.style.display !== 'none') {
    switchAppTab(pathTab);
  }

  if (typeof window._HUB_CREDS !== 'undefined' && window._HUB_CREDS) {
    const c = window._HUB_CREDS;
    setConnType(c.conn_type || 'ssh', true);
    el('cfgHost').value = c.host     || '';
    el('cfgPort').value = c.ssh_port || 22;
    el('cfgUser').value = c.user     || '';
    el('cfgPass').value = c.password || '';

    // Hub 模式：Shell Bar 已有返回按鈕，隱藏 conn-bar 的 btnHome；隱藏連線欄位
    if (el('connFields')) el('connFields').style.display = 'none';

    connectBMC();
  }
};

function _resetConnectButtons() {
  const cpBtn = document.getElementById('cpConnectBtn');
  if (cpBtn) { cpBtn.textContent = 'Connect'; cpBtn.disabled = false; }
  const barBtn = el('connectBtn');
  if (barBtn) { barBtn.textContent = '連線'; barBtn.disabled = false; }
  pm.resetActiveConnectBtn();
}

function goHome() {
  if (pm._cardsContainerId) {
    pm.renderCards(pm._cardsContainerId, pm._cardsOptions || { onConnect: connectFromProfile });
  }

  if (typeof window._HUB_CREDS !== 'undefined' && window._HUB_CREDS) {
    window.location.href = '/dashboard';
    return;
  }

  el('chipPanel').classList.remove('show');
  window.scrollTo(0, 0);
  history.replaceState({}, '', cwgHomePath());
  const cp = document.getElementById('connectPage'); if(cp) cp.style.display = '';
  document.getElementById('connBar').style.display = 'none';
  const appNav = el('cwgAppNav'); if (appNav) appNav.style.display = 'none';
  if (!window._HUB_CREDS) {
    el('mainContent').style.display = 'none';
  }
  el('connDot').className = 'conn-dot grey';
  el('connTxt').textContent = '未連線';
  el('bmcInfoBadges').style.display = 'none';
  el('bmcOsBadge').textContent = '';
  el('bmcMachineBadge').textContent = '';
  unlockConnFields();
  resetBmcBadgesSlot();
  ['cfgHost','cfgPort','cfgUser','cfgPass'].forEach(id => { el(id).value = ''; });
  const nameEl = document.getElementById('cpNewProfileName');
  if (nameEl) nameEl.value = '';
  _resetConnectButtons();
  _discover = null;
  _connFailCount = 0;

}


// ═══════════════════════════════════════════════════════════════
//  Connection
// ═══════════════════════════════════════════════════════════════
function _connectButtons() {
  const cpBtn = document.getElementById('cpConnectBtn');
  const barBtn = el('connectBtn');
  return [cpBtn, barBtn].filter(Boolean);
}

function _setConnectBtnState(text, disabled) {
  _connectButtons().forEach((btn) => {
    btn.disabled = disabled;
    if (text) btn.textContent = text;
  });
}

async function connectBMC() {
  const cfg = getFormCfg();
  if (!cfg.host || !cfg.user) return alert('請輸入連線位置與帳號');

  const cp = document.getElementById('connectPage');
  const onConnectPage = cp && cp.style.display !== 'none';

  _setConnectBtnState('測試連線中…', true);
  if (el('connDot')) el('connDot').className = 'conn-dot yellow';
  if (el('connTxt')) el('connTxt').textContent = '測試連線...';

  try {
    const dTest = await testConnection(cfg, { apiBase: '/api' });

    if (cp) cp.style.display = 'none';
    document.getElementById('connBar').style.display = '';
    el('mainContent').style.display = 'flex';
    lockConnFields();
    _setConnectBtnState('探測中…', true);
    if (el('connTxt')) el('connTxt').textContent = '探測中...';
    el('commandSections').innerHTML = `
      <div class="discover-loading">
        <div class="discover-icon">🔍</div>
        正在探測 BMC 可用工具...
      </div>`;

    const rDisc = await fetch(apiDiscover(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    });
    _discover = await parseJsonResponse(rDisc);
    if (_discover.error) throw new Error(_discover.error);

    el('connDot').className = 'conn-dot green';
    const modeLabel = _connType === 'serial' ? `COM ${cfg.host}` : `${dTest.duration_ms}ms`;
    el('connTxt').textContent = `已連線 (${modeLabel})`;
    _connFailCount = 0;
    navigateToTab(tabFromPath() || 'cmd');

    if (_discover.os_info) {
      const os = _discover.os_info;
      el('bmcOsBadge').textContent = os.os_release || '';
      el('bmcMachineBadge').textContent = os.machine || os.kernel?.split(' ')[2] || '';
      el('bmcInfoBadges').style.display = 'flex';
      placeBmcBadges();
    }

    renderCommands();

    if (typeof reconnectDBus === 'function') reconnectDBus();
  } catch (e) {
    unlockConnFields();
    if (el('connDot')) el('connDot').className = 'conn-dot red';
    if (el('connTxt')) el('connTxt').textContent = '連線失敗';
    if (onConnectPage) {
      if (typeof showConnectError === 'function') showConnectError(e);
      else alert(e.message);
      _resetConnectButtons();
    } else {
      alert(e.message);
      goHome();
    }
  } finally {
    if (!onConnectPage) _resetConnectButtons();
  }
}


// ═══════════════════════════════════════════════════════════════
//  Render Commands
// ═══════════════════════════════════════════════════════════════
function renderCommands() {
  if (!_registry) return;
  const nav  = el('navPanel');
  const cont = el('commandSections');
  nav.innerHTML = '';
  cont.innerHTML = '';

  _registry.sections.forEach(sec => {
    let show = sec.always_show;
    if (sec.probe && _discover?.tools) {
      if (_discover.tools[sec.probe]) show = true;
    }
    if (!show) return;

    const a = document.createElement('a');
    a.href = '#' + sec.id;
    a.className = 'nav-item';
    a.innerHTML = `<span class="nav-icon">${sec.icon}</span> ${escHtml(sec.title)}`;
    nav.appendChild(a);

    const div = document.createElement('div');
    div.className = 'section';
    div.id = sec.id;
    let html = `<h2>${sec.icon} ${escHtml(sec.title)}</h2>`;

    if (sec.dynamic && _discover) html += renderDynamicBlock(sec.dynamic);

    if (sec.notes) {
      html += `<div class="note-box">`;
      sec.notes.forEach(n => { html += `<div>${n.text}</div>`; });
      html += `</div>`;
    }

    if (sec.groups) {
      sec.groups.forEach(g => {
        if (g.title) html += `<h3>${escHtml(g.title)}</h3>`;
        html += `<table class="cmd-table"><tr><th class="col-desc">功能</th><th>指令</th></tr>`;
        g.commands.forEach(c => {
          const isDanger  = c.dangerous ? 'true' : 'false';
          const dangerBadge = c.dangerous ? ' <span class="tag tag-err" style="margin-left:5px;">危險</span>' : '';
          // Use data-cmd attribute — never embed cmd string directly in onclick
          html += `
            <tr class="cmd-row" title="點擊執行"
              data-cmd="${escHtml(c.cmd)}" data-dangerous="${isDanger}"
              onclick="runInlineCmd(this)">
              <td>${escHtml(c.desc)}${dangerBadge}</td>
              <td class="cmd-text"><code>${renderCommandInputs(c.cmd)}</code></td>
            </tr>`;
        });
        html += `</table>`;
      });
    }
    div.innerHTML = html;
    cont.appendChild(div);
  });

  const observer = new IntersectionObserver(entries => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        document.querySelectorAll('.nav-item').forEach(a => {
          a.classList.toggle('active', a.getAttribute('href') === '#' + entry.target.id);
        });
      }
    });
  }, { rootMargin: '-100px 0px -60% 0px', threshold: 0 });

  document.querySelectorAll('.section').forEach(sec => observer.observe(sec));
}

function renderCommandInputs(cmdStr) {
  const services    = _discover?.running_services || [];
  const dbusServices = _discover?.dbus_services   || [];
  const applets     = _discover?.busybox_applets  || [];

  return escHtml(cmdStr).replace(/&lt;([^&]+)&gt;/g, (match, p1) => {
    if (p1 === 'service' && services.length) {
      const opts = services.map(s => `<option value="${escHtml(s.unit)}">${escHtml(s.unit)}</option>`).join('');
      return `<select class="inline-select" data-param="${p1}" onclick="event.stopPropagation()" onchange="this.closest('tr').click()"><option value="">選擇服務...</option>${opts}</select>`;
    }
    if (p1 === 'dbus_service' && dbusServices.length) {
      const opts = dbusServices.map(s => `<option value="${escHtml(s)}">${escHtml(s)}</option>`).join('');
      return `<select class="inline-select" data-param="${p1}" onclick="event.stopPropagation()" onchange="this.closest('tr').click()"><option value="">選擇 D-Bus...</option>${opts}</select>`;
    }
    if (p1 === 'applet' && applets.length) {
      const opts = applets.map(a => `<option value="${escHtml(a)}">${escHtml(a)}</option>`).join('');
      return `<select class="inline-select" data-param="${p1}" onclick="event.stopPropagation()" onchange="this.closest('tr').click()"><option value="">選擇 applet...</option>${opts}</select>`;
    }
    return `<input type="text" class="inline-arg" placeholder="${p1}" data-param="${p1}" onclick="event.stopPropagation()" onkeydown="if(event.key==='Enter'){event.preventDefault();this.closest('tr').click()}">`;
  });
}

// ── Dynamic info blocks ──────────────────────────────────────
function renderDynamicBlock(dynType) {
  let html = `<div class="dynamic-info">`;
  if (dynType === 'os_info' && _discover.os_info) {
    const o = _discover.os_info;
    html += `<div class="info-grid">
      <div class="info-item"><div class="info-label">OS</div><div class="info-value">${escHtml(o.os_release)}</div></div>
      <div class="info-item"><div class="info-label">Kernel</div><div class="info-value">${escHtml(o.kernel)}</div></div>
      <div class="info-item"><div class="info-label">Machine</div><div class="info-value">${escHtml(o.machine)}</div></div>
      <div class="info-item"><div class="info-label">Build ID</div><div class="info-value">${escHtml(o.build_id || '—')}</div></div>
    </div>`;
  } else if (dynType === 'fs_info' && _discover.fs_info) {
    html += renderDiskBars(_discover.fs_info);
    if (_discover.mem_info) html += `<h3 style="margin-top:14px;">Memory</h3><pre>${escHtml(_discover.mem_info)}</pre>`;
  } else if (dynType === 'net_info' && _discover.net_info) {
    html += `<pre>${escHtml(_discover.net_info)}</pre>`;
  } else if (dynType === 'sensor_info') {
    const s = _discover.sensor_info || '';
    html += s.trim() ? `<pre>${ansiToHtml(s)}</pre>` : `<span class="text-dim">無感測器資料 (ipmitool 未取得讀值)</span>`;
  } else if (dynType === 'services_interactive') {
    html += renderServicesTable();
  } else if (dynType === 'busybox_chips') {
    html += renderBusyboxChips();
  } else {
    html += `<span class="text-dim">無資料</span>`;
  }
  html += `</div>`;
  return html;
}

function renderServicesTable() {
  const services = _discover?.running_services || [];
  if (services.length === 0) return `<div class="text-dim" style="padding:8px 0;">未取得 running services 資料</div>`;

  let html = `
    <div style="margin-bottom:10px;font-size:12px;color:var(--text-dim);">
      共 <strong style="color:var(--accent);">${services.length}</strong> 個執行中的服務
    </div>
    <table class="svc-action-table">
      <tr><th style="width:44%;">服務名稱</th><th style="width:30%;">描述</th><th style="width:26%;">操作</th></tr>`;

  services.forEach(svc => {
    // Store unit in data attribute — never embed in onclick string
    html += `
      <tr data-svc="${escHtml(svc.unit)}">
        <td style="font-family:var(--font-mono);font-size:11.5px;color:var(--text-bright);word-break:break-all;">
          ${escHtml(svc.unit)}</td>
        <td style="font-size:12px;color:var(--text-dim);">${escHtml(svc.desc || '')}</td>
        <td>
          <div class="svc-actions">
            <button class="svc-btn svc-btn-status"  onclick="svcCmd(this,'status')">status</button>
            <button class="svc-btn svc-btn-stop"    onclick="svcDangerous(this,'stop')">stop</button>
            <button class="svc-btn svc-btn-restart" onclick="svcDangerous(this,'restart')">restart</button>
            <button class="svc-btn svc-btn-journal" onclick="svcCmd(this,'journal')">journalctl</button>
          </div>
        </td>
      </tr>`;
  });
  return html + `</table>`;
}

function svcCmd(btn, action) {
  const tr  = btn.closest('tr');
  const svc = tr.dataset.svc;
  const cmd = action === 'journal'
    ? `journalctl -u ${svc} --no-pager -n 50`
    : `systemctl ${action} ${svc} --no-pager`;
  tr.dataset.cmd = cmd;
  runInlineCmd(tr);
}

function svcDangerous(btn, action) {
  const tr  = btn.closest('tr');
  const svc = tr.dataset.svc;
  const cmd = `systemctl ${action} ${svc}`;
  showWarnModal(cmd, () => {
    tr.dataset.cmd = cmd;
    runInlineCmd(tr);
  });
}

function renderBusyboxChips() {
  const applets = _discover?.busybox_applets || [];
  if (applets.length === 0) return `<span class="text-dim">未偵測到 BusyBox applet 列表</span>`;

  const categorized = new Set();
  let html = '';
  for (const [catName, catCmds] of Object.entries(BUSYBOX_CATS)) {
    const inCat = applets.filter(a => catCmds.includes(a));
    if (inCat.length === 0) continue;
    inCat.forEach(a => categorized.add(a));
    html += `<h3 style="margin-top:12px;margin-bottom:6px;">${catName} <span style="color:var(--text-muted);font-size:10.5px;font-weight:400;">(${inCat.length})</span></h3>`;
    html += `<div class="cmd-grid">`;
    inCat.forEach(cmd => { html += `<span class="cmd-chip" onclick="quickChip('${escHtml(cmd)}')">${escHtml(cmd)}</span>`; });
    html += `</div>`;
  }
  const other = applets.filter(a => !categorized.has(a));
  if (other.length > 0) {
    html += `<h3 style="margin-top:12px;margin-bottom:6px;">其他 <span style="color:var(--text-muted);font-size:10.5px;font-weight:400;">(${other.length})</span></h3>`;
    html += `<div class="cmd-grid">`;
    other.forEach(cmd => { html += `<span class="cmd-chip" onclick="quickChip('${escHtml(cmd)}')">${escHtml(cmd)}</span>`; });
    html += `</div>`;
  }
  const ver = _discover?.busybox_version || '';
  if (ver) html = `<div style="font-size:12px;color:var(--text-dim);margin-bottom:8px;">BusyBox ${escHtml(ver)} — ${applets.length} applets</div>` + html;
  return html;
}

function renderDiskBars(dfText) {
  const lines = dfText.trim().split('\n').filter(l => l.trim());
  if (lines.length < 2) return `<pre>${escHtml(dfText)}</pre>`;
  let html = `<table class="disk-table"><colgroup><col style="width:28%"><col style="width:14%"><col style="width:14%"><col style="width:22%"><col style="width:22%"></colgroup>
    <tr>
      <th style="padding:5px 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);background:var(--surface3);border-bottom:1px solid var(--border);">Filesystem</th>
      <th style="padding:5px 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);background:var(--surface3);border-bottom:1px solid var(--border);text-align:right;">Size</th>
      <th style="padding:5px 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);background:var(--surface3);border-bottom:1px solid var(--border);text-align:right;">Avail</th>
      <th style="padding:5px 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);background:var(--surface3);border-bottom:1px solid var(--border);">Usage</th>
      <th style="padding:5px 8px;font-size:10.5px;text-transform:uppercase;letter-spacing:.06em;color:var(--text-dim);background:var(--surface3);border-bottom:1px solid var(--border);">Mounted</th>
    </tr>`;
  for (let i=1; i<lines.length; i++) {
    const cols = lines[i].split(/\s+/);
    if (cols.length < 6) continue;
    const [fs,size,,avail,pctStr,...rest] = cols;
    const mount = rest.join(' ') || cols[5];
    const pct = parseInt(pctStr) || 0;
    const barClass = pct >= 90 ? 'crit' : pct >= 75 ? 'warn' : '';
    html += `<tr style="border-bottom:1px solid rgba(42,47,74,0.4);">
      <td class="disk-row-fs"   style="padding:6px 8px;">${escHtml(fs)}</td>
      <td class="disk-row-size" style="padding:6px 8px;">${escHtml(size)}</td>
      <td class="disk-row-size" style="padding:6px 8px;">${escHtml(avail)}</td>
      <td style="padding:6px 8px;">
        <div class="disk-bar-bg"><div class="disk-bar-fill ${barClass}" style="width:${pct}%;"></div></div>
        <div class="disk-bar-pct">${pctStr}</div>
      </td>
      <td class="disk-row-mount" style="padding:6px 8px;">${escHtml(mount)}</td>
    </tr>`;
  }
  return html + `</table>`;
}


// ═══════════════════════════════════════════════════════════════
//  Command Execution
// ═══════════════════════════════════════════════════════════════
let _activeCmdTr = null;

function formatSmartOutput(text) {
  if (!text || !text.trim()) return '<span class="text-dim">(無輸出)</span>';
  const coloured = ansiToHtml(text);
  const lineCount = (text.match(/\n/g) || []).length + 1;
  if (lineCount <= 120) return `<pre class="output-pre">${coloured}</pre>`;
  const lines = coloured.split('\n');
  const visible = lines.slice(0,60).join('\n');
  const hidden  = lines.slice(60).join('\n');
  const uid = 'fold' + Date.now();
  return `<pre class="output-pre">${visible}\n<span id="${uid}-more" style="display:none;">${hidden}</span></pre>
    <button class="output-fold-toggle" id="${uid}-btn"
      onclick="const m=document.getElementById('${uid}-more');const b=document.getElementById('${uid}-btn');const open=m.style.display==='none';m.style.display=open?'':'none';b.textContent=open?'▲ 折疊輸出':'▼ 展開全部 (共 ${lineCount} 行)';">
      ▼ 展開全部 (共 ${lineCount} 行)</button>`;
}

async function runInlineCmd(targetTr) {
  const tr = targetTr;
  _activeCmdTr = tr;

  // Read cmd from data attribute (never from onclick string — avoids single-quote escaping issues)
  const rawCmd = tr.dataset.cmd;
  if (!rawCmd) return;

  let finalCmd = rawCmd;
  const inputs = tr.querySelectorAll('.inline-arg, .inline-select');
  let missing = false, firstMissing = null;

  inputs.forEach(inp => {
    const val = inp.value.trim();
    if (!val) {
      inp.style.outline = '2px solid var(--red)';
      missing = true;
      if (!firstMissing) firstMissing = inp;
    } else {
      inp.style.outline = '';
      finalCmd = finalCmd.replace(`<${inp.dataset.param}>`, val);
    }
  });

  if (missing) { if (firstMissing) firstMissing.focus(); return; }

  if (tr.dataset.dangerous === 'true' && !tr.dataset.confirmed) {
    showWarnModal(finalCmd, () => { tr.dataset.confirmed = 'true'; runInlineCmd(tr); });
    return;
  }
  tr.dataset.confirmed = '';

  let outTr = tr.nextElementSibling;
  if (outTr && outTr.classList.contains('cmd-output-row')) {
    outTr.style.display = '';
  } else {
    outTr = document.createElement('tr');
    outTr.className = 'cmd-output-row';
    const uid = 'dur' + Date.now();
    outTr.innerHTML = `
      <td colspan="${tr.children.length}" class="output-cell">
        <div class="output-wrap">
          <div class="output-hdr">
            <span class="output-cmd">${escHtml(finalCmd)}</span>
            <div class="output-meta">
              <span class="exit-badge" id="exit-${uid}">…</span>
              <span class="dur-badge"  id="${uid}">…</span>
              <button class="output-btn" onclick="this.closest('tr').style.display='none'">關閉</button>
            </div>
          </div>
          <div class="output-body"></div>
        </div>
      </td>`;
    tr.parentNode.insertBefore(outTr, tr.nextSibling);
  }

  const outBody  = outTr.querySelector('.output-body');
  const durBadge = outTr.querySelector('.dur-badge');
  const exitBadge = outTr.querySelector('.exit-badge');
  const outCell  = outTr.querySelector('.output-cell');

  outCell.className = 'output-cell';
  outBody.innerHTML = '<pre class="output-pre loading"><span class="output-loader">⚙</span> 執行中...</pre>';
  durBadge.textContent = '…';
  exitBadge.textContent = '…';
  exitBadge.className = 'exit-badge';

  const cfg = getFormCfg();
  tr.style.pointerEvents = 'none';

  try {
    const res = await fetch(apiRun(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cfg, command: finalCmd })
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '執行失敗');

    durBadge.textContent = d.duration_ms + 'ms';
    const exitCode = d.exit_code ?? -1;
    if (exitCode === 0)   { outCell.classList.add('cell-ok');  exitBadge.textContent='✓ exit 0';        exitBadge.className='exit-badge exit-ok'; }
    else if (exitCode===127) { outCell.classList.add('cell-na'); exitBadge.textContent='⚠ not found'; exitBadge.className='exit-badge exit-na'; }
    else                   { outCell.classList.add('cell-err'); exitBadge.textContent=`✗ exit ${exitCode}`; exitBadge.className='exit-badge exit-err'; }

    let out = d.stdout || '';
    if (d.stderr) out += (out ? '\n[stderr]\n' : '') + d.stderr;
    outBody.innerHTML = formatSmartOutput(out);
    _connFailCount = 0;
    pushHistory(finalCmd, out, exitCode, d.duration_ms);
  } catch (e) {
    outCell.classList.add('cell-err');
    exitBadge.textContent = '✗ error'; exitBadge.className = 'exit-badge exit-err';
    outBody.innerHTML = `<pre class="output-pre pre-err">錯誤: ${escHtml(e.message)}</pre>`;
    _connFailCount++;
    if (_connFailCount >= 3) {
      const go = confirm(`連線已中斷（連續 ${_connFailCount} 次失敗），是否返回首頁？`);
      if (go) { goHome(); return; }
      _connFailCount = 0;
    }
  } finally {
    tr.style.pointerEvents = '';
  }
}

function closeChipPanel() { el('chipPanel').classList.remove('show'); }
function clearChipOutput() { el('chipOutput').textContent=''; el('chipOutput').className='chip-output-pre'; }

async function copyChipOutput() {
  const text = el('chipOutput').innerText || el('chipOutput').textContent || '';
  if (!text.trim()) return;
  try {
    await navigator.clipboard.writeText(text);
    const btn = el('copyOutputBtn');
    const orig = btn.textContent;
    btn.textContent = '✅ 已複製';
    setTimeout(() => { btn.textContent = orig; }, 1500);
  } catch (e) { alert('複製失敗：' + e.message); }
}

async function runChipCmd() {
  const cmd = el('chipInput').value.trim();
  if (!cmd) return;

  const cfg = getFormCfg();
  const btn = el('chipRunBtn');
  btn.disabled = true; btn.textContent = '…';

  const pre = el('chipOutput');
  pre.className = 'chip-output-pre loading';
  pre.textContent = '執行中...';
  _historyIdx = -1;

  try {
    const res = await fetch(apiRun(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...cfg, command: cmd })
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '執行失敗');

    let out = d.stdout || '';
    if (d.stderr) out += (out ? '\n[stderr]\n' : '') + d.stderr;
    if (!out.trim()) out = '(無輸出)';
    const exitCode = d.exit_code ?? -1;
    pre.className = exitCode===0 ? 'chip-output-pre pre-ok' : exitCode===127 ? 'chip-output-pre pre-na' : 'chip-output-pre pre-err';
    pre.innerHTML = ansiToHtml(out);
    _connFailCount = 0;
    pushHistory(cmd, out, exitCode, d.duration_ms);
  } catch (e) {
    pre.className = 'chip-output-pre pre-err';
    pre.textContent = `錯誤: ${e.message}`;
    _connFailCount++;
  } finally {
    btn.disabled = false; btn.textContent = '執行';
  }
}

function quickChip(cmd, autoRun=true) {
  el('chipInput').value = cmd;
  el('chipOutput').textContent = '';
  el('chipOutput').className = 'chip-output-pre';
  el('chipPanel').classList.add('show');
  _historyIdx = -1;
  if (autoRun) runChipCmd();
}


// ═══════════════════════════════════════════════════════════════
//  Search
// ═══════════════════════════════════════════════════════════════
function filterAll(val) {
  val = val.toLowerCase().trim();
  let total=0, visible=0;
  document.querySelectorAll('.cmd-row').forEach(tr => {
    total++;
    const show = !val || tr.textContent.toLowerCase().includes(val);
    tr.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  document.querySelectorAll('.section').forEach(sec => {
    const hasVisible = Array.from(sec.querySelectorAll('.cmd-row')).some(tr => tr.style.display !== 'none');
    sec.style.display = hasVisible ? '' : 'none';
  });
  const counter = el('searchCounter');
  if (val) { counter.style.display=''; counter.innerHTML=`找到 <em>${visible}</em> / ${total} 個指令`; }
  else { counter.style.display = 'none'; }
}


// ═══════════════════════════════════════════════════════════════
//  Command History (SQLite-backed)
// ═══════════════════════════════════════════════════════════════
async function pushHistory(cmd, stdout, exitCode, ms) {
  const entry = { cmd, stdout: (stdout||'').slice(0,800), exitCode, ms, ts: Date.now() };
  _cmdHistory.unshift(entry);
  if (_cmdHistory.length > 200) _cmdHistory = _cmdHistory.slice(0,200);
  try {
    await fetch(BASE + '/api/history', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ cmd, stdout: entry.stdout, exit_code: exitCode, duration_ms: ms })
    });
  } catch (e) { /* non-critical */ }
}

function openHistorySidebar() { renderHistoryList(); el('historyOverlay').classList.add('open'); el('historySidebar').classList.add('open'); }
function closeHistorySidebar() { el('historyOverlay').classList.remove('open'); el('historySidebar').classList.remove('open'); }

function renderHistoryList() {
  const list = el('historyList');
  if (_cmdHistory.length === 0) {
    list.innerHTML = '<div class="history-empty">尚無命令歷史<br><small>執行任意指令後即可記錄</small></div>';
    return;
  }
  list.innerHTML = _cmdHistory.map((h, i) => {
    const exitOk = h.exitCode === 0;
    return `<div class="history-item" onclick="useHistoryItem(${i})">
      <div class="history-item-cmd" title="${escHtml(h.cmd)}">${escHtml(h.cmd)}</div>
      <div class="history-item-meta">
        <span class="history-item-ts">${fmtTime(h.ts)}</span>
        <span class="history-item-exit ${exitOk?'ok':'err'}">${exitOk?'✓ '+h.exitCode:'✗ '+h.exitCode}</span>
        <span class="history-item-ms">${h.ms}ms</span>
      </div>
    </div>`;
  }).join('');
}

function useHistoryItem(idx) {
  const h = _cmdHistory[idx]; if (!h) return;
  el('chipInput').value = h.cmd;
  el('chipOutput').textContent = ''; el('chipOutput').className = 'chip-output-pre';
  el('chipPanel').classList.add('show');
  _historyIdx = idx;
  closeHistorySidebar();
}

async function clearHistory() {
  if (!confirm('確定清除所有命令歷史？')) return;
  _cmdHistory = []; _historyIdx = -1;
  try { await fetch(BASE + '/api/history', { method: 'DELETE' }); } catch (e) { /* non-critical */ }
  renderHistoryList();
}


// ═══════════════════════════════════════════════════════════════
//  Warning Modal
// ═══════════════════════════════════════════════════════════════
function showWarnModal(finalCmd, onConfirm) {
  el('warnModal').style.display = 'flex';
  el('warnReasonText').textContent = '此指令將改變系統行為或設定，確認要執行嗎？';
  el('warnCmdText').textContent = finalCmd;
  el('warnBox').className = 'warn-box warn-warn';
  el('warnIcon').textContent = '⚠️';
  _warnCallback = onConfirm;
  const btn = el('warnConfirmBtn');
  btn.className = 'warn-btn confirm-warn';
  btn.disabled = false;
  btn.textContent = '確認執行';
}
function cancelWarn() { el('warnModal').style.display='none'; _warnCallback=null; }
function confirmWarn() {
  el('warnModal').style.display='none';
  if (_warnCallback) { const cb=_warnCallback; _warnCallback=null; cb(); }
}


function shutdownApp() {
  const name = window._HUB_CREDS ? 'BMC ToolEntry 服務' : (window.BMC_SERVICE_NAME || 'CommandWebGUI 服務');
  shutdownToolService(name);
}


