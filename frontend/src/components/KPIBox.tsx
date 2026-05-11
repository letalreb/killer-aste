interface Props {
  label: string
  value: string | number
  sub?: string
  accent?: 'green' | 'amber' | 'red' | 'blue'
}

const accentMap = {
  green: 'text-emerald-400',
  amber: 'text-amber-400',
  red: 'text-red-400',
  blue: 'text-sky-400',
}

export function KPIBox({ label, value, sub, accent = 'green' }: Props) {
  return (
    <div className="bg-surface-card border border-surface-border rounded-xl p-4 flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-500 uppercase tracking-wider">{label}</span>
      <span className={`text-2xl font-bold ${accentMap[accent]}`}>{value}</span>
      {sub && <span className="text-xs text-slate-500">{sub}</span>}
    </div>
  )
}
