/**
 * RouteScope — Main Dashboard Page
 */
import NetworkGraph from '../components/NetworkGraph'
import AlgorithmPanel from '../components/AlgorithmPanel'
import ControlPanel from '../components/ControlPanel'
import SurvivabilityDash from '../components/SurvivabilityDash'
import HistoryPanel from '../components/HistoryPanel'
import useStore from '../store/useStore'

const PANEL_TITLES = {
  algorithms:    'Algorithm Results',
  control:       'Failure & Congestion',
  survivability: 'Survivability Analysis',
  history:       'Experiment History',
}

export default function Dashboard() {
  const { activePanel, selectedElement } = useStore()

  return (
    <>
      {/* Main graph canvas */}
      <div className="main-canvas">
        <NetworkGraph />

        {/* Selected element overlay */}
        {selectedElement && (
          <div className="overlay-panel" style={{ top: 12, left: '50%', transform: 'translateX(-50%)' }}>
            <ElementDetail element={selectedElement} />
          </div>
        )}
      </div>

      {/* Right panel */}
      <div className="sidebar-right">
        <div className="panel-header">
          <span className="icon">◈</span>
          {PANEL_TITLES[activePanel]}
        </div>
        <div style={{ flex: 1, overflow: 'auto' }}>
          {activePanel === 'algorithms'    && <AlgorithmPanel />}
          {activePanel === 'control'       && <ControlPanel />}
          {activePanel === 'survivability' && <SurvivabilityDash />}
          {activePanel === 'history'       && <HistoryPanel />}
        </div>
      </div>
    </>
  )
}

function ElementDetail({ element }) {
  const { setSelectedElement, graph } = useStore()
  const nodeLabel = Object.fromEntries(graph.nodes.map((n) => [n.id, n.label || n.id]))

  if (element.type === 'node') {
    return (
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <div>
          <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Node</div>
          <div style={{ fontWeight: 700 }}>{element.label || element.id}</div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
            {element.failed ? '⚡ FAILED' : '● Active'} · {element.node_type}
          </div>
        </div>
        <button className="btn btn-secondary btn-sm" onClick={() => setSelectedElement(null)}>×</button>
      </div>
    )
  }

  const srcLabel = element.sourceLabel || nodeLabel[element.source] || element.source
  const tgtLabel = element.targetLabel || nodeLabel[element.target] || element.target
  const util = element.utilization ?? 0
  const utilColor = util > 80 ? '#ff4d6d' : util > 50 ? '#ff9f43' : '#55efc4'

  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
      <div>
        <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Link</div>
        <div style={{ fontWeight: 700 }}>{srcLabel} ↔ {tgtLabel}</div>
        <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontFamily: 'var(--font-mono)' }}>
          {element.latency?.toFixed(1)}ms · {element.bandwidth}Mbps ·{' '}
          <span style={{ color: utilColor, fontWeight: 700 }}>{util.toFixed(0)}% util</span>
          {' '}· loss {element.packet_loss?.toFixed(3)}%
        </div>
      </div>
      <button className="btn btn-secondary btn-sm" onClick={() => setSelectedElement(null)}>×</button>
    </div>
  )
}
