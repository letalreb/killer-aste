import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Header } from '../../components/Header'
import { IngestionTab } from './IngestionTab'
import { StatsTab } from './StatsTab'
import { UsersTab } from './UsersTab'

type Tab = 'ingestion' | 'stats' | 'users'

const TABS: { id: Tab; label: string; description: string }[] = [
  { id: 'ingestion', label: 'Ingestion', description: 'Storico e avvio run di scraping' },
  { id: 'stats',     label: 'Statistiche', description: 'KPI di piattaforma' },
  { id: 'users',     label: 'Utenti', description: 'Gestione ruoli e accessi' },
]

export function AdminPage() {
  const [activeTab, setActiveTab] = useState<Tab>('ingestion')
  const navigate = useNavigate()

  return (
    <div className="min-h-screen bg-surface">
      <Header />

      <div className="max-w-6xl mx-auto px-4 py-8">
        {/* Page header */}
        <div className="flex items-center gap-3 mb-6">
          <button
            onClick={() => navigate('/')}
            className="text-slate-500 hover:text-slate-300 text-xs transition-colors"
          >
            ← Dashboard
          </button>
          <span className="text-slate-700">/</span>
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30 uppercase tracking-wider">
              Admin
            </span>
            <h1 className="text-base font-semibold text-white">Pannello di controllo</h1>
          </div>
        </div>

        {/* Tab bar */}
        <div className="flex gap-1 bg-surface-card border border-surface-border rounded-xl p-1 mb-6 w-fit">
          {TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                activeTab === tab.id
                  ? 'bg-purple-600/20 text-purple-300 border border-purple-500/30'
                  : 'text-slate-500 hover:text-slate-300'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Tab description */}
        <p className="text-xs text-slate-500 mb-5">
          {TABS.find((t) => t.id === activeTab)?.description}
        </p>

        {/* Tab content */}
        {activeTab === 'ingestion' && <IngestionTab />}
        {activeTab === 'stats'     && <StatsTab />}
        {activeTab === 'users'     && <UsersTab />}
      </div>
    </div>
  )
}
