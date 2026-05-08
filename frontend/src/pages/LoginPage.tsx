import { useNavigate } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { useState } from 'react'

export function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const handleSuccess = async (credential: string) => {
    setLoading(true)
    setError(null)
    try {
      const res = await authApi.googleLogin(credential)
      setAuth(res.access_token, res.user)
      navigate('/', { replace: true })
    } catch {
      setError('Accesso non riuscito. Riprova.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-surface flex flex-col items-center justify-center p-6">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500 flex items-center justify-center mx-auto mb-4 shadow-lg shadow-emerald-900/40">
            <span className="text-white text-xl font-bold">KA</span>
          </div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Killer Aste</h1>
          <p className="text-slate-500 text-sm mt-1">Real Estate Intelligence Platform</p>
        </div>

        {/* Card */}
        <div className="bg-surface-card border border-surface-border rounded-2xl p-8 shadow-xl">
          <h2 className="text-base font-semibold text-slate-200 mb-1">Accedi alla piattaforma</h2>
          <p className="text-slate-500 text-sm mb-6">
            Analizza le migliori aste immobiliari per ROI, rischio e ranking.
          </p>

          {error && (
            <div className="mb-4 px-3 py-2 rounded-lg bg-red-900/30 border border-red-800/50 text-red-400 text-xs">
              {error}
            </div>
          )}

          {loading ? (
            <div className="flex items-center justify-center py-3">
              <div className="w-5 h-5 border-2 border-emerald-500 border-t-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="flex justify-center">
              <GoogleLogin
                onSuccess={(res) => {
                  if (res.credential) handleSuccess(res.credential)
                }}
                onError={() => setError('Errore durante il login con Google.')}
                theme="filled_black"
                shape="rectangular"
                size="large"
                text="continue_with"
                locale="it"
              />
            </div>
          )}
        </div>

        <p className="text-center text-slate-600 text-xs mt-6">
          Piattaforma ad uso interno — accesso riservato
        </p>
      </div>
    </div>
  )
}
