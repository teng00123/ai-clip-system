import client from './client'
import type { Video } from '@/types'

export const uploadVideo = (projectId: string, file: File, onProgress?: (p: number) => void) => {
  const form = new FormData()
  form.append('file', file)
  return client.post<Video>(`/videos/${projectId}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
    onUploadProgress: (e) => {
      if (onProgress && e.total) {
        onProgress(Math.round((e.loaded / e.total) * 100))
      }
    },
  })
}

export const listVideos = (projectId: string) =>
  client.get<Video[]>(`/videos/${projectId}`)

export const getVideoUrl = (projectId: string, videoId: string) =>
  client.get<{ url: string }>(`/videos/${projectId}/${videoId}/url`)
