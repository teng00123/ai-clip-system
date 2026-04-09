import client from './client'
import type { GuideSession, Question } from '@/types'

export const startGuide = (projectId: string) =>
  client.post<GuideSession>(`/guide/${projectId}/start`)

export const getCurrentQuestion = (projectId: string) =>
  client.get<Question>(`/guide/${projectId}/question`)

export const submitAnswer = (projectId: string, step: number, answer: string) =>
  client.post<GuideSession>(`/guide/${projectId}/answer`, { step, answer })

export const getBrief = (projectId: string) =>
  client.get(`/guide/${projectId}/brief`)

/** 获取当前 session（不创建新的） */
export const getSession = (projectId: string) =>
  client.get<GuideSession>(`/guide/${projectId}/session`)

/** 检查动态模式是否可用 */
export const checkDynamicAvailable = (projectId: string) =>
  client.get<{ available: boolean }>(`/guide/${projectId}/dynamic/available`)

/** 启动动态模式问答 */
export const startDynamic = (projectId: string) =>
  client.post(`/guide/${projectId}/dynamic/start`)

/** 动态模式提交答案 */
export const answerDynamic = (projectId: string, answer: string) =>
  client.post(`/guide/${projectId}/dynamic/answer`, { answer })
