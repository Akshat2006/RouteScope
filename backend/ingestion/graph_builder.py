"""
RouteScope — NetworkX Graph Builder

Constructs and maintains the live network graph from topology + metrics.
Provides thread-safe snapshots for algorithm execution.

Layer 2 integration: after initialize(), the graph is handed to
tier_selector which persists it in the appropriate backend (NetworkX Tier 1
or Neo4j Tier 2). The in-memory graph here remains the authoritative
source for the UI/API; tier_selector.get_graph() is what algorithms use.
"""
import copy
import logging
import threading
from typing import Optional

import networkx as nx

from .gns3_client import gns3_client
from .metric_simulator import metric_simulator

logger = logging.getLogger(__name__)

# Spec §3.1 weight formula: effective_weight = latency_ms / (1 - utilisation + 0.001)
def _effective_weight(latency_ms: float, utilisation_pct: float) -> float:
    util_frac = max(0.0, min(utilisation_pct, 99.9)) / 100.0
    return round(latency_ms / (1.0 - util_frac + 0.001), 4)


class GraphBuilder:
    """
    Singleton that owns the live NetworkX graph.

    Thread-safety: all mutations are protected by _lock.
    Algorithms receive a graph via tier_selector.get_graph() (not snapshot()).
    snapshot() is kept for backwards compatibility and internal use.
    """

    def __init__(self):
        self._graph: nx.Graph = nx.Graph()
        self._raw_topology: dict = {"nodes": [], "links": []}
        self._failed_edges: set[tuple] = set()
        self._failed_nodes: set[str] = set()
        self._lock = threading.RLock()

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    async def initialize(self):
        """Fetch topology from GNS3 / simulator, build graph, initialise Layer 2."""
        topology = await gns3_client.fetch_topology()
        self._raw_topology = topology
        self._build_from_topology(topology)
        metric_simulator.init_links(topology["links"])
        logger.info(
            "GraphBuilder initialised: %d nodes, %d edges",
            self._graph.number_of_nodes(),
            self._graph.number_of_edges(),
        )

        # Hand the graph to Layer 2 — tier_selector picks the right backend
        from ..graph_storage import tier_selector
        await tier_selector.initialize(self.snapshot())

    def _build_from_topology(self, topology: dict):
        """Create a fresh graph from a topology dict."""
        with self._lock:
            g = nx.Graph()
            for node in topology["nodes"]:
                g.add_node(
                    node["id"],
                    label=node.get("label", node["id"]),
                    x=node.get("x", 0),
                    y=node.get("y", 0),
                    node_type=node.get("type", "router"),
                    failed=False,
                )

            for link in topology["links"]:
                src, tgt = link["source"], link["target"]
                if g.has_node(src) and g.has_node(tgt):
                    base_lat = link.get("base_latency", 5.0)
                    base_bw  = link.get("base_bandwidth", 100.0)
                    init_util = 20.0
                    g.add_edge(
                        src,
                        tgt,
                        link_id=link["id"],
                        base_latency=base_lat,
                        base_bandwidth=base_bw,
                        # Live metrics (updated by simulator)
                        latency=base_lat,
                        latency_ms=base_lat,           # spec canonical name
                        bandwidth=base_bw,
                        bandwidth_mbps=base_bw,        # spec canonical name
                        utilization=init_util,
                        utilisation=init_util,         # spec canonical name
                        packet_loss=0.1,
                        jitter=0.5,
                        cost=base_lat,
                        # Spec §3.1 weight: stamped here, kept current by apply_metric_updates
                        weight=_effective_weight(base_lat, init_util),
                        failed=False,
                    )
            self._graph = g

    # ------------------------------------------------------------------
    # Live metric updates
    # ------------------------------------------------------------------

    def apply_metric_updates(self, updates: list[dict]):
        """
        Called by MetricSimulator every tick.
        Updates edge attributes in-place and recomputes spec weight.
        """
        with self._lock:
            for upd in updates:
                lid = upd["link_id"]
                edge = self._link_id_to_edge(lid)
                if edge:
                    u, v = edge
                    if self._graph.has_edge(u, v):
                        attrs = self._graph[u][v]
                        lat  = upd["latency"]
                        util = upd["utilization"]
                        attrs["latency"]       = lat
                        attrs["latency_ms"]    = lat
                        attrs["bandwidth"]     = upd["bandwidth"]
                        attrs["bandwidth_mbps"]= upd["bandwidth"]
                        attrs["utilization"]   = util
                        attrs["utilisation"]   = util
                        attrs["packet_loss"]   = upd["packet_loss"]
                        attrs["jitter"]        = upd["jitter"]
                        attrs["cost"]          = upd["cost"]
                        # Recompute spec weight on every tick
                        attrs["weight"]        = _effective_weight(lat, util)

        # Keep Tier 1 backend weights in sync (no-op for Tier 2)
        from ..graph_storage import tier_selector
        tier_selector.update_tier1_weights(updates)

    def _link_id_to_edge(self, link_id: str) -> Optional[tuple]:
        """Return (u, v) for the edge with the given link_id."""
        for u, v, data in self._graph.edges(data=True):
            if data.get("link_id") == link_id:
                return (u, v)
        return None

    # ------------------------------------------------------------------
    # Failure injection / restoration
    # ------------------------------------------------------------------

    def fail_edge(self, u: str, v: str):
        with self._lock:
            self._failed_edges.add((min(u, v), max(u, v)))
            if self._graph.has_edge(u, v):
                self._graph[u][v]["failed"] = True
                self._graph.remove_edge(u, v)

    def restore_edge(self, u: str, v: str):
        with self._lock:
            key = (min(u, v), max(u, v))
            self._failed_edges.discard(key)
            for link in self._raw_topology["links"]:
                if {link["source"], link["target"]} == {u, v}:
                    base_lat = link.get("base_latency", 5.0)
                    base_bw  = link.get("base_bandwidth", 100.0)
                    self._graph.add_edge(
                        link["source"],
                        link["target"],
                        link_id=link["id"],
                        base_latency=base_lat,
                        base_bandwidth=base_bw,
                        latency=base_lat,
                        latency_ms=base_lat,
                        bandwidth=base_bw,
                        bandwidth_mbps=base_bw,
                        utilization=20.0,
                        utilisation=20.0,
                        packet_loss=0.1,
                        jitter=0.5,
                        cost=base_lat,
                        weight=_effective_weight(base_lat, 20.0),
                        failed=False,
                    )
                    break

    def fail_node(self, node_id: str):
        with self._lock:
            self._failed_nodes.add(node_id)
            if self._graph.has_node(node_id):
                self._graph.nodes[node_id]["failed"] = True
                neighbors = list(self._graph.neighbors(node_id))
                for nb in neighbors:
                    self._failed_edges.add((min(node_id, nb), max(node_id, nb)))
                    self._graph.remove_edge(node_id, nb)

    def restore_node(self, node_id: str):
        with self._lock:
            self._failed_nodes.discard(node_id)
            if self._graph.has_node(node_id):
                self._graph.nodes[node_id]["failed"] = False
            edges_to_restore = [
                key for key in list(self._failed_edges)
                if node_id in key
            ]
            for key in edges_to_restore:
                u, v = key
                self.restore_edge(u, v)

    def restore_all(self):
        """Clear all injected failures and rebuild graph from raw topology."""
        with self._lock:
            self._failed_edges.clear()
            self._failed_nodes.clear()
            self._build_from_topology(self._raw_topology)

    # ------------------------------------------------------------------
    # Snapshot (used internally and by routes_graph refresh)
    # ------------------------------------------------------------------

    def snapshot(self) -> nx.Graph:
        """Return a deep copy of the current graph (thread-safe)."""
        with self._lock:
            return copy.deepcopy(self._graph)

    # ------------------------------------------------------------------
    # Serialisation for API / WebSocket
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Serialise current graph state for JSON transport."""
        with self._lock:
            nodes = []
            for nid, data in self._graph.nodes(data=True):
                nodes.append({
                    "id": nid,
                    "label": data.get("label", nid),
                    "x": data.get("x", 0),
                    "y": data.get("y", 0),
                    "node_type": data.get("node_type", "router"),
                    "failed": data.get("failed", nid in self._failed_nodes),
                })

            edges = []
            for u, v, data in self._graph.edges(data=True):
                edges.append({
                    "id": data.get("link_id", f"{u}-{v}"),
                    "source": u,
                    "target": v,
                    "latency": data.get("latency", 0),
                    "bandwidth": data.get("bandwidth", 0),
                    "utilization": data.get("utilization", 0),
                    "packet_loss": data.get("packet_loss", 0),
                    "jitter": data.get("jitter", 0),
                    "cost": data.get("cost", 0),
                    "weight": data.get("weight", 0),
                    "failed": data.get("failed", False),
                })

            for nid in self._failed_nodes:
                if not any(n["id"] == nid for n in nodes):
                    nodes.append({
                        "id": nid,
                        "label": nid,
                        "x": 0, "y": 0,
                        "node_type": "router",
                        "failed": True,
                    })

            return {"nodes": nodes, "edges": edges}

    @property
    def node_ids(self) -> list[str]:
        with self._lock:
            return list(self._graph.nodes())


# Singleton
graph_builder = GraphBuilder()
