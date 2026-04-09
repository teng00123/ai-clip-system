import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Script } from '@/types'
import * as api from '@/api/scripts'

export const useScriptStore = defineStore('script', () => {
  const script = ref<Script | null>(null)
  const loading = ref(false)
  const generating = ref(false)

  async function generateScript(projectId: string) {
    generating.value = true
    try {
      const res = await api.generateScript(projectId)
      script.value = res.data
      return res.data
    } finally {
      generating.value = false
    }
  }

  async function loadLatestScript(projectId: string) {
    loading.value = true
    try {
      const res = await api.getLatestScript(projectId)
      script.value = res.data
    } catch {
      script.value = null
    } finally {
      loading.value = false
    }
  }

  async function saveScript(scriptId: string, content: object) {
    const res = await api.updateScript(scriptId, content)
    script.value = res.data
  }

  return { script, loading, generating, generateScript, loadLatestScript, saveScript }
})
