import { format, formatDistanceToNow } from 'date-fns'
import { it } from 'date-fns/locale'
import type { Auction } from '../types/api'

export function formatCurrency(value?: number | string | null): string {
  if (value == null) return '—'
  const n = Number(value)
  if (isNaN(n)) return '—'
  return new Intl.NumberFormat('it-IT', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(n)
}

export function formatPct(value?: number | string | null): string {
  if (value == null) return '—'
  const n = Number(value)
  if (isNaN(n)) return '—'
  return `${n.toFixed(1)}%`
}

export function formatDate(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return format(new Date(iso), 'dd MMM yyyy', { locale: it })
  } catch {
    return '—'
  }
}

export function formatRelative(iso?: string | null): string {
  if (!iso) return '—'
  try {
    return formatDistanceToNow(new Date(iso), { addSuffix: true, locale: it })
  } catch {
    return '—'
  }
}

export function getROI(auction: Auction): number | null {
  const v = auction.valuations?.[0]?.roi_percentage
  if (v == null) return null
  const n = Number(v)
  return isNaN(n) ? null : n
}

export function getRiskScore(auction: Auction): number {
  if (!auction.risk_flags?.length) return 0
  return Math.min(
    100,
    auction.risk_flags.reduce((acc, f) => acc + Number(f.score_contribution ?? 0), 0)
  )
}

export type RiskGrade = 'low' | 'medium' | 'high' | 'critical'

export function getRiskGrade(score: number): RiskGrade {
  if (score < 30) return 'low'
  if (score < 60) return 'medium'
  if (score < 80) return 'high'
  return 'critical'
}

export function getOverallScore(auction: Auction): number {
  const roi = getROI(auction) ?? 0
  const risk = getRiskScore(auction)
  const roiScore = Math.min(70, (roi / 35) * 70)
  const safetyScore = Math.max(0, 30 * (1 - risk / 100))
  return Math.round(roiScore + safetyScore)
}

export function propertyTypeLabel(type?: string): string {
  const map: Record<string, string> = {
    apartment: 'Appartamento',
    villa: 'Villa',
    commercial: 'Commerciale',
    land: 'Terreno',
    industrial: 'Industriale',
    garage: 'Garage',
    other: 'Altro',
  }
  return map[type ?? ''] ?? type ?? '—'
}

export function auctionTypeLabel(type?: string): string {
  const map: Record<string, string> = {
    judicial: 'Vendita Giudiziaria',
    voluntary: 'Vendita Volontaria',
    online: 'Asta Online',
    other: 'Altro',
  }
  return map[type ?? ''] ?? type ?? '—'
}
