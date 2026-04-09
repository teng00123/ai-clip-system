<template>
  <div class="guide-page">
    <!-- 顶部导航 -->
    <div class="guide-header">
      <button class="btn-back" @click="router.push('/dashboard')">← 返回</button>
      <span class="guide-title">创作向导</span>
      <span class="step-counter" v-if="question">{{ question.step + 1 }} / {{ question.total_steps }}</span>
    </div>

    <!-- 进度条 -->
    <div class="progress-bar-wrap" v-if="question">
      <div class="progress-bar" :style="{ width: progressPct + '%' }"></div>
    </div>

    <!-- 主体区 -->
    <div class="guide-body">

      <!-- 加载中 -->
      <div v-if="guideStore.loading || initializing" class="center-area">
        <div class="spinner"></div>
        <p class="hint">加载中…</p>
      </div>

      <!-- 已完成 -->
      <div v-else-if="guideStore.session?.completed" class="center-area done-area">
        <div class="done-icon">🎉</div>
        <h2>问答完成！</h2>
        <p class="hint">素材已收集完毕，正在为你生成创作简报。</p>
        <div v-if="brief" class="brief-preview">
          <h3>创作简报</h3>
          <div class="brief-row" v-for="(v, k) in brief" :key="k">
            <span class="brief-key">{{ briefKeyLabel(String(k)) }}</span>
            <span class="brief-val">{{ v }}</span>
          </div>
        </div>
        <button class="btn-primary btn-lg" @click="goToScript">去生成剧本 →</button>
      </div>

      <!-- 答题区 -->
      <div v-else-if="question" class="question-area">
        <transition name="slide-up" mode="out-in">
          <div :key="question.step" class="question-card">
            <p class="question-text">{{ question.question_text }}</p>

            <!-- 单选题 -->
            <div v-if="question.question_type === 'single_choice'" class="options-list">
              <button
                v-for="opt in question.options"
                :key="opt"
                :class="['option-btn', { selected: answer === opt }]"
                @click="answer = opt"
              >{{ opt }}</button>
            </div>

            <!-- 文本输入题 -->
            <div v-else class="input-area">
              <textarea
                v-model="answer"
                :placeholder="inputPlaceholder"
                rows="4"
                class="answer-textarea"
                @keydown.ctrl.enter="submitIfReady"
              ></textarea>
              <p class="input-hint">Ctrl + Enter 提交</p>
            </div>

            <!-- 错误提示 -->
            <p v-if="errMsg" class="err-msg">{{ errMsg }}</p>

            <!-- 操作栏 -->
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
                <span v-else>{{ isLastStep ? '完成' : '下一步 →' }}</span>
              </button>
            </div>
          </div>
        </transition>
      </div>

      <!-- 兜底空态 -->
      <div v-else class="center-area">
        <p class="hint">暂无问题</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useGuideStore } from '@/stores/guide'
import * as guideApi from '@/api/guide'

const route = useRoute()
const router = useRouter()
const guideStore = useGuideStore()

const projectId = route.params.projectId as string
const answer = ref('')
const submitting = ref(false)
const errMsg = ref('')
const initializing = ref(true)
const brief = ref<Record<string, string> | null>(null)

const question = computed(() => guideStore.currentQuestion)

const progressPct = computed(() => {
  if (!question.value) return 0
  return Math.round(((question.value.step + 1) / question.value.total_steps) * 100)
})

const isLastStep = computed(() => {
  if (!question.value) return false
  return question.value.step + 1 >= question.value.total_steps
})

const canSubmit = computed(() => answer.value.trim().length > 0)

const inputPlaceholder = computed(() => {
  if (!question.value) return '请输入你的回答…'
  const s = question.value.step
  const hints: Record<number, string> = {
    1: '例如：宠物博主、美食探店、职场干货…',
    2: '例如：18~35岁上班族，喜欢健康生活…',
    3: '例如如：让更多人了解我的手工皂品牌',
    5: '例如：轻松幽默、真诚分享、干货满满…',
    7: '例如：欢迎点赞关注，评论你的想法！',
  }
  return hints[s] || '请输入你的回答…'
})

onMounted(async () => {
  guideStore.reset()
  try {
    await guideStore.startGuide(projectId)
    if (guideStore.session?.completed) {
      await loadBrief()
    }
  } catch (e) {
    errMsg.value = '加载失败，请刷新重试'
  } finally {
    initializing.value = false
  }
})

async function submit() {
  if (!canSubmit.value || submitting.value || !question.value) return
  errMsg.value = ''
  submitting.value = true
  try {
    await guideStore.submitAnswer(projectId, question.value.step, answer.value.trim())
    answer.value = ''
    if (guideStore.session?.completed) {
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

const briefKeyMap: Record<string, string> = {
  content_type: '内容类型',
  target_audience: '目标受众',
  core_goal: '核心目标',
  key_message: '核心信息',
  tone_style: '风格调性',
  product_name: '产品/品牌',
  cta: '行动号召',
  extra_notes: '补充说明',
}
function briefKeyLabel(k: string) {
  return briefKeyMap[k] || k
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

/* Header */
.guide-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px 24px;
  border-bottom: 1px solid #1e2130;
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

/* Progress bar */
.progress-bar-wrap {
  height: 3px;
  background: #1e2130;
}
.progress-bar {
  height: 100%;
  background: linear-gradient(90deg, #4f6ef7, #7c3aed);
  transition: width 0.4s ease;
}

/* Body */
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

/* Done area */
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

/* Question card */
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
  border-color: #4f6ef7;
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
  border-color: #4f6ef7;
}
.input-hint { font-size: 12px; color: #4a5070; }

/* Footer */
.question-footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
}

/* Buttons */
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

/* Mini spinner in btn */
.mini-spin {
  display: inline-block;
  width: 14px;
  height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.7s linear infinite;
}

/* Error */
.err-msg {
  font-size: 13px;
  color: #f87171;
}

/* Slide transition */
.slide-up-enter-active,
.slide-up-leave-active {
  transition: opacity 0.25s ease, transform 0.25s ease;
}
.slide-up-enter-from { opacity: 0; transform: translateY(16px); }
.slide-up-leave-to   { opacity: 0; transform: translateY(-10px); }
</style>
