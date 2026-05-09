import { useState, useEffect, useCallback, useRef } from 'react'
import { auctionsApi, type AuctionFilters } from '../api/auctions'
import type { Auction, FilterState } from '../types/api'

const PAGE_SIZE = 200

function toApiFilters(f: FilterState, page: number): AuctionFilters {
  return {
    min_roi: f.minRoi > 0 ? f.minRoi : undefined,
    max_risk_grade: f.riskLevel !== 'all' ? f.riskLevel : undefined,
    city: f.city || undefined,
    min_price: f.minPrice > 0 ? f.minPrice : undefined,
    max_price: f.maxPrice > 0 ? f.maxPrice : undefined,
    sort_by: f.sortBy === 'score' ? 'roi' : f.sortBy,
    show_past: f.showPast ? true : undefined,
    days_ahead: f.showPast ? undefined : f.daysAhead,
    page,
    page_size: PAGE_SIZE,
  }
}

export function useAuctions(filters: FilterState) {
  const [items, setItems] = useState<Auction[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [hasMore, setHasMore] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const pageRef = useRef(1)
  const filtersRef = useRef(filters)
  filtersRef.current = filters

  const filtersKey = JSON.stringify(filters)

  useEffect(() => {
    pageRef.current = 1
    setItems([])
    setHasMore(true)
    setError(null)
    setLoading(true)

    auctionsApi
      .list(toApiFilters(filtersRef.current, 1))
      .then((data) => {
        setItems(data)
        setHasMore(data.length === PAGE_SIZE)
      })
      .catch(() => setError('Impossibile caricare le aste. Riprova.'))
      .finally(() => setLoading(false))
  // filtersKey is the stable serialized representation of filters
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filtersKey])

  const loadMore = useCallback(async () => {
    if (loadingMore || !hasMore) return
    const nextPage = pageRef.current + 1
    setLoadingMore(true)
    try {
      const data = await auctionsApi.list(toApiFilters(filtersRef.current, nextPage))
      setItems((prev) => [...prev, ...data])
      setHasMore(data.length === PAGE_SIZE)
      pageRef.current = nextPage
    } catch {
      setError('Errore nel caricamento di ulteriori aste.')
    } finally {
      setLoadingMore(false)
    }
  }, [loadingMore, hasMore])

  const refresh = useCallback(() => {
    pageRef.current = 1
    setItems([])
    setHasMore(true)
    setError(null)
    setLoading(true)
    auctionsApi
      .list(toApiFilters(filtersRef.current, 1))
      .then((data) => {
        setItems(data)
        setHasMore(data.length === PAGE_SIZE)
      })
      .catch(() => setError('Impossibile caricare le aste. Riprova.'))
      .finally(() => setLoading(false))
  }, [])

  return { items, loading, loadingMore, hasMore, loadMore, error, refresh }
}
