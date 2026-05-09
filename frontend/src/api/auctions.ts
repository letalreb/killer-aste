import { apiClient } from './client'
import type { Auction, AuctionStats } from '../types/api'

export interface AuctionFilters {
  status?: string
  province?: string
  city?: string
  min_roi?: number
  min_price?: number
  max_price?: number
  max_risk_grade?: string
  sort_by?: string
  days_ahead?: number
  show_past?: boolean
  page?: number
  page_size?: number
}

export const auctionsApi = {
  list: async (filters: AuctionFilters = {}): Promise<Auction[]> => {
    const { data } = await apiClient.get<Auction[]>('/api/v1/auctions', { params: filters })
    return data
  },

  getById: async (id: string): Promise<Auction> => {
    const { data } = await apiClient.get<Auction>(`/api/v1/auctions/${id}`)
    return data
  },

  getStats: async (): Promise<AuctionStats> => {
    const { data } = await apiClient.get<AuctionStats>('/api/v1/auctions/stats')
    return data
  },
}
