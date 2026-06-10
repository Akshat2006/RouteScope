"""
RouteScope — Layer 2: AbstractGraphBackend

The get_graph() method is the ONLY point of contact between the storage
layer and everything above it (algorithm engine, failure injector, API).
Every backend returns a NetworkX graph with these guaranteed attributes:

  Nodes:  id, label, x, y
  Edges:  weight, bandwidth_mbps, latency_ms, utilisation,
          bandwidth, latency, utilization, packet_loss, jitter, cost

  weight = latency_ms / (1 - utilisation + 0.001)   [spec §3.1]
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

import networkx as nx


class AbstractGraphBackend(ABC):
    tier: int = 0

    @abstractmethod
    async def store(self, graph: nx.Graph) -> None:
        """Persist the full NetworkX graph into this backend's storage."""

    @abstractmethod
    def get_graph(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
    ) -> nx.Graph:
        """
        Return a NetworkX graph ready for algorithm execution.

        Tier 1 — returns the full in-memory graph.
        Tier 2 — returns ego_graph(source ∪ target, radius=10) extracted
                  from Neo4j, bounding computation regardless of total size.
        """

    @abstractmethod
    def node_count(self) -> int:
        """Return current number of nodes in the backend."""

    @property
    def executor_class(self):
        """ThreadPoolExecutor for Tier 1, ProcessPoolExecutor for Tier 2+."""
        from concurrent.futures import ThreadPoolExecutor
        return ThreadPoolExecutor

    # ------------------------------------------------------------------
    # Shared utility — compute spec weight from edge attributes
    # ------------------------------------------------------------------

    @staticmethod
    def compute_weight(latency_ms: float, utilisation_pct: float) -> float:
        """
        Spec §3.1 dynamic weight formula:
          effective_weight = latency_ms / (1 - utilisation + 0.001)
        utilisation_pct is 0–100; convert to fraction before applying.
        """
        util_frac = max(0.0, min(utilisation_pct, 99.9)) / 100.0
        return round(latency_ms / (1.0 - util_frac + 0.001), 4)
