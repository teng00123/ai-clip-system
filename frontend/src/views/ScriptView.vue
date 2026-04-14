<template>
  <div class="script-page">
    <!-- Header -->
    <div class="script-header">
      <button class="btn-back" @click="router.push('/dashboard')">← {{ t('guide.back') }}</button>
      <span class="page-title">{{ t('script.title') }}</span>
      <div class="format-tabs">
        <button
          class="format-tab"
          :class="{ active: selectedFormat === 'voiceover' }"
          @click="selectedFormat = 'voiceover'"
        >{{ t('script.voiceover') }}</button>
        <button
          class="format-tab"
          :class="{ active: selectedFormat === 'storyboard' }"
          @click="selectedFormat = 'storyboard'"
        >{{ t('script.storyboard') }}</button>
      </div>
      <div class="header-actions">
        <span v-if="scriptStore.script" class="version-badge">v{{ scriptStore.script.version }}</span>
        <button
          class="btn-ghost"
          :disabled="scriptStore.generating"
          @click="handleGenerate"
          :title="`${t('script.regenerate')}（${selectedFormat === 'storyboard' ? t('script.storyboard') : t('script.voiceover')}格式）`"
        >{{ scriptStore.generating ? t('script.generating') : t('script.regenerate') }}</button>
        <button
          class="btn-primary"
          :disabled="saving || !dirty"
          @click="handleSave"
        >
          <span v-if="saving" class="mini-spin"></span>
          <span v-else>{{ dirty ? t('common.save') : t('script.saved') }}</span>
        </button>
        <button
          class="btn-next"
          :disabled="dirty"
          @click="goToUpload"
          title="{{ t('script.goUpload') }}"
        >{{ t('script.goUpload') }} →</button>
      </div>
    </div>

    <!-- generating splash -->
    <div v-if="scriptStore.generating || scriptStore.loading" class="splash">
      <div class="ai-pulse">
        <div class="pulse-ring"></div>
        <span class="ai-icon">✦</span>
      </div>
      <p class="splash-label">{{ scriptStore.generating ? t('script.aiWriting') : t('common.loading') }}</p>
      <p v-if="scriptStore.generating && generatingTokenCount > 0" class="token-counter">
        {{ t('script.tokenCount', { count: generatingTokenCount }) }}
      </p>
    </div>

    <!-- error -->
    <div v-else-if="errMsg" class="splash">
      <p class="err-msg">{{ errMsg }}</p>
      <button class="btn-primary" @click="handleGenerate">{{ t('script.retry') }}</button>
    </div>

    <!-- empty — guide not done -->
    <div v-else-if="guideIncomplete" class="splash">
      <div class="empty-icon">📋</div>
      <p class="splash-label">{{ t('script.guideIncomplete') }}</p>
      <button class="btn-primary" @click="router.push(`/project/${projectId}/guide`)">
        {{ t('script.goGuide') }}
      </button>
    </div>

    <!-- no script yet -->
    <div v-else-if="!scriptStore.script" class="splash">
      <div class="empty-icon">✨</div>
      <p class="splash-label">{{ t('script.noScript') }}</p>
      <button class="btn-primary btn-lg" @click="handleGenerate">
        {{ t('script.generate') }}
      </button>
    </div>

    <!-- script editor -->
    <div v-else class="editor-wrap">
      <div class="editor-main">

        <!-- Title + Hook -->
        <section class="editor-section">
          <label class="field-label">{{ t('script.fieldTitle') }}</label>
          <input
            v-model="draft.title"
            class="field-input"
            :placeholder="t('script.titlePlaceholder')"
            @input="dirty = true"
          />
        </section>

        <section class="editor-section">
          <label class="field-label">{{ t('script.hook') }}</label>
          <textarea
            v-model="draft.hook"
            class="field-textarea"
            rows="3"
            :placeholder="t('script.hookPlaceholder')"
            @input="dirty = true"
          ></textarea>
        </section>

        <!-- Sections -->
        <section class="editor-section">
          <div class="section-header-row">
            <label class="field-label">{{ t('script.sections') }}</label>
            <button class="btn-add-section" @click="addSection">{{ t('script.addSection') }}</button>
          </div>

          <div
            v-for="(sec, idx) in draft.sections"
            :key="sec.id"
            class="script-section-card"
          >
            <div class="section-card-header">
              <span class="section-num">{{ idx + 1 }}</span>
              <input
                v-model="sec.title"
                class="section-title-input"
                placeholder="段落标题"
                @input="dirty = true"
              />
              <span class="duration-badge">{{ sec.duration_estimate }}</span>
              <button class="btn-icon" :title="t('script.rewriteSection')" @click="openRewrite(idx)">✦</button>
              <button class="btn-icon btn-danger" @click="removeSection(idx)">✕</button>
            </div>
            <!-- voiceover: 口播文案区域 -->
            <textarea
              v-if="selectedFormat === 'voiceover' || !sec.shot_type"
              v-model="sec.content"
              class="section-content-area"
              rows="4"
              placeholder="段落内容…"
              @input="dirty = true"
            ></textarea>

            <!-- storyboard: 分镜内容区域 -->
            <div v-else class="storyboard-fields">
              <div class="sb-row">
                <label class="sb-label">🎥 景别</label>
                <input
                  v-model="sec.shot_type"
                  class="sb-input"
                  placeholder="特写/近景/中景/全景/信息图/过渡"
                  @input="dirty = true"
                />
              </div>
              <div class="sb-row">
                <label class="sb-label">👁 画面</label>
                <textarea
                  v-model="sec.visual"
                  class="sb-textarea"
                  rows="2"
                  placeholder="画面内容描述（场景、动作、构图）"
                  @input="dirty = true"
                ></textarea>
              </div>
              <div class="sb-row">
                <label class="sb-label">🎤 口播</label>
                <textarea
                  v-model="sec.voiceover"
                  class="sb-textarea"
                  rows="3"
                  :placeholder="t('script.voiceoverPlaceholder')"
                  @input="dirty = true"
                ></textarea>
              </div>
              <div class="sb-row">
                <label class="sb-label">📝 字幕</label>
                <input
                  v-model="sec.caption"
                  class="sb-input"
                  placeholder="字幕/花字文案（可为空）"
                  @input="dirty = true"
                />
              </div>
            </div>

            <!-- Inline rewrite panel -->
            <div v-if="rewriteIdx === idx" class="rewrite-panel">
              <!-- Step 1: instruction input -->
              <template v-if="!rewritePreview[idx] && !rewriteStreaming[idx]">
                <textarea
                  v-model="rewriteInstruction"
                  class="rewrite-input"
                  rows="2"
                  placeholder="改写要求，例如：更口语化、缩短到 15 秒、加入数据支撑…"
                ></textarea>
                <div class="rewrite-actions">
                  <button class="btn-ghost btn-sm" @click="closeRewrite">{{ t('common.cancel') }}</button>
                  <button
                    class="btn-primary btn-sm"
                    :disabled="rewriting || !rewriteInstruction.trim()"
                    @click="submitRewrite(idx)"
                  >
                    <span v-if="rewriting" class="mini-spin"></span>
                    <span v-else>{{ t('script.aiRewrite') }}</span>
                  </button>
                </div>
              </template>

              <!-- Step 1.5: SSE streaming (typewriter) -->
              <template v-else-if="rewriteStreaming[idx] !== undefined && !rewritePreview[idx]">
                <div class="streaming-wrap">
                  <div class="streaming-label">✦ AI 正在改写中…</div>
                  <div class="streaming-text">{{ rewriteStreaming[idx] }}<span class="cursor-blink">|</span></div>
                </div>
              </template>

              <!-- Step 2: preview diff (or streaming) -->
              <template v-else>
                <div class="diff-wrap">
                  <div class="diff-col diff-old">
                    <div class="diff-label">原文</div>
                    <div class="diff-text">{{ rewritePreview[idx].original }}</div>
                  </div>
                  <div class="diff-col diff-new">
                    <div class="diff-label">改写后 ✦</div>
                    <div class="diff-text">
                      {{ rewritePreview[idx].rewritten }}
                    </div>
                  </div>
                </div>
                <div class="rewrite-actions">
                  <button class="btn-ghost btn-sm" @click="discardRewrite(idx)">{{ t('script.discard') }}</button>
                  <button class="btn-primary btn-sm" @click="applyRewrite(idx)">✓ 应用改写</button>
                </div>
              </template>

              <p v-if="rewriteErr" class="err-msg sm">{{ rewriteErr }}</p>
            </div>
          </div>
        </section>

        <!-- CTA -->
        <section class="editor-section">
          <label class="field-label">{{ t('script.cta') }}</label>
          <textarea
            v-model="draft.cta"
            class="field-textarea"
            rows="2"
            :placeholder="t('script.ctaPlaceholder')"
            @input="dirty = true"
          ></textarea>
        </section>

        <!-- Notes -->
        <section class="editor-section">
          <label class="field-label">备注 / 拍摄提示</label>
          <textarea
            v-model="draft.notes"
            class="field-textarea notes-area"
            rows="3"
            placeholder="给自己的拍摄备忘…"
            @input="dirty = true"
          ></textarea>
        </section>
      </div>

      <!-- Sidebar -->
      <aside class="editor-sidebar">
        <div class="sidebar-card">
          <div class="sidebar-title">📊 时长估算</div>
          <div class="duration-total">{{ draft.total_duration_estimate }}</div>
          <div class="duration-breakdown">
            <div class="dur-row" v-for="sec in draft.sections" :key="sec.id">
              <span class="dur-label">{{ sec.title || t('script.untitled') }}</span>
              <span class="dur-val">{{ sec.duration_estimate }}</span>
            </div>
          </div>
        </div>

        <div class="sidebar-card">
          <div class="sidebar-title">💡 {{ t('script.format') }}</div>
          <div class="format-tag">{{ scriptStore.script.format }}</div>
        </div>

        <div class="sidebar-card tips-card">
          <div class="sidebar-title">🔧 {{ t('script.shortcuts') }}</div>
          <ul class="tips-list">
            <li>{{ t('script.tip1') }}</li>
            <li>{{ t('script.tip2') }}</li>
            <li>{{ t('script.tip3') }}</li>
          </ul>
        </div>
      </aside>
    </div>

    <!-- unsaved warning modal -->
    <teleport to="body">
      <div v-if="showLeaveConfirm" class="modal-overlay" @click.self="showLeaveConfirm = false">
        <div class="modal">
          <p>有未保存的修改，{{ t('script.leaveConfirm') }}</p>
          <div class="modal-actions">
            <button class="btn-ghost" @click="showLeaveConfirm = false">{{ t('script.keepEditing') }}</button>
            <button class="btn-danger-solid" @click="confirmLeave">{{ t('script.discardLeave') }}</button>
          </div>
        </div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter, onBeforeRouteLeave } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useScriptStore } from '@/stores/script'
import * as scriptApi from '@/api/scripts'
import type { ParagraphRewriteResult } from '@/api/scripts'
import { streamSSE } from '@/utils/sse'
import * as guideApi from '@/api/guide'
import type { ScriptContent, ScriptSection } from '@/types'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const scriptStore = useScriptStore()

const projectId = route.params.projectId as string

const dirty = ref(false)
const saving = ref(false)
const errMsg = ref('')
const guideIncomplete = ref(false)

// 剧本格式切换
type ScriptFormat = 'voiceover' | 'storyboard'
const selectedFormat = ref<ScriptFormat>('voiceover')
// 当已有剧本时，从 store 同步格式
const syncFormatFromStore = () => {
  if (scriptStore.script?.format) {
    selectedFormat.value = scriptStore.script.format as ScriptFormat
  }
}

// rewrite state
const rewriteIdx = ref(-1)
const rewriteInstruction = ref('')
const rewriting = ref(false)
const rewriteErr = ref('')
// key: paragraph index → preview result
const rewritePreview = ref<Record<number, ParagraphRewriteResult>>({})
// SSE streaming text for rewrite (shown in diff new column while streaming)
const rewriteStreaming = ref<Record<number, string>>({})
const rewriteStreamDone = ref<Record<number, boolean>>({})

// Generate with SSE streaming (typewriter)
const generatingRaw = ref('') // raw JSON accumulator during SSE
const generatingTokenCount = ref(0)
// leave confirm
const showLeaveConfirm = ref(false)
let pendingLeaveNext: (() => void) | null = null

// editable draft (deep clone from store)
const draft = reactive<ScriptContent>({
  title: '',
  hook: '',
  sections: [],
  cta: '',
  total_duration_estimate: '',
  notes: '',
})

// sync draft from store whenever script changes
watch(
  () => scriptStore.script,
  (s) => {
    if (!s) return
    draft.title = s.content.title
    draft.hook = s.content.hook
    draft.sections = s.content.sections.map((sec) => ({ ...sec }))
    draft.cta = s.content.cta
    draft.total_duration_estimate = s.content.total_duration_estimate
    draft.notes = s.content.notes
    dirty.value = false
  },
  { immediate: true },
)

onMounted(async () => {
  // 先确认 guide 是否完成，再加载剧本
  try {
    const sessionRes = await guideApi.getSession(projectId)
    if (!sessionRes.data?.completed) {
      guideIncomplete.value = true
      return
    }
  } catch {
    // session 不存在或接口异常，视为未完成
    guideIncomplete.value = true
    return
  }

  await scriptStore.loadLatestScript(projectId)
  syncFormatFromStore()
})

async function handleGenerate() {
  errMsg.value = ''
  generatingRaw.value = ''
  generatingTokenCount.value = 0
  scriptStore.generating = true

  await streamSSE(scriptApi.getGenerateStreamUrl(projectId), {
    method: 'POST',
    body: { format: selectedFormat.value },
    onToken(token) {
      generatingRaw.value += token
      generatingTokenCount.value++
    },
    async onDone() {
      try {
        const content = JSON.parse(generatingRaw.value)
        await scriptApi.saveStreamedScript(projectId, content, selectedFormat.value)
        await scriptStore.loadLatestScript(projectId)
        syncFormatFromStore()
      } catch (e: any) {
        errMsg.value = '解析生成内容失败，请重试'
      } finally {
        scriptStore.generating = false
        generatingRaw.value = ''
      }
    },
    onError(msg) {
      errMsg.value = msg || '生成失败，请重试'
      scriptStore.generating = false
      generatingRaw.value = ''
    },
  })
}

async function handleSave() {
  if (!scriptStore.script || saving.value) return
  saving.value = true
  try {
    await scriptStore.saveScript(scriptStore.script.id, { ...draft })
    dirty.value = false
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || '保存失败'
  } finally {
    saving.value = false
  }
}

function addSection() {
  const newId = draft.sections.length > 0
    ? Math.max(...draft.sections.map((s) => s.id)) + 1
    : 1
  draft.sections.push({ id: newId, title: '', content: '', duration_estimate: '30s' })
  dirty.value = true
}

function removeSection(idx: number) {
  draft.sections.splice(idx, 1)
  dirty.value = true
}

function openRewrite(idx: number) {
  rewriteIdx.value = idx
  rewriteInstruction.value = ''
  rewriteErr.value = ''
  // clear any previous preview for this index
  delete rewritePreview.value[idx]
}

function closeRewrite() {
  rewriteIdx.value = -1
  rewriteInstruction.value = ''
  rewriteErr.value = ''
}

async function submitRewrite(idx: number) {
  if (!scriptStore.script || rewriting.value || !rewriteInstruction.value.trim()) return
  rewriting.value = true
  rewriteErr.value = ''
  // 初始化流式状态
  rewriteStreaming.value = { ...rewriteStreaming.value, [idx]: '' }
  rewriteStreamDone.value = { ...rewriteStreamDone.value, [idx]: false }

  const instructionSnapshot = rewriteInstruction.value.trim()
  const originalContent = draft.sections[idx]?.content ?? ''
  const sectionTitle = draft.sections[idx]?.title ?? `段落 ${idx + 1}`

  await streamSSE(scriptApi.getRewriteStreamUrl(scriptStore.script.id), {
    method: 'POST',
    body: {
      paragraph_index: idx,
      instruction: instructionSnapshot,
      preview: true,
    },
    onToken(token) {
      rewriteStreaming.value = {
        ...rewriteStreaming.value,
        [idx]: (rewriteStreaming.value[idx] ?? '') + token,
      }
    },
    onDone() {
      const rewritten = rewriteStreaming.value[idx] ?? ''
      // 流式完成，转为预览模式（显示对比）
      rewritePreview.value = {
        ...rewritePreview.value,
        [idx]: {
          script_id: scriptStore.script!.id,
          paragraph_index: idx,
          section_title: sectionTitle,
          original: originalContent,
          rewritten,
          instruction: instructionSnapshot,
          applied: false,
        } as ParagraphRewriteResult,
      }
      rewriteStreamDone.value = { ...rewriteStreamDone.value, [idx]: true }
      rewriting.value = false
    },
    onError(msg) {
      rewriteErr.value = msg || '改写失败，请重试'
      rewriting.value = false
      // 清除未完成的流
      delete rewriteStreaming.value[idx]
    },
  })
}

async function applyRewrite(idx: number) {
  if (!scriptStore.script) return
  const preview = rewritePreview.value[idx]
  if (!preview) return
  try {
    await scriptApi.applyParagraphRewrite(scriptStore.script.id, idx, preview.rewritten)
    draft.sections[idx].content = preview.rewritten
    dirty.value = false // already saved by backend
    discardRewrite(idx)
  } catch (e: any) {
    rewriteErr.value = e?.response?.data?.detail || '应用失败，请重试'
  }
}

function discardRewrite(idx: number) {
  delete rewritePreview.value[idx]
  delete rewriteStreaming.value[idx]
  delete rewriteStreamDone.value[idx]
  rewriteIdx.value = -1
  rewriteInstruction.value = ''
  rewriteErr.value = ''
}

function goToUpload() {
  router.push(`/project/${projectId}/upload`)
}

// route leave guard
onBeforeRouteLeave((_to, _from, next) => {
  if (dirty.value) {
    showLeaveConfirm.value = true
    pendingLeaveNext = next
  } else {
    next()
  }
})

function confirmLeave() {
  showLeaveConfirm.value = false
  if (pendingLeaveNext) {
    pendingLeaveNext()
    pendingLeaveNext = null
  }
}

// browser tab close warning
function handleBeforeUnload(e: BeforeUnloadEvent) {
  if (dirty.value) {
    e.preventDefault()
    e.returnValue = ''
  }
}
onMounted(() => window.addEventListener('beforeunload', handleBeforeUnload))
onBeforeUnmount(() => window.removeEventListener('beforeunload', handleBeforeUnload))
</script>

<style scoped>
.script-page {
  min-height: 100vh;
  background: #0f1117;
  color: #e8eaf0;
  display: flex;
  flex-direction: column;
}

/* Header */
.script-header {
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
}
.btn-back:hover { color: #e8eaf0; }
.page-title {
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}
.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}
.version-badge {
  font-size: 12px;
  color: #7a82a0;
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 20px;
  padding: 2px 10px;
}

/* Splash */
.splash {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 20px;
  padding: 60px 24px;
}
.splash-label { color: #7a82a0; font-size: 15px; }
.token-counter { color: #4f6ef7; font-size: 13px; opacity: 0.8; }
.empty-icon { font-size: 48px; }

/* AI pulse animation */
.ai-pulse {
  position: relative;
  width: 72px;
  height: 72px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.pulse-ring {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  border: 2px solid #4f6ef7;
  animation: pulse-ring 1.4s ease-out infinite;
}
@keyframes pulse-ring {
  0%   { transform: scale(0.7); opacity: 0.9; }
  100% { transform: scale(1.5); opacity: 0; }
}
.ai-icon {
  font-size: 28px;
  color: #4f6ef7;
  animation: ai-blink 1.4s ease-in-out infinite alternate;
}
@keyframes ai-blink {
  from { opacity: 0.5; }
  to   { opacity: 1; }
}

/* Editor layout */
.editor-wrap {
  flex: 1;
  display: flex;
  gap: 0;
  overflow: hidden;
}
.editor-main {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.editor-sidebar {
  width: 240px;
  flex-shrink: 0;
  border-left: 1px solid #1e2130;
  padding: 20px 16px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* Sections */
.editor-section { display: flex; flex-direction: column; gap: 8px; }
.field-label {
  font-size: 12px;
  font-weight: 600;
  color: #7a82a0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.field-input, .field-textarea, .section-title-input, .section-content-area {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  color: #e8eaf0;
  font-size: 14px;
  font-family: inherit;
  padding: 10px 12px;
  width: 100%;
  box-sizing: border-box;
  resize: vertical;
  transition: border-color 0.2s;
}
.field-input:focus, .field-textarea:focus,
.section-title-input:focus, .section-content-area:focus {
  outline: none;
  border-color: #4f6ef7;
}
.notes-area { color: #a0a8c0; }

/* Script section card */
.section-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.script-section-card {
  background: #14172b;
  border: 1px solid #2a2d45;
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.section-card-header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.section-num {
  width: 22px;
  height: 22px;
  background: #2a2d45;
  border-radius: 50%;
  font-size: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  color: #7a82a0;
}
.section-title-input {
  flex: 1;
  padding: 6px 10px;
  font-size: 14px;
  resize: none;
}
.duration-badge {
  font-size: 11px;
  color: #7a82a0;
  background: #1e2130;
  border-radius: 12px;
  padding: 2px 8px;
  flex-shrink: 0;
}
.section-content-area { min-height: 80px; }

/* Rewrite panel */
.rewrite-panel {
  background: #0f1117;
  border: 1px solid #3a4070;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rewrite-input {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 6px;
  color: #e8eaf0;
  font-size: 13px;
  font-family: inherit;
  padding: 8px 10px;
  width: 100%;
  box-sizing: border-box;
  resize: none;
}
.rewrite-input:focus { outline: none; border-color: #4f6ef7; }
.rewrite-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

/* Diff view */
.diff-wrap {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.diff-col {
  background: #14172b;
  border-radius: 6px;
  padding: 10px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.diff-old { border: 1px solid #3a2020; }
.diff-new { border: 1px solid #1a3a20; }
.diff-label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.diff-old .diff-label { color: #f87171; }
.diff-new .diff-label { color: #4ade80; }
.diff-text {
  font-size: 13px;
  line-height: 1.6;
  color: #c8ccdd;
  white-space: pre-wrap;
  word-break: break-word;
}

/* Streaming typewriter */
.streaming-wrap {
  background: #0a0e1a;
  border: 1px solid #2a3a60;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.streaming-label {
  font-size: 11px;
  color: #4f6ef7;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  animation: ai-blink 1s ease-in-out infinite alternate;
}
.streaming-text {
  font-size: 13px;
  line-height: 1.6;
  color: #c8ccdd;
  white-space: pre-wrap;
  word-break: break-word;
  min-height: 40px;
}
.cursor-blink {
  display: inline-block;
  color: #4f6ef7;
  font-weight: 700;
  animation: cursor-blink 0.8s step-end infinite;
}
@keyframes cursor-blink {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0; }
}

/* Icon buttons */
.btn-icon {
  background: none;
  border: none;
  cursor: pointer;
  color: #7a82a0;
  font-size: 14px;
  padding: 4px 6px;
  border-radius: 4px;
  transition: color 0.2s, background 0.15s;
}
.btn-icon:hover { color: #4f6ef7; background: #1e2130; }
.btn-icon.btn-danger:hover { color: #f87171; background: #2a1010; }
.btn-add-section {
  background: none;
  border: 1px dashed #2a2d45;
  border-radius: 6px;
  color: #7a82a0;
  font-size: 13px;
  padding: 4px 10px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.btn-add-section:hover { color: #c8ccdd; border-color: #4a5070; }

/* Sidebar */
.sidebar-card {
  background: #14172b;
  border: 1px solid #2a2d45;
  border-radius: 10px;
  padding: 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.sidebar-title {
  font-size: 12px;
  font-weight: 600;
  color: #7a82a0;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.duration-total {
  font-size: 22px;
  font-weight: 700;
  color: #4f6ef7;
}
.duration-breakdown {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.dur-row {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
}
.dur-label { color: #7a82a0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 130px; }
.dur-val { color: #c8ccdd; flex-shrink: 0; }
.format-tag {
  font-size: 13px;
  color: #c8ccdd;
  background: #1e2130;
  border-radius: 6px;
  padding: 4px 10px;
  text-align: center;
}
.tips-card { }
.tips-list {
  list-style: none;
  padding: 0;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 6px;
  font-size: 12px;
  color: #7a82a0;
  line-height: 1.6;
}
.kbd {
  display: inline-block;
  background: #2a2d45;
  border-radius: 3px;
  padding: 0 4px;
  font-size: 11px;
  color: #c8ccdd;
}

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
.btn-primary.btn-lg { padding: 12px 28px; font-size: 16px; }
.btn-primary.btn-sm { padding: 6px 14px; font-size: 13px; }
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
.btn-ghost:disabled { opacity: 0.45; cursor: not-allowed; }
.btn-ghost.btn-sm { padding: 5px 12px; font-size: 13px; }
.btn-next {
  background: #1e2130;
  color: #c8ccdd;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  padding: 8px 16px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s, color 0.2s;
}
.btn-next:hover { background: #4f6ef7; color: #fff; border-color: #4f6ef7; }
.btn-next:disabled { opacity: 0.35; cursor: not-allowed; }
.btn-danger-solid {
  background: #7f1d1d;
  color: #fca5a5;
  border: none;
  border-radius: 8px;
  padding: 8px 18px;
  font-size: 14px;
  cursor: pointer;
  transition: background 0.2s;
}
.btn-danger-solid:hover { background: #991b1b; }

/* Mini spinner */
.mini-spin {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* Error */
.err-msg { font-size: 13px; color: #f87171; }
.err-msg.sm { font-size: 12px; }

/* Modal */
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
}
.modal {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 12px;
  padding: 28px 28px 20px;
  max-width: 360px;
  width: 90%;
  display: flex;
  flex-direction: column;
  gap: 20px;
  font-size: 15px;
  color: #e8eaf0;
}
.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* Format Tabs */
.format-tabs {
  display: flex;
  gap: 4px;
  background: #1a1d2e;
  border-radius: 8px;
  padding: 3px;
  flex-shrink: 0;
}
.format-tab {
  padding: 5px 14px;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: #7a82a0;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.18s;
  white-space: nowrap;
}
.format-tab:hover { color: #c8ccdd; }
.format-tab.active {
  background: #6366f1;
  color: #fff;
  font-weight: 600;
}

/* Storyboard section fields */
.storyboard-fields {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 4px;
}
.sb-row {
  display: grid;
  grid-template-columns: 60px 1fr;
  gap: 8px;
  align-items: start;
}
.sb-label {
  font-size: 12px;
  color: #7a82a0;
  padding-top: 6px;
  white-space: nowrap;
}
.sb-input {
  background: #1a1d2e;
  border: 1px solid #2a2e45;
  border-radius: 6px;
  color: #e8eaf0;
  font-size: 13px;
  padding: 6px 10px;
  width: 100%;
  box-sizing: border-box;
}
.sb-textarea {
  background: #1a1d2e;
  border: 1px solid #2a2e45;
  border-radius: 6px;
  color: #e8eaf0;
  font-size: 13px;
  padding: 6px 10px;
  width: 100%;
  resize: vertical;
  line-height: 1.5;
  box-sizing: border-box;
  font-family: inherit;
}
.sb-input:focus, .sb-textarea:focus {
  outline: none;
  border-color: #6366f1;
}
</style>
