/**
 * RouteScope — Zustand Global State
 *
 * Single source of truth for:
 *   - graph (nodes + edges)
 *   - algorithm results
 *   - UI state (selected src/dst, active panel, etc.)
 *   - failure events
 *   - WebSocket connection status
 */
import { create } from 'zustand'

const ALGO_COLORS = {
  'Dijkstra':     '#00d4ff',
  'Bellman-Ford': '#ff6b6b',
  'OSPF/iSPF':   '#ffd700',
  'CSPF':        '#a29bfe',
  'LFA/rLFA':    '#55efc4',
  'ECMP':        '#fd79a8',
}

const useStore = create((set, get) => ({
  // ---- WebSocket state ----
  wsStatus: 'disconnected', // 'connecting' | 'connected' | 'disconnected'
  setWsStatus: (s) => set({ wsStatus: s }),

  // ---- Graph ----
  graph: { nodes: [], edges: [] },
  graphHealth: {},
  isLive: false,
  storageTier: 1,
  storageBackend: 'NetworkX',
  setGraph: (graph, health, isLive, storageTier, storageBackend) => set({
    graph,
    graphHealth: health ?? {},
    isLive: isLive ?? false,
    storageTier: storageTier ?? 1,
    storageBackend: storageBackend ?? 'NetworkX',
  }),
  updateMetrics: (updates) => set((state) => {
    const edgeMap = {}
    state.graph.edges.forEach((e) => { edgeMap[e.id] = e })
    updates.forEach((u) => {
      if (edgeMap[u.link_id]) {
        Object.assign(edgeMap[u.link_id], {
          latency:      u.latency,
          bandwidth:    u.bandwidth,
          utilization:  u.utilization,
          packet_loss:  u.packet_loss,
          jitter:       u.jitter,
          cost:         u.cost,
        })
      }
    })
    return { graph: { ...state.graph, edges: Object.values(edgeMap) } }
  }),

  // ---- Algorithm results ----
  algoResults: null,       // last compute results
  survivabilityScore: 0,
  isComputing: false,
  setAlgoResults: (data) => set({
    algoResults: data,
    survivabilityScore: data?.survivability_score ?? 0,
    isComputing: false,
  }),
  setComputing: (v) => set({ isComputing: v }),

  // ---- Source / Destination ----
  source: '',
  destination: '',
  setSource: (s) => set({ source: s }),
  setDestination: (d) => set({ destination: d }),

  // ---- Active panel ----
  activePanel: 'algorithms', // 'algorithms' | 'control' | 'survivability' | 'history'
  setActivePanel: (p) => set({ activePanel: p }),

  // ---- Algorithm visibility (toggle per algo) ----
  visibleAlgos: Object.keys(ALGO_COLORS).reduce((acc, k) => ({ ...acc, [k]: true }), {}),
  toggleAlgo: (name) => set((state) => ({
    visibleAlgos: { ...state.visibleAlgos, [name]: !state.visibleAlgos[name] }
  })),

  // ---- Failures ----
  activeFailures: [],
  addFailure: (f) => set((state) => ({ activeFailures: [...state.activeFailures, f] })),
  clearFailures: () => set({ activeFailures: [] }),

  // ---- Selected node / edge for detail panel ----
  selectedElement: null,
  setSelectedElement: (el) => set({ selectedElement: el }),

  // ---- Experiments (history) ----
  experiments: [],
  setExperiments: (exps) => set({ experiments: exps }),
  addExperiment: (exp) => set((state) => ({ experiments: [exp, ...state.experiments] })),

  // ---- Congestion slider state ----
  congestionTarget: null,   // link_id being congested
  congestionLevel: 80,
  setCongestionTarget: (id) => set({ congestionTarget: id }),
  setCongestionLevel: (v) => set({ congestionLevel: v }),

  // ---- Helpers ----
  algoColors: ALGO_COLORS,
  getColor: (name) => ALGO_COLORS[name] ?? '#888',
}))

export default useStore
