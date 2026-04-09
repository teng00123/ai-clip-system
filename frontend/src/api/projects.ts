import client from './client'
import type { Project } from '@/types'

export const createProject = (name: string, description?: string) =>
  client.post<Project>('/projects', { name, description })

export const listProjects = () => client.get<Project[]>('/projects')

export const getProject = (id: string) => client.get<Project>(`/projects/${id}`)

export const updateProject = (id: string, data: Partial<Project>) =>
  client.patch<Project>(`/projects/${id}`, data)

export const deleteProject = (id: string) => client.delete(`/projects/${id}`)
