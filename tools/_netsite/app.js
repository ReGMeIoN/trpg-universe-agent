/* ============================================================
   跑团宇宙 · 角色关系网  —  应用逻辑
   三层钻取：势力总览 ► 卡片关系网 ► 人物档案
   布局是**确定性**的（不用力导向）：每次打开一样，方便对照与截图。
   ============================================================ */
'use strict';
const N = window.NET;
const CH = new Map(N.chars.map(c => [c.id, c]));
const KIND_COLOR = { PC: '#d8b25a', NPC: '#93a4b6', BOSS: '#d95c5c', '跨团': '#b07ad9', KP: '#5aa9d8' };
/* 卡片尺寸与格距。
   ⚠️ 必须和 CSS 的 `--card-w/--card-h` 保持一致：**坐标是 JS 算的、外观是 CSS 画的**，
      两边不一致就会「卡片互相压住」或「中间空一大块」。
   手机竖屏整体缩小一档：同样屏宽能多放几张，自动缩放也不至于把名字糊成一片。*/
const NARROW = window.innerWidth <= 900;   // ⚠️ 必须和 CSS 主断点(900px)一致，否则平板竖屏会「CSS 用手机布局、JS 用桌面尺寸」→ 卡片被压到 0.35x 糊掉
const CW = NARROW ? 92 : 120, CHh = NARROW ? 138 : 180;   // 卡片尺寸
const GX = NARROW ? 108 : 138, GY = NARROW ? 152 : 196;   // 格距
if (NARROW) {
  document.documentElement.style.setProperty('--card-w', CW + 'px');
  document.documentElement.style.setProperty('--card-h', CHh + 'px');
}

/* ── 邻接表 ───────────────────────────────────────────────── */
const ADJ = new Map();
CH.forEach((_, id) => ADJ.set(id, []));
N.rels.forEach(r => {
  if (CH.has(r.a) && CH.has(r.b)) {
    ADJ.get(r.a).push({ o: r.b, r, out: true });
    ADJ.get(r.b).push({ o: r.a, r, out: false });
  }
});
const degree = id => ADJ.get(id) ? ADJ.get(id).length : 0;
const SORD = { '强': 0, '中': 1, '弱': 2, '': 3 };

/* ── 状态 ─────────────────────────────────────────────────── */
const S = { view: 'overview', ent: null, focus: null, persp: 'group', cam: { x: 0, y: 0, k: 1 } };
const $ = s => document.querySelector(s);
const stage = $('#stage'), world = $('#world'), svg = $('#links');
const elHulls = $('#hulls'), elCards = $('#cards'), elLabels = $('#labels');

/* ── 实体（总览层的分组单元）───────────────────────────────── */
function entities() {
  const map = new Map();
  const push = (k, id, color) => {
    if (!map.has(k)) map.set(k, { key: k, name: k, ids: [], color: color || '#8fa3b8' });
    map.get(k).ids.push(id);
  };
  if (S.persp === 'group') {
    const gc = new Map(N.groups.map(g => [g.name, g]));
    CH.forEach(c => (c.groups.length ? c.groups : ['(未分组)']).forEach(g =>
      push(g, c.id, (gc.get(g) || {}).color)));
    /* 一个角色可能出现在多个团 → 总览里只算「主团」。
       ⚠️ 别再按 `N.groups` 的当前顺序判定：那个顺序是**按人数降序**的，
          某个团涨了一个人就会换序 → 跨团角色的归属跟着变 → 总览跟着抖。
          改成**按团名的稳定哈希**排序（与人数、与数据文件顺序都无关）。 */
    const order = [...map.keys()].sort((a, b) =>
      (stableHash(a) >>> 0) - (stableHash(b) >>> 0) || String(a).localeCompare(String(b)));
    const owner = new Map();
    order.forEach(g => map.get(g).ids.forEach(id => { if (!owner.has(id)) owner.set(id, g); }));
    map.forEach(e => { e.ids = e.ids.filter(id => owner.get(id) === e.key); });
  } else if (S.persp === 'creator') {
    CH.forEach(c => push(c.played_by || '(未记录)', c.id));
  } else {
    CH.forEach(c => push(c.kind, c.id, KIND_COLOR[c.kind]));
  }
  const UNI = ['#d8b25a', '#6fd6c0', '#c86fd6', '#e08a5a', '#7fa8e8', '#e0709a',
    '#9aa7b8', '#4fa3c7', '#b07ad9', '#8fbf6a', '#d95c5c', '#5aa9d8'];
  let ui = 0;
  map.forEach(e => { if (!e.color || e.color === '#8fa3b8') e.color = UNI[(ui++) % UNI.length]; });
  return [...map.values()].sort((a, b) => b.ids.length - a.ids.length);
}

/* ── 相机 ─────────────────────────────────────────────────── */
function setCam(anim = true) {
  world.style.transition = anim ? 'transform .45s cubic-bezier(.2,.8,.3,1)' : 'none';
  world.style.transform = `translate(${S.cam.x}px,${S.cam.y}px) scale(${S.cam.k})`;
}
function fitBox(x0, y0, x1, y1, pad = 90, minK = 0) {
  const W = stage.clientWidth, H = stage.clientHeight;
  const w = Math.max(1, x1 - x0 + pad * 2), h = Math.max(1, y1 - y0 + pad * 2);
  let k = Math.min(W / w, H / h, 1.6);
  // 手机竖屏：十几个势力/几十张卡塞进 375px 会缩到 0.2x，字全糊 →
  // 给一个「可读下限」，一屏放不下的部分靠拖动 / 捏合看（宁可少看几个，也别糊成一片）。
  if (minK) k = Math.min(1.6, Math.max(k, minK));
  S.cam = { k, x: (W - (x0 + x1) * k) / 2, y: (H - (y0 + y1) * k) / 2 + 12 };
  setCam(true);
}
function zoomAt(cx, cy, f) {
  const k2 = Math.min(3.2, Math.max(.22, S.cam.k * f));
  const r = k2 / S.cam.k;
  S.cam.x = cx - (cx - S.cam.x) * r;
  S.cam.y = cy - (cy - S.cam.y) * r;
  S.cam.k = k2; setCam(false);
}
/* ── 交互：鼠标 + 触摸统一（2026-10-06 加触摸支持）─────────────
   桌面行为**完全不变**：滚轮缩放 / 单键拖拽平移 / 双击空白复位。
   触摸新增：单指拖动平移 · 双指捏合缩放 · 快速双击空白复位。
   ⚠️ 必须搭配 CSS 的 `#stage{touch-action:none}`：否则浏览器会抢走手势
      （单指当页面滚动、双指当整页缩放），拖到一半还发 pointercancel ——
      表现就是「滑动乱跳、拖不动、缩放失控」。 */
const CLICKABLE = '.card,.tile,.hex';
const topH = () => stage.getBoundingClientRect().top;   // 顶栏高（手机 48 / 桌面 54，别再写死 54）
const pts = new Map();                                  // 当前按下的触点
let drag = null, pinch = null, moved = 0, tapT = 0, tapX = 0, tapY = 0, downOnCard = false;

stage.addEventListener('wheel', e => {
  e.preventDefault();
  zoomAt(e.clientX, e.clientY - topH(), e.deltaY < 0 ? 1.12 : .89);
}, { passive: false });

stage.addEventListener('pointerdown', e => {
  pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pts.size === 2) {                       // 第二根手指落下 → 进入捏合
    drag = null; moved = 0; stage.classList.remove('grabbing');
    const [a, b] = [...pts.values()];
    pinch = { d: Math.hypot(a.x - b.x, a.y - b.y) || 1, k: S.cam.k };
    stage.setPointerCapture(e.pointerId);
    return;
  }
  // ⚠️ 可点击元素必须全列上：漏了 `.tile` 的话会走拖拽分支 →
  //    setPointerCapture() 把后续指针事件全截走，封面六边形**点了没反应**（2026-10-05 踩过）。
  downOnCard = !!e.target.closest(CLICKABLE);
  if (downOnCard) return;
  drag = { x: e.clientX, y: e.clientY, ox: S.cam.x, oy: S.cam.y };
  moved = 0;
  stage.classList.add('grabbing'); stage.setPointerCapture(e.pointerId);
});

stage.addEventListener('pointermove', e => {
  if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
  if (pinch && pts.size >= 2) {               // 双指捏合：绕两指中点缩放
    const [a, b] = [...pts.values()];
    const d = Math.hypot(a.x - b.x, a.y - b.y) || 1;
    const want = Math.min(3.2, Math.max(.22, pinch.k * (d / pinch.d)));
    zoomAt((a.x + b.x) / 2, (a.y + b.y) / 2 - topH(), want / S.cam.k);
    return;
  }
  if (!drag) return;
  const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
  moved = Math.max(moved, Math.hypot(dx, dy));
  S.cam.x = drag.ox + dx; S.cam.y = drag.oy + dy; setCam(false);
});

function endPointer(e) {
  pts.delete(e.pointerId);
  if (pts.size < 2) pinch = null;
  if (pts.size) return;
  // 触摸设备不产生 dblclick：自己判「快速双击空白」→ 复位（鼠标仍走下面的 dblclick）
  if (e.type === 'pointerup' && !downOnCard && moved < 8) {
    const now = Date.now();
    if (now - tapT < 340 && Math.hypot(e.clientX - tapX, e.clientY - tapY) < 36) { goOverview(); tapT = 0; }
    else { tapT = now; tapX = e.clientX; tapY = e.clientY; }
  }
  drag = null; downOnCard = false; stage.classList.remove('grabbing');
}
stage.addEventListener('pointerup', endPointer);
stage.addEventListener('pointercancel', endPointer);   // 手势被系统打断也要复位，否则拖拽卡死
stage.addEventListener('dblclick', e => { if (!e.target.closest('.card,.hex')) goOverview(); });

/* ── 二级分类：阵营 ───────────────────────────────────────── */
/* 之前是按「度数最高的那个人」贪心分裂、再用他的名字当组名（会出现「神川玛利亚组」这种
   看着像"某人的小队"的标签）。改成**用库里的真实字段分类**：
   tags 里的 KP / 跨团 / BOSS / PC 就是权威阵营标记，其余归 NPC（= `kind` 字段，builder 已算好）。
   组内不再切子簇、也不再用人名，人多的阵营按方形排布（横向铺开，不堆成竖条）。 */
const CAMPS = ['玩家角色', 'NPC', 'BOSS', '跨团', 'KP'];
// ⚠️ 用**中英对照**认阵营，别只查 CAMP_EN：kind 恰好等于 'NPC' 时 CAMP_EN 查不到，
//    旧写法会把所有 NPC 都塞进 'NPC' 这一个桶里（看着像全团都是 NPC）。
const CAMP_NAMES = new Set(['玩家角色', 'NPC', 'BOSS', '跨团', 'KP']);
const CAMP_EN = { '玩家角色': 'PLAYER CHARACTERS', 'NPC': 'NON-PLAYER CHARACTERS', 'BOSS': 'ANTAGONISTS / BOSS', '跨团': 'CROSS-CAMPAIGN', 'KP': 'GAME MASTER' };
function campOf(c) { return c.kind === 'PC' ? '玩家角色' : (CAMP_NAMES.has(c.kind) ? c.kind : 'NPC'); }

function camps(ids) {
  const m = new Map();
  ids.forEach(id => {
    const c = CH.get(id); if (!c) return;
    const k = campOf(c);
    if (!m.has(k)) m.set(k, []);
    m.get(k).push(id);
  });
  return [...m.entries()]
    .map(([name, list]) => ({
      name, ids: list.sort((a, b) => degree(b) - degree(a) || (CH.get(a).name || '').localeCompare(CH.get(b).name || '')),
      color: list.length ? (KIND_COLOR[CH.get(list[0]).kind] || '#8fa3b8') : '#8fa3b8',
    }))
    .sort((a, b) => b.ids.length - a.ids.length);
}

/* 给测试/调试用：拿到某个实体的布局结果 */
function layoutOf(key) {
  const ent = entities().find(e => e.key === key) || entities()[0];
  if (!ent) return null;
  const L = layoutEntity(ent);
  const pos = {}, slots = {}, slotOf = {};
  L.pos.forEach((v, k) => pos[k] = [v.x, v.y]);
  L.slots.forEach((v, k) => slots[k] = [v.x, v.y]);
  L.slotOf.forEach((v, k) => slotOf[k] = v);
  return { key: ent.key, ids: ent.ids, pos, slots, slotOf };
}

/* 重建邻接表 + 重画当前视图。
   用途：编辑器改了关系之后要让图立刻跟着变；测试也靠它验证「加关系不改位置」。 */
function refreshGraph() {
  ADJ.clear();
  CH.forEach((_, id) => ADJ.set(id, []));
  N.rels.forEach(r => {
    if (CH.has(r.a) && CH.has(r.b)) {
      ADJ.get(r.a).push({ o: r.b, r, out: true });
      ADJ.get(r.b).push({ o: r.a, r, out: false });
    }
  });
  if (S.view === 'overview') renderOverview(); else renderEntity();
}

/* ── 布局：稳定槽位（2026-10-06 重写）──────────────────────────
   旧实现的病根：位置由「关系度数」和「块的动态列数」推导 ——
   任何人加一条关系、任何一个阵营多一个人，**全团卡片都会重新排座**，
   表现就是「排版错位 / 新角色跟别人重合」。
   现在改成**只增不改的槽位账本**：
     · 谁在哪个槽位由 (名字, id) 排序决定（与关系、与数据文件顺序都无关）；
     · 槽位一旦分配**永不回收**（继承历史 max+1），删除/新增别的人不会顶替它；
     · 网格容量按人数增长，位置只可能「往后长」，不会把已有卡片挤走；
     · 人工微调（拖动换位）只在账本里改 x/y 覆盖，不动自动槽位。
   所以：**加角色 / 加关系之后，已有卡片一个都不动。** */
function stableHash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); }
  return h;
}
/* 把一组成员排成网格。
   ⚠️ **块内位置只由「成员在本块内的相对次序」决定**，与全库关系、数据顺序无关；
      这个次序来自**只增不改的槽位账本**（见 assignSlots）：老成员次序永不变，
      新人一律排在最后 → **加人不会把老卡的发散位置挤走**。
   格子数按「容量档位」阶梯增长（1→4→9→25→…），块长宽比只在跨档时跳一次，
   避免每加一个人就把块重新排一遍（旧实现是 ceil(sqrt(n*1.7))，人数一变就全挪）。 */
function gridFor(n) {
  const steps = [1, 4, 9, 25, 36, 49, 64, 81];
  const cols = steps.find(s => s >= Math.max(1, n)) || Math.ceil(Math.sqrt(n));
  return { cols, rows: Math.max(1, Math.ceil(n / cols)) };
}
function slotGrid(A, keys) {
  if (!keys.length) return { cols: 1, rows: 1, map: new Map() };
  assignSlots(A, keys);
  const ordered = [...keys].sort((a, b) =>
    A.slotOf[a] - A.slotOf[b] || (stableHash(a) >>> 0) - (stableHash(b) >>> 0) || a.localeCompare(b));
  const { cols, rows } = gridFor(ordered.length);
  const map = new Map();
  ordered.forEach((k, i) => map.set(k, i));
  return { cols, rows, map };
}
/* 槽位号 → 团内网格坐标（行优先，与人数无关 → 加人不动老位置） */
function slotXY(slot, cols) {
  return { x: (slot % cols) * GX, y: Math.floor(slot / cols) * GY };
}
/* 归一化：某个成员名与别的阵营同名时（如 kind 恰好叫 'NPC'）不算撞名，故只比名字 */
function memberKey(id, c) { return (c.name || '') + '\u0000' + id; }
const byKey = (a, b) => (stableHash(a) >>> 0) - (stableHash(b) >>> 0) || a.localeCompare(b);
function slotAssignment(keys) {
  const uniq = [...new Set(keys)].sort((a, b) => (stableHash(a) >>> 0) - (stableHash(b) >>> 0) || a.localeCompare(b));
  const n = uniq.length;
  for (let extra = 0; extra <= 3; extra++) {
    const { cols, rows } = gridFor(n + extra * 2);
    const cur = new Map();
    uniq.forEach((k, i) => cur.set(k, i));
    // 校验：任意两个成员不能落在同一格（代数上不会发生，留作保险）
    const seen = new Set(); let clash = false;
    cur.forEach(v => { if (seen.has(v)) clash = true; seen.add(v); });
    if (!clash) return { cols, rows, map: cur };
  }
  return gridFor(n) && { cols: 3, rows: Math.ceil(n / 3), map: new Map(uniq.map((k, i) => [k, i])) };
}
/* 网格对齐判据：把屏幕/逻辑坐标吸到最近的格，用来判断「两张卡是不是同一格」。
   （卡片的坐标不一定落在 GX/GY 整数倍上——块内左对齐、人工微调都会带偏移，
     所以判重必须**先对齐**，否则会误判成不重叠而叠在一起。） */
function cellOf(x, y) { return Math.round(x / GX) + ':' + Math.round(y / GY); }
function snapToGrid(x, y) { return { x: Math.round(x / GX) * GX, y: Math.round(y / GY) * GY }; }
/* 找一个「和给定 id 最近」的槽位占位者（拖动换位用） */
function nearestKey(map, tx, ty, cols) {
  let best = null, bd = Infinity;
  map.forEach((slot, key) => {
    const p = slotXY(slot, cols);
    const d = (p.x - tx) * (p.x - tx) + (p.y - ty) * (p.y - ty);
    if (d < bd) { bd = d; best = key; }
  });
  return best;
}
/* ── 撤销 / 复位（2026-10-06 新增）──────────────────────────────
   主人反馈：「拖出去之后放不回去」——所以拖动一律可撤销，且能一键复位。
   三层保护：
     · 双击卡片 → 这张卡**单独复位**（回到自动槽位）；
     · 工具栏「⤾ 复位排版」→ **清空全部人工微调**（槽位账本保留，位置关系不乱）；
     · `Ctrl+Z`（或工具栏的「↶ 撤销」）→ **撤销上一次拖动**（内存里存了前一份账本）。 */
const UNDO = [];
function pushUndo(id, posJson) {
  try {
    UNDO.push({ id: id, pos: posJson });
    if (UNDO.length > 30) UNDO.shift();
  } catch (e) { /* 忽略 */ }
  syncUndoBtn();
}
function syncUndoBtn() {
  const b = $('#btnUndo');
  if (!b) return;
  b.disabled = !UNDO.length;
  b.style.opacity = UNDO.length ? '1' : '.4';
}
/* 把当前账本（含槽位）写回服务器 —— "复位"必须**连槽位账本一起同步**：
   只清本地 pos 的话，服务器上那份 slots 下次打开还会把旧顺序带回来。 */
function syncLayoutNow() {
  const A = loadAdj();
  const token = localStorage.getItem('trpg-edit-token') || localStorage.getItem('trpg_edit_token') || '';
  if (!token) return;
  fetch('/api/layout', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Edit-Token': token },
    body: JSON.stringify({ pos: A.pos || {}, slots: A.slotOf || {} }),
  }).catch(() => { /* 离线无所谓 */ });
}
/* 显式让服务器清空布局账本（复位排版用）。
   ⚠️ 别用「POST 空 pos」代替：服务端虽然也认，但语义不如 `reset:true` 明确，
      而且早期版本会直接 400（回归里表现为"复位后刷新又跑回去"）。 */
function resetLayoutServer() {
  const token = localStorage.getItem('trpg-edit-token') || localStorage.getItem('trpg_edit_token') || '';
  if (!token) return;
  fetch('/api/layout', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Edit-Token': token },
    body: JSON.stringify({ reset: true, _editor: '复位排版' }),
  }).catch(() => { /* 离线无所谓 */ });
}
function undoDrag() {
  const last = UNDO.pop();
  if (!last) { showHint('没有可撤销的拖动'); return; }
  const A = loadAdj();
  try { A.pos = JSON.parse(last.pos || '{}'); } catch (e) { A.pos = {}; }
  saveAdj();
  syncLayoutNow();
  syncUndoBtn();
  if (S.view === 'overview') renderOverview(); else renderEntity();
  const nm = CH.get(last.id);
  showHint('已撤销「' + ((nm && nm.name) || last.id) + '」的拖动');
}
/* 单张卡片复位：删掉它的人工偏移 */
function resetCardPos(id) {
  const A = loadAdj();
  if (!A.pos || !(id in A.pos)) { showHint('这张卡本来就在自动位置'); return; }
  pushUndo(id, JSON.stringify(A.pos));
  delete A.pos[id];
  saveAdj();
  syncLayoutNow();
  if (S.view === 'overview') renderOverview(); else renderEntity();
  const nm = CH.get(id);
  showHint('已复位「' + ((nm && nm.name) || id) + '」');
}
function resetLayoutAll() {
  const A = loadAdj();
  const n = Object.keys(A.pos || {}).length;
  if (!n) { showHint('现在就是自动排版，没有需要复位的'); return; }
  pushUndo('*', JSON.stringify(A.pos));
  A.pos = {};
  saveAdj();
  resetLayoutServer();                   // 显式重置：连服务器账本一起清（否则刷新又跑回去）
  if (S.view === 'overview') renderOverview(); else renderEntity();
  showHint('已复位全部 ' + n + ' 张卡片（可用 Ctrl+Z 撤销）');
}

/* ── 拖动换位 + 人工微调账本（2026-10-06 新增）────────────────
   位置 = 自动槽位（稳定） + `__layoutAdj.pos`（人工微调）。
   拖动只改「这两张卡的位置覆盖」，不动别人的槽位；存 localStorage，
   编辑器登录过的话再 POST 回 `/api/layout`（全站生效）。 */
const DRAG = { el: null, id: null, key: null, sx: 0, sy: 0, ox: 0, oy: 0, cx: 0, cy: 0,
               live: false, moved: 0 };
const LAYOUT_ADJ = { mode: 'shift' };   // shift=交换两张卡
function loadAdj() {
  if (window.__layoutAdj && window.__layoutAdj.pos) return window.__layoutAdj;
  let pos = {}, slotOf = {};
  try {
    pos = JSON.parse(localStorage.getItem('trpg-net-layout') || '{}') || {};
    slotOf = JSON.parse(localStorage.getItem('trpg-net-slots') || '{}') || {};
  } catch (e) { pos = {}; slotOf = {}; }
  window.__layoutAdj = { pos, slotOf };
  return window.__layoutAdj;
}
function saveAdj() {
  const A = window.__layoutAdj || {};
  try {
    localStorage.setItem('trpg-net-layout', JSON.stringify(A.pos || {}));
    localStorage.setItem('trpg-net-slots', JSON.stringify(A.slotOf || {}));
  } catch (e) { /* 隐私模式等，忽略 */ }
  const token = localStorage.getItem('trpg-edit-token') || localStorage.getItem('trpg_edit_token') || '';
  if (!token) return;                                    // 没登录编辑器 → 只影响本机
  fetch('/api/layout', {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Edit-Token': token },
    body: JSON.stringify({ pos: A.pos || {}, slots: A.slotOf || {} }),
  }).catch(() => { /* 离线 / 静态部署：静默 */ });
}

/* ── 槽位账本：**只增不改** ─────────────────────────────────
   规则（这是"加人不会挤走老卡"的关键）：
     · 一个成员一旦拿到槽位号，**永久保留**（存在 localStorage / `layout.json`）；
     · 没见过的新成员，按 `(名字, id)` 排序**追加到现有最大号之后**；
     · 槽位号只增不减 —— 删了人也不回收，免得回收后把别人的位置顶掉。
   顺带产出的一个好处：位置与「关系度数」「阵营人数」彻底无关，
   所以加关系、加角色都不会让任何人挪窝。 */
function slotOfKey(A, key) {
  if (A.slotOf && typeof A.slotOf[key] === 'number') return A.slotOf[key];
  return null;
}
function assignSlots(A, keys) {
  A.slotOf = A.slotOf || {};
  /* ⚠️ 关键：账本里**已经有过**的槽位号直接复用，且**新号只能比它们更大**。
     决不能"重算一个全局排序再发号"——那样加入一个新成员会让所有哈希顺序
     在其后面的人都换号，位置就跟着动了（本轮踩过：加一条关系后 3 张卡跳行）。 */
  let next = 0;
  Object.keys(A.slotOf).forEach(k => { next = Math.max(next, A.slotOf[k] + 1); });
  const fresh = keys.filter(k => typeof A.slotOf[k] !== 'number')
    .sort((a, b) => (stableHash(a) >>> 0) - (stableHash(b) >>> 0) || a.localeCompare(b));
  let changed = false;
  fresh.forEach(k => { A.slotOf[k] = next++; changed = true; });
  if (changed) saveAdj();
  return keys.map(k => A.slotOf[k]);
}
function cardDragActive(place) { return { shift: '交换位置', pos: '只挪这一张' }[place] || '交换位置'; }
function bindCardDrag(el, id) {
  el.addEventListener('pointerdown', ev => {
    if (ev.button !== 0) return;
    ev.stopPropagation();                                // 别让 stage 进入拖画布分支
    DRAG.el = el; DRAG.id = id; DRAG.key = el.dataset.key;
    DRAG.sx = ev.clientX; DRAG.sy = ev.clientY;
    DRAG.ox = parseFloat(el.style.left) || 0; DRAG.oy = parseFloat(el.style.top) || 0;
    DRAG.cx = DRAG.ox; DRAG.cy = DRAG.oy;      // ← 跟随中的当前位置（松手时按它结算）
    DRAG.live = false; DRAG.moved = 0;
    try { el.setPointerCapture(ev.pointerId); } catch (e) { /* 某些浏览器不支持，忽略 */ }
  });
  el.addEventListener('pointermove', ev => {
    if (DRAG.el !== el) return;
    const dx = ev.clientX - DRAG.sx, dy = ev.clientY - DRAG.sy;
    DRAG.moved = Math.max(DRAG.moved, Math.abs(dx) + Math.abs(dy));
    const s = S.cam.k || 1;
    if (!DRAG.live && Math.hypot(dx, dy) < 5) return;     // 5px 死区：普通点击不误触
    if (!DRAG.live) { DRAG.live = true; el.classList.add('dragging'); el.style.zIndex = 30; }
    /* ⚠️ **同步**更新位置，别用 requestAnimationFrame：
       松手（pointerup）与 rAF 回调没有先后保证 —— 曾经因此读到"中间位置"，
       于是算出来的偏移是错的（撤销/复位都回不到原位），2026-10-06 被回归抓到。 */
    DRAG.cx = DRAG.ox + dx / s;
    DRAG.cy = DRAG.oy + dy / s;
    el.style.left = DRAG.cx + 'px';
    el.style.top = DRAG.cy + 'px';
  });
  const end = ev => {
    if (DRAG.el !== el) return;
    const wasLive = DRAG.live; DRAG.el = null; DRAG.live = false;
    el.classList.remove('dragging'); el.style.zIndex = '';
    if (!wasLive) { DRAG.moved = 0; return; }             // 没真拖 → 交给 onclick
    const x = DRAG.cx + CW / 2, y = DRAG.cy + CHh / 2;    // ← 用跟随时的实测坐标
    /* 判「拖到谁身上」必须用**起始落点**，不能用拖动后的位置：
       用拖动后的位置时，落点常常离别的卡更近 → 换错目标（还会连带把两张卡叠一起）。 */
    const x0 = DRAG.ox + CW / 2, y0 = DRAG.oy + CHh / 2;
    const map = (LAST && LAST.slotOf) || new Map();       // key -> slot
    const keyById = new Map();
    if (LAST && LAST.pos) [...LAST.pos.keys()].forEach(cid => keyById.set(memberKey(cid, CH.get(cid)), cid));
    const cols = map.size ? gridFor(map.size).cols : 4;
    const nearKey = nearestKey(map, x0, y0, cols);
    const adj = loadAdj();
    const baseOf = id => (LAST && LAST.slots && LAST.slots.get(id)) || (LAST && LAST.pos.get(id)) || { x, y };
    const offsetOf = (id, tx, ty) => { const b = baseOf(id); return [Math.round(tx - b.x), Math.round(ty - b.y)]; };
    const mySlot = map.get(DRAG.key);
    /* 一律吸附：把落点吸到最近的格子；那一格被占就螺旋找最近空位。
       ⚠️ 旧写法要求"落点必须命中别的卡片"才生效 —— 拖到空位松手就**什么都不做**，
          表现就是主人说的「移动出来后放不回去」（2026-10-06 回归确认）。 */
    {
      const t0 = snapToGrid(x0, y0);
      let gx = t0.x, gy = t0.y, k = 0;
      const occupied = new Set(LAST.occupied || []);
      const myP = LAST.pos.get(id) || { x: gx, y: gy };
      occupied.delete(cellOf(myP.x, myP.y));              // 腾出自己原来的格子
      const spiral = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1],
                      [1, 1], [-1, 1], [1, -1], [-1, -1],
                      [2, 0], [-2, 0], [0, 2], [0, -2],
                      [2, 1], [-2, 1], [1, 2], [-1, 2], [2, 2], [-2, -2]];
      /* 先把落点**限制在实体范围内**：不然能把卡片拖到画布外几千像素，
         再也点不到它（只能靠"复位"救）。边界用当前实体的bounds外扩两格。 */
      if (LAST.bounds) {
        const pad = 2;
        const minX = LAST.bounds.x0 - pad * GX, maxX = LAST.bounds.x1 + pad * GX;
        const minY = LAST.bounds.y0 - pad * GY, maxY = LAST.bounds.y1 + pad * GY;
        t0.x = Math.min(Math.max(t0.x, minX), maxX);
        t0.y = Math.min(Math.max(t0.y, minY), maxY);
      }
      for (const [sx, sy] of spiral) {
        const cx2 = t0.x + sx * GX, cy2 = t0.y + sy * GY;
        if (!occupied.has(cellOf(cx2, cy2))) { gx = cx2; gy = cy2; k = Math.abs(sx) + Math.abs(sy); break; }
      }
      pushUndo(id, JSON.stringify(adj.pos));               // ← 记住拖动前的账本，供撤销
      adj.pos[id] = offsetOf(id, gx, gy);
      showHint('位置已记住（吸附到' + (k ? '最近的空格' : '目标格') + '）'
               + ' · 双击这张卡可复位 · 工具栏「复位排版」可全部还原 · Ctrl+Z 撤销');
    }
    saveAdj();
    renderEntity();
  };
  el.addEventListener('pointerup', end);
  el.addEventListener('pointercancel', end);
}

/* ── 布局：实体视图（块 + 槽位）───────────────────────────── */
function layoutEntity(ent) {
  const members = [...new Set(ent.ids.filter(i => CH.has(i)))];   // 去重（旧实现会同一 id 画两张卡）
  const mset = new Set(members);
  const outside = new Set();
  members.forEach(i => (ADJ.get(i) || []).forEach(x => { if (!mset.has(x.o) && CH.has(x.o)) outside.add(x.o); }));
  const outsideIds = [...outside].sort((a, b) =>
    (stableHash(memberKey(a, CH.get(a))) >>> 0) - (stableHash(memberKey(b, CH.get(b))) >>> 0) ||
    (CH.get(a).name || '').localeCompare(CH.get(b).name || '') || a.localeCompare(b));

  const groups = camps(members);
  const GAPX = 150, GAPY = 190, MAXROW = 980;   // MAXROW 固定 → 行切分与人数、面积都无关
  const pos = new Map(), slotOf = new Map(), centers = [], labels = [];
  const A = loadAdj();
  let maxBottom = 0;

  /* ⚠️ 所有块用**同一个列数** → 块宽是常量 → 块的位置只由「块的顺序」决定，
     与块里有几个人、用了第几行**完全无关**。这是"加人不动别人"的关键：
     旧实现让块宽随内容变，于是每加一个人，货架重排、整行居中偏移都跟着变。 */
  const UNIFORM_COLS = 6;
  const blockW = (UNIFORM_COLS - 1) * GX + CW;

  const blocks = groups.map(g => {
    const keys = g.ids.map(i => memberKey(i, CH.get(i))).sort(byKey);
    const asg = slotGrid(A, keys);
    const cols = Math.min(asg.cols, UNIFORM_COLS);
    const rows = Math.ceil(g.ids.length / cols);
    return { g, cols, rows, w: blockW, h: (rows - 1) * GY + CHh, asg };
  });

  // 货架：一行装不装得下只看**每行上限**，不看全局面积 → 加人/加块都不会把后面的块挤走
  const rowsArr = []; let cur = [], curW = 0;
  blocks.forEach(b => {
    const add = cur.length ? b.w + GAPX : b.w;
    if (cur.length && curW + add > MAXROW) { rowsArr.push({ items: cur, w: curW }); cur = []; curW = 0; }
    cur.push(b); curW += cur.length > 1 ? b.w + GAPX : b.w;
  });
  if (cur.length) rowsArr.push({ items: cur, w: curW });

  let y = 0;
  rowsArr.forEach(row => {
    const rowH = Math.max(...row.items.map(b => b.h));   // 行高对该行所有块一致 → 顶部对齐即可
    let x = -row.w / 2;
    row.items.forEach(b => {
      /* 块内定位：序号 → 格 → 块坐标。**序号 = 槽位账本里的相对次序**，
         与关系、与数据顺序都无关；新人永远追加在后面，老卡的格不会动。
         ⚠️ 每行**左对齐**（不做逐行居中）：居中会让"最后一行多来一个人"时
            整行一起左移——那正是主人抱怨的「加了新角色，老卡就挪窝」。 */
      b.g.ids.forEach(id => {
        const key = memberKey(id, CH.get(id));
        const seq = b.asg.map.get(key);
        const r = Math.floor(seq / b.cols), c = seq % b.cols;
        const p = { x: c * GX, y: r * GY };
        pos.set(id, { x: x + b.w / 2 + p.x - (b.cols - 1) * GX / 2, y: y + CHh / 2 + p.y });
        slotOf.set(key, seq);
      });
      centers.push({ g: b.g, cx: x + b.w / 2, cy: y + rowH / 2, w: b.w, h: b.h });
      labels.push({ text: `<b>${esc(b.g.name)}</b> · ${b.g.ids.length} 人`,
                    x: x + b.w / 2 - (b.cols - 1) * GX / 2 - CW / 2 - 14,
                    y: y - 26 });
      maxBottom = Math.max(maxBottom, y + b.h);
      x += b.w + GAPX;
    });
    y += rowH + GAPY;
  });

  // 关联区：**起点只由团内总高决定**，不再依赖某个人的坐标
  if (outsideIds.length) {
    const baseY = y + 110;
    const keys = outsideIds.map(i => memberKey(i, CH.get(i))).sort(byKey);
    const asg = slotGrid(A, keys);
    const cols = asg.cols;
    outsideIds.forEach(id => {
      const key = memberKey(id, CH.get(id));
      const seq = asg.map.get(key);
      const r = Math.floor(seq / cols), c = seq % cols;
      pos.set(id, { x: c * GX - (cols - 1) * GX / 2, y: baseY + r * GY });
      slotOf.set(key, seq);
    });
    labels.push({ text: `<b>关联</b>团外角色 · ${outsideIds.length} 人`,
                  x: -(cols - 1) * GX / 2 - CW / 2 - 14, y: baseY - 26 });
    maxBottom = Math.max(maxBottom, baseY + (Math.ceil(outsideIds.length / cols) - 1) * GY + CHh / 2);
  }

  // 人工微调覆盖（拖动换位的结果）：**相对自动槽位的偏移**，所以哪怕人数变了、
  // 槽位坐标整体挪了，这张卡的人工位置也仍然跟着它（用绝对坐标就会漂到别人身上）
  const ov = (window.__layoutAdj || {}).pos || {};
  const slots = new Map();                       // id -> 自动槽位坐标（拖拽算偏移要用）
  pos.forEach((p, id) => slots.set(id, { x: p.x, y: p.y }));
  const manualIds = new Set();                   // 有人工偏移的卡（只对它们做消重，自动布局一律不动）
  Object.keys(ov).forEach(id => {
    const p = ov[id];
    if (!pos.has(id) || !p) return;
    const dx = Array.isArray(p) ? p[0] : p.dx, dy = Array.isArray(p) ? p[1] : p.dy;
    if (typeof dx !== 'number' || typeof dy !== 'number') return;
    const base = slots.get(id);
    if (!base) return;
    manualIds.add(id);
    pos.set(id, { x: base.x + dx, y: base.y + dy });
  });

  /* ── 只对「人工挪过」的卡做消重（自动布局一律不动）──
     自动布局由槽位账本保证不重叠（不变量测试 12/12），**绝不能在这里动它**；
     真正需要兜底的是拖动结果：人工偏移可能让卡与别人视觉重叠。
     判据用「视觉距离」而不是格号 —— 块内左对齐会带半格偏移，格号判重会漏判。 */
  if (manualIds.size) {
    const spiral = [[0, 0], [1, 0], [-1, 0], [0, 1], [0, -1],
                    [1, 1], [-1, 1], [1, -1], [-1, -1],
                    [2, 0], [-2, 0], [0, 2], [0, -2], [2, 2], [-2, -2]];
    const placed = [];                           // 固定不动的：全部自动卡
    pos.forEach((p, id) => { if (!manualIds.has(id)) placed.push({ x: p.x, y: p.y, id }); });
    const clashes = (x, y, selfId) => placed.some(q =>
      q.id !== selfId && Math.abs(q.x - x) < GX - 2 && Math.abs(q.y - y) < GY - 2);
    [...manualIds].sort((a, b) => {
      const pa = pos.get(a), pb = pos.get(b);
      return (pa.y - pb.y) || (pa.x - pb.x) || String(a).localeCompare(String(b));
    }).forEach(id => {
      const p = pos.get(id);
      let hit = null;
      for (const [sx, sy] of spiral) {
        const cx2 = p.x + sx * GX, cy2 = p.y + sy * GY;
        if (!clashes(cx2, cy2, id)) { hit = { x: cx2, y: cy2 }; break; }
      }
      const fin = hit || { x: p.x, y: p.y };
      pos.set(id, fin);
      placed.push({ x: fin.x, y: fin.y, id });
    });
  }

  const xs = [...pos.values()].map(p => p.x), ys = [...pos.values()].map(p => p.y);
  return {
    members, outsideIds, groups, pos, slots, centers, labels, slotOf,
    bounds: pos.size
      ? { x0: Math.min(...xs) - CW / 2, y0: Math.min(...ys) - CHh / 2, x1: Math.max(...xs) + CW / 2, y1: Math.max(...ys) + CHh / 2 }
      : { x0: -CW, y0: -CHh, x1: CW, y1: CHh },
  };
}

/* ── 凸包 → 圆滑闭合路径 ─────────────────────────────────── */
function hullPath(pts, pad) {
  if (pts.length < 2) return '';
  const p = pts.slice().sort((a, b) => a.x - b.x || a.y - b.y);
  const cross = (o, a, b) => (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x);
  const lower = [], upper = [];
  for (const q of p) { while (lower.length >= 2 && cross(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (let i = p.length - 1; i >= 0; i--) { const q = p[i]; while (upper.length >= 2 && cross(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  const h = lower.slice(0, -1).concat(upper.slice(0, -1));
  const cx = h.reduce((s, a) => s + a.x, 0) / h.length, cy = h.reduce((s, a) => s + a.y, 0) / h.length;
  const ex = h.map(a => {
    const dx = a.x - cx, dy = a.y - cy, L = Math.hypot(dx, dy) || 1;
    return { x: a.x + dx / L * pad, y: a.y + dy / L * pad };
  });
  // Catmull-Rom → 三次贝塞尔，闭合
  let d = `M${ex[0].x.toFixed(1)},${ex[0].y.toFixed(1)}`;
  const m = ex.length;
  for (let i = 0; i < m; i++) {
    const p0 = ex[(i - 1 + m) % m], p1 = ex[i], p2 = ex[(i + 1) % m], p3 = ex[(i + 2) % m];
    const c1 = { x: p1.x + (p2.x - p0.x) / 6, y: p1.y + (p2.y - p0.y) / 6 };
    const c2 = { x: p2.x - (p3.x - p1.x) / 6, y: p2.y - (p3.y - p1.y) / 6 };
    d += `C${c1.x.toFixed(1)},${c1.y.toFixed(1)} ${c2.x.toFixed(1)},${c2.y.toFixed(1)} ${p2.x.toFixed(1)},${p2.y.toFixed(1)}`;
  }
  return d + 'Z';
}

/* ── 渲染：势力总览（每个势力 = 一张封面六边形）──────────── */
function coverFor(key) {
  const c = (N.covers || {})[S.persp] || {};
  return c[key] || null;
}
function renderOverview() {
  clearAll();
  const ents = entities().filter(e => e.ids.length);
  $('#bgMark').textContent = S.persp === 'creator' ? 'CREATORS' : (S.persp === 'kind' ? 'ARCHETYPES' : 'TRPG UNIVERSE');
  // 窄屏：封面缩小一档；每行个数按屏宽分档（竖屏手机 2 / 平板 3 / 桌面 5），
  // 免得 14 个势力被压进 375px 之后团名糊成一片
  const mb = NARROW;
  const TW = mb ? 196 : 300, TH = mb ? 220 : 336;
  const COLGAP = mb ? 22 : 46, ROWGAP = mb ? 48 : 96;
  const PER = window.innerWidth <= 520 ? 2 : (mb ? 3 : 5);
  ents.forEach((e, i) => {
    const col = i % PER, row = Math.floor(i / PER);
    const x = (col - (PER - 1) / 2) * (TW + COLGAP) - (row % 2 ? (TW + COLGAP) / 2 : 0);
    const y = row * (TH + ROWGAP);
    const cover = coverFor(e.key);
    const t = document.createElement('div');
    t.className = 'tile';
    t.style.left = (x - TW / 2) + 'px';
    t.style.top = (y - TH / 2) + 'px';
    t.style.width = TW + 'px';
    t.style.height = TH + 'px';
    t.style.setProperty('--c', e.color || '#8fa3b8');
    const withAv = e.ids.map(id => CH.get(id)).filter(c => c && c.avatar);
    const inner = cover
      ? `<div class="hexin" style="background-image:url('${cover}')"></div>`
      : (withAv.length
        ? `<div class="hexin noimg">${withAv.slice(0, 4).map(c => `<img src="${c.avatar.thumb}">`).join('')}</div>`
        // 一个立绘都没有（KP <KP>、叶珏那种）→ 大字首字 + 主题色，别留个空壳
        : `<div class="hexin letter" style="--c:${e.color || '#8fa3b8'}">
             <span>${esc((CH.get(e.ids[0]) || {}).name?.slice(0, 1) || '?')}</span></div>`);
    t.innerHTML = `<div class="hexwrap">${inner}<div class="veil"></div></div>
      <div class="hcnt">${e.ids.length}</div>
      <div class="tlabel"><b>${esc(e.name)}</b><i>${esc(enName(e.name))}</i></div>`;
    t.onclick = () => openEntity(e.key);
    elHulls.appendChild(t);
  });
  const rows = Math.ceil(ents.length / PER);
  const mx = mb ? 26 : 120;
  fitBox(-(PER * (TW + COLGAP)) / 2 - mx, -TH / 2 - (mb ? 14 : 40),
         (PER * (TW + COLGAP)) / 2 + mx, (rows - 1) * (TH + ROWGAP) + TH / 2 + (mb ? 44 : 90),
         mb ? 14 : 40, mb ? 0.62 : 0);
  renderCrumb();
}
function hexPts(cx, cy, r) {
  return Array.from({ length: 6 }, (_, i) => {
    const a = Math.PI / 180 * (60 * i - 90);
    return `${(cx + r * Math.cos(a)).toFixed(1)},${(cy + r * 0.92 * Math.sin(a)).toFixed(1)}`;
  }).join(' ');
}

/* ── 渲染：实体内关系网 ───────────────────────────────────── */
let LAST = null;
function renderEntity() {
  clearAll();
  const ent = entities().find(e => e.key === S.ent) || entities()[0];
  if (!ent) return;
  S.ent = ent.key;
  const { members, outsideIds, groups, pos, labels, slotOf, slots, bounds } = layoutEntity(ent);
  /* occupied = 每张卡**实际**落在的格子（拖动找空位要用它判重） */
  const occupied = new Set();
  pos.forEach(p => occupied.add(cellOf(p.x, p.y)));
  LAST = { ent, members, outsideIds, groups, pos, labels, slotOf, slots, occupied };   // ← 键名与解构保持一致
  $('#bgMark').textContent = enName(ent.name) || 'SECTOR';

  const col = ent.color || '#8fa3b8';
  const mkSvg = () => {
    const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    s.setAttribute('width', '1'); s.setAttribute('height', '1');
    s.style.cssText = 'position:absolute;left:0;top:0;overflow:visible';
    return s;
  };
  const boxPts = ids => ids.flatMap(id => {
    const p = pos.get(id); if (!p) return [];
    return [{ x: p.x - CW / 2, y: p.y - CHh / 2 }, { x: p.x + CW / 2, y: p.y - CHh / 2 },
            { x: p.x + CW / 2, y: p.y + CHh / 2 }, { x: p.x - CW / 2, y: p.y + CHh / 2 }];
  });

  // ── 阵营外壳 ──
  const hs = mkSvg();
  groups.forEach((g, gi) => {
    const pts = boxPts(g.ids);
    if (pts.length < 3) return;
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', hullPath(pts, 26));
    const gc = g.color || col;
    path.setAttribute('fill', gc); path.setAttribute('fill-opacity', '.10');
    path.setAttribute('stroke', gc); path.setAttribute('stroke-width', '1.4');
    path.setAttribute('stroke-opacity', '.55');
    if (gi % 2) path.setAttribute('stroke-dasharray', '6 5');
    hs.appendChild(path);
  });
  if (outsideIds.length) {
    const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    p.setAttribute('d', hullPath(boxPts(outsideIds), 28));
    p.setAttribute('fill', '#5d6b7c'); p.setAttribute('fill-opacity', '.07');
    p.setAttribute('stroke', '#5d6b7c'); p.setAttribute('stroke-width', '1.2');
    p.setAttribute('stroke-dasharray', '4 6');
    hs.appendChild(p);
  }
  const hw = document.createElement('div');
  hw.className = 'hull'; hw.style.cssText = 'position:absolute;left:0;top:0';
  hw.appendChild(hs); elHulls.appendChild(hw);

  // ── 阵营名：锚在**块自己的顶边**（不再用「行中心 ± 半高」——
  //    同一行里矮块跟高块共用行中心，旧算法会让矮块的铭牌钻到块内部，就是主人看到的"tag 错位"）
  (labels || []).forEach(L => {
    const lbl = document.createElement('div');
    lbl.className = 'hname';
    lbl.style.left = L.x + 'px';
    lbl.style.top = L.y + 'px';
    lbl.style.transform = 'none';
    lbl.innerHTML = L.text;
    elLabels.appendChild(lbl);
  });

  // ── 连线 ──
  const shown = new Set([...members, ...outsideIds]);
  const outSet = new Set(outsideIds);
  const frag = document.createDocumentFragment();
  N.rels.forEach(r => {
    if (!shown.has(r.a) || !shown.has(r.b)) return;
    const pa = pos.get(r.a), pb = pos.get(r.b); if (!pa || !pb) return;
    const cls = 's' + (3 - (SORD[r.strength] ?? 3));
    const far = Math.abs(pb.x - pa.x) > 420;
    const d = far
      ? `M${pa.x},${pa.y}C${pa.x + (pb.x - pa.x) * .3},${pa.y - 60} ${pa.x + (pb.x - pa.x) * .7},${pb.y - 60} ${pb.x},${pb.y}`
      : `M${pa.x},${pa.y}L${pb.x},${pb.y}`;
    const out = outSet.has(r.a) || outSet.has(r.b);
    [['halo', 0], ['core', 1]].forEach(([k]) => {
      const p = document.createElementNS('http://www.w3.org/2000/svg', 'path');
      p.setAttribute('d', d); p.setAttribute('class', `lk ${k} ${cls}` + (out ? ' out' : ''));
      p.dataset.a = r.a; p.dataset.b = r.b;
      frag.appendChild(p);
    });
  });
  const ws = mkSvg(); ws.appendChild(frag); elHulls.appendChild(ws);

  // ── 卡片 ──（渲染顺序只影响出场动画；**坐标全部来自槽位**，与排序无关）
  [...shown].sort((a, b) =>
    (stableHash(memberKey(a, CH.get(a))) >>> 0) - (stableHash(memberKey(b, CH.get(b))) >>> 0) ||
    (CH.get(a).name || '').localeCompare(CH.get(b).name || '') || a.localeCompare(b)).forEach((id, i) => {
    const c = CH.get(id), p = pos.get(id);
    const el = document.createElement('div');
    el.className = 'card d1';
    el.style.left = (p.x - CW / 2) + 'px'; el.style.top = (p.y - CHh / 2) + 'px';
    el.style.animation = `cardIn .45s ${Math.min(i * 18, 800)}ms backwards cubic-bezier(.2,.8,.3,1)`;
    const kc = KIND_COLOR[c.kind] || '#93a4b6';
    const img = c.avatar
      ? `<img class="ph" src="${c.avatar.thumb}" loading="lazy" alt="">`
      : `<div class="noportrait"><span>${esc(c.name.slice(0, 1))}</span></div>`;
    const seal = c.avatar ? '' : '<div class="seal">未解封</div>';
    el.innerHTML = `<div class="frame">${img}<div class="bar" style="background:${kc}"></div>
        <div class="tag">${esc(c.id.toUpperCase().slice(0, 9))}</div>${seal}
        <div class="plate"><div class="nm">${esc(c.name)}</div>
        <div class="sub">${esc(c.played_by || c.identity || '').slice(0, 14)}</div></div></div>
      <div class="detail">人物详情 ›</div>`;
    el.dataset.id = id;
    el.dataset.key = memberKey(id, CH.get(id));
    el.title = '拖动可换位置（双击复位这张卡）';
    el.onclick = ev => { ev.stopPropagation(); if (DRAG.moved) { DRAG.moved = 0; return; } onCard(id); };
    el.ondblclick = ev => { ev.stopPropagation(); resetCardPos(id); };
    el.querySelector('.detail').onclick = ev => { ev.stopPropagation(); openDossier(id); };
    bindCardDrag(el, id);
    elCards.appendChild(el);
  });

  // 顶部多留 120px：阵营铭牌挂在每块上方（手机改小一档）
  fitBox(bounds.x0, bounds.y0 - (NARROW ? 40 : 60), bounds.x1, bounds.y1,
         NARROW ? 18 : 90, NARROW ? 0.8 : 0);
  renderCrumb();
  showHint(`${ent.name}：${members.length} 人 · ${groups.length} 个阵营（按 tags）· 点卡片聚焦`);
}

/* ── 聚焦 ─────────────────────────────────────────────────── */
function onCard(id) {
  if (S.focus === id) { openDossier(id); return; }
  S.focus = id;
  applyFocus();
  const p = LAST.pos.get(id);
  const k = Math.max(1.0, Math.min(1.5, 1.15));
  S.cam = { k, x: stage.clientWidth / 2 - p.x * k, y: stage.clientHeight / 2 - p.y * k };
  setCam(true);
  const nb = (ADJ.get(id) || []).filter(x => LAST.pos.has(x.o)).length;
  showHint(`已聚焦「${CH.get(id).name}」（${nb} 个关系人）· 再点一次卡片看完整档案 · ESC 取消`);
}
function applyFocus() {
  const f = S.focus;
  const near = new Set();
  if (f) { ADJ.get(f).forEach(x => near.add(x.o)); near.add(f); }
  elCards.querySelectorAll('.card').forEach(el => {
    const id = el.dataset.id;
    el.classList.toggle('focus', !!f && id === f);
    el.classList.toggle('dim', !!f && !near.has(id));
  });
  elHulls.querySelectorAll('.hull').forEach(h => h.classList.toggle('dim', !!f));
  elLabels.querySelectorAll('.hname').forEach(l => l.style.opacity = f ? .25 : 1);
  svg.querySelectorAll('.lk').forEach(p => {
    const hit = !f || ((p.dataset.a === f || p.dataset.b === f) && near.has(p.dataset.a) && near.has(p.dataset.b));
    p.classList.toggle('dim', !!f && !hit);
    p.classList.toggle('hot', !!f && hit);
  });
}

/* ── 档案 ─────────────────────────────────────────────────── */
function openDossier(id) {
  const c = CH.get(id);
  $('#dosArt').style.backgroundImage = c.avatar ? `url(${c.avatar.full})` : 'none';
  $('#dosArt').style.background = c.avatar ? '' : 'repeating-linear-gradient(45deg,#141c25 0 12px,#18222c 12px 24px)';
  if (c.avatar) $('#dosArt').style.backgroundImage = `url(${c.avatar.full})`;
  $('#dosId').textContent = c.id.toUpperCase();
  $('#dosCn').textContent = c.name;
  $('#dosEn').textContent = enName(c.name) || '';
  $('#dosBadge').textContent = c.kind + (c.is_core ? ' · 主展团' : ' · 关联角色');
  $('#dosTitle').textContent = c.identity || c.name;
  $('#dosSub').textContent = (c.groups || []).join('　/　');
  const kv = [['代号', c.name], ['角色类型', c.kind],
    ['扮演 / 创作', c.played_by || '（未记录）'],
    ['出场团', (c.groups || []).join('、') || '—'],
    ['关系数', c.degree + ' 人'],
    ['标签', (c.tags || []).join('、') || '—']];
  $('#dosKv').innerHTML = kv.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join('');
  $('#dosNote').textContent = c.note || '（暂无简介）';
  const list = (ADJ.get(id) || []).map(x => ({ ...x, c: CH.get(x.o) })).filter(x => x.c)
    .sort((a, b) => (SORD[a.r.strength] ?? 3) - (SORD[b.r.strength] ?? 3) || degree(b.o) - degree(a.o));
  $('#dosRelN').textContent = list.length;
  $('#dosRels').innerHTML = list.map(({ o, r, out, c: oc }) => {
    const cls = 's' + (3 - (SORD[r.strength] ?? 3));
    return `<div class="dos-rel">
      ${out ? `<div class="other" data-go="${o}">${esc(c.name)}</div>` : `<div class="other r" data-go="${o}">${esc(oc.name)}</div>`}
      <div class="md">${out ? '──' : '←'} <span class="ty ${cls}">${esc(r.type)}</span> ${out ? '→' : '──'}</div>
      ${out ? `<div class="other r" data-go="${o}">${esc(oc.name)}</div>` : `<div class="other" data-go="${o}">${esc(c.name)}</div>`}
      <div class="why">${esc(r.event || '')}</div></div>`;
  }).join('') || '<div style="color:#5d6b7c">（选角范围内没有关系）</div>';
  $('#dosEvents').innerHTML = (c.events || []).map(g =>
    `<div class="ev-g"><b>${esc(g.group)}</b><ul>${(g.items || []).map(i => `<li>${esc(i)}</li>`).join('')}</ul></div>`
  ).join('') || '<div style="color:#5d6b7c">（暂无事件记录）</div>';
  $('#dosFoot').textContent = `档案 ID ${c.id}　·　由 trpg-agent 生成　·　${N.generated}`;
  $('#dossier').classList.add('on');
  $('#dosRels').querySelectorAll('[data-go]').forEach(el => el.onclick = () => {
    const t = el.dataset.go;
    closeDossier(); S.focus = null;
    if (!LAST.pos.has(t)) { const e = entities().find(x => x.ids.includes(t)); if (e) { S.ent = e.key; renderEntity(); } }
    onCard(t);
  });
}
function closeDossier() { $('#dossier').classList.remove('on'); }

/* ── 导航 ─────────────────────────────────────────────────── */
function goOverview() { S.view = 'overview'; S.ent = null; S.focus = null; applyFocus(); renderOverview(); }
function openEntity(key) { S.view = 'entity'; S.ent = key; S.focus = null; renderEntity(); }
function back() {
  if ($('#dossier').classList.contains('on')) return closeDossier();
  if (S.view === 'entity') return goOverview();
}
function renderCrumb() {
  const parts = [`<a data-nav="home">总览</a>`];
  if (S.view === 'entity') {
    parts.push(`<span class="sep">›</span><b>${esc(S.ent)}</b>`);
    if (S.focus) parts.push(`<span class="sep">›</span><a data-nav="focusclear">${esc(CH.get(S.focus).name)}</a>`);
  }
  $('#crumb').innerHTML = parts.join('');
  $('#crumb').querySelectorAll('[data-nav]').forEach(a => a.onclick = () => {
    const n = a.dataset.nav;
    if (n === 'home') goOverview();
    else if (n === 'focusclear') { S.focus = null; applyFocus(); renderCrumb(); }
  });
  $('#btnBack').style.opacity = S.view === 'entity' ? 1 : .35;
}
function clearAll() {
  if (window.__layoutDbg) console.log('[dbg] clearAll @' + Math.round(performance.now()) + '\n' + (new Error().stack || ''));
  elCards.innerHTML = ''; elHulls.innerHTML = ''; elLabels.innerHTML = ''; svg.innerHTML = '';
}

/* ── 杂项 ─────────────────────────────────────────────────── */
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
/* 团名的英文副标题映射（可选）。留空则直接用团名本身。
   想给某团配英文名，在 tools/_netsite/site_config.json 里加 "group_en": {"团名": "ENGLISH"}，
   构建时会注入到 window.__SITE_CFG__；这里只做兜底。 */
const EN = (typeof window !== 'undefined' && window.__SITE_CFG__ && window.__SITE_CFG__.group_en) || {};
function enName(s) {
  if (EN[s]) return EN[s];
  if (s === 'PC') return 'PLAYER CHARACTERS';
  if (s === 'NPC') return 'NON-PLAYER';
  if (s === 'BOSS') return 'ANTAGONISTS';
  if (s === '跨团') return 'CROSS-CAMPAIGN';
  if (s === 'KP') return 'GAME MASTERS';
  if (s === '(未记录)') return 'UNRECORDED';
  return '';
}
let hintT = null;
function showHint(t) {
  const h = $('#hint'); h.textContent = t; h.classList.add('on');
  clearTimeout(hintT); hintT = setTimeout(() => h.classList.remove('on'), 4200);
}

/* ── 事件绑定 ─────────────────────────────────────────────── */
$('#btnBack').onclick = back;
$('#btnZoomIn').onclick = () => zoomAt(stage.clientWidth / 2, stage.clientHeight / 2, 1.22);
$('#btnZoomOut').onclick = () => zoomAt(stage.clientWidth / 2, stage.clientHeight / 2, .82);
$('#btnFit').onclick = () => { S.focus = null; applyFocus(); S.view === 'overview' ? renderOverview() : renderEntity(); };
$('#btnHelp').onclick = () => $('#helpsheet').classList.add('on');
$('#hsOk').onclick = () => $('#helpsheet').classList.remove('on');
/* 拖动撤销 / 复位（2026-10-06） */
if ($('#btnReset')) $('#btnReset').onclick = resetLayoutAll;
if ($('#btnUndo')) $('#btnUndo').onclick = undoDrag;
syncUndoBtn();
$('#dosClose').onclick = closeDossier;
$('#persp').onclick = e => {
  const b = e.target.closest('button[data-p]'); if (!b) return;
  S.persp = b.dataset.p;
  $('#persp').querySelectorAll('button').forEach(x => x.classList.toggle('on', x === b));
  S.focus = null; S.view = 'overview'; S.ent = null; renderOverview();
};
document.addEventListener('keydown', e => {
  /* 撤销拖动：Ctrl+Z（输入框里不劫持，免得跟文本框的撤销打架） */
  const tag = (e.target && e.target.tagName) || '';
  const typing = tag === 'INPUT' || tag === 'TEXTAREA' || (e.target && e.target.isContentEditable);
  if ((e.ctrlKey || e.metaKey) && !e.shiftKey && String(e.key).toLowerCase() === 'z' && !typing) {
    if (UNDO.length) { e.preventDefault(); undoDrag(); }
    return;
  }
  if (e.key === 'Escape') { if ($('#helpsheet').classList.contains('on')) $('#helpsheet').classList.remove('on'); else back(); }
  if (e.key === '0') $('#btnFit').onclick();
});
window.addEventListener('resize', () => { S.view === 'overview' ? renderOverview() : renderEntity(); });
/* 拖拽时给个跟随手感（位置在 JS 里算，样式只管观感） */
const ds = document.createElement('style');
ds.textContent = '.card.dragging{transition:none;cursor:grabbing;filter:brightness(1.12)}'
  + '.card{cursor:grab}';
document.head.appendChild(ds);

/* ── 启动：加载动画 → 主界面 → 档案库 ─────────────────────── */
const style = document.createElement('style');
style.textContent = `@keyframes cardIn{from{opacity:0;transform:translateY(14px) scale(.94)}to{opacity:1;transform:none}}`;
document.head.appendChild(style);

const BOOT_STEPS = [
  ['初始化档案库…', 10],
  [`读取角色 ${N.chars.length} 名…`, 32],
  [`索引关系 ${N.rels.length} 条…`, 58],
  [`装载封面 ${Object.keys((N.covers || {}).group || {}).length} 张与立绘…`, 80],
  ['构建人物关系网…', 100],
];

function boot() {
  loadAdj();                                          // 先装载布局账本（服务器注入 or localStorage）
  const bar = $('#bootBar'), log = $('#bootLog'), root = $('#boot');
  if (!root || !bar || !log) { showHome(); return; }   // 没有启动页也要能跑（排障用）
  // 启动徽记：取「关系最多且带立绘」的角色头像（找不到就退回深色底）
  const hero = N.chars.filter(c => c.avatar)
    .sort((a, b) => (N.rels.filter(r => r.a === b.id || r.b === b.id).length)
                  - (N.rels.filter(r => r.a === a.id || r.b === a.id).length))[0];
  const bm = $('#bmIn');
  if (bm && hero && hero.avatar) bm.style.backgroundImage = `url('${hero.avatar.full}')`;
  let i = 0;
  const tick = () => {
    if (i >= BOOT_STEPS.length) {
      setTimeout(() => {
        root.classList.add('out');
        setTimeout(() => { root.style.display = 'none'; }, 760);
        showHome();
      }, 280);
      return;
    }
    const [t, p] = BOOT_STEPS[i++];
    log.textContent = t;
    bar.style.width = p + '%';
    setTimeout(tick, 360 + Math.random() * 220);
  };
  tick();
}

function showHome() {
  const creators = new Set(N.chars.map(c => c.played_by).filter(Boolean)).size;
  const st = $('#homeStats');
  if (st) {
    st.innerHTML = [
      [N.chars.length, '角色'], [N.rels.length, '关系'],
      [N.groups.length, '团'], [creators, '创作者'],
    ].map(([v, k]) => `<div><b>${v}</b><span>${k}</span></div>`).join('');
  }
  if ($('#homeGen')) $('#homeGen').textContent = N.generated;
  /* ⚠️ 只在**总览**视图渲染总览：深链（#/c、#/g、#/tags…）进来时 wiki 层早已把
     卡片网画好，而启动动画跑完还要 5 秒才轮到 showHome —— 那时无条件 renderOverview()
     会把刚画好的卡片**全部清掉**（而首页被 deepLink 拦着没显示）→ 整页空白。
     顺带也省掉了一次无谓的重排（N 张卡的 DOM 重建并不便宜）。 */
  if (S.view === 'overview') renderOverview();
  // ⚠️ 深链（#/c/xxx、#/g/xxx、#/review、#/tags）进来时**不要**把首页盖上来：
  //    boot 动画要跑 5 秒才调 showHome，而 wiki 层早在它之前就把路由应用完了，
  //    这里再 add('on') 会把刚打开的角色档案整页盖住 —— 表现就是
  //    「别人点开分享链接，看到的还是『进入档案库』首页」（2026-10-06 踩过）。
  const deepLink = /^#\/(c|g|review|tags|s|portal|edit)(\/|$)/.test(location.hash || '');
  if ($('#home') && !deepLink) $('#home').classList.add('on');   // 没有主界面就不挡着
}

function enterArchive() {
  if ($('#home')) $('#home').classList.remove('on');
  S.view = 'overview'; S.ent = null; S.focus = null;
  renderOverview();
  if ($('#helpsheet') && !localStorage.getItem('trpg-net-help')) {
    $('#helpsheet').classList.add('on');
    localStorage.setItem('trpg-net-help', '1');
  }
}

if ($('#homeEnter')) $('#homeEnter').onclick = enterArchive;
/* 门户 / 新增条目入口（顶栏 + 首页）—— 走 hash 让 wiki 层的路由统一处理 */
if ($('#btnPortal')) $('#btnPortal').onclick = () => { location.hash = '#/portal'; };
if ($('#homePortal')) $('#homePortal').onclick = (e) => { e.stopPropagation(); location.hash = '#/portal'; };
if ($('#btnAdd')) $('#btnAdd').onclick = () => { location.hash = '#/portal/new'; };
if ($('#homeAdd')) $('#homeAdd').onclick = (e) => { e.stopPropagation(); location.hash = '#/portal/new'; };
document.querySelectorAll('.mode').forEach(b => {
  b.onclick = () => {
    document.querySelectorAll('.mode').forEach(x => x.classList.toggle('on', x === b));
    S.persp = b.dataset.p;
    $('#persp').querySelectorAll('button').forEach(x => x.classList.toggle('on', x.dataset.p === S.persp));
    renderOverview();
  };
  b.ondblclick = enterArchive;
});
if ($('.brand')) { $('.brand').onclick = showHome; $('.brand').style.cursor = 'pointer'; }

/* ── 给 wiki 层（wiki.js）留的出口 ──────────────────────────────
   ⚠️ `const CH / S / ADJ` **不会**自动挂到 window 上（const 只进全局词法环境），
      所以 wiki.js 里写 `window.CH` 会拿到 undefined —— 2026-10-06 加 wiki 层时踩过：
      表现为「#/c/<id> 直达打不开档案」，因为路由拿不到角色表。
      function 声明（goOverview/openEntity/openDossier…）本来就挂 window，不用导出。 */
window.APP = { CH, S, ADJ, N, CW, CHh, refreshGraph, loadAdj, layoutOf, entities,
               resetLayoutAll, resetCardPos, undoDrag };

boot();
