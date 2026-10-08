/* ============================================================
   跑团宇宙 · wiki 层（搜索 / 独立链接 / 建议 / 审核）
   ------------------------------------------------------------
   设计原则：**不侵入 app.js**。app.js 只管画图，这一层靠
     · 事件代理（capture 阶段）读它的状态
     · 直接调用它已有的 openEntity / openDossier / goOverview
   来接上 wiki 的能力，所以 app.js 的渲染逻辑一行都不用动。

   四个能力：
     1. 全文搜索（角色/别名/身份/简介/事件/团/关系，Ctrl+K 或 /）
     2. 独立链接（#/g/<团> · #/c/<角色id> · #/s/<词> · #/review）
        —— 可分享、可刷新、可前进后退
     3. 建议修改 / 建议关系 / 建议删除（匿名提交，进待审箱）
     4. 管理员审核页（口令 → 通过/驳回 → 导出补丁）
   ============================================================ */
(function () {
  'use strict';

  var APP = window.APP || {};
  var N = window.NET;
  if (!N) { console.error('[wiki] window.NET 不存在'); return; }
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  /* ⚠️ app.js 里的 CH / S 是 `const`，**不会**挂到 window 上（只进全局词法环境），
     所以这里必须从 app.js 末尾导出的 window.APP 里拿 —— 直接写 window.CH 会拿到 undefined，
     表现就是「#/c/<id> 直达打不开档案」。2026-10-06 踩过。 */
  var CH = APP.CH || new Map();
  var S = APP.S || { view: 'overview', ent: null, focus: null };

  /* ── 小工具 ─────────────────────────────────────────────── */
  function E(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function rx(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }
  function hl(text, terms) {
    var s = E(text);
    terms.forEach(function (t) {
      if (!t) return;
      try { s = s.replace(new RegExp(rx(t), 'gi'), function (m) { return '<mark>' + m + '</mark>'; }); } catch (e) { }
    });
    return s;
  }
  function toast(msg, bad) {
    var el = $('#wikiToast');
    if (!el) {
      el = document.createElement('div');
      el.id = 'wikiToast'; el.className = 'wiki-toast';
      document.body.appendChild(el);
    }
    el.textContent = msg;
    el.className = 'wiki-toast on' + (bad ? ' bad' : '');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.className = 'wiki-toast'; }, 3200);
  }
  function api(path, opt) {
    opt = opt || {};
    opt.headers = Object.assign({ 'content-type': 'application/json' }, opt.headers || {});
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; });
    });
  }

  /* ══════════════════════════════════════════════════════════
     一、搜索
     ══════════════════════════════════════════════════════════ */
  var IDX = [], SE_HITS = [], SE_SEL = 0, SE_TERMS = [], TAGSEEN = {};

  /** 把 attrs 拍平成可搜索文本：`性别 女 职业 作家 侦探` */
  function attrsText(at) {
    if (!at || typeof at !== 'object') return '';
    return Object.keys(at).map(function (k) {
      var v = at[k];
      return k + ' ' + (Array.isArray(v) ? v.join(' ') : v);
    }).join(' ');
  }

  function buildIndex() {
    var items = [];
    TAGSEEN = {};
    (N.chars || []).forEach(function (c) {
      var ev = (c.events || []).map(function (g) { return (g.items || []).join(' '); }).join(' ');
      items.push({
        t: 'char', id: c.id, name: c.name, badge: c.kind || 'NPC',
        sub: (c.identity || '').slice(0, 60),
        groups: c.groups || [], note: c.note || '',
        hay: [c.name, (c.aliases || []).join(' '), c.identity, c.note, c.played_by,
          (c.groups || []).join(' '), (c.tags || []).join(' '), attrsText(c.attrs), ev]
          .join('\n').toLowerCase(),
      });
      /* 每个「维度=值」也做成一条可搜、可跳的标签条目（点进去就是标签筛选页） */
      Object.keys(c.attrs || {}).forEach(function (dim) {
        var v = c.attrs[dim];
        (Array.isArray(v) ? v : [v]).forEach(function (val) {
          if (val == null || val === '') return;
          var key = dim + '=' + val;
          if (!TAGSEEN[key]) {
            TAGSEEN[key] = {
              t: 'tag', dim: dim, val: String(val), ids: [],
              name: dim + '：' + val, badge: '标签', sub: '',
              hay: (dim + ' ' + val).toLowerCase(),
            };
            items.push(TAGSEEN[key]);
          }
          TAGSEEN[key].ids.push(c.id);
        });
      });
    });
    Object.keys(TAGSEEN).forEach(function (k) {
      TAGSEEN[k].sub = TAGSEEN[k].ids.length + ' 个角色';
    });
    (N.groups || []).forEach(function (g) {
      items.push({
        t: 'group', id: g.name, name: g.name, badge: '团',
        sub: (g.count || 0) + ' 人', groups: [g.name], hay: (g.name + ' ' + (g.en || '')).toLowerCase(),
      });
    });
    (N.rels || []).forEach(function (r) {
      var A = CH && CH.get(r.a), B = CH && CH.get(r.b);
      if (!A || !B) return;
      items.push({
        t: 'rel', a: r.a, b: r.b, name: A.name + ' —' + r.type + '→ ' + B.name,
        badge: r.type, sub: (r.event || r.raw || '').slice(0, 60), groups: A.groups || [],
        hay: [A.name, B.name, r.type, r.raw, r.event].join(' ').toLowerCase(),
      });
    });
    IDX = items;
  }
  window.__wikiReindex = buildIndex;   // 覆盖层应用后可以重建

  function search(q) {
    var terms = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
    if (!terms.length) return [];
    var out = [];
    for (var i = 0; i < IDX.length; i++) {
      var it = IDX[i], score = 0, ok = true;
      for (var j = 0; j < terms.length; j++) {
        var t = terms[j];
        var nm = it.name.toLowerCase(), ip = nm.indexOf(t), ih = it.hay.indexOf(t);
        if (ip < 0 && ih < 0) { ok = false; break; }
        score += ip === 0 ? 14 : (ip > 0 ? 7 : 0);
        if (ih >= 0) score += 2;
      }
      if (!ok) continue;
      if (it.t === 'char') score += 5;
      else if (it.t === 'group') score += 3;
      out.push({ it: it, s: score });
    }
    out.sort(function (a, b) { return b.s - a.s; });
    return out.slice(0, 50).map(function (x) { return x.it; });
  }

  function renderHits(q) {
    var box = $('#seList');
    SE_TERMS = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
    SE_HITS = search(q);
    SE_SEL = 0;
    if (!q.trim()) {
      box.innerHTML = '<div class="se-empty">输入关键词开始搜索：<br>角色名 / 别名 / 身份 / 简介 / 事件 / 团名 / 关系类型（空格分隔可多词）</div>';
      return;
    }
    if (!SE_HITS.length) { box.innerHTML = '<div class="se-empty">没搜到「' + E(q) + '」<br><span class="dim">换个词，或者用更短的词试试</span></div>'; return; }
    box.innerHTML = SE_HITS.map(function (h, i) {
      var badge = h.t === 'group' ? '团' : (h.t === 'rel' ? '关系' : h.badge);
      return '<div class="se-item' + (i === 0 ? ' on' : '') + '" data-i="' + i + '">' +
        '<span class="se-badge b-' + h.t + '">' + E(badge) + '</span>' +
        '<span class="se-main"><b>' + hl(h.name, SE_TERMS) + '</b>' +
        (h.sub ? '<i>' + hl(h.sub, SE_TERMS) + '</i>' : '') + '</span>' +
        '<span class="se-go">↵</span></div>';
    }).join('');
  }

  function openSearch(q) {
    $('#search').classList.add('on');
    $('#seInput').value = q || '';
    renderHits(q || '');
    setTimeout(function () { $('#seInput').focus(); }, 30);
  }
  function closeSearch() { $('#search').classList.remove('on'); }

  function hitOpen(h) {
    if (!h) return;
    closeSearch();
    if (h.t === 'group') { location.hash = '#/g/' + encodeURIComponent(h.id); return; }
    if (h.t === 'char') { location.hash = '#/c/' + encodeURIComponent(h.id); return; }
    if (h.t === 'tag') { location.hash = '#/tags/' + encodeURIComponent(h.dim + '=' + h.val); return; }
    if (h.t === 'rel') {
      var A = CH.get(h.a);
      var g = (A && A.groups && A.groups[0]) || null;
      if (g) { location.hash = '#/c/' + encodeURIComponent(h.a); }
      return;
    }
  }

  function moveSel(d) {
    if (!SE_HITS.length) return;
    SE_SEL = Math.max(0, Math.min(SE_HITS.length - 1, SE_SEL + d));
    $$('#seList .se-item').forEach(function (el, i) { el.classList.toggle('on', i === SE_SEL); });
    var cur = $('#seList .se-item.on');
    if (cur && cur.scrollIntoView) cur.scrollIntoView({ block: 'nearest' });
  }

  /* ══════════════════════════════════════════════════════════
     二、路由（独立链接 / 可分享 / 可后退）
     ══════════════════════════════════════════════════════════ */
  var NAVING = false, DOS_ID = null;

  function parseHash() {
    var h = location.hash.replace(/^#\/?/, '');
    var seg = h.split('/').filter(Boolean).map(decodeURIComponent);
    if (!seg.length) return { v: 'overview' };
    if (seg[0] === 'g' && seg[1]) return { v: 'group', key: seg.slice(1).join('/') };
    if (seg[0] === 'c' && seg[1]) return { v: 'char', id: seg[1] };
    if (seg[0] === 'review') return { v: 'review' };
    if (seg[0] === 'edit') return { v: 'edit', id: seg[1] || null };
    if (seg[0] === 'tags') return { v: 'tags', tag: seg[1] ? seg.slice(1).join('/') : null };
    if (seg[0] === 'portal') return { v: 'portal', tab: seg[1] || 'recent' };
    if (seg[0] === 's') return { v: 'search', q: seg.slice(1).join('/') };
    return { v: 'overview' };
  }

  /** 静默收起某个覆盖层（不动 hash —— 路由切换时用，避免和 hashchange 打架）*/
  function hidePanel(sel) { var e = $(sel); if (e) e.classList.remove('on'); }

  function applyRoute(r) {
    NAVING = true;
    try {
      /* ⚠️ 切视图时必须把**互斥的覆盖层都收起来**：
         2026-10-06 踩过 —— 只关了标签页没关审核页，结果「切到角色档案」时
         审核页还盖在上面，而断言只查 DOM（元素确实注入了）就全绿了，截图一看才发现。
         凡是"面板类"的 UI，路由切换一律先清场。 */
      var keep = r.v;                       // 'review' / 'tags' / 'search' / 'edit' 之一可不收起
      if (keep !== 'review') hidePanel('#review');
      if (keep !== 'tags') hidePanel('#tags');
      if (keep !== 'search') hidePanel('#search');
      if (keep !== 'edit') hidePanel('#editor');
      if (keep !== 'portal') hidePanel('#portal');
      /* 深链进来时首页那层也必须收起 —— 否则分享出去的 `#/c/xxx` 打开后
         看到的还是「进入档案库」首页，而不是角色档案（2026-10-06 踩过）。
         `#/` 例外：首屏就该停在首页让用户点「进入档案库」。 */
      if (r.v !== 'overview') hidePanel('#home');

      if (r.v === 'overview') { closeDossier(); if (S.view !== 'overview') goOverview(); }
      /* ⚠️ `#/g/<团>` 必须**无条件重画**：2026-10-06 实测过一次「深链落地但卡片网是空的」——
         app 层若已经把 `S.ent` 设成同一个团，旧写法 `if (S.ent !== r.key) openEntity(...)`
         就会短路，什么都不画（而首页恰好又被 hidePanel 收起了 → 整页空白）。
         openEntity 幂等（它自己会重算布局），重复调用只是重画一次，代价可以忽略。 */
      else if (r.v === 'group') { closeDossier(); openEntity(r.key); }
      else if (r.v === 'char') {
        var c = CH.get(r.id);
        if (!c) { toast('找不到角色 ' + r.id, true); NAVING = false; return; }
        var g = (c.groups && c.groups[0]) || null;
        if (g && S.ent !== g) openEntity(g);
        DOS_ID = r.id;
        openDossier(r.id);
      } else if (r.v === 'review') { openReview(); }
      else if (r.v === 'tags') { openTags(r.tag); }
      else if (r.v === 'portal') {
        /* ⚠️ portal.js 是**动态加载**的（wiki-boot 在 wiki.js 之后才 append 它），
           首屏路由可能赶在它之前跑 —— 那时 `window.__portalOpen` 还不存在。
           旧写法直接跳过 → 「深链 #/portal 打不开」。这里补一次延迟重试。 */
        if (window.__portalOpen) window.__portalOpen(r.tab);
        else setTimeout(function () {
          if (window.__portalOpen && String(location.hash).indexOf('#/portal') === 0) {
            window.__portalOpen(parseHash().tab);
          }
        }, 260);
      }
      else if (r.v === 'edit') { if (window.__editorOpen) window.__editorOpen(r.id); }
      else if (r.v === 'search') { openSearch(r.q); }
    } catch (e) {
      console.warn('[wiki] 路由失败', e);
    }
    NAVING = false;
  }

  function curHash() {
    if ($('#review').classList.contains('on')) return '#/review';
    /* ⚠️ 编辑器这一条要带上**当前编辑的角色 id**，否则任何一次 syncHash() 都会把
       `#/edit/td_dianyu` 抹成 `#/edit` —— 表现就是「点编辑跳进去了，但地址栏丢了角色，
       刷新之后只剩空编辑器」。2026-10-06 回归测试抓到的。 */
    if ($('#editor') && $('#editor').classList.contains('on')) {
      var editingId = window.__editorId ? window.__editorId() : null;
      return '#/edit' + (editingId ? '/' + encodeURIComponent(editingId) : '');
    }
    if ($('#tags') && $('#tags').classList.contains('on')) return '#/tags';
    if ($('#portal') && $('#portal').classList.contains('on')) return '#/portal';
    if ($('#search').classList.contains('on')) return '#/s/' + encodeURIComponent($('#seInput').value || '');
    if ($('#dossier').classList.contains('on') && DOS_ID) return '#/c/' + encodeURIComponent(DOS_ID);
    if (S.view === 'entity' && S.ent) return '#/g/' + encodeURIComponent(S.ent);
    return '#/';
  }
  function syncHash() {
    if (NAVING) return;
    var want = curHash();
    if (location.hash !== want) {
      try { history.replaceState(null, '', want); } catch (e) { location.hash = want; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     三、建议表单（匿名提交 → 进待审箱）
     ══════════════════════════════════════════════════════════ */
  var FORM_CTX = null;

  function fieldHtml(f) {
    var v = f.value == null ? '' : f.value;
    var label = '<label class="wf-label">' + E(f.label) +
      (f.hint ? '<i>' + E(f.hint) + '</i>' : '') + '</label>';
    if (f.type === 'textarea') {
      return '<div class="wf-row">' + label +
        '<textarea class="wf-in" data-f="' + f.name + '" rows="' + (f.rows || 3) + '">' + E(v) + '</textarea></div>';
    }
    return '<div class="wf-row">' + label +
      '<input class="wf-in" data-f="' + f.name + '" type="text" value="' + E(v) + '"></div>';
  }

  function openForm(title, desc, fields, submitText) {
    var m = $('#wikiModal');
    m.classList.add('on');
    $('#wmTitle').textContent = title;
    $('#wmDesc').innerHTML = desc || '';
    $('#wmFields').innerHTML = fields.map(fieldHtml).join('') +
      '<div class="wf-row"><label class="wf-label">署名<i>可不填</i></label>' +
      '<input class="wf-in" data-f="__author" type="text" value="' + E(localStorage.getItem('sjt-wiki-author') || '') + '"></div>';
    $('#wmSubmit').textContent = submitText || '提交建议';
    m.querySelector('.wf-in').focus();
  }
  function closeForm() { $('#wikiModal').classList.remove('on'); FORM_CTX = null; }

  function collectForm() {
    var out = {};
    $$('#wmFields .wf-in').forEach(function (el) {
      var k = el.dataset.f;
      if (k === '__author') { out.__author = el.value.trim(); return; }
      out[k] = el.value.trim();
    });
    return out;
  }

  /* attrs ⇄ 文本：一行一个「维度: 值」，值多个用「、」分隔，清空该行表示删除该维度 */
  function attrsToText(at) {
    if (!at || typeof at !== 'object') return '';
    return Object.keys(at).map(function (k) {
      var v = at[k];
      return k + ': ' + (Array.isArray(v) ? v.join('、') : v);
    }).join('\n');
  }
  function textToAttrs(txt) {
    var out = {};
    String(txt || '').split(/\r?\n/).forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var i = line.search(/[:：]/);
      var k = (i < 0 ? line : line.slice(0, i)).trim();
      var v = i < 0 ? '' : line.slice(i + 1).trim();
      if (!k) return;
      if (!v) { out[k] = null; return; }          // 留空 = 删掉这个维度
      var vals = v.split(/[、,，;；\/|]+/).map(function (x) { return x.trim(); }).filter(Boolean);
      out[k] = vals.length > 1 ? vals : (vals[0] || null);
    });
    return out;
  }

  /* ── 建议：修改角色（含所有属性标签）───────────────────── */
  function suggestEdit(id) {
    var c = CH.get(id); if (!c) return;
    FORM_CTX = { kind: 'char_update', target_id: id };
    openForm('建议修改 · ' + c.name,
      '改动会先进<b>待审箱</b>，管理员通过后才会生效（原始数据不会被直接改写）。<br>' +
      '留空表示"不改这一项"。',
      [
        { name: 'name', label: '名字', value: c.name },
        { name: 'aliases', label: '别名', hint: '用中文逗号或顿号分隔', value: (c.aliases || []).join('、') },
        { name: 'identity', label: '身份 / 设定', type: 'textarea', rows: 2, value: c.identity || '' },
        { name: 'played_by', label: '扮演 / 创作者', value: c.played_by || '' },
        { name: 'tags', label: '系统标签', hint: 'PC / NPC / BOSS / 跨团 / KP（决定卡片配色与阵营块）', value: (c.tags || []).join('、') },
        { name: 'attrs', label: '属性标签', type: 'textarea', rows: 7, value: attrsToText(c.attrs),
          hint: '每行「维度: 值」，值多个用「、」分隔；清空某行=删掉该维度。例：性别: 女　职业: 作家、侦探　种族: 鬼' },
        { name: 'note', label: '简介 / 备注', type: 'textarea', rows: 5, value: c.note || '' },
        { name: 'profile', label: '详细设定（wiki 正文）', type: 'textarea', rows: 14, value: c.profile || '',
          hint: '## 小节名（简介/背景故事/能力与装备/人物关系/台词/杂项）· - 列表 · **粗体** · *斜体* · ==关键词==（高亮）· > 台词' },
        { name: 'reason', label: '理由 / 出处', hint: '必填：说明为什么改，方便审核', type: 'textarea', rows: 2 },
      ], '提交修改建议');
  }

  /* ── 建议：删除角色 ─────────────────────────────────────── */
  function suggestDelete(id) {
    var c = CH.get(id); if (!c) return;
    FORM_CTX = { kind: 'char_delete', target_id: id };
    openForm('建议删除 · ' + c.name,
      '⚠️ 这是<b>删除建议</b>：管理员通过后，该角色会从站点上消失（含其所有关系边）。<br>' +
      '请务必写清理由，删除是很重的操作。',
      [{ name: 'reason', label: '删除理由', hint: '必填', type: 'textarea', rows: 3 }],
      '提交删除建议');
  }

  /* ── 建议：新增关系 ─────────────────────────────────────── */
  function suggestRelation(id) {
    var c = CH.get(id); if (!c) return;
    var opts = (N.chars || []).filter(function (x) { return x.id !== id; })
      .sort(function (a, b) { return (a.name || '').localeCompare(b.name || ''); });
    FORM_CTX = { kind: 'rel_create', target_id: id };
    openForm('建议关系 · 从「' + c.name + '」出发',
      '填「对方」的角色 id（可从搜索结果里复制）。关系会进待审箱。',
      [
        { name: 'to', label: '对方角色 id', hint: '例如 yy_liulong；名字：' + opts.slice(0, 3).map(function (o) { return o.name; }).join('、') + '…', value: '' },
        { name: 'type', label: '关系类型', hint: '受控词表：亲属 / 师徒 / 敌对 / 友谊 / 从属 …', value: '友谊' },
        { name: 'strength', label: '强度', hint: '强 / 中 / 弱', value: '中' },
        { name: 'event', label: '出处 / 事件', type: 'textarea', rows: 3 },
        { name: 'reason', label: '理由', type: 'textarea', rows: 2 },
      ], '提交关系建议');
  }

  /* ── 建议：新建角色 ─────────────────────────────────────── */
  function suggestCreate() {
    FORM_CTX = { kind: 'char_create', target_id: null };
    openForm('建议新建条目',
      '新建的角色会先进待审箱；管理员通过后出现在站点上（生产库由管理员另行同步）。',
      [
        { name: 'id', label: '唯一 id', hint: '英文小写+下划线，例如 xx_newnpc', value: '' },
        { name: 'name', label: '名字', value: '' },
        { name: 'groups', label: '出场团', hint: '填团名，逗号分隔', value: '' },
        { name: 'tags', label: '系统标签', hint: 'PC / NPC / BOSS / 跨团 / KP', value: 'NPC' },
        { name: 'identity', label: '身份 / 设定', type: 'textarea', rows: 2 },
        { name: 'attrs', label: '属性标签', type: 'textarea', rows: 5,
          hint: '每行「维度: 值」，例如：性别: 女　职业: 作家、侦探　种族: 鬼' },
        { name: 'note', label: '简介 / 备注', type: 'textarea', rows: 4 },
        { name: 'reason', label: '理由 / 出处', type: 'textarea', rows: 2 },
      ], '提交新条目');
  }

  function submitForm() {
    if (!FORM_CTX) return;
    var v = collectForm();
    var kind = FORM_CTX.kind;
    var reason = v.reason || '';
    var author = v.__author || '';
    delete v.reason; delete v.__author;

    var payload = {};
    if (kind === 'char_update' || kind === 'char_create') {
      ['name', 'identity', 'note', 'played_by'].forEach(function (k) { if (v[k]) payload[k] = v[k]; });
      if (v.aliases) payload.aliases = v.aliases.split(/[、,，;；\s]+/).filter(Boolean);
      if (v.groups) payload.groups = v.groups.split(/[、,，;；]+/).map(function (s) { return s.trim(); }).filter(Boolean);
      if (v.tags) payload.tags = v.tags.split(/[、,，;；\s]+/).filter(Boolean);
      if (v.id) payload.id = v.id;
      if (v.attrs !== undefined) {
        var at = textToAttrs(v.attrs);
        if (Object.keys(at).length) payload.attrs = at;
      }
      if (v.profile !== undefined) payload.profile = v.profile;
    } else if (kind === 'rel_create') {
      payload.from = FORM_CTX.target_id;
      payload.to = v.to || '';
      payload.type = v.type || '其他';
      payload.strength = v.strength || '中';
      payload.event = v.event || '';
    } else if (kind === 'rel_update') {
      payload.from = FORM_CTX.from;
      payload.to = FORM_CTX.to;
      if (v.type) payload.type = v.type;
      if (v.strength) payload.strength = v.strength;
      if (v.raw) payload.raw = v.raw;
      if (v.event !== undefined) payload.event = v.event;
    } else if (kind === 'rel_delete') {
      payload.from = FORM_CTX.from;
      payload.to = FORM_CTX.to;
      var seg = String(FORM_CTX.target_id || '').split('|');
      if (seg.length === 3 && seg[2]) payload.type = seg[2];
    } else if (kind === 'char_delete') {
      payload.id = FORM_CTX.target_id;
    }

    if (!reason.trim() && kind !== 'char_create') { toast('请写一下理由（方便审核）', true); return; }
    if (kind === 'rel_create' && !payload.to) { toast('请填对方角色 id', true); return; }
    if (kind === 'char_create' && !payload.id) { toast('请填唯一 id', true); return; }

    var btn = $('#wmSubmit');
    btn.disabled = true; btn.textContent = '提交中…';
    api('/api/suggest', {
      method: 'POST',
      body: JSON.stringify({ kind: kind, target_id: FORM_CTX.target_id, payload: payload, reason: reason, author: author }),
    }).then(function (r) {
      btn.disabled = false; btn.textContent = '提交建议';
      if (r && r.ok) {
        localStorage.setItem('sjt-wiki-author', author);
        closeForm();
        toast('已提交，编号 #' + r.id + ' · 等管理员审核通过后生效');
      } else {
        toast('提交失败：' + ((r && r.error) || '未知错误'), true);
      }
    }).catch(function () {
      btn.disabled = false; btn.textContent = '提交建议';
      toast('提交失败：连不上服务器（本地预览没有后端）', true);
    });
  }

  /* ── 档案页注入操作条 ─────────────────────────────────────
     ⚠️ 2026-10-06 主人要求：**别再摆三个「建议修改 / 建议关系 / 建议删除」**，
        统一成一个按钮 —— 直接跳到这个角色的编辑器（`#/edit/<id>`）。
        提案箱那套后端（/api/suggest + 待审箱）留着不动，只是不再挂在档案页上。 */
  function injectActions(id) {
    var head = $('.dos-head'); if (!head) return;
    var bar = $('#wikiBar');
    if (!bar) {
      bar = document.createElement('div');
      bar.id = 'wikiBar'; bar.className = 'wiki-bar';
      head.parentNode.insertBefore(bar, head.nextSibling);
    }
    var c = CH.get(id);
    var canEdit = !!ED_TOKEN();
    bar.innerHTML =
      '<button class="wb-btn on" data-wb="edit" title="打开这个角色的编辑器">' +
      '✎ 编辑这个角色</button>' +
      '<button class="wb-btn" data-wb="portal" title="门户：最近改动 / 新增条目 / 公告">' +
      '☰ 门户</button>' +
      (canEdit ? '' :
        '<span class="wb-tag" title="保存修改需要编辑器口令（新建条目、上传立绘不需要）">' +
        '改已有条目需口令</span>') +
      '<span class="wb-tag wiki-only-tag"' + (c && c._wiki ? '' : ' style="display:none"') +
      ' title="该条目含已采纳的 wiki 建议，生产库尚未同步">✎ wiki 改动</span>';
  }

  /* 编辑器口令（与 editor.js 同一个键） */
  function ED_TOKEN() {
    try {
      return localStorage.getItem('sjt-edit-token') ||
             localStorage.getItem('trpg-edit-token') || '';
    } catch (e) { return ''; }
  }

  /* ── 档案页：属性标签区（点任意标签 → 跳到标签筛选页）── */
  function injectAttrs(id) {
    var bar = $('#wikiBar'); if (!bar) return;
    var box = $('#wikiAttrs');
    if (!box) {
      box = document.createElement('div');
      box.id = 'wikiAttrs'; box.className = 'wiki-attrs';
      bar.insertAdjacentElement('afterend', box);
    }
    var c = CH.get(id) || {};
    var at = (c && c.attrs) || {};
    var dims = Object.keys(at).filter(function (k) {
      var v = at[k];
      return Array.isArray(v) ? v.length : (v != null && v !== '');
    });
    box.innerHTML =
      '<div class="wa-head">属性标签 <i>' +
      (dims.length ? dims.length + ' 个维度' : '还没有属性') +
      ' · <a class="wa-all" href="#/tags">看全部标签 ›</a></i></div>' +
      (dims.length
        ? '<div class="wa-list">' + dims.map(function (k) {
            var v = at[k];
            var vals = (Array.isArray(v) ? v : [v]);
            return '<span class="wa-dim">' + E(k) + '</span>' +
              vals.map(function (x) {
                return '<a class="wa-tag" data-tag="' + E(k + '=' + x) + '" ' +
                  'title="筛选所有「' + E(k) + '＝' + E(x) + '」的角色">' + E(x) + '</a>';
              }).join('');
          }).join('') + '</div>'
        : '<div class="wa-empty">还没有属性标签 —— 用上面的「✎ 建议修改」，在「属性标签」里按 <b>维度: 值</b> 一行一条填（性别 / 种族 / 职业 / 阵营 …）</div>');
  }

  /* ── wiki 正文渲染 ────────────────────────────────────────────
     只支持这套 Markdown 子集，**先把整行转义再替换标记**（顺序很关键：
     反过来的话 `&lt;script&gt;` 会被当成标签；先转义就杜绝了 XSS）：
        ## 小节名      分节标题
        - 列表项       无序列表
        **粗体**  *斜体*  ~~删除~~
        ==关键词==     金色高亮（专有名词）
        > 台词         台词块（特殊样式）                                     */
  function renderWiki(md) {
    if (!md) return '';
    var lines = String(md).replace(/\r\n?/g, '\n').split('\n');
    var out = [], buf = [], mode = null;

    function inline(s) {
      var t = E(s);
      t = t.replace(/==([^=]+)==/g, '<mark class="pf-key">$1</mark>');
      t = t.replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>');
      t = t.replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
      t = t.replace(/~~([^~]+)~~/g, '<s>$1</s>');
      return t;
    }
    function flush() {
      if (mode === 'ul' && buf.length) out.push('<ul class="pf-ul">' + buf.join('') + '</ul>');
      else if (mode === 'quote' && buf.length) out.push('<blockquote class="pf-quote">' + buf.join('') + '</blockquote>');
      else if (buf.length) out.push('<p>' + buf.join('<br>') + '</p>');
      buf = []; mode = null;
    }
    lines.forEach(function (raw) {
      var line = raw.replace(/\s+$/, '');
      var h = line.match(/^#{2,4}\s*(.+)$/);
      var li = line.match(/^\s*[-*]\s+(.+)$/);
      var q = line.match(/^>\s?(.*)$/);
      if (h) { flush(); out.push('<h4 class="pf-h">' + inline(h[1]) + '</h4>'); return; }
      if (li) { if (mode !== 'ul') { flush(); mode = 'ul'; } buf.push('<li>' + inline(li[1]) + '</li>'); return; }
      if (q) {
        if (!q[1].trim()) { flush(); return; }            // `>` 单独一行 → 当作分段，别渲染成空段落
        if (mode !== 'quote') { flush(); mode = 'quote'; }
        buf.push('<p>' + inline(q[1]) + '</p>'); return;
      }
      if (!line.trim()) { flush(); return; }
      if (mode) flush();
      buf.push(inline(line));
    });
    flush();
    return out.join('');
  }
  window.__wikiRender = renderWiki;      // 编辑器（editor.js）复用同一套渲染，保证预览一致

  /* ── 档案页：详细设定区 ─────────────────────────────────────── */
  function injectProfile(id) {
    var anchor = $('#wikiAttrs') || $('#wikiBar');
    if (!anchor) return;
    var box = $('#wikiProfile');
    if (!box) {
      box = document.createElement('div');
      box.id = 'wikiProfile'; box.className = 'wiki-profile';
      anchor.insertAdjacentElement('afterend', box);
    }
    var c = CH.get(id) || {};
    var md = c.profile || '';
    var src = c.profile_src
      ? '<span class="pf-src" title="内容来源">' + E(c.profile_src) + '</span>' : '';
    box.innerHTML =
      '<div class="pf-head">详细设定 ' + src + '</div>' +
      (md
        ? '<div class="pf-body">' + renderWiki(md) + '</div>'
        : '<div class="pf-empty">这个角色还没有详细设定。<br>' +
          '<span class="dim">点上面的「✎ 建议修改」就能补 —— 支持 ' +
          '<b>##</b> 分节、<b>-</b> 列表、<b>**粗体**</b>、<b>==关键词==</b>（高亮）、' +
          '<b>&gt;</b> 台词块。</span></div>');
  }

  /* ── 关系网：改 / 删（原来只能"新增关系"）─────────────────
     app.js 的 openDossier 按 `强度 → 关系人度数` 排序渲染 `.dos-rel`，
     这里**复刻同一套排序**，好让 DOM 里第 i 条与 relsOf() 的第 i 条一一对应。 */
  var SORD = { '强': 0, '中': 1, '弱': 2, '': 3 };

  function relsOf(id) {
    var ADJ = APP.ADJ;
    if (!ADJ) return [];
    return (ADJ.get(id) || []).map(function (x) {
      return { o: x.o, r: x.r, out: !!x.out, c: CH.get(x.o) };
    }).filter(function (x) { return x.c; })
      .sort(function (a, b) {
        var sa = SORD[a.r.strength] != null ? SORD[a.r.strength] : 3;
        var sb = SORD[b.r.strength] != null ? SORD[b.r.strength] : 3;
        return (sa - sb) || ((b.c.degree || 0) - (a.c.degree || 0));
      });
  }

  /** 找这条关系在 data.js 里的**完整对象**（DOM 上只存了 a/b/type）*/
  function fullRel(a, b, type) {
    var all = N.rels || [];
    for (var i = 0; i < all.length; i++) {
      if (all[i].a === a && all[i].b === b && all[i].type === type) return all[i];
    }
    for (var j = 0; j < all.length; j++) {
      if (all[j].a === a && all[j].b === b) return all[j];
    }
    return null;
  }

  function injectRelActions(id) {
    var list = relsOf(id);
    var nodes = $$('#dosRels .dos-rel');
    if (!list.length || nodes.length !== list.length) return;   // 对不上就老实不动
    nodes.forEach(function (el, i) {
      if (el.querySelector('.rel-acts')) return;
      var r = list[i].r;
      el.dataset.relFrom = r.a || '';
      el.dataset.relTo = r.b || '';
      el.dataset.relType = r.type || '';
      var bar = document.createElement('div');
      bar.className = 'rel-acts';
      bar.innerHTML = '<button class="wb-btn mini" data-relact="edit" title="改这条关系">✎ 改</button>' +
        '<button class="wb-btn mini danger" data-relact="del" title="删这条关系">🗑 删</button>';
      el.appendChild(bar);
    });
  }

  function suggestRelUpdate(r) {
    if (!r) return;
    var A = CH.get(r.a), B = CH.get(r.b);
    FORM_CTX = { kind: 'rel_update', target_id: r.a + '|' + r.b + '|' + (r.type || ''), from: r.a, to: r.b };
    openForm('建议修改关系 · ' + (A ? A.name : r.a) + ' ↔ ' + (B ? B.name : r.b),
      '这里改的是<b>已有关系</b>（类型 / 强度 / 出处）。通过后站点立刻生效，生产库由管理员另行同步。',
      [
        { name: 'type', label: '关系类型', hint: '受控词表：亲属 / 师徒 / 敌对 / 友谊 / 从属 …', value: r.type || '' },
        { name: 'strength', label: '强度', hint: '强 / 中 / 弱', value: r.strength || '中' },
        { name: 'raw', label: '类型原串', hint: '可选：原始写法（如「兄妹」「指使/求助」）', value: r.raw || '' },
        { name: 'event', label: '出处 / 事件', type: 'textarea', rows: 3, value: r.event || '' },
        { name: 'reason', label: '理由', type: 'textarea', rows: 2 },
      ], '提交关系修改');
  }

  function suggestRelDelete(r) {
    if (!r) return;
    var A = CH.get(r.a), B = CH.get(r.b);
    FORM_CTX = { kind: 'rel_delete', target_id: r.a + '|' + r.b + '|' + (r.type || ''), from: r.a, to: r.b };
    openForm('建议删除关系 · ' + (A ? A.name : r.a) + ' —' + (r.type || '') + '→ ' + (B ? B.name : r.b),
      '⚠️ 通过后这条关系会从关系网上消失（两端角色还在）。请写清理由 —— 删关系是很重的操作。',
      [{ name: 'reason', label: '删除理由', hint: '必填', type: 'textarea', rows: 3 }],
      '提交删除建议');
  }

  /* ══════════════════════════════════════════════════════════
     四、管理端：审核页
     ══════════════════════════════════════════════════════════ */
  var RV = { items: [], token: '' };

  function getToken() { return localStorage.getItem('sjt-wiki-token') || ''; }

  function describe(it) {
    var p = it.payload || {};
    var c = it.target_id && CH ? CH.get(it.target_id) : null;
    var rows = [];
    function cmp(label, now, next) {
      if (next === undefined) return;
      if (String(now == null ? '' : now) === String(next)) return;
      rows.push('<div class="rv-diff"><b>' + E(label) + '</b>' +
        '<span class="old">' + E(String(now == null ? '（空）' : now).slice(0, 200)) + '</span>' +
        '<span class="arrow">→</span>' +
        '<span class="new">' + E(String(next).slice(0, 200)) + '</span></div>');
    }
    if (it.kind === 'char_update') {
      cmp('名字', c && c.name, p.name);
      cmp('身份', c && c.identity, p.identity);
      cmp('扮演', c && c.played_by, p.played_by);
      cmp('别名', c && (c.aliases || []).join('、'), p.aliases && p.aliases.join('、'));
      cmp('系统标签', c && (c.tags || []).join('、'), p.tags && p.tags.join('、'));
      cmp('简介', c && c.note, p.note);
      /* 详细设定通常几千字，审核页只给「长度 + 开头摘要」，要看全文点开角色页 */
      if (p.profile !== undefined) {
        var op = (c && c.profile) || '';
        rows.push('<div class="rv-diff"><b>详细设定</b>' +
          '<span class="old">' + E(op ? op.slice(0, 90) + '…（' + op.length + ' 字）' : '（空）') + '</span>' +
          '<span class="arrow">→</span>' +
          '<span class="new">' + E(p.profile ? p.profile.slice(0, 90) + '…（' + p.profile.length + ' 字）' : '（清空）') +
          '</span></div>');
      }
      /* 属性标签逐个维度对比（值是 null 表示删除该维度） */
      if (p.attrs && typeof p.attrs === 'object') {
        var cur = (c && c.attrs) || {};
        Object.keys(p.attrs).forEach(function (dim) {
          var nv = p.attrs[dim];
          var ov = cur[dim];
          var ovs = ov == null ? '（无）' : (Array.isArray(ov) ? ov.join('、') : String(ov));
          if (nv === null) {
            rows.push('<div class="rv-diff"><b>属性·' + E(dim) + '</b><span class="old">' + E(ovs) +
              '</span><span class="arrow">→</span><span class="new">（删除该维度）</span></div>');
          } else {
            cmp('属性·' + dim, ovs, Array.isArray(nv) ? nv.join('、') : nv);
          }
        });
      }
    } else if (it.kind === 'rel_update') {
      var rp = String(it.target_id || '').split('|');
      var oldR = rp.length === 3 ? fullRel(rp[0], rp[1], rp[2]) : null;
      if (!oldR) oldR = fullRel(p.from, p.to, '');
      var ua = p.from && CH ? CH.get(p.from) : null;
      var ub = p.to && CH ? CH.get(p.to) : null;
      rows.push('<div class="rv-diff">改已有关系：<b>' + E(ua ? ua.name : p.from) + '</b> ↔ <b>' +
        E(ub ? ub.name : p.to) + '</b></div>');
      if (oldR) {
        cmp('类型', oldR.type, p.type);
        cmp('强度', oldR.strength, p.strength);
        cmp('原串', oldR.raw, p.raw);
        cmp('出处', oldR.event, p.event);
      }
    } else if (it.kind === 'rel_delete') {
      var dp = String(it.target_id || '').split('|');
      var oldD = dp.length === 3 ? fullRel(dp[0], dp[1], dp[2]) : null;
      var da = oldD ? oldD.a : p.from, db = oldD ? oldD.b : p.to;
      var na = CH && CH.get(da), nb2 = CH && CH.get(db);
      rows.push('<div class="rv-diff danger">删除关系：<b>' + E(na ? na.name : da) + '</b> —' +
        E(oldD ? oldD.type : (p.type || '')) + '→ <b>' + E(nb2 ? nb2.name : db) + '</b>' +
        (oldD && oldD.event ? '<br><span class="dim">' + E(String(oldD.event).slice(0, 160)) + '</span>' : '') +
        '</div>');
    } else if (it.kind === 'char_delete') {
      rows.push('<div class="rv-diff danger">删除角色 <b>' + E(c ? c.name : it.target_id) + '</b>（连同其所有关系边）</div>');
    } else if (it.kind === 'char_create') {
      rows.push('<div class="rv-diff">新建 <b>' + E(p.name || p.id) + '</b>' +
        (p.groups ? ' · 团：' + E(p.groups.join('、')) : '') + '</div>');
      if (p.identity) rows.push('<div class="rv-diff"><b>身份</b><span class="new">' + E(p.identity) + '</span></div>');
      if (p.note) rows.push('<div class="rv-diff"><b>简介</b><span class="new">' + E(p.note.slice(0, 300)) + '</span></div>');
    } else if (it.kind === 'rel_create') {
      var A = p.from && CH ? CH.get(p.from) : null, B = p.to && CH ? CH.get(p.to) : null;
      rows.push('<div class="rv-diff">新建关系 <b>' + E(A ? A.name : p.from) + '</b> —' + E(p.type || '') + '→ <b>' +
        E(B ? B.name : p.to) + '</b>（' + E(p.strength || '') + '）</div>');
      if (p.event) rows.push('<div class="rv-diff"><b>出处</b><span class="new">' + E(p.event.slice(0, 300)) + '</span></div>');
    }
    return rows.join('') || '<div class="rv-diff dim">（无可显示字段）</div>';
  }

  var KIND_CN = {
    char_update: '改角色', char_create: '新建角色', char_delete: '删角色',
    rel_update: '改关系', rel_create: '新建关系', rel_delete: '删关系',
  };

  function openReview() {
    var el = $('#review');
    el.classList.add('on');
    $('#rvToken').value = getToken();
    if (getToken()) loadReview(); else $('#rvList').innerHTML = '<div class="rv-empty">先填管理员口令，再点「加载待审」。</div>';
  }
  function closeReview() {
    $('#review').classList.remove('on');
    if (location.hash === '#/review') { try { history.replaceState(null, '', curHash() === '#/review' ? '#/' : curHash()); } catch (e) { } }
  }

  function loadReview() {
    var t = $('#rvToken').value.trim();
    if (!t) { toast('请填管理员口令', true); return; }
    localStorage.setItem('sjt-wiki-token', t);
    RV.token = t;
    $('#rvList').innerHTML = '<div class="rv-empty">加载中…</div>';
    api('/api/suggestions?status=pending&limit=200', { headers: { 'x-admin-token': t } })
      .then(function (r) {
        if (!r || !r.ok) { $('#rvList').innerHTML = '<div class="rv-empty">' + E((r && r.error) || '加载失败') + '</div>'; return; }
        RV.items = r.items || [];
        renderReview();
        api('/api/stats').then(function (s) {
          if (s && s.ok) $('#rvStats').textContent = '待审 ' + s.pending + ' · 已采纳 ' + s.approved + ' · 已驳回 ' + s.rejected;
        });
      })
      .catch(function () { $('#rvList').innerHTML = '<div class="rv-empty">连不上服务器</div>'; });
  }

  function renderReview() {
    var box = $('#rvList');
    if (!RV.items.length) { box.innerHTML = '<div class="rv-empty">🎉 没有待审建议</div>'; return; }
    box.innerHTML = RV.items.map(function (it) {
      return '<div class="rv-item" data-id="' + it.id + '">' +
        '<div class="rv-top"><span class="rv-kind k-' + it.kind + '">' + E(KIND_CN[it.kind] || it.kind) + '</span>' +
        '<span class="rv-id">#' + it.id + '</span>' +
        '<span class="rv-meta">' + E(it.author || '匿名') + ' · ' + E((it.created_at || '').replace('T', ' ').slice(0, 16)) + '</span></div>' +
        describe(it) +
        (it.reason ? '<div class="rv-why"><b>理由</b>' + E(it.reason) + '</div>' : '') +
        '<div class="rv-acts">' +
        '<button class="wb-btn ok" data-rv="approve">✓ 通过</button>' +
        '<button class="wb-btn danger" data-rv="reject">✕ 驳回</button>' +
        '<input class="rv-note" data-note placeholder="审核备注（可选）">' +
        '</div></div>';
    }).join('');
  }

  function doReview(id, action, note) {
    api('/api/review', {
      method: 'POST',
      headers: { 'x-admin-token': RV.token },
      body: JSON.stringify({ id: id, action: action, note: note || '' }),
    }).then(function (r) {
      if (r && r.ok) {
        toast(action === 'approve' ? '已通过 #' + id + ' —— 刷新后即生效' : '已驳回 #' + id);
        RV.items = RV.items.filter(function (x) { return x.id !== id; });
        renderReview();
      } else {
        toast('操作失败：' + ((r && r.error) || '未知错误'), true);
      }
    }).catch(function () { toast('连不上服务器', true); });
  }

  /* ── 导出补丁：给本地工具 _pull_suggestions.py 用 ───────── */
  function exportPatch() {
    if (!RV.token) { toast('先填口令', true); return; }
    api('/api/suggestions?status=approved&limit=200')
      .then(function (r) {
        if (!r || !r.ok) { toast('导出失败', true); return; }
        var blob = new Blob([JSON.stringify({ generated: new Date().toISOString(), items: r.items }, null, 2)],
          { type: 'application/json' });
        var a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'wiki_approved_' + new Date().toISOString().slice(0, 10) + '.json';
        a.click();
        toast('已导出 ' + r.items.length + ' 条已采纳建议');
      });
  }

  /* ══════════════════════════════════════════════════════════
     五、标签索引页（#/tags · 多标签筛选）
     ══════════════════════════════════════════════════════════ */
  var TP = { sel: [], mode: 'and', filter: '' };

  function buildFacets() {
    var f = {};
    (N.chars || []).forEach(function (c) {
      var at = c.attrs || {};
      Object.keys(at).forEach(function (k) {
        var v = at[k];
        (Array.isArray(v) ? v : [v]).forEach(function (val) {
          if (val == null || val === '') return;
          if (!f[k]) f[k] = {};
          var key = String(val);
          f[k][key] = (f[k][key] || 0) + 1;
        });
      });
    });
    return f;
  }

  function openTags(pre) {
    var el = $('#tags'); if (!el) return;
    el.classList.add('on');
    if (pre && TP.sel.indexOf(pre) < 0) TP.sel.push(pre);
    renderTags();
  }
  function closeTags() {
    var el = $('#tags'); if (!el) return;
    el.classList.remove('on');
    if (String(location.hash).indexOf('#/tags') === 0) {
      try { history.replaceState(null, '', '#/'); } catch (e) { location.hash = '#/'; }
    }
  }

  /** 门户关闭（portal.js 通过 window.__portalClose 调用） */
  window.__portalClose = function () {
    var el = $('#portal'); if (!el) return;
    el.classList.remove('on');
    if (String(location.hash).indexOf('#/portal') === 0) {
      try { history.replaceState(null, '', '#/'); } catch (e) { location.hash = '#/'; }
    }
  };

  function matchByTags() {
    var sel = TP.sel;
    if (!sel.length) return [];
    return (N.chars || []).filter(function (c) {
      var at = c.attrs || {};
      var hits = sel.filter(function (s) {
        var i = s.indexOf('=');
        if (i < 0) return false;
        var k = s.slice(0, i), v = s.slice(i + 1);
        var cv = at[k];
        if (cv == null) return false;
        return (Array.isArray(cv) ? cv : [cv]).map(String).indexOf(v) >= 0;
      }).length;
      return TP.mode === 'and' ? hits === sel.length : hits > 0;
    });
  }

  function renderTags() {
    var f = buildFacets();
    var sel = TP.sel;

    $('#tpSel').innerHTML = sel.length
      ? '<span class="tps-label">已选 ' + sel.length + ' 个</span>' +
        sel.map(function (s) {
          return '<a class="tps-chip" data-tagdel="' + E(s) + '" title="移除">' +
            E(s.replace('=', '：')) + ' <b>×</b></a>';
        }).join('') + '<a class="tps-clear" data-tagdel="__all">清空</a>'
      : '<span class="tps-label dim">还没选标签 —— 点下面任意标签开始筛选，可多选</span>';

    var q = TP.filter.trim().toLowerCase();
    var dims = Object.keys(f).sort(function (a, b) {
      var na = Object.keys(f[a]).length, nb = Object.keys(f[b]).length;
      return nb - na || a.localeCompare(b);
    });
    var html = dims.map(function (dim) {
      var vals = Object.keys(f[dim]).sort(function (a, b) {
        return f[dim][b] - f[dim][a] || a.localeCompare(b);
      });
      var shown = vals.filter(function (v) {
        return !q || (dim + '=' + v).toLowerCase().indexOf(q) >= 0;
      });
      if (!shown.length) return '';
      return '<div class="tpd"><div class="tpd-name">' + E(dim) +
        ' <i>' + vals.length + ' 个值</i></div><div class="tpd-vals">' +
        shown.map(function (v) {
          var key = dim + '=' + v;
          var on = sel.indexOf(key) >= 0;
          return '<a class="tpv' + (on ? ' on' : '') + '" data-tagadd="' + E(key) + '">' +
            E(v) + '<i>' + f[dim][v] + '</i></a>';
        }).join('') + '</div></div>';
    }).join('');
    $('#tpDims').innerHTML = html || '<div class="tp-empty">还没有任何属性标签<br><span class="dim">在角色页面用「✎ 建议修改」补</span></div>';

    renderTagRes();
  }

  function renderTagRes() {
    var box = $('#tpRes');
    if (!TP.sel.length) {
      box.innerHTML = '<div class="tp-empty">选好标签后，这里列出匹配的角色</div>';
      return;
    }
    var hits = matchByTags();
    box.innerHTML = '<div class="tpr-head">匹配 <b>' + hits.length + '</b> 个角色 · ' +
      (TP.mode === 'and' ? '全部满足' : '任一满足') + '</div>' +
      (hits.length
        ? '<div class="tpr-list">' + hits.map(function (c) {
            return '<a class="tpr-item" href="#/c/' + encodeURIComponent(c.id) + '">' +
              (c.avatar ? '<img src="' + E(c.avatar.thumb) + '" alt="">' : '<span class="tpr-ph"></span>') +
              '<span class="tpr-txt"><b>' + E(c.name) + '</b><i>' +
              E((c.groups || []).join(' / ')) + '</i></span></a>';
          }).join('') + '</div>'
        : '<div class="tp-empty">没有同时满足这些标签的角色</div>');
  }

  function toggleTag(key) {
    if (!key) return;
    var i = TP.sel.indexOf(key);
    if (i >= 0) TP.sel.splice(i, 1); else TP.sel.push(key);
    renderTags();
  }

  /* ══════════════════════════════════════════════════════════
     六、接线
     ══════════════════════════════════════════════════════════ */
  /* 绑定助手：少一个 DOM 元素**不该**把整个初始化搞崩。
     2026-10-06 踩过：`$('#rvAll')` 在 HTML 里并不存在，一个 null.addEventListener
     直接中断了 wire()，连**首屏路由与 hashchange 监听**都没绑上 ——
     表现就是「搜索能用（绑在前面）、#/c/<id> 直达打不开（绑在后面）」。 */
  function on(sel, ev, fn) {
    var e = $(sel);
    if (e) e.addEventListener(ev, fn);
    else console.warn('[wiki] 找不到元素，跳过绑定: ' + sel);
  }

  function wire() {
    buildIndex();

    /* 顶栏搜索按钮 + 快捷键 */
    on('#btnSearch', 'click', function () { location.hash = '#/s/'; openSearch(''); });
    on('#seClose', 'click', function () { closeSearch(); syncHash(); });
    on('#seInput', 'input', function (e) { renderHits(e.target.value); });
    on('#seInput', 'keydown', function (e) {
      if (e.key === 'ArrowDown') { e.preventDefault(); moveSel(1); }
      else if (e.key === 'ArrowUp') { e.preventDefault(); moveSel(-1); }
      else if (e.key === 'Enter') { e.preventDefault(); hitOpen(SE_HITS[SE_SEL]); }
      else if (e.key === 'Escape') { closeSearch(); syncHash(); }
    });
    on('#seList', 'click', function (e) {
      var it = e.target.closest('.se-item'); if (!it) return;
      hitOpen(SE_HITS[+it.dataset.i]);
    });
    document.addEventListener('keydown', function (e) {
      var typing = /^(INPUT|TEXTAREA)$/.test((e.target.tagName || ''));
      if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
        e.preventDefault(); openSearch(''); location.hash = '#/s/'; return;
      }
      if (e.key === '/' && !typing && !$('#search').classList.contains('on')) {
        e.preventDefault(); openSearch(''); location.hash = '#/s/'; return;
      }
      if (e.key === 'Escape' && $('#search').classList.contains('on')) { closeSearch(); syncHash(); }
    });

    /* 建议表单 */
    on('#wmClose', 'click', closeForm);
    on('#wmCancel', 'click', closeForm);
    on('#wmSubmit', 'click', submitForm);
    on('#wikiModal', 'click', function (e) { if (e.target.id === 'wikiModal') closeForm(); });

    /* 档案页操作条（事件代理，app.js 不用改）
       ⚠️ 2026-10-06 改动：只留「✎ 编辑这个角色」与「☰ 门户」两个按钮 ——
          点编辑直接跳这个角色的编辑器（`#/edit/<id>`），不再提交建议。 */
    document.addEventListener('click', function (e) {
      var b = e.target.closest('#wikiBar [data-wb]');
      if (b && DOS_ID) {
        var k = b.dataset.wb;
        if (k === 'edit') location.hash = '#/edit/' + encodeURIComponent(DOS_ID);
        else if (k === 'portal') location.hash = '#/portal';
      }
      var rv = e.target.closest('[data-rv]');
      if (rv) {
        var card = rv.closest('.rv-item');
        var note = card.querySelector('[data-note]');
        doReview(+card.dataset.id, rv.dataset.rv, note ? note.value : '');
      }
      var nb = e.target.closest('[data-navbtn]');
      if (nb) {
        var n = nb.dataset.navbtn;
        if (n === 'review') location.hash = '#/review';
        else if (n === 'new') suggestCreate();
        else if (n === 'tags') location.hash = '#/tags';
        else if (n === 'portal') location.hash = '#/portal';
        else if (n === 'resetlayout') {
          if (window.APP && window.APP.resetLayoutAll) window.APP.resetLayoutAll();
        }
        else if (n === 'edit') location.hash = '#/edit';
      }
      /* 点属性标签 → 跳到标签筛选页 */
      var wt = e.target.closest('.wa-tag');
      if (wt && wt.dataset.tag) location.hash = '#/tags/' + encodeURIComponent(wt.dataset.tag);
      /* 标签页：加/减标签 */
      var tad = e.target.closest('[data-tagadd]');
      if (tad) toggleTag(tad.dataset.tagadd);
      var tdl = e.target.closest('[data-tagdel]');
      if (tdl) {
        if (tdl.dataset.tagdel === '__all') TP.sel = [];
        else TP.sel = TP.sel.filter(function (x) { return x !== tdl.dataset.tagdel; });
        renderTags();
      }
      /* 关系条目的「改 / 删」 */
      var ra = e.target.closest('[data-relact]');
      if (ra) {
        var holder = ra.closest('.dos-rel');
        var fl = holder ? fullRel(holder.dataset.relFrom, holder.dataset.relTo, holder.dataset.relType) : null;
        var rel = fl || (holder ? {
          a: holder.dataset.relFrom, b: holder.dataset.relTo, type: holder.dataset.relType,
          strength: '', event: '', raw: '',
        } : null);
        if (ra.dataset.relact === 'edit') suggestRelUpdate(rel);
        else suggestRelDelete(rel);
      }
      /* 用户在图上点来点去之后，把 hash 同步一下 */
      setTimeout(syncHash, 0);
    }, false);

    /* 捕获阶段先记下「这次的卡片 id」，因为 app.js 的 handler 在冒泡阶段 */
    document.addEventListener('click', function (e) {
      var el = e.target.closest('.card');
      if (el && el.dataset.id) {
        var willOpen = !!e.target.closest('.detail') ||
          ($('#dossier').classList.contains('on'));   // 已聚焦时再点卡片 = 开档案
        if (willOpen || S.focus === el.dataset.id) DOS_ID = el.dataset.id;
      }
    }, true);
    document.addEventListener('click', function (e) {
      if (e.target.closest('#dosClose') || e.target.closest('#btnBack')) setTimeout(function () { DOS_ID = null; syncHash(); }, 0);
      if (e.target.closest('.tile')) setTimeout(function () { DOS_ID = null; syncHash(); }, 0);
    }, true);

    /* 档案页打开 → 注入操作条；关闭 → 清掉 */
    var dosEl = $('#dossier');
    if (dosEl) new MutationObserver(function () {
      var on = dosEl.classList.contains('on');
      if (on) {
        injectActions(DOS_ID);
        injectAttrs(DOS_ID);
        injectProfile(DOS_ID);
        injectRelActions(DOS_ID);
        setTimeout(syncHash, 0);
      } else {
        ['#wikiBar', '#wikiAttrs', '#wikiProfile'].forEach(function (s) { var e2 = $(s); if (e2) e2.remove(); });
        DOS_ID = null;
      }
    }).observe(dosEl, { attributes: true, attributeFilter: ['class'] });

    /* 审核页事件 */
    on('#rvLoad', 'click', loadReview);
    on('#rvClose', 'click', closeReview);
    on('#rvExport', 'click', exportPatch);
    on('#rvToken', 'keydown', function (e) { if (e.key === 'Enter') loadReview(); });

    /* 标签索引页 */
    on('#tpFilter', 'input', function (e) { TP.filter = e.target.value; renderTags(); });
    on('#tpClose', 'click', closeTags);
    on('#tpModeAnd', 'click', function () {
      TP.mode = 'and';
      var a = $('#tpModeAnd'), b = $('#tpModeOr');
      if (a) a.classList.add('on');
      if (b) b.classList.remove('on');
      renderTagRes();
    });
    on('#tpModeOr', 'click', function () {
      TP.mode = 'or';
      var a = $('#tpModeAnd'), b = $('#tpModeOr');
      if (b) b.classList.add('on');
      if (a) a.classList.remove('on');
      renderTagRes();
    });

    /* 前进 / 后退 */
    window.addEventListener('hashchange', function () { applyRoute(parseHash()); });

    /* 首屏：按 hash 落位（默认总览） */
    var r = parseHash();
    if (r.v !== 'overview') applyRoute(r);

    console.log('[wiki] 就绪：搜索索引 ' + IDX.length + ' 条' +
      (window.__WIKI_APPLIED__ ? ' · 已套用 ' + window.__WIKI_APPLIED__ + ' 条已采纳建议' : ''));
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wire);
  else wire();
})();
