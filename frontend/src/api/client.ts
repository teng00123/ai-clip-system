import axios from 'axios'
import { useAuthStore } from '@/stores/auth'
import router from '@/router'

const client = axios.create({
  baseURL: '/api',
  timeout: 30000,
})

client.interceptors.request.use((config) => {
  const authStore = useAuthStore()
  if (authStore.token) {
    config.headers.Authorization = `Bearer ${authStore.token}`
  }
  return config
})

client.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      const authStore = useAuthStore()
      authStore.logout()
      router.push('/login')
    }
    return Promise.reject(error)
  }
)

export default client
