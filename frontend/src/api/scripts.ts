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

/** 新版按 index 改写段落（支持预览模式） */
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
