/**
 * CommandWebGUI — app.js  v3.0
 * Supports SSH + COM Port (serial), commands.json driven,
 * persistent history in SQLite, ANSI colors, disk bars,
 * Firefox-compatible File System Access fallback.
 */
'use strict';

// ═══════════════════════════════════════════════════════════════
//  Global state
// ═══════════════════════════════════════════════════════════════
let _registry    = null;   // commands.json
let _discover    = null;   // /api/discover response
let _dbHandle    = null;   // File System Access handle (Chromium only)
let _connType    = 'ssh';  // 'ssh' | 'serial'
let _editConnType = 'ssh'; // conn_type in edit modal

// Session command history (backed by SQLite via /api/history)
let _cmdHistory = [];
let _historyIdx = -1;

// Warn modal state
let _warnCallback = null;

// Connection failure counter
let _connFailCount = 0;

const el = (id) => document.getElementById(id);

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
    user:      el('cfgUser').value.trim(),
    password:  el('cfgPass').value,
    conn_type: _connType,
  };
}

function hasPlaceholders(cmd) { return /<[^>]+>/.test(cmd); }

function lockConnFields() {
  ['cfgHost','cfgPort','cfgUser','cfgPass'].forEach(id => {
    const e = el(id); if(e) e.setAttribute('readonly','');
  });
  el('cfgSerialSel')?.setAttribute('disabled','');
  el('cfgBaudSel')?.setAttribute('disabled','');
  el('typeBtnSsh')?.setAttribute('disabled','');
  el('typeBtnSerial')?.setAttribute('disabled','');
  el('connBar').classList.add('connected');
  el('connectBtn').style.display = 'none';
}
function unlockConnFields() {
  ['cfgHost','cfgPort','cfgUser','cfgPass'].forEach(id => {
    const e = el(id); if(e) e.removeAttribute('readonly');
  });
  el('cfgSerialSel')?.removeAttribute('disabled');
  el('cfgBaudSel')?.removeAttribute('disabled');
  el('typeBtnSsh')?.removeAttribute('disabled');
  el('typeBtnSerial')?.removeAttribute('disabled');
  el('connBar').classList.remove('connected');
  el('connectBtn').style.display = '';
}

function fmtTime(ts) {
  return new Date(ts).toLocaleTimeString('zh-TW', { hour:'2-digit', minute:'2-digit', second:'2-digit' });
}

// API endpoint routing based on connection type
function apiRun()      { return _connType === 'serial' ? '/api/serial/run'      : '/api/run'; }
function apiTest()     { return _connType === 'serial' ? '/api/serial/test'     : '/api/test'; }
function apiDiscover() { return _connType === 'serial' ? '/api/serial/discover' : '/api/discover'; }


// ═══════════════════════════════════════════════════════════════
//  Connection Type Toggle
// ═══════════════════════════════════════════════════════════════
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

function setEditConnType(type) {
  _editConnType = type;
  const isSsh = type === 'ssh';
  el('editTypeBtnSsh').classList.toggle('active', isSsh);
  el('editTypeBtnSerial').classList.toggle('active', !isSsh);
  el('editLblHost').textContent = isSsh ? 'Host' : 'COM Port';
  el('editLblPort').textContent = isSsh ? 'Port' : 'Baud Rate';
  el('editProfHost').placeholder = isSsh ? 'BMC IP' : 'COM3 / /dev/ttyUSB0';
  if (!isSsh && (!el('editProfPort').value || el('editProfPort').value === '22')) {
    el('editProfPort').value = '115200';
  }
}

async function fetchSerialPorts() {
  const sel = el('cfgSerialSel');
  try {
    const res = await fetch('/api/serial/ports');
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
    const res = await fetch('/static/commands.json');
    _registry = await res.json();
  } catch (e) {
    console.error('Failed to load commands.json', e);
  }

  // Load persistent history from SQLite
  try {
    const res = await fetch('/api/history');
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

  await loadWelcomeProfiles();
};

function goHome() {
  el('chipPanel').classList.remove('show');
  window.scrollTo(0, 0);
  el('welcomePage').style.display = '';
  el('mainContent').style.display = 'none';
  el('connDot').className = 'conn-dot grey';
  el('connTxt').textContent = '未連線';
  el('saveConnBtn').style.display = 'none';
  el('bmcInfoBadges').style.display = 'none';
  el('bmcOsBadge').textContent = '';
  el('bmcMachineBadge').textContent = '';
  unlockConnFields();
  ['cfgHost','cfgPort','cfgUser','cfgPass'].forEach(id => { el(id).value = ''; });
  _discover = null;
  _connFailCount = 0;
  loadWelcomeProfiles();
}


// ═══════════════════════════════════════════════════════════════
//  Connection
// ═══════════════════════════════════════════════════════════════
async function connectBMC() {
  const cfg = getFormCfg();
  if (!cfg.host || !cfg.user) return alert('請輸入連線位置與帳號');

  const btn = el('connectBtn');
  btn.disabled = true;
  btn.textContent = '連線中...';
  el('connDot').className = 'conn-dot yellow';
  el('connTxt').textContent = '測試連線...';

  try {
    const rTest = await fetch(apiTest(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg)
    });
    const dTest = await rTest.json();
    if (!dTest.ok) throw new Error(dTest.error || '連線失敗');

    el('connTxt').textContent = '探測中...';
    el('welcomePage').style.display = 'none';
    el('mainContent').style.display = 'block';
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
    _discover = await rDisc.json();
    if (_discover.error) throw new Error(_discover.error);

    el('connDot').className = 'conn-dot green';
    const modeLabel = _connType === 'serial' ? `COM ${cfg.host}` : `${dTest.duration_ms}ms`;
    el('connTxt').textContent = `已連線 (${modeLabel})`;
    el('saveConnBtn').style.display = 'inline-block';
    _connFailCount = 0;
    lockConnFields();

    if (_discover.os_info) {
      const os = _discover.os_info;
      el('bmcOsBadge').textContent = os.os_release || '';
      el('bmcMachineBadge').textContent = os.machine || os.kernel?.split(' ')[2] || '';
      el('bmcInfoBadges').style.display = 'flex';
    }

    renderCommands();
    await populateProfileSelect();
  } catch (e) {
    el('connDot').className = 'conn-dot red';
    el('connTxt').textContent = '連線失敗';
    alert(e.message);
    goHome();
  } finally {
    btn.disabled = false;
    btn.textContent = '連線';
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
    await fetch('/api/history', {
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
  try { await fetch('/api/history', { method: 'DELETE' }); } catch (e) { /* non-critical */ }
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


// ═══════════════════════════════════════════════════════════════
//  Profile Management
// ═══════════════════════════════════════════════════════════════
async function loadWelcomeProfiles() {
  try {
    const res = await fetch('/api/profiles');
    const data = await res.json();
    const cont = el('welcomeProfileCards');
    cont.innerHTML = '';
    if (!data.profiles || data.profiles.length === 0) {
      cont.innerHTML = `<div style="color:var(--text-dim);font-size:13px;padding:10px 0;">目前尚無已儲存的連線</div>`;
      return;
    }
    data.profiles.forEach(p => {
      const card = document.createElement('div');
      card.className = 'prof-card';
      const isSerial = p.conn_type === 'serial';
      const badge = `<span class="conn-type-badge ${isSerial?'serial':'ssh'}">${isSerial?'COM':'SSH'}</span>`;
      const connInfo = isSerial
        ? `${p.host} @ ${p.port}bps`
        : `${p.user}@${p.host}:${p.port}`;
      const savedAt = p.saved_at ? `<div class="prof-card-meta">${escHtml(p.saved_at)}</div>` : '';
      card.innerHTML = `
        ${badge}
        <div class="prof-card-title">${escHtml(p.name)}</div>
        <div class="prof-card-info">${escHtml(connInfo)}</div>
        ${savedAt}
        <div class="prof-card-actions">
          <button class="prof-btn btn-connect" onclick="applyProfile('${escHtml(p.name)}')">▶ 連線</button>
          <button class="prof-btn" onclick="openEditModal('${escHtml(p.name)}')">編輯</button>
          <button class="prof-btn btn-danger" onclick="delProfile('${escHtml(p.name)}')">刪除</button>
        </div>`;
      cont.appendChild(card);
    });
  } catch (e) { console.error(e); }
}

async function applyProfile(name) {
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(name)}`);
    const p = await res.json();
    if (p.error) throw new Error(p.error);
    const ct = p.conn_type || 'ssh';
    setConnType(ct, true);  // skip auto fetchSerialPorts; we'll do it below if needed
    el('cfgHost').value = p.host;
    el('cfgPort').value = p.port;
    el('cfgUser').value = p.user;
    el('cfgPass').value = p.password || '';
    if (ct === 'serial') {
      el('cfgBaudSel').value = String(p.port);
      await fetchSerialPorts();
      // If dropdown is shown, try to select the saved port
      const sel = el('cfgSerialSel');
      if (sel.style.display !== 'none') {
        const match = Array.from(sel.options).find(o => o.value === p.host);
        if (match) {
          sel.value = p.host;
        } else {
          // Saved port not in detected list — switch to manual input
          sel.style.display = 'none';
          el('cfgHost').style.display = '';
        }
      }
    }
    connectBMC();
  } catch (e) { alert(e.message); }
}

let _editingProfile = null;
async function openEditModal(name) {
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(name)}`);
    const p = await res.json();
    if (p.error) throw new Error(p.error);
    _editingProfile = p;
    const ct = p.conn_type || 'ssh';
    el('editOrigName').value = p.name;
    el('editProfName').value = p.name;
    el('editProfHost').value = p.host;
    el('editProfPort').value = p.port;
    el('editProfUser').value = p.user;
    el('editProfPass').value = p.password || '';
    el('editProfError').style.display = 'none';
    setEditConnType(ct);
    el('editProfileModal').style.display = 'flex';
  } catch (e) { alert(e.message); }
}

function closeEditModal() { el('editProfileModal').style.display='none'; _editingProfile=null; }

async function saveEditProfile() {
  const origName = el('editOrigName').value;
  const newName  = el('editProfName').value.trim();
  const host     = el('editProfHost').value.trim();
  const port     = el('editProfPort').value;
  const user     = el('editProfUser').value.trim();
  const pass     = el('editProfPass').value;

  if (!newName || !host || !port || !user) {
    el('editProfError').textContent='請填寫所有必填欄位'; el('editProfError').style.display='block'; return;
  }
  try {
    const btn = el('editProfSaveBtn'); btn.disabled = true;
    const res = await fetch(`/api/profiles/${encodeURIComponent(origName)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name:newName, host, port:parseInt(port), user, password:pass, conn_type:_editConnType })
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '儲存失敗');
    if (_dbHandle) await autoSyncDb();
    closeEditModal();
    loadWelcomeProfiles();
    populateProfileSelect();
  } catch (e) {
    el('editProfError').textContent=e.message; el('editProfError').style.display='block';
  } finally { el('editProfSaveBtn').disabled=false; }
}

async function delProfile(name) {
  if (!confirm(`確定要刪除連線 "${name}" 嗎？`)) return;
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(name)}`, { method:'DELETE' });
    if (!res.ok) throw new Error('刪除失敗');
    if (_dbHandle) await autoSyncDb();
    loadWelcomeProfiles();
  } catch (e) { alert(e.message); }
}

async function cmdSaveConnection() {
  const cfg = getFormCfg();
  if (!cfg.host || !cfg.user) return alert('Host/User 不能為空');
  const name = prompt('請輸入連線名稱：', cfg.host);
  if (!name) return;

  const btn = el('saveConnBtn');
  const origText = btn.textContent;
  btn.disabled = true; btn.textContent = '產生檔案中...';

  try {
    let handle;
    if (window.showSaveFilePicker) {
      try {
        handle = await window.showSaveFilePicker({
          suggestedName: `${name}.db`,
          types: [{ description:'SQLite DB', accept:{'application/x-sqlite3':['.db']} }]
        });
      } catch (err) {
        if (err.name === 'AbortError') { btn.textContent=origText; btn.disabled=false; return; }
      }
    }

    const generateR = await fetch('/api/profiles/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ...cfg, results: _discover })
    });
    if (!generateR.ok) throw new Error('產生連線檔失敗');
    const blob = await generateR.blob();

    if (handle) {
      const writable = await handle.createWritable();
      await writable.write(blob); await writable.close();
      btn.textContent = '✅ 已存檔';
    } else {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = `${name}.db`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(a.href);
      btn.textContent = '✅ 已下載';
    }

    await fetch('/api/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, ...cfg, results: _discover })
    });
  } catch (e) { alert(e.message); }
  setTimeout(() => { btn.textContent=origText; btn.disabled=false; }, 1600);
}


// ═══════════════════════════════════════════════════════════════
//  Workspace (File System Access API + Firefox fallback)
// ═══════════════════════════════════════════════════════════════
async function cmdOpenDb() {
  if (!window.showOpenFilePicker) {
    // Firefox / non-HTTPS fallback: use hidden file input
    const input = document.createElement('input');
    input.type = 'file'; input.accept = '.db';
    input.onchange = async (e) => {
      const file = e.target.files[0]; if (!file) return;
      const formData = new FormData(); formData.append('file', file);
      try {
        const res = await fetch('/api/profiles/import', { method:'POST', body:formData });
        const d = await res.json();
        if (!res.ok) throw new Error(d.error || '匯入失敗');
        el('openedDbName').textContent = file.name; el('openedDbName').style.display='inline-block';
        await loadWelcomeProfiles();
      } catch (e) { alert(e.message); }
    };
    input.click();
    return;
  }
  try {
    const [handle] = await window.showOpenFilePicker({
      types: [{ description:'SQLite DB', accept:{'application/x-sqlite3':['.db']} }]
    });
    _dbHandle = handle;
    const file = await handle.getFile();
    const formData = new FormData(); formData.append('file', file);
    const res = await fetch('/api/profiles/import', { method:'POST', body:formData });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || '匯入失敗');
    el('openedDbName').textContent = file.name; el('openedDbName').style.display='inline-block';
    await loadWelcomeProfiles();
  } catch (e) { if (e.name !== 'AbortError') alert(e.message); }
}

async function cmdSaveAsDb() {
  if (!window.showSaveFilePicker) {
    // Firefox fallback: trigger download
    try {
      const res = await fetch('/api/profiles/export_all');
      if (!res.ok) throw new Error('匯出失敗');
      const blob = await res.blob();
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob); a.download = 'profiles.db';
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(a.href);
    } catch (e) { alert(e.message); }
    return;
  }
  try {
    const handle = await window.showSaveFilePicker({
      suggestedName: 'profiles.db',
      types: [{ description:'SQLite DB', accept:{'application/x-sqlite3':['.db']} }]
    });
    const res = await fetch('/api/profiles/export_all');
    if (!res.ok) throw new Error('匯出失敗');
    const blob = await res.blob();
    const writable = await handle.createWritable();
    await writable.write(blob); await writable.close();
    _dbHandle = handle;
    el('openedDbName').textContent = handle.name; el('openedDbName').style.display='inline-block';
    alert('✅ 已另存並切換工作區');
  } catch (e) { if (e.name !== 'AbortError') alert(e.message); }
}

async function autoSyncDb() {
  if (!_dbHandle) return;
  try {
    const res = await fetch('/api/profiles/export_all');
    if (!res.ok) return;
    const blob = await res.blob();
    const writable = await _dbHandle.createWritable();
    await writable.write(blob); await writable.close();
  } catch (e) { console.error('Auto-sync failed:', e); }
}


// ═══════════════════════════════════════════════════════════════
//  Profile Bar (in-session)
// ═══════════════════════════════════════════════════════════════
async function populateProfileSelect() {
  const sel = el('profileSelect'); if (!sel) return;
  try {
    const res = await fetch('/api/profiles');
    const data = await res.json();
    sel.innerHTML = '<option value="">── 選擇已儲存的設定檔 ──</option>';
    (data.profiles || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.name;
      const badge = p.conn_type === 'serial' ? '[COM] ' : '';
      opt.textContent = `${badge}${p.name} (${p.host}:${p.port})`;
      sel.appendChild(opt);
    });
  } catch (e) { console.error(e); }
  updateProfileBtns();
}

function updateProfileBtns() {
  const val = el('profileSelect')?.value;
  if (el('profileLoadBtn'))   el('profileLoadBtn').disabled   = !val;
  if (el('profileDeleteBtn')) el('profileDeleteBtn').disabled = !val;
}

async function loadSelectedProfile() {
  const name = el('profileSelect')?.value; if (!name) return;
  await applyProfile(name);
}

async function deleteSelectedProfile() {
  const name = el('profileSelect')?.value; if (!name) return;
  await delProfile(name);
  await populateProfileSelect();
}

async function shutdownApp() {
  if (!confirm('確定要關閉 CommandWebGUI 應用程式？')) return;
  await fetch('/api/shutdown', { method: 'POST' }).catch(() => {});
  document.body.innerHTML = '<div style="display:flex;height:100vh;align-items:center;justify-content:center;font-family:monospace;color:#94a3b8;">CommandWebGUI 已關閉，可以關閉此分頁。</div>';
}
