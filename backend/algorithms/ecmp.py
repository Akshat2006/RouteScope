"""
RouteScope — ECMP (Equal-Cost Multi-Path)

Finds ALL shortest paths of equal cost between source and destination.
Returns all paths for multi-path overlay on the dashboard.

Flow splitting model: round-robin across all equal-cost paths.
"""
import time
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult


class ECMPAlgorithm(BaseRoutingAlgorithm):
    name = "ECMP"
    color = "#fd79a8"  # pink

    def compute(self, graph: nx.Graph, source: str, destination: str, **kwargs) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            # Enumerate ALL shortest paths (by cost weight)
            # NetworkX all_shortest_paths uses BFS — for weighted we use
            # dijkstra + path enumeration
            best_cost = nx.dijkstra_path_length(graph, source, destination, weight="cost")

            # Find all paths with cost ≤ best_cost + epsilon
            epsilon = best_cost * 0.001  # 0.1% tolerance
            all_paths = []

            for path in nx.all_simple_paths(graph, source, destination):
                path_cost = self._path_cost(graph, path)
                if abs(path_cost - best_cost) <= epsilon:
                    all_paths.append((path, path_cost))
                    if len(all_paths) >= 16:  # cap to 16 paths for performance
                        break

            runtime_ms = (time.perf_counter() - t0) * 1000

            if not all_paths:
                return self._unreachable(self.name, self.color, runtime_ms)

            # Primary path is the first found; all_paths for overlay
            primary = all_paths[0][0]

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=primary,
                cost=best_cost,
                hop_count=len(primary) - 1,
                runtime_ms=runtime_ms,
                convergence_ms=runtime_ms * 1.0,
                reachable=True,
                all_paths=[p for p, _ in all_paths],
                metadata={
                    "ecmp_path_count": len(all_paths),
                    "load_balance": "round-robin",
                    "paths": [
                        {"path": p, "cost": round(c, 4)}
                        for p, c in all_paths
                    ],
                },
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
