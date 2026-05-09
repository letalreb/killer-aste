import { useNavigate } from 'react-router-dom'
import { GoogleLogin } from '@react-oauth/google'
import { authApi } from '../api/auth'
import { useAuthStore } from '../store/authStore'
import { useState } from 'react'

const GOOGLE_CLIENT_ID = import.meta.env.VITE_GOOGLE_CLIENT_ID ?? ''

const ERROR_KEY = 'ka-login-error'

function persistError(msg: string) {
  sessionStorage.setItem(ERROR_KEY, msg)
}
function clearPersistedError() {
  sessionStorage.removeItem(ERROR_KEY)
}

export function LoginPage() {
  const navigate = useNavigate()
  const setAuth = useAuthStore((s) => s.setAuth)
  const [error, setError] = useState<string | null>(() => sessionStorage.getItem(ERROR_KEY))
  const [loading, setLoading] = useState(false)

  const showError = (msg: string) => {
    persistError(msg)
    setError(msg)
  }

  const handleSuccess = async (credential: string) => {
    setLoading(true)
    clearPersistedError()
    setError(null)
    try {
      const res = await authApi.googleLogin(credential)
      setAuth(res.access_token, res.user)
      navigate('/', { replace: true })
    } catch {
      showError('Accesso non riuscito. Riprova.')
    } finally {
      setLoading(false)
    }
  }

  const handleGoogleError = () => {
    showError(
      "Login Google non riuscito. Se l'errore persiste, l'origine di questa pagina potrebbe non essere autorizzata nella Google Cloud Console."
    )
  }

  const missingClientId = !GOOGLE_CLIENT_ID

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

          {missingClientId && (
            <div className="mb-4 px-3 py-2 rounded-lg bg-amber-900/30 border border-amber-700/50 text-amber-400 text-xs">
              ⚠ <strong>VITE_GOOGLE_CLIENT_ID</strong> non configurato. Il login Google non è disponibile.
            </div>
          )}

          {error && (
            <div className="mb-4 px-3 py-2 rounded-lg bg-red-900/30 border border-red-800/50 text-red-400 text-xs leading-relaxed flex items-start gap-2">
              <span className="flex-1">{error}</span>
              <button
                onClick={() => { clearPersistedError(); setError(null) }}
                className="flex-shrink-0 text-red-600 hover:text-red-400 leading-none mt-0.5"
                aria-label="Chiudi"
              >
                ✕
              </button>
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
                onError={handleGoogleError}
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
