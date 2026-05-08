import clsx from 'clsx'
import { useNavigate } from 'react-router-dom'
import type { Auction } from '../types/api'
import {
  formatCurrency,
  formatDate,
  getROI,
  getRiskGrade,
  getRiskScore,
  getOverallScore,
  propertyTypeLabel,
} from '../utils/formatters'
import { RiskBadge } from './RiskBadge'
import { FavoriteButton } from './FavoriteButton'

interface Props {
  readonly auction: Auction
  readonly rank: number
}

function ROIChip({ roi }: { roi: number | null }) {
  if (roi == null) return <span className="text-slate-500 text-sm">—</span>
  const cls =
    roi >= 30
      ? 'text-emerald-300 font-bold'
      : roi >= 20
      ? 'text-emerald-400 font-semibold'
      : roi >= 10
      ? 'text-amber-400 font-semibold'
      : 'text-slate-400'
  return <span className={clsx('text-xl tabular-nums', cls)}>{roi.toFixed(1)}%</span>
}

function ScoreRing({ score }: { score: number }) {
  const color =
    score >= 70 ? 'text-emerald-400' : score >= 50 ? 'text-amber-400' : 'text-slate-500'
  return (
    <div className={clsx('text-center', color)}>
      <div className="text-lg font-bold tabular-nums">{score}</div>
      <div className="text-[9px] uppercase tracking-wider text-slate-600">score</div>
    </div>
  )
}

export function AuctionCard({ auction, rank }: Props) {
  const navigate = useNavigate()
  const roi = getROI(auction)
  const riskScore = getRiskScore(auction)
  const riskGrade = getRiskGrade(riskScore)
  const overallScore = getOverallScore(auction)
  const prop = auction.property

  return (
    <article
      onClick={() => navigate(`/auctions/${auction.id}`)}
      className="group bg-surface-card border border-surface-border hover:border-slate-600 rounded-xl p-4 cursor-pointer transition-all hover:shadow-lg hover:shadow-black/30 active:scale-[0.99]"
    >
      {/* Header row */}
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-[10px] font-bold text-slate-600 w-5 flex-shrink-0">#{rank}</span>
          <div className="min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span className="text-xs text-slate-400 font-medium">
                {propertyTypeLabel(prop?.property_type)}
              </span>
              {prop?.area_sqm && (
                <span className="text-[10px] text-slate-600">{prop.area_sqm} m²</span>
              )}
            </div>
            <div className="text-sm font-semibold text-slate-200 truncate mt-0.5">
              {prop?.city ?? '—'}
              {prop?.province ? (
                <span className="text-slate-500 font-normal ml-1">({prop.province})</span>
              ) : null}
            </div>
            {prop?.address && (
              <div className="text-xs text-slate-600 truncate">{prop.address}</div>
            )}
          </div>
        </div>

        {/* Score + favourite — stacked, no overlap */}
        <div className="flex flex-col items-center gap-1.5 flex-shrink-0">
          <FavoriteButton
            item={{
              id: auction.id,
              label: `${prop?.city ?? '—'}${prop?.province ? ` (${prop.province})` : ''}`,
              base_price: auction.base_price ? Number(auction.base_price) : undefined,
              roi: roi ?? undefined,
            }}
            size="sm"
          />
          <ScoreRing score={overallScore} />
        </div>
      </div>

      {/* Price row */}
      <div className="grid grid-cols-2 gap-2 mb-3 p-2 rounded-lg bg-slate-900/50">
        <div>
          <div className="text-[10px] text-slate-600 uppercase tracking-wide">Base asta</div>
          <div className="text-sm font-semibold text-white tabular-nums">
            {formatCurrency(auction.base_price)}
          </div>
        </div>
        <div>
          {(() => {
            const val = auction.valuations?.[0]
            const mv = val?.market_value
            const assumed = val?.assumptions?.market_value_assumed
            return (
              <>
                <div className="text-[10px] text-slate-600 uppercase tracking-wide">
                  Valore mercato{assumed ? ' ~' : ''}
                </div>
                <div className="text-sm font-medium text-slate-300 tabular-nums">
                  {mv != null ? formatCurrency(Number(mv)) : '—'}
                </div>
              </>
            )
          })()}
        </div>
      </div>

      {/* Metrics row */}
      <div className="flex items-center justify-between">
        <div>
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mb-0.5">ROI stimato</div>
          <ROIChip roi={roi} />
        </div>
        <div className="text-right">
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mb-1">Rischio</div>
          <RiskBadge grade={riskGrade} small />
        </div>
        <div className="text-right">
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mb-0.5">Data</div>
          <div className="text-xs text-slate-400">{formatDate(auction.auction_date)}</div>
        </div>
      </div>

      {/* Footer: court + partecipa */}
      <div className="mt-2 pt-2 border-t border-surface-border flex items-center justify-between gap-2">
        <div className="text-[10px] text-slate-600 truncate min-w-0">
          {auction.court ?? ''}
        </div>
        <a
          href={`https://www.google.com/search?q=${encodeURIComponent(
            ['asta', prop?.city, prop?.address].filter(Boolean).join(' ')
          )}`}
          target="_blank"
          rel="noopener noreferrer"
          onClick={(e) => e.stopPropagation()}
          className="flex-shrink-0 flex items-center gap-1 text-[10px] text-slate-500 hover:text-emerald-400 transition-colors"
        >
          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21.35 11.1H12.18V13.83H18.69C18.36 17.64 15.19 19.27 12.19 19.27C8.36 19.27 5 16.25 5 12C5 7.9 8.2 4.73 12.2 4.73C15.29 4.73 17.1 6.7 17.1 6.7L19 4.72C19 4.72 16.56 2 12.1 2C6.42 2 2.03 6.8 2.03 12C2.03 17.05 6.16 22 12.25 22C17.6 22 21.5 18.33 21.5 12.91C21.5 11.76 21.35 11.1 21.35 11.1Z"/>
          </svg>
          Partecipa
        </a>
      </div>
    </article>
  )
}
