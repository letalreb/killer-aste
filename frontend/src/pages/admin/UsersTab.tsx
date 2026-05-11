import { useState, useEffect, useCallback } from 'react'
import { adminApi, type AdminUser } from '../../api/admin'

const ROLES = ['standard', 'premium', 'admin'] as const
type Role = typeof ROLES[number]

const ROLE_STYLE: Record<Role, string> = {
  admin:    'bg-purple-500/15 text-purple-400 border-purple-500/30',
  premium:  'bg-amber-500/15 text-amber-400 border-amber-500/30',
  standard: 'bg-slate-700 text-slate-400 border-slate-600',
}

function RoleBadge({ role }: { role: string }) {
  const style = ROLE_STYLE[role as Role] ?? ROLE_STYLE.standard
  return (
    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded border uppercase tracking-wider ${style}`}>
      {role}
    </span>
  )
}

function fmt(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}

export function UsersTab() {
  const [users, setUsers] = useState<AdminUser[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState<string | null>(null)
  const [search, setSearch] = useState('')

  const fetchUsers = useCallback(async () => {
    try {
      const data = await adminApi.listUsers()
      setUsers(data)
    } catch {
      setError('Errore nel caricamento utenti')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchUsers() }, [fetchUsers])

  const handleRoleChange = async (userId: string, newRole: string) => {
    setSaving(userId)
    try {
      await adminApi.setRole(userId, newRole)
      setUsers((prev) => prev.map((u) => u.id === userId ? { ...u, role: newRole } : u))
    } catch {
      setError('Errore nel cambio ruolo')
    } finally {
      setSaving(null)
    }
  }

  const filtered = search.trim()
    ? users.filter((u) =>
        u.email.toLowerCase().includes(search.toLowerCase()) ||
        u.name.toLowerCase().includes(search.toLowerCase())
      )
    : users

  return (
    <div className="space-y-4">
      {/* Search */}
      <div className="flex items-center gap-3">
        <input
          type="text"
          placeholder="Cerca per nome o email…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="flex-1 max-w-xs bg-surface-card border border-surface-border rounded-lg px-3 py-1.5 text-sm text-slate-300 placeholder:text-slate-600 focus:outline-none focus:border-slate-500"
        />
        <span className="text-xs text-slate-500">{filtered.length} utenti</span>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      <div className="bg-surface-card border border-surface-border rounded-xl overflow-hidden">
        {loading ? (
          <div className="p-8 text-center text-slate-500 text-sm">Caricamento…</div>
        ) : filtered.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">Nessun utente trovato</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="text-slate-500 border-b border-surface-border">
                  <th className="px-4 py-2 text-left font-medium">Utente</th>
                  <th className="px-4 py-2 text-left font-medium">Email</th>
                  <th className="px-4 py-2 text-left font-medium">Ruolo</th>
                  <th className="px-4 py-2 text-right font-medium">Max ♡</th>
                  <th className="px-4 py-2 text-left font-medium">Ultimo login</th>
                  <th className="px-4 py-2 text-left font-medium">Registrato</th>
                  <th className="px-4 py-2 text-left font-medium">Cambia ruolo</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((u) => (
                  <tr key={u.id} className="border-b border-surface-border/50 hover:bg-slate-800/30">
                    <td className="px-4 py-2">
                      <div className="flex items-center gap-2">
                        {u.picture ? (
                          <img src={u.picture} alt={u.name} className="w-6 h-6 rounded-full object-cover" />
                        ) : (
                          <div className="w-6 h-6 rounded-full bg-slate-700 flex items-center justify-center text-slate-400 text-[10px] font-bold">
                            {u.name[0]?.toUpperCase()}
                          </div>
                        )}
                        <span className="text-slate-300">{u.name}</span>
                      </div>
                    </td>
                    <td className="px-4 py-2 text-slate-400 font-mono">{u.email}</td>
                    <td className="px-4 py-2"><RoleBadge role={u.role} /></td>
                    <td className="px-4 py-2 text-right text-slate-400">{u.max_favorites}</td>
                    <td className="px-4 py-2 text-slate-400">{fmt(u.last_login_at)}</td>
                    <td className="px-4 py-2 text-slate-500">{fmt(u.created_at)}</td>
                    <td className="px-4 py-2">
                      <select
                        value={u.role}
                        disabled={saving === u.id}
                        onChange={(e) => handleRoleChange(u.id, e.target.value)}
                        className="bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-300 focus:outline-none focus:border-slate-500 disabled:opacity-40"
                      >
                        {ROLES.map((r) => (
                          <option key={r} value={r}>{r}</option>
                        ))}
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
