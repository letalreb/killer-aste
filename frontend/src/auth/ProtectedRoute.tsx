import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'
import { useFavoritesStore } from '../store/favoritesStore'

const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === 'true'

const DEV_USER = {
  sub: 'dev',
  email: 'dev@local',
  name: 'Dev User',
  picture: undefined,
  role: 'admin' as const,
  max_favorites: 3,
}

export function ProtectedRoute({ children }: { readonly children: React.ReactNode }) {
  const { token, user, setAuth } = useAuthStore()
  const setMaxFavorites = useFavoritesStore((s) => s.setMaxFavorites)

  useEffect(() => {
    if (SKIP_AUTH) setAuth('dev-token', DEV_USER)
  }, [setAuth])

  useEffect(() => {
    if (user?.max_favorites) setMaxFavorites(user.max_favorites)
  }, [user?.max_favorites, setMaxFavorites])

  if (!SKIP_AUTH && !token) return <Navigate to="/login" replace />
  return <>{children}</>
}
