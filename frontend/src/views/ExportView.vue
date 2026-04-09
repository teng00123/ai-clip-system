<template>
  <div class="export-page">
    <!-- Header -->
    <div class="export-header">
      <button class="btn-back" @click="router.push(`/project/${projectId}/clip/${jobId}`)">← 剪辑</button>
      <span class="page-title">导出成品</span>
      <button class="btn-ghost" @click="router.push('/dashboard')">回到项目列表</button>
    </div>

    <div class="export-body">

      <!-- ── 主区 ── -->
      <div class="export-main">

        <!-- loading -->
        <div v-if="loading" class="splash">
          <div class="spinner"></div>
          <p class="splash-hint">加载中…</p>
        </div>

        <!-- job not found / wrong state -->
        <div v-else-if="!job" class="splash">
          <div class="splash-icon">🔍</div>
          <p class="splash-hint">找不到剪辑任务，请返回重试。</p>
          <button class="btn-primary" @click="router.push(`/project/${projectId}/clip`)">返回剪辑页</button>
        </div>

        <div v-else-if="job.status !== 'done'" class="splash">
          <div class="splash-icon">⏳</div>
          <p class="splash-hint">剪辑尚未完成（当前状态：{{ statusLabel(job.status) }}）</p>
          <button class="btn-primary" @click="router.push(`/project/${projectId}/clip/${jobId}`)">返回查看进度</button>
        </div>

        <!-- main export UI -->
        <template v-else>

          <!-- 成功横幅 -->
          <div class="success-banner">
            <span class="banner-icon">🎬</span>
            <div class="banner-text">
              <p class="banner-title">成品已就绪！</p>
              <p class="banner-sub">共 {{ job.clip_plan?.total_scenes ?? 0 }} 个片段，可一键下载或分享。</p>
            </div>
          </div>

          <!-- 下载区 -->
          <div class="card download-card">
            <div class="card-title">📥 下载成品视频</div>

            <div class="download-meta">
              <div class="meta-item">
                <span class="meta-k">片段数</span>
                <span class="meta-v">{{ job.clip_plan?.total_scenes ?? '–' }}</span>
              </div>
              <div class="meta-item">
                <span class="meta-k">任务 ID</span>
                <span class="meta-v mono">{{ job.id.slice(0, 12) }}…</span>
              </div>
              <div class="meta-item">
                <span class="meta-k">完成时间</span>
                <span class="meta-v">{{ fmtDate(job.updated_at) }}</span>
              </div>
            </div>

            <div class="download-actions">
              <button
                class="btn-download"
                :disabled="downloading"
                @click="handleDownload"
              >
                <span v-if="downloading" class="mini-spin"></span>
                <span v-else>⬇️ 下载视频</span>
              </button>
              <button class="btn-copy" @click="handleCopyLink">
                {{ copied ? '✓ 已复制' : '🔗 复制链接' }}
              </button>
            </div>

            <p v-if="downloadErr" class="err-msg">{{ downloadErr }}</p>
            <p class="download-note">下载链接有效期 24 小时，过期后需重新获取。</p>
          </div>

          <!-- 片段列表 -->
          <div class="card segments-card" v-if="job.clip_plan?.segments.length">
            <div class="card-title">
              片段预览
              <span class="seg-count">{{ job.clip_plan.total_scenes }} 个</span>
            </div>
            <div class="segments-list">
              <div
                v-for="seg in job.clip_plan.segments"
                :key="seg.id"
                class="seg-row"
              >
                <div class="seg-num">{{ seg.id }}</div>
                <div class="seg-body">
                  <div class="seg-time">
                    <span class="seg-ts">{{ fmtSec(seg.start) }}</span>
                    <span class="seg-arr">→</span>
                    <span class="seg-ts">{{ fmtSec(seg.end) }}</span>
                    <span class="seg-dur">{{ fmtSec(seg.duration) }}</span>
                  </div>
                  <p v-if="seg.transcript" class="seg-transcript">{{ seg.transcript }}</p>
                </div>
              </div>
            </div>
          </div>

          <!-- 下一步操作 -->
          <div class="card next-steps-card">
            <div class="card-title">🚀 继续创作</div>
            <div class="next-grid">
              <button class="next-item" @click="router.push(`/project/${projectId}/script`)">
                <span class="ni-icon">📝</span>
                <span class="ni-label">修改剧本</span>
                <span class="ni-hint">调整内容后重新剪辑</span>
              </button>
              <button class="next-item" @click="router.push(`/project/${projectId}/upload`)">
                <span class="ni-icon">🎥</span>
                <span class="ni-label">换一段视频</span>
                <span class="ni-hint">用不同素材重新剪辑</span>
              </button>
              <button class="next-item" @click="router.push('/dashboard')">
                <span class="ni-icon">📁</span>
                <span class="ni-label">新建项目</span>
                <span class="ni-hint">开始下一个创作</span>
              </button>
            </div>
          </div>

        </template>
      </div>

      <!-- ── 侧边栏 ── -->
      <aside class="export-sidebar" v-if="job?.status === 'done'">

        <div class="sidebar-card">
          <div class="sidebar-title">📊 任务信息</div>
          <div class="s-meta-row"><span class="sm-k">状态</span>
            <span class="status-done">已完成</span></div>
          <div class="s-meta-row"><span class="sm-k">项目</span>
            <span class="sm-v">{{ projectId.slice(0,8) }}…</span></div>
          <div class="s-meta-row"><span class="sm-k">视频</span>
            <span class="sm-v">{{ job.video_id.slice(0,8) }}…</span></div>
        </div>

        <div class="sidebar-card share-card">
          <div class="sidebar-title">📤 分享提示</div>
          <ul class="tips-list">
            <li>建议上传至抖音 / 视频号</li>
            <li>添加字幕效果更佳</li>
            <li>发布前检查音量和画质</li>
            <li>配合封面图提升点击率</li>
          </ul>
        </div>

        <div class="sidebar-card">
          <div class="sidebar-title">♻️ 重新剪辑</div>
          <p class="recut-hint">想换个风格？可以修改剧本再来一次。</p>
          <button
            class="btn-recut"
            @click="router.push(`/project/${projectId}/clip`)"
          >重新剪辑</button>
        </div>
      </aside>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { ClipJob } from '@/types'
import * as clipApi from '@/api/clips'

const route  = useRoute()
const router = useRouter()

const projectId = route.params.projectId as string
const jobId     = route.params.jobId as string

const loading     = ref(true)
const job         = ref<ClipJob | null>(null)
const downloading = ref(false)
const downloadErr = ref('')
const copied      = ref(false)
let   downloadUrl = ''   // cached presigned URL

onMounted(async () => {
  try {
    const res = await clipApi.getClipJob(jobId)
    job.value = res.data
  } catch {
    job.value = null
  } finally {
    loading.value = false
  }
})

async function getUrl(): Promise<string> {
  if (downloadUrl) return downloadUrl
  const res = await clipApi.getDownloadUrl(jobId)
  downloadUrl = res.data.url
  return downloadUrl
}

async function handleDownload() {
  if (downloading.value) return
  downloadErr.value = ''
  downloading.value = true
  try {
    const url = await getUrl()
    // trigger browser download via hidden anchor
    const a = document.createElement('a')
    a.href = url
    a.download = `clip-${jobId.slice(0, 8)}.mp4`
    a.target = '_blank'
    a.rel = 'noopener'
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
  } catch (e: any) {
    downloadErr.value = e?.response?.data?.detail || '获取下载链接失败，请重试'
  } finally {
    downloading.value = false
  }
}

async function handleCopyLink() {
  try {
    const url = await getUrl()
    await navigator.clipboard.writeText(url)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch {
    downloadErr.value = '复制失败，请手动复制链接'
  }
}

function statusLabel(s: string) {
  return ({ pending: '等待中', processing: '处理中', done: '已完成', failed: '失败' })[s] ?? s
}

function fmtSec(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`
}

function fmtDate(d: string) {
  return new Date(d).toLocaleString('zh-CN', {
    month: '2-digit', day: '2-digit',
    hour:  '2-digit', minute: '2-digit',
  })
}
</script>

<style scoped>
.export-page {
  min-height: 100vh;
  background: #0f1117;
  color: #e8eaf0;
  display: flex;
  flex-direction: column;
}

/* Header */
.export-header {
  display: flex; align-items: center; gap: 12px;
  padding: 14px 24px; border-bottom: 1px solid #1e2130; flex-shrink: 0;
}
.btn-back {
  background: none; border: none; color: #7a82a0;
  cursor: pointer; font-size: 14px; padding: 4px 8px;
  border-radius: 6px; transition: color 0.2s;
}
.btn-back:hover { color: #e8eaf0; }
.page-title { font-size: 16px; font-weight: 600; flex: 1; }

/* Body */
.export-body {
  flex: 1; display: flex; padding: 24px; gap: 20px; overflow: auto;
}
.export-main {
  flex: 1; display: flex; flex-direction: column; gap: 18px; min-width: 0;
}

/* Splash */
.splash {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px; padding: 60px;
}
.splash-icon { font-size: 48px; }
.splash-hint { color: #7a82a0; font-size: 15px; }
.spinner {
  width: 36px; height: 36px;
  border: 3px solid #1e2130; border-top-color: #4f6ef7;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Success banner */
.success-banner {
  display: flex; align-items: center; gap: 16px;
  background: linear-gradient(135deg, #0d2a1a 0%, #0a1a30 100%);
  border: 1px solid #2a4a35;
  border-radius: 14px; padding: 20px 24px;
}
.banner-icon { font-size: 40px; }
.banner-title { font-size: 18px; font-weight: 700; color: #4ade80; margin-bottom: 4px; }
.banner-sub   { font-size: 13px; color: #7a82a0; }

/* Cards */
.card {
  background: #14172b; border: 1px solid #2a2d45;
  border-radius: 12px; padding: 18px 20px;
  display: flex; flex-direction: column; gap: 14px;
}
.card-title {
  font-size: 13px; font-weight: 600; color: #7a82a0;
  text-transform: uppercase; letter-spacing: 0.06em;
  display: flex; align-items: center; gap: 8px;
}
.seg-count {
  background: #1e2130; border-radius: 20px;
  padding: 1px 8px; font-size: 11px; color: #a0a8c0;
}

/* Download card */
.download-meta {
  display: flex; flex-wrap: wrap; gap: 16px;
}
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-k { font-size: 11px; color: #7a82a0; text-transform: uppercase; letter-spacing: 0.05em; }
.meta-v { font-size: 14px; color: #c8ccdd; }
.mono { font-family: monospace; }

.download-actions {
  display: flex; gap: 10px; flex-wrap: wrap;
}
.btn-download {
  background: linear-gradient(135deg, #4f6ef7, #7c3aed);
  color: #fff; border: none; border-radius: 10px;
  padding: 12px 28px; font-size: 15px; font-weight: 700;
  cursor: pointer; display: flex; align-items: center; gap: 8px;
  transition: opacity 0.2s, transform 0.15s;
}
.btn-download:hover:not(:disabled) { opacity: 0.88; transform: translateY(-1px); }
.btn-download:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-copy {
  background: #1e2130; color: #c8ccdd;
  border: 1px solid #2a2d45; border-radius: 10px;
  padding: 12px 22px; font-size: 15px; font-weight: 600;
  cursor: pointer; transition: background 0.2s, color 0.2s;
}
.btn-copy:hover { background: #2a2d45; }
.download-note { font-size: 12px; color: #4a5070; }

/* Segments */
.segments-list { display: flex; flex-direction: column; gap: 8px; }
.seg-row {
  display: flex; gap: 12px; align-items: flex-start;
  background: #0f1117; border: 1px solid #1e2130;
  border-radius: 8px; padding: 10px 12px;
}
.seg-num {
  width: 22px; height: 22px; background: #2a2d45;
  border-radius: 50%; font-size: 11px; color: #7a82a0;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.seg-body { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.seg-time { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.seg-ts { font-family: monospace; color: #c8ccdd; }
.seg-arr { color: #4a5070; }
.seg-dur { color: #7a82a0; font-size: 12px; margin-left: 4px; }
.seg-transcript { font-size: 13px; color: #a0a8c0; line-height: 1.5; margin: 0; }

/* Next steps */
.next-grid {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px;
}
.next-item {
  background: #0f1117; border: 1px solid #2a2d45;
  border-radius: 10px; padding: 14px 12px;
  display: flex; flex-direction: column; align-items: center; gap: 6px;
  cursor: pointer; transition: border-color 0.2s, background 0.2s;
  text-align: center;
}
.next-item:hover { border-color: #4f6ef7; background: #141729; }
.ni-icon  { font-size: 24px; }
.ni-label { font-size: 13px; font-weight: 600; color: #c8ccdd; }
.ni-hint  { font-size: 11px; color: #7a82a0; line-height: 1.4; }

/* Sidebar */
.export-sidebar {
  width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 14px;
}
.sidebar-card {
  background: #14172b; border: 1px solid #2a2d45;
  border-radius: 10px; padding: 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.sidebar-title {
  font-size: 12px; font-weight: 600; color: #7a82a0;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.s-meta-row { display: flex; justify-content: space-between; align-items: center; font-size: 12px; }
.sm-k { color: #7a82a0; }
.sm-v { color: #c8ccdd; font-family: monospace; }
.status-done { color: #4ade80; font-weight: 600; font-size: 12px; }

.tips-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 6px;
  font-size: 12px; color: #7a82a0; line-height: 1.6;
}
.tips-list li::before { content: '·'; margin-right: 6px; color: #4f6ef7; }

.recut-hint { font-size: 12px; color: #7a82a0; line-height: 1.5; }
.btn-recut {
  background: none; border: 1px solid #2a2d45; color: #a0a8c0;
  border-radius: 8px; padding: 7px 14px; font-size: 13px;
  cursor: pointer; transition: color 0.2s, border-color 0.2s; align-self: flex-start;
}
.btn-recut:hover { color: #c8ccdd; border-color: #4a5070; }

/* Shared buttons */
.btn-primary {
  background: #4f6ef7; color: #fff; border: none; border-radius: 8px;
  padding: 8px 18px; font-size: 14px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: background 0.2s;
}
.btn-primary:hover { background: #3a57e0; }
.btn-ghost {
  background: none; color: #7a82a0; border: 1px solid #2a2d45;
  border-radius: 8px; padding: 7px 14px; font-size: 14px; cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.btn-ghost:hover { color: #c8ccdd; border-color: #4a5070; }

.mini-spin {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
.err-msg { font-size: 13px; color: #f87171; }
</style>
