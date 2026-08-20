/**
 * FigurinePro Neo-Brutalism WebUI Controller
 */
(function() {
  'use strict';

  // API Client with fallback
  let bridge = null;

  async function initBridge() {
    let attempts = 0;
    while (!window.AstrBotPluginPage && attempts < 20) {
      await new Promise(r => setTimeout(r, 100));
      attempts++;
    }
    if (window.AstrBotPluginPage) {
      await window.AstrBotPluginPage.ready();
      bridge = window.AstrBotPluginPage;
      console.log("[Neo-UI] AstrBot Bridge Connected!");
    } else {
      console.warn("[Neo-UI] AstrBot Bridge unavailable, running in standalone/fallback mode.");
    }
  }

  // Custom Modal Confirm (Replaces native window.confirm to support sandboxed iframe)
  let confirmResolve = null;
  function showConfirm(message, title = '⚠️ 确认操作') {
    return new Promise(resolve => {
      const modal = document.getElementById('customConfirmModal');
      const msgEl = document.getElementById('customConfirmMsg');
      const titleEl = document.getElementById('customConfirmTitle');
      if (!modal || !msgEl) {
        // Fallback
        resolve(true);
        return;
      }
      confirmResolve = resolve;
      titleEl.textContent = title;
      msgEl.textContent = message;
      modal.classList.add('open');
    });
  }

  // Toast Notification
  function showToast(msg, type = 'success') {
    let container = document.getElementById('toastContainer');
    if (!container) {
      container = document.createElement('div');
      container.id = 'toastContainer';
      container.className = 'toast-container';
      document.body.appendChild(container);
    }
    const toast = document.createElement('div');
    toast.className = `neo-toast ${type === 'error' ? 'error' : (type === 'info' ? 'info' : '')}`;
    toast.textContent = msg;
    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.2s';
      setTimeout(() => toast.remove(), 200);
    }, 3000);
  }

  // API Call Wrapper
  async function apiGet(endpoint, params = {}) {
    if (bridge && typeof bridge.apiGet === 'function') {
      try {
        const res = await bridge.apiGet(endpoint, params);
        return res?.data ?? res;
      } catch (err) {
        console.error(`[Bridge GET ${endpoint}]`, err);
        throw err;
      }
    }
    // Fallback direct fetch
    const url = new URL(`/api/v1/plugins/extensions/astrbot_plugin_shoubanhua/${endpoint}`, window.location.origin);
    Object.keys(params).forEach(k => url.searchParams.set(k, params[k]));
    const resp = await fetch(url);
    const json = await resp.json();
    if (json.status === 'error') throw new Error(json.message);
    return json.data ?? json;
  }

  async function apiPost(endpoint, body = {}) {
    if (bridge && typeof bridge.apiPost === 'function') {
      try {
        const res = await bridge.apiPost(endpoint, body);
        return res?.data ?? res;
      } catch (err) {
        console.error(`[Bridge POST ${endpoint}]`, err);
        throw err;
      }
    }
    const url = `/api/v1/plugins/extensions/astrbot_plugin_shoubanhua/${endpoint}`;
    const resp = await fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
    const json = await resp.json();
    if (json.status === 'error') throw new Error(json.message);
    return json.data ?? json;
  }

  // App State
  const state = {
    activeTab: 'overview',
    config: {},
    presets: [],
    keys: [],
    quotas: { users: [], groups: [] },
    generating: false,
    galleryPage: 1,
    galleryTotalPages: 1,
  };

  // Switch Tab
  function switchTab(tabId) {
    state.activeTab = tabId;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabId);
    });
    document.querySelectorAll('.tab-pane').forEach(pane => {
      pane.classList.toggle('active', pane.id === `tab-${tabId}`);
    });

    if (tabId === 'overview') {
      loadOverview();
      loadGallery(1);
    }
    if (tabId === 'persona') loadPersona();
    if (tabId === 'presets') loadPresets();
    if (tabId === 'config') loadConfig();
    if (tabId === 'providers') loadProviders();
    if (tabId === 'quota') loadQuota();
  }

  // 1. Overview Tab & Gallery
  async function loadOverview() {
    try {
      const data = await apiGet('status');
      document.getElementById('statTodayUsers').textContent = data.stats?.today_users || 0;
      document.getElementById('statTodayCalls').textContent = (data.stats?.today_user_calls || 0) + (data.stats?.today_group_calls || 0);
      document.getElementById('statTotalImages').textContent = data.storage?.file_count || 0;
      
      const sizeMb = data.storage?.size_mb || 0;
      const sizeGb = data.storage?.size_gb || 0;
      const maxGb = Number.isFinite(Number(data.max_gb)) ? Number(data.max_gb) : 5.0;
      document.getElementById('statStorageSize').textContent = `${sizeMb > 1024 ? sizeGb + ' GB' : sizeMb + ' MB'} / ${maxGb}GB`;
    } catch (e) {
      console.error('加载概览指标失败:', e);
    }
  }

  async function loadGallery(page = 1) {
    state.galleryPage = page;
    const grid = document.getElementById('galleryGrid');
    const loading = document.getElementById('galleryLoading');
    const empty = document.getElementById('galleryEmpty');
    const badge = document.getElementById('galleryCountBadge');
    const summary = document.getElementById('storageSummary');
    const pageIndicator = document.getElementById('pageIndicator');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');

    grid.innerHTML = '';
    loading.style.display = 'block';
    empty.style.display = 'none';

    try {
      const res = await apiGet('gallery', { page, page_size: 30 });
      loading.style.display = 'none';

      state.galleryTotalPages = res.total_pages || 1;
      badge.textContent = `${res.total || 0} 张`;
      pageIndicator.textContent = `第 ${res.page} / ${res.total_pages || 1} 页 (共 ${res.total} 张)`;

      const storage = res.storage || { size_mb: 0, size_gb: 0 };
      summary.textContent = `存储占用: ${storage.size_mb > 1024 ? storage.size_gb + ' GB' : storage.size_mb + ' MB'} / ${res.max_gb} GB (超限清理 ${intRatio(res.cleanup_ratio)}%)`;

      prevBtn.disabled = res.page <= 1;
      nextBtn.disabled = res.page >= res.total_pages;

      if (!res.items || res.items.length === 0) {
        empty.style.display = 'block';
        return;
      }

      res.items.forEach(item => {
        const card = document.createElement('div');
        card.className = 'neo-box';
        card.style.padding = '8px';
        card.style.display = 'flex';
        card.style.flexDirection = 'column';
        card.style.background = '#fff';

        const rawUid = String(item.uid || '');
        const legacyGroupMatch = !item.gid ? rawUid.match(/^[^:]+:GroupMessage:(.+)$/) : null;
        const displayGid = item.gid || legacyGroupMatch?.[1] || '';
        const displayUid = legacyGroupMatch ? '未知用户' : rawUid;
        const userTag = displayGid ? `群 ${displayGid} · ${displayUid}` : `私聊 · ${displayUid}`;
        const previewItem = { ...item, displayGid, displayUid, userTag };

        card.innerHTML = `
          <div style="position: relative; width: 100%; aspect-ratio: 1; overflow: hidden; border: 2px solid #000; background: #eee; margin-bottom: 8px;">
            <img
              loading="lazy"
              src="${item.url}"
              alt="${item.preset || '手办化'}生成图片"
              style="width: 100%; height: 100%; object-fit: cover; cursor: pointer; transition: transform 0.2s;"
            />
            <span class="neo-badge pink" style="position: absolute; top: 4px; left: 4px; font-size: 10px; padding: 1px 4px;">
              ${item.preset || '自定义'}
            </span>
            <button
              type="button"
              title="删除此张图片"
              aria-label="删除图片 ${item.filename || ''}"
              style="position: absolute; top: 4px; right: 4px; background: rgba(0,0,0,0.7); color: #fff; border: 1px solid #000; border-radius: 4px; cursor: pointer; font-size: 11px; padding: 2px 5px;">
              🗑️
            </button>
          </div>
          <div style="font-size: 11px; font-weight: 800; color: #111; margin-bottom: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${item.uid}">
            👤 <strong>${userTag}</strong>
          </div>
          <div style="font-size: 11px; line-height: 1.3; color: #444; margin-bottom: 6px; height: 28px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical;" title="${item.prompt}">
            💬 ${item.prompt || '(无提示词)'}
          </div>
          <div style="margin-top: auto; display: flex; justify-content: space-between; align-items: center; border-top: 1px dashed #000; padding-top: 4px; font-size: 10px; color: #666; font-weight: 700;">
            <span>${item.time ? item.time.slice(5, 16) : ''}</span>
            <span>${item.size_kb} KB</span>
          </div>
        `;

        const image = card.querySelector('img');
        const deleteButton = card.querySelector('button');
        image?.addEventListener('click', () => openImagePreview({ kind: 'gallery', item: previewItem }, image));
        image?.setAttribute('tabindex', '0');
        image?.setAttribute('role', 'button');
        image?.setAttribute('aria-label', '查看图片与完整生成信息');
        image?.addEventListener('keydown', (event) => {
          if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            openImagePreview({ kind: 'gallery', item: previewItem }, image);
          }
        });
        image?.addEventListener('error', () => {
          image.src = "data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='100' height='100'><rect fill='%23eee' width='100' height='100'/><text x='50%' y='50%' dominant-baseline='middle' text-anchor='middle' font-size='12'>已清理</text></svg>";
        }, { once: true });
        deleteButton?.addEventListener('click', (event) => {
          event.stopPropagation();
          window.deleteSingleImage(item.filename);
        });
        grid.appendChild(card);
      });
    } catch (e) {
      loading.style.display = 'none';
      empty.style.display = 'block';
      showToast('获取图片画廊失败: ' + e.message, 'error');
    }
  }

  function intRatio(ratio) {
    return Math.round((parseFloat(ratio) || 0.5) * 100);
  }

  let currentLightboxReqId = 0;
  let activePreview = null;
  let lightboxReturnFocus = null;

  function setMetaRows(container, rows) {
    if (!container) return;
    container.innerHTML = '';
    rows.filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '').forEach(([label, value]) => {
      const term = document.createElement('dt');
      const detail = document.createElement('dd');
      term.textContent = label;
      detail.textContent = String(value);
      container.append(term, detail);
    });
  }

  function getLightboxFocusableElements() {
    const modal = document.getElementById('imageLightboxModal');
    if (!modal) return [];
    return [...modal.querySelectorAll('button:not([disabled]), [href], input:not([disabled]), [tabindex]:not([tabindex="-1"])')]
      .filter(element => element.offsetParent !== null);
  }

  function closeImagePreview() {
    const modal = document.getElementById('imageLightboxModal');
    if (!modal?.classList.contains('open')) return;

    currentLightboxReqId++;
    modal.classList.remove('open');
    modal.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('preview-open');
    activePreview = null;

    const returnFocus = lightboxReturnFocus;
    lightboxReturnFocus = null;
    if (returnFocus && typeof returnFocus.focus === 'function' && document.contains(returnFocus)) {
      returnFocus.focus();
    }
  }

  async function loadPreviewRawImage(filename, requestId) {
    const img = document.getElementById('lightboxImg');
    const spinner = document.getElementById('lightboxSpinner');
    if (!filename || !img) return;

    try {
      const res = await apiGet('gallery/raw', { filename });
      if (requestId !== currentLightboxReqId || !res?.data_uri) return;

      const fullImg = new Image();
      fullImg.onload = () => {
        if (requestId !== currentLightboxReqId) return;
        img.src = res.data_uri;
        img.style.filter = 'none';
        img.style.opacity = '1';
        if (spinner) spinner.style.display = 'none';
      };
      fullImg.onerror = () => {
        if (requestId !== currentLightboxReqId) return;
        img.style.filter = 'none';
        img.style.opacity = '1';
        if (spinner) spinner.style.display = 'none';
      };
      fullImg.src = res.data_uri;
    } catch (e) {
      console.warn('加载高清原图失败，使用缩略图显示:', e);
      if (requestId === currentLightboxReqId) {
        img.style.filter = 'none';
        img.style.opacity = '1';
        if (spinner) spinner.style.display = 'none';
      }
    }
  }

  function openImagePreview(preview, triggerElement = null) {
    const modal = document.getElementById('imageLightboxModal');
    const img = document.getElementById('lightboxImg');
    const title = document.getElementById('lightboxTitle');
    const caption = document.getElementById('lightboxCaption');
    const prompt = document.getElementById('lightboxPrompt');
    const typeBadge = document.getElementById('lightboxTypeBadge');
    const spinner = document.getElementById('lightboxSpinner');
    const generationMeta = document.getElementById('lightboxGenerationMeta');
    const fileMeta = document.getElementById('lightboxFileMeta');
    const copyButton = document.getElementById('lightboxCopyPromptBtn');
    const deleteButton = document.getElementById('lightboxDeleteBtn');
    if (!modal || !img || !preview) return;

    currentLightboxReqId++;
    const requestId = currentLightboxReqId;
    activePreview = preview;
    lightboxReturnFocus = triggerElement || document.activeElement;

    if (preview.kind === 'gallery') {
      const item = preview.item || {};
      const fullPrompt = String(item.prompt || '');
      const titleText = item.preset ? `${item.preset} · 生成图片` : '手办化生成图片';
      const originText = item.userTag || (item.gid ? `群 ${item.gid} · ${item.uid || '未知用户'}` : `私聊 · ${item.uid || '未知用户'}`);

      if (typeBadge) typeBadge.textContent = 'GALLERY';
      if (title) title.textContent = titleText;
      if (caption) caption.textContent = originText;
      if (prompt) prompt.textContent = fullPrompt || '暂无提示词';
      if (copyButton) copyButton.style.display = fullPrompt ? '' : 'none';
      if (deleteButton) deleteButton.style.display = item.filename ? '' : 'none';

      setMetaRows(generationMeta, [
        ['会话来源', item.displayGid || item.gid ? '群聊' : '私聊'],
        ['用户 ID', item.displayUid || item.uid || '未知用户'],
        ['群 ID', item.displayGid || item.gid || '—'],
        ['预设', item.preset || '自定义'],
        ['模型', item.model || '未记录'],
        ['生成时间', item.time || '未记录'],
      ]);
      setMetaRows(fileMeta, [
        ['文件名', item.filename || '未记录'],
        ['文件大小', Number.isFinite(Number(item.size_kb)) ? `${item.size_kb} KB` : '未记录'],
        ['记录 ID', item.id || '未记录'],
      ]);

      img.src = item.url || '';
      img.alt = `${titleText}，${originText}`;
      img.style.filter = item.url ? 'blur(4px)' : 'none';
      img.style.opacity = item.url ? '0.92' : '1';
      if (spinner) spinner.style.display = item.filename ? 'flex' : 'none';
      if (item.filename) loadPreviewRawImage(item.filename, requestId);
    } else {
      const item = preview.item || {};
      if (typeBadge) typeBadge.textContent = 'PERSONA';
      if (title) title.textContent = preview.title || '人设参考照片';
      if (caption) caption.textContent = 'Persona Reference · 人设参考图';
      if (prompt) prompt.textContent = '该图片为人设参考照片，不包含生成提示词。';
      if (copyButton) copyButton.style.display = 'none';
      if (deleteButton) deleteButton.style.display = 'none';
      setMetaRows(generationMeta, [
        ['类型', '人设参考照片'],
        ['序号', preview.index !== undefined ? `#${preview.index + 1}` : '—'],
      ]);
      setMetaRows(fileMeta, [
        ['文件大小', Number.isFinite(Number(item.size_kb)) ? `${item.size_kb} KB` : '未记录'],
      ]);
      img.src = item.url || '';
      img.alt = preview.title || '人设参考照片';
      img.style.filter = 'none';
      img.style.opacity = '1';
      if (spinner) spinner.style.display = 'none';
    }

    modal.classList.add('open');
    modal.setAttribute('aria-hidden', 'false');
    document.body.classList.add('preview-open');
    requestAnimationFrame(() => document.getElementById('closeLightboxBtn')?.focus());
  }

  async function copyPreviewPrompt() {
    const text = activePreview?.kind === 'gallery' ? String(activePreview.item?.prompt || '') : '';
    if (!text) return;

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      } else {
        const textarea = document.createElement('textarea');
        textarea.value = text;
        textarea.style.position = 'fixed';
        textarea.style.opacity = '0';
        document.body.appendChild(textarea);
        textarea.select();
        document.execCommand('copy');
        textarea.remove();
      }
      showToast('完整提示词已复制');
    } catch (e) {
      showToast('复制失败，请手动选择提示词', 'error');
    }
  }

  window.previewImage = function(filename, thumbUrl = '', caption = '') {
    openImagePreview({
      kind: 'gallery',
      item: {
        filename,
        url: thumbUrl,
        prompt: '',
        preset: caption || '手办化',
        userTag: caption,
      }
    });
  };

  window.deleteSingleImage = async function(filename) {
    const ok = await showConfirm(`确定删除此张生成图片 (${filename}) 吗？`, '🗑️ 删除图片');
    if (!ok) return;
    try {
      await apiPost('gallery/delete', { filename });
      showToast('图片已删除');
      loadOverview();
      loadGallery(state.galleryPage);
      return true;
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
      return false;
    }
  };

  async function handleManualCleanupRatio(ratio, label) {
    const ok = await showConfirm(`确定立即${label}吗？\n注意：清理后图片将从磁盘永久移除。`, '🧹 存储清理');
    if (!ok) return;
    try {
      const res = await apiPost('gallery/cleanup', { ratio });
      showToast(res.message || '清理完成！');
      loadOverview();
      loadGallery(1);
    } catch (e) {
      showToast('清理失败: ' + e.message, 'error');
    }
  }

  // 2. Presets Tab
  async function loadPresets() {
    try {
      const res = await apiGet('presets');
      state.presets = res.presets || [];
      renderPresets();
    } catch (e) {
      showToast('获取预设失败: ' + e.message, 'error');
    }
  }

  function renderPresets() {
    const grid = document.getElementById('presetsGrid');
    const filter = document.getElementById('presetSearch').value.toLowerCase().trim();
    grid.innerHTML = '';

    const filtered = state.presets.filter(p => p.name.toLowerCase().includes(filter));

    if (filtered.length === 0) {
      grid.innerHTML = '<div class="neo-box" style="grid-column: 1/-1; text-align: center;">没有找到匹配的预设</div>';
      return;
    }

    filtered.forEach(p => {
      const card = document.createElement('div');
      card.className = 'preset-card';
      card.innerHTML = `
        <div>
          <div class="preset-header">
            <span class="preset-title">${p.name}</span>
            <span class="neo-badge ${p.is_builtin ? 'cyan' : 'pink'}">${p.is_builtin ? '内置' : '自定义'}</span>
          </div>
          <div class="preset-prompt" title="${p.prompt}">${p.prompt}</div>
        </div>
        <div class="preset-actions">
          <button class="neo-btn white" style="padding: 4px 8px; font-size: 11px;" onclick="window.useInStudio('${p.name}')">🎨 调试</button>
          ${!p.is_builtin ? `
            <button class="neo-btn white" style="padding: 4px 8px; font-size: 11px;" onclick="window.editPreset('${p.name}', \`${p.prompt.replace(/`/g, '\\`')}\`)">✏️ 编辑</button>
            <button class="neo-btn pink" style="padding: 4px 8px; font-size: 11px;" onclick="window.deletePreset('${p.name}')">🗑️ 删除</button>
          ` : ''}
        </div>
      `;
      grid.appendChild(card);
    });
  }

  // 3. Config Tab
  async function loadConfig() {
    try {
      const res = await apiGet('config');
      state.config = res.config || {};
      
      // Fill Form
      const c = state.config;
      document.getElementById('cfgInterfaceMode').value = c.interface_mode || 'openai_image';
      document.getElementById('cfgBaseUrl').value = c.base_url || '';
      document.getElementById('cfgModel').value = c.model || 'nano-banana';
      document.getElementById('cfgT2IModel').value = c.text_to_image_model || '';
      document.getElementById('cfgResolution').value = c.image_resolution || '1K';
      document.getElementById('cfgAspectRatio').value = c.image_aspect_ratio || '4:3';
      document.getElementById('cfgTimeout').value = c.timeout || 120;
      document.getElementById('cfgStorageMaxGB').value = c.image_storage_max_gb || 5.0;
      document.getElementById('cfgCleanupRatio').value = String(c.image_cleanup_ratio || 0.5);
      document.getElementById('cfgLuxuryMode').checked = !!c.enable_luxury_mode;
      document.getElementById('cfgRebellious').checked = !!c.enable_rebellious_mode;
      document.getElementById('cfgLLMAutoDetect').checked = !!c.enable_llm_auto_detect;
      document.getElementById('cfgUserLimit').checked = !!c.enable_user_limit;
      document.getElementById('cfgCheckin').checked = !!c.enable_checkin;
      document.getElementById('cfgHelpText').value = c.help_text || '';

      // Fill API Keys
      const rawKeys = c.api_keys || '';
      let keysStr = '';
      let count = 0;
      if (Array.isArray(rawKeys)) {
        keysStr = rawKeys.join('\n');
        count = rawKeys.length;
      } else if (typeof rawKeys === 'string') {
        keysStr = rawKeys;
        count = rawKeys.split('\n').filter(k => k.trim()).length;
      }
      document.getElementById('keysRawTextarea').value = keysStr;
      const countBadge = document.getElementById('configKeyCountBadge');
      if (countBadge) countBadge.textContent = `${count} 个 Key`;
    } catch (e) {
      showToast('加载配置失败: ' + e.message, 'error');
    }
  }

  async function saveConfig() {
    try {
      const keysText = document.getElementById('keysRawTextarea').value;
      const keysList = keysText.split('\n').map(k => k.trim()).filter(Boolean);

      const payload = {
        config: {
          interface_mode: document.getElementById('cfgInterfaceMode').value,
          base_url: document.getElementById('cfgBaseUrl').value.trim(),
          api_keys: keysList.join('\n'),
          model: document.getElementById('cfgModel').value.trim(),
          text_to_image_model: document.getElementById('cfgT2IModel').value.trim(),
          image_resolution: document.getElementById('cfgResolution').value,
          image_aspect_ratio: document.getElementById('cfgAspectRatio').value,
          timeout: parseInt(document.getElementById('cfgTimeout').value) || 120,
          image_storage_max_gb: parseFloat(document.getElementById('cfgStorageMaxGB').value) || 5.0,
          image_cleanup_ratio: parseFloat(document.getElementById('cfgCleanupRatio').value) || 0.5,
          enable_luxury_mode: document.getElementById('cfgLuxuryMode').checked,
          enable_rebellious_mode: document.getElementById('cfgRebellious').checked,
          enable_llm_auto_detect: document.getElementById('cfgLLMAutoDetect').checked,
          enable_user_limit: document.getElementById('cfgUserLimit').checked,
          enable_checkin: document.getElementById('cfgCheckin').checked,
          help_text: document.getElementById('cfgHelpText').value,
        }
      };

      await apiPost('config/save', payload);
      showToast('🎉 配置与 Key 池已成功保存并热重载！');
      loadConfig();
    } catch (e) {
      showToast('保存配置失败: ' + e.message, 'error');
    }
  }

  // 3.5 Providers Tab (Multi-Provider Management)
  let backupProvidersList = [];

  function renderBackupProviders() {
    const container = document.getElementById('backupProvidersContainer');
    if (!container) return;
    container.innerHTML = '';

    if (backupProvidersList.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 24px; border: 2px dashed #000; font-weight: 700; background: #fff;">
          当前未配置任何备用供应商。当主供应商发生网络故障或限额时将直接报错。点击上方按钮可添加备用供应商。
        </div>
      `;
      return;
    }

    backupProvidersList.forEach((p, idx) => {
      const card = document.createElement('div');
      card.className = 'neo-box';
      card.style.background = p.enabled !== false ? '#fff' : '#f0f0f0';
      card.style.position = 'relative';
      card.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #000; padding-bottom: 8px; margin-bottom: 12px;">
          <div style="font-weight: 900; font-size: 14px; display: flex; align-items: center; gap: 8px;">
            <span class="neo-badge purple">备用 #${idx + 1}</span>
            <span>${p.name || '未命名备用供应商'}</span>
          </div>
          <div style="display: flex; gap: 8px; align-items: center;">
            <label style="font-size: 12px; font-weight: 700; display: flex; align-items: center; gap: 4px;">
              <input type="checkbox" class="provider-enabled" data-idx="${idx}" ${p.enabled !== false ? 'checked' : ''} />
              启用
            </label>
            <button class="neo-btn pink" style="padding: 2px 8px; font-size: 11px;" onclick="window.removeBackupProvider(${idx})">🗑️ 删除</button>
          </div>
        </div>

        <div class="grid-2" style="margin-bottom: 12px;">
          <div class="form-group">
            <label class="form-label">供应商名称 / 备注</label>
            <input class="form-input provider-name" data-idx="${idx}" value="${p.name || ''}" placeholder="如：备用站-Gemini直连" />
          </div>
          <div class="form-group">
            <label class="form-label">接口模式</label>
            <select class="form-select provider-mode" data-idx="${idx}">
              <option value="openai_image" ${p.interface_mode === 'openai_image' ? 'selected' : ''}>openai_image (DALL-E 格式)</option>
              <option value="openai_chat" ${p.interface_mode === 'openai_chat' ? 'selected' : ''}>openai_chat (Chat 生图)</option>
              <option value="gemini_official" ${p.interface_mode === 'gemini_official' ? 'selected' : ''}>gemini_official (Google Gemini 原生)</option>
              <option value="custom_endpoint" ${p.interface_mode === 'custom_endpoint' ? 'selected' : ''}>custom_endpoint (自定义完整端点)</option>
            </select>
          </div>
        </div>

        <div class="grid-2" style="margin-bottom: 12px;">
          <div class="form-group">
            <label class="form-label">接口地址 (Base URL)</label>
            <input class="form-input provider-base" data-idx="${idx}" value="${p.base_url || ''}" placeholder="https://api.backup-service.com" />
          </div>
          <div class="form-group">
            <label class="form-label">指定模型 (留空则沿用主配置)</label>
            <input class="form-input provider-model" data-idx="${idx}" value="${p.model || ''}" placeholder="如：gemini-2.5-flash-image" />
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">专属 API Key(s) (每行一个或逗号隔开)</label>
          <textarea class="form-textarea provider-keys" data-idx="${idx}" style="min-height: 60px; font-family: monospace;" placeholder="sk-xxxx">${Array.isArray(p.api_keys) ? p.api_keys.join('\n') : (p.api_keys || '')}</textarea>
        </div>
      `;
      container.appendChild(card);
    });

    // 绑定内部输入更新
    container.querySelectorAll('.provider-name').forEach(el => el.addEventListener('input', e => backupProvidersList[e.target.dataset.idx].name = e.target.value));
    container.querySelectorAll('.provider-mode').forEach(el => el.addEventListener('change', e => backupProvidersList[e.target.dataset.idx].interface_mode = e.target.value));
    container.querySelectorAll('.provider-base').forEach(el => el.addEventListener('input', e => backupProvidersList[e.target.dataset.idx].base_url = e.target.value));
    container.querySelectorAll('.provider-model').forEach(el => el.addEventListener('input', e => backupProvidersList[e.target.dataset.idx].model = e.target.value));
    container.querySelectorAll('.provider-keys').forEach(el => el.addEventListener('input', e => backupProvidersList[e.target.dataset.idx].api_keys = e.target.value));
    container.querySelectorAll('.provider-enabled').forEach(el => el.addEventListener('change', e => backupProvidersList[e.target.dataset.idx].enabled = e.target.checked));
  }

  async function loadProviders() {
    try {
      const res = await apiGet('config');
      const conf = res.config || {};
      backupProvidersList = Array.isArray(conf.backup_providers) ? JSON.parse(JSON.stringify(conf.backup_providers)) : [];
      const thresholdSelect = document.getElementById('cfgFailoverThreshold');
      if (thresholdSelect) {
        thresholdSelect.value = String(conf.provider_failover_threshold || 1);
      }
      renderBackupProviders();
    } catch (e) {
      showToast('加载供应商配置失败: ' + e.message, 'error');
    }
  }

  function addBackupProviderItem() {
    backupProvidersList.push({
      name: `备用供应商 ${backupProvidersList.length + 1}`,
      interface_mode: 'openai_image',
      base_url: '',
      model: '',
      api_keys: '',
      enabled: true
    });
    renderBackupProviders();
  }

  window.removeBackupProvider = function(idx) {
    backupProvidersList.splice(idx, 1);
    renderBackupProviders();
  };

  async function saveProviders() {
    try {
      const thresholdVal = parseInt(document.getElementById('cfgFailoverThreshold').value) || 1;
      const payload = {
        config: {
          provider_failover_threshold: thresholdVal,
          backup_providers: backupProvidersList
        }
      };
      await apiPost('config/save', payload);
      showToast('🎉 供应商与故障转移设置保存成功！');
      loadProviders();
    } catch (e) {
      showToast('保存供应商配置失败: ' + e.message, 'error');
    }
  }

  // 2.5 Persona Tab (Character Photos & Selfies)
  let personaState = {
    ref_images: []
  };

  async function loadPersona() {
    try {
      const res = await apiGet('persona/config');
      const data = res || {};
      
      document.getElementById('personaEnable').checked = data.enable_persona_mode !== false;
      document.getElementById('personaName').value = data.persona_name || '';
      document.getElementById('personaDesc').value = data.persona_description || '';
      document.getElementById('personaStyle').value = data.persona_photo_style || '';
      
      const kws = data.persona_trigger_keywords;
      document.getElementById('personaKeywords').value = Array.isArray(kws) ? kws.join(', ') : (kws || '');
      
      const scenes = data.persona_scene_prompts;
      document.getElementById('personaScenes').value = Array.isArray(scenes) ? scenes.join('\n') : (scenes || '');

      personaState.ref_images = data.ref_images || [];
      renderPersonaPhotos();
    } catch (e) {
      showToast('加载人设配置失败: ' + e.message, 'error');
    }
  }

  function renderPersonaPhotos() {
    const grid = document.getElementById('personaPhotosGrid');
    const empty = document.getElementById('personaEmpty');
    const badge = document.getElementById('personaRefBadge');
    if (!grid) return;

    badge.textContent = `${personaState.ref_images.length} 张`;
    grid.innerHTML = '';

    if (personaState.ref_images.length === 0) {
      empty.style.display = 'block';
      grid.style.display = 'none';
      return;
    }

    empty.style.display = 'none';
    grid.style.display = 'grid';

    personaState.ref_images.forEach((img, idx) => {
      const card = document.createElement('div');
      card.style.position = 'relative';
      card.style.border = '2px solid #000';
      card.style.borderRadius = '4px';
      card.style.overflow = 'hidden';
      card.style.background = '#fff';
      card.style.boxShadow = '2px 2px 0px #000';

      const mediaButton = document.createElement('button');
      mediaButton.type = 'button';
      mediaButton.style.cssText = 'display:block; width:100%; padding:0; border:0; aspect-ratio:1; overflow:hidden; background:#eee; cursor:pointer;';
      mediaButton.setAttribute('aria-label', `查看人设参考照片 #${idx + 1}`);

      const photo = document.createElement('img');
      photo.src = img.url;
      photo.alt = `人设参考图 #${idx + 1}`;
      photo.style.cssText = 'width:100%; height:100%; object-fit:cover; display:block;';
      mediaButton.appendChild(photo);
      mediaButton.addEventListener('click', () => openImagePreview({
        kind: 'persona',
        item: img,
        index: idx,
        title: `人设参考照片 #${idx + 1}`,
      }, mediaButton));

      const footer = document.createElement('div');
      footer.style.cssText = 'padding:6px; display:flex; justify-content:space-between; align-items:center; background:#fff; border-top:2px solid #000;';

      const label = document.createElement('span');
      label.style.cssText = 'font-size:11px; font-weight:800;';
      label.textContent = `#${idx + 1} (${img.size_kb || 0}KB)`;

      const deleteButton = document.createElement('button');
      deleteButton.type = 'button';
      deleteButton.className = 'neo-btn pink';
      deleteButton.style.cssText = 'padding:2px 6px; font-size:10px;';
      deleteButton.setAttribute('aria-label', `删除人设参考照片 #${idx + 1}`);
      deleteButton.textContent = '🗑️';
      deleteButton.addEventListener('click', () => window.deletePersonaPhoto(idx));

      footer.append(label, deleteButton);
      card.append(mediaButton, footer);
      grid.appendChild(card);
    });
  }

  window.viewPersonaPhoto = function(idx) {
    const item = personaState.ref_images[idx];
    if (item?.url) {
      openImagePreview({
        kind: 'persona',
        item,
        index: idx,
        title: `人设参考照片 #${idx + 1}`,
      }, document.activeElement);
    }
  };

  window.deletePersonaPhoto = async function(idx) {
    const ok = await showConfirm(`确定要删除这张人设参考照片 #${idx + 1} 吗？`, '🗑️ 删除人设参考图');
    if (!ok) return;

    try {
      await apiPost('persona/delete_ref', { index: idx });
      showToast('人设参考照片已删除！');
      loadPersona();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  };

  async function handlePersonaFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = async () => {
      const b64 = reader.result;
      try {
        showToast('正在上传人设参考图...');
        await apiPost('persona/upload_ref', { image_base64: b64 });
        showToast('🎉 人设参考照片上传成功！');
        loadPersona();
      } catch (err) {
        showToast('上传失败: ' + err.message, 'error');
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  }

  async function savePersonaConfig() {
    try {
      const kwsRaw = document.getElementById('personaKeywords').value;
      const kwsList = kwsRaw.split(/[,，\n]/).map(s => s.trim()).filter(Boolean);

      const scenesRaw = document.getElementById('personaScenes').value;
      const scenesList = scenesRaw.split('\n').map(s => s.trim()).filter(Boolean);

      const payload = {
        enable_persona_mode: document.getElementById('personaEnable').checked,
        persona_name: document.getElementById('personaName').value.trim(),
        persona_description: document.getElementById('personaDesc').value.trim(),
        persona_photo_style: document.getElementById('personaStyle').value.trim(),
        persona_trigger_keywords: kwsList,
        persona_scene_prompts: scenesList
      };

      await apiPost('persona/save', payload);
      showToast('🎉 人设写真配置已成功保存！');
    } catch (e) {
      showToast('保存人设配置失败: ' + e.message, 'error');
    }
  }

  // 5. Quota Tab
  async function loadQuota() {
    try {
      const res = await apiGet('quota/list');
      state.quotas = res || { users: [], groups: [] };

      const userBody = document.getElementById('userQuotaTableBody');
      userBody.innerHTML = '';
      (res.users || []).forEach(u => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${u.id}</strong></td>
          <td><span class="neo-badge green">${u.quota} 次</span></td>
          <td>${u.today_calls} 次</td>
          <td>
            <button class="neo-btn cyan" style="padding:2px 6px;font-size:11px;" onclick="window.modifyQuota('user', '${u.id}', 10)">+10</button>
            <button class="neo-btn white" style="padding:2px 6px;font-size:11px;" onclick="window.modifyQuota('user', '${u.id}', 50)">+50</button>
          </td>
        `;
        userBody.appendChild(tr);
      });

      const groupBody = document.getElementById('groupQuotaTableBody');
      groupBody.innerHTML = '';
      (res.groups || []).forEach(g => {
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td><strong>${g.id}</strong></td>
          <td><span class="neo-badge purple">${g.quota} 次</span></td>
          <td>${g.today_calls} 次</td>
          <td>
            <button class="neo-btn cyan" style="padding:2px 6px;font-size:11px;" onclick="window.modifyQuota('group', '${g.id}', 50)">+50</button>
          </td>
        `;
        groupBody.appendChild(tr);
      });
    } catch (e) {
      showToast('获取配额统计失败: ' + e.message, 'error');
    }
  }

  // 6. Studio Generate
  let uploadedImageB64 = "";

  async function handleImageUpload(e) {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = function(evt) {
      uploadedImageB64 = evt.target.result;
      document.getElementById('studioInputPreview').src = uploadedImageB64;
      document.getElementById('studioInputPreview').style.display = 'block';
      document.getElementById('studioUploadLabel').textContent = `已选: ${file.name}`;
    };
    reader.readAsDataURL(file);
  }

  async function runStudioGenerate() {
    if (state.generating) return;
    const prompt = document.getElementById('studioPrompt').value.trim();
    const preset = document.getElementById('studioPresetSelect').value;
    const customModel = document.getElementById('studioModelInput').value.trim();

    if (!prompt && !preset) {
      showToast('请输入提示词或选择预设！', 'error');
      return;
    }

    state.generating = true;
    const genBtn = document.getElementById('studioGenBtn');
    genBtn.disabled = true;
    genBtn.innerHTML = '⚡ 正在生成中...';
    document.getElementById('stageLoading').style.display = 'flex';
    document.getElementById('stageEmpty').style.display = 'none';
    document.getElementById('stageResult').style.display = 'none';

    try {
      const res = await apiPost('generate', {
        prompt,
        preset,
        model: customModel,
        image_base64: uploadedImageB64
      });

      if (res && res.image) {
        document.getElementById('stageResultImg').src = res.image;
        document.getElementById('stageResultMeta').textContent = `模型: ${res.model} | 耗时: ${res.elapsed}s | 预设: ${res.preset || '自定义'}`;
        document.getElementById('stageResult').style.display = 'block';
        showToast(`生图完成！耗时 ${res.elapsed}s`);
      }
    } catch (e) {
      showToast('生图失败: ' + e.message, 'error');
      document.getElementById('stageEmpty').style.display = 'flex';
    } finally {
      state.generating = false;
      genBtn.disabled = false;
      genBtn.innerHTML = '⚡ 立即生成图片 (Ctrl+Enter)';
      document.getElementById('stageLoading').style.display = 'none';
    }
  }

  // Global window functions for event handlers
  window.useInStudio = function(presetName) {
    switchTab('studio');
    document.getElementById('studioPresetSelect').value = presetName;
  };

  window.editPreset = function(name, prompt) {
    document.getElementById('modalPresetName').value = name;
    document.getElementById('modalPresetPrompt').value = prompt;
    document.getElementById('presetModalTitle').textContent = '编辑自定义预设';
    document.getElementById('presetModal').classList.add('open');
  };

  window.deletePreset = async function(name) {
    const ok = await showConfirm(`确定删除自定义预设 [${name}] 吗？`, '🗑️ 删除预设');
    if (!ok) return;
    try {
      await apiPost('presets/delete', { name });
      showToast(`预设 [${name}] 已删除`);
      loadPresets();
    } catch (e) {
      showToast('删除失败: ' + e.message, 'error');
    }
  };

  window.modifyQuota = async function(type, id, val) {
    try {
      await apiPost('quota/set', { type, id, value: val, mode: 'add' });
      showToast(`已为 ${id} 增加 ${val} 次使用次数`);
      loadQuota();
    } catch (e) {
      showToast('修改配额失败: ' + e.message, 'error');
    }
  };

  window.removeSingleKey = function(idx) {
    state.keys.splice(idx, 1);
    document.getElementById('keysRawTextarea').value = state.keys.map(k => k.key).join('\n');
    saveKeys();
  };

  // Document Ready
  document.addEventListener('DOMContentLoaded', async () => {
    await initBridge();

    // Bind Tab Click
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    // Preset Search
    document.getElementById('presetSearch')?.addEventListener('input', renderPresets);

    // Modal Events
    document.getElementById('addPresetBtn')?.addEventListener('click', () => {
      document.getElementById('modalPresetName').value = '';
      document.getElementById('modalPresetPrompt').value = '';
      document.getElementById('presetModalTitle').textContent = '新增自定义预设';
      document.getElementById('presetModal').classList.add('open');
    });

    document.getElementById('closeModalBtn')?.addEventListener('click', () => {
      document.getElementById('presetModal').classList.remove('open');
    });

    document.getElementById('savePresetModalBtn')?.addEventListener('click', async () => {
      const name = document.getElementById('modalPresetName').value.trim();
      const prompt = document.getElementById('modalPresetPrompt').value.trim();
      if (!name || !prompt) {
        showToast('预设名称与提示词不能为空！', 'error');
        return;
      }
      try {
        await apiPost('presets/save', { name, prompt });
        showToast(`预设 [${name}] 保存成功！`);
        document.getElementById('presetModal').classList.remove('open');
        loadPresets();
      } catch (e) {
        showToast('保存失败: ' + e.message, 'error');
      }
    });

    // Gallery & Overview actions
    document.getElementById('manualCleanup50Btn')?.addEventListener('click', () => handleManualCleanupRatio(0.5, '清理 50% 最旧历史图片'));
    document.getElementById('manualCleanupAllBtn')?.addEventListener('click', () => handleManualCleanupRatio(1.0, '全部清空所有历史图片 (100%)'));
    document.getElementById('prevPageBtn')?.addEventListener('click', () => {
      if (state.galleryPage > 1) loadGallery(state.galleryPage - 1);
    });
    document.getElementById('nextPageBtn')?.addEventListener('click', () => {
      if (state.galleryPage < state.galleryTotalPages) loadGallery(state.galleryPage + 1);
    });

    // Persona actions
    document.getElementById('savePersonaBtn')?.addEventListener('click', savePersonaConfig);
    document.getElementById('personaFileInput')?.addEventListener('change', handlePersonaFileUpload);

    // Config & Provider actions
    document.getElementById('saveConfigBtn')?.addEventListener('click', saveConfig);
    document.getElementById('saveProvidersBtn')?.addEventListener('click', saveProviders);
    document.getElementById('addBackupProviderBtn')?.addEventListener('click', addBackupProviderItem);
    document.getElementById('testApiBtn')?.addEventListener('click', async () => {
      const btn = document.getElementById('testApiBtn');
      const origText = btn.innerHTML;
      btn.disabled = true;
      btn.innerHTML = '⏳ 正在调用生图模型测试...';
      try {
        const res = await apiPost('keys/test', {
          prompt: "a tiny cute plastic figure on a wooden desk, masterwork, masterpiece"
        });
        showToast(res.message || '🎉 绘图测试成功！');
        if (res.data && res.data.image) {
          // 如果在生图工作台，直接展示
          document.getElementById('stageResultImg').src = res.data.image;
          document.getElementById('stageResultMeta').textContent = `测试成功 | 模型: ${res.data.model} | 耗时: ${res.data.elapsed}s`;
          document.getElementById('stageResult').style.display = 'block';
          document.getElementById('stageEmpty').style.display = 'none';
        }
      } catch (e) {
        showToast('生图测试失败: ' + e.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = origText;
      }
    });

    // Studio Events
    document.getElementById('studioFileInput')?.addEventListener('change', handleImageUpload);
    document.getElementById('studioGenBtn')?.addEventListener('click', runStudioGenerate);
    document.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        if (state.activeTab === 'studio') {
          e.preventDefault();
          runStudioGenerate();
        }
      }
    });

    // Lightbox & Confirm Modal Events
    document.getElementById('closeLightboxBtn')?.addEventListener('click', closeImagePreview);
    document.getElementById('lightboxDoneBtn')?.addEventListener('click', closeImagePreview);
    document.getElementById('lightboxCopyPromptBtn')?.addEventListener('click', copyPreviewPrompt);
    document.getElementById('lightboxDeleteBtn')?.addEventListener('click', async () => {
      const filename = activePreview?.kind === 'gallery' ? activePreview.item?.filename : '';
      if (!filename) return;
      const deleted = await window.deleteSingleImage(filename);
      if (deleted) closeImagePreview();
    });
    document.getElementById('imageLightboxModal')?.addEventListener('click', (e) => {
      if (e.target.id === 'imageLightboxModal') closeImagePreview();
    });
    document.addEventListener('keydown', (e) => {
      const modal = document.getElementById('imageLightboxModal');
      if (!modal?.classList.contains('open')) return;

      if (e.key === 'Escape') {
        e.preventDefault();
        closeImagePreview();
        return;
      }

      if (e.key === 'Tab') {
        const focusable = getLightboxFocusableElements();
        if (!focusable.length) return;
        const first = focusable[0];
        const last = focusable[focusable.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    });

    document.getElementById('customConfirmOkBtn')?.addEventListener('click', () => {
      document.getElementById('customConfirmModal')?.classList.remove('open');
      if (confirmResolve) {
        confirmResolve(true);
        confirmResolve = null;
      }
    });

    document.getElementById('customConfirmCancelBtn')?.addEventListener('click', () => {
      document.getElementById('customConfirmModal')?.classList.remove('open');
      if (confirmResolve) {
        confirmResolve(false);
        confirmResolve = null;
      }
    });

    // Load initial tab: Overview & Gallery
    loadOverview();
    loadGallery(1);
  });
})();
