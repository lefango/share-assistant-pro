/* 分享助手 · 好友端网页逻辑（新版草稿） */
(() => {
  'use strict';

  const $ = (id) => document.getElementById(id);
  const app = $('app'), crumbEl = $('crumb'), lb = $('lb'), lbBody = $('lbBody'),
        lbName = $('lbName'), lbMeta = $('lbMeta'), lbDl = $('lbDl'),
        searchEl = $('search'), topEl = $('top');

  // 品牌标记用「享」字。
  // 注意：以前这里放的是「托盘 + 向上箭头」的上传图标，放在紫色圆角方块里，
  // 和右下角的上传按钮长得一模一样，用户一直把左上角的 logo 当成上传按钮点
  // （反馈：「手机开链接找不到上传按钮，左上角那个点了没反应」）。别再改回图标。
  const LOGO_MARK = '享';
  const ICON_DL = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1"'
    + ' stroke-linecap="round" stroke-linejoin="round"><path d="M12 4v11"/>'
    + '<path d="m7 11 5 5 5-5"/><path d="M5 20h14"/></svg>';
  const ICON_PLAY = '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M8 5.5v13l11-6.5z"/></svg>';
  const ICON_EYE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"'
    + ' stroke-linecap="round" stroke-linejoin="round"><path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7z"/>'
    + '<circle cx="12" cy="12" r="3"/></svg>';

  let META = null, DATA = null;
  let cur = '', filter = '', lastSig = '';
  let media = [], idx = 0;
  let expireLeft = -1, timerId = null;
  let loading = false;

  // 目录里文件特别多（几千上万个）时分批渲染，否则浏览器直接卡死
  const RENDER_CHUNK = 150;
  let renderLimit = RENDER_CHUNK;

  /* ---------------- 工具 ---------------- */
  const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const attr = (s) => esc(s).replace(/\n/g, ' ');

  function fmtSize(n) {
    if (!n) return '';
    if (n < 1024) return n + ' B';
    const u = ['KB', 'MB', 'GB', 'TB'];
    let v = n;
    for (let i = 0; i < u.length; i++) {
      v /= 1024;
      if (v < 1024) return (v < 100 ? v.toFixed(1) : Math.round(v)) + ' ' + u[i];
    }
    return v.toFixed(1) + ' PB';
  }

  const fmtTime = (ts) => {
    if (!ts) return '';
    const d = new Date(ts * 1000), n = new Date();
    const p = (x) => String(x).padStart(2, '0');
    const diff = (n - d) / 1000;
    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
    if (d.toDateString() === n.toDateString()) return '今天 ' + p(d.getHours()) + ':' + p(d.getMinutes());
    if (diff < 86400 * 2) return '昨天 ' + p(d.getHours()) + ':' + p(d.getMinutes());
    if (d.getFullYear() === n.getFullYear()) return p(d.getMonth() + 1) + '-' + p(d.getDate());
    return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate());
  };

  const fmtLeft = (sec) => {
    if (sec < 0) return '';
    if (sec <= 0) return '已结束';
    const d = Math.floor(sec / 86400), h = Math.floor((sec % 86400) / 3600),
          m = Math.floor((sec % 3600) / 60), s = sec % 60;
    if (d) return d + '天' + h + '小时';
    if (h) return h + '小时' + m + '分';
    if (m) return m + '分' + s + '秒';
    return s + '秒';
  };

  function toast(msg, kind) {
    const el = document.createElement('div');
    el.className = 'toast ' + (kind || '');
    el.textContent = msg;
    $('toastWrap').appendChild(el);
    setTimeout(() => { el.style.transition = 'opacity .3s'; el.style.opacity = '0'; }, 2600);
    setTimeout(() => el.remove(), 3050);
  }

  const fileUrl = (path) => '/f/' + path.split('/').map(encodeURIComponent).join('/');

  /* ---------------- 网络 ---------------- */
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({ credentials: 'same-origin' }, opts));
    let data = null;
    try { data = await res.json(); } catch (e) { data = { ok: false, error: 'HTTP ' + res.status }; }
    return { status: res.status, data };
  }

  async function loadMeta() {
    const r = await api('/api/meta');
    const status = r.status, data = r.data;
    if (!data || !data.ok) { if (status === 410) showExpired(); return; }
    META = data;
    document.title = data.title || '分享';
    if (data.need_password && !data.authed) { showGate(); return; }
    $('gate').hidden = true;
    $('shell').hidden = false;
    $('upBtn').hidden = !data.allow_upload;
    $('brandText').textContent = data.title || '分享';
    $('logo').textContent = LOGO_MARK;
    startTimer(data.expires_in);
    updateFoot();
    try {
      const p = new URLSearchParams(location.search).get('path');
      if (p) { cur = p; syncUrl(); }
    } catch (e) { /* 忽略 */ }
    load();
  }

  function showGate() {
    $('shell').hidden = true;
    $('gate').hidden = false;
    $('gateTip').textContent = '《' + (META.title || '分享') + '》需要访问密码';
    setTimeout(() => $('gateInput').focus(), 140);
  }

  function showExpired() {
    $('shell').hidden = true;
    $('gate').hidden = false;
    $('gateInput').hidden = true;
    $('gateBtn').hidden = true;
    $('gateTip').textContent = '这次分享已经结束了';
    $('gateErr').hidden = false;
    $('gateErr').textContent = '请向分享者索要新的链接。';
  }

  function startTimer(sec) {
    expireLeft = sec;
    if (timerId) clearInterval(timerId);
    const pill = $('timer');
    if (sec < 0) { pill.hidden = true; return; }
    pill.hidden = false;
    const tick = () => {
      if (expireLeft <= 0) { pill.textContent = '分享已结束'; clearInterval(timerId); showExpired(); return; }
      pill.textContent = '链接剩余 ' + fmtLeft(expireLeft);
      expireLeft -= 1;
    };
    tick();
    timerId = setInterval(tick, 1000);
  }

  function skeleton() {
    let html = '<div class="grid">';
    for (let i = 0; i < 8; i++) {
      html += '<div class="sk"><div class="sk-thumb"></div>'
            + '<div class="sk-line"></div><div class="sk-line short"></div></div>';
    }
    return html + '</div>';
  }

  async function load(fresh) {
    if (loading) return;
    loading = true;
    if (!DATA) app.innerHTML = skeleton();
    const r = await api('/api/tree?path=' + encodeURIComponent(cur));
    loading = false;
    if (r.status === 401) { await loadMeta(); return; }
    if (r.status === 410) { showExpired(); return; }
    if (!r.data || !r.data.ok) { toast((r.data && r.data.error) || '加载失败', 'err'); return; }

    const sig = signature(r.data);
    const changed = sig !== lastSig;
    DATA = r.data;
    lastSig = sig;
    if (fresh) { toast('已刷新'); render(); return; }
    if (changed) render();
  }

  function signature(d) {
    const parts = [];
    const dirs = d.dirs || [], files = d.files || [];
    for (let i = 0; i < dirs.length; i++) {
      parts.push('d' + dirs[i].name + '|' + (dirs[i].count || 0) + '|' + dirs[i].mtime);
    }
    for (let i = 0; i < files.length; i++) {
      parts.push('f' + files[i].name + '|' + files[i].size + '|' + files[i].mtime);
    }
    return parts.join('\u0001');
  }

  function syncUrl() {
    try {
      const url = cur ? location.pathname + '?path=' + encodeURIComponent(cur) : location.pathname;
      history.replaceState(null, '', url);
    } catch (e) { /* 忽略 */ }
  }

  /* ---------------- 渲染 ---------------- */
  function computeTotal() {
    // 服务端给了就用服务端的；没给就自己从各文件夹统计里凑一个
    if (DATA.total) return DATA.total;
    let count = DATA.files.length, size = 0, hasSize = false;
    for (let i = 0; i < DATA.dirs.length; i++) {
      const d = DATA.dirs[i];
      count += d.count || 0;
      if (typeof d.size === 'number') { size += d.size; hasSize = true; }
    }
    for (let i = 0; i < DATA.files.length; i++) size += DATA.files[i].size || 0;
    return {
      dirs: DATA.dirs.length,
      files: count,
      size: size,
      size_text: hasSize || size ? fmtSize(size) : '',
    };
  }

  function render() {
    if (!DATA) return;
    renderCrumb();

    const q = filter.trim().toLowerCase();
    const match = (n) => !q || String(n).toLowerCase().indexOf(q) >= 0;
    const dirs = DATA.dirs.filter((d) => match(d.name));
    const files = DATA.files.filter((f) => match(f.name));

    if (!dirs.length && !files.length) {
      const has = DATA.dirs.length + DATA.files.length;
      const ico = has ? '🔍' : (cur ? '📂' : '📭');
      const title = has ? '没有匹配的内容' : (cur ? '这个文件夹还是空的' : '还没有内容');
      const sub = has ? '换个关键词试试'
                      : (cur ? '分享者还没有往这里放东西' : '分享者还没有上传任何文件');
      app.innerHTML = '<div class="grid"><div class="empty"><div class="em-ico">' + ico + '</div>'
        + '<b>' + title + '</b><span>' + sub + '</span></div></div>';
      media = [];
      return;
    }

    // 只有前 renderLimit 项进 DOM，剩下的靠「点击继续显示」追加
    const shown = files.slice(0, renderLimit);
    const rest = files.length - shown.length;
    media = shown.filter((f) => f.kind === 'image' || f.kind === 'video' || f.kind === 'audio');

    let html = '';
    if (!cur && !q) html += heroHtml();

    html += '<div class="grid">';

    if (dirs.length) {
      html += sec('分类', '📁', dirs.length);
      html += dirs.map(folderCard).join('');
    }

    const groups = [
      ['video', '视频', '🎬'], ['image', '图片', '🖼'], ['audio', '音频', '🎵'],
      ['pdf', 'PDF', '📕'], ['text', '文本', '📃'], ['file', '文件', '📄'],
    ];
    for (let i = 0; i < groups.length; i++) {
      const kind = groups[i][0], label = groups[i][1], ico = groups[i][2];
      const list = shown.filter((f) => f.kind === kind);
      if (!list.length) continue;
      html += sec(label, ico, list.length);
      html += (kind === 'video' || kind === 'image' || kind === 'audio')
        ? list.map(mediaCard).join('')
        : docList(list);
    }

    if (rest > 0) {
      html += '<div class="more"><button id="moreBtn" type="button">还有 '
            + rest + ' 项，点击继续显示</button></div>';
    }

    html += '</div>';
    app.innerHTML = html;

    const moreBtn = document.getElementById('moreBtn');
    if (moreBtn) {
      moreBtn.onclick = () => {
        renderLimit += RENDER_CHUNK;
        render();
      };
    }
    window.scrollTo(0, 0);
  }

  function sec(title, ico, n) {
    return '<div class="sec"><span class="sec-ico">' + ico + '</span>' + esc(title)
         + '<span class="sec-n">' + n + '</span></div>';
  }

  function heroHtml() {
    let t = null;
    try { t = computeTotal(); } catch (e) { t = null; }
    const bits = [];
    if (t) {
      if (t.dirs) bits.push('<span><i>' + t.dirs + '</i> 个分类</span>');
      if (t.files) bits.push('<span><i>' + t.files + '</i> 个项目</span>');
      if (t.size_text) bits.push('<span>共 <i>' + esc(t.size_text) + '</i></span>');
    }
    let actions = '';
    if (META && META.allow_download && t && t.files) {
      actions += '<a class="btn primary" href="/zip?path=" download>' + ICON_DL
              + ' 打包下载全部</a>';
    }
    actions += '<button class="btn" onclick="SM.focusSearch()">🔍 搜索文件</button>';
    return '<section class="hero"><div class="hero-in">'
      + '<h1>' + esc(META.title || '我的分享') + '</h1>'
      + (bits.length ? '<div class="hero-stats">' + bits.join('') + '</div>' : '')
      + '<div class="hero-actions">' + actions + '</div></div></section>';
  }

  // 缩略图加载失败时不要给用户看浏览器的"破图"图标，换成占位符
  const IMG_FAIL_ONE = "this.classList.add('on');this.style.opacity='.3'";
  const IMG_FALLBACK = "var p=document.createElement('div');p.className='ph';"
    + "p.textContent='🖼';this.replaceWith(p);";

  function tilesHtml(d) {
    const imgs = (d.images || []).slice(0, 4);
    const vids = (d.videos || []).slice(0, 1);
    const badge = dlBadge(d);
    if (!imgs.length && !vids.length) {
      return '<div class="tiles"><div class="ph">📁</div>' + badge + '</div>';
    }
    if (imgs.length === 1 && !vids.length) {
      return '<div class="tiles one"><img loading="lazy" src="' + imgs[0] + '"'
        + ' onload="this.classList.add(\'on\')"'
        + " onerror=\"" + IMG_FAIL_ONE + "if(!this.naturalWidth){" + IMG_FALLBACK + "}\""
        + ' alt="">'
        + badge + '</div>';
    }
    if (vids.length && !imgs.length) {
      return '<div class="tiles one"><video src="' + vids[0]
        + '" muted preload="metadata" onloadeddata="this.classList.add(\'on\')"></video>'
        + badge + '</div>';
    }
    const cls = imgs.length === 2 ? 'tiles two' : 'tiles';
    return '<div class="' + cls + '">' + imgs.map((u) =>
      '<img loading="lazy" src="' + u + '" onload="this.classList.add(\'on\')"'
      + " onerror=\"" + IMG_FAIL_ONE + "if(!this.naturalWidth){" + IMG_FALLBACK + "}\""
      + ' alt="">').join('')
      + badge + '</div>';
  }

  function dlBadge(d) {
    if (!META || !META.allow_download) return '';
    return '<span class="badge">' + (d.count || 0) + '</span>'
      + '<a class="ov-btn zipbtn" href="/zip?path=' + encodeURIComponent(d.path) + '"'
      + ' title="打包下载" onclick="event.stopPropagation()">' + ICON_DL + '</a>';
  }

  function folderCard(d) {
    const meta = [];
    if (d.count) meta.push(d.count + ' 项');
    if (d.size_text) meta.push(d.size_text);
    const p = JSON.stringify(d.path).replace(/"/g, '&quot;');
    return '<div class="card folder" onclick="SM.go(' + p + ')">'
      + tilesHtml(d)
      + '<div class="cap"><b>' + esc(d.name) + '</b>'
      + '<div class="meta">' + esc(meta.join(' · ') || '空文件夹') + '</div></div></div>';
  }

  function mediaCard(f) {
    const i = media.indexOf(f);
    const open = 'onclick="SM.openLb(' + i + ')"';
    const dl = (META && META.allow_download)
      ? '<a class="dl" href="' + f.url + '?dl=1" download="' + attr(f.name) + '"'
        + ' title="下载" onclick="event.stopPropagation()">' + ICON_DL + '</a>' : '';

    if (f.kind === 'video') {
      return '<div class="card" ' + open + '><div class="thumb">'
        + '<video src="' + f.url + '" muted preload="metadata"'
        + ' onloadeddata="this.classList.add(\'on\')"></video>'
        + '<span class="tag">视频</span>'
        + '<div class="ov"><button class="ov-btn play">' + ICON_PLAY + '</button>' + dl + '</div>'
        + '</div><div class="cap"><b>' + esc(f.name) + '</b>'
        + '<div class="meta">' + esc(f.size_text) + '<span class="dot">·</span>'
        + esc(fmtTime(f.mtime)) + '</div></div></div>';
    }
    if (f.kind === 'audio') {
      return '<div class="card" ' + open + '><div class="thumb">'
        + '<div class="ph">🎵</div><span class="tag">' + esc(f.size_text) + '</span>'
        + '<div class="ov"><button class="ov-btn play">' + ICON_PLAY + '</button>' + dl + '</div>'
        + '</div><div class="cap"><b>' + esc(f.name) + '</b>'
        + '<div class="meta">点击播放<span class="dot">·</span>' + esc(fmtTime(f.mtime))
        + '</div></div></div>';
    }
    return '<div class="card" ' + open + '><div class="thumb">'
      + '<img loading="lazy" src="' + (f.thumb || f.url) + '" data-full="' + f.url + '"'
      + ' onload="this.classList.add(\'on\')"'
      + ' onerror="if(!this.dataset.retried){this.dataset.retried=1;this.src=this.dataset.full;}'
      + 'else{var p=document.createElement(\'div\');p.className=\'ph\';p.textContent=\'🖼\';'
      + 'this.replaceWith(p);}" alt="' + attr(f.name) + '">'
      + '<span class="tag">' + esc(f.size_text) + '</span>'
      + '<div class="ov"><button class="ov-btn">' + ICON_EYE + '</button>' + dl + '</div>'
      + '</div><div class="cap"><b>' + esc(f.name) + '</b>'
      + '<div class="meta">' + esc(fmtTime(f.mtime)) + '</div></div></div>';
  }

  /* 只有这两类能在浏览器里直接看，其余（zip / apk / exe / docx …）一律走下载。
     之前这些被 previewFile 拦下来当文本读，结果压缩包根本下不下来。 */
  const PREVIEWABLE = { pdf: 1, text: 1 };
  const ARCHIVE_EXT = ['zip', 'rar', '7z', 'tar', 'gz', 'bz2', 'xz', 'iso'];

  function fileIcon(f) {
    if (f.kind === 'pdf') return '📕';
    if (f.kind === 'text') return '📃';
    const ext = (f.name.split('.').pop() || '').toLowerCase();
    if (ARCHIVE_EXT.indexOf(ext) >= 0) return '🗜';
    return '📄';
  }

  function docList(list) {
    const allow = !!(META && META.allow_download);
    return '<ul class="list">' + list.map((f) => {
      const canPreview = !!PREVIEWABLE[f.kind];
      const href = allow ? f.url + '?dl=1' : f.url;
      // 关键：不能在线预览的类型，链接必须老老实实走下载，不能被预览逻辑拦下来
      const click = canPreview
        ? 'onclick="SM.previewFile(' + JSON.stringify(f.path).replace(/"/g, '&quot;')
          + ',\'' + f.kind + '\');return false;"'
        : '';
      const attrs = canPreview ? 'target="_blank"' : 'download="' + attr(f.name) + '"';
      const dl = allow
        ? '<a class="rowdl" href="' + f.url + '?dl=1" download="' + attr(f.name) + '" title="下载"'
          + ' onclick="event.stopPropagation()">' + ICON_DL + '</a>'
        : '';
      return '<li><span class="ico">' + fileIcon(f) + '</span>'
        + '<div class="grow"><a class="nm" href="' + href + '" ' + attrs + ' ' + click + '>'
        + esc(f.name) + '</a>'
        + '<div class="sub">' + esc(fmtTime(f.mtime)) + '</div></div>'
        + '<span class="sz">' + esc(f.size_text) + '</span>' + dl + '</li>';
    }).join('') + '</ul>';
  }

  function renderCrumb() {
    const crumbs = (DATA && DATA.crumbs) || [{ name: '根目录', path: '' }];
    crumbEl.innerHTML = crumbs.map((c, i) => {
      const last = i === crumbs.length - 1;
      const label = i === 0 ? '🏠 ' + esc(c.name) : esc(c.name);
      if (last) return (i ? '<span class="sep">/</span>' : '') + '<span class="now">' + label + '</span>';
      const p = JSON.stringify(c.path).replace(/"/g, '&quot;');
      return (i ? '<span class="sep">/</span>' : '')
        + '<span class="seg" onclick="SM.go(' + p + ')">' + label + '</span>';
    }).join('');
    crumbEl.scrollLeft = crumbEl.scrollWidth;
  }

  function updateFoot() {
    $('footLeft').innerHTML = '<span style="opacity:.6">由</span><b>'
      + esc(META.title || '朋友') + '</b><span style="opacity:.6">分享</span>';
    const pills = [META.allow_download ? '可下载' : '仅在线浏览'];
    if (META.allow_upload) pills.push('可上传');
    $('footRight').innerHTML = pills.map((p) => '<span class="pill">' + p + '</span>').join('');
  }

  /* ---------------- 预览 ---------------- */
  function openLb(i) {
    if (i < 0 || i >= media.length) return;
    idx = i;
    showLb();
    document.body.style.overflow = 'hidden';
  }

  function showLb() {
    const f = media[idx];
    if (!f) { closeLb(); return; }
    if (f.kind === 'video') {
      lbBody.innerHTML = '<video src="' + f.url + '" controls autoplay playsinline></video>';
    } else if (f.kind === 'audio') {
      lbBody.innerHTML = '<div class="audio-wrap"><div class="ai">🎵</div>'
        + '<div class="an">' + esc(f.name) + '</div>'
        + '<audio src="' + f.url + '" controls autoplay style="width:min(440px,80vw)"></audio></div>';
    } else {
      lbBody.innerHTML = '<img src="' + f.url + '" alt="">';
    }
    lbName.textContent = f.name;
    lbMeta.textContent = f.size_text + ' · ' + (idx + 1) + ' / ' + media.length;
    lbDl.href = f.url + '?dl=1';
    lbDl.download = f.name;
    lbDl.hidden = !(META && META.allow_download);
    lb.classList.add('show');
    requestAnimationFrame(() => lb.classList.add('vis'));
  }

  function closeLb() {
    lb.classList.remove('vis');
    setTimeout(() => {
      lb.classList.remove('show');
      lbBody.innerHTML = '';
      document.body.style.overflow = '';
    }, 210);
  }

  function step(d) {
    if (!media.length) return;
    idx = (idx + d + media.length) % media.length;
    lb.classList.remove('vis');
    setTimeout(showLb, 130);
  }

  async function previewFile(path, kind) {
    const url = fileUrl(path);
    const info = ((DATA && DATA.files) || []).find((x) => x.path === path);

    // 兜底：不能在线预览的类型（zip / apk / exe …）直接触发下载，
    // 否则会被下面当文本读，结果文件根本下不下来。
    if (!PREVIEWABLE[kind]) {
      if (META && META.allow_download) {
        const a = document.createElement('a');
        a.href = url + '?dl=1';
        a.download = path.split('/').pop();
        document.body.appendChild(a);
        a.click();
        a.remove();
      } else {
        toast('此分享不允许下载', 'err');
      }
      return;
    }

    if (kind === 'pdf') {
      lbBody.innerHTML = '<iframe src="' + url + '#toolbar=0" title="PDF"></iframe>';
    } else {
      if (info && info.size > 4 * 1024 * 1024) {
        toast('文本太大，请直接下载查看', 'err');
        return;
      }
      lbBody.innerHTML = '<pre>加载中…</pre>';
      try {
        const res = await fetch(url);
        let text = await res.text();
        if (text.length > 400000) text = text.slice(0, 400000) + '\n\n…（内容过长，已截断）';
        lbBody.innerHTML = '<pre>' + esc(text) + '</pre>';
      } catch (e) {
        lbBody.innerHTML = '<pre>无法读取该文件</pre>';
      }
    }
    const name = path.split('/').pop();
    lbName.textContent = name;
    lbMeta.textContent = info ? info.size_text : '';
    lbDl.href = url + '?dl=1';
    lbDl.download = name;
    lbDl.hidden = !(META && META.allow_download);
    lb.classList.add('show');
    requestAnimationFrame(() => lb.classList.add('vis'));
    document.body.style.overflow = 'hidden';
  }

  /* ---------------- 上传 ---------------- */
  function upload(files) {
    if (!files || !files.length) return;
    if (!META || !META.allow_upload) { toast('此分享未开启上传', 'err'); return; }
    const list = Array.prototype.slice.call(files);
    let i = 0;
    const next = function () {
      if (i >= list.length) {
        $('upBox').hidden = true;
        toast('已上传 ' + list.length + ' 个文件到「收件箱」', 'ok');
        lastSig = '';
        load(true);
        return;
      }
      const file = list[i++];
      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/upload');
      xhr.setRequestHeader('X-File-Name', encodeURIComponent(file.name));
      xhr.setRequestHeader('Content-Type', 'application/octet-stream');
      $('upBox').hidden = false;
      $('upName').textContent = '(' + i + '/' + list.length + ') ' + file.name;
      $('upPct').textContent = '0%';
      $('upBar').style.width = '0%';
      xhr.upload.onprogress = function (e) {
        if (!e.lengthComputable) return;
        const pct = Math.round((e.loaded / e.total) * 100);
        $('upPct').textContent = pct + '%';
        $('upBar').style.width = pct + '%';
      };
      xhr.onload = function () {
        try {
          const r = JSON.parse(xhr.responseText || '{}');
          if (!r.ok) toast('「' + file.name + '」上传失败：' + (r.error || xhr.status), 'err');
        } catch (e) { toast('「' + file.name + '」上传失败', 'err'); }
        next();
      };
      xhr.onerror = function () { toast('「' + file.name + '」网络错误', 'err'); next(); };
      xhr.send(file);
    };
    next();
  }

  /* ---------------- 事件 ---------------- */
  const VIEW_ICON_GRID = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="2" stroke-linecap="round"><rect x="3" y="3" width="7" height="7" rx="1.6"/>'
    + '<rect x="14" y="3" width="7" height="7" rx="1.6"/><rect x="3" y="14" width="7" height="7" rx="1.6"/>'
    + '<rect x="14" y="14" width="7" height="7" rx="1.6"/></svg>';
  const VIEW_ICON_LIST = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="2" stroke-linecap="round"><path d="M4 6h16"/><path d="M4 12h16"/>'
    + '<path d="M4 18h16"/></svg>';

  function setView(v) {
    document.body.classList.toggle('view-list', v === 'list');
    try { localStorage.setItem('sm_view', v); } catch (e) { /* 忽略 */ }
    $('viewBtn').innerHTML = v === 'list' ? VIEW_ICON_GRID : VIEW_ICON_LIST;
  }

  function init() {
    let view = 'grid';
    try {
      const q = new URLSearchParams(location.search).get('view');
      view = q || localStorage.getItem('sm_view') || 'grid';
    } catch (e) { /* 忽略 */ }
    setView(view);

    $('viewBtn').onclick = () => {
      setView(document.body.classList.contains('view-list') ? 'grid' : 'list');
    };
    $('searchBtn').onclick = () => {
      const bar = $('searchBar');
      bar.hidden = !bar.hidden;
      $('searchBtn').classList.toggle('on', !bar.hidden);
      if (!bar.hidden) searchEl.focus();
      else { searchEl.value = ''; filter = ''; render(); }
    };
    $('refreshBtn').onclick = () => { lastSig = ''; load(true); loadMeta(); };
    $('topBtn').onclick = () => window.scrollTo({ top: 0, behavior: 'smooth' });
    $('gateBtn').onclick = doLogin;
    $('gateInput').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });
    searchEl.addEventListener('input', () => {
      filter = searchEl.value;
      renderLimit = RENDER_CHUNK;
      render();
    });

    $('lbClose').onclick = closeLb;
    lb.addEventListener('click', (e) => {
      if (e.target === lb || e.target === lbBody) closeLb();
      if (e.target.tagName === 'IMG') e.target.classList.toggle('zoom');
    });
    document.addEventListener('keydown', (e) => {
      if (!lb.classList.contains('show')) {
        if (e.key === '/' && document.activeElement !== searchEl) {
          e.preventDefault();
          window.SM.focusSearch();
        }
        return;
      }
      if (e.key === 'Escape') closeLb();
      if (e.key === 'ArrowRight') step(1);
      if (e.key === 'ArrowLeft') step(-1);
    });
    let tx = 0, ty = 0;
    lb.addEventListener('touchstart', (e) => {
      tx = e.touches[0].clientX; ty = e.touches[0].clientY;
    }, { passive: true });
    lb.addEventListener('touchend', (e) => {
      const dx = e.changedTouches[0].clientX - tx, dy = e.changedTouches[0].clientY - ty;
      if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy)) step(dx < 0 ? 1 : -1);
      else if (dy > 90) closeLb();
    }, { passive: true });

    const onScroll = () => {
      topEl.classList.toggle('stuck', window.scrollY > 6);
      $('topBtn').classList.toggle('off', window.scrollY < 420);
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    onScroll();

    initUpload();
    if (navigator.serviceWorker) navigator.serviceWorker.register('/sw.js').catch(() => {});
    setInterval(() => {
      if (document.hidden || !META) return;
      if (lb.classList.contains('show')) return;
      load();
    }, 15000);
  }

  function initUpload() {
    const mask = $('dropMask');
    let depth = 0;
    const allow = () => META && META.allow_upload;
    window.addEventListener('dragenter', (e) => {
      if (!allow()) return;
      e.preventDefault(); depth++; mask.classList.add('on');
    });
    window.addEventListener('dragover', (e) => { if (allow()) e.preventDefault(); });
    window.addEventListener('dragleave', () => {
      if (!allow()) return;
      depth = Math.max(0, depth - 1);
      if (!depth) mask.classList.remove('on');
    });
    window.addEventListener('drop', (e) => {
      if (!allow()) return;
      e.preventDefault(); depth = 0; mask.classList.remove('on');
      if (e.dataTransfer && e.dataTransfer.files) upload(e.dataTransfer.files);
    });
    $('upBtn').onclick = () => $('upInput').click();
    $('upInput').onchange = (e) => { upload(e.target.files); e.target.value = ''; };
  }

  async function doLogin() {
    const pwd = $('gateInput').value;
    if (!pwd) return;
    $('gateErr').hidden = true;
    const r = await api('/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pwd }),
    });
    if (r.data && r.data.ok) {
      $('gateInput').value = '';
      await loadMeta();
    } else {
      $('gateErr').hidden = false;
      $('gateErr').textContent = (r.data && r.data.error) || '密码不正确';
      $('gateInput').select();
    }
  }

  /* ---------------- 对外接口 ---------------- */
  window.SM = {
    go(path) {
      cur = path || '';
      lastSig = '';
      searchEl.value = '';
      filter = '';
      renderLimit = RENDER_CHUNK;
      syncUrl();
      load();
    },
    openLb: openLb,
    previewFile: previewFile,
    focusSearch() {
      $('searchBar').hidden = false;
      $('searchBtn').classList.add('on');
      searchEl.focus();
    },
  };

  document.addEventListener('DOMContentLoaded', () => { init(); loadMeta(); });
})();
