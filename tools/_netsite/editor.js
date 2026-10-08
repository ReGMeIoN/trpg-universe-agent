/* ============================================================
   跑团宇宙 · 编辑器（#/edit）
   ------------------------------------------------------------
   和「提案箱」的根本区别：**写进去就是真的** —— 没有审核关，保存即生效。
   所以配套了三样东西：
     · 一个共享口令（防外人扫链接乱改，不防朋友）
     · **每次保存都进版本历史**，任何一版都能一键回滚
     · 删角色 / 删关系前，服务端自动备份数据文件

   能改的东西（主人要的"越多越好"）：
     角色：名字 / 别名 / 团 / 系统标签 / 扮演者 / 身份 / 简介 / 详细设定(Markdown) / 属性标签 / 立绘
     关系：新增、改类型/强度/出处、删除
     结构：新建角色、新建团（直接在"团"字段里写新名字）、新建 tag 维度（直接在属性里写新维度）
     历史：看谁在什么时候改了什么，一键回滚
   ============================================================ */
(function () {
  'use strict';

  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };
  function E(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }
  function md(s) { return (window.__wikiRender || E)(s || ''); }

  var ED = {
    token: localStorage.getItem('trpg-edit-token') || '',
    who: localStorage.getItem('trpg-edit-who') || '',
    cur: null,          // 当前编辑的角色 id
    meta: null,
    all: null,          // 全量角色（编辑器用；站点画图用的是选角子集）
    rels: null,         // 全量关系
    live: false,        // 是否连上了服务器
    host: '',           // /api/edit/* 需要口令
  };

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
    el._t = setTimeout(function () { el.className = 'wiki-toast'; }, 3600);
  }

  function api(path, opt) {
    opt = opt || {};
    opt.headers = Object.assign({
      'content-type': 'application/json',
      'x-edit-token': ED.token,
    }, opt.headers || {});
    if (opt.body && typeof opt.body !== 'string') opt.body = JSON.stringify(opt.body);
    return fetch(path, opt).then(function (r) {
      return r.json().catch(function () { return { ok: false, error: 'HTTP ' + r.status }; });
    });
  }

  /* ══════════════════════════════════════════════════════════
     打开 / 关闭
     ══════════════════════════════════════════════════════════ */
  function openEditor(id) {
    var el = $('#editor');
    if (!el) { toast('编辑器没加载（editor.js 缺失）', true); return; }
    el.classList.add('on');
    ED.cur = id || ED.cur;
    api('/api/edit/ping').then(function (r) {
      ED.live = !!(r && r.ok);
      ED.host = ED.live && r.protected;
      if (!ED.live) {
        $('#edLock').innerHTML = '<div class="ed-lock-in">' +
          '<b>没连上服务器</b><div class="dim">现在打开的是纯静态站点，没有编辑后端。<br>' +
          '要能编辑，需要用 <code>server/app.py</code> 起服务（或者把它部署到你的服务器）。</div></div>';
        $('#edLock').style.display = 'block';
        return;
      }
      if (r.protected && !r.authed) { showLock(); return; }
      hideLock();
      bootEditor();
    });
  }

  function showLock() {
    var l = $('#edLock');
    l.style.display = 'block';
    l.innerHTML = '<div class="ed-lock-in">' +
      '<b>需要编辑口令</b>' +
      '<div class="dim">口令是给大家共用的那一个（管理员会发给你）。填一次就记住了。</div>' +
      '<div class="ed-lock-row">' +
      '<input id="edTokenIn" type="password" placeholder="编辑口令">' +
      '<input id="edWhoIn" type="text" placeholder="你的昵称（留个名，好查历史）" value="' + E(ED.who) + '">' +
      '<button class="wb-btn ok" id="edLoginBtn">进入编辑</button>' +
      '</div><div class="ed-err" id="edErr"></div></div>';
    $('#edLoginBtn').onclick = function () {
      var t = $('#edTokenIn').value.trim();
      var who = $('#edWhoIn').value.trim();
      fetch('/api/edit/login', {
        method: 'POST', headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ token: t, editor: who }),
      }).then(function (r) { return r.json(); }).then(function (d) {
        if (d && d.ok) {
          ED.token = t; ED.who = who || '匿名';
          localStorage.setItem('trpg-edit-token', t);
          localStorage.setItem('trpg-edit-who', ED.who);
          hideLock(); bootEditor();
        } else {
          $('#edErr').textContent = (d && d.error) || '口令不对';
        }
      }).catch(function () { $('#edErr').textContent = '连不上服务器'; });
    };
    setTimeout(function () { var i = $('#edTokenIn'); if (i) i.focus(); }, 50);
  }
  function hideLock() { var l = $('#edLock'); if (l) l.style.display = 'none'; }

  function closeEditor() {
    var el = $('#editor'); if (el) el.classList.remove('on');
    if (String(location.hash).indexOf('#/edit') === 0) {
      try { history.replaceState(null, '', '#/'); } catch (e) { location.hash = '#/'; }
    }
  }

  /* ══════════════════════════════════════════════════════════
     列表
     ══════════════════════════════════════════════════════════ */
  /* 列表用**全量**：站点画关系图用的是「选角后」的子集（约 135 人，布局才不会挤爆），
     但编辑器要能改**所有人**，所以另外拉一份 `scope=all`。 */
  function chars() {
    return (ED.all && ED.all.length) ? ED.all : ((window.NET && window.NET.chars) || []);
  }
  function byId(id) { return chars().filter(function (c) { return c.id === id; })[0] || null; }

  function renderList() {
    var q = ($('#edSearch').value || '').trim().toLowerCase();
    var list = chars().slice().sort(function (a, b) {
      return (a.name || '').localeCompare(b.name || '', 'zh');
    });
    if (q) {
      list = list.filter(function (c) {
        return (c.name || '').toLowerCase().indexOf(q) >= 0 ||
          (c.id || '').toLowerCase().indexOf(q) >= 0 ||
          (c.aliases || []).join(' ').toLowerCase().indexOf(q) >= 0 ||
          (c.groups || []).join(' ').toLowerCase().indexOf(q) >= 0;
      });
    }
    $('#edList').innerHTML =
      '<div class="ed-list-head">' + list.length + ' 个角色' +
      (q ? '（含搜索）' : '') + '</div>' +
      list.map(function (c) {
        return '<a class="ed-item' + (c.id === ED.cur ? ' on' : '') + '" data-ed="' + E(c.id) + '">' +
          '<span class="ed-item-n">' + E(c.name || c.id) + '</span>' +
          '<span class="ed-item-i">' + E((c.groups || []).join('/') || '—') + '</span></a>';
      }).join('');
  }

  /* ══════════════════════════════════════════════════════════
     表单
     ══════════════════════════════════════════════════════════ */
  function field(label, name, value, hint, rows) {
    var v = value == null ? '' : value;
    return '<div class="ed-f"><label>' + E(label) +
      (hint ? '<i>' + E(hint) + '</i>' : '') + '</label>' +
      (rows
        ? '<textarea class="ed-in" data-f="' + name + '" rows="' + rows + '">' + E(v) + '</textarea>'
        : '<input class="ed-in" data-f="' + name + '" type="text" value="' + E(v) + '">') + '</div>';
  }

  function renderForm() {
    var box = $('#edForm');
    var c = ED.cur ? byId(ED.cur) : null;
    if (!c) {
      box.innerHTML = '<div class="ed-empty">' +
        '<b>左边选一个角色开始改</b>' +
        '<div class="dim">或者点右上角「＋ 新建角色」。<br><br>' +
        '能改的东西：名字 / 别名 / 出场团 / 系统标签 / 扮演者 / 身份 / 简介 / ' +
        '<b>详细设定（Markdown）</b> / <b>属性标签</b> / <b>立绘</b> / 关系 —— 保存即生效。</div></div>';
      return;
    }
    var dims = ED.meta ? Object.keys(ED.meta.dims || {}) : [];
    var attrsText = Object.keys(c.attrs || {}).map(function (k) {
      var v = c.attrs[k];
      return k + ': ' + (Array.isArray(v) ? v.join('、') : v);
    }).join('\n');

    /* 卡面式布局：**左立绘 · 右表单**（像看角色卡一样编辑）。
       ⚠️ 两个容器分开写（`#edArtCard` / `#edRight`），立绘上传时只重画左边，
          否则整张表单会被 innerHTML 重建 → 正在填的字全丢。 */
    var art = c.avatar
      ? '<img class="ed-art-img" src="' + E(c.avatar.full || c.avatar.thumb) + '" alt="">'
      : '<div class="ed-art-ph"><span>' + E((c.name || '?').slice(0, 1)) + '</span>' +
        '<i>还没有立绘</i></div>';

    box.innerHTML =
      '<div class="ed-bar">' +
      '<button class="wb-btn ok" id="edSave">💾 保存</button>' +
      '<button class="wb-btn" id="edHistBtn">🕘 历史</button>' +
      '<button class="wb-btn" id="edMergeBtn" title="把另一个条目并进当前这个（同一个人被建了两份时用）">🔗 合并</button>' +
      '<button class="wb-btn danger" id="edDel">🗑 删除这个角色</button>' +
      '<span class="ed-savenote" id="edNote"></span>' +
      '</div>' +

      '<div class="ed-cardwrap">' +
      /* ── 左：角色卡（立绘 + 上传）── */
      '<div class="ed-artcard" id="edArtCard">' +
      '<div class="ed-artbox">' + art + '</div>' +
      '<div class="ed-artname">' + E(c.name) + '</div>' +
      '<div class="ed-artid">' + E(c.id) + '</div>' +
      '<input type="file" id="edArtFile" accept="image/png,image/jpeg,image/webp" hidden>' +
      '<button class="wb-btn on ed-artup" id="edArtUp">🖼 上传 / 更换立绘</button>' +
      '<div class="ed-arthint" id="edArtHint">PNG / JPG / WebP，≤12MB（免口令）</div>' +
      '</div>' +

      /* ── 右：表单 ── */
      '<div class="ed-right" id="edRight">' +
      '<div class="ed-sec"><h4>基础</h4>' +
      '<div class="ed-grid">' +
      field('id（唯一标识，改了就换个人）', 'id', c.id, '字母数字下划线') +
      field('名字', 'name', c.name) +
      field('别名', 'aliases', (c.aliases || []).join('、'), '用「、」或逗号分隔') +
      field('出场团', 'groups', (c.groups || []).join('、'), '直接写新团名就是新建团') +
      field('系统标签', 'tags', (c.tags || []).join('、'), 'PC / NPC / BOSS / 跨团 / KP') +
      field('扮演 / 创作者', 'played_by', c.played_by) +
      '</div></div>' +

      '<div class="ed-sec"><h4>身份与简介</h4>' +
      field('身份 / 设定（一句话）', 'identity', c.identity, '', 2) +
      field('简介 / 备注', 'note', c.note, '档案页顶部那段小字', 4) +
      '</div>' +

      '<div class="ed-sec"><h4>属性标签 <i>一行一个「维度: 值」；值多个用「、」；清空某行=删除该维度</i></h4>' +
      '<textarea class="ed-in ed-mono" data-f="attrs" rows="6">' + E(attrsText) + '</textarea>' +
      (dims.length ? '<div class="ed-chips">已有维度：' + dims.map(function (d) {
        return '<span class="ed-chip" data-dim="' + E(d) + '">' + E(d) + '</span>';
      }).join('') + '</div>' : '') +
      '</div>' +

      '<div class="ed-sec"><h4>详细设定（Markdown）<i>支持 ## 分节 · **粗体** · ==关键词== · &gt; 台词 · - 列表</i></h4>' +
      '<div class="ed-md">' +
      '<div class="ed-md-l">' +
      '<div class="ed-md-bar">' +
      '<button data-md="## ">## 小节</button><button data-md="**粗体**">**粗体**</button>' +
      '<button data-md="==关键词==">==高亮==</button><button data-md="- ">- 列表</button>' +
      '<button data-md="> ">&gt; 台词</button>' +
      '</div>' +
      '<textarea class="ed-in ed-mono" id="edProfile" data-f="profile" rows="22">' + E(c.profile || '') + '</textarea>' +
      '</div>' +
      '<div class="ed-md-r"><div class="ed-md-prev" id="edPrev">' + (c.profile ? md(c.profile) : '<span class="dim">预览区</span>') + '</div></div>' +
      '</div></div>' +

      '<div class="ed-sec"><h4>关系（' + relsOf(c.id).length + '）</h4>' +
      '<div id="edRels">' + renderRels(c.id) + '</div>' +
      '<div class="ed-addrel">' +
      '<input id="edRelTo" list="edCharIds" placeholder="对方角色 id 或名字">' +
      '<datalist id="edCharIds">' + chars().map(function (x) {
        return '<option value="' + E(x.id) + '">' + E(x.name) + '</option>';
      }).join('') + '</datalist>' +
      '<input id="edRelType" placeholder="关系类型" list="edTypes" value="友谊">' +
      '<datalist id="edTypes">' + ((ED.meta && ED.meta.types) || []).map(function (t) {
        return '<option value="' + E(t) + '">';
      }).join('') + '</datalist>' +
      '<input id="edRelStr" placeholder="强度" value="中" style="width:70px">' +
      '<input id="edRelEv" placeholder="出处 / 事件（可空）">' +
      '<button class="wb-btn" id="edRelAdd">＋ 加关系</button>' +
      '</div></div>' +
      '</div>' +   /* /ed-right */
      '</div>';    /* /ed-cardwrap */
    wireForm();
    wirePortrait();
  }

  /* ── 立绘上传（免口令）：传完当场刷新左边那张卡 ── */
  function wirePortrait() {
    var btn = $('#edArtUp'), file = $('#edArtFile');
    if (!btn || !file) return;
    btn.onclick = function () { file.click(); };
    file.onchange = function () {
      var f = file.files && file.files[0];
      if (!f || !ED.cur) return;
      if (f.size > 12 * 1024 * 1024) { toast('图太大了（上限 12MB）', true); return; }
      var hint = $('#edArtHint');
      if (hint) hint.textContent = '上传中…';
      var fr = new FileReader();
      fr.onload = function () {
        fetch('/api/upload/portrait', {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id: ED.cur, data: fr.result, _editor: ED.who || '匿名' })
        }).then(function (r) { return r.json().catch(function () { return {}; }); })
          .then(function (res) {
            if (!res || !res.ok) { if (hint) hint.textContent = (res && res.error) || '上传失败'; return; }
            // 立刻把新图显示出来：直接改本地那份数据（两份尺寸由服务端当场生成）
            var c = byId(ED.cur);
            if (c) c.avatar = { thumb: '/assets/portraits/' + ED.cur + '_t.jpg?v=' + Date.now(),
                                full: '/assets/portraits/' + ED.cur + '_f.jpg?v=' + Date.now() };
            var card = $('#edArtCard');
            if (card) {
              var box2 = card.querySelector('.ed-artbox');
              if (box2) box2.innerHTML = '<img class="ed-art-img" src="' +
                E(c.avatar.full) + '" alt="">';
            }
            if (hint) hint.textContent = '✅ 已更新立绘（存档页刷新即可看到）';
            file.value = '';
          })
          .catch(function () { if (hint) hint.textContent = '上传失败（网络）'; });
      };
      fr.readAsDataURL(f);
    };
  }

  function relsOf(id) {
    var all = ED.rels || (window.NET && window.NET.rels) || [];
    return all.filter(function (r) { return r.a === id || r.b === id; })
      .map(function (r) {
        var other = r.a === id ? r.b : r.a;
        var oc = byId(other);
        return { r: r, other: other, name: oc ? oc.name : other, out: r.a === id };
      });
  }

  function renderRels(id) {
    var rs = relsOf(id);
    if (!rs.length) return '<div class="dim" style="padding:6px 0">还没有关系</div>';
    return rs.map(function (x, i) {
      return '<div class="ed-rel" data-i="' + i + '">' +
        '<span class="ed-rel-dir">' + (x.out ? '→' : '←') + '</span>' +
        '<span class="ed-rel-n">' + E(x.name) + '</span>' +
        '<input class="ed-rel-t" value="' + E(x.r.type || '') + '" data-rel="type" list="edTypes">' +
        '<input class="ed-rel-s" value="' + E(x.r.strength || '') + '" data-rel="strength" style="width:64px">' +
        '<input class="ed-rel-e" value="' + E(x.r.event || '') + '" data-rel="event" placeholder="出处">' +
        '<button class="wb-btn mini" data-relsave="' + i + '">存</button>' +
        '<button class="wb-btn mini danger" data-reldel="' + i + '">删</button>' +
        '</div>';
    }).join('');
  }

  /* ══════════════════════════════════════════════════════════
     保存
     ══════════════════════════════════════════════════════════ */
  function textToAttrs(txt) {
    var out = {};
    String(txt || '').split(/\r?\n/).forEach(function (line) {
      line = line.trim();
      if (!line) return;
      var i = line.search(/[:：]/);
      var k = (i < 0 ? line : line.slice(0, i)).trim();
      var v = i < 0 ? '' : line.slice(i + 1).trim();
      if (!k) return;
      if (!v) { out[k] = null; return; }
      var vals = v.split(/[、,，;；\/|]+/).map(function (x) { return x.trim(); }).filter(Boolean);
      out[k] = vals.length > 1 ? vals : vals[0];
    });
    return out;
  }
  function splitList(v) {
    return String(v || '').split(/[、,，;；\s]+/).map(function (x) { return x.trim(); }).filter(Boolean);
  }

  function saveChar() {
    var el = $('#edForm');
    var body = { _editor: ED.who };
    $$('#edForm .ed-in[data-f]').forEach(function (i) {
      var k = i.dataset.f, v = i.value;
      if (k === 'aliases' || k === 'groups' || k === 'tags') body[k] = splitList(v);
      else if (k === 'attrs') body.attrs = textToAttrs(v);
      else body[k] = v;
    });
    if (!body.id) { toast('id 不能空', true); return; }
    var btn = $('#edSave');
    btn.disabled = true; btn.textContent = '保存中…';
    api('/api/edit/char', { method: 'POST', body: body }).then(function (r) {
      if (r && r.ok) {
        localStorage.removeItem('trpg-edit-draft');
        toast('已保存' + (r.created ? '（新建角色）' : '') + ' · 刷新中…');
        setTimeout(function () {
          var h = '#/edit' + (ED.cur ? '/' + ED.cur : '');
          location.hash = h;
          location.reload();
        }, 700);
      } else {
        btn.disabled = false; btn.textContent = '💾 保存';
        toast('保存失败：' + ((r && r.error) || '未知错误'), true);
      }
    }).catch(function () {
      btn.disabled = false; btn.textContent = '💾 保存';
      toast('保存失败：连不上服务器', true);
    });
  }

  function deleteChar() {
    if (!ED.cur) return;
    var c = byId(ED.cur);
    if (!confirm('确定删除「' + (c ? c.name : ED.cur) + '」？\n\n它会连同该角色的所有关系一起删掉。\n（服务端会先自动备份，且这次改动会进版本历史，可以回滚）')) return;
    api('/api/edit/char/' + encodeURIComponent(ED.cur), { method: 'DELETE' }).then(function (r) {
      if (r && r.ok) { toast('已删除（可回滚）'); setTimeout(function () { location.hash = '#/edit'; location.reload(); }, 700); }
      else toast('删除失败：' + ((r && r.error) || ''), true);
    });
  }

  function saveRel(i) {
    var row = $$('#edRels .ed-rel')[i];
    if (!row) return;
    var list = relsOf(ED.cur);
    var x = list[i];
    var body = {
      from: x.r.a, to: x.r.b, old_type: x.r.type,
      type: row.querySelector('[data-rel="type"]').value.trim() || '其他',
      strength: row.querySelector('[data-rel="strength"]').value.trim() || '中',
      event: row.querySelector('[data-rel="event"]').value,
      _editor: ED.who,
    };
    api('/api/edit/rel', { method: 'POST', body: body }).then(function (r) {
      if (r && r.ok) { toast('关系已保存 · 刷新中…'); setTimeout(function () { location.reload(); }, 600); }
      else toast('失败：' + ((r && r.error) || ''), true);
    });
  }

  function delRel(i) {
    var x = relsOf(ED.cur)[i];
    if (!x || !confirm('删除这条关系？\n' + x.name + ' —' + x.r.type + '→ （可回滚）')) return;
    api('/api/edit/rel/delete', {
      method: 'POST',
      body: { from: x.r.a, to: x.r.b, type: x.r.type, _editor: ED.who },
    }).then(function (r) {
      if (r && r.ok) { toast('已删除'); setTimeout(function () { location.reload(); }, 600); }
      else toast('失败：' + ((r && r.error) || ''), true);
    });
  }

  function addRel() {
    var to = $('#edRelTo').value.trim();
    if (!to) { toast('填对方角色 id', true); return; }
    // 允许填名字：转成 id
    var hit = chars().filter(function (c) { return c.id === to || c.name === to; })[0];
    if (!hit) { toast('找不到这个角色', true); return; }
    api('/api/edit/rel', {
      method: 'POST',
      body: {
        from: ED.cur, to: hit.id,
        type: $('#edRelType').value.trim() || '其他',
        strength: $('#edRelStr').value.trim() || '中',
        event: $('#edRelEv').value,
        _editor: ED.who,
      },
    }).then(function (r) {
      if (r && r.ok) { toast('已加关系'); setTimeout(function () { location.reload(); }, 600); }
      else toast('失败：' + ((r && r.error) || ''), true);
    });
  }

  /* ══════════════════════════════════════════════════════════
     新建角色
     ══════════════════════════════════════════════════════════ */
  function newChar() {
    var id = prompt('新角色的 id（英文/数字/下划线，例如 my_xinnpc）：');
    if (!id) return;
    var nm = prompt('名字：') || id;
    api('/api/edit/char', {
      method: 'POST',
      body: { id: id.trim(), name: nm.trim(), tags: ['NPC'], _editor: ED.who, _note: '新建' },
    }).then(function (r) {
      if (r && r.ok) {
        toast('已创建，正在打开…');
        setTimeout(function () { location.hash = '#/edit/' + id.trim(); location.reload(); }, 700);
      } else toast('创建失败：' + ((r && r.error) || ''), true);
    });
  }

  /* ══════════════════════════════════════════════════════════
     历史 / 回滚
     ══════════════════════════════════════════════════════════ */
  function openHistory(target) {
    var m = $('#edHistory');
    m.classList.add('on');
    $('#edHistList').innerHTML = '<div class="dim">加载中…</div>';
    api('/api/history?limit=120' + (target ? '&target=' + encodeURIComponent(target) : ''))
      .then(function (r) {
        if (!r || !r.ok) { $('#edHistList').innerHTML = '<div class="dim">读不到历史</div>'; return; }
        $('#edHistList').innerHTML =
          '<div class="ed-hist-head">' + (target ? '「' + E(target) + '」的改动' : '全部改动') +
          '（' + r.items.length + ' 条）</div>' +
          (r.items.length ? r.items.map(function (h) {
            return '<div class="ed-hist">' +
              '<span class="ed-hist-rev">#' + h.rev + '</span>' +
              '<span class="ed-hist-ts">' + E((h.ts || '').replace('T', ' ').replace('Z', '')) + '</span>' +
              '<span class="ed-hist-who">' + E(h.editor || '匿名') + '</span>' +
              '<span class="ed-hist-sum">' + E(h.summary || h.kind || '') + '</span>' +
              '<button class="wb-btn mini" data-rollback="' + h.rev + '">回滚到这版</button>' +
              '</div>';
          }).join('') : '<div class="dim">还没有历史记录</div>');
      });
  }

  function rollback(rev) {
    if (!confirm('回滚到 #' + rev + '？\n\n当前数据会被那一版覆盖（回滚本身也会记一条历史，随时能再退回来）。')) return;
    api('/api/rollback', { method: 'POST', body: { rev: rev, _editor: ED.who } })
      .then(function (r) {
        if (r && r.ok) { toast('已回滚 · 刷新中…'); setTimeout(function () { location.reload(); }, 800); }
        else toast('回滚失败：' + ((r && r.error) || ''), true);
      });
  }

  /* ══════════════════════════════════════════════════════════
     接线
     ══════════════════════════════════════════════════════════ */
  /* ══════════════════════════════════════════════════════════
     角色合并（2026-10-06 新增）
     场景：同一个人被建成了两份条目（拼音/别名/音近没归一时很常见）。
     语义：把**选中的那个并进当前这个**（当前 = dst 保留；选中 = src 消失）。
     ══════════════════════════════════════════════════════════ */
  var MG = { src: null, q: '' };

  function openMerge() {
    var el = $('#edMerge');
    if (!el || !ED.cur) return;
    MG.src = null; MG.q = '';
    var s = $('#edMergeSearch'); if (s) s.value = '';
    var p = $('#edMergePrev'); if (p) p.textContent = '还没有选角色';
    var g = $('#edMergeGo'); if (g) g.disabled = true;
    el.classList.add('on');
    renderMergeList('');
    setTimeout(function () { var i = $('#edMergeSearch'); if (i) i.focus(); }, 50);
  }
  function closeMerge() {
    var el = $('#edMerge'); if (el) el.classList.remove('on');
    MG.src = null;
  }

  function renderMergeList(q) {
    var box = $('#edMergeList'); if (!box) return;
    MG.q = q || '';
    var n = MG.q.trim().toLowerCase();
    var list = chars().filter(function (c) { return c.id !== ED.cur; });
    if (n) {
      list = list.filter(function (c) {
        var hay = [c.id, c.name, (c.groups || []).join('/'), (c.aliases || []).join('/')].join(' ').toLowerCase();
        return hay.indexOf(n) >= 0;
      });
    }
    var me = byId(ED.cur);
    list.sort(function (a, b) {
      // 同一个团的排前面（同一个人被建两份，多半在同一团）
      var am = ((me && me.groups) || []).some(function (x) { return (a.groups || []).indexOf(x) >= 0; }) ? 0 : 1;
      var bm = ((me && me.groups) || []).some(function (x) { return (b.groups || []).indexOf(x) >= 0; }) ? 0 : 1;
      return am - bm || relsOf(a.id).length - relsOf(b.id).length || String(a.name || '').localeCompare(String(b.name || ''));
    });
    box.innerHTML = list.slice(0, 60).map(function (c) {
      return '<a class="ed-mitem' + (MG.src === c.id ? ' on' : '') + '" data-mpick="' + E(c.id) + '">' +
        '<b>' + E(c.name || c.id) + '</b>' +
        '<i>' + E(c.id) + '</i>' +
        '<span>' + E((c.groups || []).join('/') || '—') + ' · ' + relsOf(c.id).length + ' 条关系</span></a>';
    }).join('') || '<div class="dim" style="padding:8px">没搜到</div>';
  }

  function pickMerge(id) {
    MG.src = id;
    renderMergeList(MG.q);
    var c = byId(id);
    var n = relsOf(id).length;
    var p = $('#edMergePrev');
    if (p) p.innerHTML = '把这个并进来：<b>' + E(c ? (c.name || id) : id) + '</b>' +
      '（' + E(id) + '）· 它会带着 <b>' + n + '</b> 条关系一起并入当前角色，然后消失。';
    var g = $('#edMergeGo'); if (g) g.disabled = false;
  }

  function doMerge() {
    if (!MG.src || !ED.cur) { toast('先选一个要并进来的角色', true); return; }
    var a = byId(MG.src), b = byId(ED.cur);
    var msg = '确定把「' + (a ? a.name : MG.src) + '」并进「' + (b ? b.name : ED.cur) + '」吗？\n\n' +
      '· 别名 / 出场团 / 标签 / 事件 / 属性 → 并集\n' +
      '· 它名下的 ' + relsOf(MG.src).length + ' 条关系 → 全部改指过来（重复的自动去掉）\n' +
      '· 被并掉的那个随后消失（可在历史里一键回滚）';
    if (!window.confirm(msg)) return;
    var btn = $('#edMergeGo'); if (btn) { btn.disabled = true; btn.textContent = '合并中…'; }
    api('/api/edit/merge', { method: 'POST', body: { src: MG.src, dst: ED.cur, _editor: ED.who } })
      .then(function (r) {
        if (!r || !r.ok) {
          toast('合并失败：' + ((r && r.error) || '未知错误'), true);
          if (btn) { btn.disabled = false; btn.textContent = '合并进来'; }
          return;
        }
        var m = r.merged || {};
        toast('已合并（关系 ' + (m.rels || 0) + ' 处，去重 ' + (m.dropped || 0) + ' 条）· 刷新中…');
        closeMerge();
        setTimeout(function () { location.reload(); }, 800);
      })
      .catch(function () {
        toast('合并失败：连不上服务器', true);
        if (btn) { btn.disabled = false; btn.textContent = '合并进来'; }
      });
  }

  function wireForm() {
    var p = $('#edProfile'), prev = $('#edPrev');
    if (p) p.addEventListener('input', function () {
      if (prev) prev.innerHTML = p.value ? md(p.value) : '<span class="dim">预览区</span>';
    });
    $$('#edForm [data-md]').forEach(function (b) {
      b.onclick = function () {
        var t = p, ins = b.dataset.md;
        if (!t) return;
        var s = t.selectionStart, e = t.selectionEnd, v = t.value;
        var sel = v.slice(s, e) || (ins === '## ' ? '小节名' : ins === '- ' ? '列表项' : ins === '> ' ? '台词' : '文字');
        var out;
        if (ins === '## ' || ins === '- ' || ins === '> ') out = ins + sel;
        else out = ins.slice(0, ins.indexOf('*') >= 0 ? 2 : 2) + sel + ins.slice(ins.length - 2);
        t.value = v.slice(0, s) + out + v.slice(e);
        t.focus(); t.selectionStart = s; t.selectionEnd = s + out.length;
        t.dispatchEvent(new Event('input'));
      };
    });
    $$('#edForm .ed-chip').forEach(function (ch) {
      ch.onclick = function () {
        var t = $('#edForm [data-f="attrs"]');
        if (!t) return;
        t.value = (t.value.replace(/\s+$/, '') + '\n' + ch.dataset.dim + ': ').replace(/^\n/, '');
        t.focus();
        t.selectionStart = t.selectionEnd = t.value.length;
      };
    });
  }

  function bootEditor() {
    api('/api/meta').then(function (r) { if (r && r.ok) ED.meta = r; });
    // 编辑器要能改所有人 → 额外拉一份全量（站点画图用的是选角后的子集）
    api('/api/data?scope=all').then(function (r) {
      if (r && r.ok && r.chars) {
        ED.all = r.chars;
        ED.rels = r.rels || [];
        renderList();
        if (ED.cur) renderForm();
      }
    });
    $('#edList').onclick = function (e) {
      var a = e.target.closest('[data-ed]');
      if (!a) return;
      ED.cur = a.dataset.ed;
      location.hash = '#/edit/' + ED.cur;
      renderList(); renderForm();
    };
    renderList();
    renderForm();
    if (ED.cur) setTimeout(function () { var f = $('#edSearch'); if (f) f.focus(); }, 30);
  }

  window.__editorOpen = openEditor;
  /* wiki.js 的 curHash() 要用它把当前编辑的角色写回地址栏（否则 #/edit/<id> 会被抹成 #/edit） */
  window.__editorId = function () { return ED.cur || null; };

  /* ⚠️ editor.js 是**动态加载**的（wiki-boot → app.js → wiki.js → editor.js），
     执行时 DOMContentLoaded **早就触发过了** —— 如果把绑定写进
     `document.addEventListener('DOMContentLoaded', …)`，它永远不会跑，
     表现就是「按钮点了毫无反应、请求根本没发出去」（2026-10-06 踩过，日志里连
     一条 POST /api/edit/char 都没有，查了半天）。所以按 readyState 判断。 */
  function wireEditor() {
    var el = $('#editor');
    if (!el) { console.warn('[editor] 缺 #editor 节点，跳过绑定'); return; }
    $('#edClose').onclick = closeEditor;
    $('#edSearch').addEventListener('input', renderList);
    $('#edNew').onclick = newChar;
    $('#edHist').onclick = function () { openHistory(null); };
    $('#edHistClose').onclick = function () { $('#edHistory').classList.remove('on'); };
    document.addEventListener('click', function (e) {
      var ed = e.target.closest('[data-ed]');
      if (ed && $('#editor').classList.contains('on')) {
        ED.cur = ed.dataset.ed;
        location.hash = '#/edit/' + ED.cur;
        renderList(); renderForm();
      }
      if (e.target.id === 'edSave') saveChar();
      if (e.target.id === 'edHistBtn') openHistory(ED.cur);
      if (e.target.id === 'edDel') deleteChar();
      if (e.target.id === 'edMergeBtn') openMerge();
      var mc = e.target.closest('[data-mpick]');
      if (mc) pickMerge(mc.dataset.mpick);
      if (e.target.id === 'edMergeGo') doMerge();
      if (e.target.id === 'edMergeClose') closeMerge();
      if (e.target.id === 'edRelAdd') addRel();
      var rs = e.target.closest('[data-relsave]');
      if (rs) saveRel(+rs.dataset.relsave);
      var rd = e.target.closest('[data-reldel]');
      if (rd) delRel(+rd.dataset.reldel);
      var rb = e.target.closest('[data-rollback]');
      if (rb) rollback(+rb.dataset.rollback);
    });
    console.log('[editor] 就绪');
    /* 合并窗口：搜索框 + Esc 关闭 */
    var mSearch = $('#edMergeSearch');
    if (mSearch) {
      mSearch.addEventListener('input', function () { renderMergeList(mSearch.value); });
      mSearch.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          var first = document.querySelector('#edMergeList .ed-mitem');
          if (first) pickMerge(first.dataset.mpick);
        }
      });
    }
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && $('#edMerge') && $('#edMerge').classList.contains('on')) closeMerge();
    });
    /* ⚠️ editor.js 比 wiki.js **晚加载**（wiki-boot → app → wiki → editor），
       wiki.js 跑首屏路由时 window.__editorOpen 还不存在，`#/edit` 会被静默跳过。
       所以这里自己补一次：如果当前 hash 就是编辑器，主动打开。 */
    if (/^#\/edit/.test(location.hash || '')) {
      var seg = String(location.hash).split('/');
      openEditor(seg[2] || null);
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', wireEditor);
  else wireEditor();
})();
