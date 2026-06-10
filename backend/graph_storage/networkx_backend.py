"""
RouteScope — Layer 2: Tier 1 NetworkX Backend

Uses the existing in-memory graph_builder as its data source.
get_graph() returns a deep-copied snapshot of the full graph,
with the spec weight attribute stamped on every edge.

Active when node_count ≤ TIER1_MAX_NODES (default 50,000).
Uses ThreadPoolExecutor (GIL-bound, acceptable at Tier 1 scale).
"""
from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import networkx as nx

from .base import AbstractGraphBackend

logger = logging.getLogger(__name__)


class NetworkXBackend(AbstractGraphBackend):
    tier: int = 1

    def __init__(self):
        self._graph: nx.Graph = nx.Graph()

    async def store(self, graph: nx.Graph) -> None:
        """Accept the full NetworkX graph and stamp weight on every edge."""
        self._stamp_weights(graph)
        self._graph = graph
        logger.info(
            "[Tier 1] NetworkXBackend stored %d nodes, %d edges",
            graph.number_of_nodes(),
            graph.number_of_edges(),
        )

    def get_graph(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
    ) -> nx.Graph:
        """Return a deep-copied snapshot. source/target ignored at Tier 1."""
        import copy
        return copy.deepcopy(self._graph)

    def node_count(self) -> int:
        return self._graph.number_of_nodes()

    @property
    def executor_class(self):
        return ThreadPoolExecutor

    def update_edge_weights(self, updates: list[dict]) -> None:
        """
        Called by MetricSimulator every tick to keep weight in sync.
        updates: list of {link_id, latency, utilization, ...}
        """
        for upd in updates:
            lid = upd["link_id"]
            edge = self._find_edge(lid)
            if edge:
                u, v = edge
                if self._graph.has_edge(u, v):
                    attrs = self._graph[u][v]
                    lat = upd.get("latency", attrs.get("latency_ms", attrs.get("latency", 5.0)))
                    util = upd.get("utilization", attrs.get("utilisation", attrs.get("utilization", 0.0)))
                    attrs["weight"] = self.compute_weight(lat, util)

    def _find_edge(self, link_id: str) -> Optional[tuple]:
        for u, v, data in self._graph.edges(data=True):
            if data.get("link_id") == link_id:
                return (u, v)
        return None

    @staticmethod
    def _stamp_weights(graph: nx.Graph) -> None:
        """Compute and set the spec weight on every edge that lacks one."""
        for u, v, data in graph.edges(data=True):
            lat = data.get("latency_ms", data.get("latency", data.get("base_latency", 5.0)))
            util = data.get("utilisation", data.get("utilization", 0.0))
            util_frac = max(0.0, min(util, 99.9)) / 100.0
            data["weight"] = round(lat / (1.0 - util_frac + 0.001), 4)
            # Ensure spec-canonical attribute names exist alongside existing ones
            data.setdefault("latency_ms", lat)
            data.setdefault("bandwidth_mbps", data.get("bandwidth", 100.0))
            data.setdefault("utilisation", util)


# Singleton
networkx_backend = NetworkXBackend()
