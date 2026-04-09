import client from './client'
import type { Script } from '@/types'

export const generateScript = (projectId: string) =>
  client.post<Script>(`/scripts/generate/${projectId}`)

export const listScripts = (projectId: string) =>
  client.get<Script[]>(`/scripts/${projectId}`)

export const getLatestScript = (projectId: string) =>
  client.get<Script>(`/scripts/${projectId}/latest`)

export const updateScript = (scriptId: string, content: object) =>
  client.patch<Script>(`/scripts/${scriptId}`, { content })

export const rewriteSection = (scriptId: string, sectionContent: string, instruction: string) =>
  client.post(`/scripts/${scriptId}/rewrite-section`, { section_content: sectionContent, instruction })
