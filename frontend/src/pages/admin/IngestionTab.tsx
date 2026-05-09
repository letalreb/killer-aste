import { useState, useEffect, useCallback } from 'react'
import { adminApi, type IngestionRun } from '../../api/admin'

const STALE_HOURS = 2

const STATUS_STYLE: Record<string, string> = {
  completed: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30',
  running:   'bg-sky-500/15 text-sky-400 border-sky-500/30 animate-pulse',
  failed:    'bg-red-500/15 text-red-400 border-red-500/30',
  dry_run:   'bg-slate-500/15 text-slate-400 border-slate-600',
}

function StatusBadge({ status }: { readonly status: string }) {
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${STATUS_STYLE[status] ?? 'bg-slate-700 text-slate-400'}`}>
      {status}
    </span>
  )
}

function fmt(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}

function elapsedSince(iso: string | null, now: number): string {
  if (!iso) return '—'
  const s = Math.round((now - new Date(iso).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
}

function completedDuration(r: IngestionRun): string {
  if (!r.started_at || !r.completed_at) return '—'
  const s = Math.round((new Date(r.completed_at).getTime() - new Date(r.started_at).getTime()) / 1000)
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`
  const h = Math.floor(s / 3600)
  return `${h}h ${Math.floor((s % 3600) / 60)}m`
}

function isStale(r: IngestionRun, now: number): boolean {
  if (r.status !== 'running' || !r.started_at) return false
  return (now - new Date(r.started_at).getTime()) > STALE_HOURS * 3600 * 1000
}

export function IngestionTab() {
  const [runs, setRuns] = useState<IngestionRun[]>([])
  const [loading, setLoading] = useState(true)
  const [triggering, setTriggering] = useState(false)
  const [cancelling, setCancelling] = useState<string | null>(null)
  const [dryRun, setDryRun] = useState(false)
  const [activeRunId, setActiveRunId] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [now, setNow] = useState(Date.now())

  const fetchRuns = useCallback(async () => {
    try {
      const data = await adminApi.listRuns(30)
      setRuns(data)
      setActiveRunId(data.find((r) => r.status === 'running')?.run_id ?? null)
    } catch {
      setError('Errore nel caricamento delle run')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchRuns() }, [fetchRuns])

  // Poll DB while a run is active
  useEffect(() => {
    if (!activeRunId) return
    const interval = setInterval(fetchRuns, 4000)
    return () => clearInterval(interval)
  }, [activeRunId, fetchRuns])

  // Tick clock every second when something is running (for elapsed time display)
  useEffect(() => {
    if (!activeRunId) return
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [activeRunId])

  const handleTrigger = async () => {
    setTriggering(true)
    setError(null)
    try {
      await adminApi.triggerIngestion('pvp', dryRun)
      await new Promise((r) => setTimeout(r, 1500))
      await fetchRuns()
    } catch {
      setError('Errore nel triggering ingestion')
    } finally {
      setTriggering(false)
    }
  }

  const handleCancel = async (run_id: string) => {
    setCancelling(run_id)
    setError(null)
    try {
      await adminApi.cancelRun(run_id)
      await new Promise((r) => setTimeout(r, 1000))
      await fetchRuns()
    } catch {
      setError('Errore durante la richiesta di stop')
    } finally {
      setCancelling(null)
    }
  }

  let triggerLabel = 'Avvia ingestion'
  if (triggering) triggerLabel = 'Avvio…'
  else if (activeRunId) triggerLabel = 'Run in corso…'

  return (
    <div className="space-y-6">
      {/* Trigger card */}
      <div className="bg-surface-card border border-surface-border rounded-xl p-5">
        <h3 className="text-sm font-semibold text-white mb-1">Avvia nuova ingestion</h3>
        <p className="text-xs text-slate-500 mb-4">
          La run parte in background. Aggiorna automaticamente ogni 4s finché è attiva.
          Runs attive da più di {STALE_HOURS}h vengono segnalate in arancione.
        </p>
        <div className="flex items-center gap-4">
          <label className="flex items-center gap-2 text-sm text-slate-400 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={dryRun}
              onChange={(e) => setDryRun(e.target.checked)}
              className="accent-emerald-500"
            />
            Dry run (nessuna scrittura su DB)
          </label>
          <button
            onClick={handleTrigger}
            disabled={triggering || !!activeRunId}
            className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-40 disabled:cursor-not-allowed text-white text-sm font-medium transition-colors"
          >
            {triggerLabel}
          </button>
          {activeRunId && (
            <span className="text-xs text-sky-400 animate-pulse">
              Run ID: {activeRunId} — {elapsedSince(runs.find((r) => r.run_id === activeRunId)?.started_at ?? null, now)}
            </span>
          )}
        </div>
        {error && <p className="text-xs text-red-400 mt-3">{error}</p>}
      </div>

      {/* Runs table */}
      <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-surface-border flex items-center justify-between">
          <span className="text-sm font-semibold text-white">Storico run</span>
          <button
            onClick={fetchRuns}
            className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
          >
            Aggiorna
          </button>
        </div>
        {loading ? (
          <div className="p-8 text-center text-slate-500 text-sm">Caricamento…</div>
        ) : runs.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">Nessuna run registrata</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-surface-border">
                  <th className="px-4 py-2 text-left font-medium">Run ID</th>
                  <th className="px-4 py-2 text-left font-medium">Status</th>
                  <th className="px-4 py-2 text-left font-medium">Avviata</th>
                  <th className="px-4 py-2 text-right font-medium">Durata</th>
                  <th className="px-4 py-2 text-right font-medium">Pag. sc.</th>
                  <th className="px-4 py-2 text-right font-medium">Richieste</th>
                  <th className="px-4 py-2 text-right font-medium">Trovati</th>
                  <th className="px-3 py-2 text-right font-medium text-emerald-600/70">Aste ins.</th>
                  <th className="px-3 py-2 text-right font-medium text-sky-600/70">Aste agg.</th>
                  <th className="px-3 py-2 text-right font-medium text-emerald-600/70">Prop. ins.</th>
                  <th className="px-3 py-2 text-right font-medium text-sky-600/70">Prop. agg.</th>
                  <th className="px-4 py-2 text-right font-medium">Errori</th>
                  <th className="px-4 py-2" />
                </tr>
              </thead>
              <tbody>
                {runs.map((r) => {
                  const stale = isStale(r, now)
                  let rowBg = ''
                  if (stale) rowBg = 'bg-amber-900/10'
                  else if (r.status === 'running') rowBg = 'bg-sky-900/10'
                  const durationCell = r.status === 'running'
                    ? <span className="text-sky-400">{elapsedSince(r.started_at, now)}</span>
                    : <span className="text-slate-400">{completedDuration(r)}</span>

                  return (
                    <tr key={r.id} className={`border-b border-surface-border/50 hover:bg-slate-800/30 ${rowBg}`}>
                      <td className="px-4 py-2 font-mono text-slate-400">{r.run_id}</td>
                      <td className="px-4 py-2">
                        <div className="flex items-center gap-1.5">
                          <StatusBadge status={r.status} />
                          {stale && <span title={`Attiva da più di ${STALE_HOURS}h`} className="text-amber-400 text-[10px]">⚠</span>}
                        </div>
                      </td>
                      <td className="px-4 py-2 text-slate-400">{fmt(r.started_at)}</td>
                      <td className="px-4 py-2 text-right">{durationCell}</td>
                      <td className="px-4 py-2 text-right text-slate-300">{r.pages_fetched}</td>
                      <td className="px-4 py-2 text-right text-slate-300">{r.requests_made}</td>
                      <td className="px-4 py-2 text-right text-slate-300">{r.records_found}</td>
                      <td className="px-3 py-2 text-right text-emerald-400 font-medium">{r.records_inserted}</td>
                      <td className="px-3 py-2 text-right text-sky-400">{r.records_updated}</td>
                      <td className="px-3 py-2 text-right text-emerald-400 font-medium">{r.properties_inserted}</td>
                      <td className="px-3 py-2 text-right text-sky-400">{r.properties_updated}</td>
                      <td className="px-4 py-2 text-right">
                        <span className={r.errors_count > 0 ? 'text-red-400 font-medium' : 'text-slate-500'}>
                          {r.errors_count}
                        </span>
                      </td>
                      <td className="px-4 py-2 text-right">
                        {r.status === 'running' && (
                          <button
                            onClick={() => handleCancel(r.run_id)}
                            disabled={cancelling === r.run_id}
                            className="px-2 py-0.5 rounded border border-red-700/50 text-red-400 hover:bg-red-900/20 disabled:opacity-40 transition-colors text-[10px] font-medium"
                          >
                            {cancelling === r.run_id ? 'Stop…' : 'Stop'}
                          </button>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
