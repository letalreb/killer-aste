import { useState, useEffect } from 'react'
import { adminApi, type AdminStats } from '../../api/admin'
import { KPIBox } from '../../components/KPIBox'

function fmt(iso: string | null): string {
  if (!iso) return 'Mai'
  return new Date(iso).toLocaleString('it-IT', { dateStyle: 'medium', timeStyle: 'short' })
}

function pct(n: number, total: number): string {
  if (!total) return '0%'
  return `${Math.round((n / total) * 100)}%`
}

function BarRow({ label, value, total, color }: { label: string; value: number; total: number; color: string }) {
  const w = total ? Math.round((value / total) * 100) : 0
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-slate-400 w-24 shrink-0">{label}</span>
      <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${w}%` }} />
      </div>
      <span className="text-xs text-slate-300 w-12 text-right">{value.toLocaleString()}</span>
      <span className="text-xs text-slate-600 w-8 text-right">{pct(value, total)}</span>
    </div>
  )
}

export function StatsTab() {
  const [stats, setStats] = useState<AdminStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    adminApi.getStats()
      .then(setStats)
      .catch(() => setError('Errore nel caricamento statistiche'))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <div className="text-center py-16 text-slate-500 text-sm">Caricamento…</div>
  if (error || !stats) return <div className="text-center py-16 text-red-400 text-sm">{error}</div>

  const auctionTotal = stats.auctions.total
  const userTotal = stats.users.total

  return (
    <div className="space-y-6">
      {/* KPI row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <KPIBox
          label="Utenti attivi"
          value={userTotal.toLocaleString()}
          sub={`${stats.users.logins_last_30d} login negli ultimi 30gg`}
          accent="blue"
        />
        <KPIBox
          label="Aste totali"
          value={auctionTotal.toLocaleString()}
          sub={`${stats.auctions.with_roi} con ROI calcolato`}
          accent="green"
        />
        <KPIBox
          label="Immobili"
          value={stats.properties.total.toLocaleString()}
          accent="amber"
        />
        <KPIBox
          label="Run ingestion"
          value={stats.ingestion.total_runs.toLocaleString()}
          sub={`Ultima: ${fmt(stats.ingestion.last_successful_at)}`}
          accent="green"
        />
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {/* Auctions by status */}
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white mb-4">Aste per stato</h3>
          <div className="space-y-3">
            {Object.entries(stats.auctions.by_status).map(([status, count]) => (
              <BarRow
                key={status}
                label={status}
                value={count}
                total={auctionTotal}
                color={status === 'scheduled' ? 'bg-emerald-500' : status === 'completed' ? 'bg-slate-500' : 'bg-red-500'}
              />
            ))}
          </div>
        </div>

        {/* Users by role */}
        <div className="bg-surface-card border border-surface-border rounded-xl p-5">
          <h3 className="text-sm font-semibold text-white mb-4">Utenti per ruolo</h3>
          <div className="space-y-3">
            {Object.entries(stats.users.by_role).map(([role, count]) => (
              <BarRow
                key={role}
                label={role}
                value={count}
                total={userTotal}
                color={role === 'admin' ? 'bg-purple-500' : role === 'premium' ? 'bg-amber-500' : 'bg-slate-500'}
              />
            ))}
          </div>
          <div className="mt-4 pt-4 border-t border-surface-border space-y-1">
            <p className="text-xs text-slate-500">Standard: fino a 3 preferiti</p>
            <p className="text-xs text-slate-500">Premium: fino a 10 preferiti</p>
            <p className="text-xs text-slate-500">Admin: accesso illimitato</p>
          </div>
        </div>
      </div>

      {/* Sources */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-3">Fonti dati attive</h3>
        <div className="flex flex-wrap gap-2">
          {stats.sources.map((src) => (
            <span
              key={src}
              className="text-xs px-2.5 py-1 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono"
            >
              {src}
            </span>
          ))}
        </div>
        <p className="text-xs text-slate-600 mt-3">
          Nuove fonti vengono aggiunte automaticamente all&apos;elenco quando lo scraper corrispondente viene attivato.
        </p>
      </div>
    </div>
  )
}
