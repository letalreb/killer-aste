import { useFavoritesStore, MAX_FAVORITES, type FavoriteItem } from '../store/favoritesStore'

interface Props {
  readonly item: FavoriteItem
  readonly size?: 'sm' | 'md'
}

export function FavoriteButton({ item, size = 'md' }: Props) {
  const { has, isFull, toggle } = useFavoritesStore()
  const isFav = has(item.id)
  const full = isFull()
  const disabled = !isFav && full

  const dim = size === 'sm' ? 'w-7 h-7' : 'w-8 h-8'
  const icon = size === 'sm' ? 'w-3.5 h-3.5' : 'w-4 h-4'

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        e.preventDefault()
        toggle(item)
      }}
      disabled={disabled}
      title={
        isFav
          ? 'Rimuovi dai preferiti'
          : disabled
          ? `Massimo ${MAX_FAVORITES} preferiti raggiunto`
          : 'Aggiungi ai preferiti'
      }
      className={`
        ${dim} rounded-full flex items-center justify-center transition-all
        ${isFav
          ? 'bg-rose-500/20 border border-rose-500/50 text-rose-400 hover:bg-rose-500/30'
          : disabled
          ? 'bg-slate-800/60 border border-surface-border text-slate-600 cursor-not-allowed'
          : 'bg-slate-800/60 border border-surface-border text-slate-500 hover:text-rose-400 hover:border-rose-500/50 hover:bg-rose-500/10'
        }
      `}
      aria-pressed={isFav}
      aria-label={isFav ? 'Rimuovi dai preferiti' : 'Aggiungi ai preferiti'}
    >
      <svg
        className={icon}
        fill={isFav ? 'currentColor' : 'none'}
        viewBox="0 0 24 24"
        stroke="currentColor"
        strokeWidth={2}
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          d="M4.318 6.318a4.5 4.5 0 000 6.364L12 20.364l7.682-7.682a4.5 4.5 0 00-6.364-6.364L12 7.636l-1.318-1.318a4.5 4.5 0 00-6.364 0z"
        />
      </svg>
    </button>
  )
}
