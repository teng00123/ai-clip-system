<template>
  <div class="clip-page">
    <!-- Header -->
    <div class="clip-header">
      <button class="btn-back" @click="router.push(`/project/${projectId}/upload`)">← 上传</button>
      <span class="page-title">AI 剪辑</span>
      <div class="header-actions">
        <button
          v-if="canExport"
          class="btn-next"
          @click="goToExport"
        >导出 →</button>
      </div>
    </div>

    <div class="clip-body">

      <!-- ── 左主区 ── -->
      <div class="clip-main">

        <!-- 初始化中 -->
        <div v-if="initializing" class="splash">
          <div class="spinner"></div>
          <p class="splash-hint">加载中…</p>
        </div>

        <!-- 无可用视频 -->
        <div v-else-if="!videoList.length" class="splash">
          <div class="splash-icon">📹</div>
          <p class="splash-hint">请先上传视频再开始剪辑</p>
          <button class="btn-primary" @click="router.push(`/project/${projectId}/upload`)">
            去上传视频
          </button>
        </div>

        <!-- 有视频：选择 + 提交 -->
        <template v-else>

          <!-- 视频选择 -->
          <section class="card select-card">
            <div class="card-title">选择视频</div>
            <div class="video-options">
              <div
                v-for="v in videoList"
                :key="v.id"
                :class="['video-opt', { 'video-opt--active': selectedVideoId === v.id }]"
                @click="selectedVideoId = v.id"
              >
                <span class="vo-icon">🎞</span>
                <span class="vo-name">{{ v.filename }}</span>
                <span v-if="v.duration" class="vo-dur">{{ fmtDur(v.duration) }}</span>
                <span v-if="selectedVideoId === v.id" class="vo-check">✓</span>
              </div>
            </div>
          </section>

          <!-- 提交 / 状态区 -->
          <section class="card job-card">
            <!-- pending: 未提交 -->
            <template v-if="!clipStore.job">
              <div class="job-ready">
                <div class="ready-icon">✂️</div>
                <div class="ready-text">
                  <p class="ready-title">准备好了！</p>
                  <p class="ready-hint">AI 将根据剧本，从视频中剪出最精彩的片段。</p>
                </div>
              </div>
              <p v-if="submitErr" class="err-msg">{{ submitErr }}</p>
              <button
                class="btn-primary btn-submit"
                :disabled="!selectedVideoId || clipStore.loading"
                @click="handleSubmit"
              >
                <span v-if="clipStore.loading" class="mini-spin"></span>
                <span v-else>🚀 开始 AI 剪辑</span>
              </button>
            </template>

            <!-- processing: 进行中 -->
            <template v-else-if="isProcessing">
              <div class="job-running">
                <div class="running-header">
                  <div class="ai-pulse-sm">
                    <div class="pr-ring"></div>
                    <span class="pr-icon">✦</span>
                  </div>
                  <div>
                    <p class="running-title">剪辑进行中</p>
                    <p class="running-msg">{{ clipStore.progressMessage || 'AI 正在分析视频…' }}</p>
                  </div>
                </div>
                <div class="big-progress-track">
                  <div class="big-progress-fill" :style="{ width: clipStore.progress + '%' }"></div>
                </div>
                <div class="progress-row">
                  <span class="progress-pct">{{ clipStore.progress }}%</span>
                  <span class="progress-eta" v-if="etaText">预计剩余 {{ etaText }}</span>
                </div>
              </div>
            </template>

            <!-- done: 完成 -->
            <template v-else-if="isDone">
              <div class="job-done">
                <div class="done-badge">🎉</div>
                <div>
                  <p class="done-title">剪辑完成！</p>
                  <p class="done-hint">共生成 {{ clipStore.job?.clip_plan?.total_scenes ?? 0 }} 个片段</p>
                </div>
              </div>
            </template>

            <!-- failed -->
            <template v-else-if="isFailed">
              <div class="job-failed">
                <div class="failed-icon">❌</div>
                <div>
                  <p class="failed-title">剪辑失败</p>
                  <p class="failed-hint">{{ clipStore.job?.error_msg || '未知错误' }}</p>
                </div>
              </div>
              <button class="btn-ghost" @click="retryJob">重新剪辑</button>
            </template>
          </section>

          <!-- 时间轴编辑器（done 时展示） -->
          <section v-if="isDone && clipStore.job?.clip_plan?.segments?.length" class="card timeline-card">
            <div class="card-title">
              ✂ 时间轴编辑器
              <span class="segments-count">{{ clipStore.job.clip_plan.total_scenes }} 个片段</span>
              <span class="tl-hint">拖动切点调整剪辑范围</span>
            </div>
            <TimelineEditor
              :job-id="clipStore.job.id"
              :clip-plan="clipStore.job.clip_plan"
              @plan-updated="onPlanUpdated"
            />
          </section>

        </template>
      </div>

      <!-- ── 右侧边栏 ── -->
      <aside class="clip-sidebar">
        <!-- 任务状态卡 -->
        <div class="sidebar-card" v-if="clipStore.job">
          <div class="sidebar-title">📋 任务状态</div>
          <div :class="['status-pill', statusClass]">{{ statusLabel }}</div>
          <div class="meta-row">
            <span class="meta-k">任务 ID</span>
            <span class="meta-v mono">{{ clipStore.job.id.slice(0, 8) }}…</span>
          </div>
          <div class="meta-row" v-if="clipStore.job.clip_plan">
            <span class="meta-k">片段数</span>
            <span class="meta-v">{{ clipStore.job.clip_plan.total_scenes }}</span>
          </div>
          <div class="meta-row">
            <span class="meta-k">创建于</span>
            <span class="meta-v">{{ fmtDate(clipStore.job.created_at) }}</span>
          </div>
        </div>

        <!-- 历史任务 -->
        <div class="sidebar-card" v-if="historyJobs.length > 1">
          <div class="sidebar-title">🕐 历史任务</div>
          <div
            v-for="j in historyJobs.slice(0, 5)"
            :key="j.id"
            :class="['history-row', { 'history-row--active': clipStore.job?.id === j.id }]"
            @click="loadJob(j)"
          >
            <span :class="['h-dot', j.status]"></span>
            <span class="h-name">{{ fmtDate(j.created_at) }}</span>
            <span class="h-status">{{ statusLabelOf(j.status) }}</span>
          </div>
        </div>

        <!-- 导出卡 -->
        <div class="sidebar-card next-card" v-if="canExport">
          <div class="sidebar-title">✅ 下一步</div>
          <p class="next-hint">剪辑完成，可以下载或导出成品视频。</p>
          <button class="btn-primary btn-block" @click="goToExport">去导出 →</button>
        </div>

        <!-- tips -->
        <div class="sidebar-card tips-card" v-if="!clipStore.job || isProcessing">
          <div class="sidebar-title">💡 小贴士</div>
          <ul class="tips-list">
            <li>剪辑通常需要 1 ~ 3 分钟</li>
            <li>可关闭页面，稍后回来查看</li>
            <li>结果基于你的剧本生成</li>
          </ul>
        </div>
      </aside>

    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useClipStore } from '@/stores/clip'
import type { ClipJob, Video } from '@/types'
import * as videoApi from '@/api/videos'
import * as clipApi from '@/api/clips'
import TimelineEditor from '@/components/TimelineEditor.vue'

const route = useRoute()
const router = useRouter()
const clipStore = useClipStore()

const projectId = route.params.projectId as string
// optional jobId from route — used to resume a known job
const routeJobId = route.params.jobId as string | undefined

const initializing = ref(true)
const videoList = ref<Video[]>([])
const selectedVideoId = ref('')
const historyJobs = ref<ClipJob[]>([])
const submitErr = ref('')

// ── ETA timer ────────────────────────────────────────────────────────────────
const etaText = ref('')
let etaTimer: ReturnType<typeof setInterval> | null = null
let jobStartTime = 0

function startEta() {
  jobStartTime = Date.now()
  etaTimer = setInterval(() => {
    const p = clipStore.progress
    if (p <= 0 || p >= 100) { etaText.value = ''; return }
    const elapsed = (Date.now() - jobStartTime) / 1000
    const total = elapsed / (p / 100)
    const remaining = Math.max(0, Math.round(total - elapsed))
    etaText.value = remaining < 60 ? `${remaining} 秒` : `${Math.round(remaining / 60)} 分钟`
  }, 1000)
}
function stopEta() {
  if (etaTimer) { clearInterval(etaTimer); etaTimer = null }
  etaText.value = ''
}

// ── Computed ─────────────────────────────────────────────────────────────────
const isProcessing = computed(() =>
  clipStore.job?.status === 'pending' || clipStore.job?.status === 'processing'
)
const isDone    = computed(() => clipStore.job?.status === 'done')
const isFailed  = computed(() => clipStore.job?.status === 'failed')
const canExport = computed(() => isDone.value && !!clipStore.job?.output_path)

const statusLabel = computed(() => statusLabelOf(clipStore.job?.status ?? ''))
const statusClass = computed(() => clipStore.job?.status ?? 'pending')

function statusLabelOf(s: string) {
  return ({ pending: '等待中', processing: '处理中', done: '已完成', failed: '失败' })[s] ?? s
}

// ── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(async () => {
  try {
    const [vRes, jRes] = await Promise.all([
      videoApi.listVideos(projectId),
      clipApi.listProjectJobs(projectId),
    ])
    videoList.value = vRes.data
    historyJobs.value = jRes.data

    // pick selected video
    if (videoList.value.length) {
      selectedVideoId.value = videoList.value[0].id
    }

    // resume job: prefer routeJobId, else latest
    const targetJob = routeJobId
      ? jRes.data.find((j) => j.id === routeJobId) ?? jRes.data[0]
      : jRes.data[0]

    if (targetJob) {
      clipStore.job = targetJob
      clipStore.progress = targetJob.progress
      if (isProcessing.value) {
        clipStore.connectWs?.(targetJob.id)  // reconnect WS if method is exposed
        startEta()
      }
    }
  } catch { /* ignore */ }
  finally {
    initializing.value = false
  }
})

onBeforeUnmount(() => stopEta())

// watch for job completion
watch(isDone, (v) => { if (v) stopEta() })
watch(isFailed, (v) => { if (v) stopEta() })
watch(isProcessing, (v) => {
  if (v && etaTimer === null) startEta()
})

// ── Actions ──────────────────────────────────────────────────────────────────
async function handleSubmit() {
  if (!selectedVideoId.value || clipStore.loading) return
  submitErr.value = ''
  try {
    await clipStore.submitJob(projectId, selectedVideoId.value)
    historyJobs.value = (await clipApi.listProjectJobs(projectId)).data
    startEta()
  } catch (e: any) {
    submitErr.value = e?.response?.data?.detail || '提交失败，请重试'
  }
}

/** TimelineEditor 时间轴保存回调 */
function onPlanUpdated(plan: any) {
  if (clipStore.job) {
    clipStore.job.clip_plan = plan
  }
}

async function retryJob() {
  clipStore.reset()
  await handleSubmit()
}

function loadJob(j: ClipJob) {
  clipStore.job = j
  clipStore.progress = j.progress
  if (j.status === 'processing' || j.status === 'pending') {
    startEta()
  } else {
    stopEta()
  }
}

function goToExport() {
  if (!clipStore.job) return
  router.push(`/project/${projectId}/export/${clipStore.job.id}`)
}

// ── Formatters ────────────────────────────────────────────────────────────────
function fmtDur(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return m > 0 ? `${m}分${s.toString().padStart(2,'0')}秒` : `${s}秒`
}
function fmtSec(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m.toString().padStart(2,'0')}:${s.toString().padStart(2,'0')}`
}
function fmtDate(d: string) {
  return new Date(d).toLocaleString('zh-CN', { month:'2-digit', day:'2-digit', hour:'2-digit', minute:'2-digit' })
}
</script>

<style scoped>
.clip-page {
  min-height: 100vh;
  background: #0f1117;
  color: #e8eaf0;
  display: flex;
  flex-direction: column;
}

/* Header */
.clip-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-bottom: 1px solid #1e2130;
  flex-shrink: 0;
}
.btn-back {
  background: none; border: none; color: #7a82a0;
  cursor: pointer; font-size: 14px; padding: 4px 8px;
  border-radius: 6px; transition: color 0.2s;
}
.btn-back:hover { color: #e8eaf0; }
.page-title { font-size: 16px; font-weight: 600; flex: 1; }
.header-actions { display: flex; gap: 10px; }

/* Body */
.clip-body {
  flex: 1; display: flex; padding: 24px; gap: 20px; overflow: auto;
}
.clip-main {
  flex: 1; display: flex; flex-direction: column; gap: 16px; min-width: 0;
}

/* Splash */
.splash {
  flex: 1; display: flex; flex-direction: column;
  align-items: center; justify-content: center; gap: 16px; padding: 48px;
}
.splash-icon { font-size: 48px; }
.splash-hint { color: #7a82a0; font-size: 15px; }
.spinner {
  width: 36px; height: 36px;
  border: 3px solid #1e2130; border-top-color: #4f6ef7;
  border-radius: 50%; animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Cards */
.card {
  background: #14172b; border: 1px solid #2a2d45;
  border-radius: 12px; padding: 18px 20px;
}
.card-title {
  font-size: 13px; font-weight: 600; color: #7a82a0;
  text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 12px; display: flex; align-items: center; gap: 8px;
}
.segments-count {
  background: #1e2130; border-radius: 20px;
  padding: 1px 8px; font-size: 11px; color: #a0a8c0;
}
.tl-hint {
  font-size: 11px; color: #4a5070; font-style: italic;
  text-transform: none; letter-spacing: 0;
}
.timeline-card { padding: 14px 0 0; }
.timeline-card .card-title { padding: 0 16px 10px; border-bottom: 1px solid #1e2130; margin-bottom: 0; }

/* Video options */
.video-options { display: flex; flex-direction: column; gap: 8px; }
.video-opt {
  display: flex; align-items: center; gap: 10px;
  background: #0f1117; border: 1px solid #2a2d45;
  border-radius: 8px; padding: 10px 14px; cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.video-opt:hover { border-color: #4f6ef7; background: #141729; }
.video-opt--active { border-color: #4f6ef7; background: #1a2060; }
.vo-icon { font-size: 16px; }
.vo-name { flex: 1; font-size: 14px; color: #c8ccdd; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vo-dur { font-size: 12px; color: #7a82a0; flex-shrink: 0; }
.vo-check { color: #4f6ef7; font-weight: 700; flex-shrink: 0; }

/* Job card states */
.job-ready { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; }
.ready-icon { font-size: 36px; }
.ready-title { font-size: 16px; font-weight: 600; color: #e8eaf0; margin-bottom: 4px; }
.ready-hint { font-size: 13px; color: #7a82a0; }
.btn-submit { width: 100%; justify-content: center; padding: 14px; font-size: 16px; }

/* Processing */
.job-running { display: flex; flex-direction: column; gap: 14px; }
.running-header { display: flex; align-items: center; gap: 14px; }
.running-title { font-size: 15px; font-weight: 600; color: #e8eaf0; margin-bottom: 3px; }
.running-msg { font-size: 13px; color: #7a82a0; }
.ai-pulse-sm {
  position: relative; width: 44px; height: 44px;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.pr-ring {
  position: absolute; inset: 0; border-radius: 50%;
  border: 2px solid #4f6ef7;
  animation: pulse-ring 1.4s ease-out infinite;
}
@keyframes pulse-ring {
  0%   { transform: scale(0.7); opacity: 0.9; }
  100% { transform: scale(1.6); opacity: 0; }
}
.pr-icon { font-size: 18px; color: #4f6ef7; animation: ai-blink 1.2s ease-in-out infinite alternate; }
@keyframes ai-blink { from { opacity: 0.4; } to { opacity: 1; } }

.big-progress-track {
  height: 8px; background: #1e2130; border-radius: 4px; overflow: hidden;
}
.big-progress-fill {
  height: 100%; background: linear-gradient(90deg, #4f6ef7, #7c3aed);
  border-radius: 4px; transition: width 0.4s ease;
}
.progress-row { display: flex; justify-content: space-between; align-items: center; }
.progress-pct { font-size: 20px; font-weight: 700; color: #4f6ef7; }
.progress-eta { font-size: 13px; color: #7a82a0; }

/* Done / Failed */
.job-done, .job-failed {
  display: flex; align-items: center; gap: 16px;
}
.done-badge, .failed-icon { font-size: 36px; }
.done-title { font-size: 16px; font-weight: 600; color: #4ade80; margin-bottom: 3px; }
.done-hint { font-size: 13px; color: #7a82a0; }
.failed-title { font-size: 16px; font-weight: 600; color: #f87171; margin-bottom: 3px; }
.failed-hint { font-size: 13px; color: #7a82a0; }

/* Segments */
.segments-list { display: flex; flex-direction: column; gap: 10px; }
.segment-row {
  display: flex; gap: 12px; align-items: flex-start;
  background: #0f1117; border: 1px solid #1e2130;
  border-radius: 8px; padding: 10px 12px;
}
.seg-index {
  width: 22px; height: 22px; background: #2a2d45;
  border-radius: 50%; font-size: 11px; color: #7a82a0;
  display: flex; align-items: center; justify-content: center; flex-shrink: 0;
}
.seg-body { flex: 1; display: flex; flex-direction: column; gap: 4px; }
.seg-time { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.seg-ts { font-family: monospace; color: #c8ccdd; }
.seg-arrow { color: #4a5070; }
.seg-dur { color: #7a82a0; font-size: 12px; }
.seg-transcript { font-size: 13px; color: #a0a8c0; line-height: 1.5; margin: 0; }

/* Sidebar */
.clip-sidebar { width: 220px; flex-shrink: 0; display: flex; flex-direction: column; gap: 14px; }
.sidebar-card {
  background: #14172b; border: 1px solid #2a2d45;
  border-radius: 10px; padding: 14px;
  display: flex; flex-direction: column; gap: 8px;
}
.sidebar-title {
  font-size: 12px; font-weight: 600; color: #7a82a0;
  text-transform: uppercase; letter-spacing: 0.05em;
}
.status-pill {
  display: inline-flex; align-items: center;
  border-radius: 20px; padding: 3px 12px; font-size: 13px; font-weight: 600;
  align-self: flex-start;
}
.status-pill.pending   { background: #1e2130; color: #a0a8c0; }
.status-pill.processing{ background: #1a2060; color: #7ca4f7; }
.status-pill.done      { background: #0d2a1a; color: #4ade80; }
.status-pill.failed    { background: #2a0d0d; color: #f87171; }

.meta-row { display: flex; justify-content: space-between; font-size: 12px; }
.meta-k { color: #7a82a0; }
.meta-v { color: #c8ccdd; }
.mono { font-family: monospace; }

/* History */
.history-row {
  display: flex; align-items: center; gap: 8px;
  font-size: 12px; color: #a0a8c0; cursor: pointer;
  border-radius: 6px; padding: 4px 6px;
  transition: background 0.15s;
}
.history-row:hover { background: #1e2130; }
.history-row--active { background: #1a2060; color: #c8ccdd; }
.h-dot {
  width: 7px; height: 7px; border-radius: 50%; flex-shrink: 0;
}
.h-dot.pending   { background: #a0a8c0; }
.h-dot.processing{ background: #4f6ef7; }
.h-dot.done      { background: #4ade80; }
.h-dot.failed    { background: #f87171; }
.h-name { flex: 1; }
.h-status { color: #7a82a0; }

.next-card { border-color: #2a4a35; }
.next-hint { font-size: 13px; color: #7a82a0; line-height: 1.5; }
.tips-list {
  list-style: none; padding: 0; margin: 0;
  display: flex; flex-direction: column; gap: 6px;
  font-size: 12px; color: #7a82a0; line-height: 1.6;
}
.tips-list li::before { content: '·'; margin-right: 6px; color: #4f6ef7; }

/* Buttons */
.btn-primary {
  background: #4f6ef7; color: #fff; border: none; border-radius: 8px;
  padding: 8px 18px; font-size: 14px; font-weight: 600; cursor: pointer;
  display: flex; align-items: center; gap: 6px;
  transition: background 0.2s, opacity 0.2s;
}
.btn-primary:hover { background: #3a57e0; }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-block { width: 100%; justify-content: center; }
.btn-ghost {
  background: none; color: #7a82a0; border: 1px solid #2a2d45;
  border-radius: 8px; padding: 8px 16px; font-size: 14px; cursor: pointer;
  transition: color 0.2s, border-color 0.2s; align-self: flex-start;
}
.btn-ghost:hover { color: #c8ccdd; border-color: #4a5070; }
.btn-next {
  background: #1e2130; color: #c8ccdd; border: 1px solid #2a2d45;
  border-radius: 8px; padding: 8px 16px; font-size: 14px; cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.btn-next:hover { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }

.mini-spin {
  display: inline-block; width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3); border-top-color: #fff;
  border-radius: 50%; animation: spin 0.7s linear infinite;
}
.err-msg { font-size: 13px; color: #f87171; }
</style>
