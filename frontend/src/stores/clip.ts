import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { ClipJob, ClipProgress } from '@/types'
import * as api from '@/api/clips'

export const useClipStore = defineStore('clip', () => {
  const job = ref<ClipJob | null>(null)
  const progress = ref(0)
  const progressMessage = ref('')
  const loading = ref(false)
  let ws: WebSocket | null = null

  async function submitJob(projectId: string, videoId: string) {
    loading.value = true
    const res = await api.submitClipJob(projectId, videoId)
    job.value = res.data
    loading.value = false
    connectWs(res.data.id)
    return res.data
  }

  function connectWs(jobId: string) {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const token = localStorage.getItem('token')
    const query = token ? `?token=${encodeURIComponent(token)}` : ''
    ws = new WebSocket(`${proto}://${location.host}/ws/clip/${jobId}${query}`)
    ws.onmessage = (e) => {
      const data: ClipProgress = JSON.parse(e.data)
      progress.value = data.progress
      progressMessage.value = data.message
      if (data.progress === 100) {
        refreshJob(jobId)
        ws?.close()
      }
    }
  }

  async function refreshJob(jobId: string) {
    const res = await api.getClipJob(jobId)
    job.value = res.data
    progress.value = res.data.progress
  }

  async function getDownloadUrl(jobId: string) {
    const res = await api.getDownloadUrl(jobId)
    return res.data.url
  }

  function reset() {
    job.value = null
    progress.value = 0
    progressMessage.value = ''
    ws?.close()
  }

  return { job, progress, progressMessage, loading, submitJob, refreshJob, getDownloadUrl, connectWs, reset }
})
