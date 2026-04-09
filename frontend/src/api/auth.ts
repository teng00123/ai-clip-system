import client from './client'
import type { TokenOut } from '@/types'

export const register = (email: string, password: string, nickname?: string) =>
  client.post<TokenOut>('/auth/register', { email, password, nickname })

export const login = (email: string, password: string) =>
  client.post<TokenOut>('/auth/login', { email, password })

export const getMe = () => client.get('/auth/me')
