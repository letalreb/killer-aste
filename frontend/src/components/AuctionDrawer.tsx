import { useEffect, useState } from 'react'
import type { Auction } from '../types/api'
import { auctionsApi } from '../api/auctions'
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
import { RiskBadge } from './RiskBadge'

interface Props {
  auctionId: string | null
  onClose: () => void
}

function Row({ label, value }: { label: string; value?: string | number | null }) {
  return (
    <div className="flex justify-between py-2 border-b border-surface-border last:border-0">
      <span className="text-xs text-slate-500">{label}</span>
      <span className="text-xs text-slate-200 font-medium text-right max-w-[60%]">
        {value ?? '—'}
      </span>
    </div>
  )
}

export function AuctionDrawer({ auctionId, onClose }: Props) {
  const [auction, setAuction] = useState<Auction | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!auctionId) { setAuction(null); return }
    setLoading(true)
    auctionsApi
      .getById(auctionId)
      .then(setAuction)
      .finally(() => setLoading(false))
  }, [auctionId])

  // Close on Escape + lock body scroll when open
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  const isOpen = !!auctionId

  useEffect(() => {
    document.body.style.overflow = isOpen ? 'hidden' : ''
    return () => { document.body.style.overflow = '' }
  }, [isOpen])

  return (
    <>
      {/* Backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 bg-black/60 z-40 backdrop-blur-sm"
          onClick={onClose}
        />
      )}

      {/* Drawer */}
      <div
        className={`fixed top-0 right-0 h-full w-full sm:w-[480px] bg-surface-card border-l border-surface-border z-50 flex flex-col shadow-2xl transition-transform duration-300 ${
          isOpen ? 'translate-x-0' : 'translate-x-full'
        }`}
      >
        {/* Drawer header */}
        <div className="flex items-center gap-3 px-4 sm:px-5 py-4 border-b border-surface-border flex-shrink-0">
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors p-1 -ml-1 rounded-lg hover:bg-slate-800"
            aria-label="Chiudi"
          >
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
            </svg>
          </button>
          <span className="text-sm font-semibold text-slate-200">Dettaglio Asta</span>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto px-4 sm:px-5 py-4 space-y-5">
          {loading ? (
            <div className="flex items-center justify-center h-40">
              <div className="w-6 h-6 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : auction ? (
            <DrawerContent auction={auction} />
          ) : null}
        </div>
      </div>
    </>
  )
}

function DrawerContent({ auction }: { auction: Auction }) {
  const prop = auction.property
  const val = auction.valuations?.[0]
  const roi = getROI(auction)
  const riskScore = getRiskScore(auction)
  const riskGrade = getRiskGrade(riskScore)
  const overallScore = getOverallScore(auction)

  return (
    <div className="space-y-5">
      {/* Hero */}
      <div className="rounded-xl bg-slate-900 p-4 flex items-start justify-between gap-4">
        <div>
          <div className="text-xs text-slate-500 mb-1">
            {propertyTypeLabel(prop?.property_type)} · {auctionTypeLabel(auction.auction_type)}
          </div>
          <div className="text-base font-semibold text-white">
            {prop?.city ?? '—'}
            {prop?.province ? ` (${prop.province})` : ''}
          </div>
          {prop?.address && (
            <div className="text-xs text-slate-400 mt-0.5">{prop.address}</div>
          )}
        </div>
        <div className="text-center flex-shrink-0">
          <div
            className={`text-2xl font-bold ${
              overallScore >= 70
                ? 'text-emerald-400'
                : overallScore >= 50
                ? 'text-amber-400'
                : 'text-slate-400'
            }`}
          >
            {overallScore}
          </div>
          <div className="text-[9px] text-slate-600 uppercase tracking-wide">score</div>
        </div>
      </div>

      {/* ROI Summary */}
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-emerald-900/20 border border-emerald-800/30 p-3 text-center">
          <div className="text-[10px] text-emerald-600 uppercase tracking-wide mb-1">ROI</div>
          <div className="text-lg font-bold text-emerald-400">{roi != null ? `${roi.toFixed(1)}%` : '—'}</div>
        </div>
        <div className="rounded-lg bg-slate-900 border border-surface-border p-3 text-center">
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mb-1">Rischio</div>
          <RiskBadge grade={riskGrade} />
        </div>
        <div className="rounded-lg bg-slate-900 border border-surface-border p-3 text-center">
          <div className="text-[10px] text-slate-600 uppercase tracking-wide mb-1">Payback</div>
          <div className="text-sm font-semibold text-slate-300">
            {val?.payback_years != null ? `${val.payback_years.toFixed(1)} y` : '—'}
          </div>
        </div>
      </div>

      {/* Pricing */}
      <section>
        <h3 className="section-title">Prezzi</h3>
        <div className="rounded-lg border border-surface-border overflow-hidden">
          <Row label="Base d'asta" value={val?.purchase_price != null ? formatCurrency(val.purchase_price) : formatCurrency(auction.base_price)} />
          <Row label="Offerta minima" value={formatCurrency(auction.minimum_bid)} />
          <Row
            label={val?.assumptions?.market_value_assumed ? 'Valore di mercato (stimato ×1.3)' : 'Valore di mercato'}
            value={val?.market_value != null ? (val.assumptions?.market_value_assumed ? `~ ${formatCurrency(val.market_value)}` : formatCurrency(val.market_value)) : '—'}
          />
          <Row label="Costo totale stimato" value={formatCurrency(val?.total_acquisition_cost)} />
          <Row label="Profitto netto stimato" value={formatCurrency(val?.net_profit_estimate)} />
        </div>
        {Boolean(val?.assumptions?.market_value_assumed) && (
          <p className="text-[10px] text-amber-600 mt-1.5 px-1">
            ⚠ Valore di mercato non disponibile nell'API — stimato come prezzo base × 1.3 (approssimazione conservativa).
          </p>
        )}
      </section>

      {/* ROI Breakdown */}
      {val?.assumptions && (
        <section>
          <h3 className="section-title">Breakdown ROI</h3>
          <div className="rounded-lg border border-surface-border overflow-hidden">
            {Object.entries(val.assumptions).map(([k, v]) => (
              <Row
                key={k}
                label={k.replace(/_/g, ' ')}
                value={typeof v === 'number' ? (k.includes('pct') || k.includes('roi') ? formatPct(v) : formatCurrency(v)) : String(v)}
              />
            ))}
          </div>
        </section>
      )}

      {/* Property Details */}
      <section>
        <h3 className="section-title">Immobile</h3>
        <div className="rounded-lg border border-surface-border overflow-hidden">
          <Row label="Tipo" value={propertyTypeLabel(prop?.property_type)} />
          <Row label="Superficie" value={prop?.area_sqm ? `${prop.area_sqm} m²` : undefined} />
          <Row label="Piano" value={prop?.floor} />
          <Row label="Vani" value={prop?.rooms} />
          <Row label="CAP" value={prop?.postal_code} />
        </div>
      </section>

      {/* Auction Details */}
      <section>
        <h3 className="section-title">Procedura</h3>
        <div className="rounded-lg border border-surface-border overflow-hidden">
          <Row label="Tribunale" value={auction.court} />
          <Row label="N. procedura" value={auction.procedure_number} />
          <Row label="Tipo" value={auctionTypeLabel(auction.auction_type)} />
          <Row label="Data asta" value={formatDate(auction.auction_date)} />
          <Row label="Scadenza" value={formatDate(auction.auction_deadline)} />
          <Row label="Cauzione" value={formatCurrency(auction.deposit_required)} />
          <Row label="Rilancio minimo" value={formatCurrency(auction.bid_increment)} />
          <Row label="Inserito" value={formatRelative(auction.created_at)} />
        </div>
      </section>

      {/* Risk Flags */}
      {auction.risk_flags?.length > 0 && (
        <section>
          <h3 className="section-title">Fattori di rischio</h3>
          <div className="space-y-2">
            {auction.risk_flags.map((f) => (
              <div
                key={f.id}
                className="rounded-lg border border-surface-border p-3 flex items-start gap-3"
              >
                <RiskBadge grade={f.severity as 'low' | 'medium' | 'high' | 'critical'} small />
                <div className="min-w-0">
                  <div className="text-xs font-medium text-slate-300">{f.description}</div>
                  {f.score_contribution != null && (
                    <div className="text-[10px] text-slate-600 mt-0.5">
                      Contributo: +{f.score_contribution.toFixed(0)} pt
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Source link */}
      {auction.source_url && (
        <a
          href={auction.source_url}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full text-center py-2.5 rounded-lg border border-emerald-700/50 text-emerald-400 text-sm hover:bg-emerald-900/20 transition-colors"
        >
          Apri su PVP →
        </a>
      )}
    </div>
  )
}
