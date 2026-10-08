#!/usr/bin/env bash
# ============================================================
#  跑团宇宙 wiki · Debian 12 一键部署
#  ------------------------------------------------------------
#  用法（在 Debian 12 上，用有 sudo 权限的账号跑）：
#      sudo bash deploy-debian.sh /opt/trpg-universe
#
#  它会做：
#    1. 装 python3-venv / rsync / sqlite3
#    2. 建虚拟环境并装 fastapi + uvicorn（**不加别的依赖**）
#    3. 建 systemd 服务（开机自启、崩了自动重启）
#    4. 生成 .env（含随机编辑口令）并打印出来
#    5. 建好数据目录 + 每日备份 cron
#  它**不做**：改你的 nginx/caddy 配置（那步给你命令，自己粘）
#
#  说明：站点是纯静态 + 一个 FastAPI 进程，**不需要 Node、不需要数据库服务**。
#        数据是 JSON 文件（人可读可备份），SQLite 只存版本历史。
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/trpg-universe}"
SERVICE_NAME="trpg-universe"
PORT="${PORT:-8788}"
SVC_USER="${SVC_USER:-www-data}"

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m[!] %s\033[0m\n' "$*"; }

if [[ $EUID -ne 0 ]]; then
  echo "请用 sudo 跑：sudo bash deploy-debian.sh $APP_DIR" >&2
  exit 1
fi

say "1/6 安装系统依赖"
export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq python3-venv python3-pip rsync sqlite3 curl ca-certificates

say "2/6 检查应用目录"
if [[ ! -f "$APP_DIR/server/app.py" ]]; then
  warn "在 $APP_DIR 里没找到 server/app.py。"
  echo "    先把项目传上去，例如在本机执行："
  echo "        rsync -av --exclude .venv --exclude .tmp ./ user@server:$APP_DIR/"
  echo "    然后重跑本脚本。"
  exit 1
fi
cd "$APP_DIR"

say "3/6 建虚拟环境并装依赖"
if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# 国内镜像加速；装**不带 extras** 的 uvicorn —— `uvicorn[standard]` 会拉
# httptools/uvloop 等 C 扩展，小机器编译慢还可能失败，这个访问量纯 Python 版足够。
# ⚠️ 两个坑都踩过：
#   1) 只给 `-i` **不够**：pip 仍可能从 files.pythonhosted.org 取文件而 ReadTimeout；
#   2) 镜像环境变量必须**最先**设 —— 连 `pip install --upgrade pip` 都要走镜像，
#      否则它先超时、配合 set -e 直接把脚本带走。
PIP_INDEX="${PIP_INDEX:-https://mirrors.aliyun.com/pypi/simple/}"
export PIP_INDEX_URL="$PIP_INDEX"
export PIP_TRUSTED_HOST="$(printf '%s' "$PIP_INDEX" | sed -E 's#https?://([^/]+)/.*#\1#')"
export PIP_TIMEOUT="${PIP_TIMEOUT:-60}"
export PIP_RETRIES="${PIP_RETRIES:-5}"
./.venv/bin/pip install -q --no-cache-dir --upgrade pip
./.venv/bin/pip install -q --no-cache-dir fastapi uvicorn
echo "    fastapi + uvicorn 装好了（只有这两个）"

say "4/6 生成 .env（含随机编辑口令）"
if [[ -f .env ]]; then
  warn ".env 已存在，保留原样（想换口令就编辑它）"
  EDIT_TOKEN="$(grep -E '^EDIT_TOKEN=' .env | cut -d= -f2- || true)"
else
  EDIT_TOKEN="$(head -c 32 /dev/urandom | base64 | tr -dc 'A-Za-z0-9' | head -c 40)"
  cat > .env <<EOF
# 跑团宇宙 wiki · 环境变量（权限 600，别外传）
EDIT_TOKEN=$EDIT_TOKEN
ADMIN_TOKEN=$EDIT_TOKEN
# 权威数据（人可读 JSON）
WIKI_DATA=$APP_DIR/server/data
# 版本历史数据库
WIKI_DB=$APP_DIR/server/wiki.db
# 静态站点
SITE_DIR=$APP_DIR/site
# 立绘上传落点（会被站点直接访问）
PORTRAIT_DIR=$APP_DIR/site/assets/portraits
# 已有头像目录（可选：给还没上传立绘的角色兜底）
# AVATAR_DIR=/path/to/头像
EOF
  chmod 600 .env
  echo "    .env 建好了"
fi

# 数据目录
mkdir -p "$APP_DIR/server/data" "$APP_DIR/site/assets/portraits"
if [[ ! -f "$APP_DIR/server/data/characters.json" ]]; then
  cat > "$APP_DIR/server/data/characters.json" <<'EOF'
{ "characters": [] }
EOF
  cat > "$APP_DIR/server/data/relations.json" <<'EOF'
{ "relations": [] }
EOF
  warn "server/data/ 是空的 —— 记得把你现有的 characters.json / relations.json 放进去，"
  echo "        或者用 tools/_export_d1.py 从 Cloudflare 导一份。"
fi

chown -R "$SVC_USER:$SVC_USER" "$APP_DIR/server" "$APP_DIR/site" 2>/dev/null || true

say "5/6 安装 systemd 服务"
cat > "/etc/systemd/system/$SERVICE_NAME.service" <<EOF
[Unit]
Description=TRPG Universe Wiki (static site + editing API)
After=network.target

[Service]
Type=simple
User=$SVC_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn server.app:app --host 127.0.0.1 --port $PORT
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable --now "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "    服务已启动 ✅"
else
  warn "服务没起来，看日志：journalctl -u $SERVICE_NAME -n 50 --no-pager"
fi

say "6/6 每日备份 cron"
cat > "/etc/cron.daily/$SERVICE_NAME-backup" <<EOF
#!/bin/sh
# 数据 JSON + 版本历史库，每天备份，保留 30 天
D=$APP_DIR/backups
mkdir -p "\$D"
STAMP=\$(date +%F)
cp -f $APP_DIR/server/data/characters.json "\$D/characters-\$STAMP.json" 2>/dev/null || true
cp -f $APP_DIR/server/data/relations.json  "\$D/relations-\$STAMP.json"  2>/dev/null || true
sqlite3 $APP_DIR/server/wiki.db ".backup '\$D/wiki-\$STAMP.db'" 2>/dev/null || true
find "\$D" -type f -mtime +30 -delete
EOF
chmod +x "/etc/cron.daily/$SERVICE_NAME-backup"
echo "    备份脚本：/etc/cron.daily/$SERVICE_NAME-backup（保留 30 天）"

echo
echo "============================================================"
echo " 部署完成"
echo "============================================================"
echo " 服务状态 : systemctl status $SERVICE_NAME"
echo " 本地探活 : curl -s localhost:$PORT/api/edit/ping"
echo
echo " **编辑口令（发给一起玩的人）** ："
echo "     $EDIT_TOKEN"
echo "   （也存在 $APP_DIR/.env，权限 600）"
echo
echo " 还差一步：把外面接进来（二选一）"
echo
echo " 【Caddy，自动 HTTPS，最省事】"
echo "   apt install -y caddy"
echo "   cat > /etc/caddy/Caddyfile <<'CFG'"
echo "   wiki.example.com {"
echo "       root * $APP_DIR/site"
echo "       @api path /api/*"
echo "       reverse_proxy @api 127.0.0.1:$PORT"
echo "       try_files {path} /index.html"
echo "       file_server"
echo "       encode gzip"
echo "   }"
echo "   CFG"
echo "   systemctl reload caddy"
echo
echo " 【nginx】"
echo "   server {"
echo "       listen 80; server_name wiki.example.com;"
echo "       root $APP_DIR/site; index index.html;"
echo "       location /assets/ { expires 30d; add_header Cache-Control \"public, immutable\"; }"
echo "       location ~* \\.(html|js|css)\$ { add_header Cache-Control \"no-cache\"; }"
echo "       location /api/ {"
echo "           proxy_pass http://127.0.0.1:$PORT;"
echo "           proxy_set_header Host \$host;"
echo "           proxy_set_header X-Real-IP \$remote_addr;"
echo "           proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;"
echo "       }"
echo "       location / { try_files \$uri \$uri/ /index.html; }"
echo "   }"
echo
echo " 改完前端要同步到服务器："
echo "   rsync -av --delete site/ user@server:$APP_DIR/site/"
echo
echo " ⚠️ 国内服务器用域名 + 80/443 需要 ICP 备案；只用 IP:端口 能跑但体验差。"
echo "============================================================"
