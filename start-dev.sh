#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# start-dev.sh — 裸机开发环境一键启动脚本（非 Docker）
#
# 使用前提：
#   1. Redis 已在本机 localhost:6379 运行
#   2. MySQL 已在本机运行（DATABASE_URL 里的地址可达）
#   3. MinIO 已在本机运行（MINIO_ENDPOINT 里的地址可达）
#   4. .env 文件中所有地址已改为 localhost（见 .env.local.example）
#   5. 虚拟环境已安装依赖：pip install -r backend/requirements.txt
#
# 用法：
#   chmod +x start-dev.sh
#   ./start-dev.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e

VENV="${VENV_PATH:-/tmp/ai-clip-test-env}"
BACKEND_DIR="$(cd "$(dirname "$0")/backend" && pwd)"
PYTHON="$VENV/bin/python3"
CELERY="$VENV/bin/celery"

# 颜色
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[START]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()  { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 检查虚拟环境 ──────────────────────────────────────────────────────────────
[ -x "$PYTHON" ] || die "虚拟环境不存在: $PYTHON\n请先运行: python3 -m venv $VENV && $VENV/bin/pip install -r backend/requirements.txt"

# ── 检查 .env ─────────────────────────────────────────────────────────────────
[ -f "$BACKEND_DIR/../.env" ] || die ".env 文件不存在，请复制 .env.local.example 并填写配置"

# 检查是否还用 Docker 服务名
if grep -qE "redis://redis:|@postgres:|@mysql:" "$BACKEND_DIR/../.env"; then
    warn ".env 中仍使用 Docker 服务名（redis/postgres/mysql），裸机运行需改为 localhost"
    warn "继续启动，但连接可能失败..."
fi

cd "$BACKEND_DIR"

# ── 启动 Celery Worker ────────────────────────────────────────────────────────
log "启动 Celery worker..."
CELERY_LOG="$BACKEND_DIR/../logs/celery.log"
mkdir -p "$(dirname "$CELERY_LOG")"

PYTHONPATH="$BACKEND_DIR" "$CELERY" \
    -A app.tasks.celery_app worker \
    --loglevel=info \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --logfile="$CELERY_LOG" \
    --detach \
    --pidfile="/tmp/ai-clip-celery.pid"

log "Celery worker 已在后台启动，日志: $CELERY_LOG"

# ── 启动 FastAPI ───────────────────────────────────────────────────────────────
log "启动 FastAPI (uvicorn)..."
log "后端地址: http://0.0.0.0:8000"
log "API 文档: http://localhost:8000/docs"
echo ""

PYTHONPATH="$BACKEND_DIR" "$VENV/bin/uvicorn" app.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --reload \
    --reload-dir "$BACKEND_DIR/app"
