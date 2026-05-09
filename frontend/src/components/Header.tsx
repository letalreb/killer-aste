import { Link } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

function TierBadge({ role }: { readonly role: string }) {
  if (role === 'admin') {
    return (
      <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-400 border border-purple-500/30 uppercase tracking-wider">
        Admin
      </span>
    )
  }
  if (role === 'premium') {
    return (
      <span className="hidden sm:inline text-[10px] font-bold px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-400 border border-amber-500/30 uppercase tracking-wider">
        Premium
      </span>
    )
  }
  return (
    <span className="hidden sm:inline text-[10px] font-bold px-1.5 py-0.5 rounded bg-slate-700 text-slate-500 border border-slate-700 uppercase tracking-wider">
      Standard
    </span>
  )
}

export function Header() {
  const { user, logout } = useAuthStore()

  return (
    <header className="bg-surface-card border-b border-surface-border px-6 py-3 flex items-center justify-between sticky top-0 z-40">
      <div className="flex items-center gap-3">
        <div className="w-7 h-7 rounded bg-emerald-500 flex items-center justify-center">
          <span className="text-white text-xs font-bold">KA</span>
        </div>
        <span className="font-semibold text-white text-sm tracking-tight">
          Killer Aste
        </span>
        <span className="hidden sm:inline text-slate-500 text-xs ml-1">
          Real Estate Intelligence
        </span>
      </div>

      <div className="flex items-center gap-3">
        {user?.role && <TierBadge role={user.role} />}
        {user?.role === 'admin' && (
          <Link
            to="/admin"
            className="text-xs px-2 py-1 rounded border border-purple-500/40 text-purple-400 hover:bg-purple-500/10 transition-colors"
          >
            Admin
          </Link>
        )}
        {user?.picture ? (
          <img
            src={user.picture}
            alt={user.name}
            className="w-7 h-7 rounded-full object-cover"
          />
        ) : (
          <div className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center">
            <span className="text-slate-300 text-xs font-semibold">
              {user?.name?.[0]?.toUpperCase() ?? '?'}
            </span>
          </div>
        )}
        <span className="hidden sm:inline text-slate-300 text-sm">{user?.name}</span>
        <button
          onClick={logout}
          className="text-slate-500 hover:text-slate-300 text-xs px-2 py-1 rounded border border-surface-border hover:border-slate-600 transition-colors"
        >
          Esci
        </button>
      </div>
    </header>
  )
}
