"""
RouteScope — Layer 2: Tier 2 Neo4j Backend

Persists the graph in Neo4j Community using native graph storage
(edges as physical disk pointers between node records, not relational JOINs).

get_graph(source, target) extracts ego_graph(radius=10) around source and
target from Neo4j and returns a NetworkX subgraph. This bounds algorithm
computation to a fixed neighbourhood regardless of total topology size —
Dijkstra on a 500,000-node graph touches only the subgraph nodes.

Active when TIER1_MAX_NODES < node_count ≤ TIER2_MAX_NODES.
Uses ProcessPoolExecutor to bypass Python's GIL for true CPU parallelism.

Graceful fallback: if Neo4j is unreachable, store() logs a warning
and is_available() returns False so TierSelector stays on Tier 1.
"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor
from typing import Optional

import networkx as nx

from .base import AbstractGraphBackend

logger = logging.getLogger(__name__)

# Cypher: store all nodes
_MERGE_NODE = """
MERGE (n:Router {id: $id})
SET n.label       = $label,
    n.x           = $x,
    n.y           = $y,
    n.node_type   = $node_type
"""

# Cypher: store a directed link (stored as undirected via MERGE on canonical order)
_MERGE_LINK = """
MATCH (a:Router {id: $source}), (b:Router {id: $target})
MERGE (a)-[r:LINK {id: $link_id}]->(b)
SET r.weight         = $weight,
    r.latency_ms     = $latency_ms,
    r.bandwidth_mbps = $bandwidth_mbps,
    r.utilisation    = $utilisation,
    r.packet_loss    = $packet_loss,
    r.jitter         = $jitter,
    r.cost           = $cost
"""

# Cypher: ego subgraph — nodes within N hops of start, plus all links between them
_EGO_NODES = """
MATCH (start:Router {id: $start_id})-[:LINK*0..$radius]-(n:Router)
RETURN DISTINCT n.id AS id, n.label AS label, n.x AS x, n.y AS y,
       n.node_type AS node_type
"""

_EGO_LINKS = """
MATCH (start:Router {id: $start_id})-[:LINK*0..$radius]-(n:Router)
WITH collect(DISTINCT n) AS nbrs
UNWIND nbrs AS a
MATCH (a)-[r:LINK]->(b:Router)
WHERE b IN nbrs
RETURN a.id AS source, b.id AS target,
       r.id AS link_id, r.weight AS weight,
       r.latency_ms AS latency_ms, r.bandwidth_mbps AS bandwidth_mbps,
       r.utilisation AS utilisation, r.packet_loss AS packet_loss,
       r.jitter AS jitter, r.cost AS cost
"""


class Neo4jBackend(AbstractGraphBackend):
    tier: int = 2
    EGO_RADIUS: int = 10

    def __init__(self, uri: str, user: str, password: str):
        self._uri = uri
        self._user = user
        self._password = password
        self._driver = None
        self._available = False
        self._node_count: int = 0

    # ------------------------------------------------------------------
    # Connection lifecycle
    # ------------------------------------------------------------------

    def connect(self) -> bool:
        """Attempt to open a Neo4j driver. Returns True on success."""
        try:
            from neo4j import GraphDatabase  # type: ignore
            self._driver = GraphDatabase.driver(
                self._uri, auth=(self._user, self._password)
            )
            # Verify connectivity
            self._driver.verify_connectivity()
            self._available = True
            logger.info("[Tier 2] Neo4j connected at %s", self._uri)
            return True
        except ImportError:
            logger.warning(
                "[Tier 2] neo4j Python driver not installed. "
                "Install with: pip install neo4j>=5.0. Staying on Tier 1."
            )
        except Exception as exc:
            logger.warning(
                "[Tier 2] Neo4j unreachable at %s (%s). Staying on Tier 1.",
                self._uri, exc,
            )
        self._available = False
        return False

    def close(self):
        if self._driver:
            try:
                self._driver.close()
            except Exception:
                pass

    @property
    def is_available(self) -> bool:
        return self._available

    # ------------------------------------------------------------------
    # AbstractGraphBackend interface
    # ------------------------------------------------------------------

    async def store(self, graph: nx.Graph) -> None:
        """Write all nodes and edges to Neo4j using MERGE (idempotent)."""
        if not self._available:
            return
        try:
            with self._driver.session() as session:
                # Clear old data first for a clean reload
                session.run("MATCH (n:Router) DETACH DELETE n")

                # Write nodes
                for node_id, data in graph.nodes(data=True):
                    session.run(_MERGE_NODE, {
                        "id":        node_id,
                        "label":     data.get("label", node_id),
                        "x":         float(data.get("x", 0)),
                        "y":         float(data.get("y", 0)),
                        "node_type": data.get("node_type", "router"),
                    })

                # Write edges
                for u, v, data in graph.edges(data=True):
                    lat  = data.get("latency_ms",    data.get("latency",    5.0))
                    util = data.get("utilisation",   data.get("utilization", 0.0))
                    session.run(_MERGE_LINK, {
                        "source":        u,
                        "target":        v,
                        "link_id":       data.get("link_id", f"{u}-{v}"),
                        "weight":        data.get("weight",  self.compute_weight(lat, util)),
                        "latency_ms":    lat,
                        "bandwidth_mbps": data.get("bandwidth_mbps", data.get("bandwidth", 100.0)),
                        "utilisation":   util,
                        "packet_loss":   data.get("packet_loss", 0.0),
                        "jitter":        data.get("jitter", 0.0),
                        "cost":          data.get("cost",   lat),
                    })

            self._node_count = graph.number_of_nodes()
            logger.info(
                "[Tier 2] Neo4j stored %d nodes, %d edges",
                graph.number_of_nodes(), graph.number_of_edges(),
            )
        except Exception as exc:
            logger.error("[Tier 2] Neo4j store failed: %s", exc)

    def get_graph(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
    ) -> nx.Graph:
        """
        Extract ego_graph(radius=10) from Neo4j for source (and target).
        The union of both ego subgraphs is returned so the algorithm has
        full connectivity context around both endpoints.
        """
        if not self._available:
            raise RuntimeError("Neo4j backend not available")

        g = nx.Graph()

        for start_id in filter(None, [source, target]):
            self._add_ego_subgraph(g, start_id)

        if g.number_of_nodes() == 0 and source:
            logger.warning(
                "[Tier 2] Ego subgraph for %s is empty — "
                "check that node exists in Neo4j",
                source,
            )
        return g

    def node_count(self) -> int:
        return self._node_count

    @property
    def executor_class(self):
        return ProcessPoolExecutor

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _add_ego_subgraph(self, g: nx.Graph, start_id: str) -> None:
        """Query Neo4j for ego subgraph around start_id and merge into g."""
        with self._driver.session() as session:
            # Nodes
            node_result = session.run(
                _EGO_NODES, {"start_id": start_id, "radius": self.EGO_RADIUS}
            )
            for rec in node_result:
                nid = rec["id"]
                if not g.has_node(nid):
                    g.add_node(
                        nid,
                        label=rec["label"] or nid,
                        x=float(rec["x"] or 0),
                        y=float(rec["y"] or 0),
                        node_type=rec["node_type"] or "router",
                        failed=False,
                    )

            # Links
            link_result = session.run(
                _EGO_LINKS, {"start_id": start_id, "radius": self.EGO_RADIUS}
            )
            for rec in link_result:
                src, tgt = rec["source"], rec["target"]
                if g.has_node(src) and g.has_node(tgt) and not g.has_edge(src, tgt):
                    lat  = float(rec["latency_ms"]    or 5.0)
                    util = float(rec["utilisation"]   or 0.0)
                    g.add_edge(src, tgt,
                        link_id       = rec["link_id"] or f"{src}-{tgt}",
                        weight        = float(rec["weight"] or self.compute_weight(lat, util)),
                        latency_ms    = lat,
                        latency       = lat,
                        bandwidth_mbps= float(rec["bandwidth_mbps"] or 100.0),
                        bandwidth     = float(rec["bandwidth_mbps"] or 100.0),
                        utilisation   = util,
                        utilization   = util,
                        packet_loss   = float(rec["packet_loss"] or 0.0),
                        jitter        = float(rec["jitter"]      or 0.0),
                        cost          = float(rec["cost"]        or lat),
                        failed        = False,
                    )
