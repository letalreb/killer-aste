import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { MapContainer, TileLayer, useMap } from 'react-leaflet'
import MarkerClusterGroup from 'react-leaflet-cluster'
import L from 'leaflet'
import type { Auction } from '../types/api'
import { getROI, getRiskGrade, getRiskScore, formatCurrency, getOverallScore } from '../utils/formatters'

// Fix Leaflet's broken default icon paths when bundled with Vite
import iconUrl from 'leaflet/dist/images/marker-icon.png'
import iconRetinaUrl from 'leaflet/dist/images/marker-icon-2x.png'
import shadowUrl from 'leaflet/dist/images/marker-shadow.png'
delete (L.Icon.Default.prototype as unknown as Record<string, unknown>)._getIconUrl
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl })

interface Props {
  readonly auctions: Auction[]
}

// ── Marker colours by ROI ─────────────────────────────────────────────────────
function roiColor(roi: number | null): string {
  if (roi == null) return '#64748b'   // slate — no data
  if (roi >= 20)   return '#10b981'   // emerald — great deal
  if (roi >= 10)   return '#f59e0b'   // amber   — decent
  return '#64748b'                     // slate   — low
}

function makeIcon(roi: number | null): L.DivIcon {
  const color = roiColor(roi)
  const size = roi != null && roi >= 20 ? 14 : 11
  return L.divIcon({
    className: '',
    html: `<div style="
      width:${size}px;height:${size}px;
      background:${color};
      border:2px solid rgba(255,255,255,0.5);
      border-radius:50%;
      box-shadow:0 0 6px ${color}88;
    "></div>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
    popupAnchor: [0, -(size / 2 + 4)],
  })
}

// ── Italy bounds auto-fit ─────────────────────────────────────────────────────
function FitBounds({ points }: { points: [number, number][] }) {
  const map = useMap()
  useEffect(() => {
    if (points.length === 0) return
    if (points.length === 1) {
      map.setView(points[0], 13)
      return
    }
    const bounds = L.latLngBounds(points)
    map.fitBounds(bounds, { padding: [40, 40] })
  }, [map, points])
  return null
}

// ── Popup content (plain HTML string — no JSX in Leaflet popups) ─────────────
function popupHtml(auction: Auction, roi: number | null): string {
  const prop = auction.property
  const score = getOverallScore(auction)
  const riskGrade = getRiskGrade(getRiskScore(auction))
  const riskLabel: Record<string, string> = {
    low: 'Basso', medium: 'Medio', high: 'Alto', critical: 'Critico',
  }
  return `
    <div style="font-family:system-ui,sans-serif;min-width:200px">
      <div style="font-size:11px;color:#94a3b8;margin-bottom:2px">
        ${prop?.city ?? ''}${prop?.province ? ` (${prop.province})` : ''}
      </div>
      <div style="font-size:14px;font-weight:600;color:#e2e8f0;margin-bottom:8px;line-height:1.3">
        ${prop?.address ?? prop?.city ?? '—'}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;margin-bottom:10px">
        <div style="background:#0f172a;border-radius:6px;padding:6px 8px;text-align:center">
          <div style="font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.05em">ROI</div>
          <div style="font-size:16px;font-weight:700;color:${roiColor(roi)}">${roi != null ? roi.toFixed(1) + '%' : '—'}</div>
        </div>
        <div style="background:#0f172a;border-radius:6px;padding:6px 8px;text-align:center">
          <div style="font-size:9px;color:#475569;text-transform:uppercase;letter-spacing:.05em">Score</div>
          <div style="font-size:16px;font-weight:700;color:#e2e8f0">${score}</div>
        </div>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px">
        <span style="font-size:12px;color:#94a3b8">Base asta</span>
        <span style="font-size:13px;font-weight:600;color:#f1f5f9">${formatCurrency(auction.base_price)}</span>
      </div>
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">
        <span style="font-size:12px;color:#94a3b8">Rischio</span>
        <span style="font-size:11px;font-weight:600;color:#94a3b8">${riskLabel[riskGrade] ?? riskGrade}</span>
      </div>
      <a href="/auctions/${auction.id}" style="
        display:block;text-align:center;padding:6px;
        background:#065f46;color:#6ee7b7;border-radius:6px;
        font-size:12px;font-weight:600;text-decoration:none;
      ">Vedi dettaglio →</a>
    </div>
  `
}

// ── Main component ────────────────────────────────────────────────────────────
export function MapView({ auctions }: Props) {
  const navigate = useNavigate()

  // Only auctions that have coordinates
  const mapped = auctions.filter(
    (a) => a.property?.latitude != null && a.property?.longitude != null
  )

  const points: [number, number][] = mapped.map((a) => [
    Number(a.property!.latitude),
    Number(a.property!.longitude),
  ])

  const unmappedCount = auctions.length - mapped.length

  return (
    <div className="relative flex-1 min-h-0 rounded-xl overflow-hidden border border-surface-border">
      {unmappedCount > 0 && (
        <div className="absolute top-3 right-3 z-[1000] bg-slate-900/90 backdrop-blur text-xs text-slate-400 px-3 py-1.5 rounded-lg border border-surface-border pointer-events-none">
          {mapped.length} su mappa · {unmappedCount} senza coordinate
        </div>
      )}

      {mapped.length === 0 ? (
        <div className="flex items-center justify-center h-full text-slate-500 text-sm">
          Nessuna asta con coordinate disponibili
        </div>
      ) : (
        <MapContainer
          center={[41.9, 12.5]}
          zoom={6}
          style={{ height: '100%', width: '100%', background: '#0f172a' }}
          zoomControl={true}
        >
          {/* CartoDB Dark Matter — dark tile, free, no API key */}
          <TileLayer
            attribution='&copy; <a href="https://carto.com">CARTO</a> &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
            url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
            subdomains="abcd"
            maxZoom={19}
          />

          <FitBounds points={points} />

          <MarkerClusterGroup
            chunkedLoading
            showCoverageOnHover={false}
            maxClusterRadius={50}
            iconCreateFunction={(cluster: { getChildCount: () => number }) => {
              const count = cluster.getChildCount()
              const size = count > 50 ? 44 : count > 10 ? 36 : 28
              return L.divIcon({
                className: '',
                html: `<div style="
                  width:${size}px;height:${size}px;
                  background:rgba(16,185,129,0.15);
                  border:2px solid rgba(16,185,129,0.5);
                  border-radius:50%;
                  display:flex;align-items:center;justify-content:center;
                  font-size:${size < 36 ? 11 : 13}px;
                  font-weight:700;color:#6ee7b7;
                  backdrop-filter:blur(4px);
                ">${count}</div>`,
                iconSize: [size, size],
                iconAnchor: [size / 2, size / 2],
              })
            }}
          >
            {mapped.map((auction) => {
              const roi = getROI(auction)
              const icon = makeIcon(roi)
              const lat = Number(auction.property!.latitude)
              const lng = Number(auction.property!.longitude)
              // Use L.marker imperatively so we can wire the popup click
              const marker = L.marker([lat, lng], { icon })
              marker.bindPopup(popupHtml(auction, roi), {
                maxWidth: 260,
                className: 'ka-popup',
              })
              marker.on('popupopen', () => {
                // Wire the "Vedi dettaglio" link inside the popup to use React Router
                setTimeout(() => {
                  const link = document.querySelector<HTMLAnchorElement>(
                    `.ka-popup a[href="/auctions/${auction.id}"]`
                  )
                  if (link) {
                    link.addEventListener('click', (e) => {
                      e.preventDefault()
                      navigate(`/auctions/${auction.id}`)
                    })
                  }
                }, 0)
              })
              // Return a React component that wraps the imperative marker
              return (
                <ImperativeMarker
                  key={auction.id}
                  marker={marker}
                  lat={lat}
                  lng={lng}
                />
              )
            })}
          </MarkerClusterGroup>
        </MapContainer>
      )}

      {/* Legend */}
      <div className="absolute bottom-6 left-3 z-[1000] bg-slate-900/90 backdrop-blur rounded-lg border border-surface-border px-3 py-2 space-y-1 pointer-events-none">
        {[
          { color: '#10b981', label: 'ROI ≥ 20%' },
          { color: '#f59e0b', label: 'ROI 10–20%' },
          { color: '#64748b', label: 'ROI < 10%' },
        ].map(({ color, label }) => (
          <div key={label} className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full flex-shrink-0" style={{ background: color }} />
            <span className="text-[10px] text-slate-400">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Thin wrapper that adds an imperative Leaflet marker to the cluster ────────
function ImperativeMarker({
  marker,
}: {
  marker: L.Marker
  lat: number
  lng: number
}) {
  const map = useMap()
  useEffect(() => {
    marker.addTo(map)
    return () => { marker.removeFrom(map) }
  }, [map, marker])
  return null
}
