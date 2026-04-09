import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { User, TokenOut } from '@/types'
import { login as apiLogin, register as apiRegister } from '@/api/auth'

export const useAuthStore = defineStore('auth', () => {
  const token = ref<string | null>(localStorage.getItem('token'))
  const user = ref<User | null>(JSON.parse(localStorage.getItem('user') || 'null'))

  const isLoggedIn = computed(() => !!token.value)

  function setAuth(data: TokenOut) {
    token.value = data.access_token
    user.value = data.user
    localStorage.setItem('token', data.access_token)
    localStorage.setItem('user', JSON.stringify(data.user))
  }

  function logout() {
    token.value = null
    user.value = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }

  async function login(email: string, password: string) {
    const res = await apiLogin(email, password)
    setAuth(res.data)
  }

  async function register(email: string, password: string, nickname?: string) {
    const res = await apiRegister(email, password, nickname)
    setAuth(res.data)
  }

  return { token, user, isLoggedIn, login, register, logout }
})
