import { apiClient } from './client'

const SKIP_AUTH = import.meta.env.VITE_SKIP_AUTH === 'true'

export interface IngestionRun {
  id: string
  run_id: string
  source: string
  mode: string
  status: 'running' | 'completed' | 'failed' | 'dry_run'
  started_at: string | null
  completed_at: string | null
  pages_fetched: number
  records_found: number
  records_inserted: number
  records_updated: number
  errors_count: number
  requests_made: number
  error_detail: string | null
}

export interface AdminStats {
  users: {
    total: number
    by_role: Record<string, number>
    logins_last_30d: number
  }
  auctions: {
    total: number
    by_status: Record<string, number>
    with_roi: number
  }
  properties: {
    total: number
  }
  ingestion: {
    total_runs: number
    last_successful_at: string | null
    last_run_inserted: number
  }
  sources: string[]
}

export interface AdminUser {
  id: string
  email: string
  name: string
  picture: string | null
  role: string
  is_active: boolean
  max_favorites: number
  last_login_at: string | null
  created_at: string
}

const MOCK_RUNS: IngestionRun[] = [
  {
    id: 'mock-1', run_id: 'abc12345', source: 'pvp', mode: 'safe', status: 'completed',
    started_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3540000).toISOString(),
    pages_fetched: 12, records_found: 240, records_inserted: 18, records_updated: 42,
    errors_count: 0, requests_made: 14, error_detail: null,
  },
  {
    id: 'mock-2', run_id: 'def67890', source: 'pvp', mode: 'safe', status: 'failed',
    started_at: new Date(Date.now() - 86400000).toISOString(),
    completed_at: new Date(Date.now() - 86350000).toISOString(),
    pages_fetched: 3, records_found: 60, records_inserted: 0, records_updated: 0,
    errors_count: 5, requests_made: 4, error_detail: 'AccessDenied: rate limit reached',
  },
]

const MOCK_STATS: AdminStats = {
  users: { total: 3, by_role: { standard: 1, premium: 1, admin: 1 }, logins_last_30d: 12 },
  auctions: { total: 580, by_status: { scheduled: 412, completed: 140, cancelled: 28 }, with_roi: 395 },
  properties: { total: 548 },
  ingestion: { total_runs: 2, last_successful_at: new Date(Date.now() - 3540000).toISOString(), last_run_inserted: 18 },
  sources: ['pvp.giustizia.it'],
}

const MOCK_USERS: AdminUser[] = [
  { id: 'mock-u1', email: 'admin@local', name: 'Dev Admin', picture: null, role: 'admin', is_active: true, max_favorites: 999, last_login_at: new Date().toISOString(), created_at: new Date().toISOString() },
  { id: 'mock-u2', email: 'premium@local', name: 'Premium User', picture: null, role: 'premium', is_active: true, max_favorites: 10, last_login_at: new Date(Date.now() - 86400000).toISOString(), created_at: new Date().toISOString() },
  { id: 'mock-u3', email: 'user@local', name: 'Standard User', picture: null, role: 'standard', is_active: true, max_favorites: 3, last_login_at: null, created_at: new Date().toISOString() },
]

export const adminApi = {
  triggerIngestion: async (source = 'pvp', dry_run = false) => {
    if (SKIP_AUTH) return { status: 'queued', source, dry_run }
    const { data } = await apiClient.post('/api/v1/admin/ingestion/trigger', { source, dry_run })
    return data as { status: string; source: string; dry_run: boolean }
  },

  listRuns: async (limit = 20) => {
    if (SKIP_AUTH) return MOCK_RUNS.slice(0, limit)
    const { data } = await apiClient.get<IngestionRun[]>('/api/v1/admin/ingestion/runs', { params: { limit } })
    return data
  },

  getRun: async (run_id: string) => {
    if (SKIP_AUTH) return MOCK_RUNS.find((r) => r.run_id === run_id) ?? MOCK_RUNS[0]
    const { data } = await apiClient.get<IngestionRun>(`/api/v1/admin/ingestion/runs/${run_id}`)
    return data
  },

  getStats: async () => {
    if (SKIP_AUTH) return MOCK_STATS
    const { data } = await apiClient.get<AdminStats>('/api/v1/admin/stats')
    return data
  },

  listUsers: async () => {
    if (SKIP_AUTH) return MOCK_USERS
    const { data } = await apiClient.get<AdminUser[]>('/api/v1/admin/users')
    return data
  },

  setRole: async (userId: string, role: string) => {
    if (SKIP_AUTH) return { user_id: userId, role }
    const { data } = await apiClient.patch(`/api/v1/admin/users/${userId}/role`, { role })
    return data as { user_id: string; role: string }
  },

  cancelRun: async (run_id: string) => {
    if (SKIP_AUTH) return { run_id, status: 'cancel_requested' }
    const { data } = await apiClient.post(`/api/v1/admin/ingestion/runs/${run_id}/cancel`)
    return data as { run_id: string; status: string }
  },
}
