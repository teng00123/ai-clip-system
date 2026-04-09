import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Project } from '@/types'
import * as api from '@/api/projects'

export const useProjectStore = defineStore('project', () => {
  const projects = ref<Project[]>([])
  const currentProject = ref<Project | null>(null)
  const loading = ref(false)

  async function fetchProjects() {
    loading.value = true
    const res = await api.listProjects()
    projects.value = res.data
    loading.value = false
  }

  async function createProject(name: string, description?: string) {
    const res = await api.createProject(name, description)
    projects.value.unshift(res.data)
    return res.data
  }

  async function selectProject(id: string) {
    const res = await api.getProject(id)
    currentProject.value = res.data
    return res.data
  }

  async function deleteProject(id: string) {
    await api.deleteProject(id)
    projects.value = projects.value.filter(p => p.id !== id)
    if (currentProject.value?.id === id) currentProject.value = null
  }

  return { projects, currentProject, loading, fetchProjects, createProject, selectProject, deleteProject }
})
