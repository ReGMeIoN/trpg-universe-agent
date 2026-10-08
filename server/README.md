# 自托管部署 · 跑团宇宙 wiki

把这套站点从 Cloudflare 搬到你自己的服务器。**三个组件，一个进程就能跑**：

```
服务器
├─ server/app.py      ← 提案箱 API + **自由编辑 API**（FastAPI + SQLite）
├─ site/              ← 前端（**一行都不用改**，API 走同源 /api/*）
├─ server/data/*.json ← **权威数据**（人可读、可 git、可手工改）
└─ server/wiki.db     ← SQLite：只存**版本历史**（每次保存一份快照，可回滚）
```

---

## 一、自由编辑（`#/edit`）—— 这一版的重点

和「提案箱」的根本区别：**写进去就是真的，没有审核关**（主人：都是一起玩认识的人）。

| 能做 | 说明 |
|---|---|
| **改角色所有字段** | 名字 / 别名 / 出场团 / 系统标签 / 扮演者 / 身份 / 简介 / **详细设定(Markdown)** / **属性标签** / 立绘 |
| **改关系** | 新增、改类型·强度·出处、删除（连「改类型」都能定得住） |
| **新建** | 角色（`＋ 新建角色`）、团（在「出场团」里直接写新名字）、tag 维度（在属性里直接写新维度） |
| **Markdown 实时预览** | 左写右看；支持 `## 分节`、`**粗体**`、`==关键词==`、`> 台词`、`- 列表` |
| **版本历史 / 回滚** | 谁在什么时候改了什么，任何一版一键回滚（回滚本身也记一条历史） |
| **立绘上传** | base64 直传（**不依赖 python-multipart**），落进 `site/assets/portraits/` |

**入口**：站点帮助面板 →「✎ 编辑器」，或直接访问 `#/edit`。
**口令**：`.env` 里的 `EDIT_TOKEN`（一个共享口令，防的是「链接被外人扫到」，不防朋友）。
**安全三件套**：① 共享口令　② **每次改动都进版本历史**　③ 删角色 / 删关系前**自动备份数据文件**。

> ⚠️ **编辑器要连后端才有用**：纯静态部署（只挂 `site/`）时打开编辑器会提示「没连上服务器」，
> 站点本身照常浏览 —— 因为 `wiki-boot.js` 对 `/api/data` 失败会静默退回静态 `data.js`。

**数据流**

```
编辑者保存 ──► POST /api/edit/*  ──► 原子写 data/*.json（先写临时文件再 rename）
                                  └─► gzip 快照进 wiki.db（可回滚）
站点打开   ──► GET /api/data      ──► 全量数据（拿不到就退回静态 data.js）
```

**端点速查**

| 端点 | 权限 | 用途 |
|---|---|---|
| `GET /api/data` · `GET /api/meta` | 公开 | 全量数据 / 编辑器元信息（维度·团·类型） |
| `POST /api/edit/char` | 口令 | 新建或更新角色（含 attrs / profile） |
| `DELETE /api/edit/char/{id}?editor=昵称` | 口令 | 删角色（连带关系；**先自动备份**） |
| `POST /api/edit/rel` · `/api/edit/rel/delete` | 口令 | 关系增改 / 删除 |
| `GET /api/history` · `GET /api/history/{rev}` | 公开 | 版本历史 / 某版快照 |
| `POST /api/rollback` | 口令 | 回滚到某一版 |
| `POST /api/upload/portrait` | 口令 | 立绘上传（base64 JSON） |
| `POST /api/edit/login` · `GET /api/edit/ping` | — | 口令校验 / 状态探测 |

---

## 二、Debian 12 一键部署

```bash
# 1) 把项目传上去（排除虚拟环境与临时文件）
rsync -av --exclude .venv --exclude .tmp --exclude novelai/archive ./ user@server:/opt/trpg-universe/

# 2) 服务器上跑部署脚本（装依赖 + 建 systemd 服务 + 生成口令 + 建每日备份 cron）
sudo bash /opt/trpg-universe/server/deploy-debian.sh /opt/trpg-universe
```

脚本**不会**动你的 nginx/caddy —— 跑完会把该粘的配置直接打印出来（两种都给）。
它只装 **fastapi + uvicorn** 两个依赖（**不需要 Node、不需要数据库服务**）。

**迁移现有数据**：

```powershell
# 本机：直接从生产库拷（最快、最全）
Copy-Item "<工作区>\数据\characters.json" "server\data\characters.json" -Force
Copy-Item "<工作区>\数据\relations.json"  "server\data\relations.json"  -Force
# 或者：从 Cloudflare D1 导提案箱数据成本地 sqlite
.\.venv\Scripts\python.exe tools\_export_d1.py --out server\wiki.db
```

---

## 二之二、已部署实例（2026-10-06）

| 项 | 值 |
|---|---|
| **访问地址** | **<http://<服务器IP>:8080/>** ← ⚠️ 走 **8080**，不是 80 |
| 系统 | Debian 12.1 · 2 核 / 2GB 内存 / 30GB 磁盘 |
| 应用目录 | `/opt/trpg-universe` |
| 服务 | `systemctl status trpg-universe`（uvicorn 绑 `127.0.0.1:8788`，实测内存 **34MB**） |
| 反向代理 | nginx（同时监听 `0.0.0.0:80` **和** `:8080`） |
| 数据 | `/opt/trpg-universe/server/data/*.json`（角色 / 关系） |
| 版本历史 | `/opt/trpg-universe/server/wiki.db` |
| **编辑口令** | 服务器 `/opt/trpg-universe/.env` 里的 `EDIT_TOKEN`（部署脚本生成时打印过一次） |
| 每日备份 | `/etc/cron.daily/trpg-universe-backup` → `/opt/trpg-universe/backups/`（保留 30 天） |

### ⚠️ 为什么是 8080 而不是 80

**这台服务器的 80 端口被运营商 HTTP 劫持了**：请求 `http://<服务器IP>/` 返回的是
**Apache 的 301**，跳到 `http://183.136.132.24`（一个陌生页面）—— **而服务器上跑的是 nginx**。
这是国内**未备案**服务器的常见现象，**不是你配置错了**。

所以 nginx 同时听 80 和 8080，**备案前一律用 `:8080` 访问**。

### 部署时踩的坑（都已修进脚本/代码）

1. **pip 只给 `-i` 不够** —— 仍会从 `files.pythonhosted.org` 拉文件而 `ReadTimeout`。
   要整组设 `PIP_INDEX_URL` / `PIP_TRUSTED_HOST` / `PIP_TIMEOUT` / `PIP_RETRIES`，
   而且**必须设在 `pip install --upgrade pip` 之前**（否则那一步先超时，配合 `set -e` 直接把脚本带走）。
2. **别装 `uvicorn[standard]`** —— httptools/uvloop 等 C 扩展在小机器上编译慢还可能失败；
   这个访问量纯 Python 版完全够用。
3. **`server/data/` 必须给 `www-data` 可写** —— 脚本里已 `chown -R`；
   否则会「能读不能写、保存报 500」。同理 `site/assets/portraits/`（立绘上传落点）。

### ⚠️⚠️ 切数据源时踩的两个大坑（2026-10-06，主人报「立绘掉了 + 排版重叠」）

**症状**：站点从静态 `data.js` 切到 `/api/data` 之后，**大量立绘变破图**，卡片网**错位重叠**。

**根因有两个，都在这边**：

1. **`/api/data` 忘了做「选角」** —— 静态站的数据是 `build_net_site.py` **选角后**的约 135 人
   （核心团全部 + 关系邻居 + 跨团 + 各团代表），而 API 直接返回了**全量 266 人**。
   布局参数是按 135 调的 → 266 人（461 条关系）塞进去，卡片网必然挤爆、阵营块互相压。
   → 已把选角逻辑搬进 `server/edit_api.py` 的 `select_site_scope()`，**口径必须和
     `tools/build_net_site.py` 保持一致**，改一边就得改另一边。
2. **`avatar` 直接把生产库字段吐给前端** —— 生产库里是
   `数据\头像\<团名>_<角色>.jpg` 这种 **Windows 路径**，前端拿去当 URL 一定 404。
   站点里的图是 build 时生成的 `<id>_t.jpg` / `<id>_f.jpg`。
   → 已改成 `portrait_of()`：按文件名去 `assets/portraits/` 里找，**找不到就返回 `null`**
     （前端显示「未解封」剪影卡，比破图体面）。

**顺带**：站点看 `?scope=site`（选角，约 139 人），**编辑器看 `?scope=all`（全量 266 人）**
—— 所以编辑器能改所有人，而关系图不会挤爆。

> 诊断脚本：`.tmp\_missing_av2.py`（查「选角里哪些人没立绘、是本来没图还是没拷进来」）、
> `.tmp\_chk_live.py`（打线上 API 核对角色数与立绘路径格式）。

---

## 三、先在本机试跑（30 秒）

`.venv` 里已经有 FastAPI + uvicorn，不用装任何东西：

```powershell
cd <仓库>
$env:ADMIN_TOKEN = (Get-Content "<凭据文件-未随仓库发布>" -Raw).Trim()
.\.venv\Scripts\python.exe server\app.py
# → http://127.0.0.1:8788/   同时提供静态站 + API
```

想只出 API（静态交给 nginx）：加 `$env:NO_SITE = "1"`。

自测（15 项，与线上同一套）：
```powershell
$env:WIKI_API = "http://127.0.0.1:8788"
.\.venv\Scripts\python.exe .tmp\test_wiki_api.py
```

---

## 二、搬到 Linux 服务器

### 1. 传文件

最小集合（约 16 MB）：

```
site/                  整个静态目录
server/app.py
trpg_agent/            ← 只有需要在本机跑同步/重建工具时才传
tools/                 ← 同上
.venv/                 ← 或者在服务器上重建（见下）
```

```bash
# 服务器上建虚拟环境（Python ≥ 3.10）
sudo apt install -y python3-venv python3-pip
cd /opt/trpg-agent
python3 -m venv .venv
.venv/bin/pip install fastapi uvicorn          # 只需要这两个
```

> 如果还要在服务器上跑 `trpg_agent` / `build_net_site.py`，就 `pip install -r requirements.txt`。

### 2. 配环境变量

`/opt/trpg-agent/.env`（**权限设 600**，里面有口令）：

```ini
ADMIN_TOKEN=把 <凭据文件-未随仓库发布> 里的那串粘过来
WIKI_DB=/opt/trpg-agent/server/wiki.db
SITE_DIR=/opt/trpg-agent/site
```

```bash
chmod 600 /opt/trpg-agent/.env
```

### 3. 跑成系统服务（systemd）

`/etc/systemd/system/trpg-universe.service`：

```ini
[Unit]
Description=TRPG Universe Wiki (proposal box API)
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/trpg-agent
EnvironmentFile=/opt/trpg-agent/.env
ExecStart=/opt/trpg-agent/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port 8788
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

```bash
sudo chown -R www-data:www-data /opt/trpg-agent/server   # 让服务能写 sqlite
sudo systemctl daemon-reload
sudo systemctl enable --now trpg-universe
sudo systemctl status trpg-universe
```

> 我把 uvicorn 绑在 `127.0.0.1:8788`，**外面只暴露 nginx/caddy**。
> 如果你想让它直接托管静态（省掉 nginx），把 `--host` 改成 `0.0.0.0` 并开放端口即可 ——
> 小规模访问完全够用，只是没有 gzip/缓存/HTTPS。

### 4. 反向代理 + HTTPS

**Caddy（最省事，自动签证书）** —— `/etc/caddy/Caddyfile`：

```caddy
wiki.example.com {
    root * /opt/trpg-agent/site

    @api path /api/*
    reverse_proxy @api 127.0.0.1:8788

    try_files {path} /index.html     # SPA 回退
    file_server
    encode gzip
}
```

**nginx** —— `/etc/nginx/sites-available/trpg-universe`：

```nginx
server {
    listen 80;
    server_name wiki.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name wiki.example.com;

    ssl_certificate     /etc/letsencrypt/live/wiki.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/wiki.example.com/privkey.pem;

    root  /opt/trpg-agent/site;
    index index.html;

    # 立绘/封面文件名带角色 id，内容不会变 → 长缓存
    location /assets/ { expires 30d; add_header Cache-Control "public, immutable"; }
    # ⚠️ 前端的 html/js/css **别缓存**，否则你部署新版后别人还看旧的
    location ~* \.(html|js|css)$ { add_header Cache-Control "no-cache"; }

    location /api/ {
        proxy_pass http://127.0.0.1:8788;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
    }

    location / { try_files $uri $uri/ /index.html; }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/trpg-universe /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d wiki.example.com      # 证书
```

---

## 三、把线上数据搬过来（D1 → SQLite）

**在本机（有 wrangler 登录态的那台）导出**：

```powershell
cd <仓库>
npx --yes wrangler@latest d1 export <D1库名> --remote --output wiki_dump.sql
```

`wiki_dump.sql` 是标准 SQL（建表 + INSERT），**直接喂 sqlite3 就行**：

```bash
scp wiki_dump.sql user@server:/opt/trpg-agent/
ssh user@server
cd /opt/trpg-agent
sqlite3 server/wiki.db < wiki_dump.sql
sqlite3 server/wiki.db "SELECT status, COUNT(*) FROM suggestions GROUP BY status;"
```

> 表结构两边完全一致，所以**没有转换步骤**。
> 服务器上没装 sqlite3 CLI 就 `sudo apt install -y sqlite3`。

---

## 四、日常运维

### 备份（SQLite 是单文件，`.backup` 是热备，最稳）

```bash
sudo mkdir -p /backup
sudo sqlite3 /opt/trpg-agent/server/wiki.db ".backup /backup/wiki-$(date +%F).db"
```

crontab 每天 4 点：

```cron
0 4 * * * sqlite3 /opt/trpg-agent/server/wiki.db ".backup /backup/wiki-$(date +\%F).db" && find /backup -name 'wiki-*.db' -mtime +30 -delete
```

### 更新站点

在本机改前端 → 重建 → 同步：

```powershell
.\.venv\Scripts\python.exe tools\build_net_site.py
# 然后 rsync/scp 把 site/ 推上去
```

```bash
rsync -av --delete site/ user@server:/opt/trpg-agent/site/
```

### 把建议拉回生产库

站点换成自托管后，`_pull_suggestions.py` 指到新地址即可：

```powershell
.\.venv\Scripts\python.exe tools\_pull_suggestions.py --url https://wiki.example.com
```

---

## 五、几个必须知道的坑

| 坑 | 说明 |
|---|---|
| **ICP 备案** | 国内服务器用**域名 + 80/443 必须备案**。只用 `IP:端口` 能跑，但体验差、可能被拦。境外服务器不需要备案，但国内访问看线路。 |
| **HTTPS** | Caddy 自动签；nginx 用 certbot。没有域名就只能 HTTP（浏览器会提示"不安全"）。 |
| **别两边同时收建议** | 搬过来之后，建议箱数据以**一边为准**。两边都开着会分叉，`_pull_suggestions.py` 拉到的不是全量。 |
| **多 worker 会漏限流** | 限流计数存在进程内存里，`uvicorn --workers 4` 会各算各的（等于放宽 4 倍）。这个规模没必要多 worker，单进程足够；真要多进程就把限流挪到 SQLite 计数。 |
| **`ADMIN_TOKEN` 是口令** | 别提交到仓库、别写进前端。审核页只在浏览器 localStorage 里存，请求时走 `x-admin-token` 头。 |
| **`no-store` 与缓存** | API 响应都带 `cache-control: no-store`；静态的 `js/css/html` 记得配 `no-cache`，否则更新后用户看旧的。 |

---

## 六、搬回 Cloudflare / 两边共存

`worker/index.js` 和 `server/app.py` 是**同一套逻辑的两个实现**，端点、鉴权、限流口径完全一致，
`.tmp/test_wiki_api.py` 两边都能跑（用 `WIKI_API` 环境变量换地址）。

所以你可以：
- **先自托管试水**，稳定后停掉 Cloudflare；或者
- **Cloudflare 当主力、服务器当国内镜像**（但数据要单向同步，别双写）；
- 想搬回去：`wrangler d1 execute <D1库名> --remote --file=<sqlite 导出>` 即可反向迁移。

> 前端的 API 地址是**同源相对路径**（`/api/...`），所以换后端**不用改前端一个字**。
> 只有 `wiki-boot.js` 的 `/api/overrides` 失败时会静默降级 —— 没有后端也能正常浏览、搜索、用独立链接。
