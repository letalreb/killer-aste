import { useNavigate } from 'react-router-dom'
import { useFavoritesStore, MAX_FAVORITES } from '../store/favoritesStore'
import { formatCurrency } from '../utils/formatters'

export function FavoritesBar() {
  const { items, remove } = useFavoritesStore()
  const navigate = useNavigate()

  if (items.length === 0) return null

  const slots = Array.from({ length: MAX_FAVORITES })
  const full = items.length === MAX_FAVORITES

  return (
    <div className="fixed bottom-0 left-0 right-0 z-[200] px-3 pb-3 pointer-events-none">
      <div className="max-w-[1400px] mx-auto">
        <div className="pointer-events-auto bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-2xl shadow-2xl px-4 py-3 flex items-center gap-3">

          {/* Label */}
          <div className="flex-shrink-0 hidden sm:block">
            <div className="text-[10px] text-slate-500 uppercase tracking-wider">Preferiti</div>
            <div className={`text-xs font-semibold ${full ? 'text-rose-400' : 'text-slate-300'}`}>
              {items.length}/{MAX_FAVORITES}
            </div>
          </div>

          <div className="w-px h-8 bg-slate-700 hidden sm:block flex-shrink-0" />

          {/* Slots */}
          <div className="flex-1 flex items-center gap-2 min-w-0">
            {slots.map((_, idx) => {
              const item = items[idx]
              if (!item) {
                return (
                  <div
                    key={`empty-${idx}`}
                    className="flex-1 min-w-0 h-12 rounded-xl border border-dashed border-slate-700 flex items-center justify-center"
                  >
                    <span className="text-xs text-slate-700">+</span>
                  </div>
                )
              }
              return (
                <button
                  key={item.id}
                  type="button"
                  onClick={() => navigate(`/auctions/${item.id}`)}
                  className="group flex-1 min-w-0 h-12 rounded-xl bg-slate-800 border border-slate-600 hover:border-emerald-600 transition-colors px-3 flex items-center gap-2 relative"
                >
                  {/* Remove */}
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); remove(item.id) }}
                    aria-label="Rimuovi"
                    className="absolute -top-1.5 -right-1.5 w-4 h-4 rounded-full bg-slate-700 border border-slate-600 text-slate-400 hover:text-white hover:bg-rose-600 hover:border-rose-500 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-all text-[10px] leading-none"
                  >
                    ×
                  </button>

                  {/* Content */}
                  <div className="min-w-0 flex-1 text-left">
                    <div className="text-xs font-medium text-slate-200 truncate leading-tight">
                      {item.label}
                    </div>
                    <div className="text-[10px] text-slate-500 leading-tight">
                      {item.base_price ? formatCurrency(item.base_price) : '—'}
                      {item.roi != null && (
                        <span className={`ml-1.5 font-semibold ${item.roi >= 20 ? 'text-emerald-400' : item.roi >= 10 ? 'text-amber-400' : 'text-slate-400'}`}>
                          {item.roi.toFixed(1)}%
                        </span>
                      )}
                    </div>
                  </div>
                </button>
              )
            })}
          </div>

          {/* Clear all */}
          <button
            type="button"
            onClick={() => useFavoritesStore.getState().clear()}
            className="flex-shrink-0 text-[10px] text-slate-600 hover:text-slate-400 transition-colors px-1"
            title="Svuota preferiti"
          >
            Svuota
          </button>
        </div>
      </div>
    </div>
  )
}
