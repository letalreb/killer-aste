import { useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useAuthStore } from '../store/authStore'

const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === 'true'

const DEV_USER = {
  sub: 'dev',
  email: 'dev@local',
  name: 'Dev User',
  picture: undefined,
}

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, setAuth } = useAuthStore()

  useEffect(() => {
    if (SKIP_AUTH && !token) setAuth('dev-token', DEV_USER)
  }, [token, setAuth])

  if (!SKIP_AUTH && !token) return <Navigate to="/login" replace />
  return <>{children}</>
}
