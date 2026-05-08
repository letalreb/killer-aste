import { apiClient } from './client'
import type { Auction, AuctionStats } from '../types/api'

export interface AuctionFilters {
  status?: string
  province?: string
  min_roi?: number
  page?: number
  page_size?: number
}

const PAGE_SIZE = 200

export const auctionsApi = {
  list: async (filters: AuctionFilters = {}): Promise<Auction[]> => {
    const all: Auction[] = []
    let page = 1
    while (true) {
      const params = { status: 'scheduled', page_size: PAGE_SIZE, page, ...filters }
      const { data } = await apiClient.get<Auction[]>('/api/v1/auctions', { params })
      all.push(...data)
      if (data.length < PAGE_SIZE) break
      page++
    }
    return all
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
