/* ============================================================
   跑团宇宙 · wiki 覆盖层引导
   职责（就两件）：
     1. 先把 /api/overrides（管理员已采纳的建议）拉下来，**套在 data.js 之上**
        → 审核一通过，站点立刻能看到，而生产库一个字节没动；
     2. 套完再依次加载 app.js 与 wiki.js（顺序很重要：app.js 建索引时
        读的就是打完补丁的 window.NET，否则会出现「档案页显示了新名字、
        卡片网还是旧名字」这种不一致）。
   ⚠️ 必须容错：接口挂了 / 本地没后端 / 离线，都要**照常加载 app.js**，
      绝不能因为一个可选功能把整站搞白屏。 */
(function () {
  'use strict';
  var LOADED = false;

  function boot() {
    if (LOADED) return;
    LOADED = true;
    var a = document.createElement('script');
    a.src = 'app.js';
    a.onload = function () {
      var w = document.createElement('script');
      w.src = 'wiki.js';
      w.onload = function () {
        var ed = document.createElement('script');   // 编辑器（可编辑时才有用）
        ed.src = 'editor.js';
        document.body.appendChild(ed);
        var pt = document.createElement('script');   // 门户（最近改动 / 新增条目 / 公告）
        pt.src = 'portal.js';
        document.body.appendChild(pt);
      };
      document.body.appendChild(w);
    };
    a.onerror = function () { console.error('[wiki] app.js 加载失败'); };
    document.body.appendChild(a);
  }

  /* ── 覆盖层应用：把这批「已采纳建议」合并进 window.NET ─────── */
  function applyOverrides(NET, items) {
    if (!NET || !Array.isArray(items) || !items.length) return 0;
    var chars = NET.chars || [], rels = NET.rels || [];
    var byId = new Map(chars.map(function (c) { return [c.id, c]; }));
    var groups = NET.groups || (NET.groups = []);
    var PAL = ['#d8b25a', '#6fd6c0', '#c86fd6', '#e08a5a', '#7fa8e8', '#e0709a'];
    var applied = 0;

    function ensureGroup(name) {
      if (!name) return;
      if (!groups.some(function (g) { return (g.name || g) === name; })) {
        groups.push({ name: name, count: 0, color: PAL[groups.length % PAL.length], core: false, _wiki: true });
      }
    }

    /* 关系定位：target_id 为 `from|to|原type`（这样「改 type」也定得住），
       缺失时退化为按端点找第一条。 */
    function findRel(it, p) {
      var parts = String(it.target_id || '').split('|');
      if (parts.length === 3) {
        var hit = rels.find(function (x) {
          return x.a === parts[0] && x.b === parts[1] && x.type === parts[2];
        });
        if (hit) return hit;
      }
      return rels.find(function (x) { return x.a === p.from && x.b === p.to; }) || null;
    }

    items.forEach(function (it) {
      var p = it.payload || {};
      var k = it.kind;
      if (k === 'char_update') {
        var c = byId.get(it.target_id);
        if (!c) return;
        ['name', 'identity', 'note', 'profile', 'played_by', 'aliases', 'groups', 'tags'].forEach(function (f) {
          if (p[f] !== undefined) c[f] = p[f];
        });
        /* attrs **按维度合并**：值为 null 表示删掉该维度，其余覆盖。
           不能整体替换 —— 否则两人先后改不同维度时会互相覆盖。 */
        if (p.attrs && typeof p.attrs === 'object') {
          c.attrs = c.attrs || {};
          Object.keys(p.attrs).forEach(function (dim) {
            if (p.attrs[dim] === null) delete c.attrs[dim];
            else c.attrs[dim] = p.attrs[dim];
          });
        }
        (p.groups || []).forEach(ensureGroup);
        c._wiki = true;
        applied++;
      } else if (k === 'char_create') {
        if (!p.id || byId.has(p.id)) return;
        var nc = {
          id: p.id, name: p.name || p.id,
          groups: p.groups || [], tags: p.tags || [],
          kind: (p.tags && p.tags[0]) || 'NPC',
          played_by: p.played_by || '', identity: p.identity || '',
          note: p.note || '', attrs: p.attrs || {},
          degree: 0, events: [], avatar: null,
          is_core: false, _wiki: true, _wikiNew: true,
        };
        chars.push(nc); byId.set(nc.id, nc);
        (p.groups || []).forEach(ensureGroup);
        applied++;
      } else if (k === 'char_delete') {
        var id = it.target_id || p.id;
        if (!id || !byId.has(id)) return;
        var i = chars.findIndex(function (x) { return x.id === id; });
        if (i >= 0) chars.splice(i, 1);
        byId.delete(id);
        for (var j = rels.length - 1; j >= 0; j--) if (rels[j].a === id || rels[j].b === id) rels.splice(j, 1);
        applied++;
      } else if (k === 'rel_create') {
        if (!p.from || !p.to || !byId.has(p.from) || !byId.has(p.to)) return;
        rels.push({
          a: p.from, b: p.to, type: p.type || '其他', raw: p.raw || '',
          strength: p.strength || '中', event: p.event || '', _wiki: true,
        });
        applied++;
      } else if (k === 'rel_update') {
        var r = findRel(it, p);
        if (!r) return;
        /* from/to 是端点（不改），type/strength/event/raw 才是新值；
           定位靠 target_id = `from|to|原type`，这样「改 type」也能定得住。 */
        ['type', 'strength', 'event', 'raw'].forEach(function (f) {
          if (p[f] !== undefined && p[f] !== '') r[f] = p[f];
        });
        r._wiki = true; applied++;
      } else if (k === 'rel_delete') {
        var n = rels.indexOf(findRel(it, p));
        if (n < 0) return;
        rels.splice(n, 1); applied++;
      }
    });

    /* 关系度数要重算：不然「关系数 N」和图表密度还是旧的 */
    var deg = new Map();
    rels.forEach(function (r) {
      deg.set(r.a, (deg.get(r.a) || 0) + 1);
      deg.set(r.b, (deg.get(r.b) || 0) + 1);
    });
    chars.forEach(function (c) { c.degree = deg.get(c.id) || 0; });
    return applied;
  }

  window.__applyWikiOverrides = applyOverrides;   // 供调试与后续复用

  function applyApiData(d) {
    var NET = window.NET || (window.NET = {});
    if (Array.isArray(d.chars)) NET.chars = d.chars;
    if (Array.isArray(d.rels)) NET.rels = d.rels;
    if (Array.isArray(d.groups)) NET.groups = d.groups;
    if (Array.isArray(d.kinds)) NET.kinds = d.kinds;
    if (d.generated) NET.generated = d.generated;
    if (d.stats) NET.stats = d.stats;
    window.__WIKI_LIVE__ = true;                  // 标记「数据来自服务器」，编辑器靠它判断
    console.log('[wiki] 数据源：服务器 /api/data（' + (d.chars || []).length + ' 角色 / ' +
      (d.rels || []).length + ' 关系）');
  }

  /* 数据源优先级：
       ① /api/data      —— 自托管服务器的**权威数据**（含朋友刚编辑的内容）
       ② 静态 data.js    —— 拿不到后端时降级（纯静态部署、本地 python -m http.server 都能跑）
       ③ /api/overrides —— 只有「静态数据 + 提案箱」这种组合才需要叠加覆盖层
     三步全程容错：任何一步失败都照常进站，绝不因为可选功能把整站搞白。 */
  var guard = setTimeout(boot, 2500);             // 接口慢/挂 → 最多等 2.5 秒就进站
  var jobs = 1;                                   // 还差几个接口没回来（各最多等 1 秒）

  function done() { if (--jobs <= 0) { clearTimeout(guard); boot(); } }

  /* 布局账本（人工微调过的卡片位置）。
     ⚠️ 与数据分开拉：**布局挂了绝不能拖住站点**，所以自己一个 1 秒超时，
        且 app.js 还有 localStorage 兜底（见 loadAdj）。 */
  var lg = setTimeout(done, 1000);
  fetch('/api/layout', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (d && d.ok && d.layout) window.__layoutAdj = d.layout;
    })
    .catch(function () { /* 静态部署 / 离线 → 用本地账本 */ })
    .then(function () { clearTimeout(lg); done(); });

  fetch('/api/data', { cache: 'no-store' })
    .then(function (r) { return r.ok ? r.json() : null; })
    .then(function (d) {
      if (d && d.ok && Array.isArray(d.chars)) {
        applyApiData(d);
        return null;                              // 已有权威数据，不需要覆盖层
      }
      return fetch('/api/overrides', { cache: 'no-store' })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (o) {
          if (o && o.ok && Array.isArray(o.items) && o.items.length) {
            var n = applyOverrides(window.NET, o.items);
            window.__WIKI_APPLIED__ = n;
            console.log('[wiki] 已套用 ' + n + ' 条已采纳建议（静态数据源）');
          }
        });
    })
    .catch(function () { /* 本地无后端 / 离线 → 静默降级到静态 data.js */ })
    .then(function () { clearTimeout(guard); done(); });
})();
