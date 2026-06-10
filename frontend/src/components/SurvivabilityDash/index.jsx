/**
 * RouteScope — Survivability Dashboard
 *
 * Radar chart comparing all algorithms across:
 *   Speed, Path Quality, Reachability, Convergence, Efficiency
 * + Individual algorithm score cards
 */
import {
  RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ResponsiveContainer, Tooltip, BarChart, Bar, XAxis, YAxis, CartesianGrid, Cell
} from 'recharts'
import useStore from '../../store/useStore'

const DIMENSIONS = ['Speed', 'Path Quality', 'Reachability', 'Convergence', 'Efficiency']

function normalize(value, min, max) {
  if (max === min) return 0.5
  return (value - min) / (max - min)
}

function buildRadarData(results) {
  if (!results?.length) return []

  const costs     = results.map((r) => r.cost).filter((c) => c !== null && c !== undefined)
  const runtimes  = results.map((r) => r.runtime_ms)
  const convTimes = results.map((r) => r.convergence_ms)

  const minCost = Math.min(...costs), maxCost = Math.max(...costs)
  const minRT   = Math.min(...runtimes), maxRT = Math.max(...runtimes)
  const minConv = Math.min(...convTimes), maxConv = Math.max(...convTimes)

  return results.map((r) => {
    const speed       = r.reachable ? 1 - normalize(r.runtime_ms, minRT, maxRT) : 0
    const pathQuality = r.reachable ? 1 - normalize(r.cost, minCost, maxCost) : 0
    const reachability = r.reachable ? 1 : 0
    const convergence = r.reachable ? 1 - normalize(r.convergence_ms, minConv, maxConv) : 0
    const efficiency  = r.reachable ? (r.hop_count > 0 ? 1 / r.hop_count : 0) : 0

    return {
      algorithm: r.algorithm,
      color: r.color,
      Speed:        Math.round(speed * 100),
      'Path Quality': Math.round(pathQuality * 100),
      Reachability: Math.round(reachability * 100),
      Convergence:  Math.round(convergence * 100),
      Efficiency:   Math.round(Math.min(efficiency * 100 * 3, 100)),
    }
  })
}

function ScorecardRow({ result, rank }) {
  const scoreColor = result.reachable
    ? result.cost < 20 ? 'var(--accent-green)' : 'var(--accent-orange)'
    : 'var(--accent-red)'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8, padding: '7px 0',
      borderBottom: '1px solid var(--border)',
    }}>
      <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', width: 16 }}>#{rank + 1}</span>
      <div style={{ width: 8, height: 8, borderRadius: '50%', background: result.color, boxShadow: `0 0 6px ${result.color}`, flexShrink: 0 }} />
      <span style={{ flex: 1, fontSize: '0.8125rem', fontWeight: 600 }}>{result.algorithm}</span>
      <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
        {result.reachable ? `${result.hop_count}h · ${result.convergence_ms?.toFixed(1)}ms` : '—'}
      </span>
      <span className={`badge ${result.reachable ? 'badge-success' : 'badge-danger'}`}>
        {result.reachable ? '✓' : '✗'}
      </span>
    </div>
  )
}

export default function SurvivabilityDash() {
  const { algoResults, survivabilityScore } = useStore()

  if (!algoResults) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
        Run algorithms to see survivability
      </div>
    )
  }

  const radarData = buildRadarData(algoResults.results)
  const reachableCount = algoResults.results.filter((r) => r.reachable).length
  const scoreColor = survivabilityScore > 0.7 ? 'var(--accent-green)'
                   : survivabilityScore > 0.4 ? 'var(--accent-orange)'
                   : 'var(--accent-red)'

  // Build bar chart: convergence time per algo
  const barData = algoResults.results.map((r) => ({
    name: r.algorithm.replace('/', '/\n'),
    convergence: r.reachable ? r.convergence_ms : 0,
    fill: r.color,
  }))

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 0, height: '100%', overflow: 'auto' }}>
      {/* Score header */}
      <div className="surv-ring-container" style={{ padding: 16, borderBottom: '1px solid var(--border)' }}>
        <div className="surv-score-label">Survivability Score</div>
        <div className="surv-score-value" style={{ color: scoreColor }}>
          {(survivabilityScore * 100).toFixed(1)}%
        </div>
        <div style={{ display: 'flex', gap: 12 }}>
          <span className="badge badge-info">{reachableCount}/{algoResults.results.length} reachable</span>
          <span className="badge badge-purple">{algoResults.total_runtime_ms?.toFixed(1)}ms total</span>
        </div>
      </div>

      {/* Radar chart */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
          Algorithm Comparison
        </div>
        <ResponsiveContainer width="100%" height={200}>
          <RadarChart data={DIMENSIONS.map((d) => {
            const point = { dimension: d }
            radarData.forEach((r) => { point[r.algorithm] = r[d] || 0 })
            return point
          })}>
            <PolarGrid stroke="rgba(255,255,255,0.06)" />
            <PolarAngleAxis dataKey="dimension" tick={{ fill: 'var(--text-muted)', fontSize: 10 }} />
            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
            {radarData.map((r) => (
              <Radar
                key={r.algorithm}
                name={r.algorithm}
                dataKey={r.algorithm}
                stroke={r.color}
                fill={r.color}
                fillOpacity={0.12}
                strokeWidth={1.5}
              />
            ))}
            <Tooltip
              contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 12 }}
            />
          </RadarChart>
        </ResponsiveContainer>
      </div>

      {/* Convergence bar chart */}
      <div style={{ padding: 12, borderBottom: '1px solid var(--border)' }}>
        <div style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
          Convergence Time (ms)
        </div>
        <ResponsiveContainer width="100%" height={100}>
          <BarChart data={barData} margin={{ top: 0, right: 0, bottom: 0, left: -20 }}>
            <CartesianGrid strokeDasharray="2 4" stroke="rgba(255,255,255,0.04)" />
            <XAxis dataKey="name" tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
            <YAxis tick={{ fontSize: 9, fill: 'var(--text-muted)' }} />
            <Bar dataKey="convergence" radius={[3, 3, 0, 0]}>
              {barData.map((entry, i) => (
                <Cell key={i} fill={entry.fill} />
              ))}
            </Bar>
            <Tooltip
              contentStyle={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)', borderRadius: 6, fontSize: 11 }}
              formatter={(v) => [`${v.toFixed(2)}ms`, 'Convergence']}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Per-algorithm scorecards */}
      <div style={{ padding: '8px 12px' }}>
        <div style={{ fontWeight: 700, fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em', marginBottom: 8 }}>
          Algorithm Ranking
        </div>
        {[...algoResults.results]
          .sort((a, b) => {
            if (a.reachable !== b.reachable) return a.reachable ? -1 : 1
            return a.cost - b.cost
          })
          .map((r, i) => <ScorecardRow key={r.algorithm} result={r} rank={i} />)
        }
      </div>
    </div>
  )
}
