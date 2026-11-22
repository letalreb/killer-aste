import { apiClient } from './client'
import type { FavoriteItem } from '../store/favoritesStore'

export interface FavoritesResponse {
  max_favorites: number
  items: FavoriteItem[]
}

export const favoritesApi = {
  list: async (): Promise<FavoritesResponse> => {
    const { data } = await apiClient.get<FavoritesResponse>('/api/v1/favorites')
    return data
  },
  add: async (auctionId: string): Promise<FavoritesResponse> => {
    const { data } = await apiClient.put<FavoritesResponse>(`/api/v1/favorites/${auctionId}`)
    return data
  },
  remove: async (auctionId: string): Promise<void> => {
    await apiClient.delete(`/api/v1/favorites/${auctionId}`)
  },
  clear: async (): Promise<void> => {
    await apiClient.delete('/api/v1/favorites')
  },
}
