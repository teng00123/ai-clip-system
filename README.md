# ✂️ AI Clip System

> **用 AI 的力量，让短视频剪辑化繁为简。**
>
> 从创意到成片的完整工作流：引导问答 → LLM 生成剧本 → 视频上传 → AI 自动剪辑 → 字幕烧录 → MP4 导出

---

## 目录

- [功能特性](#功能特性)
- [技术栈](#技术栈)
- [架构概览](#架构概览)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [API 参考](#api-参考)
- [开发指南](#开发指南)
- [测试](#测试)
- [生产部署](#生产部署)
- [配置说明](#配置说明)
- [FAQ](#faq)

---

## 功能特性

| 功能 | 描述 |
|---|---|
| 🎯 **引导问答** | 多轮对话式引导，帮助梳理视频创作意图 |
| 📝 **AI 剧本生成** | 基于问答结果，调用 GPT-4o 自动生成分镜剧本 |
| 🎬 **视频上传** | 支持最大 500MB 视频，MinIO 对象存储 |
| ✂️ **AI 自动剪辑** | PySceneDetect 场景识别 + Whisper ASR + FFmpeg 渲染 |
| 💬 **字幕烧录** | 自动生成 SRT，可选硬字幕烧录 |
| 📡 **实时进度** | WebSocket 推送剪辑进度，前端实时展示 |
| 📦 **MP4 导出** | 生成预签名下载链接，直接下载成品 |
| 🔐 **安全** | JWT 鉴权、资源归属校验、级联删除 |

---

## 技术栈

```
前端           后端              基础设施
────────────   ───────────────   ─────────────
Vue 3          FastAPI           PostgreSQL 16
TypeScript     SQLAlchemy async  Redis 7
Pinia          Celery 5.4        MinIO (S3)
Vite           asyncpg           FFmpeg
               Alembic           Nginx (prod)

AI
──────────────
OpenAI GPT-4o    ← 剧本生成
OpenAI Whisper   ← 语音识别 / 字幕
PySceneDetect    ← 场景识别
```

---

## 架构概览

```
用户浏览器
    │
    ├── HTTP / WS
    ▼
┌──────────────────────────────────┐
│  Nginx（生产模式）               │
│  /api/* → backend:8000           │
│  /ws/*  → backend:8000           │
│  /*     → frontend:5173          │
└──────────────────────────────────┘
         │
         ├─── FastAPI (backend:8000)
         │      ├── JWT 鉴权
         │      ├── REST API
         │      ├── WebSocket /ws/clip/{job_id}
         │      └── 写 Celery 任务到 Redis
         │
         ├─── Celery Worker
         │      └── clip_task.process_clip_job
         │            ├── ffprobe 探测时长
         │            ├── PySceneDetect 场景切割
         │            ├── Whisper ASR → SRT 字幕
         │            ├── FFmpeg 拼接 + 字幕烧录
         │            └── 推送进度 → Redis Pub/Sub → WS
         │
         ├─── PostgreSQL  （用户/项目/视频/剪辑任务）
         └─── MinIO       （视频原始文件 + 成品）
```

---

## 快速开始

### 前置条件

- **Docker** ≥ 24 + **Docker Compose** v2
- （可选）OpenAI API Key — 无 key 时 ASR/LLM 步骤自动跳过，仍可走完完整流程

### 一键初始化（开发环境）

```bash
# 1. 进入项目目录
cd ai-clip-system

# 2. 首次初始化
#    - 复制 .env.example → .env
#    - 并行构建所有镜像
#    - 启动全部服务
#    - 执行数据库迁移
make setup
```

> ⚠️ **初始化完成后**，务必编辑 `.env`：
> ```bash
> vim .env   # 或 nano .env
> ```
> 最低必填：`JWT_SECRET`（生成方法见 [配置说明](#配置说明)）

### 访问地址

| 服务 | 地址 | 说明 |
|---|---|---|
| 前端 | http://localhost:5173 | Vue 3 开发服务器 |
| 后端 API | http://localhost:8000 | FastAPI |
| Swagger UI | http://localhost:8000/docs | 交互式 API 文档 |
| ReDoc | http://localhost:8000/redoc | 阅读式 API 文档 |
| MinIO 控制台 | http://localhost:9001 | 对象存储管理（admin/minioadmin123） |

### 常用命令

```bash
# 服务管理
make up           # 后台启动所有服务
make down         # 停止所有服务
make build        # 重新构建镜像（并行）
make rebuild      # 强制重新构建（无缓存）
make clean        # 停止 + 删除所有卷（⚠️ 会清空数据库）

# 日志查看
make logs         # 所有服务日志（实时）
make logs-backend # 仅后端日志
make logs-worker  # 仅 Celery Worker 日志

# 数据库迁移
make migrate           # 应用所有待执行迁移
make migrate-create    # 创建新迁移（交互式输入名称）
make migrate-history   # 查看迁移历史
make migrate-down      # 回滚最近一次迁移

# 进入容器 Shell
make shell-backend  # 后端容器 bash
make shell-worker   # Celery Worker 容器 bash
make shell-db       # psql 客户端
make shell-redis    # redis-cli

# 测试
make test           # 容器内运行测试
make test-v         # 容器内 verbose 模式
make test-local     # 本地直接运行（需 aiosqlite）
```

---

## 项目结构

```
ai-clip-system/
│
├── .env.example               ← 环境变量模板（含详细注释）
├── docker-compose.yml         ← 8 个服务定义
├── Makefile                   ← 开发/运维快捷命令
│
├── backend/
│   ├── Dockerfile             ← python:3.11-slim，非 root 用户
│   ├── requirements.txt       ← Python 依赖（含版本锁）
│   │
│   ├── app/
│   │   ├── main.py            ← FastAPI 应用入口
│   │   ├── config.py          ← Pydantic Settings 配置
│   │   │
│   │   ├── api/               ← 路由层
│   │   │   ├── auth.py        ← 注册 / 登录 / 当前用户
│   │   │   ├── projects.py    ← 项目 CRUD + 级联删除
│   │   │   ├── guide.py       ← 引导问答会话
│   │   │   ├── scripts.py     ← 剧本生成 / 编辑
│   │   │   ├── videos.py      ← 视频上传（≤500MB）
│   │   │   ├── clips.py       ← 剪辑任务创建 / 查询 / 导出
│   │   │   └── ws.py          ← WebSocket 进度推送
│   │   │
│   │   ├── models/            ← SQLAlchemy 模型
│   │   │   ├── types.py       ← JsonType（SQLite/PG 兼容）
│   │   │   ├── guide_session.py
│   │   │   ├── script.py
│   │   │   ├── video.py
│   │   │   └── clip_job.py
│   │   │
│   │   ├── tasks/
│   │   │   ├── celery_app.py  ← Celery 实例配置
│   │   │   └── clip_task.py   ← 完整剪辑管道（场景/ASR/FFmpeg）
│   │   │
│   │   └── utils/
│   │       ├── auth.py        ← JWT 工具（创建/验证）
│   │       ├── jwt_utils.py   ← bcrypt/sha256 密码哈希（自动降级）
│   │       └── storage.py     ← MinIO 操作封装
│   │
│   ├── alembic/
│   │   ├── env.py             ← async-aware 迁移环境
│   │   └── versions/
│   │       └── 0001_initial.py ← 初始建表迁移（6 张表 + 索引）
│   │
│   └── tests/
│       ├── conftest.py        ← 测试基础设施（async aiosqlite + mock）
│       ├── test_authz.py      ← 鉴权 + 资源归属测试
│       ├── test_video_upload.py ← 上传限制测试
│       ├── test_project_cleanup.py ← 级联删除测试
│       ├── test_e2e.py        ← 完整 API 流程测试（31 个）
│       └── test_clip_task.py  ← Celery task 单元测试（27 个）
│
├── frontend/
│   ├── Dockerfile             ← 开发服务器（node:20-alpine）
│   ├── Dockerfile.prod        ← 生产构建（multi-stage + nginx）
│   │
│   └── src/
│       ├── main.ts            ← 应用入口
│       ├── App.vue            ← 根组件
│       │
│       ├── assets/
│       │   └── main.css       ← 全局样式（Design tokens + 组件库）
│       │
│       ├── types/index.ts     ← TypeScript 类型定义
│       │
│       ├── api/               ← HTTP 客户端（axios）
│       │   ├── client.ts      ← axios 实例 + 401 拦截
│       │   ├── auth.ts
│       │   ├── projects.ts
│       │   ├── guide.ts
│       │   ├── scripts.ts
│       │   ├── videos.ts
│       │   └── clips.ts
│       │
│       ├── stores/            ← Pinia 状态管理
│       │   ├── auth.ts        ← 用户登录态（localStorage 持久化）
│       │   ├── project.ts
│       │   ├── guide.ts
│       │   ├── script.ts
│       │   └── clip.ts
│       │
│       ├── router/index.ts    ← 嵌套路由 + 登录守卫
│       │
│       ├── components/
│       │   └── common/
│       │       ├── AppLayout.vue    ← 带 NavBar 的布局容器
│       │       ├── NavBar.vue       ← 顶部导航（步骤条 + 用户菜单）
│       │       └── LoadingSpinner.vue
│       │
│       └── views/             ← 8 个核心页面
│           ├── LoginView.vue
│           ├── RegisterView.vue
│           ├── DashboardView.vue
│           ├── GuideView.vue
│           ├── ScriptView.vue
│           ├── VideoUploadView.vue
│           ├── ClipView.vue
│           └── ExportView.vue
│
└── nginx/
    └── nginx.conf             ← 反向代理配置（prod profile）
```

---

## API 参考

### 认证

所有需要鉴权的接口在 `Authorization: Bearer <token>` header 中携带 JWT。

```
POST /api/auth/register    { email, password, nickname? }  → TokenOut
POST /api/auth/login       { email, password }             → TokenOut
GET  /api/auth/me                                          → UserOut
```

### 项目

```
POST   /api/projects                      创建项目
GET    /api/projects                      列出当前用户所有项目
GET    /api/projects/{id}                 获取项目详情
PATCH  /api/projects/{id}                 更新项目
DELETE /api/projects/{id}                 删除项目（级联清理 DB + MinIO）
```

### 引导问答

```
POST /api/guide/{project_id}/start        开始新的问答会话
GET  /api/guide/{session_id}/question     获取当前问题
POST /api/guide/{session_id}/answer       提交回答，获取下一题
GET  /api/guide/{session_id}/summary      获取会话摘要
```

### 剧本

```
POST /api/scripts/{project_id}/generate   基于问答摘要调用 GPT-4o 生成剧本
GET  /api/scripts/{project_id}            获取剧本
PUT  /api/scripts/{script_id}             更新剧本内容
```

### 视频

```
POST /api/videos/{project_id}/upload      上传视频（multipart, ≤500MB）
GET  /api/videos/{project_id}             列出项目视频
DELETE /api/videos/{video_id}             删除视频（含 MinIO 对象）
```

### 剪辑任务

```
POST /api/clips                           创建剪辑任务（触发 Celery）
GET  /api/clips/{job_id}                  查询任务状态与进度
GET  /api/clips/{job_id}/download         获取成品预签名下载 URL
```

### WebSocket 进度

```
WS /ws/clip/{job_id}?token=<jwt>
```

连接后持续接收进度消息，格式：

```json
{ "type": "progress", "progress": 65, "message": "生成字幕中…" }
{ "type": "done",     "progress": 100, "message": "剪辑完成" }
{ "type": "error",    "progress": 0,   "message": "FFmpeg 渲染失败" }
```

---

## 开发指南

### 本地后端开发（不用 Docker）

```bash
cd backend

# 创建 virtualenv
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动外部服务（仅 postgres/redis/minio）
docker compose up -d postgres redis minio minio-init

# 复制并编辑 .env（在项目根目录）
cp ../.env.example ../.env

# 执行迁移
alembic upgrade head

# 启动 FastAPI
uvicorn app.main:app --reload --port 8000

# 另开终端，启动 Celery Worker
celery -A app.tasks.celery_app worker --loglevel=info --queues=clip
```

### 本地前端开发

```bash
cd frontend
npm install
npm run dev
# 访问 http://localhost:5173
```

> 前端默认将 `/api/*` 代理到 `http://localhost:8000`（见 `vite.config.ts`）

### 添加新迁移

```bash
# 修改 app/models/ 后：
make migrate-create   # 输入迁移名称
make migrate          # 应用
```

### 代码风格

- **后端**：Black + isort（无强制 CI，保持 PEP 8 即可）
- **前端**：Vue 3 `<script setup>` + TypeScript strict 模式

---

## 测试

```bash
# 推荐：本地直接运行（无需 Docker，快）
cd backend
pytest --tb=short -q
# 结果：66 passed, 10 warnings
```

### 测试覆盖

| 文件 | 数量 | 覆盖内容 |
|---|---|---|
| `test_authz.py` | 5 | JWT 鉴权、跨用户资源隔离 |
| `test_video_upload.py` | 2 | 文件大小限制、格式校验 |
| `test_project_cleanup.py` | 1 | 项目删除级联清理 |
| `test_e2e.py` | 31 | 完整 API 流程（register→login→project→guide→script→upload→clip→export） |
| `test_clip_task.py` | 27 | Celery task 全管道（ffprobe/scenedetect/whisper/ffmpeg 全部 mock） |
| **合计** | **66** | — |

### 测试设计

- **数据库**：`sqlite+aiosqlite:///:memory:` + `StaticPool`，无需真实 PG
- **外部服务**：MinIO / OpenAI / Redis 全部通过 `unittest.mock.patch` mock
- **scenedetect**：通过 `sys.modules` 注入 fake module，绕过 `libGL.so.1` 依赖

---

## 生产部署

### 启动生产模式

```bash
# 1. 编辑 .env（填写所有生产密钥）
cp .env.example .env && vim .env

# 2. 构建 + 启动（含 Nginx 反向代理）
make prod-up

# 3. 执行迁移
make migrate
```

### 生产检查清单

- [ ] `JWT_SECRET` — 64位随机十六进制，例：`python -c "import secrets; print(secrets.token_hex(32))"`
- [ ] `POSTGRES_PASSWORD` — 强密码
- [ ] `MINIO_SECRET_KEY` — 强密钥（≥8位）
- [ ] `OPENAI_API_KEY` — 有效的 OpenAI API Key
- [ ] 配置 HTTPS（在 Nginx 前加 Certbot / 外部 LB）
- [ ] 设置 MinIO bucket 权限为私有
- [ ] 配置防火墙，仅开放 80/443 端口
- [ ] 定期备份 PostgreSQL 数据卷

### 服务端口

| 服务 | 容器端口 | 宿主机端口 | 说明 |
|---|---|---|---|
| frontend | 5173 | 5173 | 仅开发模式暴露 |
| backend | 8000 | 8000 | API 服务 |
| postgres | 5432 | 5432 | 数据库 |
| redis | 6379 | 6379 | 消息队列 |
| minio | 9000 | 9000 | S3 API |
| minio | 9001 | 9001 | Web 控制台 |
| nginx | 80 | 80 | 反向代理（prod profile） |

---

## 配置说明

完整配置见 `.env.example`。关键变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `JWT_SECRET` | `change-me-in-production` | **必须修改**，JWT 签名密钥 |
| `JWT_EXPIRE_HOURS` | `24` | Token 有效期（小时） |
| `OPENAI_API_KEY` | _(空)_ | 不填时 LLM/ASR 步骤跳过 |
| `OPENAI_MODEL` | `gpt-4o` | 剧本生成用模型 |
| `WHISPER_MODEL` | `whisper-1` | 语音转文字模型 |
| `CELERY_CONCURRENCY` | `2` | Worker 并发数 |
| `MINIO_BUCKET` | `ai-clip` | 存储桶名称（自动创建） |
| `DATABASE_URL` | `postgresql+asyncpg://...` | 异步 PG 连接串 |

---

## FAQ

**Q: 没有 OpenAI API Key 也能用吗？**

A: 可以。留空 `OPENAI_API_KEY` 时，剧本生成会返回 placeholder 内容，ASR 字幕步骤会跳过（视频仍能剪辑，只是无字幕烧录）。

**Q: 视频上传有大小限制吗？**

A: 默认 500MB。可在 `backend/app/api/videos.py` 修改 `MAX_FILE_SIZE` 常量，同时更新 `nginx/nginx.conf` 中的 `client_max_body_size`。

**Q: 如何查看剪辑任务日志？**

A: `make logs-worker` 实时查看 Celery Worker 输出，或通过 `GET /api/clips/{job_id}` 查询任务状态字段。

**Q: 测试跑不起来，报 `aiosqlite` not found？**

A: 确保已安装测试依赖：`pip install aiosqlite pytest-asyncio anyio`，或直接 `pip install -r requirements.txt`。

**Q: scenedetect 报 `libGL.so.1 not found`？**

A: 这是 OpenCV 在无显示环境下的已知问题。生产环境 Docker 镜像已内置 `libglib2.0-0`；本地开发可安装 `opencv-python-headless` 替代 `opencv-python`。

**Q: WebSocket 连接立即断开，code 1008？**

A: Token 无效或不属于该任务的所有者。确认 URL 中 `?token=` 参数为有效 JWT，且该任务由当前用户创建。

---

## License

MIT License — 仅供学习与个人项目使用。商业使用请确认 OpenAI、FFmpeg 等组件各自的授权条款。
