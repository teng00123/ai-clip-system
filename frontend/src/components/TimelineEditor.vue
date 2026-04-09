<template>
  <div class="timeline-root" ref="rootEl">
    <!-- Toolbar -->
    <div class="tl-toolbar">
      <div class="tl-zoom-group">
        <span class="tl-label">缩放</span>
        <button
          v-for="z in ZOOM_LEVELS"
          :key="z.label"
          :class="['tl-zoom-btn', { active: zoomLevel === z.value }]"
          @click="setZoom(z.value)"
        >{{ z.label }}</button>
      </div>
      <div class="tl-info">
        <span v-if="selectedSegId !== null" class="tl-sel-info">
          ✂ 片段 {{ selectedSegId }}：{{ fmtSec(editSegments.find(s => s.id === selectedSegId)?.start ?? 0) }} → {{ fmtSec(editSegments.find(s => s.id === selectedSegId)?.end ?? 0) }}
          <span class="tl-dur">({{ fmtSec((editSegments.find(s => s.id === selectedSegId)?.end ?? 0) - (editSegments.find(s => s.id === selectedSegId)?.start ?? 0)) }})</span>
        </span>
        <span v-else class="tl-sel-hint">点击片段选中</span>
      </div>
      <div class="tl-actions">
        <button
          class="tl-btn-del"
          :disabled="selectedSegId === null"
          @click="deleteSelected"
          title="删除选中片段"
        >🗑 删除</button>
        <button
          class="tl-btn-save"
          :disabled="!dirty || saving"
          @click="savePlan"
          title="保存方案到服务器"
        >
          <span v-if="saving" class="mini-spin"></span>
          <span v-else>{{ dirty ? '💾 保存方案' : '✓ 已保存' }}</span>
        </button>
      </div>
    </div>

    <!-- Canvas area -->
    <div class="tl-canvas-wrap" ref="canvasWrap" @wheel.prevent="onWheel">
      <canvas
        ref="canvasEl"
        class="tl-canvas"
        @mousedown="onMouseDown"
        @mousemove="onMouseMove"
        @mouseup="onMouseUp"
        @mouseleave="onMouseLeave"
        @click="onCanvasClick"
      ></canvas>
      <!-- Playhead (CSS, positioned absolutely over canvas) -->
      <div
        class="tl-playhead"
        :style="{ left: playheadX + 'px' }"
        @mousedown.stop="startDragPlayhead"
      >
        <div class="tl-playhead-head"></div>
        <div class="tl-playhead-line"></div>
      </div>
    </div>

    <!-- Subtitle edit inline panel (appears below canvas when subtitle row clicked) -->
    <transition name="sub-panel">
      <div v-if="editingSubtitle !== null" class="tl-sub-edit-panel">
        <label class="sub-edit-label">编辑字幕（片段 {{ editingSubtitle.segId }}）</label>
        <div class="sub-edit-row">
          <textarea
            v-model="editingSubtitle.text"
            class="sub-edit-input"
            rows="2"
            placeholder="字幕文本…"
            @keydown.escape="closeSubtitleEdit"
          ></textarea>
          <div class="sub-edit-actions">
            <button class="tl-btn-sm" @click="closeSubtitleEdit">取消</button>
            <button class="tl-btn-sm tl-btn-sm--primary" @click="applySubtitleEdit">应用</button>
          </div>
        </div>
      </div>
    </transition>

    <!-- Segment list mini table -->
    <div class="tl-seg-list">
      <div class="tl-seg-list-head">
        <span>片段</span><span>入点</span><span>出点</span><span>时长</span><span>字幕</span><span></span>
      </div>
      <div
        v-for="seg in editSegments"
        :key="seg.id"
        :class="['tl-seg-row', { 'tl-seg-row--sel': selectedSegId === seg.id }]"
        @click="selectedSegId = seg.id"
      >
        <span class="seg-num">{{ seg.id }}</span>
        <span>{{ fmtSec(seg.start) }}</span>
        <span>{{ fmtSec(seg.end) }}</span>
        <span class="seg-dur">{{ fmtSec(seg.end - seg.start) }}</span>
        <span class="seg-transcript">{{ seg.transcript || '—' }}</span>
        <button class="tl-icon-btn" @click.stop="openSubtitleEdit(seg)" title="编辑字幕">✏</button>
      </div>
    </div>

    <!-- Error -->
    <p v-if="saveErr" class="tl-err">{{ saveErr }}</p>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import * as clipApi from '@/api/clips'

// ── Props ──────────────────────────────────────────────────────────────────────
interface Segment {
  id: number
  start: number
  end: number
  duration: number
  transcript: string
}
interface ClipPlan {
  segments: Segment[]
  total_scenes: number
  total_duration: number
}

const props = defineProps<{
  jobId: string
  clipPlan: ClipPlan
}>()

const emit = defineEmits<{
  (e: 'planUpdated', plan: ClipPlan): void
}>()

// ── Zoom levels ───────────────────────────────────────────────────────────────
const ZOOM_LEVELS = [
  { label: '概览', value: 1 },
  { label: '30s', value: 2 },
  { label: '10s', value: 5 },
] as const
type ZoomValue = 1 | 2 | 5
const zoomLevel = ref<ZoomValue>(1)

// ── State ─────────────────────────────────────────────────────────────────────
const rootEl = ref<HTMLElement | null>(null)
const canvasEl = ref<HTMLCanvasElement | null>(null)
const canvasWrap = ref<HTMLElement | null>(null)

// Working copy of segments (mutable)
const editSegments = ref<Segment[]>([])

const dirty = ref(false)
const saving = ref(false)
const saveErr = ref('')
const selectedSegId = ref<number | null>(null)
const playheadSec = ref(0)
const playheadX = ref(0)

// Drag state for segment boundaries
interface DragState {
  active: boolean
  segId: number
  side: 'left' | 'right'   // which edge being dragged
  startX: number
  origValue: number
}
const drag = reactive<DragState>({ active: false, segId: -1, side: 'left', startX: 0, origValue: 0 })

// Subtitle inline editor
interface SubEdit {
  segId: number
  text: string
}
const editingSubtitle = ref<SubEdit | null>(null)

// ── Derived constants ──────────────────────────────────────────────────────────
const totalDuration = computed(() =>
  editSegments.value.length ? Math.max(...editSegments.value.map(s => s.end)) : 60
)

// Layout constants (rows)
const ROW_RULER_H  = 24
const ROW_SEG_H    = 44
const ROW_SUB_H    = 28
const CANVAS_H     = ROW_RULER_H + ROW_SEG_H + ROW_SUB_H + 12

// Palette for segments (cycle)
const SEG_COLORS = ['#4f6ef7', '#7c3aed', '#0ea5e9', '#059669', '#d97706', '#dc2626']

function segColor(i: number, alpha = 1) {
  const hex = SEG_COLORS[i % SEG_COLORS.length]
  if (alpha === 1) return hex
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return `rgba(${r},${g},${b},${alpha})`
}

// ── Coordinate helpers ─────────────────────────────────────────────────────────
function canvasWidth(): number {
  return canvasEl.value?.width ?? 800
}

/** seconds → canvas X pixel */
function secToX(sec: number): number {
  const w = canvasWidth()
  const td = totalDuration.value
  return (sec / td) * w * zoomLevel.value
}

/** canvas X pixel → seconds */
function xToSec(x: number): number {
  const w = canvasWidth()
  const td = totalDuration.value
  return (x / (w * zoomLevel.value)) * td
}

// ── Draw ───────────────────────────────────────────────────────────────────────
function draw() {
  const canvas = canvasEl.value
  if (!canvas) return
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  const w = canvas.width
  const h = canvas.height

  // Clear
  ctx.clearRect(0, 0, w, h)

  // Background
  ctx.fillStyle = '#0f1117'
  ctx.fillRect(0, 0, w, h)

  // ── Ruler row ──
  drawRuler(ctx, w)

  // ── Segment track ──
  const segY = ROW_RULER_H
  editSegments.value.forEach((seg, i) => {
    const x1 = secToX(seg.start)
    const x2 = secToX(seg.end)
    const bw = Math.max(x2 - x1, 2)
    const isSel = selectedSegId.value === seg.id

    // Body
    ctx.fillStyle = isSel ? segColor(i, 0.92) : segColor(i, 0.72)
    roundRect(ctx, x1 + 1, segY + 4, bw - 2, ROW_SEG_H - 8, 5)
    ctx.fill()

    // Border
    ctx.strokeStyle = isSel ? '#fff' : segColor(i, 0.5)
    ctx.lineWidth = isSel ? 1.5 : 1
    roundRect(ctx, x1 + 1, segY + 4, bw - 2, ROW_SEG_H - 8, 5)
    ctx.stroke()

    // Label: id + duration
    const label = `${seg.id} (${fmtSec(seg.end - seg.start)})`
    ctx.fillStyle = '#ffffff'
    ctx.font = 'bold 11px system-ui'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    const labelX = x1 + bw / 2
    const labelY = segY + ROW_SEG_H / 2
    if (bw > 28) {
      ctx.fillText(label, labelX, labelY, bw - 8)
    }

    // Drag handles (left & right edges)
    ;['left', 'right'].forEach(side => {
      const hx = side === 'left' ? x1 + 3 : x2 - 3
      ctx.fillStyle = isSel ? '#fff' : 'rgba(255,255,255,0.4)'
      ctx.beginPath()
      ctx.arc(hx, segY + ROW_SEG_H / 2, 4, 0, Math.PI * 2)
      ctx.fill()
    })
  })

  // ── Subtitle track ──
  const subY = ROW_RULER_H + ROW_SEG_H
  ctx.fillStyle = '#1a1d2e'
  ctx.fillRect(0, subY, w, ROW_SUB_H + 8)

  editSegments.value.forEach((seg, i) => {
    const x1 = secToX(seg.start)
    const x2 = secToX(seg.end)
    const bw = Math.max(x2 - x1, 2)
    if (!seg.transcript) return

    ctx.fillStyle = segColor(i, 0.25)
    ctx.fillRect(x1 + 1, subY + 3, bw - 2, ROW_SUB_H + 2)

    ctx.fillStyle = '#c8ccdd'
    ctx.font = '10px system-ui'
    ctx.textAlign = 'left'
    ctx.textBaseline = 'middle'
    const text = seg.transcript.length > 20 ? seg.transcript.slice(0, 20) + '…' : seg.transcript
    if (bw > 16) {
      ctx.fillText(text, x1 + 5, subY + ROW_SUB_H / 2 + 4, bw - 10)
    }
  })

  // ── Track labels ──
  ctx.fillStyle = '#4a5070'
  ctx.font = '10px system-ui'
  ctx.textAlign = 'left'
  ctx.textBaseline = 'middle'
  ctx.fillText('片段', 4, ROW_RULER_H + ROW_SEG_H / 2)
  ctx.fillText('字幕', 4, ROW_RULER_H + ROW_SEG_H + ROW_SUB_H / 2 + 5)
}

function drawRuler(ctx: CanvasRenderingContext2D, w: number) {
  ctx.fillStyle = '#1a1d2e'
  ctx.fillRect(0, 0, w, ROW_RULER_H)

  ctx.strokeStyle = '#2a2d45'
  ctx.lineWidth = 1

  const td = totalDuration.value
  // Determine tick interval based on zoom
  const pxPerSec = (w * zoomLevel.value) / td
  let tickInterval = 1
  const targetPxGap = 40
  for (const t of [1, 2, 5, 10, 15, 30, 60]) {
    if (pxPerSec * t >= targetPxGap) { tickInterval = t; break }
  }

  for (let t = 0; t <= td; t += tickInterval) {
    const x = secToX(t)
    if (x > w) break
    const isMajor = t % (tickInterval * 5) === 0 || tickInterval >= 10
    ctx.strokeStyle = isMajor ? '#4a5070' : '#2a2d45'
    ctx.beginPath()
    ctx.moveTo(x, isMajor ? 4 : 10)
    ctx.lineTo(x, ROW_RULER_H)
    ctx.stroke()

    if (isMajor) {
      ctx.fillStyle = '#7a82a0'
      ctx.font = '9px system-ui'
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillText(fmtSec(t), x, 3)
    }
  }
}

function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number, y: number, w: number, h: number, r: number
) {
  if (w < 2 * r) r = w / 2
  if (h < 2 * r) r = h / 2
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

// ── Mouse interaction ─────────────────────────────────────────────────────────
const HANDLE_RADIUS = 8  // px hit radius for edge handles

function hitTestSegmentEdge(x: number, y: number): { segId: number; side: 'left' | 'right' } | null {
  const segY = ROW_RULER_H
  if (y < segY || y > segY + ROW_SEG_H) return null
  for (const seg of editSegments.value) {
    const x1 = secToX(seg.start)
    const x2 = secToX(seg.end)
    if (Math.abs(x - x1) <= HANDLE_RADIUS) return { segId: seg.id, side: 'left' }
    if (Math.abs(x - x2) <= HANDLE_RADIUS) return { segId: seg.id, side: 'right' }
  }
  return null
}

function hitTestSegment(x: number, y: number): number | null {
  const segY = ROW_RULER_H
  if (y < segY || y > segY + ROW_SEG_H) return null
  for (const seg of editSegments.value) {
    const x1 = secToX(seg.start)
    const x2 = secToX(seg.end)
    if (x >= x1 && x <= x2) return seg.id
  }
  return null
}

function hitTestSubtitle(x: number, y: number): number | null {
  const subY = ROW_RULER_H + ROW_SEG_H
  if (y < subY || y > subY + ROW_SUB_H + 8) return null
  for (const seg of editSegments.value) {
    const x1 = secToX(seg.start)
    const x2 = secToX(seg.end)
    if (x >= x1 && x <= x2) return seg.id
  }
  return null
}

function getCanvasXY(e: MouseEvent): { x: number; y: number } {
  const rect = canvasEl.value!.getBoundingClientRect()
  return { x: e.clientX - rect.left, y: e.clientY - rect.top }
}

function onMouseDown(e: MouseEvent) {
  const { x, y } = getCanvasXY(e)
  const edge = hitTestSegmentEdge(x, y)
  if (edge) {
    drag.active = true
    drag.segId = edge.segId
    drag.side = edge.side
    drag.startX = x
    const seg = editSegments.value.find(s => s.id === edge.segId)!
    drag.origValue = edge.side === 'left' ? seg.start : seg.end
    e.preventDefault()
  }
}

function onMouseMove(e: MouseEvent) {
  const { x, y } = getCanvasXY(e)
  // Cursor change
  const edge = hitTestSegmentEdge(x, y)
  if (canvasEl.value) {
    canvasEl.value.style.cursor = edge ? 'ew-resize' : 'default'
  }

  if (!drag.active) return

  const dx = x - drag.startX
  const newSec = Math.max(0, drag.origValue + xToSec(dx))

  const seg = editSegments.value.find(s => s.id === drag.segId)
  if (!seg) return

  if (drag.side === 'left') {
    // Can't drag past right edge or below 0.5s
    const minEnd = seg.end - 0.5
    seg.start = Math.min(newSec, minEnd)
    seg.duration = seg.end - seg.start
  } else {
    // Can't drag below start + 0.5s
    const minStart = seg.start + 0.5
    seg.end = Math.max(newSec, minStart)
    seg.duration = seg.end - seg.start
  }
  dirty.value = true
  draw()
}

function onMouseUp(_e: MouseEvent) {
  drag.active = false
}
function onMouseLeave(_e: MouseEvent) {
  drag.active = false
}

function onCanvasClick(e: MouseEvent) {
  if (drag.active) return
  const { x, y } = getCanvasXY(e)

  // Click subtitle track → open subtitle editor
  const subSegId = hitTestSubtitle(x, y)
  if (subSegId !== null) {
    const seg = editSegments.value.find(s => s.id === subSegId)!
    openSubtitleEdit(seg)
    return
  }

  // Click segment track → select
  const segId = hitTestSegment(x, y)
  selectedSegId.value = segId
  draw()
}

function onWheel(e: WheelEvent) {
  // Scroll horizontally (or zoom with ctrl)
  if (e.ctrlKey || e.metaKey) {
    const levels: ZoomValue[] = [1, 2, 5]
    const cur = levels.indexOf(zoomLevel.value)
    if (e.deltaY < 0 && cur < levels.length - 1) zoomLevel.value = levels[cur + 1]
    if (e.deltaY > 0 && cur > 0) zoomLevel.value = levels[cur - 1]
  }
}

// ── Playhead drag ─────────────────────────────────────────────────────────────
let draggingPlayhead = false
function startDragPlayhead(e: MouseEvent) {
  draggingPlayhead = true
  e.preventDefault()
  window.addEventListener('mousemove', dragPlayheadMove)
  window.addEventListener('mouseup', stopDragPlayhead)
}
function dragPlayheadMove(e: MouseEvent) {
  if (!draggingPlayhead || !canvasWrap.value) return
  const rect = canvasWrap.value.getBoundingClientRect()
  const x = Math.max(0, Math.min(e.clientX - rect.left, rect.width))
  playheadSec.value = xToSec(x)
  updatePlayheadX()
}
function stopDragPlayhead() {
  draggingPlayhead = false
  window.removeEventListener('mousemove', dragPlayheadMove)
  window.removeEventListener('mouseup', stopDragPlayhead)
}
function updatePlayheadX() {
  playheadX.value = secToX(playheadSec.value)
}

// ── Zoom control ──────────────────────────────────────────────────────────────
function setZoom(v: ZoomValue) {
  zoomLevel.value = v
  resizeCanvas()
  draw()
  updatePlayheadX()
}

// ── Segment operations ────────────────────────────────────────────────────────
function deleteSelected() {
  if (selectedSegId.value === null) return
  editSegments.value = editSegments.value.filter(s => s.id !== selectedSegId.value)
  // Renumber
  editSegments.value.forEach((s, i) => { s.id = i + 1 })
  selectedSegId.value = null
  dirty.value = true
  draw()
}

// ── Subtitle edit ─────────────────────────────────────────────────────────────
function openSubtitleEdit(seg: Segment) {
  editingSubtitle.value = { segId: seg.id, text: seg.transcript || '' }
}
function closeSubtitleEdit() {
  editingSubtitle.value = null
}
function applySubtitleEdit() {
  if (!editingSubtitle.value) return
  const seg = editSegments.value.find(s => s.id === editingSubtitle.value!.segId)
  if (seg) {
    seg.transcript = editingSubtitle.value.text
    dirty.value = true
    draw()
  }
  editingSubtitle.value = null
}

// ── Save plan ─────────────────────────────────────────────────────────────────
async function savePlan() {
  if (!dirty.value || saving.value) return
  saving.value = true
  saveErr.value = ''
  try {
    const segments = editSegments.value.map(s => ({
      id: s.id,
      start: s.start,
      end: s.end,
      transcript: s.transcript,
    }))
    const res = await clipApi.patchClipPlan(props.jobId, segments)
    const updated = res.data
    emit('planUpdated', updated.clip_plan!)
    dirty.value = false
  } catch (e: any) {
    saveErr.value = e?.response?.data?.detail || '保存失败，请重试'
  } finally {
    saving.value = false
  }
}

// ── Canvas resize ─────────────────────────────────────────────────────────────
function resizeCanvas() {
  const canvas = canvasEl.value
  const wrap = canvasWrap.value
  if (!canvas || !wrap) return
  const w = wrap.clientWidth || 800
  canvas.width = Math.round(w * zoomLevel.value)
  canvas.height = CANVAS_H
  canvas.style.width = `${canvas.width}px`
  canvas.style.height = `${canvas.height}px`
}

const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(() => {
  resizeCanvas()
  draw()
}) : null

// ── Utilities ─────────────────────────────────────────────────────────────────
function fmtSec(s: number): string {
  if (!isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = (s % 60).toFixed(1)
  return `${m}:${sec.padStart(4, '0')}`
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
function initFromPlan(plan: ClipPlan) {
  editSegments.value = plan.segments.map(s => ({ ...s }))
  dirty.value = false
  selectedSegId.value = null
}

onMounted(async () => {
  initFromPlan(props.clipPlan)
  await nextTick()
  resizeCanvas()
  draw()
  updatePlayheadX()
  if (ro && canvasWrap.value) ro.observe(canvasWrap.value)
})

onBeforeUnmount(() => {
  if (ro && canvasWrap.value) ro.unobserve(canvasWrap.value)
  window.removeEventListener('mousemove', dragPlayheadMove)
  window.removeEventListener('mouseup', stopDragPlayhead)
})

watch(() => props.clipPlan, (plan) => {
  initFromPlan(plan)
  resizeCanvas()
  draw()
}, { deep: true })

watch(zoomLevel, () => {
  resizeCanvas()
  draw()
  updatePlayheadX()
})

watch(editSegments, () => {
  draw()
}, { deep: true })

watch(selectedSegId, () => {
  draw()
})
</script>

<style scoped>
.timeline-root {
  display: flex;
  flex-direction: column;
  gap: 0;
  background: #0f1117;
  border: 1px solid #2a2d45;
  border-radius: 10px;
  overflow: hidden;
}

/* Toolbar */
.tl-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 14px;
  background: #12151f;
  border-bottom: 1px solid #1e2130;
  flex-wrap: wrap;
}
.tl-label {
  font-size: 12px;
  color: #7a82a0;
  margin-right: 4px;
}
.tl-zoom-group {
  display: flex;
  align-items: center;
  gap: 4px;
}
.tl-zoom-btn {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  color: #7a82a0;
  border-radius: 6px;
  padding: 3px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
}
.tl-zoom-btn:hover { color: #c8ccdd; border-color: #4a5070; }
.tl-zoom-btn.active {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
  font-weight: 600;
}
.tl-info {
  flex: 1;
  font-size: 12px;
  color: #7a82a0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tl-sel-info { color: #a78bfa; }
.tl-dur { color: #7a82a0; margin-left: 4px; }
.tl-sel-hint { font-style: italic; }
.tl-actions { display: flex; gap: 8px; }
.tl-btn-del {
  background: none;
  border: 1px solid #3a2020;
  color: #f87171;
  border-radius: 6px;
  padding: 4px 10px;
  font-size: 12px;
  cursor: pointer;
  transition: background 0.15s;
}
.tl-btn-del:hover:not(:disabled) { background: #2a1414; }
.tl-btn-del:disabled { opacity: 0.35; cursor: not-allowed; }
.tl-btn-save {
  background: #6366f1;
  border: none;
  color: #fff;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 5px;
  transition: background 0.15s;
}
.tl-btn-save:hover:not(:disabled) { background: #4f51d0; }
.tl-btn-save:disabled { opacity: 0.5; cursor: not-allowed; }

/* Canvas wrap */
.tl-canvas-wrap {
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  min-height: 108px;
  background: #0f1117;
}
.tl-canvas {
  display: block;
  cursor: default;
}

/* Playhead */
.tl-playhead {
  position: absolute;
  top: 0;
  bottom: 0;
  width: 12px;
  transform: translateX(-50%);
  cursor: ew-resize;
  z-index: 10;
  pointer-events: all;
}
.tl-playhead-head {
  width: 10px;
  height: 10px;
  background: #f59e0b;
  clip-path: polygon(0 0, 100% 0, 50% 100%);
  margin: 0 auto;
}
.tl-playhead-line {
  width: 1px;
  background: #f59e0b;
  height: calc(100% - 10px);
  margin: 0 auto;
  opacity: 0.6;
}

/* Subtitle edit panel */
.tl-sub-edit-panel {
  background: #1a1d2e;
  border-top: 1px solid #2a2d45;
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.sub-edit-label { font-size: 12px; color: #7a82a0; }
.sub-edit-row { display: flex; gap: 10px; align-items: flex-end; }
.sub-edit-input {
  flex: 1;
  background: #0f1117;
  border: 1px solid #2a2d45;
  border-radius: 6px;
  color: #e8eaf0;
  font-size: 13px;
  padding: 6px 10px;
  resize: none;
  font-family: inherit;
}
.sub-edit-input:focus { outline: none; border-color: #6366f1; }
.sub-edit-actions { display: flex; flex-direction: column; gap: 5px; }
.tl-btn-sm {
  background: #1e2130;
  border: 1px solid #2a2d45;
  color: #7a82a0;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.tl-btn-sm:hover { color: #c8ccdd; }
.tl-btn-sm--primary {
  background: #6366f1;
  border-color: #6366f1;
  color: #fff;
  font-weight: 600;
}
.tl-btn-sm--primary:hover { background: #4f51d0; }

/* Segment list */
.tl-seg-list {
  border-top: 1px solid #1e2130;
  font-size: 12px;
  max-height: 200px;
  overflow-y: auto;
}
.tl-seg-list-head {
  display: grid;
  grid-template-columns: 36px 70px 70px 70px 1fr 28px;
  gap: 4px;
  padding: 6px 14px;
  background: #12151f;
  color: #4a5070;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 1;
}
.tl-seg-row {
  display: grid;
  grid-template-columns: 36px 70px 70px 70px 1fr 28px;
  gap: 4px;
  padding: 6px 14px;
  border-top: 1px solid #1a1d2e;
  color: #c8ccdd;
  cursor: pointer;
  transition: background 0.12s;
  align-items: center;
}
.tl-seg-row:hover { background: #141729; }
.tl-seg-row--sel { background: #1e2140; color: #e8eaf0; }
.seg-num {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 4px;
  background: #2a2d45;
  font-weight: 700;
  font-size: 11px;
  color: #e8eaf0;
}
.seg-dur { color: #6366f1; font-weight: 600; }
.seg-transcript {
  color: #7a82a0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tl-icon-btn {
  background: none;
  border: none;
  color: #4a5070;
  cursor: pointer;
  font-size: 13px;
  padding: 2px 4px;
  border-radius: 4px;
  transition: color 0.15s;
}
.tl-icon-btn:hover { color: #a78bfa; }

/* Error */
.tl-err {
  color: #f87171;
  font-size: 12px;
  padding: 6px 14px;
  background: #1a0f0f;
}

/* Subtitle panel transition */
.sub-panel-enter-active, .sub-panel-leave-active {
  transition: all 0.18s ease;
}
.sub-panel-enter-from, .sub-panel-leave-to {
  opacity: 0;
  transform: translateY(-6px);
}

/* mini-spin */
.mini-spin {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
