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
