// HTML works: snapshot cards everywhere; the real site loads only in the maximized viewer.
const WEB_VIEWPORTS = [
    { id: 'desktop', label: '桌機', width: 0 },
    { id: 'tablet', label: '平板', width: 820 },
    { id: 'phone', label: '手機', width: 390 }
];
const WEB_ZOOMS = [1, 0.75, 0.5];
const WEB_ROTATE_SECONDS = [0, 15, 30, 60];
const WEB_BRIGHTNESS = [1, 0.7, 1.25];

function webIcon(name) {
    const paths = {
        reload: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
        previous: '<path d="M5 5v14m14-14L7 12l12 7Z"/>',
        next: '<path d="M19 5v14M5 5l12 7-12 7Z"/>',
        freeze: '<rect x="4" y="5" width="16" height="12" rx="1"/><path d="M8 21h8M12 17v4M9 9v4m6-4v4"/>',
        live: '<rect x="4" y="5" width="16" height="12" rx="1"/><path d="M8 21h8M12 17v4m-2-10 4 2-4 2Z"/>',
        rotate: '<path d="M4 12a8 8 0 0 1 14-5.3L20 9"/><path d="M20 4v5h-5M20 12a8 8 0 0 1-14 5.3L4 15"/><path d="M4 20v-5h5"/>',
        shuffle: '<path d="M3 6h3c5 0 7 12 12 12h3m-4-4 4 4-4 4M3 18h3c2 0 3-2 4-4m4-4c1-2 2-4 4-4h3m-4-4 4 4-4 4"/>',
        heart: '<path d="M20 5c-3-3-7-1-8 2-1-3-5-5-8-2-4 4 1 9 8 15 7-6 12-11 8-15Z"/>',
        desktop: '<rect x="3" y="4" width="18" height="12" rx="1"/><path d="M8 20h8m-4-4v4"/>',
        tablet: '<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M11 18h2"/>',
        phone: '<rect x="7" y="3" width="10" height="18" rx="2"/><path d="M11 18h2"/>',
        zoom: '<circle cx="11" cy="11" r="6"/><path d="m20 20-4.5-4.5M8.5 11h5"/>',
        brightness: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M5 19l1.5-1.5m11-11L19 5"/>',
        tag: '<path d="m3 3 9 1 9 9-8 8-9-9Z"/><circle cx="8" cy="8" r="1"/>',
        camera: '<path d="M4 8h3l2-3h6l2 3h3v11H4Z"/><circle cx="12" cy="13" r="3.5"/>',
        copy: '<rect x="8" y="8" width="12" height="12" rx="1"/><path d="M16 8V4H4v12h4"/>',
        edit: '<path d="m4 20 1-5L16 4l4 4L9 19Z"/><path d="m14 6 4 4"/>',
        trash: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6m4-6v6"/>',
        external: '<path d="M14 4h6v6M20 4l-9 9"/><path d="M18 14v6H4V6h6"/>',
        help: '<circle cx="12" cy="12" r="9"/><path d="M9 9a3 3 0 1 1 4 3c-1 .4-1 1-1 2m0 3h.01"/>',
        expand: '<path d="M9 4H4v5m11-5h5v5M4 15v5h5m11-5v5h-5"/>',
        contract: '<path d="M4 9h5V4m6 0v5h5M9 20v-5H4m16 0h-5v5"/>',
        close: '<path d="m6 6 12 12M18 6 6 18"/>',
        add: '<path d="M12 5v14M5 12h14"/>',
        globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c3 3 3 15 0 18M12 3c-3 3-3 15 0 18"/>'
    };
    return '<svg class="playerIcon" aria-hidden="true" focusable="false" viewBox="0 0 24 24">' + (paths[name] || paths.globe) + '</svg>';
}

function readWebSetting(key, fallback) {
    try { const value = localStorage.getItem('localcinema:web-' + key); return value === null ? fallback : Number(value) } catch { return fallback }
}
function saveWebSetting(key, value) { try { localStorage.setItem('localcinema:web-' + key, String(value)) } catch { } }

const webView = {
    item: null, live: false, forceEmbed: false, session: '', rotateTimer: null, random: false, loadTimer: null,
    viewport: Math.min(WEB_VIEWPORTS.length - 1, Math.max(0, readWebSetting('viewport', 0))),
    zoom: Math.min(WEB_ZOOMS.length - 1, Math.max(0, readWebSetting('zoom', 0))),
    rotate: Math.min(WEB_ROTATE_SECONDS.length - 1, Math.max(0, readWebSetting('rotate', 0))),
    brightness: 0
};

function isWebGroup(groupId = currentGroupId) {
    return sourceGroups.find(group => group.id === groupId)?.kind === 'web';
}
function webHost(url) { try { return new URL(url).host } catch { return url || '' } }
function webSession() {
    return typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Array.from(crypto.getRandomValues(new Uint8Array(16)), b => b.toString(16).padStart(2, '0')).join('');
}

function buildWebViewer() {
    if (document.getElementById('webModal')) return;
    const dialog = document.createElement('dialog');
    dialog.id = 'webModal';
    dialog.innerHTML = `
<div id="webStage">
  <div id="webCanvas"><img id="webSnapshot" alt="" draggable="false"><div id="webFrameBox"></div></div>
  <div class="privacy-glass" aria-hidden="true"></div>
  <div id="webBlocked" hidden><p>此網站不允許被嵌入其他頁面，目前顯示的是快照。</p><div><button id="webBlockedOpen" class="primary"></button><button id="webTryEmbed">仍嘗試嵌入</button></div></div>
  <div id="webHead"><div class="webTitleBlock"><h2 id="webTitle"></h2><a id="webHost" target="_blank" rel="noopener noreferrer"></a><span id="webState" role="status"></span></div>
    <div class="headActions"><button id="webBoss" title="隱藏畫面">Hide</button><button id="webClose" aria-label="關閉作品檢視"></button></div></div>
  <div id="webToolbar" class="playerTools">
    <div class="controlsLeft">
      <button id="webReload" title="重新載入作品（R）" aria-label="重新載入作品"></button>
      <button id="webPrevious" title="上一個作品（←）" aria-label="上一個作品"></button>
      <button id="webNext" title="下一個作品（→）" aria-label="下一個作品"></button>
      <button id="webFreeze" title="凍結作品：換回快照並停止網頁（P）" aria-label="凍結作品"></button>
      <span id="webPosition" class="playbackClock"></span>
    </div>
    <div class="controlsRight">
      <button id="webRotate" title="自動輪播" aria-label="自動輪播"></button>
      <button id="webRandom" aria-pressed="false" title="隨機下一個" aria-label="隨機下一個"></button>
      <button id="webFavorite" title="加入我的最愛" aria-label="加入我的最愛"></button>
      <button id="webViewport" title="檢視寬度" aria-label="檢視寬度"></button>
      <button id="webZoom" title="縮放比例" aria-label="縮放比例"></button>
      <button id="webBrightness" title="亮度" aria-label="亮度"></button>
      <button id="webTags" title="快速設定Tag" aria-label="快速設定Tag"></button>
      <button id="webSnapshotRetake" title="重新擷取快照（開啟 10 秒後）" aria-label="重新擷取快照"></button>
      <button id="webCopy" title="複製網址" aria-label="複製網址"></button>
      <button id="webEdit" title="編輯標題或網址" aria-label="編輯作品"></button>
      <button id="webDelete" title="刪除作品" aria-label="刪除作品"></button>
      <button id="webOpenTab" title="以分頁開啟（O）" aria-label="以分頁開啟"></button>
      <button id="webHelpToggle" aria-expanded="false" title="操作說明" aria-label="操作說明"></button>
      <button id="webFullscreen" title="全螢幕（F）" aria-label="全螢幕"></button>
    </div>
  </div>
  <section id="webHelp" class="help" hidden aria-label="作品檢視說明"><div class="helpHeading"><h3>作品檢視</h3><button id="webHelpClose">收起</button></div>
    <div class="shortcutColumns"><div>
      <div class="shortcutRow"><span>上一個／下一個作品</span><span><kbd>←</kbd><i>/</i><kbd>→</kbd></span></div>
      <div class="shortcutRow"><span>重新載入</span><span><kbd>R</kbd></span></div>
      <div class="shortcutRow"><span>凍結／恢復網頁</span><span><kbd>P</kbd></span></div>
    </div><div>
      <div class="shortcutRow"><span>以分頁開啟</span><span><kbd>O</kbd></span></div>
      <div class="shortcutRow"><span>全螢幕／退出</span><span><kbd>F</kbd></span></div>
      <div class="shortcutRow"><span>關閉檢視</span><span><kbd>Esc</kbd></span></div>
    </div></div>
    <p class="helpNote">在網頁內部點擊後，鍵盤會交給該網站；點作品外的工具列即可恢復快捷鍵。部分網站禁止嵌入，請使用「以分頁開啟」。</p></section>
</div>`;
    document.body.append(dialog);
    const form = document.createElement('dialog');
    form.id = 'webEditDialog';
    form.innerHTML = `<form method="dialog" id="webEditForm"><h2 id="webEditHeading">新增作品網址</h2>
<label>網址<input id="webEditUrl" type="text" inputmode="url" required maxlength="2048" placeholder="https://example.com/" autocomplete="off"></label>
<label>標題（選填，留白使用網頁標題）<input id="webEditTitle" maxlength="120" autocomplete="off"></label>
<p class="muted">新增後會在背景開啟網站 10 秒並擷取快照。</p><p id="webEditError" role="alert"></p>
<div class="dialogActions"><button type="button" id="webEditCancel">取消</button><button class="primary" id="webEditSave">儲存</button></div></form>`;
    document.body.append(form);
    const confirmBox = document.createElement('dialog');
    confirmBox.id = 'webConfirm';
    confirmBox.innerHTML = `<h2 id="webConfirmTitle"></h2><p id="webConfirmText"></p><div class="dialogActions"><button id="webConfirmNo">取消</button><button id="webConfirmYes" class="danger"></button></div>`;
    document.body.append(confirmBox);
}

function webConfirm(title, text, action) {
    return new Promise(resolve => {
        const box = $('webConfirm');
        $('webConfirmTitle').textContent = title; $('webConfirmText').textContent = text; $('webConfirmYes').textContent = action;
        const finish = value => { $('webConfirmYes').onclick = $('webConfirmNo').onclick = box.oncancel = null; if (box.open) box.close(); resolve(value) };
        $('webConfirmYes').onclick = () => finish(true); $('webConfirmNo').onclick = () => finish(false);
        box.oncancel = event => { event.preventDefault(); finish(false) };
        box.showModal(); $('webConfirmNo').focus();
    });
}

function webPool() {
    const items = filteredCatalog().filter(item => item.kind === 'web');
    return items.length ? items : sourceGroupItems().filter(item => item.kind === 'web');
}

function webCanEmbed(item) { return item.frame !== 'blocked' || webView.forceEmbed }

function unloadWebFrame() {
    clearTimeout(webView.loadTimer);
    $('webFrameBox').replaceChildren();
    $('webCanvas').classList.remove('frame-ready');
    webView.live = false;
    syncWebToolbar();
}

function loadWebFrame() {
    const item = webView.item;
    unloadWebFrame();
    if (!item || bossActive) return;
    $('webBlocked').hidden = webCanEmbed(item);
    if (!webCanEmbed(item)) { $('webState').textContent = '此網站禁止嵌入'; return }
    const frame = document.createElement('iframe');
    frame.id = 'webFrame';
    frame.title = item.title;
    frame.referrerPolicy = 'no-referrer';
    frame.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-pointer-lock allow-downloads');
    frame.allow = 'fullscreen; autoplay; clipboard-write; encrypted-media; picture-in-picture';
    frame.setAttribute('allowfullscreen', '');
    $('webState').textContent = '正在載入網頁…';
    frame.onload = () => { if (frame.isConnected) { $('webState').textContent = ''; $('webCanvas').classList.add('frame-ready') } };
    webView.loadTimer = setTimeout(() => { if (frame.isConnected && !$('webCanvas').classList.contains('frame-ready')) $('webState').textContent = '載入較慢；若一直空白，可能被網站禁止嵌入，請以分頁開啟。' }, 12000);
    $('webCanvas').classList.remove('frame-ready');
    frame.src = item.url;
    $('webFrameBox').append(frame);
    webView.live = true;
    applyWebLayout();
    syncWebToolbar();
}

function applyWebLayout() {
    const viewport = WEB_VIEWPORTS[webView.viewport], zoom = WEB_ZOOMS[webView.zoom], box = $('webFrameBox');
    const canvas = $('webCanvas'), available = canvas.clientWidth || window.innerWidth;
    const width = viewport.width ? Math.min(viewport.width, available / zoom) : available / zoom;
    box.style.width = width + 'px';
    box.style.height = (canvas.clientHeight || window.innerHeight) / zoom + 'px';
    box.style.transform = 'scale(' + zoom + ')';
    box.classList.toggle('framed', !!viewport.width);
    canvas.style.setProperty('--web-brightness', String(WEB_BRIGHTNESS[webView.brightness]));
}

function syncWebToolbar() {
    const item = webView.item;
    if (!item) return;
    const viewport = WEB_VIEWPORTS[webView.viewport], zoom = WEB_ZOOMS[webView.zoom], seconds = WEB_ROTATE_SECONDS[webView.rotate];
    $('webFreeze').innerHTML = webIcon(webView.live ? 'freeze' : 'live');
    $('webFreeze').title = webView.live ? '凍結作品：換回快照並停止網頁（P）' : '恢復即時網頁（P）';
    $('webFreeze').classList.toggle('is-on', !webView.live);
    $('webViewport').innerHTML = webIcon(viewport.id); $('webViewport').title = '檢視寬度：' + viewport.label;
    $('webZoom').innerHTML = webIcon('zoom') + '<span class="webBadge">' + Math.round(zoom * 100) + '%</span>'; $('webZoom').title = '縮放比例：' + Math.round(zoom * 100) + '%';
    $('webRotate').innerHTML = webIcon('rotate') + (seconds ? '<span class="webBadge">' + seconds + 's</span>' : '');
    $('webRotate').title = seconds ? '自動輪播：每 ' + seconds + ' 秒' : '自動輪播：關閉';
    $('webRotate').classList.toggle('is-on', !!seconds);
    $('webRandom').classList.toggle('is-on', webView.random); $('webRandom').setAttribute('aria-pressed', String(webView.random));
    $('webBrightness').title = '亮度：' + ['一般', '柔暗', '明亮'][webView.brightness];
    $('webBrightness').classList.toggle('is-on', webView.brightness !== 0);
    $('webFavorite').title = item.favorite ? '移除我的最愛' : '加入我的最愛';
    $('webFavorite').classList.toggle('is-on', !!item.favorite);
    const pool = webPool(), index = pool.findIndex(entry => entry.id === item.id);
    $('webPosition').textContent = index >= 0 ? (index + 1) + ' / ' + pool.length : '';
    $('webPrevious').disabled = $('webNext').disabled = pool.length < 2 && !(pool.length === 1 && pool[0].id !== item.id);
}

function drawWebItem() {
    const item = webView.item;
    $('webTitle').textContent = item.title;
    $('webHost').textContent = webHost(item.url); $('webHost').href = item.url;
    $('webSnapshot').src = '/poster/' + item.id + '?v=' + (item.snapshotAt || 0);
    $('webSnapshot').style.visibility = item.snapshotAt ? 'visible' : 'hidden';
    $('webBlocked').hidden = webCanEmbed(item);
    syncWebToolbar();
}

function openWebWork(item, options = {}) {
    buildWebViewer();
    if (shorts.active && !shorts.suspended) pauseShortsForPlayer();
    bossActive = false; document.body.classList.remove('boss-mode'); $('bossScreen').hidden = true;
    for (const stop of [...previews]) stop();
    webView.item = item; webView.forceEmbed = false; webView.session = webSession();
    const dialog = $('webModal');
    drawWebItem();
    if (!dialog.open) dialog.showModal();
    if (!options.automatic && !document.fullscreenElement) $('webStage').requestFullscreen?.().catch(() => { });
    loadWebFrame();
    restartWebRotation();
    post('/api/works/visit', { id: item.id, session: webView.session }).catch(() => { });
}

function closeWebWork() {
    const dialog = document.getElementById('webModal');
    if (!dialog || (!dialog.open && !webView.item)) return;
    clearInterval(webView.rotateTimer); webView.rotateTimer = null;
    unloadWebFrame();
    if (document.fullscreenElement && dialog.contains(document.fullscreenElement)) document.exitFullscreen().catch(() => { });
    if (dialog.open) dialog.close();
    webView.item = null;
    $('webHelp').hidden = true;
    if (typeof refresh === 'function') refresh();
    resumeShortsAfterPlayer();
}

function stepWebWork(direction) {
    const item = webView.item, pool = webPool();
    if (!item || !pool.length) return;
    let next;
    if (webView.random && direction > 0) {
        const others = pool.filter(entry => entry.id !== item.id);
        next = others[Math.floor(Math.random() * others.length)];
    } else {
        const index = pool.findIndex(entry => entry.id === item.id);
        next = pool[(index + direction + pool.length) % pool.length];
    }
    if (next && next.id !== item.id) openWebWork(next, { automatic: true });
}

function restartWebRotation() {
    clearInterval(webView.rotateTimer); webView.rotateTimer = null;
    const seconds = WEB_ROTATE_SECONDS[webView.rotate];
    if (seconds) webView.rotateTimer = setInterval(() => {
        const dialog = document.getElementById('webModal');
        if (!dialog?.open || bossActive || document.hidden || !$('webHelp').hidden) return;
        stepWebWork(1);
    }, seconds * 1000);
}

async function saveWebWork(existing) {
    buildWebViewer();
    const dialog = $('webEditDialog');
    $('webEditHeading').textContent = existing ? '編輯作品' : '新增作品網址';
    $('webEditUrl').value = existing?.url || ''; $('webEditTitle').value = existing?.title || ''; $('webEditError').textContent = '';
    return new Promise(resolve => {
        const done = value => { $('webEditForm').onsubmit = $('webEditCancel').onclick = null; if (dialog.open) dialog.close(); resolve(value) };
        $('webEditCancel').onclick = () => done(false);
        $('webEditForm').onsubmit = async event => {
            event.preventDefault();
            const url = $('webEditUrl').value.trim(), title = $('webEditTitle').value.trim();
            $('webEditSave').disabled = true; $('webEditError').textContent = '';
            try {
                const response = await fetch(existing ? '/api/works/update' : '/api/works/add', {
                    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Cinema-Token': token },
                    body: JSON.stringify(existing ? { id: existing.id, url, title } : { group: currentGroupId, url, title })
                });
                const data = await response.json().catch(() => ({}));
                if (!response.ok) throw Error(data.error || '儲存失敗');
                toast(existing ? '已更新作品' : '已加入作品，快照擷取中…');
                done(true); await refreshWebNow(); watchWebSnapshots();
            } catch (error) { $('webEditError').textContent = error.message || '儲存失敗' }
            finally { $('webEditSave').disabled = false }
        };
        dialog.showModal(); $('webEditUrl').focus();
    });
}

async function deleteWebWork(item) {
    if (!item) return false;
    if (!await webConfirm('刪除作品？', `「${item.title}」\n${item.url}\n只移除映室中的網址、快照、標籤與最愛，不影響網站本身。`, '刪除')) return false;
    if (!await webConfirm('再次確認刪除', '此操作無法復原。確定要刪除這個作品嗎？', '確定刪除')) return false;
    try { await post('/api/works/delete', { id: item.id, confirm: item.id }); toast('已刪除作品'); refresh(); return true }
    catch { toast('刪除失敗，請稍後再試'); return false }
}

// Refresh now even if a poll is in flight, so new or recaptured works show at once.
async function refreshWebNow() {
    for (let i = 0; i < 40 && busy; i++) await new Promise(resolve => setTimeout(resolve, 100));
    await refresh();
}

let webPendingTimer = null;
function watchWebSnapshots() {
    clearTimeout(webPendingTimer);
    if (library.some(item => item.kind === 'web' && item.snapshotPending)) webPendingTimer = setTimeout(async () => { await refreshWebNow(); watchWebSnapshots() }, 1500);
}

async function captureVisibleWork() {
    // Tab capture only: the cross-origin site cannot be read directly, but the composited tab can.
    const stream = await navigator.mediaDevices.getDisplayMedia({ video: { displaySurface: 'browser', frameRate: 5 }, audio: false, preferCurrentTab: true, selfBrowserSurface: 'include', surfaceSwitching: 'exclude' });
    const track = stream.getVideoTracks()[0];
    const wrong = () => Object.assign(new Error('請選擇目前這個分頁'), { name: 'WrongSurface' });
    try {
        const surface = track.getSettings().displaySurface;
        if (surface && surface !== 'browser') throw wrong();
        let cropped = false;
        if (typeof CropTarget !== 'undefined' && track.cropTo) {
            try { await track.cropTo(await CropTarget.fromElement($('webCanvas'))); cropped = true } catch { throw wrong() }
        }
        const video = document.createElement('video');
        video.muted = true; video.playsInline = true; video.srcObject = stream;
        await video.play();
        await new Promise(resolve => setTimeout(resolve, 400));
        const canvas = document.createElement('canvas'), area = $('webCanvas').getBoundingClientRect();
        let sx = 0, sy = 0, sw = video.videoWidth, sh = video.videoHeight;
        if (!cropped) {
            const scale = video.videoWidth / window.innerWidth;
            sx = area.left * scale; sy = area.top * scale; sw = area.width * scale; sh = area.height * scale;
        }
        canvas.width = Math.round(Math.min(1600, sw)); canvas.height = Math.round(canvas.width * sh / sw);
        canvas.getContext('2d').drawImage(video, sx, sy, sw, sh, 0, 0, canvas.width, canvas.height);
        video.srcObject = null;
        return canvas.toDataURL('image/jpeg', 0.88);
    } finally { stream.getTracks().forEach(t => t.stop()) }
}

async function retakeWebSnapshot() {
    const item = webView.item, button = $('webSnapshotRetake');
    if (!item || button.disabled) return;
    button.disabled = true;
    try {
        if (webView.live && window.isSecureContext && navigator.mediaDevices?.getDisplayMedia) {
            try {
                const image = await captureVisibleWork();
                await post('/api/works/snapshot-upload', { id: item.id, image });
                toast('已將目前畫面設為預覽圖');
                await refreshWebNow(); return;
            } catch { /* picker declined, unsupported or wrong surface: fall back to the host capture */ }
        }
        toast('正在重新擷取網頁畫面…');
        const response = await fetch('/api/works/snapshot', { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Cinema-Token': token }, body: JSON.stringify({ id: item.id, now: true }) });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) throw Error(data.error || '擷取失敗');
        toast('已重新擷取並設為預覽圖');
        await refreshWebNow();
    } catch (error) { toast(error.message || '擷取失敗') }
    finally { button.disabled = false }
}

function installWebControls() {
    buildWebViewer();
    const icons = [['webReload', 'reload'], ['webPrevious', 'previous'], ['webNext', 'next'], ['webRandom', 'shuffle'], ['webFavorite', 'heart'], ['webBrightness', 'brightness'], ['webTags', 'tag'], ['webSnapshotRetake', 'camera'], ['webCopy', 'copy'], ['webEdit', 'edit'], ['webDelete', 'trash'], ['webOpenTab', 'external'], ['webHelpToggle', 'help'], ['webFullscreen', 'expand'], ['webClose', 'close']];
    for (const [id, name] of icons) $(id).innerHTML = webIcon(name);
    $('webBlockedOpen').innerHTML = webIcon('external') + '以分頁開啟';
    const open = () => { if (webView.item) window.open(webView.item.url, '_blank', 'noopener,noreferrer') };
    $('webOpenTab').onclick = open; $('webBlockedOpen').onclick = open;
    $('webTryEmbed').onclick = () => { webView.forceEmbed = true; loadWebFrame() };
    $('webClose').onclick = closeWebWork;
    $('webBoss').onclick = () => bossMode();
    $('webModal').addEventListener('cancel', event => { event.preventDefault(); if (document.fullscreenElement) document.exitFullscreen().catch(() => { }); else closeWebWork() });
    $('webReload').onclick = () => loadWebFrame();
    $('webPrevious').onclick = () => stepWebWork(-1);
    $('webNext').onclick = () => stepWebWork(1);
    $('webFreeze').onclick = () => webView.live ? unloadWebFrame() : loadWebFrame();
    $('webRotate').onclick = () => { webView.rotate = (webView.rotate + 1) % WEB_ROTATE_SECONDS.length; saveWebSetting('rotate', webView.rotate); restartWebRotation(); syncWebToolbar() };
    $('webRandom').onclick = () => { webView.random = !webView.random; syncWebToolbar() };
    $('webViewport').onclick = () => { webView.viewport = (webView.viewport + 1) % WEB_VIEWPORTS.length; saveWebSetting('viewport', webView.viewport); applyWebLayout(); syncWebToolbar() };
    $('webZoom').onclick = () => { webView.zoom = (webView.zoom + 1) % WEB_ZOOMS.length; saveWebSetting('zoom', webView.zoom); applyWebLayout(); syncWebToolbar() };
    $('webBrightness').onclick = () => { webView.brightness = (webView.brightness + 1) % WEB_BRIGHTNESS.length; applyWebLayout(); syncWebToolbar() };
    $('webFavorite').onclick = async () => {
        const item = webView.item; if (!item) return;
        try { const value = !item.favorite; await post('/api/favorite', { id: item.id, favorite: value }); item.favorite = value; syncWebToolbar(); refresh() } catch { toast('無法更新我的最愛') }
    };
    $('webTags').onclick = () => { if (webView.item) openQuickTags(webView.item) };
    $('webSnapshotRetake').onclick = retakeWebSnapshot;
    $('webCopy').onclick = async () => {
        if (!webView.item) return;
        try { await navigator.clipboard.writeText(webView.item.url); toast('已複製網址') } catch { toast(webView.item.url) }
    };
    $('webEdit').onclick = async () => { if (webView.item && await saveWebWork(webView.item)) loadWebFrame() };
    $('webDelete').onclick = async () => { const item = webView.item; if (await deleteWebWork(item) && webView.item === item) closeWebWork() };
    const toggleHelp = force => { const help = $('webHelp'); help.hidden = force ?? !help.hidden; $('webHelpToggle').setAttribute('aria-expanded', String(!help.hidden)) };
    $('webHelpToggle').onclick = () => toggleHelp(); $('webHelpClose').onclick = () => toggleHelp(true);
    const updateFull = () => { const full = !!document.fullscreenElement; $('webFullscreen').innerHTML = webIcon(full ? 'contract' : 'expand'); $('webFullscreen').title = full ? '退出全螢幕（F）' : '全螢幕（F）'; requestAnimationFrame(applyWebLayout) };
    $('webFullscreen').onclick = () => document.fullscreenElement ? document.exitFullscreen().catch(() => { }) : $('webStage').requestFullscreen?.().catch(() => { });
    document.addEventListener('fullscreenchange', updateFull);
    window.addEventListener('resize', () => { if ($('webModal').open) applyWebLayout() });
    document.addEventListener('keydown', event => {
        if (!$('webModal').open || $('webEditDialog').open || $('webConfirm').open || $('tagDialog')?.open) return;
        if (['INPUT', 'SELECT', 'TEXTAREA'].includes(document.activeElement?.tagName)) return;
        const key = event.key.toLowerCase();
        const actions = { arrowleft: () => stepWebWork(-1), arrowright: () => stepWebWork(1), r: () => loadWebFrame(), p: () => $('webFreeze').click(), o: open, f: () => $('webFullscreen').click() };
        if (actions[key]) { event.preventDefault(); actions[key]() }
    });
    $('webEditDialog').addEventListener('cancel', () => $('webEditCancel').click());
    updateFull();
}

// Library integration hooks called from index.html.
function syncWorkMode() {
    const web = isWebGroup();
    document.body.classList.toggle('web-group', web);
    const add = document.getElementById('addWebWork');
    if (add) add.hidden = !web;
    const labels = web
        ? { allView: '作品庫', randomAll: '隨機開啟', randomFav: '隨機最愛', randomTag: '依標籤抽選' }
        : { allView: '影片庫', randomAll: '隨機播放', randomFav: '隨機最愛', randomTag: '依標籤抽片' };
    for (const [id, label] of Object.entries(labels)) {
        const button = document.getElementById(id);
        if (!button || button.dataset.label === label) continue;
        const span = button.querySelector('span'), svg = button.querySelector('svg');
        if (span) span.textContent = label;
        else if (svg) button.replaceChildren(svg, document.createTextNode(label));
        else continue;
        button.dataset.label = label;
    }
    const heading = document.getElementById('viewTitle');
    if (heading && view === 'all') heading.textContent = web ? '所有作品' : '所有影片';
    const search = document.getElementById('search');
    if (search) search.placeholder = web ? '搜尋作品名稱、網址或標籤…' : '搜尋影片名稱或標籤…';
}

function decorateWebCard(item, visual, meta) {
    visual.onclick = () => openPlayer(item);
    visual.onkeydown = event => { if (event.key === 'Enter') openPlayer(item) };
    visual.setAttribute('aria-label', '開啟作品 ' + item.title);
    if (item.snapshotPending || !item.snapshotAt) {
        const pending = document.createElement('span');
        pending.className = 'webPending';
        pending.textContent = item.snapshotPending ? '快照擷取中…' : '尚無快照';
        visual.append(pending);
    }
    const host = document.createElement('span');
    host.className = 'webCardHost'; host.textContent = webHost(item.url);
    const tab = document.createElement('button');
    tab.className = 'webCardAction webCardTab'; tab.innerHTML = webIcon('external'); tab.title = '以分頁開啟'; tab.setAttribute('aria-label', '以分頁開啟 ' + item.title);
    tab.onclick = () => window.open(item.url, '_blank', 'noopener,noreferrer');
    const remove = document.createElement('button');
    remove.className = 'webCardAction webCardDelete'; remove.innerHTML = webIcon('trash'); remove.title = '刪除作品'; remove.setAttribute('aria-label', '刪除作品 ' + item.title);
    remove.onclick = () => deleteWebWork(item);
    meta.prepend(host);
    meta.append(tab, remove);
}

function webBadgeText(item) { return item.frame === 'blocked' ? '分頁瀏覽' : '網頁' }

function webAfterRefresh() {
    const dialog = document.getElementById('webModal');
    if (!dialog?.open || !webView.item) return;
    const latest = library.find(item => item.id === webView.item.id);
    if (!latest || !sourceGroupItems().some(item => item.id === latest.id)) { closeWebWork(); return }
    const urlChanged = latest.url !== webView.item.url;
    if (latest.snapshotAt !== webView.item.snapshotAt) $('webSnapshot').src = '/poster/' + latest.id + '?v=' + (latest.snapshotAt || 0);
    webView.item = latest;
    drawWebItem();
    if (urlChanged && webView.live) loadWebFrame();
}

// Short: one snapshot card per work; nothing loads until the card is expanded.
const buildVideoShortEntries = buildShortEntries;
buildShortEntries = function (items) {
    const entries = buildVideoShortEntries(items.filter(item => item.kind !== 'web'));
    for (const item of items) if (item.kind === 'web') entries.push({ key: item.id + ':web', item, episode: { id: item.id, name: webHost(item.url) } });
    return entries;
};

// Mouse drag scrolls between Short cards; only a still, short press opens the work.
function installWebShortGesture(card, video) {
    let gesture = null;
    video.draggable = false;
    video.addEventListener('pointerdown', event => {
        if (event.button !== 0) return;
        const scroller = $('shortScroller');
        gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, top: scroller.scrollTop, at: Date.now(), moved: false, mouse: event.pointerType === 'mouse' };
        if (gesture.mouse) { video.setPointerCapture(event.pointerId); event.preventDefault() }
    });
    video.addEventListener('pointermove', event => {
        if (!gesture || event.pointerId !== gesture.id) return;
        const dx = event.clientX - gesture.x, dy = event.clientY - gesture.y;
        if (Math.hypot(dx, dy) > 8) gesture.moved = true;
        if (gesture.mouse && gesture.moved) {
            const scroller = $('shortScroller');
            scroller.classList.add('short-updating');
            scroller.scrollTop = gesture.top - dy;
        }
    });
    const finish = (event, cancel) => {
        if (!gesture || event.pointerId !== gesture.id) return;
        const done = gesture; gesture = null;
        if (Math.hypot(event.clientX - done.x, event.clientY - done.y) > 8) done.moved = true;
        const scroller = $('shortScroller');
        const scrolled = scroller.scrollTop !== done.top;
        if (done.mouse && done.moved) {
            const dy = event.clientY - done.y;
            scroller.scrollTop = done.top;
            requestAnimationFrame(() => {
                scroller.classList.remove('short-updating');
                if (!shorts.activeCard) shorts.activeCard = card;
                if (!cancel && Math.abs(dy) > 40) navigateShort(dy < 0 ? 1 : -1);
                else card.scrollIntoView({ block: 'start', behavior: 'smooth' });
            });
        }
        card._suppressClickUntil = done.moved || scrolled || Date.now() - done.at > 600 ? Date.now() + 400 : 0;
    };
    video.addEventListener('pointerup', event => finish(event, false));
    video.addEventListener('pointercancel', event => finish(event, true));
    video.onclick = event => {
        event.preventDefault();
        if (Date.now() < (card._suppressClickUntil || 0)) return;
        if (shorts.activeCard !== card) { card.scrollIntoView({ block: 'start', behavior: 'smooth' }); return }
        openPlayer(card._entry.item);
    };
}

function decorateWebShort(card, video, expand) {
    card._web = true;
    card.classList.add('webShort');
    video.preload = 'none';
    installWebShortGesture(card, video);
    expand.title = '放大開啟網頁'; expand.setAttribute('aria-label', '放大開啟網頁 ' + card._entry.item.title);
    expand.onclick = () => openPlayer(card._entry.item);
    const tab = document.createElement('button');
    tab.className = 'shortExpand webShortTab'; tab.innerHTML = webIcon('external'); tab.title = '以分頁開啟';
    tab.onclick = () => window.open(card._entry.item.url, '_blank', 'noopener,noreferrer');
    expand.after(tab);
}

document.addEventListener('DOMContentLoaded', () => {
    installWebControls();
    const actions = document.querySelector('.sectionTop') || document.querySelector('.collectionActions');
    if (actions && !document.getElementById('addWebWork')) {
        const add = document.createElement('button');
        add.id = 'addWebWork'; add.hidden = true; add.innerHTML = webIcon('add') + '新增作品網址';
        add.onclick = () => saveWebWork(null);
        actions.append(add);
    }
    syncWorkMode();
});
