"""
RouteScope — Layer 2: TierSelector

Automatic backend selection based on node count (spec §9.1):

  Tier 1  ≤ TIER1_MAX_NODES  (default 50,000)   → NetworkXBackend
  Tier 2  ≤ TIER2_MAX_NODES  (default 500,000)  → Neo4jBackend
  Tier 3  > TIER2_MAX_NODES                      → Neo4j cluster (future)

The selector is initialised once at startup by main.py after graph_builder
has loaded the topology. From that point, every call to get_graph()
returns a NetworkX graph — the caller never knows or cares which backend
produced it.
"""
from __future__ import annotations

import logging
from typing import Optional

import networkx as nx

from .base import AbstractGraphBackend
from .networkx_backend import networkx_backend, NetworkXBackend
from .neo4j_backend import Neo4jBackend

logger = logging.getLogger(__name__)


class TierSelector:
    """
    Singleton that owns the active backend and exposes get_graph().

    Usage (in main.py lifespan):
        await tier_selector.initialize(graph_builder.snapshot())

    Usage (in algorithm_runner.py):
        graph = tier_selector.get_graph(source, destination)
    """

    def __init__(self):
        self._backend: AbstractGraphBackend = networkx_backend
        self._neo4j: Optional[Neo4jBackend] = None

    async def initialize(self, graph: nx.Graph) -> None:
        """
        Select and initialise the appropriate backend for the given graph.
        Called once at startup after topology is loaded.

        FORCE_STORAGE_TIER=2 overrides auto-selection for demo purposes.
        """
        from ..config import settings

        n = graph.number_of_nodes()
        forced = settings.FORCE_STORAGE_TIER

        if forced == 2:
            logger.info(
                "[Layer 2] FORCE_STORAGE_TIER=2 — activating Tier 2 Neo4j "
                "(graph has %d nodes, would normally be Tier 1)", n
            )
            await self._activate_tier2(graph, settings)
            return

        logger.info("[Layer 2] Graph has %d nodes — selecting tier...", n)

        if n <= settings.TIER1_MAX_NODES:
            await self._activate_tier1(graph)

        elif n <= settings.TIER2_MAX_NODES:
            await self._activate_tier2(graph, settings)

        else:
            # Tier 3 placeholder — fall back to Tier 1 with a warning
            logger.warning(
                "[Layer 2] %d nodes exceeds Tier 2 max (%d). "
                "Tier 3 (Neo4j cluster + Kafka) is not yet implemented. "
                "Falling back to Tier 1 NetworkX backend.",
                n, settings.TIER2_MAX_NODES,
            )
            await self._activate_tier1(graph)

    async def _activate_tier1(self, graph: nx.Graph) -> None:
        self._backend = networkx_backend
        await networkx_backend.store(graph)
        logger.info(
            "[Layer 2] Active: Tier 1 — NetworkX in-memory "
            "(ThreadPoolExecutor, full graph over WebSocket)"
        )

    async def _activate_tier2(self, graph: nx.Graph, settings) -> None:
        neo4j = Neo4jBackend(
            uri=settings.NEO4J_URI,
            user=settings.NEO4J_USER,
            password=settings.NEO4J_PASS,
        )
        connected = neo4j.connect()

        if connected:
            await neo4j.store(graph)
            self._neo4j = neo4j
            self._backend = neo4j
            logger.info(
                "[Layer 2] Active: Tier 2 — Neo4j Community "
                "(ProcessPoolExecutor, ego_graph subgraph extraction, radius=%d)",
                Neo4jBackend.EGO_RADIUS,
            )
        else:
            logger.warning(
                "[Layer 2] Tier 2 selected but Neo4j unavailable. "
                "Falling back to Tier 1 NetworkX backend."
            )
            await self._activate_tier1(graph)

    def get_graph(
        self,
        source: Optional[str] = None,
        target: Optional[str] = None,
    ) -> nx.Graph:
        """
        Return the graph for algorithm execution.
        Tier 1: full snapshot deep-copy.
        Tier 2: ego_graph(source ∪ target, radius=10) from Neo4j.
        """
        return self._backend.get_graph(source, target)

    @property
    def active_tier(self) -> int:
        return self._backend.tier

    @property
    def backend_name(self) -> str:
        from .neo4j_backend import Neo4jBackend
        if isinstance(self._backend, Neo4jBackend):
            return "Neo4j"
        return "NetworkX"

    @property
    def executor_class(self):
        return self._backend.executor_class

    def node_count(self) -> int:
        return self._backend.node_count()

    def update_tier1_weights(self, updates: list[dict]) -> None:
        """Called by MetricSimulator to keep Tier 1 weights current."""
        if isinstance(self._backend, NetworkXBackend):
            self._backend.update_edge_weights(updates)

    def close(self):
        if self._neo4j:
            self._neo4j.close()


# Singleton
tier_selector = TierSelector()
