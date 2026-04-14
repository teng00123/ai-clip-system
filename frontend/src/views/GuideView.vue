<template>
  <div class="guide-page">
    <!-- Header -->
    <div class="guide-header">
      <button class="btn-back" @click="router.push('/dashboard')">← {{ t('guide.back') }}</button>
      <span class="guide-title">{{ t('guide.title') }}</span>
      <!-- Mode toggle — 仅在未开始时显示 -->
      <div v-if="!started && !initializing" class="mode-toggle">
        <button
          :class="['mode-btn', { active: mode === 'static' }]"
          @click="mode = 'static'"
          :title="t('guide.staticDesc')"
        >📋 {{ t('guide.static') }}</button>
        <button
          :class="['mode-btn', { active: mode === 'dynamic' }]"
          @click="mode = 'dynamic'"
          :disabled="!dynamicAvailable"
          :title="dynamicAvailable ? t('guide.dynamicDesc') : t('guide.dynamicUnavailable')"
        >✦ {{ t('guide.dynamic') }}{{ dynamicAvailable ? '' : '（' + t('guide.dynamicUnavailable') + '）' }}</button>
      </div>
      <!-- progress indicator when in dynamic mode -->
      <span v-else-if="mode === 'dynamic' && started && !completed" class="step-counter dynamic-counter">
        ✦ {{ t('guide.answeredCount', { count: dynamicAnswersCount }) }}
      </span>
      <span v-else-if="mode === 'static' && question" class="step-counter">
        {{ question.step + 1 }} / {{ question.total_steps }}
      </span>
    </div>

    <!-- Progress bar (static only) -->
    <div v-if="mode === 'static' && question" class="progress-bar-wrap">
      <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
    </div>
    <!-- Dynamic mode: thin animated pulse bar -->
    <div v-else-if="mode === 'dynamic' && started && !completed" class="progress-bar-wrap">
      <div class="progress-bar dynamic-bar"></div>
    </div>

    <!-- Main body -->
    <div class="guide-body">

      <!-- loading -->
      <div v-if="guideStore.loading || initializing" class="center-area">
        <div class="spinner"></div>
        <p class="hint">{{ dynamicLoading ? t('guide.thinking') : t('guide.loading') }}</p>
      </div>

      <!-- MODE SELECT — before started -->
      <div v-else-if="!started" class="center-area mode-select-area">
        <div class="mode-card-wrap">
          <!-- Static card -->
          <div
            :class="['mode-card', { selected: mode === 'static' }]"
            @click="mode = 'static'"
          >
            <div class="mode-card-icon">📋</div>
            <div class="mode-card-title">{{ t('guide.static') }}</div>
            <div class="mode-card-desc">{{ t('guide.staticDesc') }}</div>
            <div class="mode-card-badge">{{ t('guide.recommended') }}</div>
          </div>
          <!-- Dynamic card -->
          <div
            :class="['mode-card', { selected: mode === 'dynamic', disabled: !dynamicAvailable }]"
            @click="dynamicAvailable && (mode = 'dynamic')"
          >
            <div class="mode-card-icon">✦</div>
            <div class="mode-card-title">{{ t('guide.dynamic') }}</div>
            <div class="mode-card-desc">{{ t('guide.dynamicDesc') }}</div>
            <div v-if="!dynamicAvailable" class="mode-card-badge disabled-badge">{{ t('guide.dynamicUnavailable') }}</div>
            <div v-else class="mode-card-badge dynamic-badge">{{ t('guide.smart') }}</div>
          </div>
        </div>
        <button class="btn-primary btn-lg" @click="startMode">
          {{ t('guide.start') }} →
        </button>
      </div>

      <!-- completed -->
      <div v-else-if="completed" class="center-area done-area">
        <div class="done-icon">🎉</div>
        <h2>{{ t('guide.completed') }}</h2>
        <p class="hint">{{ t('guide.completedDesc') }}</p>
        <div v-if="brief" class="brief-preview">
          <h3>{{ t('guide.viewBrief') }}</h3>
          <div class="brief-row" v-for="(v, k) in brief" :key="k">
            <span class="brief-key">{{ briefKeyLabel(String(k)) }}</span>
            <span class="brief-val">{{ v }}</span>
          </div>
        </div>
        <button class="btn-primary btn-lg" @click="goToScript">{{ t('guide.nextStep') }} →</button>
      </div>

      <!-- Static mode: question -->
      <div v-else-if="mode === 'static' && question" class="question-area">
        <transition name="slide-up" mode="out-in">
          <div :key="question.step" class="question-card">
            <p class="question-text">{{ question.question_text }}</p>

            <!-- single_choice -->
            <div v-if="question.question_type === 'single_choice'" class="options-list">
              <button
                v-for="opt in question.options"
                :key="opt"
                :class="['option-btn', { selected: answer === opt }]"
                @click="answer = opt"
              >{{ opt }}</button>
            </div>

            <!-- text_input -->
            <div v-else class="input-area">
              <textarea
                v-model="answer"
                :placeholder="inputPlaceholder"
                rows="4"
                class="answer-textarea"
                @keydown.ctrl.enter="submitIfReady"
              ></textarea>
              <p class="input-hint">Ctrl + Enter {{ t('guide.submit') }}</p>
            </div>

            <p v-if="errMsg" class="err-msg">{{ errMsg }}</p>

            <div class="question-footer">
              <button
                class="btn-ghost"
                @click="skipAnswer"
                v-if="question.question_type === 'text_input'"
              >跳过</button>
              <button
                class="btn-primary"
                :disabled="!canSubmit || submitting"
                @click="submit"
              >
                <span v-if="submitting" class="mini-spin"></span>
                <span v-else>{{ isLastStep ? t('guide.complete') : t('guide.next') + ' →' }}</span>
              </button>
            </div>
          </div>
        </transition>
      </div>

      <!-- Dynamic mode: chat-like Q&A -->
      <div v-else-if="mode === 'dynamic'" class="dynamic-area">
        <!-- Chat history bubble list -->
        <div class="chat-history" ref="chatHistoryEl">
          <div
            v-for="(msg, i) in chatMessages"
            :key="i"
            :class="['chat-bubble', msg.role]"
          >
            <div class="bubble-avatar">
              <span v-if="msg.role === 'assistant'">✦</span>
              <span v-else>你</span>
            </div>
            <div class="bubble-body">
              <div class="bubble-text">{{ msg.content }}</div>
            </div>
          </div>
          <!-- Typing indicator when waiting for LLM -->
          <div v-if="dynamicLoading" class="chat-bubble assistant typing-indicator">
            <div class="bubble-avatar"><span>✦</span></div>
            <div class="bubble-body">
              <div class="bubble-text typing-dots">
                <span></span><span></span><span></span>
              </div>
            </div>
          </div>
        </div>

        <!-- Input area -->
        <div class="dynamic-input-wrap" v-if="dynamicQuestion && !dynamicLoading">
          <!-- Single choice options -->
          <div v-if="dynamicQuestion.question_type === 'single_choice'" class="options-list dynamic-options">
            <button
              v-for="opt in dynamicQuestion.options"
              :key="opt"
              :class="['option-btn', { selected: answer === opt }]"
              @click="answer = opt"
            >{{ opt }}</button>
            <div class="question-footer dynamic-footer">
              <button
                class="btn-primary"
                :disabled="!canSubmit || submitting"
                @click="submitDynamic"
              >
                <span v-if="submitting" class="mini-spin"></span>
                <span v-else>发送 →</span>
              </button>
            </div>
          </div>

          <!-- Multi choice -->
          <div v-else-if="dynamicQuestion.question_type === 'multi_choice'" class="options-list dynamic-options">
            <button
              v-for="opt in dynamicQuestion.options"
              :key="opt"
              :class="['option-btn', { selected: multiSelected.includes(opt) }]"
              @click="toggleMulti(opt)"
            >{{ opt }}</button>
            <div class="question-footer dynamic-footer">
              <button
                class="btn-primary"
                :disabled="multiSelected.length === 0 || submitting"
                @click="submitDynamic"
              >
                <span v-if="submitting" class="mini-spin"></span>
                <span v-else>发送 →</span>
              </button>
            </div>
          </div>

          <!-- Text input -->
          <div v-else class="dynamic-text-input">
            <textarea
              v-model="answer"
              :placeholder="t('guide.answerPlaceholder') + ' (Ctrl+Enter)'"
              rows="3"
              class="answer-textarea"
              @keydown.ctrl.enter="submitDynamic"
            ></textarea>
            <div class="dynamic-text-footer">
              <button class="btn-ghost btn-sm" @click="skipDynamic">跳过</button>
              <button
                class="btn-primary"
                :disabled="!canSubmit || submitting"
                @click="submitDynamic"
              >
                <span v-if="submitting" class="mini-spin"></span>
                <span v-else>发送 →</span>
              </button>
            </div>
          </div>
        </div>

        <p v-if="errMsg" class="err-msg err-msg-dynamic">{{ errMsg }}</p>
      </div>

      <!-- fallback -->
      <div v-else class="center-area">
        <p class="hint">暂无问题</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, nextTick, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useI18n } from 'vue-i18n'
import { useGuideStore } from '@/stores/guide'
import * as guideApi from '@/api/guide'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()
const guideStore = useGuideStore()

const projectId = route.params.projectId as string

// ── Mode ─────────────────────────────────────────────────────────────────────
type GuideMode = 'static' | 'dynamic'
const mode = ref<GuideMode>('static')
const dynamicAvailable = ref(true) // will be checked on mount
const started = ref(false)         // whether user clicked "开始向导"
const completed = ref(false)

// ── Common state ─────────────────────────────────────────────────────────────
const answer = ref('')
const submitting = ref(false)
const errMsg = ref('')
const initializing = ref(true)
const brief = ref<Record<string, string> | null>(null)

// ── Static mode state ─────────────────────────────────────────────────────────
const question = computed(() => guideStore.currentQuestion)
const progressPct = computed(() => {
  if (!question.value) return 0
  return Math.round(((question.value.step + 1) / question.value.total_steps) * 100)
})
const isLastStep = computed(() => {
  if (!question.value) return false
  return question.value.step + 1 >= question.value.total_steps
})
const canSubmit = computed(() => {
  if (mode.value === 'dynamic' && dynamicQuestion.value?.question_type === 'multi_choice') {
    return multiSelected.value.length > 0
  }
  return answer.value.trim().length > 0
})
const inputPlaceholder = computed(() => {
  if (!question.value) return t('guide.answerPlaceholder')
  const s = question.value.step
  const hints: Record<number, string> = {
    1: t('guide.hints.step1', '例如：宠物博主、美食探店、职场干货…'),
    2: t('guide.hints.step2', '例如：18~35岁上班族，喜欢健康生活…'),
    3: t('guide.hints.step3', '例如：让更多人了解我的手工皂品牌'),
    5: t('guide.hints.step5', '例如：轻松幽默、真诚分享、干货满满…'),
    7: t('guide.hints.step7', '例如：欢迎点赞关注，评论你的想法！'),
  }
  return hints[s] || t('guide.answerPlaceholder')
})

// ── Dynamic mode state ────────────────────────────────────────────────────────
interface DynamicQuestion {
  question: string
  question_type: 'single_choice' | 'multi_choice' | 'text_input'
  options?: string[]
  is_complete: boolean
  answers_count: number
  mode: string
}

const dynamicQuestion = ref<DynamicQuestion | null>(null)
const dynamicAnswersCount = ref(0)
const dynamicLoading = ref(false)
const multiSelected = ref<string[]>([])
const chatMessages = ref<{ role: 'assistant' | 'user'; content: string }[]>([])
const chatHistoryEl = ref<HTMLElement | null>(null)

function toggleMulti(opt: string) {
  const i = multiSelected.value.indexOf(opt)
  if (i >= 0) multiSelected.value.splice(i, 1)
  else multiSelected.value.push(opt)
}

async function scrollChatToBottom() {
  await nextTick()
  if (chatHistoryEl.value) {
    chatHistoryEl.value.scrollTop = chatHistoryEl.value.scrollHeight
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(async () => {
  guideStore.reset()
  // Check if dynamic mode is available
  try {
    const res = await guideApi.checkDynamicAvailable(projectId)
    dynamicAvailable.value = res.data?.available !== false
  } catch {
    dynamicAvailable.value = false
  }

  // Check if guide already completed
  try {
    const res = await guideApi.getSession(projectId)
    if (res.data?.completed) {
      completed.value = true
      started.value = true
      await loadBrief()
      return
    }
    // If there's already a session, auto-start with its mode
    if (res.data?.id) {
      mode.value = (res.data.mode as GuideMode) || 'static'
      started.value = true
      if (mode.value === 'static') {
        await guideStore.startGuide(projectId)
      } else {
        await resumeDynamic(res.data)
      }
    }
  } catch {
    // No session yet — show mode selector
  } finally {
    initializing.value = false
  }
})

async function startMode() {
  initializing.value = true
  errMsg.value = ''
  try {
    if (mode.value === 'static') {
      await guideStore.startGuide(projectId)
      if (guideStore.session?.completed) {
        completed.value = true
        await loadBrief()
      }
    } else {
      dynamicLoading.value = true
      const res = await guideApi.startDynamic(projectId)
      dynamicQuestion.value = res.data
      dynamicAnswersCount.value = res.data.answers_count || 0
      chatMessages.value = [{ role: 'assistant', content: res.data.question }]
      dynamicLoading.value = false
      await scrollChatToBottom()
    }
    started.value = true
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || '启动失败，请重试'
  } finally {
    initializing.value = false
  }
}

async function resumeDynamic(session: any) {
  // Resume from existing conversation_history
  const history: { role: string; content: string }[] = session.conversation_history || []
  chatMessages.value = history.map((m: any) => ({
    role: m.role as 'assistant' | 'user',
    content: m.content,
  }))
  dynamicAnswersCount.value = session.step || 0
  // Get the last assistant question
  const lastAssistant = [...history].reverse().find((m: any) => m.role === 'assistant')
  if (lastAssistant) {
    dynamicQuestion.value = {
      question: lastAssistant.content,
      question_type: 'text_input',
      options: undefined,
      is_complete: false,
      answers_count: dynamicAnswersCount.value,
      mode: 'dynamic',
    }
  } else {
    // Start fresh dynamic
    dynamicLoading.value = true
    const res = await guideApi.startDynamic(projectId)
    dynamicQuestion.value = res.data
    chatMessages.value = [{ role: 'assistant', content: res.data.question }]
    dynamicLoading.value = false
  }
  await scrollChatToBottom()
}

// ── Static submit ─────────────────────────────────────────────────────────────
async function submit() {
  if (!canSubmit.value || submitting.value || !question.value) return
  errMsg.value = ''
  submitting.value = true
  try {
    await guideStore.submitAnswer(projectId, question.value.step, answer.value.trim())
    answer.value = ''
    if (guideStore.session?.completed) {
      completed.value = true
      await loadBrief()
    }
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || '提交失败，请重试'
  } finally {
    submitting.value = false
  }
}

async function skipAnswer() {
  if (!question.value || submitting.value) return
  answer.value = '（略过）'
  await submit()
}

function submitIfReady() {
  if (canSubmit.value) submit()
}

// ── Dynamic submit ────────────────────────────────────────────────────────────
async function submitDynamic() {
  if (submitting.value) return
  const dq = dynamicQuestion.value
  if (!dq) return

  let userAnswer: string
  if (dq.question_type === 'multi_choice') {
    if (multiSelected.value.length === 0) return
    userAnswer = multiSelected.value.join('、')
    multiSelected.value = []
  } else {
    if (!answer.value.trim()) return
    userAnswer = answer.value.trim()
    answer.value = ''
  }

  // push user bubble
  chatMessages.value.push({ role: 'user', content: userAnswer })
  await scrollChatToBottom()

  submitting.value = true
  dynamicLoading.value = true
  errMsg.value = ''

  try {
    const res = await guideApi.answerDynamic(projectId, userAnswer)
    const result = res.data as DynamicQuestion
    dynamicAnswersCount.value = result.answers_count || dynamicAnswersCount.value + 1

    if (result.is_complete) {
      // Guide complete!
      completed.value = true
      await loadBrief()
    } else {
      // Push assistant question bubble
      chatMessages.value.push({ role: 'assistant', content: result.question })
      dynamicQuestion.value = result
      await scrollChatToBottom()
    }
  } catch (e: any) {
    errMsg.value = e?.response?.data?.detail || 'AI 响应失败，请重试'
    chatMessages.value.pop() // revert optimistic user bubble
  } finally {
    submitting.value = false
    dynamicLoading.value = false
  }
}

async function skipDynamic() {
  answer.value = '（略过）'
  await submitDynamic()
}

// ── Shared utils ──────────────────────────────────────────────────────────────
async function loadBrief() {
  try {
    const res = await guideApi.getBrief(projectId)
    brief.value = res.data?.brief || null
  } catch {
    brief.value = null
  }
}

function goToScript() {
  router.push(`/project/${projectId}/script`)
}

function briefKeyLabel(k: string) {
  return t(`guide.briefKeys.${k}`, k)
}
</script>

<style scoped>
.guide-page {
  min-height: 100vh;
  background: #0f1117;
  color: #e8eaf0;
  display: flex;
  flex-direction: column;
}

/* ── Header ── */
.guide-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid #1e2130;
  flex-wrap: wrap;
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
.guide-title {
  font-size: 16px;
  font-weight: 600;
  flex: 1;
}
.step-counter {
  font-size: 13px;
  color: #7a82a0;
}
.dynamic-counter {
  color: #a78bfa;
  font-size: 13px;
}

/* Mode toggle (in header) */
.mode-toggle {
  display: flex;
  gap: 4px;
  background: #1a1d2e;
  border-radius: 8px;
  padding: 3px;
}
.mode-btn {
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
.mode-btn:hover:not(:disabled) { color: #c8ccdd; }
.mode-btn.active {
  background: #6366f1;
  color: #fff;
  font-weight: 600;
}
.mode-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ── Progress bar ── */
.progress-bar-wrap {
  height: 3px;
  background: #1e2130;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4f6ef7, #7c3aed);
  transition: width 0.4s ease;
}
.dynamic-bar {
  width: 100%;
  background: linear-gradient(90deg, #6366f1, #a78bfa, #6366f1);
  background-size: 200% 100%;
  animation: shimmer 1.8s linear infinite;
}
@keyframes shimmer {
  0% { background-position: 200% 0; }
  100% { background-position: -200% 0; }
}

/* ── Body ── */
.guide-body {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}
.center-area {
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}
.hint {
  color: #7a82a0;
  font-size: 14px;
}

/* Spinner */
.spinner {
  width: 36px;
  height: 36px;
  border: 3px solid #1e2130;
  border-top-color: #4f6ef7;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Mode Select (pre-start) ── */
.mode-select-area {
  max-width: 640px;
  width: 100%;
  gap: 24px;
}
.mode-card-wrap {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 16px;
  width: 100%;
}
@media (max-width: 480px) {
  .mode-card-wrap { grid-template-columns: 1fr; }
}
.mode-card {
  background: #1a1d2e;
  border: 2px solid #2a2d45;
  border-radius: 14px;
  padding: 24px 20px;
  text-align: left;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.mode-card:hover:not(.disabled) {
  border-color: #6366f1;
  background: #1e2140;
}
.mode-card.selected {
  border-color: #6366f1;
  background: #1e2140;
}
.mode-card.disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.mode-card-icon { font-size: 28px; }
.mode-card-title {
  font-size: 16px;
  font-weight: 700;
  color: #e8eaf0;
}
.mode-card-desc {
  font-size: 13px;
  color: #7a82a0;
  line-height: 1.5;
}
.mode-card-badge {
  position: absolute;
  top: 12px;
  right: 12px;
  background: #4f6ef7;
  color: #fff;
  font-size: 11px;
  padding: 2px 8px;
  border-radius: 20px;
  font-weight: 600;
}
.disabled-badge { background: #3a3d55; color: #7a82a0; }
.dynamic-badge { background: #7c3aed; }

/* ── Done area ── */
.done-area { max-width: 560px; }
.done-icon { font-size: 48px; }
.done-area h2 { font-size: 22px; font-weight: 700; }

.brief-preview {
  width: 100%;
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 10px;
  padding: 16px 20px;
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 8px 0 16px;
}
.brief-preview h3 {
  font-size: 13px;
  font-weight: 600;
  color: #7a82a0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin: 0 0 4px;
}
.brief-row {
  display: flex;
  gap: 12px;
  font-size: 14px;
  line-height: 1.5;
}
.brief-key {
  color: #7a82a0;
  min-width: 80px;
  flex-shrink: 0;
}
.brief-val { color: #c8ccdd; }

/* ── Static question card ── */
.question-area {
  width: 100%;
  max-width: 600px;
}
.question-card {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 14px;
  padding: 32px 28px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.question-text {
  font-size: 18px;
  font-weight: 600;
  line-height: 1.5;
  color: #e8eaf0;
}

/* Options */
.options-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.option-btn {
  text-align: left;
  background: #0f1117;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  color: #c8ccdd;
  font-size: 15px;
  padding: 12px 16px;
  cursor: pointer;
  transition: border-color 0.2s, background 0.2s;
}
.option-btn:hover { border-color: #4f6ef7; background: #141729; }
.option-btn.selected {
  border-color: #6366f1;
  background: #1a2060;
  color: #e8eaf0;
}

/* Textarea */
.input-area { display: flex; flex-direction: column; gap: 6px; }
.answer-textarea {
  width: 100%;
  background: #0f1117;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  color: #e8eaf0;
  font-size: 15px;
  padding: 12px 14px;
  resize: vertical;
  transition: border-color 0.2s;
  font-family: inherit;
  box-sizing: border-box;
}
.answer-textarea:focus {
  outline: none;
  border-color: #6366f1;
}
.input-hint { font-size: 12px; color: #4a5070; }

/* Footer */
.question-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* ── Dynamic mode ── */
.dynamic-area {
  width: 100%;
  max-width: 680px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  height: calc(100vh - 130px);
}

/* Chat history */
.chat-history {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 8px 0 4px;
  scroll-behavior: smooth;
}
.chat-history::-webkit-scrollbar { width: 4px; }
.chat-history::-webkit-scrollbar-track { background: transparent; }
.chat-history::-webkit-scrollbar-thumb { background: #2a2d45; border-radius: 2px; }

/* Chat bubbles */
.chat-bubble {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}
.chat-bubble.user {
  flex-direction: row-reverse;
}
.bubble-avatar {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 700;
  flex-shrink: 0;
}
.assistant .bubble-avatar {
  background: linear-gradient(135deg, #6366f1, #7c3aed);
  color: #fff;
}
.user .bubble-avatar {
  background: #1e2130;
  border: 1px solid #2a2d45;
  color: #7a82a0;
}
.bubble-body { max-width: 80%; }
.bubble-text {
  padding: 12px 16px;
  border-radius: 12px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
}
.assistant .bubble-text {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  color: #e8eaf0;
  border-top-left-radius: 2px;
}
.user .bubble-text {
  background: #2a3a80;
  border: 1px solid #3a4aa0;
  color: #e8eaf0;
  border-top-right-radius: 2px;
}

/* Typing indicator */
.typing-dots {
  display: flex;
  gap: 5px;
  align-items: center;
  height: 20px;
}
.typing-dots span {
  width: 7px;
  height: 7px;
  background: #6366f1;
  border-radius: 50%;
  animation: bounce-dot 1.2s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce-dot {
  0%, 80%, 100% { transform: scale(0.6); opacity: 0.4; }
  40% { transform: scale(1); opacity: 1; }
}

/* Dynamic input wrap */
.dynamic-input-wrap {
  background: #1a1d2e;
  border: 1px solid #2a2d45;
  border-radius: 12px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}
.dynamic-options { gap: 8px; }
.dynamic-footer {
  margin-top: 4px;
  padding-top: 10px;
  border-top: 1px solid #2a2d45;
}
.dynamic-text-input { display: flex; flex-direction: column; gap: 8px; }
.dynamic-text-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}
.err-msg-dynamic {
  text-align: center;
  margin-top: 4px;
}

/* ── Buttons ── */
.btn-primary {
  background: #4f6ef7;
  color: #fff;
  border: none;
  border-radius: 8px;
  padding: 10px 22px;
  font-size: 15px;
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
.btn-ghost {
  background: none;
  color: #7a82a0;
  border: 1px solid #2a2d45;
  border-radius: 8px;
  padding: 10px 18px;
  font-size: 14px;
  cursor: pointer;
  transition: color 0.2s, border-color 0.2s;
}
.btn-ghost:hover { color: #c8ccdd; border-color: #4a5070; }
.btn-sm {
  padding: 7px 14px !important;
  font-size: 13px !important;
}

/* Mini spinner */
.mini-spin {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* Err */
.err-msg {
  color: #f87171;
  font-size: 13px;
}

/* Slide transition */
.slide-up-enter-active, .slide-up-leave-active {
  transition: all 0.22s ease;
}
.slide-up-enter-from {
  opacity: 0;
  transform: translateY(12px);
}
.slide-up-leave-to {
  opacity: 0;
  transform: translateY(-8px);
}
</style>
