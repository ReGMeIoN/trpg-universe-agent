/* ============================================================
   跑团宇宙 · 门户层（#/portal）
   —— 一个「公告栏 + 最近改动 + 新增条目」的入口页。
   设计约束（2026-10-06 主人拍板）：
     · **新增条目 / 上传立绘 / 发公告 不需要口令**；改已有的、删、回滚才要口令。
     · 所有写入都进版本历史，门户上能看见「谁在什么时候添了什么」。
   依赖：app.js 的 window.APP / window.NET（wiki-boot 保证顺序），wiki.js 的 hash 路由。
   ============================================================ */
(function () {
  'use strict';
  var $ = function (s) { return document.querySelector(s); };
  var api = function (p, opt) {
    return fetch(p, Object.assign({ cache: 'no-store' }, opt || {}))
      .then(function (r) { return r.json().catch(function () { return {}; }); });
  };
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function token() {
    try { return localStorage.getItem('trpg-edit-token') || localStorage.getItem('trpg-edit-token') || ''; }
    catch (e) { return ''; }
  }
  function nick() {
    try { return localStorage.getItem('trpg-nick') || ''; } catch (e) { return ''; }
  }
  function when(ts) {
    if (!ts) return '';
    try {
      var d = new Date(ts);
      var p = function (n) { return (n < 10 ? '0' : '') + n; };
      return d.getFullYear() + '-' + p(d.getMonth() + 1) + '-' + p(d.getDate()) + ' ' +
             p(d.getHours()) + ':' + p(d.getMinutes());
    } catch (e) { return String(ts).slice(0, 16); }
  }
  var KIND_CN = { char_create: '新建角色', char_update: '改角色', char_delete: '删角色',
                  rel_create: '新建关系', rel_update: '改关系', rel_delete: '删关系',
                  portrait: '上传立绘', rollback: '回滚', edit: '编辑' };

  var P = { tab: 'recent', loaded: {} };

  function show(tab) {
    P.tab = tab || P.tab;
    [['#ptRecent', 'recent'], ['#ptNew', 'new'], ['#ptAnn', 'ann']].forEach(function (kv) {
      var b = $(kv[0]); if (b) b.classList.toggle('on', P.tab === kv[1]);
    });
    ['#pvRecent', '#pvNew', '#pvAnn'].forEach(function (s, i) {
      var el = $(s); if (el) el.classList.toggle('on', ['recent', 'new', 'ann'][i] === P.tab);
    });
    if (P.tab === 'recent') loadRecent();
    else if (P.tab === 'new') loadNew();
    else loadAnn();
  }
  window.__portalTab = show;

  /* ── ① 最近改动（版本历史）────────────────────────────── */
  function loadRecent() {
    var box = $('#pvRecent'); if (!box) return;
    box.innerHTML = '<div class="pt-empty">读取中…</div>';
    api('/api/history?limit=80').then(function (r) {
      var items = (r && r.items) || (r && r.history) || [];
      if (!items.length) { box.innerHTML = '<div class="pt-empty">还没有改动记录（第一次编辑之后这里就热闹了）</div>'; return; }
      box.innerHTML = items.map(function (it) {
        var kn = KIND_CN[it.kind] || it.kind || '改动';
        var cls = (it.kind || '').indexOf('delete') >= 0 ? 'del' : (it.kind || '').indexOf('create') >= 0 ? 'new' : '';
        return '<div class="pt-row">' +
          '<span class="pt-kind ' + cls + '">' + esc(kn) + '</span>' +
          '<span class="pt-txt">' + esc(it.summary || it.target || '') + '</span>' +
          '<span class="pt-who">' + esc(it.editor || '匿名') + '</span>' +
          '<span class="pt-ts">' + esc(when(it.ts)) + '</span></div>';
      }).join('');
    }).catch(function () { box.innerHTML = '<div class="pt-empty">读不到改动记录（服务器没连上？）</div>'; });
  }

  /* ── ② 新增条目（最近新建的角色 + 新建入口）──────────── */
  function loadNew() {
    var box = $('#pnFeed'); if (!box) return;      // ⚠️ 只写列表容器，别覆盖 #pvNew（表单在里面）
    box.innerHTML = '<div class="pt-empty">读取中…</div>';
    api('/api/history?limit=200').then(function (r) {
      var items = ((r && r.items) || (r && r.history) || []).filter(function (x) {
        return x.kind === 'char_create' || x.kind === 'portrait' || x.kind === 'rel_create';
      }).slice(0, 40);
      return api('/api/data?scope=all').then(function (d) {
        var chars = (d && d.chars) || [];
        /* 「新增」判定用 created_at（24h 内）—— 比版本历史的 kind 更可靠：
           新建后立刻再改一次会把历史里那条 char_create 顶掉，但 created_at 一直在 */
        var dayAgo = Date.now() - 24 * 3600 * 1000;
        var mine = chars.filter(function (c) {
          var t = c.created_at ? Date.parse(c.created_at) : 0;
          return t && t > dayAgo;
        }).sort(function (a, b) {
          return String(b.created_at).localeCompare(String(a.created_at));
        });
        var html = '';
        if (mine.length) {
          html += '<div class="pt-sub">最近新增的角色</div><div class="pt-grid">' +
            mine.slice(0, 24).map(function (c) {
              return '<a class="pt-mini" href="#/c/' + encodeURIComponent(c.id) + '">' +
                (c.avatar ? '<img src="' + esc(c.avatar.thumb || c.avatar.full) + '" alt="">'
                          : '<span class="pt-ph">' + esc((c.name || '?').slice(0, 1)) + '</span>') +
                '<b>' + esc(c.name) + '</b><i>' + esc((c.groups || [])[0] || '未分组') + '</i></a>';
            }).join('') + '</div>';
        }
        html += '<div class="pt-sub">最近的写入</div>' + (items.length
          ? items.map(function (it) {
              return '<div class="pt-row"><span class="pt-kind new">' + esc(KIND_CN[it.kind] || it.kind) + '</span>' +
                '<span class="pt-txt">' + esc(it.summary || it.target) + '</span>' +
                '<span class="pt-who">' + esc(it.editor || '匿名') + '</span>' +
                '<span class="pt-ts">' + esc(when(it.ts)) + '</span></div>';
            }).join('')
          : '<div class="pt-empty">还没有新增记录</div>');
        box.innerHTML = html;
      });
    }).catch(function () { box.innerHTML = '<div class="pt-empty">读不到数据</div>'; });
  }

  /* ── ③ 公告栏 ─────────────────────────────────────────── */
  function loadAnn() {
    var box = $('#pnAnn'); if (!box) return;       // ⚠️ 只写列表容器，别覆盖 #pvAnn（发帖框在里面）
    box.innerHTML = '<div class="pt-empty">读取中…</div>';
    api('/api/announce?limit=60').then(function (r) {
      var items = (r && r.items) || [];
      var hasTok = !!token();
      box.innerHTML = (items.length ? items.map(function (a) {
        return '<div class="pt-ann"><div class="pt-ann-h"><b>' + esc(a.who || '匿名') + '</b>' +
          '<span>' + esc(when(a.ts)) + '</span>' +
          (hasTok ? '<button class="pt-del" data-del="' + esc(a.id) + '" title="删这条（要口令）">×</button>' : '') +
          '</div><div class="pt-ann-b">' + esc(a.text).replace(/\n/g, '<br>') + '</div></div>';
      }).join('') : '<div class="pt-empty">公告栏还是空的 —— 下面写一条试试</div>');
      box.querySelectorAll('[data-del]').forEach(function (b) {
        b.onclick = function () {
          if (!confirm('删掉这条公告？')) return;
          api('/api/announce/delete', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Edit-Token': token() },
            body: JSON.stringify({ id: Number(b.dataset.del) })
          }).then(function (x) {
            if (!x.ok) alert(x.error || '删除失败（可能要口令）');
            loadAnn();
          });
        };
      });
    }).catch(function () { box.innerHTML = '<div class="pt-empty">公告读不到（离线？）</div>'; });
  }

  function postAnn() {
    var ta = $('#ptAnnText');
    var txt = (ta && ta.value || '').trim();
    if (!txt) return;
    var nm = $('#ptNick');
    if (nm && nm.value.trim()) { try { localStorage.setItem('trpg-nick', nm.value.trim().slice(0, 24)); } catch (e) {} }
    api('/api/announce', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: txt, _editor: nick() })
    }).then(function (r) {
      if (!r.ok) { alert(r.error || '发布失败'); return; }
      if (ta) ta.value = '';
      loadAnn();
    });
  }

  /* ── ④ 新增条目（免口令）──────────────────────────────── */
  function fillGroups() {
    var sel = $('#pnGroup'); if (!sel) return;
    var gs = ((window.NET && window.NET.groups) || []).map(function (g) { return g.name || g; });
    sel.innerHTML = '<option value="">（不选）</option>' + gs.map(function (g) {
      return '<option value="' + esc(g) + '">' + esc(g) + '</option>';
    }).join('');
  }

  function submitNew() {
    var id = ($('#pnId') && $('#pnId').value || '').trim();
    var name = ($('#pnName') && $('#pnName').value || '').trim();
    var grp = ($('#pnGroup') && $('#pnGroup').value) || '';
    var ident = ($('#pnIdentity') && $('#pnIdentity').value || '').trim();
    var note = ($('#pnNote') && $('#pnNote').value || '').trim();
    var nm = ($('#ptNick') && $('#ptNick').value || '').trim();
    if (!/^[A-Za-z0-9_\-]{2,64}$/.test(id)) { alert('ID 只能用字母/数字/下划线/连字符（2–64 位），例如 my_char_01'); return; }
    if (!name) { alert('名字不能空'); return; }
    if (nm) { try { localStorage.setItem('trpg-nick', nm.slice(0, 24)); } catch (e) {} }
    var body = { id: id, name: name, groups: grp ? [grp] : [], tags: ['NPC'],
                 identity: ident, note: note, _editor: nm || '匿名访客' };
    api('/api/edit/char', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(body) }).then(function (r) {
      if (!r.ok) { alert(r.error || '新建失败'); return; }
      var f = $('#pnFile');
      if (f && f.files && f.files[0]) uploadPortrait(id, f.files[0], function () { done(id, name); });
      else done(id, name);
    });
  }
  function done(id, name) {
    var msg = $('#pnMsg');
    if (msg) msg.innerHTML = '✅ 已新建「' + esc(name) + '」 —— <a href="#/c/' + encodeURIComponent(id) + '">去看档案</a>';
    ['#pnId', '#pnName', '#pnIdentity', '#pnNote'].forEach(function (s) { var e = $(s); if (e) e.value = ''; });
    var f = $('#pnFile'); if (f) f.value = '';
  }

  /* 立绘上传：读成 dataURL → POST /api/upload/portrait（免口令） */
  function uploadPortrait(cid, file, cb) {
    if (!file) { cb && cb(); return; }
    if (file.size > 12 * 1024 * 1024) { alert('图太大了（上限 12MB）'); cb && cb(); return; }
    var fr = new FileReader();
    fr.onload = function () {
      api('/api/upload/portrait', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: cid, data: fr.result, _editor: nick() })
      }).then(function (r) {
        if (!r.ok) alert(r.error || '立绘上传失败（角色已建好，可以之后再传）');
        cb && cb();
      }).catch(function () { alert('立绘上传失败（网络）'); cb && cb(); });
    };
    fr.readAsDataURL(file);
  }
  window.__portalUpload = uploadPortrait;

  /* ── 装配 ─────────────────────────────────────────────── */
  function wire() {
    var el = $('#portal'); if (!el || el.__wired) return;
    el.__wired = true;
    $('#ptRecent').onclick = function () { show('recent'); };
    $('#ptNew').onclick = function () { show('new'); };
    $('#ptAnn').onclick = function () { show('ann'); };
    $('#ptClose').onclick = function () { if (window.__portalClose) window.__portalClose(); };
    $('#ptAnnPost').onclick = postAnn;
    $('#pnSubmit').onclick = submitNew;
    var f = $('#pnFile');
    if (f) f.onchange = function () {
      var t = $('#pnFileName');
      if (t) t.textContent = (f.files && f.files[0]) ? f.files[0].name : '（没选图）';
    };
    var nm = $('#ptNick'); if (nm) nm.value = nick();
    fillGroups();
  }

  function open(tab) {
    var el = $('#portal'); if (!el) return;
    wire();
    fillGroups();
    el.classList.add('on');
    show(tab || 'recent');
  }
  window.__portalOpen = open;

  /* 顶部按钮 + 首页入口 */
  document.addEventListener('click', function (e) {
    var t = e.target && e.target.closest && e.target.closest('#btnPortal,#homePortal');
    if (t) { e.preventDefault(); open('recent'); }
  });
  /* 自己补开一次：本文件是动态加载的，首屏路由（#/portal 深链）可能跑在我们前面 */
  function selfOpen() {
    wire();
    if (String(location.hash).indexOf('#/portal') === 0) {
      open((String(location.hash).split('/')[2] || 'recent'));
    }
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', selfOpen);
  } else { selfOpen(); }
})();
