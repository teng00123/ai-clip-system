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

export interface SegmentPatch {
  id: number
  start: number
  end: number
  transcript?: string
}

/** 更新剪辑方案 (PATCH /clips/{jobId}/plan) */
export const patchClipPlan = (jobId: string, segments: SegmentPatch[]) =>
  client.patch<ClipJob>(`/clips/${jobId}/plan`, { segments })

/** 以当前 clip_plan 重新渲染视频 (POST /clips/{jobId}/rerender) */
export const rerenderClip = (jobId: string) =>
  client.post<ClipJob>(`/clips/${jobId}/rerender`)
