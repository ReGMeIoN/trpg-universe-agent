// 与后端 FastAPI 的通信层。所有路径都相对 /api, 开发模式由 Vite 代理。
const j = async (r) => {
  if (!r.ok) {
    let detail = r.statusText
    try { detail = (await r.json()).detail || detail } catch (e) { /* ignore */ }
    throw new Error(`${r.status} ${detail}`)
  }
  return r.json()
}

export const api = {
  workspace: () => fetch('/api/workspace').then(j),
  status: () => fetch('/api/status').then(j),
  groups: () => fetch('/api/groups').then(j),
  jobs: () => fetch('/api/jobs').then(j),
  jobLog: (id, tail = 200) => fetch(`/api/jobs/${id}/log?tail=${tail}`).then(j),
  jobKill: (id) => fetch(`/api/jobs/${id}/kill`, { method: 'POST' }).then(j),
  startJob: (body) => fetch('/api/jobs', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }).then(j),
  review: (group) => fetch(`/api/review/${encodeURIComponent(group)}`).then(j),
  saveDecisions: (group, decisions) => fetch(`/api/review/${encodeURIComponent(group)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ decisions }),
  }).then(j),
  applyDecisions: (group) => fetch(`/api/review/${encodeURIComponent(group)}/apply`, { method: 'POST' }).then(j),
  report: (group, kind) => fetch(`/api/reports/${encodeURIComponent(group)}?kind=${kind}`).then(j),
  patch: (group) => fetch(`/api/patches/${encodeURIComponent(group)}`).then(j),
  segments: (group) => fetch(`/api/segments/${encodeURIComponent(group)}`).then(j),
  extractMd: (group, n) => fetch(`/api/extract/${encodeURIComponent(group)}/${n}`).then(j),
  products: () => fetch('/api/products').then(j),
  markdownProduct: (path) => fetch(`/api/product?path=${encodeURIComponent(path)}`).then(j),
}

export const productUrl = (path) => `/api/product?path=${encodeURIComponent(path)}`
