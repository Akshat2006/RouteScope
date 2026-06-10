"""
RouteScope — Dijkstra Algorithm

Standard shortest-path on composite 'cost' weight.
Uses NetworkX's optimised heap-based implementation.
"""
import time
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult


class DijkstraAlgorithm(BaseRoutingAlgorithm):
    name = "Dijkstra"
    color = "#00d4ff"  # cyan

    def compute(self, graph: nx.Graph, source: str, destination: str, **kwargs) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            path = nx.dijkstra_path(graph, source, destination, weight="cost")
            cost = nx.dijkstra_path_length(graph, source, destination, weight="cost")
            runtime_ms = (time.perf_counter() - t0) * 1000

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=path,
                cost=cost,
                hop_count=len(path) - 1,
                runtime_ms=runtime_ms,
                convergence_ms=runtime_ms * 1.1,
                reachable=True,
                metadata={"weight": "cost"},
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
