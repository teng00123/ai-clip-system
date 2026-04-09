import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Question, GuideSession } from '@/types'
import * as api from '@/api/guide'

export const useGuideStore = defineStore('guide', () => {
  const session = ref<GuideSession | null>(null)
  const currentQuestion = ref<Question | null>(null)
  const loading = ref(false)

  async function startGuide(projectId: string) {
    loading.value = true
    const res = await api.startGuide(projectId)
    session.value = res.data
    await loadQuestion(projectId)
    loading.value = false
  }

  async function loadQuestion(projectId: string) {
    if (session.value?.completed) return
    const res = await api.getCurrentQuestion(projectId)
    currentQuestion.value = res.data
  }

  async function submitAnswer(projectId: string, step: number, answer: string) {
    const res = await api.submitAnswer(projectId, step, answer)
    session.value = res.data
    if (!res.data.completed) {
      await loadQuestion(projectId)
    }
  }

  function reset() {
    session.value = null
    currentQuestion.value = null
  }

  return { session, currentQuestion, loading, startGuide, submitAnswer, reset }
})
