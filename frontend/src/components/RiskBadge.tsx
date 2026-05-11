import clsx from 'clsx'
import type { RiskGrade } from '../utils/formatters'

const config: Record<RiskGrade, { label: string; cls: string }> = {
  low: {
    label: 'BASSO',
    cls: 'bg-emerald-900/40 text-emerald-400 border-emerald-700/50',
  },
  medium: {
    label: 'MEDIO',
    cls: 'bg-amber-900/40 text-amber-400 border-amber-700/50',
  },
  high: {
    label: 'ALTO',
    cls: 'bg-orange-900/40 text-orange-400 border-orange-700/50',
  },
  critical: {
    label: 'CRITICO',
    cls: 'bg-red-900/40 text-red-400 border-red-700/50',
  },
}

interface Props {
  grade: RiskGrade
  small?: boolean
}

export function RiskBadge({ grade, small }: Props) {
  const { label, cls } = config[grade]
  return (
    <span
      className={clsx(
        'inline-flex items-center border rounded font-semibold tracking-wider',
        small ? 'px-1.5 py-0.5 text-[10px]' : 'px-2 py-1 text-xs',
        cls
      )}
    >
      {label}
    </span>
  )
}
