"""
RouteScope — Bellman-Ford Algorithm

Supports graphs with negative-weight edges.
Detects negative cycles and reports them in metadata.
"""
import time
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult


class BellmanFordAlgorithm(BaseRoutingAlgorithm):
    name = "Bellman-Ford"
    color = "#ff6b6b"  # coral red

    def compute(self, graph: nx.Graph, source: str, destination: str, **kwargs) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            # nx.bellman_ford_path uses the Bellman-Ford relaxation
            path = nx.bellman_ford_path(graph, source, destination, weight="cost")
            cost = nx.bellman_ford_path_length(graph, source, destination, weight="cost")
            runtime_ms = (time.perf_counter() - t0) * 1000

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=path,
                cost=cost,
                hop_count=len(path) - 1,
                runtime_ms=runtime_ms,
                # Bellman-Ford has O(VE) convergence — slower than Dijkstra
                convergence_ms=runtime_ms * 2.0,
                reachable=True,
                metadata={"negative_cycle": False},
            )
        except nx.NetworkXUnbounded:
            runtime_ms = (time.perf_counter() - t0) * 1000
            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=[],
                cost=float("-inf"),
                hop_count=0,
                runtime_ms=runtime_ms,
                convergence_ms=runtime_ms * 2.0,
                reachable=False,
                metadata={"negative_cycle": True},
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
