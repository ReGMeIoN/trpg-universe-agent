/**
 * 跑团宇宙 · 提案箱 API（Cloudflare Worker）
 * ============================================================
 * 静态资源仍由同一個 Worker 的 Assets 提供（`wrangler.jsonc` 的 `assets.directory=./site`），
 * 只有 `/api/*` 会先打到这个脚本（`assets.run_worker_first`）。
 *
 * 端点：
 *   GET  /api/stats                   公开 · 待审/已采纳计数
 *   GET  /api/overrides               公开 · 已采纳的改动（前端当覆盖层套在 data.js 上）
 *   GET  /api/suggestions?status=…    仅管理员可看 pending/rejected；approved 公开
 *   POST /api/suggest                 公开 · 提交建议（匿名）
 *   POST /api/review                  仅管理员 · 通过 / 驳回
 *
 * 安全与防滥用：
 *   · 字段白名单裁剪（只收认识的字段，长度全部截断）
 *   · 同 IP 10 分钟最多 8 条（只存 IP 的 SHA-256，不存明文）
 *   · 请求体上限 16KB
 *   · 管理员用 secret `ADMIN_TOKEN`（请求头 `x-admin-token`），比较为常数时间
 *   · 所有返回 JSON、`no-store`；内容只当**数据**存与回，永远不执行
 */

const KINDS = new Set([
  'char_update', 'char_create', 'char_delete',
  'rel_update', 'rel_create', 'rel_delete',
]);
const MAX_BODY = 16 * 1024;
const MAX_TEXT = 4000;
const RATE_WINDOW_MS = 10 * 60 * 1000;
const RATE_MAX = 8;
const ALLOW_ORIGIN = '*';

const json = (obj, status = 200) => new Response(JSON.stringify(obj), {
  status,
  headers: {
    'content-type': 'application/json; charset=utf-8',
    'cache-control': 'no-store',
    'access-control-allow-origin': ALLOW_ORIGIN,
    'access-control-allow-headers': 'content-type,x-admin-token',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
  },
});

async function sha256hex(s) {
  const buf = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(s));
  return [...new Uint8Array(buf)].map(b => b.toString(16).padStart(2, '0')).join('');
}

/** 常数时间比较，避免逐字符短路泄漏口令 */
function safeEqual(a, b) {
  const x = String(a || ''), y = String(b || '');
  if (x.length !== y.length) return false;
  let d = 0;
  for (let i = 0; i < x.length; i++) d |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return d === 0;
}
const isAdmin = (req, env) =>
  !!env.ADMIN_TOKEN && safeEqual(req.headers.get('x-admin-token'), env.ADMIN_TOKEN);

const str = (v, max = 200) => (typeof v === 'string' ? v.trim().slice(0, max) : '');
const strArr = (v, n = 20, max = 80) =>
  Array.isArray(v) ? v.filter(x => typeof x === 'string' && x.trim()).slice(0, n).map(x => x.trim().slice(0, max)) : undefined;

/** attrs：结构化属性标签 `{维度: 值}`；值可为字符串或字符串数组，值为 `null` 表示**删除该维度**。 */
function cleanAttrs(raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return undefined;
  const out = {};
  let n = 0;
  for (const k of Object.keys(raw)) {
    if (n >= 40) break;                                    // 维度数量上限
    const key = String(k).trim().slice(0, 30);
    if (!key) continue;
    const v = raw[k];
    if (v === null) { out[key] = null; n++; continue; }     // 显式删除该维度
    if (typeof v === 'string') {
      const s = v.trim().slice(0, 120);
      if (s) { out[key] = s; n++; }
    } else if (Array.isArray(v)) {
      const arr = v.filter(x => typeof x === 'string' && x.trim())
        .slice(0, 12).map(x => x.trim().slice(0, 120));
      if (arr.length) { out[key] = arr; n++; }
    }
  }
  return Object.keys(out).length ? out : undefined;
}

/** 按 kind 做字段白名单裁剪 —— 不认识的字段一律丢弃 */
function cleanPayload(kind, raw) {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const out = {};
  const put = (k, v) => { if (v !== undefined && v !== '') out[k] = v; };

  if (kind.startsWith('char_')) {
    put('id', str(raw.id, 64));
    put('name', str(raw.name, 80));
    put('identity', str(raw.identity, 400));
    put('note', str(raw.note, MAX_TEXT));
    put('profile', str(raw.profile, 12000));      // wiki 正文，比 note 宽
    put('played_by', str(raw.played_by, 80));
    const al = strArr(raw.aliases), gr = strArr(raw.groups), tg = strArr(raw.tags, 10, 40);
    if (al) put('aliases', al);
    if (gr) put('groups', gr);
    if (tg) put('tags', tg);
    const at = cleanAttrs(raw.attrs);
    if (at) put('attrs', at);
  } else {
    put('from', str(raw.from, 64));
    put('to', str(raw.to, 64));
    put('type', str(raw.type, 60));
    put('strength', str(raw.strength, 10));
    put('event', str(raw.event, MAX_TEXT));
    put('raw', str(raw.raw, 120));
  }
  if (kind === 'char_delete' || kind === 'rel_delete') return out;   // 删除只要目标
  return Object.keys(out).length ? out : null;
}

async function readBody(request) {
  const len = parseInt(request.headers.get('content-length') || '0', 10);
  if (len > MAX_BODY) return { err: '请求体过大（上限 16KB）' };
  let text;
  try { text = await request.text(); } catch { return { err: '读取请求体失败' }; }
  if (text.length > MAX_BODY) return { err: '请求体过大（上限 16KB）' };
  try { return { body: JSON.parse(text) }; } catch { return { err: 'JSON 解析失败' }; }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (request.method === 'OPTIONS') return json({ ok: true });
    if (!url.pathname.startsWith('/api/')) return env.ASSETS.fetch(request);
    try {
      return await handleApi(request, env, url);
    } catch (e) {
      return json({ ok: false, error: '服务器内部错误: ' + (e && e.message ? e.message : e) }, 500);
    }
  },
};

async function handleApi(request, env, url) {
  const DB = env.DB;
  const path = url.pathname;
  const method = request.method;
  if (!DB) return json({ ok: false, error: 'D1 未绑定' }, 500);

  /* ── 公开：计数 ─────────────────────────────────────────── */
  if (path === '/api/stats' && method === 'GET') {
    const r = await DB.prepare(
      `SELECT status, COUNT(*) AS n FROM suggestions GROUP BY status`).all();
    const m = { pending: 0, approved: 0, rejected: 0 };
    (r.results || []).forEach(x => { m[x.status] = x.n; });
    return json({ ok: true, ...m });
  }

  /* ── 公开：已采纳的覆盖层（前端套在 data.js 上，立刻可见）── */
  if (path === '/api/overrides' && method === 'GET') {
    const r = await DB.prepare(
      `SELECT id, kind, target_id, payload, author, created_at
         FROM suggestions WHERE status='approved' ORDER BY reviewed_at ASC, id ASC`).all();
    const items = (r.results || []).map(x => ({
      id: x.id, kind: x.kind, target_id: x.target_id,
      payload: safeParse(x.payload), author: x.author, at: x.created_at,
    }));
    return json({ ok: true, count: items.length, items });
  }

  /* ── 列表：approved 公开，pending/rejected 仅管理员 ──────── */
  if (path === '/api/suggestions' && method === 'GET') {
    const status = url.searchParams.get('status') || 'approved';
    if (!['pending', 'approved', 'rejected'].includes(status)) {
      return json({ ok: false, error: 'status 非法' }, 400);
    }
    if (status !== 'approved' && !isAdmin(request, env)) {
      return json({ ok: false, error: '需要管理员口令' }, 401);
    }
    const limit = Math.min(200, Math.max(1, parseInt(url.searchParams.get('limit') || '100', 10) || 100));
    const r = await DB.prepare(
      `SELECT * FROM suggestions WHERE status=? ORDER BY created_at DESC, id DESC LIMIT ?`)
      .bind(status, limit).all();
    return json({
      ok: true, status, count: (r.results || []).length,
      items: (r.results || []).map(x => ({ ...x, payload: safeParse(x.payload), ip_hash: undefined })),
    });
  }

  /* ── 公开：提交建议 ─────────────────────────────────────── */
  if (path === '/api/suggest' && method === 'POST') {
    const { body, err } = await readBody(request);
    if (err) return json({ ok: false, error: err }, 400);

    const kind = str(body.kind, 20);
    if (!KINDS.has(kind)) return json({ ok: false, error: 'kind 非法' }, 400);

    const payload = cleanPayload(kind, body.payload);
    if (!payload) return json({ ok: false, error: '没有可用的字段内容' }, 400);

    const isDel = kind.endsWith('_delete');
    const target = str(body.target_id || payload.id || payload.from, 64) || null;
    if (!isDel && kind === 'char_update' && !target) {
      return json({ ok: false, error: 'char_update 必须带 target_id' }, 400);
    }
    if (kind.startsWith('rel_') && (!payload.from || !payload.to)) {
      return json({ ok: false, error: '关系类建议必须带 from / to' }, 400);
    }

    // 限流：同一 IP 10 分钟内最多 RATE_MAX 条
    const ip = request.headers.get('cf-connecting-ip') || request.headers.get('x-forwarded-for') || '';
    const ipHash = await sha256hex('wiki|' + ip);
    const since = new Date(Date.now() - RATE_WINDOW_MS).toISOString();
    const cnt = await DB.prepare(
      `SELECT COUNT(*) AS n FROM suggestions WHERE ip_hash=? AND created_at>?`)
      .bind(ipHash, since).first();
    if ((cnt && cnt.n) >= RATE_MAX) {
      return json({ ok: false, error: `提交太频繁（10 分钟内最多 ${RATE_MAX} 条），歇一会儿再来` }, 429);
    }

    const now = new Date().toISOString();
    const info = await DB.prepare(
      `INSERT INTO suggestions (kind, target_id, payload, reason, author, status, created_at, ip_hash)
       VALUES (?,?,?,?,?, 'pending', ?, ?)`)
      .bind(kind, target, JSON.stringify(payload), str(body.reason, 600), str(body.author, 40), now, ipHash)
      .run();
    return json({ ok: true, id: info.meta && info.meta.last_row_id, status: 'pending' });
  }

  /* ── 仅管理员：审核 ────────────────────────────────────── */
  if (path === '/api/review' && method === 'POST') {
    if (!isAdmin(request, env)) return json({ ok: false, error: '需要管理员口令' }, 401);
    const { body, err } = await readBody(request);
    if (err) return json({ ok: false, error: err }, 400);
    const id = parseInt(body.id, 10);
    const action = str(body.action, 12);
    if (!id || !['approve', 'reject', 'reopen'].includes(action)) {
      return json({ ok: false, error: 'id / action 非法' }, 400);
    }
    const status = action === 'approve' ? 'approved' : (action === 'reject' ? 'rejected' : 'pending');
    const now = new Date().toISOString();
    const r = await DB.prepare(
      `UPDATE suggestions SET status=?, reviewed_at=?, review_note=? WHERE id=?`)
      .bind(status, action === 'reopen' ? null : now, str(body.note, 300), id).run();
    if (!r.meta || r.meta.changes === 0) return json({ ok: false, error: '找不到该条建议' }, 404);
    return json({ ok: true, id, status });
  }

  return json({ ok: false, error: '未知端点' }, 404);
}

function safeParse(s) {
  try { return JSON.parse(s); } catch { return {}; }
}
