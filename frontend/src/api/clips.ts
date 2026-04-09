import client from './client'
import type { ClipJob } from '@/types'

export const submitClipJob = (projectId: string, videoId: string) =>
  client.post<ClipJob>('/clips', { project_id: projectId, video_id: videoId })

export const getClipJob = (jobId: string) =>
  client.get<ClipJob>(`/clips/${jobId}`)

export const listProjectJobs = (projectId: string) =>
  client.get<ClipJob[]>(`/clips/project/${projectId}`)

export const getDownloadUrl = (jobId: string) =>
  client.get<{ url: string }>(`/clips/${jobId}/download-url`)
