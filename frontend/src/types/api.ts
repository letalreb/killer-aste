export interface Property {
  id: string
  external_id: string
  source: string
  address?: string
  city?: string
  province?: string
  postal_code?: string
  property_type: string
  area_sqm?: number
  floor?: number
  rooms?: number
  market_value_estimate?: number
  latitude?: number
  longitude?: number
  encumbrances?: string
  condition_notes?: string
  created_at: string
  updated_at: string
}

export interface Valuation {
  id: string
  auction_id: string
  market_value?: number
  purchase_price?: number
  total_acquisition_cost?: number
  net_profit_estimate?: number
  roi_percentage?: number
  payback_years?: number
  assumptions?: Record<string, unknown>
  created_at: string
}

export type RiskSeverity = 'low' | 'medium' | 'high' | 'critical'

export interface RiskFlag {
  id: string
  flag_type: string
  severity: RiskSeverity
  score_contribution?: number
  description: string
  extra?: Record<string, unknown>
}

export interface Auction {
  id: string
  external_id: string
  source: string
  court?: string
  procedure_number?: string
  auction_type: string
  status: string
  base_price?: number
  minimum_bid?: number
  bid_increment?: number
  deposit_required?: number
  auction_date?: string
  auction_deadline?: string
  source_url?: string
  property?: Property
  valuations: Valuation[]
  risk_flags: RiskFlag[]
  created_at: string
  updated_at: string
}

export interface AuctionStats {
  [status: string]: number
}

export type UserRole = 'standard' | 'premium' | 'admin'

export interface User {
  sub: string
  email: string
  name: string
  picture?: string
  role: UserRole
  max_favorites: number
}

export interface AuthResponse {
  access_token: string
  token_type: string
  expires_in: number
  user: User
}

export interface FilterState {
  minRoi: number
  riskLevel: 'all' | 'low' | 'medium' | 'high'
  city: string
  minPrice: number
  maxPrice: number
  sortBy: 'roi' | 'date' | 'price' | 'score'
  showPast: boolean
}
