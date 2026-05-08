import type { FilterState } from '../types/api'

interface Props {
  readonly filters: FilterState
  readonly onChange: (f: FilterState) => void
}

const SORT_OPTIONS: { value: FilterState['sortBy']; label: string }[] = [
  { value: 'roi', label: 'ROI %' },
  { value: 'score', label: 'Punteggio' },
  { value: 'date', label: 'Data asta' },
  { value: 'price', label: 'Prezzo' },
]

const RISK_OPTIONS: { value: FilterState['riskLevel']; label: string }[] = [
  { value: 'all', label: 'Tutti' },
  { value: 'low', label: 'Basso' },
  { value: 'medium', label: 'Medio' },
  { value: 'high', label: 'Alto' },
]

export function FilterPanel({ filters, onChange }: Props) {
  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) =>
    onChange({ ...filters, [key]: value })

  return (
    <aside className="w-full lg:w-60 flex-shrink-0 space-y-5">
      <div>
        <span className="filter-label">Ordina per</span>
        <div className="grid grid-cols-2 gap-1 mt-1" role="group" aria-label="Ordina per">
          {SORT_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => set('sortBy', o.value)}
              aria-pressed={filters.sortBy === o.value}
              className={`px-2 py-1.5 text-xs rounded border transition-colors ${
                filters.sortBy === o.value
                  ? 'bg-emerald-700/30 border-emerald-600 text-emerald-300'
                  : 'border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <span className="filter-label">Rischio massimo</span>
        <div className="grid grid-cols-2 gap-1 mt-1" role="group" aria-label="Rischio massimo">
          {RISK_OPTIONS.map((o) => (
            <button
              key={o.value}
              onClick={() => set('riskLevel', o.value)}
              aria-pressed={filters.riskLevel === o.value}
              className={`px-2 py-1.5 text-xs rounded border transition-colors ${
                filters.riskLevel === o.value
                  ? 'bg-emerald-700/30 border-emerald-600 text-emerald-300'
                  : 'border-surface-border text-slate-400 hover:text-slate-200 hover:border-slate-600'
              }`}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label htmlFor="filter-roi" className="filter-label">
          ROI minimo ({filters.minRoi}%)
        </label>
        <input
          id="filter-roi"
          type="range"
          min={0}
          max={50}
          step={5}
          value={filters.minRoi}
          onChange={(e) => set('minRoi', Number(e.target.value))}
          className="w-full mt-2 accent-emerald-500"
        />
        <div className="flex justify-between text-[10px] text-slate-600 mt-0.5">
          <span>0%</span>
          <span>50%</span>
        </div>
      </div>

      <div>
        <label htmlFor="filter-city" className="filter-label">
          Città / Provincia
        </label>
        <input
          id="filter-city"
          type="text"
          placeholder="es. Milano, MI"
          value={filters.city}
          onChange={(e) => set('city', e.target.value)}
          className="mt-1 w-full bg-surface-card border border-surface-border rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-700"
        />
      </div>

      <div>
        <label htmlFor="filter-price" className="filter-label">
          Prezzo max (€)
        </label>
        <input
          id="filter-price"
          type="number"
          placeholder="es. 200000"
          value={filters.maxPrice || ''}
          onChange={(e) => set('maxPrice', Number(e.target.value))}
          className="mt-1 w-full bg-surface-card border border-surface-border rounded px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-emerald-700"
        />
      </div>

      <label className="flex items-center gap-2 cursor-pointer select-none group">
        <input
          type="checkbox"
          checked={filters.showPast}
          onChange={(e) => set('showPast', e.target.checked)}
          className="w-3.5 h-3.5 accent-emerald-500 rounded"
        />
        <span className="text-xs text-slate-400 group-hover:text-slate-200 transition-colors">
          Mostra date passate
        </span>
      </label>
    </aside>
  )
}
