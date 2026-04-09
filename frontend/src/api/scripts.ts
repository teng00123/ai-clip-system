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

/** 旧版自由段落改写（保留兼容） */
export const rewriteSection = (scriptId: string, sectionContent: string, instruction: string) =>
  client.post(`/scripts/${scriptId}/rewrite-section`, { section_content: sectionContent, instruction })

/** 将 SSE 流式生成结束后前端拼接的完整 JSON 保存到 DB */
export const saveStreamedScript = (projectId: string, content: object, format: 'voiceover' | 'storyboard' = 'voiceover') =>
  client.post<Script>(`/scripts/generate/${projectId}/save`, { content, format })

/** SSE 流式生成剧本，返回 EventSource URL + token 头，供 fetch streaming 使用 */
export const getGenerateStreamUrl = (projectId: string) =>
  `/api/scripts/generate/${projectId}/stream`

/** SSE 流式段落改写，返回 fetch stream URL */
export const getRewriteStreamUrl = (scriptId: string) =>
  `/api/scripts/${scriptId}/rewrite/stream`
export interface ParagraphRewriteResult {
  script_id: string
  paragraph_index: number
  section_title: string
  original: string
  rewritten: string
  instruction: string
  applied: boolean
}

export const rewriteParagraph = (
  scriptId: string,
  paragraphIndex: number,
  instruction: string,
  preview = true,
) =>
  client.post<ParagraphRewriteResult>(`/scripts/${scriptId}/rewrite`, {
    paragraph_index: paragraphIndex,
    instruction,
    preview,
  })

/** 应用预览改写到 DB */
export const applyParagraphRewrite = (
  scriptId: string,
  paragraphIndex: number,
  rewrittenText: string,
) =>
  client.post<Script>(`/scripts/${scriptId}/rewrite/apply`, {
    paragraph_index: paragraphIndex,
    rewritten_text: rewrittenText,
  })
