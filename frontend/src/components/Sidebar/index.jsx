/**
 * RouteScope — Left Sidebar Navigation
 */
import { useEffect, useState } from 'react'
import { Route, AlertTriangle, BarChart2, History, RefreshCw } from 'lucide-react'
import axios from 'axios'
import useStore from '../../store/useStore'

const NAV_ITEMS = [
  { id: 'algorithms',    label: 'Algorithms',    icon: Route },
  { id: 'control',       label: 'Failure Ctrl',  icon: AlertTriangle },
  { id: 'survivability', label: 'Survivability', icon: BarChart2 },
  { id: 'history',       label: 'History',       icon: History },
]

// Derive live averages directly from graph.edges (updated every 2s by metric_update WS)
function useLiveMetrics(edges) {
  if (!edges?.length) return null
  const n = edges.length
  return {
    avgLatency:  (edges.reduce((s, e) => s + (e.latency ?? 0), 0) / n).toFixed(2),
    avgUtil:     (edges.reduce((s, e) => s + (e.utilization ?? 0), 0) / n).toFixed(1),
    avgLoss:     (edges.reduce((s, e) => s + (e.packet_loss ?? 0), 0) / n).toFixed(3),
    avgJitter:   (edges.reduce((s, e) => s + (e.jitter ?? 0), 0) / n).toFixed(2),
    maxUtil:     Math.max(...edges.map(e => e.utilization ?? 0)).toFixed(1),
  }
}

export default function Sidebar() {
  const { activePanel, setActivePanel, graph, graphHealth, isLive, wsStatus, setGraph, storageTier, storageBackend } = useStore()
  const [collectorStatus, setCollectorStatus] = useState(null)
  const liveMetrics = useLiveMetrics(graph.edges)

  // Poll collector status every 15s
  useEffect(() => {
    const fetch_ = () =>
      axios.get('/api/graph/collectors').then(r => setCollectorStatus(r.data)).catch(() => {})
    fetch_()
    const t = setInterval(fetch_, 15000)
    return () => clearInterval(t)
  }, [])

  const refreshGraph = async () => {
    try {
      await axios.post('/api/graph/refresh')
      const g = await axios.get('/api/graph')
      setGraph(g.data.graph, g.data.health, g.data.live)
    } catch (e) {
      console.warn('Refresh failed', e)
    }
  }

  const health = graphHealth?.health_score ?? 0
  const healthColor = health > 0.7 ? 'var(--accent-green)' : health > 0.4 ? 'var(--accent-orange)' : 'var(--accent-red)'

  return (
    <div className="sidebar-left">
      {/* Graph stats */}
      <div className="card" style={{ marginBottom: 4 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
          <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Graph
          </span>
          <button className="btn btn-secondary btn-sm" style={{ padding: '2px 6px' }} onClick={refreshGraph} title="Refresh topology">
            <RefreshCw size={11} />
          </button>
        </div>
        <div className="metrics-grid">
          <div className="metric-tile">
            <span className="label">Nodes</span>
            <span className="value">{graph.nodes?.length ?? 0}</span>
          </div>
          <div className="metric-tile">
            <span className="label">Links</span>
            <span className="value">{graph.edges?.length ?? 0}</span>
          </div>
          <div className="metric-tile">
            <span className="label">Health</span>
            <span className="value" style={{ color: healthColor }}>{(health * 100).toFixed(0)}%</span>
          </div>
          <div className="metric-tile">
            <span className="label">Util</span>
            <span className="value">{graphHealth?.avg_utilization_pct?.toFixed(0) ?? '—'}%</span>
          </div>
        </div>

        {/* Health bar */}
        <div className="util-bar" style={{ marginTop: 8 }}>
          <div className="util-bar-fill" style={{ width: `${health * 100}%`, background: healthColor }} />
        </div>

        <div style={{ marginTop: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span className={`status-dot ${isLive ? 'live' : 'sim'}`} />
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
            {isLive ? 'GNS3 Live' : 'Simulation'}
          </span>
        </div>

        {/* Layer 2 storage tier badge */}
        <div style={{ marginTop: 6, display: 'flex', alignItems: 'center', gap: 6 }}>
          <span style={{
            fontSize: '0.6rem', fontWeight: 800, padding: '2px 7px', borderRadius: 99,
            background: storageTier === 2 ? 'rgba(124,109,250,0.2)' : 'rgba(0,212,255,0.12)',
            color: storageTier === 2 ? '#a29bfe' : '#00d4ff',
            border: `1px solid ${storageTier === 2 ? '#7c6dfa55' : '#00d4ff44'}`,
            fontFamily: 'var(--font-mono)', letterSpacing: '0.05em',
            textTransform: 'uppercase',
          }}>
            L2 · Tier {storageTier}
          </span>
          <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>
            {storageBackend}
          </span>
        </div>
      </div>

      {/* WS status */}
      <div className={`conn-bar ${wsStatus}`} style={{ marginBottom: 4, justifyContent: 'center' }}>
        <span className={`status-dot ${wsStatus === 'connected' ? 'live' : wsStatus === 'connecting' ? 'sim' : 'error'}`} />
        {wsStatus === 'connected' ? 'Live Stream' : wsStatus === 'connecting' ? 'Connecting…' : 'Disconnected'}
      </div>

      <div className="section-divider" />
      <div className="section-label">Panels</div>

      {/* Navigation */}
      {NAV_ITEMS.map(({ id, label, icon: Icon }) => (
        <button
          key={id}
          id={`nav-${id}`}
          className={`nav-item ${activePanel === id ? 'active' : ''}`}
          onClick={() => setActivePanel(id)}
          style={{ background: 'none', border: activePanel === id ? '1px solid rgba(124,109,250,0.3)' : '1px solid transparent', width: '100%', textAlign: 'left' }}
        >
          <Icon size={15} className="nav-icon" />
          {label}
        </button>
      ))}

      <div className="section-divider" />

      {/* Live metrics panel — updates every 2s from metric_update WS */}
      {liveMetrics && (
        <div style={{ padding: '0 4px' }}>
          <div className="section-label" style={{ marginBottom: 6, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Live Metrics</span>
            <span style={{ fontSize: '0.6rem', color: 'var(--accent-green)', fontFamily: 'var(--font-mono)' }}>● live</span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
            {[
              { label: 'Avg Latency',  value: `${liveMetrics.avgLatency} ms` },
              { label: 'Avg Util',     value: `${liveMetrics.avgUtil}%`,  warn: liveMetrics.avgUtil > 70 },
              { label: 'Peak Util',    value: `${liveMetrics.maxUtil}%`,  warn: liveMetrics.maxUtil > 80 },
              { label: 'Avg Jitter',   value: `${liveMetrics.avgJitter} ms` },
              { label: 'Avg Loss',     value: `${liveMetrics.avgLoss}%`,  warn: liveMetrics.avgLoss > 1 },
            ].map(({ label, value, warn }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.72rem' }}>
                <span style={{ color: 'var(--text-muted)' }}>{label}</span>
                <span style={{ fontFamily: 'var(--font-mono)', fontWeight: 700, color: warn ? 'var(--accent-orange)' : 'var(--text-primary)' }}>
                  {value}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Collector status */}
      {collectorStatus && (
        <>
          <div className="section-divider" />
          <div style={{ padding: '0 4px' }}>
            <div className="section-label" style={{ marginBottom: 6 }}>Collectors</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              {Object.entries(collectorStatus.collectors).map(([name, info]) => (
                <div key={name} style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.7rem', alignItems: 'center' }}>
                  <span style={{ color: 'var(--text-muted)', textTransform: 'capitalize' }}>{name}</span>
                  <span style={{ fontWeight: 700, color: info.available ? 'var(--accent-green)' : 'var(--text-muted)' }}>
                    {info.available ? (name === 'iperf3' && !info.server_configured ? 'no server' : '✓') : '—'}
                  </span>
                </div>
              ))}
              <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: 2 }}>
                last collect: {Math.round(collectorStatus.last_collect_age_seconds)}s ago
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}
