"""
RouteScope — Base Routing Algorithm

Every algorithm must inherit BaseRoutingAlgorithm and implement compute().
AlgorithmResult is the canonical return type.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

import networkx as nx


@dataclass
class AlgorithmResult:
    algorithm: str
    color: str                          # hex color for dashboard overlay
    path: List[str]                     # primary path (ordered node IDs)
    cost: float                         # total path cost
    hop_count: int                      # number of hops
    runtime_ms: float                   # wall-clock execution time (ms)
    convergence_ms: float               # estimated protocol convergence time
    reachable: bool                     # True if src → dst is reachable
    all_paths: List[List[str]] = field(default_factory=list)  # for ECMP / multi-path
    metadata: dict = field(default_factory=dict)              # algorithm-specific extras

    @staticmethod
    def _safe_float(v: float) -> float | None:
        """Convert inf/nan to None so JSON serialisation never crashes."""
        if v is None:
            return None
        import math
        if math.isinf(v) or math.isnan(v):
            return None
        return round(v, 4)

    def to_dict(self) -> dict:
        return {
            "algorithm": self.algorithm,
            "color": self.color,
            "path": self.path,
            "cost": self._safe_float(self.cost),
            "hop_count": self.hop_count,
            "runtime_ms": self._safe_float(self.runtime_ms),
            "convergence_ms": self._safe_float(self.convergence_ms),
            "reachable": self.reachable,
            "all_paths": self.all_paths,
            "metadata": self.metadata,
        }


class BaseRoutingAlgorithm(ABC):
    """
    Abstract base class for all routing algorithms.

    Subclasses must define:
        name  (str)  — display name
        color (str)  — hex colour for graph overlay
    and implement:
        compute(graph, source, destination) -> AlgorithmResult
    """

    name: str = "base"
    color: str = "#ffffff"

    @abstractmethod
    def compute(
        self,
        graph: nx.Graph,
        source: str,
        destination: str,
        **kwargs,
    ) -> AlgorithmResult:
        """Run the routing algorithm on a graph snapshot."""

    # ------------------------------------------------------------------
    # Utility helpers shared by all algorithms
    # ------------------------------------------------------------------

    @staticmethod
    def _edge_cost(graph: nx.Graph, u: str, v: str) -> float:
        """Return the 'cost' attribute of edge (u,v)."""
        return graph[u][v].get("cost", 1.0)

    @staticmethod
    def _path_cost(graph: nx.Graph, path: List[str]) -> float:
        """Sum edge costs along a path."""
        if not path or len(path) < 2:
            return 0.0
        return sum(
            graph[path[i]][path[i + 1]].get("cost", 1.0)
            for i in range(len(path) - 1)
        )

    @staticmethod
    def _unreachable(algorithm: str, color: str, runtime_ms: float) -> AlgorithmResult:
        """Return a standard 'unreachable' result."""
        return AlgorithmResult(
            algorithm=algorithm,
            color=color,
            path=[],
            cost=float("inf"),
            hop_count=0,
            runtime_ms=runtime_ms,
            convergence_ms=runtime_ms * 1.5,
            reachable=False,
        )

    def _timed_compute(self, fn, *args, **kwargs):
        """Run fn(*args, **kwargs) and return (result, elapsed_ms)."""
        t0 = time.perf_counter()
        result = fn(*args, **kwargs)
        elapsed = (time.perf_counter() - t0) * 1000
        return result, elapsed
