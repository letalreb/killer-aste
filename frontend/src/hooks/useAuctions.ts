import { useState, useEffect, useCallback } from 'react'
import { auctionsApi, type AuctionFilters } from '../api/auctions'
import type { Auction, FilterState } from '../types/api'
import { getROI, getRiskGrade, getRiskScore, getOverallScore } from '../utils/formatters'

export function useAuctions() {
  const [allAuctions, setAllAuctions] = useState<Auction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetch = useCallback(async (filters?: AuctionFilters) => {
    setLoading(true)
    setError(null)
    try {
      const data = await auctionsApi.list(filters)
      setAllAuctions(data)
    } catch (e) {
      setError('Impossibile caricare le aste. Riprova.')
      console.error(e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetch()
  }, [fetch])

  return { allAuctions, loading, error, refresh: fetch }
}

export function applyFilters(auctions: Auction[], filters: FilterState): Auction[] {
  let result = [...auctions]

  if (!filters.showPast) {
    const now = new Date()
    result = result.filter((a) => {
      if (!a.auction_date) return true
      return new Date(a.auction_date) >= now
    })
  }

  if (filters.minRoi > 0) {
    result = result.filter((a) => (getROI(a) ?? 0) >= filters.minRoi)
  }

  if (filters.riskLevel !== 'all') {
    result = result.filter((a) => {
      const grade = getRiskGrade(getRiskScore(a))
      if (filters.riskLevel === 'low') return grade === 'low'
      if (filters.riskLevel === 'medium') return grade === 'low' || grade === 'medium'
      if (filters.riskLevel === 'high') return true
      return true
    })
  }

  if (filters.city) {
    const q = filters.city.toLowerCase()
    result = result.filter(
      (a) =>
        a.property?.city?.toLowerCase().includes(q) ||
        a.property?.province?.toLowerCase().includes(q)
    )
  }

  if (filters.minPrice > 0) {
    result = result.filter((a) => (a.base_price ?? 0) >= filters.minPrice)
  }

  if (filters.maxPrice > 0) {
    result = result.filter((a) => (a.base_price ?? 0) <= filters.maxPrice)
  }

  result.sort((a, b) => {
    switch (filters.sortBy) {
      case 'roi':
        return (getROI(b) ?? -Infinity) - (getROI(a) ?? -Infinity)
      case 'score':
        return getOverallScore(b) - getOverallScore(a)
      case 'price':
        return (a.base_price ?? 0) - (b.base_price ?? 0)
      case 'date': {
        const da = a.auction_date ? new Date(a.auction_date).getTime() : Infinity
        const db = b.auction_date ? new Date(b.auction_date).getTime() : Infinity
        return da - db
      }
      default:
        return 0
    }
  })

  return result
}
