import { apiClient } from './client'
import type { AuthResponse, User } from '../types/api'

export const authApi = {
  googleLogin: async (token: string): Promise<AuthResponse> => {
    const { data } = await apiClient.post<AuthResponse>('/auth/google', { token })
    return data
  },
  getMe: async (): Promise<User> => {
    const { data } = await apiClient.get<User>('/auth/me')
    return data
  },
}
