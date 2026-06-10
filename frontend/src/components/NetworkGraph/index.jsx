/**
 * RouteScope — NetworkGraph Component (Cytoscape.js)
 *
 * Features:
 *   - Renders nodes as labelled router circles
 *   - Edge width ∝ bandwidth
 *   - Edge color = utilization heatmap (green→yellow→red)
 *   - Multi-path overlays: colored ghost-edges per algorithm
 *   - Click node/edge → Zustand selectedElement
 *   - Failed elements rendered with dashed/dimmed style
 *   - Minimap overlay (bottom-right)
 */
import { useEffect, useRef, useCallback, useState } from 'react'
import React from 'react'
import cytoscape from 'cytoscape'
import useStore from '../../store/useStore'

// ---- Util: utilization → hsl color ----
function utilColor(util) {
  // 0% → green(140°), 50% → yellow(60°), 100% → red(0°)
  const hue = Math.max(0, 140 - util * 1.4)
  const sat = 80
  const lit = 50 + (1 - util / 100) * 10
  return `hsl(${hue}, ${sat}%, ${lit}%)`
}

// ---- Util: edge width from bandwidth ----
function edgeWidth(bw) {
  if (bw >= 1000) return 4
  if (bw >= 500)  return 3.5
  if (bw >= 100)  return 3
  if (bw >= 50)   return 2.5
  return 2
}

// ---- Build Cytoscape elements from graph state ----
function buildElements(graph) {
  const nodeLabel = Object.fromEntries(graph.nodes.map((n) => [n.id, n.label || n.id]))

  const nodes = graph.nodes.map((n) => ({
    data: {
      id: n.id,
      label: n.label || n.id,
      failed: n.failed,
      node_type: n.node_type,
    },
    position: { x: n.x || 0, y: n.y || 0 },
    classes: n.failed ? 'failed' : '',
  }))

  const edges = graph.edges.map((e) => ({
    data: {
      id: e.id,
      source: e.source,
      target: e.target,
      sourceLabel: nodeLabel[e.source] || e.source,
      targetLabel: nodeLabel[e.target] || e.target,
      latency:     e.latency,
      bandwidth:   e.bandwidth,
      utilization: e.utilization,
      packet_loss: e.packet_loss,
      cost:        e.cost,
      failed:      e.failed,
      color:       e.failed ? '#333' : utilColor(e.utilization ?? 0),
      width:       e.failed ? 1 : edgeWidth(e.bandwidth ?? 100),
    },
    classes: e.failed ? 'failed-edge' : '',
  }))

  return [...nodes, ...edges]
}

// ---- Build overlay path edges ----
function buildPathOverlay(results, visibleAlgos) {
  const overlayEdges = []
  if (!results?.results) return overlayEdges

  results.results.forEach((r) => {
    if (!visibleAlgos[r.algorithm]) return
    const paths = r.all_paths?.length ? r.all_paths : (r.path?.length ? [r.path] : [])

    paths.forEach((path, pi) => {
      for (let i = 0; i < path.length - 1; i++) {
        overlayEdges.push({
          data: {
            id: `ov-${r.algorithm}-${pi}-${i}`,
            source: path[i],
            target: path[i + 1],
            color: r.color,
            algorithm: r.algorithm,
          },
          classes: 'path-overlay',
        })
      }
    })
  })
  return overlayEdges
}

const BASE_STYLE = [
  {
    selector: 'node',
    style: {
      'background-color': '#1a2540',
      'border-color': '#3a4a6a',
      'border-width': 2,
      'width': 42,
      'height': 42,
      'label': 'data(label)',
      'color': '#e8edf5',
      'font-size': 11,
      'font-family': 'Inter, sans-serif',
      'font-weight': 600,
      'text-valign': 'bottom',
      'text-margin-y': 4,
      'text-outline-width': 2,
      'text-outline-color': '#080c18',
      'background-image': 'none',
      'transition-property': 'background-color, border-color, width, height',
      'transition-duration': '0.2s',
    },
  },
  {
    selector: 'node:selected',
    style: {
      'border-color': '#7c6dfa',
      'border-width': 3,
      'background-color': '#1f2e55',
      'box-shadow': '0 0 12px #7c6dfa',
    },
  },
  {
    selector: 'node.failed',
    style: {
      'background-color': '#2a1520',
      'border-color': '#ff4d6d',
      'border-style': 'dashed',
      'opacity': 0.5,
    },
  },
  {
    selector: 'edge',
    style: {
      'line-color': 'data(color)',
      'width': 'data(width)',
      'opacity': 0.85,
      'curve-style': 'bezier',
      'target-arrow-shape': 'none',
      'transition-property': 'line-color, width, opacity',
      'transition-duration': '0.3s',
    },
  },
  {
    selector: 'edge.failed-edge',
    style: {
      'line-color': '#2a2a3a',
      'line-style': 'dashed',
      'opacity': 0.3,
      'width': 1,
    },
  },
  {
    selector: 'edge:selected',
    style: {
      'line-color': '#7c6dfa',
      'width': 4,
      'opacity': 1,
    },
  },
  {
    selector: 'edge.path-overlay',
    style: {
      'line-color': 'data(color)',
      'width': 5,
      'opacity': 0.7,
      'curve-style': 'unbundled-bezier',
      'control-point-step-size': 20,
      'z-index': 10,
      'line-style': 'solid',
      'target-arrow-shape': 'triangle',
      'target-arrow-color': 'data(color)',
      'arrow-scale': 0.8,
    },
  },
]

export default function NetworkGraph() {
  const cyRef = useRef(null)
  const containerRef = useRef(null)
  const { graph, algoResults, visibleAlgos, setSelectedElement } = useStore()

  // ---- Init Cytoscape ----
  useEffect(() => {
    if (!containerRef.current) return

    const cy = cytoscape({
      container: containerRef.current,
      elements: buildElements(graph),
      style: BASE_STYLE,
      layout: { name: 'preset' },
      minZoom: 0.3,
      maxZoom: 3,
      wheelSensitivity: 0.3,
    })
    cyRef.current = cy

    // Fit on load
    setTimeout(() => cy.fit(undefined, 40), 100)

    // Click handlers
    cy.on('tap', 'node', (e) => {
      const d = e.target.data()
      setSelectedElement({ type: 'node', ...d })
    })
    cy.on('tap', 'edge', (e) => {
      const d = e.target.data()
      setSelectedElement({ type: 'edge', ...d })
    })
    cy.on('tap', (e) => {
      if (e.target === cy) setSelectedElement(null)
    })

    return () => { cy.destroy(); cyRef.current = null }
  }, []) // only on mount

  // ---- Update graph data without re-init ----
  useEffect(() => {
    const cy = cyRef.current
    if (!cy) return

    const elements = buildElements(graph)
    const overlays = buildPathOverlay(algoResults, visibleAlgos)
    const all = [...elements, ...overlays]

    cy.batch(() => {
      // Remove stale overlay edges
      cy.elements('.path-overlay').remove()

      // Update / add nodes & edges
      all.forEach((el) => {
        const existing = cy.getElementById(el.data.id)
        if (existing.length > 0) {
          existing.data(el.data)
          if (el.classes !== undefined) {
            existing.removeClass('failed failed-edge path-overlay')
            if (el.classes) existing.addClass(el.classes)
          }
          if (el.position) existing.position(el.position)
        } else {
          cy.add(el)
        }
      })

      // Remove elements no longer in graph
      const currentIds = new Set(all.map((el) => el.data.id))
      cy.elements().not('.path-overlay').forEach((el) => {
        if (!currentIds.has(el.id()) && !el.hasClass('path-overlay')) {
          el.remove()
        }
      })
    })
  }, [graph, algoResults, visibleAlgos])

  return (
    <div style={{ width: '100%', height: '100%', position: 'relative' }}>
      <div
        ref={containerRef}
        id="cy-container"
        style={{ width: '100%', height: '100%' }}
      />
      <GraphLegend />
      <GraphControls cyRef={cyRef} />
    </div>
  )
}

function GraphLegend() {
  return (
    <div className="overlay-panel" style={{ bottom: 16, left: 16, right: 'auto', top: 'auto' }}>
      <div style={{ fontSize: '0.6875rem', fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.08em', color: 'var(--text-muted)', marginBottom: 8 }}>
        Link Utilization
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ width: 80, height: 6, borderRadius: 99, background: 'linear-gradient(90deg, hsl(140,80%,55%), hsl(60,80%,55%), hsl(0,80%,50%))' }} />
        <span style={{ fontSize: '0.6875rem', color: 'var(--text-muted)' }}>0% → 100%</span>
      </div>
    </div>
  )
}

function GraphControls({ cyRef }) {
  const [syncing, setSyncing] = useState(false)

  async function syncFromGns3() {
    setSyncing(true)
    try {
      await fetch('/api/graph/refresh', { method: 'POST' })
    } catch (e) {
      console.error('GNS3 sync failed:', e)
    } finally {
      setSyncing(false)
    }
  }

  return (
    <div className="overlay-panel" style={{ bottom: 16, right: 16, top: 'auto', left: 'auto', display: 'flex', flexDirection: 'column', gap: 6 }}>
      <button className="btn btn-secondary btn-sm" onClick={syncFromGns3} disabled={syncing} title="Re-fetch topology from GNS3">
        {syncing ? '...' : 'Sync GNS3'}
      </button>
      <button className="btn btn-secondary btn-sm" onClick={() => cyRef.current?.fit(undefined, 40)}>
        Fit
      </button>
      <button className="btn btn-secondary btn-sm" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 1.2)}>
        +
      </button>
      <button className="btn btn-secondary btn-sm" onClick={() => cyRef.current?.zoom(cyRef.current.zoom() * 0.8)}>
        −
      </button>
    </div>
  )
}
