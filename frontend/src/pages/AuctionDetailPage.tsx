import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import type { Auction } from '../types/api'
import { auctionsApi } from '../api/auctions'
import { FavoriteButton } from '../components/FavoriteButton'
import {
  formatCurrency,
  formatDate,
  formatRelative,
  formatPct,
  getROI,
  getRiskGrade,
  getRiskScore,
  getOverallScore,
  propertyTypeLabel,
  auctionTypeLabel,
} from '../utils/formatters'
import { RiskBadge } from '../components/RiskBadge'

function Row({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="flex justify-between py-2.5 border-b border-surface-border last:border-0">
      <span className="text-sm text-slate-500">{label}</span>
      <span className="text-sm text-slate-200 font-medium text-right max-w-[60%]">
        {value ?? '—'}
      </span>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">
        {title}
      </h2>
      {children}
    </section>
  )
}

export function AuctionDetailPage() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [auction, setAuction] = useState<Auction | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!id) return
    setLoading(true)
    auctionsApi
      .getById(id)
      .then(setAuction)
      .catch(() => setError('Asta non trovata o errore di rete.'))
      .finally(() => setLoading(false))
  }, [id])

  return (
    <div className="min-h-screen bg-surface flex flex-col">
      {/* Top bar */}
      <header className="sticky top-0 z-10 bg-surface/90 backdrop-blur border-b border-surface-border">
        <div className="max-w-3xl mx-auto px-4 sm:px-6 h-14 flex items-center justify-between gap-3">
          <button
            onClick={() => navigate(-1)}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1.5 -ml-1.5 rounded-lg hover:bg-slate-800 flex items-center gap-1.5"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
            <span className="text-sm">Torna alle aste</span>
          </button>
          {auction && (
            <FavoriteButton
              item={{
                id: auction.id,
                label: `${auction.property?.city ?? '—'}${auction.property?.province ? ` (${auction.property.province})` : ''}`,
                base_price: auction.base_price ? Number(auction.base_price) : undefined,
                roi: getROI(auction) ?? undefined,
              }}
            />
          )}
        </div>
      </header>

      <main className="flex-1 max-w-3xl mx-auto w-full px-4 sm:px-6 py-6 space-y-6">
        {loading && (
          <div className="flex items-center justify-center h-60">
            <div className="w-8 h-8 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
          </div>
        )}

        {error && (
          <div className="rounded-xl border border-red-800/50 bg-red-900/20 px-5 py-4 text-red-400 text-sm">
            {error}
          </div>
        )}

        {auction && <AuctionDetail auction={auction} />}
      </main>
    </div>
  )
}

function AuctionDetail({ auction }: { auction: Auction }) {
  const prop = auction.property
  const val = auction.valuations?.[0]
  const roi = getROI(auction)
  const riskScore = getRiskScore(auction)
  const riskGrade = getRiskGrade(riskScore)
  const overallScore = getOverallScore(auction)

  return (
    <div className="space-y-6">
      {/* Hero */}
      <div className="rounded-2xl bg-slate-900 border border-surface-border p-5 sm:p-6 flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="text-xs text-slate-500 mb-1.5">
            {propertyTypeLabel(prop?.property_type)} · {auctionTypeLabel(auction.auction_type)}
          </div>
          <h1 className="text-xl sm:text-2xl font-bold text-white">
            {prop?.city ?? '—'}
            {prop?.province ? (
              <span className="text-slate-400 font-normal ml-1.5 text-base">({prop.province})</span>
            ) : null}
          </h1>
          {prop?.address && (
            <div className="text-sm text-slate-400 mt-1">{prop.address}</div>
          )}
          {prop?.area_sqm && (
            <div className="text-xs text-slate-500 mt-1">{prop.area_sqm} m²</div>
          )}
        </div>
        <div className="text-center flex-shrink-0 bg-slate-800 rounded-xl p-3 sm:p-4 min-w-[64px]">
          <div
            className={`text-3xl font-bold tabular-nums ${
              overallScore >= 70
                ? 'text-emerald-400'
                : overallScore >= 50
                ? 'text-amber-400'
                : 'text-slate-400'
            }`}
          >
            {overallScore}
          </div>
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mt-0.5">score</div>
        </div>
      </div>

      {/* Metrics summary */}
      <div className="grid grid-cols-3 gap-3">
        <div className="rounded-xl bg-emerald-900/20 border border-emerald-800/30 p-4 text-center">
          <div className="text-[10px] text-emerald-600 uppercase tracking-wider mb-1.5">ROI stimato</div>
          <div className="text-2xl font-bold text-emerald-400 tabular-nums">
            {roi != null ? `${roi.toFixed(1)}%` : '—'}
          </div>
        </div>
        <div className="rounded-xl bg-slate-900 border border-surface-border p-4 text-center">
          <div className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Rischio</div>
          <RiskBadge grade={riskGrade} />
        </div>
        <div className="rounded-xl bg-slate-900 border border-surface-border p-4 text-center">
          <div className="text-[10px] text-slate-600 uppercase tracking-wider mb-1.5">Payback</div>
          <div className="text-base font-semibold text-slate-300">
            {val?.payback_years != null ? `${Number(val.payback_years).toFixed(1)} y` : '—'}
          </div>
        </div>
      </div>

      {/* Pricing */}
      <Section title="Prezzi">
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <Row
            label="Base d'asta"
            value={val?.purchase_price != null ? formatCurrency(val.purchase_price) : formatCurrency(auction.base_price)}
          />
          <Row label="Offerta minima" value={formatCurrency(auction.minimum_bid)} />
          <Row
            label={val?.assumptions?.market_value_assumed ? 'Valore di mercato (stimato ×1.3)' : 'Valore di mercato'}
            value={
              val?.market_value != null
                ? val?.assumptions?.market_value_assumed
                  ? `~ ${formatCurrency(val.market_value)}`
                  : formatCurrency(val.market_value)
                : '—'
            }
          />
          <Row label="Costo totale stimato" value={formatCurrency(val?.total_acquisition_cost)} />
          <Row label="Profitto netto stimato" value={formatCurrency(val?.net_profit_estimate)} />
        </div>
        {Boolean(val?.assumptions?.market_value_assumed) && (
          <p className="text-xs text-amber-600 mt-2 px-1">
            ⚠ Valore di mercato non disponibile nell'API — stimato come prezzo base × 1.3 (approssimazione conservativa).
          </p>
        )}
      </Section>

      {/* ROI Breakdown */}
      {val?.assumptions && (
        <Section title="Breakdown ROI">
          <div className="rounded-xl border border-surface-border overflow-hidden">
            {Object.entries(val.assumptions).map(([k, v]) => (
              <Row
                key={k}
                label={k.replace(/_/g, ' ')}
                value={
                  typeof v === 'number'
                    ? k.includes('pct') || k.includes('roi')
                      ? formatPct(v)
                      : formatCurrency(v)
                    : String(v)
                }
              />
            ))}
          </div>
        </Section>
      )}

      {/* Property */}
      <Section title="Immobile">
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <Row label="Tipo" value={propertyTypeLabel(prop?.property_type)} />
          <Row label="Superficie" value={prop?.area_sqm ? `${prop.area_sqm} m²` : undefined} />
          <Row label="Piano" value={prop?.floor} />
          <Row label="Vani" value={prop?.rooms} />
          <Row label="CAP" value={prop?.postal_code} />
        </div>
      </Section>

      {/* Procedure */}
      <Section title="Procedura">
        <div className="rounded-xl border border-surface-border overflow-hidden">
          <Row label="Tribunale" value={auction.court} />
          <Row label="N. procedura" value={auction.procedure_number} />
          <Row label="Tipo asta" value={auctionTypeLabel(auction.auction_type)} />
          <Row label="Data asta" value={formatDate(auction.auction_date)} />
          <Row label="Scadenza" value={formatDate(auction.auction_deadline)} />
          <Row label="Cauzione" value={formatCurrency(auction.deposit_required)} />
          <Row label="Rilancio minimo" value={formatCurrency(auction.bid_increment)} />
          <Row label="Inserito" value={formatRelative(auction.created_at)} />
        </div>
      </Section>

      {/* Risk flags */}
      {auction.risk_flags?.length > 0 && (
        <Section title="Fattori di rischio">
          <div className="space-y-2">
            {auction.risk_flags.map((f) => (
              <div
                key={f.id}
                className="rounded-xl border border-surface-border p-4 flex items-start gap-3"
              >
                <RiskBadge grade={f.severity as 'low' | 'medium' | 'high' | 'critical'} small />
                <div className="min-w-0">
                  <div className="text-sm font-medium text-slate-300">{f.description}</div>
                  {f.score_contribution != null && (
                    <div className="text-xs text-slate-600 mt-0.5">
                      Contributo: +{Number(f.score_contribution).toFixed(0)} pt
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* CTA buttons */}
      <div className="flex flex-col sm:flex-row gap-2">
        {auction.source_url && (
          <a
            href={auction.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="flex-1 block text-center py-3 rounded-xl border border-emerald-700/50 text-emerald-400 hover:bg-emerald-900/20 transition-colors text-sm font-medium"
          >
            Apri su PVP →
          </a>
        )}
        <a
          href={`https://www.google.com/search?q=${encodeURIComponent(
            ['asta', prop?.city, prop?.address].filter(Boolean).join(' ')
          )}`}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 flex items-center justify-center gap-2 py-3 rounded-xl border border-slate-700 text-slate-300 hover:bg-slate-800 hover:border-slate-600 transition-colors text-sm font-medium"
        >
          <svg className="w-4 h-4 flex-shrink-0" viewBox="0 0 24 24" fill="currentColor">
            <path d="M21.35 11.1H12.18V13.83H18.69C18.36 17.64 15.19 19.27 12.19 19.27C8.36 19.27 5 16.25 5 12C5 7.9 8.2 4.73 12.2 4.73C15.29 4.73 17.1 6.7 17.1 6.7L19 4.72C19 4.72 16.56 2 12.1 2C6.42 2 2.03 6.8 2.03 12C2.03 17.05 6.16 22 12.25 22C17.6 22 21.5 18.33 21.5 12.91C21.5 11.76 21.35 11.1 21.35 11.1Z"/>
          </svg>
          Partecipa
        </a>
      </div>
    </div>
  )
}
