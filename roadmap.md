# AI 辅助短视频剪辑系统 — 迭代计划文档

> 版本：v0.3 | 最后更新：2026-04-09  
> 原则：**先跑通，再做精，再做全**

---

## 总体里程碑

```
         MVP          V1.0         V1.5         V2.0
Week  1─────────6  7─────────12  13──────16  17────────24
      ████████████  ░░░░░░░░░░░   ░░░░░░░░    ░░░░░░░░░░
      ✅ 已完成
```

---

## ✅ MVP（第一阶段）— 已完成

**周期完成时间**：2026-04-09  
**目标**：用户能完成「引导问答 → 生成剧本 → 上传视频 → AI 自动剪辑草稿 → 字幕 → 导出 MP4」完整闭环

### 后端任务

- [x] FastAPI 项目脚手架 + Docker Compose 配置（8 服务）
- [x] PostgreSQL 数据库设计（6 张表 + 索引）+ Alembic 迁移
- [x] 用户注册/登录（JWT 鉴权，bcrypt/sha256_crypt 自动降级）
- [x] 会话服务：固定问题集状态机，存储答案，生成 Brief JSON
- [x] 剧本服务：接入 OpenAI GPT-4o，按口播格式生成初稿，版本存储
- [x] 文件上传接口：接收视频文件（≤500MB），存 MinIO，提取元数据
- [x] Celery 异步任务框架（Redis broker）
- [x] AI 剪辑任务完整 Pipeline：
  - [x] ffprobe 探测时长
  - [x] PySceneDetect 场景切割（空结果 fallback 全视频）
  - [x] Whisper ASR → SRT 字幕（无 API Key 时跳过）
  - [x] FFmpeg concat demuxer + 可选字幕烧录
- [x] WebSocket 进度推送（`/ws/clip/{job_id}?token=<jwt>`）
- [x] 全面安全加固：资源归属校验、级联删除、WS 双重鉴权
- [x] 全套测试 66 个（8 单元 + 31 E2E + 27 clip_task），全绿

### 前端任务

- [x] Vue3 + Vite + TypeScript 项目初始化，路由（vue-router）+ 状态管理（Pinia）
- [x] 全局 CSS 体系（Design tokens + 组件样式库）
- [x] 登录页（表单验证 + 密码可见切换 + 背景光晕动画）
- [x] 注册页（密码强度条 + 四字段验证）
- [x] Dashboard（项目卡片网格 + 创建/删除 modal）
- [x] 引导问答界面（进度条 + 多题型渲染 + 答案提交）
- [x] 剧本展示 + 纯文本编辑器
- [x] 文件上传组件（拖拽 + 进度条）
- [x] AI 剪辑结果展示（片段列表 + 字幕预览）
- [x] WebSocket 监听任务进度
- [x] 导出按钮 + 预签名下载链接
- [x] NavBar 步骤条 + AppLayout 嵌套路由 + 登录守卫

### 容器化

- [x] docker-compose.yml（postgres/redis/minio/minio-init/backend/celery-worker/frontend/nginx）
- [x] backend/Dockerfile（非 root 用户 appuser 1001）
- [x] frontend/Dockerfile（开发）+ Dockerfile.prod（multi-stage）
- [x] nginx/nginx.conf（反向代理，API/WS/frontend，600m 上限）
- [x] Makefile（20+ 常用命令）
- [x] .env.example + README.md（516 行，12 章节）

### 验收结果

| 指标 | 结果 |
|---|---|
| 测试覆盖 | 66 passed, 0 failed |
| 核心链路 | 注册→登录→项目→问答→剧本→上传→剪辑→导出 全通 |
| 容器化 | YAML 语法验证通过，8 服务定义完整 |
| 文档 | README + roadmap + architecture.md 齐全 |

---

## 🔜 V1.0（第二阶段）— 下一周期计划

**目标时间**：4～6 周  
**核心主题**：剪辑体验升级 + 人工深度介入 + LLM 能力增强

> **优先级说明**：🔴 必须 | 🟡 重要 | 🟢 可选

### 迭代 3.1 — LLM 能力增强（Week 1～2）

**目标**：从固定问题集升级到 LLM 动态对话，剧本支持段落级重写

**后端**
- [ ] 🔴 动态问答引擎：LangChain ConversationChain，基于前序答案生成下一问题（替换固定题库）
- [ ] 🔴 段落重写 API：`POST /api/scripts/{script_id}/rewrite`，接受 `{ paragraph_index, instruction }` → LLM 重写单段
- [ ] 🔴 剧本格式支持：新增 `format` 字段，支持 `voiceover`（口播）/ `storyboard`（分镜）两种格式
- [ ] 🟡 SSE 流式输出：剧本生成改为 Server-Sent Events，前端逐字显示（改善长等待体验）
- [ ] 🟡 Brief JSON schema 扩展：补充 `tone`（语气）、`target_audience`、`duration_target` 字段

**前端**
- [ ] 🔴 问答界面升级：支持「动态问题」模式（服务端流式返回问题文本）
- [ ] 🔴 剧本编辑器增加「AI 重写」按钮（选中段落 → 输入指令 → 实时预览新版本）
- [ ] 🟡 剧本格式切换 Tab（口播文案 / 分镜脚本）
- [ ] 🟡 SSE 流式渲染（打字机效果）

**测试**
- [ ] 🔴 新增 LLM 动态问答 mock 测试（ConversationChain 全 mock）
- [ ] 🔴 段落重写 API E2E 测试
- [ ] 🟡 SSE 响应格式测试

---

### 迭代 3.2 — 时间轴编辑器（Week 2～4）

**目标**：前端核心差距补全——可交互时间轴，让用户可以精确调整剪辑方案

> 这是 V1.0 最高难度任务，建议先调研 `wavesurfer.js` / `peaks.js` 改造成本

**前端**
- [ ] 🔴 `TimelineEditor.vue` 组件（基于 Canvas 或 SVG）：
  - 片段色块可视化（宽度 = 时长比例）
  - 可拖动的切点标记（左/右边界拖拽调整片段时长）
  - 字幕轨道（独立一行，可点击编辑文本）
  - 缩放控制（10s/30s/全览 三档）
- [ ] 🔴 片段操作：删除片段、合并相邻片段
- [ ] 🟡 字幕在线编辑（点击字幕轨道 → 弹出 inline 编辑框）
- [ ] 🟡 时间轴与视频播放器联动（拖动播放头）

**后端**
- [ ] 🔴 剪辑方案修改 API：`PATCH /api/clips/{job_id}/plan`，接受修改后的 `clip_plan` JSON
- [ ] 🔴 重新渲染 API：`POST /api/clips/{job_id}/rerender`，基于修改后的 plan 重新触发 FFmpeg
- [ ] 🟡 方案版本快照：每次 `PATCH` 自动保存版本 diff，支持撤销（`GET /api/clips/{job_id}/plan/history`）

**测试**
- [ ] 🔴 剪辑方案修改 + 重新渲染 API 测试
- [ ] 🟡 版本回退测试

---

### 迭代 3.3 — 转场 & 字幕样式（Week 4～5）

**目标**：成片质量提升，支持基础转场效果和自定义字幕样式

**后端**
- [ ] 🔴 FFmpeg 转场支持：`clip_plan` 中新增 `transition` 字段（`fade`/`wipe`/`dissolve`），渲染时使用 `xfade` filter
- [ ] 🔴 字幕样式参数：`subtitle_style` 字段（font_size/color/position/background），生成 ASS 格式传给 FFmpeg
- [ ] 🟡 大文件分片上传：`POST /api/videos/{project_id}/upload/init` → `PUT` 分片 → `POST` 完成，支持最大 2GB

**前端**
- [ ] 🔴 转场选择 Panel（可选 4 种：无/淡入淡出/叠化/推拉），关联时间轴切点
- [ ] 🔴 字幕样式编辑器（字号/颜色/位置选择器）
- [ ] 🟡 大文件分片上传组件（基于 resumable.js 或自研）

**测试**
- [ ] 🔴 转场参数传递测试（FFmpeg 命令拼接单元测试）
- [ ] 🔴 字幕样式 ASS 生成测试

---

### 迭代 3.4 — 体验打磨 & 稳定性（Week 5～6）

**目标**：消除 MVP 阶段的体验粗糙点，提升生产可用性

**后端**
- [ ] 🔴 任务失败重试机制：区分可重试错误（网络/超时）和不可重试错误（文件损坏），配置 `autoretry_for`
- [ ] 🔴 任务超时保护：Celery soft_time_limit（10min）+ hard time_limit（15min），超时状态写回 DB
- [ ] 🟡 API 限流：`slowapi` 装饰器，登录接口 5次/分钟，上传接口 10次/小时
- [ ] 🟡 结构化日志：统一 JSON 格式（含 request_id、user_id、耗时）

**前端**
- [ ] 🔴 全局 Toast 通知组件（成功/失败/警告，自动消失）
- [ ] 🔴 API 错误统一处理（401 自动跳登录，5xx 显示友好提示）
- [ ] 🔴 表单加载状态完善（所有提交按钮增加 disabled + spinner）
- [ ] 🟡 页面骨架屏（Dashboard 项目列表加载时）
- [ ] 🟡 移动端适配（NavBar 折叠 + 页面最小宽度 375px）

**DevOps**
- [ ] 🟡 GitHub Actions CI：push 时自动跑 `pytest`，PR 时 `docker build` 验证
- [ ] 🟡 Makefile 补充 `make lint`（flake8/black check）和 `make type-check`（mypy）
- [ ] 🟢 Sentry 接入（错误上报，后端 + 前端）

---

## 优先级汇总表（V1.0 周期）

| 迭代 | 任务 | 优先级 | 预估工时 |
|---|---|---|---|
| 3.1 | LLM 动态问答 | 🔴 | 3d |
| 3.1 | 段落重写 API + 前端 | 🔴 | 2d |
| 3.1 | SSE 流式输出 | 🟡 | 1d |
| 3.2 | 时间轴组件 | 🔴 | 5d |
| 3.2 | 剪辑方案修改 + 重新渲染 API | 🔴 | 2d |
| 3.2 | 版本快照 | 🟡 | 1d |
| 3.3 | FFmpeg 转场 | 🔴 | 2d |
| 3.3 | 字幕样式 ASS | 🔴 | 1d |
| 3.3 | 大文件分片上传 | 🟡 | 2d |
| 3.4 | Toast + 错误处理 | 🔴 | 1d |
| 3.4 | 任务超时/重试 | 🔴 | 1d |
| 3.4 | CI/CD | 🟡 | 1d |

**总预估**：~22 工作日（含余量）

---

## 后续阶段（待 V1.0 完成后详细规划）

### V1.5 — 抖音生态接入（3～4 周）
- 抖音链接解析 + 火山引擎 veVOD API 下载无水印视频
- 剪辑风格模板库（vlog/美食/知识分享/带货/旅行）
- 字幕样式库（多字体/颜色/动画预设）
- 批量素材导入

### V2.0 — 智能化升级（4～6 周）
- 多模态联合分析（视觉 + 音频 + 字幕）
- AI 剪辑方案评分 + 多方案对比
- 协作功能（多人审核、批注）
- EDL/XML 导出（兼容 Premiere Pro）
- 数据看板

---

## 技术债务清单

> 在 V1.0 周期内应同步偿还的已知问题

| 问题 | 影响 | 优先级 |
|---|---|---|
| `guide.py` 问题集硬编码在代码里，非动态 LLM | 问答质量低 | 🔴 |
| 无 API 限流，暴力破解风险 | 安全 | 🟡 |
| 前端无全局 Toast，错误提示不一致 | 体验 | 🔴 |
| 任务超时无上限，Worker 可能长期阻塞 | 稳定性 | 🔴 |
| 无 CI，每次改动靠手动运行测试 | 工程效率 | 🟡 |
| `clip_plan` 修改无版本管理，误操作不可恢复 | 数据安全 | 🟡 |

---

*文档版本：v0.3 | 配套文档：architecture.md / README.md*
