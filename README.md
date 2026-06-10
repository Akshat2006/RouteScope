# RouteScope

A real-time network routing algorithm comparison platform. Draw a topology in GNS3, run six routing algorithms simultaneously, inject failures, and watch metrics update live — all from a browser.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Data Ingestion                                   │
│  GNS3 REST API · Netmiko/Telnet · iperf3 · Scapy · pyshark │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 2 — Graph Storage (auto-tiered)                      │
│  Tier 1 ≤ 50k nodes  → NetworkX in-memory (ThreadPool)     │
│  Tier 2 ≤ 500k nodes → Neo4j Community   (ProcessPool)     │
│  Tier 3 > 500k nodes → Neo4j cluster + Kafka  [future]     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 3 — Algorithm Engine                                  │
│  Dijkstra · Bellman-Ford · OSPF/iSPF · CSPF · LFA · ECMP  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Frontend — React + Cytoscape.js                            │
│  Live graph · Algorithm results · Failure injection         │
└─────────────────────────────────────────────────────────────┘
```

---

## Features

- **Live GNS3 integration** — topology auto-discovered from whatever project is open; click Sync GNS3 to pull updates instantly
- **Six routing algorithms** run in parallel with per-algorithm path overlay on the graph
- **Real-time metrics** — link utilization, latency, jitter, packet loss updated every 2 seconds via WebSocket
- **Real data collectors** — Netmiko reads actual interface counters from routers via GNS3 telnet console; iperf3, Scapy, and pyshark blend in when available
- **Auto-tiered graph storage** — NetworkX for small topologies, Neo4j for large ones; zero algorithm code changes between tiers
- **Edge weight formula** — `weight = latency / (1 − utilisation + 0.001)` means congested links cost exponentially more, so algorithms route around them automatically
- **Failure injection** — link fail, node fail, multi-link, cascading, maintenance drain, congestion boost
- **Simulation fallback** — if GNS3 is unreachable the system falls back to a 10-node synthetic topology automatically; nothing crashes

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.13, FastAPI, uvicorn |
| Graph algorithms | NetworkX, SciPy |
| Graph storage Tier 2 | Neo4j Community 5.x |
| Real data collection | Netmiko, Scapy, pyshark, iperf3 |
| Database | SQLite (aiosqlite) |
| Frontend | React 18, Vite, Cytoscape.js, Zustand |
| Network emulator | GNS3 2.2 + GNS3 VM (VirtualBox) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+
- GNS3 2.2 with GNS3 VM (VirtualBox)
- *(Optional)* Neo4j Desktop for Tier 2 storage demo
- *(Optional)* Wireshark/tshark for pyshark packet capture
- *(Optional)* Npcap for Scapy traceroute on Windows

---

## Quick Start

### 1. Clone and install

```bash
git clone <repo-url>
cd routescope

# Backend
python -m venv backend\.venv
backend\.venv\Scripts\pip install -r backend\requirements.txt

# Frontend
cd frontend && npm install && cd ..
```

### 2. Configure

```bash
copy backend\.env.example backend\.env
```

Edit `backend\.env` — the only required change is the GNS3 password:

```env
GNS3_PASS=<your GNS3 password>
SIMULATION_MODE=false
```

> **Finding your GNS3 password:** Open `%APPDATA%\GNS3\2.2\gns3_server.ini` and read the `password =` line under `[Server]`.

### 3. Start

```bash
# Terminal 1 — backend
start_backend.bat
# or: backend\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — frontend
start_frontend.bat
# or: cd frontend && npm run dev
```

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

### 4. Draw a topology in GNS3 and click **Sync GNS3** on the website

---

## Project Structure

```
routescope/
├── backend/
│   ├── algorithms/           # Six routing algorithm implementations
│   │   ├── dijkstra.py
│   │   ├── bellman_ford.py
│   │   ├── ospf_ispf.py
│   │   ├── cspf.py
│   │   ├── lfa.py
│   │   └── ecmp.py
│   ├── api/                  # FastAPI routers + WebSocket manager
│   │   ├── routes_graph.py
│   │   ├── routes_algo.py
│   │   ├── routes_failure.py
│   │   ├── routes_experiment.py
│   │   └── websocket.py
│   ├── engine/               # Algorithm runner, metrics engine, failure injector
│   ├── graph_storage/        # Layer 2: auto-tiered backends
│   │   ├── base.py           # AbstractGraphBackend + weight formula
│   │   ├── networkx_backend.py   # Tier 1
│   │   ├── neo4j_backend.py      # Tier 2
│   │   └── tier_selector.py      # Auto-selection singleton
│   ├── ingestion/            # Layer 1: data collectors
│   │   ├── gns3_client.py        # GNS3 REST API
│   │   ├── graph_builder.py      # NetworkX graph construction
│   │   ├── metric_simulator.py   # Simulation + real-data blend
│   │   ├── netmiko_collector.py  # Telnet → router interface stats
│   │   ├── iperf3_collector.py   # TCP throughput + UDP jitter
│   │   ├── scapy_collector.py    # ICMP traceroute latency
│   │   └── pyshark_collector.py  # Packet capture throughput
│   ├── config.py
│   ├── main.py
│   ├── requirements.txt
│   └── .env.example          # Template — copy to .env
├── frontend/
│   └── src/
│       ├── components/
│       │   ├── NetworkGraph/     # Cytoscape.js canvas with utilization heatmap
│       │   ├── ControlPanel/     # Failure injection + route compute
│       │   ├── AlgorithmPanel/   # Algorithm results + path overlays
│       │   ├── Sidebar/          # Live metrics, collector status, tier badge
│       │   ├── SurvivabilityDash/
│       │   └── HistoryPanel/
│       ├── hooks/useWebSocket.js
│       ├── store/useStore.js     # Zustand global state
│       └── pages/Dashboard.jsx
├── start_backend.bat
├── start_frontend.bat
├── test_api.py               # Smoke test script
└── README.md
```

---

## Configuration Reference

All settings in `backend/.env`:

| Variable | Default | Description |
|---|---|---|
| `GNS3_URL` | `http://localhost:3080` | GNS3 server address |
| `GNS3_USER` | `admin` | GNS3 username |
| `GNS3_PASS` | `admin` | GNS3 password (check gns3_server.ini after reinstall) |
| `GNS3_PROJECT_ID` | *(empty)* | Leave blank — auto-discovers the open project |
| `SIMULATION_MODE` | `false` | `true` = synthetic data only, no GNS3 needed |
| `METRIC_UPDATE_INTERVAL` | `2.0` | Seconds between metric ticks |
| `ALGORITHM_TIMEOUT` | `30.0` | Per-algorithm timeout in seconds |
| `IPERF3_SERVER` | *(empty)* | IP of a host running `iperf3 -s` |
| `NETMIKO_DEVICE_TYPE` | `cisco_ios` | Netmiko device type for SSH |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j bolt connection URI |
| `NEO4J_USER` | `neo4j` | Neo4j username |
| `NEO4J_PASS` | `routescope` | Neo4j password |
| `FORCE_STORAGE_TIER` | `0` | `0` = auto, `2` = force Neo4j for demos |

---

## Layer 1 — Data Collectors

Collectors run every 10 seconds and blend real measurements into the metric stream. Simulation fills gaps for any metric not covered — nothing breaks if a tool is missing.

| Collector | What it needs | What it measures |
|---|---|---|
| **GNS3 REST API** | GNS3 running | Topology (nodes + links) |
| **Netmiko/Telnet** | Router nodes started in GNS3 | Real TX/RX bytes → bandwidth utilization + packet loss per link |
| **iperf3** | `iperf3` binary + `IPERF3_SERVER` in `.env` | Real TCP throughput, UDP jitter |
| **Scapy** | Npcap installed (Windows) | ICMP traceroute → real per-hop latency |
| **pyshark** | Wireshark/tshark installed | Live packet capture → throughput |

Check live collector status: `GET /api/graph/collectors`

---

## Layer 2 — Graph Storage Tiers

Tier is selected automatically at startup from node count. Override with `FORCE_STORAGE_TIER=2` to demo Neo4j with any topology size.

| Tier | Node count | Backend | Concurrency model |
|---|---|---|---|
| 1 | ≤ 50,000 | NetworkX in-memory | ThreadPoolExecutor |
| 2 | ≤ 500,000 | Neo4j Community | ProcessPoolExecutor |
| 3 | > 500,000 | Neo4j cluster + Kafka | Celery *(planned)* |

The active tier is shown as a badge in the sidebar (**L2 · Tier 1** or **L2 · Tier 2**).

### Neo4j Setup (Tier 2 demo)

1. Download **Neo4j Desktop** — neo4j.com/download
2. Create a **Local DBMS**, set a password, click **Start**
3. Update `backend/.env`:
   ```env
   NEO4J_PASS=<your password>
   FORCE_STORAGE_TIER=2
   ```
4. Restart the backend — logs will show:
   ```
   [Layer 2] Active: Tier 2 — Neo4j Community (ProcessPoolExecutor, ego_graph radius=10)
   ```
5. Inspect the stored graph in Neo4j Browser (`http://localhost:7474`):
   ```cypher
   -- See all stored routers
   MATCH (n:Router) RETURN n

   -- See all links
   MATCH (a:Router)-[r:LINK]->(b:Router) RETURN a, r, b

   -- Ego subgraph used by algorithms (radius 10 from a node)
   MATCH path = (s:Router {node_id: 'R1'})-[*..10]-(n:Router)
   RETURN path LIMIT 50
   ```

---

## API Reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | System status, GNS3 live flag, node count, storage tier |
| GET | `/api/graph` | Current graph with nodes, edges, and live metrics |
| POST | `/api/graph/refresh` | Re-fetch topology from GNS3 and broadcast update |
| GET | `/api/graph/metrics` | Per-link metrics snapshot |
| GET | `/api/graph/collectors` | Collector availability and real-data cache status |
| GET | `/api/algorithms` | List all registered algorithms |
| POST | `/api/compute` | Run all algorithms (REST, for scripting) |
| POST | `/api/failure/inject` | Inject failure event or congestion |
| DELETE | `/api/failure/clear` | Restore full topology |
| WS | `/ws` | Bidirectional live stream |
| GET | `/docs` | Swagger UI |

---

## WebSocket Protocol

**Server → Client messages:**

```jsonc
// Full graph state (on connect, refresh, or failure event)
{ "type": "graph_update", "data": { "nodes": [...], "edges": [...] }, "storage_tier": 1, "storage_backend": "NetworkX" }

// Per-link metric tick (every 2s)
{ "type": "metric_update", "data": [{ "link_id": "...", "latency": 4.2, "utilization": 38.1, "packet_loss": 0.02, "jitter": 0.5, "cost": 6.8 }] }

// Algorithm results (after compute request)
{ "type": "algo_results", "data": { "results": [...], "survivability_score": 0.87, "tier": 1 } }

// Failure or congestion event
{ "type": "failure_event", "data": { "event_type": "link_failure", "affected": ["R1↔R2"], "graph": {...} } }
```

**Client → Server messages:**

```jsonc
{ "type": "compute", "source": "R1", "destination": "R5" }
{ "type": "ping" }
```

---

## GNS3 Tips

- **Multiple router ports:** Go to *Edit → Preferences → Dynamips → IOS Routers → Edit → Slots* and add `PA-FE-TX` to slots 1–4 (gives FastEthernet on each slot)
- **FRR containers:** Use `frrouting/frr:latest` Docker image — supports OSPF, BGP, ISIS
- **Netmiko real data:** Router nodes must be **started** (green play button in GNS3) for telnet console access
- **Password after reinstall:** GNS3 generates a new random password — find it in `%APPDATA%\GNS3\2.2\gns3_server.ini` under `[Server] → password =`

---

## License

MIT
