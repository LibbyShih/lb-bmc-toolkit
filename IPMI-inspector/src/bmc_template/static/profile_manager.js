/**
 * Shared ProfileManager
 * Handles profile API calls and renders unified UI components.
 */

const SP_BAUD_RATES = [9600, 19200, 38400, 57600, 115200, 230400, 460800];

class ProfileManager {
  constructor(options = {}) {
    this.apiBase = options.apiBase || '/api';
    this.toolMode = options.toolMode || 'full'; // 'full' | 'ipmi'
    this.profiles = [];
    this.onConnect = options.onConnect || null;
    this.onDbOpened = options.onDbOpened || null;
    this.dbHandle = null;
    this.linkedDbLabel = null;
    this.metaDbPath = '';
    this._cardsContainerId = null;
    this._cardsOptions = null;
    this._bottomBarRendered = false;
    this._selectedProfileName = null;
    this._activeConnectBtn = null;
    this._collectProfileData = null;
    this._saveNewProfileWired = false;
  }

  /**
   * 公版 Connect 頁初始化：右側 Load Profiles + 卡片連線 + 左側儲存 Profile。
   */
  initConnectPage({ cardsId, onConnect, collectProfileData }) {
    this._collectProfileData = collectProfileData || null;
    this.onConnect = onConnect || null;
    this._wireSaveNewProfileBtn();
    return this.renderCards(cardsId, { onConnect });
  }

  async saveNewProfileFromForm(data) {
    const nameEl = document.getElementById('cpNewProfileName');
    const name = nameEl?.value.trim();
    if (!data?.host || !data?.user) throw new Error('請先填寫 Host 與 Username');
    if (!name) throw new Error('請輸入 Profile 名稱');
    await this.saveProfile({ name, ...data });
    if (nameEl) nameEl.value = '';
    if (this._cardsContainerId) {
      await this.renderCards(this._cardsContainerId, this._cardsOptions || {});
    }
  }

  resetActiveConnectBtn(label = '連線') {
    if (!this._activeConnectBtn) return;
    this._activeConnectBtn.textContent = label;
    this._activeConnectBtn.disabled = false;
    this._activeConnectBtn = null;
  }

  setActiveConnectLabel(text) {
    if (this._activeConnectBtn && text) this._activeConnectBtn.textContent = text;
  }

  _wireSaveNewProfileBtn() {
    const btn = document.getElementById('spSaveNewProfileBtn');
    if (!btn || this._saveNewProfileWired) return;
    this._saveNewProfileWired = true;
    btn.addEventListener('click', async () => {
      if (!this._collectProfileData) return;
      btn.disabled = true;
      const prev = btn.textContent;
      btn.textContent = '儲存中…';
      try {
        const data = this._collectProfileData();
        await this.saveNewProfileFromForm(data);
        if (typeof showConnectError === 'function') showConnectError('');
      } catch (e) {
        if (typeof showConnectError === 'function') showConnectError(e.message);
        else alert(e.message);
      } finally {
        btn.disabled = false;
        btn.textContent = prev;
      }
    });
  }

  // ── API ────────────────────────────────────────────────────────────────────

  async loadProfiles() {
    try {
      const res = await fetch(this.apiBase + '/profiles');
      const data = await res.json();
      this.profiles = data.profiles || [];
      return this.profiles;
    } catch (e) {
      console.error('Failed to load profiles:', e);
      return [];
    }
  }

  async fetchMeta() {
    try {
      const res = await fetch(this.apiBase + '/profiles/meta');
      if (!res.ok) return null;
      return await res.json();
    } catch (_) {
      return null;
    }
  }

  async updateDbSourceLabel() {
    const label = document.getElementById('spProfilesDb');
    if (!label) return;
    const meta = await this.fetchMeta();
    if (meta) {
      this.metaDbPath = meta.db_path || '';
      if (!this.linkedDbLabel) this.linkedDbLabel = meta.db_name || 'profiles.db';
    }
    const name = this.linkedDbLabel || meta?.db_name || 'profiles.db';
    const path = this.metaDbPath || meta?.db_path || '';
    label.textContent = path || name;
    label.title = path ? path : name;
  }

  getSelectedProfile() {
    if (!this._selectedProfileName) return null;
    return this.profiles.find(p => p.name === this._selectedProfileName) || null;
  }

  async saveProfile(profileData) {
    const res = await fetch(this.apiBase + '/profiles/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profileData)
    });
    const d = await res.json();
    if (this.dbHandle) await this.syncToFileSystem();
    return d;
  }

  async deleteProfile(name) {
    const res = await fetch(`${this.apiBase}/profiles/${encodeURIComponent(name)}`, {
      method: 'DELETE'
    });
    const d = await res.json();
    if (this.dbHandle) await this.syncToFileSystem();
    return d;
  }

  async importProfiles(file, replace = false) {
    const formData = new FormData();
    formData.append('file', file);
    const url = this.apiBase + '/profiles/import' + (replace ? '?replace=1' : '');
    const res = await fetch(url, { method: 'POST', body: formData });
    return res.json();
  }

  // ── File System Access ─────────────────────────────────────────────────────

  async syncToFileSystem() {
    if (!this.dbHandle) return;
    const res = await fetch(this.apiBase + '/profiles/export_all');
    const blob = await res.blob();
    const writable = await this.dbHandle.createWritable();
    await writable.write(blob);
    await writable.close();
  }

  async cmdOpenDb() {
    if (!window.showOpenFilePicker) {
      const input = document.createElement('input');
      input.type = 'file'; input.accept = '.db';
      input.onchange = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        try {
          const d = await this.importProfiles(file, true);
          if (!d.ok) throw new Error(d.error || '匯入失敗');
          this.linkedDbLabel = file.name;
          if (this.onDbOpened) this.onDbOpened(file.name);
          await this._refreshAll();
        } catch (err) { alert(err.message); }
      };
      input.click();
      return;
    }
    try {
      const [handle] = await window.showOpenFilePicker({
        types: [{ description: 'SQLite DB', accept: { 'application/x-sqlite3': ['.db'] } }]
      });
      this.dbHandle = handle;
      const file = await handle.getFile();
      const d = await this.importProfiles(file, true);
      if (!d.ok) throw new Error(d.error || '匯入失敗');
      this.linkedDbLabel = handle.name;
      if (this.onDbOpened) this.onDbOpened(file.name);
      await this._refreshAll();
    } catch (e) {
      if (e.name !== 'AbortError') alert(e.message);
    }
  }

  async cmdSaveAsDb() {
    if (!window.showSaveFilePicker) {
      window.location.href = this.apiBase + '/profiles/export_all';
      return;
    }
    try {
      const handle = await window.showSaveFilePicker({
        suggestedName: 'profiles.db',
        types: [{ description: 'SQLite DB', accept: { 'application/x-sqlite3': ['.db'] } }]
      });
      const res = await fetch(this.apiBase + '/profiles/export_all');
      if (!res.ok) throw new Error('匯出失敗');
      const blob = await res.blob();
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      this.dbHandle = handle;
      this.linkedDbLabel = handle.name;
      if (this.onDbOpened) this.onDbOpened(handle.name);
      await this.updateDbSourceLabel();
    } catch (e) {
      if (e.name !== 'AbortError') alert(e.message);
    }
  }

  async _refreshAll() {
    if (this._cardsContainerId) {
      await this.renderCards(this._cardsContainerId, this._cardsOptions || {});
    }
    if (this._bottomBarRendered) {
      await this.refreshBottomBar();
    }
  }

  // ── UI: Profile Cards ──────────────────────────────────────────────────────

  /**
   * Render profile cards into a container div.
   * Card body click selects profile (does not fill the connect form).
   * options.onConnect(profile) — 連線 button: connect with profile data
   */
  async renderCards(containerId, options = {}) {
    this._cardsContainerId = containerId;
    this._cardsOptions = options;

    const container = document.getElementById(containerId);
    if (!container) return;

    await this.loadProfiles();
    await this.updateDbSourceLabel();
    const { onConnect } = options;

    container.replaceChildren();
    this._selectedProfileName = null;
    this._activeConnectBtn = null;

    if (this.profiles.length === 0) {
      container.innerHTML = '<div class="sp-no-profiles">目前無 Profile</div>';
      return;
    }

    this.profiles.forEach(p => {
      const card = document.createElement('div');
      card.className = 'sp-profile-card';

      const connType  = p.conn_type || 'ssh';
      const isSerial  = connType === 'serial';
      const isIpmi    = this.toolMode === 'ipmi';
      const typeBadge = isIpmi ? 'IPMI' : (isSerial ? 'COM' : 'SSH');
      const sshPort   = _spResolveSshPort(p);
      const ipmiPort  = p.ipmi_port || 623;

      const hostLine = typeof formatConnHost === 'function'
        ? (isIpmi
          ? formatConnHost({ host: p.host, ipmi_port: ipmiPort, ipmi_only: true, user: p.user })
          : formatConnHost({ host: p.host, conn_type: connType, ssh_port: sshPort, user: p.user }))
        : (isIpmi
          ? `${p.host}:${ipmiPort}${p.user ? ' · ' + p.user : ''}`
          : `${p.host}:${sshPort}${p.user ? ' · ' + p.user : ''}`);

      card.innerHTML = `
        <div class="sp-card-top">
          <div class="sp-card-name">${_escHtml(p.name)}</div>
          <div class="sp-card-actions">
            ${onConnect ? '<button type="button" class="sp-card-btn sp-card-connect">連線</button>' : ''}
            <button type="button" class="sp-card-btn sp-card-edit">編輯</button>
            <button type="button" class="sp-card-btn sp-card-del">刪除</button>
          </div>
        </div>
        <div class="sp-card-meta">
          <span class="sp-card-type">${typeBadge}</span>
          <span class="sp-card-host">${_escHtml(hostLine)}</span>
        </div>
        <div class="sp-card-ports">${isIpmi || isSerial ? '' : `IPMI:${ipmiPort}`}</div>
      `;

      card.onclick = (e) => {
        if (e.target.closest('.sp-card-actions')) return;
        this._toggleCardSelection(card, p, container);
      };
      card.style.cursor = 'pointer';

      const connectBtn = card.querySelector('.sp-card-connect');
      if (connectBtn && onConnect) {
        connectBtn.onclick = async (e) => {
          e.stopPropagation();
          this._selectCard(card, p, container);
          this._activeConnectBtn = connectBtn;
          const prev = connectBtn.textContent;
          connectBtn.disabled = true;
          connectBtn.textContent = '測試中…';
          try {
            await Promise.resolve(onConnect(p));
          } catch (err) {
            if (typeof showConnectError === 'function') showConnectError(err);
            connectBtn.textContent = prev;
            connectBtn.disabled = false;
            this._activeConnectBtn = null;
          }
        };
      }

      card.querySelector('.sp-card-edit').onclick = (e) => {
        e.stopPropagation();
        this.openEditModal(p, async () => {
          this._selectedProfileName = null;
          await this.renderCards(containerId, options);
          await this.refreshBottomBar();
        });
      };

      card.querySelector('.sp-card-del').onclick = async (e) => {
        e.stopPropagation();
        if (!confirm(`刪除 profile "${p.name}"？`)) return;
        await this.deleteProfile(p.name);
        await this.renderCards(containerId, options);
        await this.refreshBottomBar();
      };

      container.appendChild(card);
    });
  }

  _selectCard(card, profile, container) {
    this._selectedProfileName = profile.name;
    container.querySelectorAll('.sp-profile-card').forEach(c => {
      c.classList.remove('sp-profile-card-selected');
    });
    card.classList.add('sp-profile-card-selected');
  }

  _toggleCardSelection(card, profile, container) {
    const deselect = this._selectedProfileName === profile.name;
    if (deselect) {
      this._selectedProfileName = null;
      card.classList.remove('sp-profile-card-selected');
    } else {
      this._selectCard(card, profile, container);
    }
  }

  // ── UI: Edit Modal ─────────────────────────────────────────────────────────

  /**
   * Open a modal to edit an existing profile.
   * onSave(updatedProfile) called after successful PUT.
   */
  openEditModal(profile, onSave) {
    const existing = document.getElementById('sp-edit-modal');
    if (existing) existing.remove();

    const isSsh    = (profile.conn_type || 'ssh') !== 'serial';
    const sshPort  = _spResolveSshPort(profile);
    const ipmiPort = profile.ipmi_port || 623;

    const modal = document.createElement('div');
    modal.id = 'sp-edit-modal';
    modal.className = 'sp-modal-overlay';
    modal.innerHTML = `
      <div class="sp-modal-box">
        <div class="sp-modal-title">✏️ 編輯 Profile</div>
        <div class="sp-modal-type">
          <button id="spEditBtnSsh"    class="${isSsh ? 'active' : ''}">SSH</button>
          <button id="spEditBtnSerial" class="${!isSsh ? 'active' : ''}">COM Port</button>
        </div>
        <input type="hidden" id="spEditConnType" value="${_escAttr(profile.conn_type || 'ssh')}">
        <label>名稱</label>
        <input id="spEditName" type="text" value="${_escAttr(profile.name || '')}">
        <div class="sp-modal-row">
          <div>
            <label>Host / COM Port</label>
            <input id="spEditHost" type="text" value="${_escAttr(profile.host || '')}">
          </div>
          <div>
            <label id="spEditLblSshPort">${isSsh ? 'SSH Port' : 'Baud Rate'}</label>
            <div id="spEditPortWrap">${_spEditPortFieldHtml(isSsh, sshPort)}</div>
          </div>
        </div>
        <div class="sp-modal-row">
          <div>
            <label>Username</label>
            <input id="spEditUser" type="text" value="${_escAttr(profile.user || '')}">
          </div>
          <div>
            <label>IPMI Port</label>
            <input id="spEditIpmiPort" type="number" value="${ipmiPort}">
          </div>
        </div>
        <div>
          <label>Password</label>
          <input id="spEditPass" type="password" value="${_escAttr(profile.password || '')}">
        </div>
        <div id="spEditError" class="sp-modal-error" style="display:none;"></div>
        <div class="sp-modal-actions">
          <button id="spEditCancel">取消</button>
          <button id="spEditSave" class="sp-btn-primary">儲存</button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);

    const setType = (type) => {
      const isSshType = type === 'ssh';
      const curVal = document.getElementById('spEditSshPort')?.value;
      document.getElementById('spEditConnType').value = type;
      document.getElementById('spEditBtnSsh').className    = isSshType ? 'active' : '';
      document.getElementById('spEditBtnSerial').className = !isSshType ? 'active' : '';
      document.getElementById('spEditLblSshPort').textContent = isSshType ? 'SSH Port' : 'Baud Rate';
      document.getElementById('spEditPortWrap').innerHTML =
        _spEditPortFieldHtml(isSshType, isSshType ? (curVal || 22) : (curVal || 115200));
    };

    document.getElementById('spEditBtnSsh').onclick    = () => setType('ssh');
    document.getElementById('spEditBtnSerial').onclick = () => setType('serial');
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    document.getElementById('spEditCancel').onclick = () => modal.remove();

    document.getElementById('spEditSave').onclick = async () => {
      const name     = document.getElementById('spEditName').value.trim();
      const host     = document.getElementById('spEditHost').value.trim();
      const sp       = parseInt(document.getElementById('spEditSshPort').value, 10) || 22;
      const ip       = parseInt(document.getElementById('spEditIpmiPort').value, 10) || 623;
      const user     = document.getElementById('spEditUser').value.trim();
      const password = document.getElementById('spEditPass').value;
      const connType = document.getElementById('spEditConnType').value;
      const errEl    = document.getElementById('spEditError');

      if (!name || !host || !user) {
        errEl.textContent = 'name、host、user 為必填';
        errEl.style.display = 'block';
        return;
      }

      try {
        const res = await fetch(
          `${this.apiBase}/profiles/${encodeURIComponent(profile.name)}`,
          {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, host, ssh_port: sp, ipmi_port: ip,
                                   user, password, conn_type: connType })
          }
        );
        const d = await res.json();
        if (!res.ok) throw new Error(d.error || '儲存失敗');
        modal.remove();
        if (onSave) await onSave({ name, host, ssh_port: sp, ipmi_port: ip,
                                   user, password, conn_type: connType });
      } catch (e) {
        errEl.textContent = e.message;
        errEl.style.display = 'block';
      }
    };
  }

  // ── UI: Bottom Fixed Bar ───────────────────────────────────────────────────

  /**
   * Render a fixed bottom bar with profile select, Connect, Delete, Open DB, Save DB.
   */
  renderBottomBar(containerId) {
    this._bottomBarRendered    = true;
    this._bottomBarContainerId = containerId;

    const container = document.getElementById(containerId);
    if (!container) return;

    container.innerHTML = `
      <div class="sp-profile-bar">
        <span class="sp-profile-label">📂 Profile</span>
        <select class="sp-profile-select" id="spBtmSelect">
          <option value="">── 選擇設定檔 ──</option>
        </select>
        <button class="sp-btn sp-btn-primary" id="spBtmConnect" disabled>連線</button>
        <button class="sp-btn"                id="spBtmDelete"  disabled>刪除</button>
        <button class="sp-btn" id="spBtmOpenDb" title="開啟 DB">📂</button>
        <button class="sp-btn" id="spBtmSaveDb" title="另存 DB">💾</button>
      </div>
    `;

    const select     = document.getElementById('spBtmSelect');
    const connectBtn = document.getElementById('spBtmConnect');
    const deleteBtn  = document.getElementById('spBtmDelete');

    select.onchange = () => {
      const has = !!select.value;
      connectBtn.disabled = !has;
      deleteBtn.disabled  = !has;
    };

    connectBtn.onclick = () => {
      const profile = this.profiles.find(p => p.name === select.value);
      if (profile && this.onConnect) this.onConnect(profile);
    };

    deleteBtn.onclick = async () => {
      const name = select.value;
      if (!name) return;
      if (!confirm(`刪除 profile "${name}"？`)) return;
      await this.deleteProfile(name);
      await this.refreshBottomBar();
    };

    document.getElementById('spBtmOpenDb').onclick = () => this.cmdOpenDb();
    document.getElementById('spBtmSaveDb').onclick = () => this.cmdSaveAsDb();

    this.refreshBottomBar();
  }

  async refreshBottomBar() {
    const select = document.getElementById('spBtmSelect');
    if (!select) return;

    await this.loadProfiles();
    const cur = select.value;
    select.innerHTML = '<option value="">── 選擇設定檔 ──</option>';
    this.profiles.forEach(p => {
      const sp  = _spResolveSshPort(p);
      const opt = document.createElement('option');
      opt.value       = p.name;
      opt.textContent = `${p.name} — ${p.host}  SSH:${sp}  IPMI:${p.ipmi_port || 623}`;
      select.appendChild(opt);
    });
    if (cur && this.profiles.find(p => p.name === cur)) select.value = cur;

    const connectBtn = document.getElementById('spBtmConnect');
    const deleteBtn  = document.getElementById('spBtmDelete');
    if (connectBtn) connectBtn.disabled = !select.value;
    if (deleteBtn)  deleteBtn.disabled  = !select.value;
  }

  // legacy alias
  async refreshSelect() { return this.refreshBottomBar(); }
}

// ── Helpers ────────────────────────────────────────────────────────────────

function _escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function _escAttr(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function _spResolveSshPort(profile) {
  if (profile.ssh_port != null && profile.ssh_port !== '') {
    return profile.ssh_port;
  }
  return (profile.conn_type || 'ssh') === 'serial' ? 115200 : 22;
}

function _spEditPortFieldHtml(isSsh, value) {
  const v = value || (isSsh ? 22 : 115200);
  if (isSsh) {
    return `<input id="spEditSshPort" type="number" value="${_escAttr(v)}" min="1" max="65535">`;
  }
  const opts = SP_BAUD_RATES.map(r => {
    const sel = String(r) === String(v) ? ' selected' : '';
    return `<option value="${r}"${sel}>${r}</option>`;
  }).join('');
  return `<select id="spEditSshPort">${opts}</select>`;
}

window.ProfileManager = ProfileManager;
window.SP_BAUD_RATES = SP_BAUD_RATES;
