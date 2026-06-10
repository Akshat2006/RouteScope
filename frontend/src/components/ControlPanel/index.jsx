/**
 * RouteScope — Control Panel
 *
 * Failure injection, congestion simulation, and compute controls.
 */
import { useState } from 'react'
import { Play, Trash2, Zap, AlertTriangle, Wrench, Network, Layers } from 'lucide-react'
import axios from 'axios'
import useStore from '../../store/useStore'
import { useWebSocket } from '../../hooks/useWebSocket'

const FAILURE_TYPES = [
  { type: 'link_failure',  label: 'Link Fail',  icon: '⚡', color: '#ff4d6d' },
  { type: 'node_failure',  label: 'Node Fail',  icon: '🔴', color: '#ff4d6d' },
  { type: 'multi_link',   label: 'Multi-Link',  icon: '💥', color: '#ff9500' },
  { type: 'cascading',    label: 'Cascading',   icon: '🌊', color: '#ff6b6b' },
  { type: 'maintenance',  label: 'Maintenance', icon: '🔧', color: '#ffd700' },
  { type: 'congestion',   label: 'Congestion',  icon: '📈', color: '#a29bfe' },
]

export default function ControlPanel() {
  const {
    graph, source, destination,
    setSource, setDestination,
    setComputing, setAlgoResults,
    clearFailures, activeFailures,
    congestionLevel, setCongestionLevel,
  } = useStore()
  const { computeViaWS } = useWebSocket()

  const [selectedFailureType, setSelectedFailureType] = useState('link_failure')
  const [selectedElements, setSelectedElements] = useState([])
  const [injecting, setInjecting] = useState(false)
  const [msg, setMsg] = useState(null)

  const nodes = graph.nodes.filter((n) => !n.failed)
  const edges = graph.edges.filter((e) => !e.failed)
  const nodeLabel = Object.fromEntries(graph.nodes.map((n) => [n.id, n.label || n.id]))

  const showMsg = (text, type = 'info') => {
    setMsg({ text, type })
    setTimeout(() => setMsg(null), 3000)
  }

  const handleCompute = () => {
    if (!source || !destination) return showMsg('Select source and destination', 'warning')
    if (source === destination) return showMsg('Source and destination must differ', 'warning')
    setComputing(true)
    computeViaWS(source, destination)
  }

  const handleInjectFailure = async () => {
    if (!selectedElements.length) return showMsg('Select at least one element', 'warning')
    setInjecting(true)
    try {
      const body = {
        type: selectedFailureType,
        elements: selectedElements,
        description: `Manual ${selectedFailureType}`,
        congestion_pct: congestionLevel,
        recompute_source: source || undefined,
        recompute_destination: destination || undefined,
      }
      const res = await axios.post('/api/failure/inject', body)
      showMsg(`Injected: ${res.data.affected?.join(', ')}`, 'success')
      setSelectedElements([])
    } catch (e) {
      showMsg('Injection failed: ' + e.message, 'error')
    } finally {
      setInjecting(false)
    }
  }

  const handleClearFailures = async () => {
    try {
      await axios.delete('/api/failure/clear')
      clearFailures()
      showMsg('All failures cleared', 'success')
    } catch (e) {
      showMsg('Clear failed', 'error')
    }
  }

  const addElement = (type, value) => {
    if (type === 'link') {
      const [src, tgt] = value.split('::')
      if (!selectedElements.find((e) => e.source === src && e.target === tgt)) {
        setSelectedElements((el) => [...el, { source: src, target: tgt }])
      }
    } else if (type === 'node') {
      if (!selectedElements.find((e) => e.node === value)) {
        setSelectedElements((el) => [...el, { node: value, link_id: value }])
      }
    }
  }

  const needsNode = selectedFailureType === 'node_failure'
  const needsCongestion = selectedFailureType === 'congestion'

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%' }}>
      {/* Compute Section */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: '0.8125rem', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
          <Play size={14} style={{ color: 'var(--accent-purple)' }} /> Route Computation
        </div>

        <div className="form-group" style={{ marginBottom: 8 }}>
          <label>Source Node</label>
          <select id="source-select" value={source} onChange={(e) => setSource(e.target.value)}>
            <option value="">— select source —</option>
            {nodes.map((n) => <option key={n.id} value={n.id}>{n.label || n.id}</option>)}
          </select>
        </div>

        <div className="form-group" style={{ marginBottom: 10 }}>
          <label>Destination Node</label>
          <select id="dest-select" value={destination} onChange={(e) => setDestination(e.target.value)}>
            <option value="">— select destination —</option>
            {nodes.map((n) => <option key={n.id} value={n.id}>{n.label || n.id}</option>)}
          </select>
        </div>

        <button id="compute-btn" className="btn btn-primary w-full" onClick={handleCompute}>
          <Zap size={14} /> Run All 6 Algorithms
        </button>
      </div>

      {/* Failure Type */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: '0.8125rem', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
          <AlertTriangle size={14} style={{ color: 'var(--accent-red)' }} /> Failure Injection
        </div>

        <div className="failure-grid" style={{ marginBottom: 10 }}>
          {FAILURE_TYPES.map((ft) => (
            <button
              key={ft.type}
              className={`failure-btn ${selectedFailureType === ft.type ? 'active' : ''}`}
              onClick={() => setSelectedFailureType(ft.type)}
            >
              {ft.icon} {ft.label}
            </button>
          ))}
        </div>

        {/* Element selector */}
        {!needsCongestion && (
          <div className="form-group" style={{ marginBottom: 8 }}>
            <label>{needsNode ? 'Select Node to Fail' : 'Select Link to Fail'}</label>
            <select
              onChange={(e) => {
                if (e.target.value) {
                  addElement(needsNode ? 'node' : 'link', e.target.value)
                  e.target.value = ''
                }
              }}
            >
              <option value="">— pick element —</option>
              {needsNode
                ? nodes.map((n) => <option key={n.id} value={n.id}>{n.label || n.id}</option>)
                : edges.map((e) => <option key={e.id} value={`${e.source}::${e.target}`}>{nodeLabel[e.source] || e.source} ↔ {nodeLabel[e.target] || e.target}</option>)
              }
            </select>
          </div>
        )}

        {/* Congestion slider */}
        {needsCongestion && (
          <>
            <div className="form-group" style={{ marginBottom: 8 }}>
              <label>Select Link</label>
              <select onChange={(e) => { if (e.target.value) addElement('link', e.target.value) }}>
                <option value="">— pick link —</option>
                {edges.map((e) => <option key={e.id} value={`${e.source}::${e.target}`}>{nodeLabel[e.source] || e.source} ↔ {nodeLabel[e.target] || e.target}</option>)}
              </select>
            </div>
            <div className="form-group" style={{ marginBottom: 8 }}>
              <label>Congestion Level: {congestionLevel}%</label>
              <input
                type="range" min={0} max={100} value={congestionLevel}
                onChange={(e) => setCongestionLevel(Number(e.target.value))}
              />
            </div>
          </>
        )}

        {/* Selected elements */}
        {selectedElements.length > 0 && (
          <div style={{ marginBottom: 8 }}>
            <label>Queued</label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
              {selectedElements.map((el, i) => (
                <span key={i} className="badge badge-warning" style={{ cursor: 'pointer' }}
                  onClick={() => setSelectedElements((prev) => prev.filter((_, j) => j !== i))}>
                  {el.node || `${el.source}↔${el.target}`} ×
                </span>
              ))}
            </div>
          </div>
        )}

        <div style={{ display: 'flex', gap: 6 }}>
          <button id="inject-btn" className="btn btn-danger flex-1" onClick={handleInjectFailure} disabled={injecting}>
            <AlertTriangle size={13} /> Inject
          </button>
          <button id="clear-btn" className="btn btn-success flex-1" onClick={handleClearFailures}>
            <Trash2 size={13} /> Clear All
          </button>
        </div>
      </div>

      {/* Active failures */}
      {activeFailures.length > 0 && (
        <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
          <div style={{ fontWeight: 600, fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: 6 }}>
            Active Failures ({activeFailures.length})
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            {activeFailures.slice(-5).map((f, i) => (
              <div key={i} className="badge badge-danger" style={{ justifyContent: 'flex-start', borderRadius: 4 }}>
                {f.type}: {Array.isArray(f.affected) ? f.affected.join(', ') : f.affected}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Status message */}
      {msg && (
        <div
          className={`badge ${msg.type === 'success' ? 'badge-success' : msg.type === 'warning' ? 'badge-warning' : 'badge-danger'}`}
          style={{ margin: 12, padding: '8px 12px', borderRadius: 'var(--radius-sm)', display: 'block', fontSize: '0.75rem' }}
        >
          {msg.text}
        </div>
      )}
    </div>
  )
}
