import { useAuthStore } from '../store/authStore'

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
