import clsx from 'clsx'

interface Props {
  page: number
  totalPages: number
  totalItems: number
  pageSize: number
  onPageChange: (page: number) => void
}

function pageNumbers(current: number, total: number): (number | '…')[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  if (current <= 4) return [1, 2, 3, 4, 5, '…', total]
  if (current >= total - 3) return [1, '…', total - 4, total - 3, total - 2, total - 1, total]
  return [1, '…', current - 1, current, current + 1, '…', total]
}

export function Pagination({ page, totalPages, totalItems, pageSize, onPageChange }: Props) {
  if (totalPages <= 1) return null

  const from = (page - 1) * pageSize + 1
  const to = Math.min(page * pageSize, totalItems)

  const btn = (p: number | '…', key: string | number) => {
    if (p === '…') {
      return (
        <span key={key} className="px-1 text-slate-600 text-sm select-none">
          …
        </span>
      )
    }
    const active = p === page
    return (
      <button
        key={key}
        onClick={() => onPageChange(p)}
        className={clsx(
          'w-8 h-8 rounded text-sm font-medium transition-colors',
          active
            ? 'bg-emerald-700 text-white'
            : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
        )}
      >
        {p}
      </button>
    )
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-4 border-t border-surface-border mt-4">
      {/* Result range */}
      <span className="text-xs text-slate-500 order-2 sm:order-1">
        {from}–{to} di {totalItems} aste
      </span>

      {/* Controls */}
      <div className="flex items-center gap-1 order-1 sm:order-2">
        {/* Prev */}
        <button
          onClick={() => onPageChange(page - 1)}
          disabled={page === 1}
          className="flex items-center gap-1 px-3 h-8 rounded text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          ← <span className="hidden sm:inline">Precedente</span>
        </button>

        {/* Page numbers — desktop */}
        <div className="hidden sm:flex items-center gap-0.5">
          {pageNumbers(page, totalPages).map((p, i) => btn(p, i))}
        </div>

        {/* Page indicator — mobile */}
        <span className="sm:hidden text-sm text-slate-400 px-3">
          {page} / {totalPages}
        </span>

        {/* Next */}
        <button
          onClick={() => onPageChange(page + 1)}
          disabled={page === totalPages}
          className="flex items-center gap-1 px-3 h-8 rounded text-sm text-slate-400 hover:text-slate-200 hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
        >
          <span className="hidden sm:inline">Successivo</span> →
        </button>
      </div>
    </div>
  )
}
