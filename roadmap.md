# AI 辅助短视频剪辑系统 — 迭代计划文档

> 版本：v0.1 | 日期：2026-04-08  
> 原则：**先跑通，再做精，再做全**

---

## 总体里程碑一览

```
Week  1     4     8     12    16    20    24
      ├─────┤─────┤─────┤─────┤─────┤─────┤
      │  MVP（W1-W6）     │
                  │  V1.0（W7-W12）  │
                              │  V1.5（W13-W16）│
                                        │  V2.0（W17-W24）│
```

---

## 📦 MVP（第一阶段）— 跑通核心链路

**周期**：4～6 周  
**目标**：用户能完成「引导问答 → 生成剧本 → 上传视频 → AI 自动剪辑草稿 → 字幕 → 导出 MP4」完整闭环

### ✅ 功能范围（IN）

| 功能模块 | 具体内容 |
|----------|----------|
| 引导问答 | 固定题目集（8 题），单选 + 文字填空，无动态调整 |
| 剧本生成 | 基于 Brief 调用 LLM 生成口播文案格式初稿 |
| 剧本编辑 | 纯文本编辑，无模板切换 |
| 素材管理 | 本地上传 MP4/MOV，最大 500MB |
| AI 剪辑 | 场景自动切片（PySceneDetect）|
| 字幕生成 | Whisper ASR 自动生成 SRT，字幕烧录到成品 |
| 预览 | 基础视频播放器，展示 AI 切片结果 |
| 导出 | 导出 1080P MP4（FFmpeg 合成）|
| 用户系统 | 注册/登录（JWT），项目管理 |

### ❌ 暂不包含（OUT）
- BGM 匹配
- 转场特效
- 抖音链接下载
- 自定义剧本模板
- 可交互时间轴编辑

### 🔧 技术任务清单

**后端**
- [ ] FastAPI 项目脚手架 + Docker Compose 配置
- [ ] PostgreSQL 数据库设计（users / projects / scripts / clip_jobs）
- [ ] 用户注册/登录（JWT 鉴权）
- [ ] 会话服务：固定问题集状态机，存储答案，生成 Brief JSON
- [ ] 剧本服务：接入 LLM API，按口播格式生成初稿，版本存储
- [ ] 文件上传接口：接收视频文件，存 MinIO，提取元数据
- [ ] Celery 异步任务框架搭建（Redis broker）
- [ ] AI 剪辑任务：PySceneDetect 场景切割 → Whisper ASR → 生成剪辑方案 JSON
- [ ] 渲染任务：FFmpeg 拼接 + 字幕烧录 → 输出 MP4
- [ ] WebSocket 进度推送接口

**前端**
- [ ] Vue3 + Vite 项目初始化，配置路由（vue-router）+ 状态管理（Pinia）
- [ ] 登录/注册页
- [ ] 引导问答界面（进度条 + 题目渲染 + 答案提交）
- [ ] 剧本展示 + 纯文本编辑器
- [ ] 文件上传组件（拖拽 + 进度条）
- [ ] AI 剪辑结果展示（片段列表 + 字幕预览）
- [ ] WebSocket 监听任务进度
- [ ] 导出按钮 + 下载链接

### 🎯 验收标准
1. 用户完成 8 步问答，生成可编辑的口播文案
2. 上传一段 3 分钟视频，AI 自动切割为多个场景片段
3. 字幕准确率 ≥ 80%（普通话环境）
4. 从提交剪辑到获取下载链接，5 分钟内完成（3 分钟视频）
5. 导出 MP4 可在手机正常播放

### ⚠️ 风险点
| 风险 | 应对措施 |
|------|----------|
| Whisper 本地部署耗时 | 先接入云端 ASR API（腾讯云/阿里云）快速验证 |
| FFmpeg 渲染慢 | MVP 只支持小文件（<500MB），后续优化并发渲染 |
| LLM 生成质量不稳定 | 设计 Prompt 模板，加人工重新生成按钮 |

---

## 🚀 V1.0（第二阶段）— 完善剪辑能力

**周期**：4～6 周  
**目标**：剪辑体验升级，支持人工深度介入，剧本自定义模板，BGM + 转场

### ✅ 新增功能

| 功能模块 | 具体内容 |
|----------|----------|
| 可交互时间轴 | 拖动切点、删除/合并片段、支持缩放 |
| BGM 匹配 | Librosa 分析视频情绪 → 从曲库推荐 BGM，支持试听/替换 |
| 转场特效 | 内置 8 种转场（淡入淡出、叠化、推拉等），FFmpeg 实现 |
| 自定义剧本模板 | 用户可定义字段 + 排版，保存为个人模板 |
| 格式切换 | 分镜脚本 / 口播文案 / 标准剧本，三种内置格式 |
| 问答动态化 | LLM 根据前序答案动态生成下一问题（非固定题库）|
| 段落重写 | 剧本中选中某段，让 AI 按新要求重写 |
| 文件大小提升 | 支持最大 2GB 视频 |
| 版本历史 | 剪辑方案版本管理，支持回退 |

### 🔧 技术任务清单

**后端**
- [ ] LLM 动态问题生成：LangChain ConversationChain，上下文感知
- [ ] 剧本模板 CRUD API（用户自定义模板存储）
- [ ] Librosa 集成：视频音轨提取 → 节拍/情绪分析 → 曲库匹配
- [ ] BGM 曲库管理（初期内置 50 首，按情绪/风格标签）
- [ ] 剪辑方案版本管理（每次人工修改生成 snapshot）
- [ ] FFmpeg 转场合成支持（concat + xfade filter）
- [ ] 大文件分片上传（multipart upload）
- [ ] 段落重写 API：接受片段文本 + 修改指令 → LLM 输出

**前端**
- [ ] 时间轴组件开发（自研，基于 Canvas）：
  - 视频帧预览条
  - 可拖动的切点标记
  - 字幕轨道可视化
  - BGM 轨道显示
- [ ] 剧本模板编辑器（字段配置界面）
- [ ] BGM 面板（推荐列表 + 试听 + 替换）
- [ ] 转场选择 Panel
- [ ] 版本历史侧栏

### 🎯 验收标准
1. 用户可在时间轴上自由调整切点，结果实时反映在预览
2. BGM 推荐与视频情绪匹配度主观评分 ≥ 7/10
3. 自定义剧本模板保存、加载、切换流程无误
4. 转场效果正确渲染到导出成品
5. 动态问答流程（≥12 步）流畅无明显延迟

### ⚠️ 风险点
| 风险 | 应对措施 |
|------|----------|
| 时间轴组件开发复杂 | 先调研 wavesurfer.js / peaks.js 改造成本，必要时复用 |
| BGM 版权问题 | 初期只内置免费授权曲库（ccMixter / Free Music Archive）|
| 动态 LLM 问答延迟 | 流式输出（SSE）+ 加载动画改善体验 |

---

## 🎵 V1.5（第三阶段）— 接入抖音生态

**周期**：3～4 周  
**目标**：支持抖音链接一键导入，丰富剪辑风格模板库

### ✅ 新增功能

| 功能模块 | 具体内容 |
|----------|----------|
| 抖音链接下载 | 输入抖音分享链接，后台调用火山引擎 veVOD API 下载无水印视频 |
| 抖音视频分析 | 调用火山引擎视频理解 API 补充场景标签 |
| 剪辑风格模板库 | 预置「vlog / 美食 / 知识分享 / 带货 / 旅行」5 种风格 |
| 风格一键应用 | 选择风格模板，AI 自动套用对应的节奏、转场、字幕样式 |
| 字幕样式 | 支持字体、颜色、描边、位置自定义 |
| 批量导入 | 一次输入多个视频链接或上传多个文件 |

### 🔧 技术任务清单

**后端**
- [ ] 火山引擎 SDK 集成（volcengine-python-sdk）
- [ ] 抖音链接解析：HTTP 重定向跟踪 → 提取 video_id
- [ ] veVOD API 调用：GetPlayInfo 获取播放地址 → 异步下载
- [ ] 火山引擎内容理解 API（可选）：视频标签增强
- [ ] 剪辑风格模板 CRUD（风格 JSON 定义：节奏参数 + 转场类型 + 字幕配置）
- [ ] 字幕样式参数传递至 FFmpeg（ass/srt 格式 + 样式覆盖）
- [ ] 批量任务调度（并发 Celery 任务，限制并发数）

**前端**
- [ ] 链接输入框（支持识别抖音域名，显示抖音图标）
- [ ] 下载进度展示
- [ ] 风格模板选择界面（卡片式，带预览 GIF）
- [ ] 字幕样式编辑 Panel
- [ ] 批量素材管理界面

### 🎯 验收标准
1. 粘贴抖音分享链接，5 分钟内完成下载并进入剪辑流程
2. 应用风格模板后，导出视频符合该风格的视觉预期
3. 字幕样式自定义后正确渲染到成品

### ⚠️ 风险点
| 风险 | 应对措施 |
|------|----------|
| 抖音链接解析失效（平台反爬） | 火山引擎官方 API 作为正式通道，稳定性更高；备用人工上传 |
| veVOD API 费用 | 评估用量，设置下载次数限额 / 用户配额 |
| 批量任务资源占用 | Celery 并发数限制（max_concurrency），队列优先级 |

---

## 🧠 V2.0（第四阶段）— 智能化升级

**周期**：4～6 周  
**目标**：多模态理解、AI 自动评分剪辑方案、协作审核

### ✅ 新增功能

| 功能模块 | 具体内容 |
|----------|----------|
| 多模态联合分析 | 视觉 + 音频 + 字幕三轨联合分析，生成更精准的切点和情绪曲线 |
| AI 剪辑评分 | 对 AI 生成的多个剪辑方案打分（节奏感、视觉丰富度、信息密度），推荐最优解 |
| 多方案对比 | AI 同时生成 3 个不同风格剪辑方案，用户对比选择 |
| 协作功能 | 多人（创作者 + 编导）共享项目，标注批注，审核流程 |
| 智能 B-roll 推荐 | 根据口播文案内容，推荐插入对应的 B-roll 素材（需用户提供素材库）|
| 数据看板 | 项目历史统计：创作时长、AI 剪辑节省时间、常用风格等 |
| 剪辑方案导出 | 导出为 EDL / XML 格式，兼容 Premiere Pro / DaVinci Resolve |

### 🔧 技术任务清单

**后端**
- [ ] 多模态分析 Pipeline：视觉帧特征 + Mel 频谱 + ASR 文本 → 联合情绪曲线
- [ ] 剪辑方案评分模型（可以是规则引擎 + LLM 评判双轨）
- [ ] 多方案生成调度（并行 Celery 任务，3 个方案同时生成）
- [ ] 协作数据模型：project_members、comment_threads、review_status
- [ ] 协作 WebSocket：实时共享编辑状态（operational transform 或 CRDT 简化版）
- [ ] B-roll 匹配：文本语义向量 → 素材库向量检索（pgvector）
- [ ] EDL / XML 导出生成器
- [ ] 数据统计聚合接口

**前端**
- [ ] 多方案对比界面（并排展示时间轴 + 分数 + 特点说明）
- [ ] 协作功能：在线用户状态、批注标记、审核意见侧栏
- [ ] 情绪曲线可视化（叠加在时间轴上）
- [ ] 数据看板页面

### 🎯 验收标准
1. 多模态分析后，切点质量主观评分提升 ≥ 15%（与 MVP 对比）
2. AI 推荐最优方案被用户选择率 ≥ 60%
3. 协作功能：两人同时操作不发生数据冲突
4. 导出 EDL 可正确被 Premiere Pro 识别并导入

### ⚠️ 风险点
| 风险 | 应对措施 |
|------|----------|
| 多模态模型计算资源大 | 先用规则 + LLM 文字评判替代，模型方案作为后期优化 |
| 协作冲突处理复杂 | V2.0 用「最后写入胜出 + 操作日志」简化，CRDT 放 V3.0 |
| B-roll 匹配准确率 | 初期仅推荐候选列表，不自动插入 |

---

## 附录：数据库核心表设计（MVP）

```sql
-- 用户表
CREATE TABLE users (
    id UUID PRIMARY KEY,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 项目表
CREATE TABLE projects (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'draft',  -- draft/scripting/clipping/done
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 引导会话表
CREATE TABLE guide_sessions (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    answers JSONB,          -- 每步的答案
    brief JSONB,            -- 最终生成的创作简报
    step INTEGER DEFAULT 0,
    completed BOOLEAN DEFAULT FALSE,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 剧本版本表
CREATE TABLE scripts (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    version INTEGER DEFAULT 1,
    format VARCHAR(50),     -- voiceover / storyboard / screenplay
    content JSONB,          -- 剧本内容（按格式结构化）
    is_latest BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 视频素材表
CREATE TABLE videos (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    source VARCHAR(20),     -- local / douyin
    original_url TEXT,
    storage_path TEXT,      -- MinIO 路径
    duration FLOAT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

-- 剪辑任务表
CREATE TABLE clip_jobs (
    id UUID PRIMARY KEY,
    project_id UUID REFERENCES projects(id),
    video_id UUID REFERENCES videos(id),
    status VARCHAR(50) DEFAULT 'pending',  -- pending/processing/done/failed
    clip_plan JSONB,        -- AI 生成的剪辑方案
    progress INTEGER DEFAULT 0,
    output_path TEXT,       -- 成品存储路径
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);
```

---

*文档版本：v0.1 | 配套文档：architecture.md*
