/**
 * RouteScope — App Root
 *
 * Layout: Topbar | Left Sidebar | Main Canvas | Right Panel
 * WebSocket is initialised at this level.
 */
import { useEffect } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Network, Cpu, Wifi, WifiOff, Activity } from 'lucide-react'
import axios from 'axios'
import Sidebar from './components/Sidebar'
import Dashboard from './pages/Dashboard'
import useStore from './store/useStore'
import { useWebSocket } from './hooks/useWebSocket'

function Topbar() {
  const { wsStatus, graph, survivabilityScore, algoResults } = useStore()
  const wsIcon = wsStatus === 'connected' ? <Wifi size={13} /> : <WifiOff size={13} />

  return (
    <header className="topbar">
      {/* Logo */}
      <a href="/" className="logo-mark" style={{ textDecoration: 'none' }}>
        <div className="logo-icon">RS</div>
        <div>
          <div className="logo-text">RouteScope</div>
          <div className="logo-sub">Network Routing Intelligence</div>
        </div>
      </a>

      <div style={{ width: 1, height: 28, background: 'var(--border)', margin: '0 8px' }} />

      {/* Topbar stats */}
      <div style={{ display: 'flex', gap: 20, flex: 1 }}>
        <TopStat icon={<Network size={13} />} label="Nodes" value={graph.nodes?.length ?? 0} />
        <TopStat icon={<Activity size={13} />} label="Links" value={graph.edges?.filter(e => !e.failed).length ?? 0} />
        {algoResults && (
          <TopStat icon={<Cpu size={13} />} label="Survivability" value={`${(survivabilityScore * 100).toFixed(0)}%`} />
        )}
      </div>

      {/* WS badge */}
      <div className={`conn-bar ${wsStatus}`}>
        {wsIcon}
        {wsStatus === 'connected' ? 'Live' : wsStatus === 'connecting' ? 'Connecting' : 'Offline'}
      </div>
    </header>
  )
}

function TopStat({ icon, label, value }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
      <span style={{ color: 'var(--text-muted)' }}>{icon}</span>
      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>{label}</span>
      <span style={{ fontWeight: 700, fontFamily: 'var(--font-mono)', fontSize: '0.875rem' }}>{value}</span>
    </div>
  )
}

function AppContent() {
  // Init WebSocket (singleton at app level)
  useWebSocket()

  const { setGraph } = useStore()

  // Bootstrap: fetch initial graph via REST
  useEffect(() => {
    axios.get('/api/graph').then((res) => {
      setGraph(res.data.graph, res.data.health, res.data.live)
    }).catch(console.warn)
  }, [])

  return (
    <div className="app-layout">
      <Topbar />
      <Sidebar />
      <Routes>
        <Route path="/*" element={<Dashboard />} />
      </Routes>
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AppContent />
    </BrowserRouter>
  )
}
