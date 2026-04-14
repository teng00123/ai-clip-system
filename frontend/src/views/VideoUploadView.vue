<template>
  <div class="upload-page">
    <!-- Header -->
    <div class="upload-header">
      <button class="btn-back" @click="router.push(`/project/${projectId}/script`)">← {{ t('nav.step2') }}</button>
      <span class="page-title">{{ t('video.title') }}</span>
      <button
        class="btn-next"
        :disabled="!uploadedVideo"
        @click="goToClip"
      >{{ t('video.startClip') }} →</button>
    </div>

    <div class="upload-body">

      <!-- ── 左栏：上传区 ── -->
      <div class="upload-main">

        <!-- 上传完成态 -->
        <div v-if="uploadedVideo" class="uploaded-card">
          <div class="uploaded-icon">🎬</div>
          <div class="uploaded-info">
            <p class="uploaded-filename">{{ uploadedVideo.filename }}</p>
            <p class="uploaded-meta">
              <span v-if="uploadedVideo.duration">{{ t('video.duration') }} {{ formatDuration(uploadedVideo.duration) }}</span>
              <span class="dot" v-if="uploadedVideo.duration"> · </span>
              <span class="uploaded-ok">✓ {{ t('video.uploadComplete') }}</span>
            </p>
          </div>
          <button class="btn-ghost btn-sm" @click="resetUpload">{{ t('video.changeFile') }}</button>
        </div>

        <!-- 拖拽 / 点选区 -->
        <div
          v-else
          :class="['drop-zone', { 'drop-zone--active': dragging, 'drop-zone--error': fileErr }]"
          @dragenter.prevent="dragging = true"
          @dragover.prevent="dragging = true"
          @dragleave.prevent="dragging = false"
          @drop.prevent="onDrop"
          @click="fileInput?.click()"
        >
          <input
            ref="fileInput"
            type="file"
            accept="video/mp4,video/quicktime,video/x-msvideo,video/avi"
            class="hidden-input"
            @change="onFileSelect"
          />

          <div v-if="!uploading" class="drop-content">
            <div class="drop-icon">📁</div>
            <p class="drop-label">{{ t('video.dragHint') }}</p>
            <p class="drop-hint">{{ t('video.clickHint') }}</p>
            <p class="drop-formats">{{ t('video.formats') }}</p>
          </div>

          <!-- 上传进度 -->
          <div v-else class="upload-progress-wrap">
            <div class="progress-filename">{{ pendingFile?.name }}</div>
            <div class="progress-bar-track">
              <div class="progress-bar-fill" :style="{ width: uploadProgress + '%' }"></div>
            </div>
            <div class="progress-pct">{{ uploadProgress }}%</div>
            <button class="btn-cancel" @click.stop="cancelUpload">{{ t('common.cancel') }}</button>
          </div>
        </div>

        <p v-if="fileErr" class="err-msg">{{ fileErr }}</p>

        <!-- 已上传列表 -->
        <div v-if="videoList.length > 0" class="video-list">
          <div class="list-label">{{ t('video.uploadedList') }}</div>
          <div
            v-for="v in videoList"
            :key="v.id"
            :class="['video-row', { 'video-row--selected': uploadedVideo?.id === v.id }]"
            @click="selectExisting(v)"
          >
            <span class="video-row-icon">🎞</span>
            <span class="video-row-name">{{ v.filename }}</span>
            <span v-if="v.duration" class="video-row-dur">{{ formatDuration(v.duration) }}</span>
            <span v-if="uploadedVideo?.id === v.id" class="selected-mark">✓</span>
          </div>
        </div>
      </div>

      <!-- ── 右栏：说明 ── -->
      <aside class="upload-sidebar">
        <div class="sidebar-card">
          <div class="sidebar-title">📋 {{ t('video.requirements') }}</div>
          <ul class="req-list">
            <li>{{ t('video.reqFormat') }}</li>
            <li>{{ t('video.reqSize') }}</li>
            <li>{{ t('video.reqRatio') }}</li>
            <li>{{ t('video.reqResolution') }}</li>
          </ul>
        </div>

        <div class="sidebar-card tips-card">
          <div class="sidebar-title">💡 拍摄建议</div>
          <ul class="tips-list">
            <li>保持画面稳定，减少抖动</li>
            <li>光线充足，避免逆光</li>
            <li>声音清晰，背景噪音低</li>
            <li>单个镜头不超过 3 分钟</li>
          </ul>
        </div>

        <div v-if="uploadedVideo" class="sidebar-card next-card">
          <div class="sidebar-title">✅ 下一步</div>
          <p class="next-hint">视频已就位，AI 将根据剧本自动剪辑精华片段。</p>
          <button class="btn-primary btn-block" @click="goToClip">开始 AI 剪辑 →</button>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import type { Video } from '@/types'
import * as videoApi from '@/api/videos'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const projectId = route.params.projectId as string

const MAX_SIZE = 500 * 1024 * 1024
const ALLOWED_TYPES = new Set(['video/mp4', 'video/quicktime', 'video/x-msvideo', 'video/avi'])

const fileInput = ref<HTMLInputElement | null>(null)
const dragging = ref(false)
const uploading = ref(false)
const uploadProgress = ref(0)
const uploadedVideo = ref<Video | null>(null)
const pendingFile = ref<File | null>(null)
const fileErr = ref('')
const videoList = ref<Video[]>([])
let abortController: AbortController | null = null

onMounted(async () => {
  try {
    const res = await videoApi.listVideos(projectId)
    videoList.value = res.data
    if (res.data.length > 0) {
      uploadedVideo.value = res.data[0]
    }
  } catch { /* no videos yet */ }
})

function validate(file: File): string {
  if (!ALLOWED_TYPES.has(file.type)) return `不支持的格式：${file.type || '未知'}，请上传 MP4 / MOV / AVI`
  if (file.size > MAX_SIZE) return `文件过大（${formatSize(file.size)}），最大 500 MB`
  return ''
}

function onFileSelect(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (file) startUpload(file)
  target.value = ''
}

function onDrop(e: DragEvent) {
  dragging.value = false
  const file = e.dataTransfer?.files[0]
  if (file) startUpload(file)
}

async function startUpload(file: File) {
  fileErr.value = ''
  const err = validate(file)
  if (err) { fileErr.value = err; return }

  pendingFile.value = file
  uploading.value = true
  uploadProgress.value = 0
  abortController = new AbortController()

  try {
    const res = await videoApi.uploadVideo(projectId, file, (p) => {
      uploadProgress.value = p
    })
    uploadedVideo.value = res.data
    videoList.value = [res.data, ...videoList.value.filter((v) => v.id !== res.data.id)]
  } catch (e: any) {
    if (e?.code === 'ERR_CANCELED') return
    fileErr.value = e?.response?.data?.detail || '上传失败，请重试'
  } finally {
    uploading.value = false
    pendingFile.value = null
  }
}

function cancelUpload() {
  abortController?.abort()
  uploading.value = false
  uploadProgress.value = 0
  pendingFile.value = null
}

function resetUpload() {
  uploadedVideo.value = null
  fileErr.value = ''
}

function selectExisting(v: Video) {
  uploadedVideo.value = v
  fileErr.value = ''
}

function goToClip() {
  if (!uploadedVideo.value) return
  router.push(`/project/${projectId}/clip`)
}

function formatDuration(sec: number) {
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return m > 0 ? `${m}分${s.toString().padStart(2, '0')}秒` : `${s}秒`
}

function formatSize(bytes: number) {
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}
</script>

<style scoped>
.upload-page {
  min-height: 100vh;
  background: #0f1117;
  color: #e8eaf0;
  display: flex;
  flex-direction: column;
}

/* Header */
.upload-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 14px 24px;
  border-bottom: 1px solid #1e2130;
  flex-shrink: 0;
}
.btn-back {
  background: none;
  border: none;
  color: #7a82a0;
  cursor: pointer;
  font-size: 14px;
  padding: 4px 8px;
  border-radius: 6px;
  transition: color 0.2s;
}
.btn-back:hover { color: #e8eaf0; }
.page-title { font-size: 16px; font-weight: 600; flex: 1; }

/* Body */
.upload-body {
  flex: 1;
  display: flex;
  padding: 28px 24px;
  gap: 24px;
  overflow: auto;
}
.upload-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 20px;
  min-width: 0;
}

/* Drop zone */
.drop-zone {
  border: 2px dashed #2a2d45;
  border-radius: 14px;
  padding: 48px 32px;
  text-align: center;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  background: #14172b;
  user-select: none;
}
.drop-zone:hover,
.drop-zone--active {
  border-color: #4f6ef7;
  background: #16193a;
}
.drop-zone--error { border-color: #f87171; }

.hidden-input { display: none; }

.drop-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}
.drop-icon { font-size: 48px; }
.drop-label { font-size: 16px; font-weight: 600; color: #c8ccdd; }
.drop-hint { font-size: 13px; color: #7a82a0; }
.drop-formats { font-size: 12px; color: #4a5070; margin-top: 4px; }

/* Upload progress */
.upload-progress-wrap {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
}
.progress-filename {
  font-size: 13px;
  color: #a0a8c0;
  max-width: 360px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.progress-bar-track {
  width: 100%;
  max-width: 360px;
  height: 6px;
  background: #1e2130;
  border-radius: 3px;
  overflow: hidden;
}
.progress-bar-fill {
  height: 100%;
  background: linear-gradient(90deg, #4f6ef7, #7c3aed);
  border-radius: 3px;
  transition: width 0.2s ease;
}
.progress-pct { font-size: 14px; font-weight: 600; color: #4f6ef7; }
.btn-cancel {
  background: none;
  border: 1px solid #2a2d45;
  color: #7a82a0;
  border-radius: 6px;
  padding: 5px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.btn-cancel:hover { color: #f87171; border-color: #f87171; }

/* Uploaded card */
.uploaded-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #14172b;
  border: 1px solid #2a4a35;
  border-radius: 12px;
  padding: 16px 20px;
}
.uploaded-icon { font-size: 32px; }
.uploaded-info { flex: 1; min-width: 0; }
.uploaded-filename {
  font-size: 15px;
  font-weight: 600;
  color: #e8eaf0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.uploaded-meta {
  font-size: 13px;
  color: #7a82a0;
  margin-top: 4px;
}
.dot { margin: 0 4px; }
.uploaded-ok { color: #4ade80; }

/* Video list */
.video-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.list-label {
  font-size: 12px;
  font-weight: 600;
  color: #7a82a0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  padding: 0 2px;
}
.video-row {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #14172b;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  padding: 10px 14px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.video-row:hover { border-color: #4f6ef7; background: #16193a; }
.video-row--selected { border-color: #4f6ef7; background: #1a2060; }
.video-row-icon { font-size: 16px; }
.video-row-name {
  flex: 1;
  font-size: 14px;
  color: #c8ccdd;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.video-row-dur { font-size: 12px; color: #7a82a0; flex-shrink: 0; }
.selected-mark { color: #4f6ef7; font-size: 14px; font-weight: 700; flex-shrink: 0; }

/* Sidebar */
.upload-sidebar {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.sidebar-card {
  background: #14172b;
  border: 1px solid #2a2d45;
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: #7a82a0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.req-list, .tips-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 13px;
  color: #a0a8c0;
  line-height: 1.5;
}
.req-list li::before, .tips-list li::before {
  content: '·';
  margin-right: 6px;
  color: #4f6ef7;
}
.next-card { border-color: #2a4a35; }
.next-hint { font-size: 13px; color: #7a82a0; line-height: 1.5; }
.btn-block { width: 100%; justify-content: center; }

/* Buttons */
.btn-primary {
  background: #4f6ef7;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: background 0.2s, opacity 0.2s;
}
.btn-primary:hover { background: #3a57e0; }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-ghost {
  background: none;
  color: #7a82a0;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.btn-ghost:hover { color: #c8ccdd; border-color: #4a5070; }
.btn-ghost.btn-sm { padding: 5px 12px; font-size: 13px; }
.btn-next {
  background: #1e2130;
  color: #c8ccdd;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s, border-color 0.2s;
}
.btn-next:hover:not(:disabled) { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }
.btn-next:disabled { opacity: 0.35; cursor: not-allowed; }

/* Error */
.err-msg { font-size: 13px; color: #f87171; }
</style>
