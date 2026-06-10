/**
 * RouteScope — Algorithm Results Panel
 *
 * Shows per-algorithm result cards with:
 *   - Path, cost, hop count, runtime, convergence
 *   - Color-coded badge matching graph overlay
 *   - Toggle visibility (hides overlay in graph)
 *   - Survivability contribution badge
 *   - Metadata accordion (LFA table, ECMP paths, etc.)
 */
import { useState } from 'react'
import { ChevronDown, ChevronRight, Eye, EyeOff, Zap, Route, Clock, Activity } from 'lucide-react'
import useStore from '../../store/useStore'

function costColor(cost, allCosts) {
  if (cost === null || cost === undefined) return 'var(--text-muted)'
  const validCosts = allCosts.filter((c) => c !== null && c !== undefined && isFinite(c))
  if (!validCosts.length) return 'var(--text-primary)'
  const min = Math.min(...validCosts)
  const max = Math.max(...validCosts)
  if (cost === min) return 'var(--accent-green)'
  if (cost === max) return 'var(--accent-red)'
  return 'var(--accent-orange)'
}

function AlgoCard({ result, allCosts, rank }) {
  const [expanded, setExpanded] = useState(false)
  const { visibleAlgos, toggleAlgo } = useStore()
  const visible = visibleAlgos[result.algorithm] !== false

  const pathStr = result.path?.join(' → ') || '—'
  const isFastest = result.convergence_ms === Math.min(...allCosts.filter((c) => c < Infinity))

  return (
    <div
      className={`algo-card fade-in ${!result.reachable ? 'unreachable' : ''}`}
      style={{ borderLeftColor: result.color, borderLeftWidth: 3 }}
    >
      <div className="algo-header">
        <div className="algo-dot" style={{ color: result.color, background: result.color }} />
        <span className="algo-name">{result.algorithm}</span>
        <div style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          {result.reachable ? (
            <span className="badge badge-success">✓ Reachable</span>
          ) : (
            <span className="badge badge-danger">✗ Unreachable</span>
          )}
          <button
            className="btn btn-secondary btn-sm"
            style={{ padding: '2px 6px' }}
            onClick={() => toggleAlgo(result.algorithm)}
            title={visible ? 'Hide overlay' : 'Show overlay'}
          >
            {visible ? <Eye size={12} /> : <EyeOff size={12} />}
          </button>
        </div>
      </div>

      {result.reachable && (
        <>
          <div className="algo-stats">
            <div className="algo-stat">
              <span className="s-label">Cost</span>
              <span className="s-value" style={{ color: costColor(result.cost, allCosts) }}>
                {result.cost !== null && result.cost !== undefined ? result.cost.toFixed(2) : '∞'}
              </span>
            </div>
            <div className="algo-stat">
              <span className="s-label">Hops</span>
              <span className="s-value">{result.hop_count}</span>
            </div>
            <div className="algo-stat">
              <span className="s-label">Runtime</span>
              <span className="s-value">{result.runtime_ms?.toFixed(2)}ms</span>
            </div>
          </div>

          <div className="algo-stat" style={{ marginBottom: 4 }}>
            <span className="s-label">Convergence</span>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <span className="s-value">{result.convergence_ms?.toFixed(2)}ms</span>
              {result.convergence_ms < 10 && (
                <span className="badge badge-success" style={{ fontSize: '0.5rem' }}>Fast</span>
              )}
            </div>
          </div>

          <div className="path-display">{pathStr}</div>

          {result.all_paths?.length > 1 && (
            <span className="badge badge-info" style={{ alignSelf: 'flex-start' }}>
              {result.all_paths.length} equal-cost paths
            </span>
          )}

          {/* Metadata accordion */}
          {result.metadata && Object.keys(result.metadata).length > 0 && (
            <button
              style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4, color: 'var(--text-muted)', fontSize: '0.75rem', padding: 0 }}
              onClick={() => setExpanded((e) => !e)}
            >
              {expanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
              Details
            </button>
          )}
          {expanded && result.metadata && (
            <div style={{ background: 'var(--bg-elevated)', borderRadius: 'var(--radius-sm)', padding: 8, fontSize: '0.6875rem', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)', overflowX: 'auto' }}>
              <pre style={{ margin: 0, whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                {JSON.stringify(result.metadata, null, 2)}
              </pre>
            </div>
          )}
        </>
      )}
    </div>
  )
}

export default function AlgorithmPanel() {
  const { algoResults, isComputing, survivabilityScore, source, destination } = useStore()

  if (isComputing) {
    return (
      <div className="panel-body" style={{ alignItems: 'center', justifyContent: 'center', gap: 16, padding: 24 }}>
        <div style={{ animation: 'pulse-dot 1s ease infinite', fontSize: '2rem' }}>⚡</div>
        <span style={{ color: 'var(--text-secondary)', fontSize: '0.875rem' }}>
          Running 7 algorithms in parallel…
        </span>
      </div>
    )
  }

  if (!algoResults) {
    return (
      <div className="panel-body" style={{ alignItems: 'center', justifyContent: 'center', padding: 32, gap: 10 }}>
        <Route size={32} style={{ color: 'var(--text-muted)' }} />
        <span style={{ color: 'var(--text-muted)', fontSize: '0.875rem', textAlign: 'center' }}>
          Select source & destination,<br />then click Compute
        </span>
      </div>
    )
  }

  const allCosts = algoResults.results.map((r) => r.cost).filter((c) => c !== null && c !== undefined)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
      {/* Summary header */}
      <div style={{
        padding: '10px 12px',
        background: 'rgba(124,109,250,0.08)',
        borderBottom: '1px solid var(--border)',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {source} → {destination}
          </div>
          <div style={{ fontSize: '0.8125rem', fontWeight: 600 }}>
            {algoResults.algorithm_count} algorithms · {algoResults.total_runtime_ms?.toFixed(1)}ms
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Survivability</div>
          <div style={{
            fontSize: '1.25rem', fontWeight: 800, fontFamily: 'var(--font-mono)',
            color: survivabilityScore > 0.7 ? 'var(--accent-green)' : survivabilityScore > 0.4 ? 'var(--accent-orange)' : 'var(--accent-red)',
          }}>
            {(survivabilityScore * 100).toFixed(0)}%
          </div>
        </div>
      </div>

      <div className="panel-body scrollable" style={{ maxHeight: 'calc(100vh - 280px)' }}>
        {algoResults.results.map((r, i) => (
          <AlgoCard key={r.algorithm} result={r} allCosts={allCosts} rank={i} />
        ))}
      </div>
    </div>
  )
}
