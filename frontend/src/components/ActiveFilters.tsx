import type { FilterState } from '../types/api'
import { formatCurrency } from '../utils/formatters'

interface Chip {
  label: string
  onRemove: () => void
}

interface Props {
  filters: FilterState
  onChange: (f: FilterState) => void
}

const DEFAULT: FilterState = {
  minRoi: 0,
  riskLevel: 'all',
  city: '',
  minPrice: 0,
  maxPrice: 0,
  sortBy: 'roi',
  showPast: false,
}

const RISK_LABELS: Record<string, string> = {
  low: 'Basso',
  medium: 'Medio',
  high: 'Alto',
}

export function countActiveFilters(filters: FilterState): number {
  let n = 0
  if (filters.minRoi > 0) n++
  if (filters.riskLevel !== 'all') n++
  if (filters.city) n++
  if (filters.minPrice > 0) n++
  if (filters.maxPrice > 0) n++
  if (filters.showPast) n++
  return n
}

export function ActiveFilters({ filters, onChange }: Props) {
  const set = <K extends keyof FilterState>(key: K, value: FilterState[K]) =>
    onChange({ ...filters, [key]: value })

  const chips: Chip[] = []

  if (filters.minRoi > 0)
    chips.push({ label: `ROI ≥ ${filters.minRoi}%`, onRemove: () => set('minRoi', 0) })

  if (filters.riskLevel !== 'all')
    chips.push({
      label: `Rischio: ${RISK_LABELS[filters.riskLevel] ?? filters.riskLevel}`,
      onRemove: () => set('riskLevel', 'all'),
    })

  if (filters.city)
    chips.push({ label: `Città: ${filters.city}`, onRemove: () => set('city', '') })

  if (filters.minPrice > 0)
    chips.push({
      label: `Min: ${formatCurrency(filters.minPrice)}`,
      onRemove: () => set('minPrice', 0),
    })

  if (filters.maxPrice > 0)
    chips.push({
      label: `Max: ${formatCurrency(filters.maxPrice)}`,
      onRemove: () => set('maxPrice', 0),
    })

  if (filters.showPast)
    chips.push({ label: 'Con date passate', onRemove: () => set('showPast', false) })

  if (!chips.length) return null

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {chips.map((chip) => (
        <span
          key={chip.label}
          className="inline-flex items-center gap-1.5 bg-slate-800 border border-slate-700 rounded-full pl-3 pr-2 py-1 text-xs text-slate-300"
        >
          {chip.label}
          <button
            onClick={chip.onRemove}
            className="text-slate-500 hover:text-slate-200 transition-colors leading-none"
            aria-label="Rimuovi filtro"
          >
            ×
          </button>
        </span>
      ))}
      <button
        onClick={() => onChange(DEFAULT)}
        className="text-xs text-slate-500 hover:text-slate-300 transition-colors ml-1"
      >
        Azzera tutto
      </button>
    </div>
  )
}
