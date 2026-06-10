"""
RouteScope — CSPF (Constrained Shortest Path First)

Traffic-engineering variant of Dijkstra with constraints:
  1. Bandwidth constraint: prune links with available_bw < required_bw
  2. Latency constraint (optional): prune links exceeding max_latency
  3. Loss constraint (optional): prune links exceeding max_loss

Falls back to unconstrained Dijkstra if no path satisfies constraints.
"""
import time
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult

# Default CSPF constraints (overridable via kwargs)
DEFAULT_MIN_BW = 10.0        # Mbps — minimum required bandwidth
DEFAULT_MAX_LATENCY = 200.0  # ms — max acceptable per-hop latency
DEFAULT_MAX_LOSS = 5.0       # %  — max acceptable packet loss


class CSPFAlgorithm(BaseRoutingAlgorithm):
    name = "CSPF"
    color = "#a29bfe"  # lavender

    def compute(
        self,
        graph: nx.Graph,
        source: str,
        destination: str,
        min_bandwidth: float = DEFAULT_MIN_BW,
        max_latency: float = DEFAULT_MAX_LATENCY,
        max_loss: float = DEFAULT_MAX_LOSS,
        **kwargs,
    ) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            # Build constraint-pruned subgraph
            pruned = nx.Graph()
            pruned.add_nodes_from(graph.nodes(data=True))
            pruned_count = 0

            for u, v, data in graph.edges(data=True):
                bw = data.get("bandwidth", 100.0)
                lat = data.get("latency", 5.0)
                loss = data.get("packet_loss", 0.0)

                # Apply constraints (all must be satisfied)
                if bw < min_bandwidth:
                    pruned_count += 1
                    continue
                if lat > max_latency:
                    pruned_count += 1
                    continue
                if loss > max_loss:
                    pruned_count += 1
                    continue

                pruned.add_edge(u, v, **data)

            # Try constrained path first
            constrained = True
            try:
                path = nx.dijkstra_path(pruned, source, destination, weight="cost")
                cost = nx.dijkstra_path_length(pruned, source, destination, weight="cost")
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                # Fall back to unconstrained
                constrained = False
                path = nx.dijkstra_path(graph, source, destination, weight="cost")
                cost = nx.dijkstra_path_length(graph, source, destination, weight="cost")

            runtime_ms = (time.perf_counter() - t0) * 1000

            # Per-hop constraint satisfaction
            satisfied = []
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                if graph.has_edge(u, v):
                    d = graph[u][v]
                    satisfied.append({
                        "link": f"{u}→{v}",
                        "bw_ok": d.get("bandwidth", 0) >= min_bandwidth,
                        "lat_ok": d.get("latency", 0) <= max_latency,
                        "loss_ok": d.get("packet_loss", 0) <= max_loss,
                    })

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=path,
                cost=cost,
                hop_count=len(path) - 1,
                runtime_ms=runtime_ms,
                convergence_ms=runtime_ms * 1.2,
                reachable=True,
                metadata={
                    "constrained": constrained,
                    "pruned_links": pruned_count,
                    "constraints": {
                        "min_bandwidth_mbps": min_bandwidth,
                        "max_latency_ms": max_latency,
                        "max_loss_pct": max_loss,
                    },
                    "hop_satisfaction": satisfied,
                },
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
