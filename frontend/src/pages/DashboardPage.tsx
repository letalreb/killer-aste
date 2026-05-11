import { useState, useMemo, useCallback, useEffect, useRef } from 'react'
import { Header } from '../components/Header'
import { KPIBox } from '../components/KPIBox'
import { AuctionCard } from '../components/AuctionCard'
import { FilterPanel } from '../components/FilterPanel'
import { ActiveFilters, countActiveFilters } from '../components/ActiveFilters'
import { MapView } from '../components/MapView'
import { useAuctions } from '../hooks/useAuctions'
import { useFavoritesStore } from '../store/favoritesStore'
import { formatCurrency, getROI, getOverallScore } from '../utils/formatters'
import type { FilterState } from '../types/api'

const DEFAULT_FILTERS: FilterState = {
  minRoi: 0,
  riskLevel: 'all',
  city: '',
  minPrice: 0,
  maxPrice: 0,
  sortBy: 'date',
  showPast: false,
  daysAhead: 30,
}

const SKELETON_IDS = Array.from({ length: 6 }, (_, i) => `skeleton-${i}`)

type ViewMode = 'cards' | 'map'

export function DashboardPage() {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS)
  const [showFilters, setShowFilters] = useState(false)
  const [viewMode, setViewMode] = useState<ViewMode>('cards')
  const [showOnlyFavorites, setShowOnlyFavorites] = useState(false)

  const { items, loading, loadingMore, hasMore, loadMore, error, refresh } = useAuctions(filters)

  const favoriteItems = useFavoritesStore((s) => s.items)
  const favoriteIds = useMemo(() => new Set(favoriteItems.map((i) => i.id)), [favoriteItems])

  // Favorites filter applied client-side only (no backend trip needed)
  const auctions = useMemo(
    () => showOnlyFavorites ? items.filter((a) => favoriteIds.has(a.id)) : items,
    [items, showOnlyFavorites, favoriteIds],
  )

  const kpis = useMemo(() => {
    if (items.length === 0) return null
    const rois = items.map((a) => getROI(a)).filter((r): r is number => r != null)
    const avgRoi = rois.length ? rois.reduce((a, b) => a + b, 0) / rois.length : 0
    const bestRoi = rois.length ? Math.max(...rois) : 0
    const prices = items.map((a) => Number(a.base_price)).filter((p) => !Number.isNaN(p) && p > 0)
    const avgPrice = prices.length ? prices.reduce((a, b) => a + b, 0) / prices.length : 0
    const topDeal = [...items].sort((a, b) => getOverallScore(b) - getOverallScore(a))[0]
    return { avgRoi, bestRoi, avgPrice, topCity: topDeal?.property?.city ?? '—' }
  }, [items])

  // ── Infinite scroll sentinel ──────────────────────────────────────────────
  // Use a ref so the observer callback always sees the latest loadMore without
  // needing to recreate the observer every time loadMore changes identity.
  const loadMoreRef = useRef(loadMore)
  useEffect(() => { loadMoreRef.current = loadMore }, [loadMore])

  const observerRef = useRef<IntersectionObserver | null>(null)

  // Callback ref fires whenever the sentinel node mounts or unmounts,
  // ensuring the observer is attached even though the sentinel starts hidden.
  const sentinelRef = useCallback((node: HTMLDivElement | null) => {
    observerRef.current?.disconnect()
    if (!node) return
    observerRef.current = new IntersectionObserver(
      (entries) => { if (entries[0]?.isIntersecting) loadMoreRef.current() },
      { rootMargin: '200px' },
    )
    observerRef.current.observe(node)
  }, [])

  const setFiltersAndReset = useCallback((f: FilterState) => setFilters(f), [])

  const activeFilterCount = countActiveFilters(filters)

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      <Header />

      <main className="flex-1 max-w-[1400px] mx-auto w-full px-3 sm:px-4 lg:px-6 py-4 sm:py-6 space-y-4 sm:space-y-6">

        {/* KPI row */}
        {kpis && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
            <KPIBox
              label="Aste caricate"
              value={auctions.length === items.length
                ? items.length
                : `${auctions.length} / ${items.length}`}
              sub={hasMore && !showOnlyFavorites ? 'Scorri per caricare altre' : undefined}
              accent="blue"
            />
            <KPIBox label="ROI medio" value={`${kpis.avgRoi.toFixed(1)}%`} accent="green" />
            <KPIBox label="Best ROI" value={`${kpis.bestRoi.toFixed(1)}%`} accent="green" />
            <KPIBox
              label="Prezzo medio"
              value={formatCurrency(kpis.avgPrice)}
              sub={`Top: ${kpis.topCity}`}
              accent="amber"
            />
          </div>
        )}

        {/* Layout: sidebar + content */}
        <div className="flex gap-5 items-start">

          {/* Desktop filter sidebar */}
          {viewMode === 'cards' && (
            <div className="hidden lg:block sticky top-16 flex-shrink-0">
              <FilterPanel filters={filters} onChange={setFiltersAndReset} />
            </div>
          )}

          {/* Main column */}
          <div className={`flex-1 min-w-0 space-y-3 ${viewMode === 'map' ? 'flex flex-col' : ''}`}>

            {/* Toolbar */}
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <div className="text-sm text-slate-400">
                {loading ? (
                  <span className="animate-pulse">Caricamento…</span>
                ) : (
                  <>
                    <span className="font-medium text-slate-300">{auctions.length}</span>
                    <span className="text-slate-500"> aste</span>
                    {hasMore && !showOnlyFavorites && (
                      <span className="text-slate-600 ml-1">— altri disponibili</span>
                    )}
                  </>
                )}
              </div>

              <div className="flex items-center gap-2">
                {favoriteIds.size > 0 && (
                  <button
                    onClick={() => setShowOnlyFavorites((v) => !v)}
                    aria-pressed={showOnlyFavorites}
                    className={`px-2.5 py-1.5 text-xs flex items-center gap-1.5 border rounded-lg transition-colors ${
                      showOnlyFavorites
                        ? 'bg-rose-500/20 border-rose-500/50 text-rose-400'
                        : 'border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-600'
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill={showOnlyFavorites ? 'currentColor' : 'none'} viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z" />
                    </svg>
                    <span className="hidden sm:inline">Preferiti</span>
                    <span className="font-semibold">{favoriteIds.size}</span>
                  </button>
                )}

                {/* View toggle */}
                <div className="flex items-center border border-surface-border rounded-lg overflow-hidden">
                  <button
                    onClick={() => setViewMode('cards')}
                    aria-pressed={viewMode === 'cards'}
                    className={`px-2.5 py-1.5 text-xs flex items-center gap-1.5 transition-colors ${
                      viewMode === 'cards' ? 'bg-emerald-700/30 text-emerald-300' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M4 6h16M4 10h16M4 14h16M4 18h16" />
                    </svg>
                    <span className="hidden sm:inline">Card</span>
                  </button>
                  <button
                    onClick={() => setViewMode('map')}
                    aria-pressed={viewMode === 'map'}
                    className={`px-2.5 py-1.5 text-xs flex items-center gap-1.5 transition-colors border-l border-surface-border ${
                      viewMode === 'map' ? 'bg-emerald-700/30 text-emerald-300' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                    </svg>
                    <span className="hidden sm:inline">Mappa</span>
                  </button>
                </div>

                <button
                  onClick={refresh}
                  disabled={loading}
                  className="text-xs text-slate-500 hover:text-slate-300 px-2.5 py-1.5 border border-surface-border rounded-lg hover:border-slate-600 transition-colors disabled:opacity-40"
                >
                  ↻ Aggiorna
                </button>

                <button
                  onClick={() => setShowFilters(true)}
                  className="lg:hidden relative text-xs text-slate-300 px-2.5 py-1.5 border border-surface-border rounded-lg hover:border-slate-500 transition-colors flex items-center gap-1.5"
                >
                  <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 4h18M7 12h10M10 20h4" />
                  </svg>
                  Filtri
                  {activeFilterCount > 0 && (
                    <span className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-emerald-500 text-white text-[9px] font-bold flex items-center justify-center">
                      {activeFilterCount}
                    </span>
                  )}
                </button>
              </div>
            </div>

            <ActiveFilters filters={filters} onChange={setFiltersAndReset} />

            {/* Error */}
            {error && (
              <div className="rounded-xl border border-red-800/50 bg-red-900/20 px-4 py-3 text-red-400 text-sm flex items-center gap-2">
                <span>⚠</span>
                <span>{error}</span>
                <button onClick={refresh} className="ml-auto text-xs underline opacity-70 hover:opacity-100">
                  Riprova
                </button>
              </div>
            )}

            {/* Loading skeleton */}
            {loading && viewMode === 'cards' && (
              <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                {SKELETON_IDS.map((id, i) => (
                  <div
                    key={id}
                    className="bg-surface-card border border-surface-border rounded-xl h-52 animate-pulse"
                    style={{ animationDelay: `${i * 50}ms` }}
                  />
                ))}
              </div>
            )}

            {loading && viewMode === 'map' && (
              <div className="h-[calc(100vh-280px)] rounded-xl bg-surface-card border border-surface-border animate-pulse" />
            )}

            {/* Empty state */}
            {!loading && !error && auctions.length === 0 && (
              <div className="text-center py-20 text-slate-600">
                <div className="text-5xl mb-4">🔍</div>
                <div className="text-sm text-slate-500 mb-3">Nessuna asta trovata.</div>
                {activeFilterCount > 0 && (
                  <button
                    onClick={() => setFiltersAndReset(DEFAULT_FILTERS)}
                    className="text-xs text-emerald-500 hover:text-emerald-400 underline"
                  >
                    Azzera i filtri
                  </button>
                )}
              </div>
            )}

            {/* Map view */}
            {!loading && viewMode === 'map' && auctions.length > 0 && (
              <div className="h-[calc(100vh-280px)] min-h-[480px] flex">
                <MapView auctions={auctions} />
              </div>
            )}

            {/* Cards + infinite scroll */}
            {viewMode === 'cards' && auctions.length > 0 && (
              <>
                <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-3">
                  {auctions.map((a, i) => (
                    <AuctionCard key={a.id} auction={a} rank={i + 1} />
                  ))}
                </div>

                {/* Sentinel — triggers loadMore via IntersectionObserver */}
                {!showOnlyFavorites && (
                  <div ref={sentinelRef} className="h-1" />
                )}

                {/* Spinner while fetching next page */}
                {loadingMore && (
                  <div className="flex justify-center py-6">
                    <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
                  </div>
                )}

                {/* End-of-list message */}
                {!hasMore && !loadingMore && items.length > 0 && !showOnlyFavorites && (
                  <p className="text-center text-xs text-slate-600 py-4">
                    Tutte le {items.length} aste caricate
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      </main>

      {/* Mobile filter bottom sheet */}
      {showFilters && (
        <>
          <button
            type="button"
            aria-label="Chiudi filtri"
            className="fixed inset-0 bg-black/70 z-40 lg:hidden w-full cursor-default"
            onClick={() => setShowFilters(false)}
          />
          <div className="fixed bottom-0 left-0 right-0 z-50 bg-surface-card border-t border-surface-border rounded-t-2xl lg:hidden flex flex-col max-h-[85vh]">
            <div className="flex justify-center pt-2 pb-1 flex-shrink-0">
              <div className="w-10 h-1 rounded-full bg-slate-700" />
            </div>
            <div className="flex items-center justify-between px-5 py-3 border-b border-surface-border flex-shrink-0">
              <span className="text-sm font-semibold text-slate-200">
                Filtri
                {activeFilterCount > 0 && (
                  <span className="ml-2 text-xs text-emerald-400">({activeFilterCount} attivi)</span>
                )}
              </span>
              <button onClick={() => setShowFilters(false)} className="text-slate-500 hover:text-slate-200 transition-colors p-1">
                ✕
              </button>
            </div>
            <div className="overflow-y-auto flex-1 px-5 py-4">
              <FilterPanel filters={filters} onChange={setFiltersAndReset} />
            </div>
            <div className="px-5 py-4 border-t border-surface-border flex-shrink-0">
              <button
                onClick={() => setShowFilters(false)}
                className="w-full py-3 rounded-xl bg-emerald-700 hover:bg-emerald-600 text-white text-sm font-semibold transition-colors"
              >
                Vedi {auctions.length} aste
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
