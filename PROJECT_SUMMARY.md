# RouteScope — Project Summary

## What It Is

RouteScope is a real-time network routing intelligence platform built as a final-year engineering project. It connects to a live GNS3 network emulator, reads the topology and real interface metrics from the routers, stores the graph in a tiered backend, runs six industry-standard routing algorithms in parallel, and visualises everything in a browser — updating live every two seconds.

The core academic contribution is the three-layer architecture: a multi-source data ingestion layer feeds an auto-tiered graph storage layer, which serves a parallel algorithm execution engine. Every layer is independently testable and falls back gracefully when dependencies are unavailable.

---

## Problem Statement

Network engineers cannot easily compare how different routing algorithms would respond to the same topology under real traffic conditions. Simulators exist but they are static — you run one algorithm at a time, against synthetic data, with no live feedback. RouteScope solves this by:

1. Pulling a live topology from GNS3 (the industry-standard network emulator)
2. Collecting real metrics from the routers (interface counters, packet loss, jitter)
3. Running all six algorithms simultaneously against the same live graph
4. Showing results, path overlays, and metric changes in real time
5. Letting you break things — inject link failures, node failures, and congestion — and immediately see how each algorithm re-routes

---

## System Architecture

The system is divided into three layers, each with a clear interface boundary to the next.

### Layer 1 — Data Ingestion

Responsible for building and maintaining the live representation of the network. Five data sources feed into this layer:

**GNS3 REST API** is the primary source. On startup the backend calls `/v2/projects` to discover the open project, then fetches `/v2/projects/{id}/nodes` and `/v2/projects/{id}/links` to build the initial topology. Any time the user clicks Sync GNS3 on the website, the backend re-fetches and broadcasts the updated topology over WebSocket.

**Netmiko/Telnet Collector** connects to each router's console port via raw asyncio telnet (GNS3 exposes console ports on the VM's IP). It runs `ip -s link show` on FRR/Linux routers, parses the TX/RX byte and error counters, and computes per-link bandwidth utilization and packet loss from the delta between successive samples. This runs every 10 seconds in a background task.

**iperf3 Collector** runs the `iperf3` binary as a subprocess against a configured server. It executes a 3-second TCP test for throughput and a UDP test for jitter and packet loss, returning the JSON results. Active when `IPERF3_SERVER` is set in the environment.

**Scapy Collector** sends ICMP echo requests and traceroute probes to node IP addresses using Scapy's raw socket interface, measuring real round-trip latency per hop. Requires Npcap on Windows.

**pyshark Collector** captures live packets on a network interface using pyshark (a tshark wrapper), derives bytes-per-second throughput, and feeds that back as bandwidth utilization. Requires Wireshark to be installed.

All five collectors write into a shared `RealMetricsCache`. The metric simulator reads from this cache every tick. If a real measurement is present and less than 30 seconds old it overrides the simulated value for that field. Otherwise simulation fills the gap. The system never fails because a collector is unavailable.

The metric simulator runs on a 2-second tick using statistical distributions: sinusoidal utilization cycles (period 60s), log-normal latency with queuing delay proportional to utilization, Pareto-distributed packet loss that spikes above 80% utilization, and random burst events lasting 2–8 seconds at 2% probability per tick.

### Layer 2 — Graph Storage

The graph storage layer receives a NetworkX graph from the ingestion layer and persists it in the appropriate backend based on node count. The abstraction point is the `get_graph(source, target)` method — algorithms call this and receive a NetworkX graph regardless of which backend is active.

**Tier 1 — NetworkX** (≤ 50,000 nodes): The graph lives in Python RAM. `get_graph()` returns a deep copy of the full graph. Algorithm execution uses a `ThreadPoolExecutor`. This is what runs for all realistic GNS3 topologies.

**Tier 2 — Neo4j Community** (50,001–500,000 nodes): The graph is persisted to Neo4j using native graph storage (pointer-based physical adjacency, not relational joins). `get_graph(source, target)` runs a Cypher ego-graph query extracting the radius-10 neighbourhood around both endpoints. This bounds algorithm computation to a fixed subgraph regardless of total topology size — Dijkstra on a 500,000-node graph never touches more than the local neighbourhood. Execution uses a `ProcessPoolExecutor` to bypass Python's GIL. Neo4j is optional; if unreachable the system falls back to Tier 1 with a log warning.

**Tier 3 — Neo4j Cluster + Kafka** (> 500,000 nodes): Architected in the specification (Neo4j cluster, Kafka event stream, Celery workers) but not yet implemented. The selector falls back to Tier 1 with a warning.

Tier selection is automatic at startup. `FORCE_STORAGE_TIER=2` in the environment overrides the threshold for demo purposes, allowing Tier 2 to be demonstrated with a small topology.

The edge weight formula used across all tiers is from the technical specification:

```
weight = latency_ms / (1 − utilisation + 0.001)
```

At 0% utilization a 5ms link has weight 5.005. At 90% utilization the same link has weight 45.5 — nine times heavier. Algorithms naturally route around congested links without any special congestion-aware code.

### Layer 3 — Algorithm Engine

Six algorithms are implemented, all sharing the same interface: they receive a NetworkX graph, source node, and destination node, and return a result dict with path, cost, hop count, and runtime.

| Algorithm | Type | Key property |
|---|---|---|
| **Dijkstra** | Greedy shortest path | Optimal under non-negative weights; O((V+E) log V) |
| **Bellman-Ford** | Dynamic programming | Handles negative weights; detects negative cycles |
| **OSPF/iSPF** | Incremental SPF | Reuses previous SPT; only recomputes affected subtree on topology change |
| **CSPF** | Constrained shortest path | Prunes links that do not meet bandwidth or latency constraints before running Dijkstra |
| **LFA/rLFA** | Loop-free alternates | Pre-computes backup next-hops for fast reroute without signalling |
| **ECMP** | Equal-cost multipath | Finds all shortest paths of equal cost; load-balances across them |

All six run concurrently using the executor from the active storage tier (Thread for Tier 1, Process for Tier 2). Results are collected with `asyncio.gather`, sorted by cost, and returned with a survivability score computed from path diversity and network health indicators.

---

## Frontend

The frontend is a single-page React application built with Vite. State is managed with Zustand. The network graph is rendered with Cytoscape.js.

**NetworkGraph** renders nodes and edges from the graph state. Edge color maps utilization to a green→yellow→red heatmap using HSL: `hue = 140 − utilisation × 1.4`. Edge width scales with bandwidth. When algorithms run, each algorithm gets a distinct colored overlay drawn as additional edges on the same canvas, making path differences visually obvious. Failed elements are dimmed and dashed.

**ControlPanel** handles route computation (source/destination dropdowns) and failure injection. Six failure types are supported: link fail, node fail, multi-link, cascading (removes overloaded links after primary failure), maintenance (drains cost to infinity then removes), and congestion (boosts utilization on selected links).

**Sidebar** shows a live metrics panel reading directly from the Zustand graph state — these numbers update every 2 seconds as metric_update WebSocket messages arrive. A collector status panel polls `/api/graph/collectors` every 15 seconds and shows which collectors are available and when they last fired. A Layer 2 storage tier badge shows **L2 · Tier 1 · NetworkX** or **L2 · Tier 2 · Neo4j**.

**WebSocket hook** maintains a persistent connection to `/ws`, reconnects automatically on disconnect, and dispatches incoming messages to the Zustand store. The four message types are `graph_update`, `metric_update`, `algo_results`, and `failure_event`.

---

## Data Flow

```
GNS3 topology change
        │
        ▼
gns3_client.fetch_topology()
        │
        ▼
graph_builder.initialize()   ←── metric_simulator.init_links()
        │                               │
        ▼                               ▼ (every 2s)
tier_selector.initialize()      metric_simulator.tick()
        │                               │
        ▼                     real collectors (every 10s)
  NetworkX / Neo4j                      │
        │                               ▼
        │                    graph_builder.apply_metric_updates()
        │                               │
        └───────────────────────────────▼
                              ws_manager.broadcast(metric_update)
                                        │
                                        ▼
                              browser ← WebSocket
                                        │
                              Cytoscape edge colors update
```

When a user requests path computation:

```
browser → WS: { type: "compute", source: "R1", destination: "R5" }
        │
        ▼
tier_selector.get_graph("R1", "R5")
        │  Tier 1: deep copy of full graph
        │  Tier 2: Cypher ego_graph from Neo4j
        ▼
run_all_algorithms(graph, "R1", "R5")
        │  6 algorithms, concurrent executor
        ▼
browser ← WS: { type: "algo_results", data: { results: [...] } }
        │
        ▼
Cytoscape path overlay drawn per algorithm
```

---

## Key Design Decisions

**Graceful degradation everywhere.** If GNS3 is down, simulation runs. If Neo4j is down, Tier 1 activates. If Netmiko cannot connect to a console, that link gets simulated values. If the WebSocket disconnects, it reconnects in 3 seconds. The system is never in an unrecoverable state.

**Single abstraction point between storage and algorithms.** `tier_selector.get_graph()` is the only interface the algorithm engine uses. Adding a new storage backend (e.g. Amazon Neptune for Tier 3) requires implementing one class — no algorithm code changes.

**Real data blended with simulation.** Rather than choosing between real or fake data, the system treats real measurements as overrides. This means partial deployments work: if only Netmiko is available, bandwidth and loss are real while latency and jitter are simulated. The collector status endpoint shows exactly which fields are real for each link.

**Project ID never cached.** The GNS3 client re-discovers the active project on every `fetch_topology()` call. Switching projects in GNS3 and clicking Sync GNS3 on the website immediately loads the new topology — no restart needed.

**Link names are always human-readable.** The frontend builds a `nodeId → label` map from the graph state and applies it to all dropdowns, the click-to-inspect overlay, and the active failures list. GNS3 UUIDs never appear in the UI.

---

## File Count and Scale

| Area | Files | Purpose |
|---|---|---|
| Backend algorithms | 6 | One file per routing algorithm |
| Backend API routes | 5 | Graph, algorithms, failures, experiments, WebSocket |
| Backend engine | 3 | Algorithm runner, metrics engine, failure injector |
| Backend graph storage | 4 | Base class, NetworkX backend, Neo4j backend, tier selector |
| Backend ingestion | 7 | GNS3 client, graph builder, metric simulator, 4 collectors |
| Backend config/db | 4 | Config, database, models, main |
| Frontend components | 6 | NetworkGraph, ControlPanel, AlgorithmPanel, Sidebar, SurvivabilityDash, HistoryPanel |
| Frontend state/hooks | 2 | Zustand store, WebSocket hook |

---

## What Can Be Demonstrated

| Feature | How to show it |
|---|---|
| Live GNS3 integration | Add a router in GNS3 → click Sync GNS3 → node appears on website |
| Real interface metrics | Start router nodes in GNS3 → watch sidebar numbers update every 2s |
| Algorithm comparison | Select two nodes → Run All 6 Algorithms → six colored path overlays |
| Congestion routing | Inject 100% congestion on a link → re-run algorithms → paths avoid the red link |
| Failure injection | Fail a link → link disappears → algorithms find alternate paths |
| Layer 2 Tier 2 | Set FORCE_STORAGE_TIER=2 → restart → sidebar shows "L2 · Tier 2 · Neo4j" → inspect in Neo4j Browser |
| Collector status | Open /api/graph/collectors → shows which collectors are live and last fire time |
| Simulation fallback | Stop GNS3 → backend continues serving 10-node simulated topology |
| WebSocket stream | Open browser DevTools Network tab → WS frame → metric_update every 2s |
