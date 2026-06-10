"""
RouteScope — EIGRP DUAL (Diffusing Update Algorithm)

Key DUAL concepts implemented:
  - Feasible Distance (FD): best known path cost to a destination
  - Reported Distance (RD): cost reported by a neighbor (= neighbor's FD)
  - Successor: best next-hop (lowest FD)
  - Feasible Successor (FS): backup next-hop satisfying RD < FD (loop-free)
  - Feasibility Condition: RD_neighbor < FD_current (guarantees loop-freedom)

Composite EIGRP metric (simplified K-values K1=K3=1, K2=K4=K5=0):
  metric = bandwidth_term + delay_term
  bandwidth_term = (10^7 / min_bw_kbps) * 256
  delay_term     = (sum_delay_us / 10) * 256
"""
import time
import heapq
import math
from typing import Dict, List, Optional, Tuple
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult


def eigrp_metric(graph: nx.Graph, path: List[str]) -> float:
    """Compute EIGRP composite metric for a path."""
    if len(path) < 2:
        return 0.0

    min_bw = float("inf")   # kbps
    total_delay = 0.0        # microseconds

    for i in range(len(path) - 1):
        data = graph[path[i]][path[i+1]]
        bw_mbps = data.get("bandwidth", 100.0)
        bw_kbps = bw_mbps * 1000
        min_bw = min(min_bw, bw_kbps)

        latency_ms = data.get("latency", 5.0)
        total_delay += latency_ms * 1000  # convert to microseconds

    if min_bw == float("inf") or min_bw <= 0:
        min_bw = 1.0

    bw_term = (10_000_000 / min_bw) * 256
    delay_term = (total_delay / 10) * 256
    return bw_term + delay_term


class EIGRPDualAlgorithm(BaseRoutingAlgorithm):
    name = "EIGRP-DUAL"
    color = "#ff9f43"  # orange

    def compute(self, graph: nx.Graph, source: str, destination: str, **kwargs) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            # Phase 1: Run Dijkstra with EIGRP composite metric to get FD for all nodes
            # We use a modified Dijkstra where edge weight = EIGRP metric contribution
            # Simplified: use composite metric as weight
            def eigrp_edge_weight(u, v, data):
                bw_kbps = data.get("bandwidth", 100.0) * 1000
                latency_us = data.get("latency", 5.0) * 1000
                bw_term = (10_000_000 / max(bw_kbps, 1)) * 256
                delay_term = (latency_us / 10) * 256
                return bw_term + delay_term

            # Build weighted graph with EIGRP metrics
            lengths, paths = nx.single_source_dijkstra(
                graph, source, weight=eigrp_edge_weight
            )

            if destination not in paths:
                raise nx.NetworkXNoPath()

            best_path = paths[destination]
            fd = lengths[destination]

            # Phase 2: Find Feasible Successors for the first hop
            feasible_successors = []
            for neighbor in graph.neighbors(source):
                if neighbor == best_path[1] if len(best_path) > 1 else False:
                    continue  # skip the successor itself
                # RD = FD from this neighbor to destination
                if neighbor in lengths:
                    # Check feasibility condition: RD(neighbor) < FD(source)
                    try:
                        rd_paths = nx.single_source_dijkstra(graph, neighbor, weight=eigrp_edge_weight)
                        rd = rd_paths[0].get(destination, float("inf"))
                        if rd < fd:  # Feasibility condition
                            feasible_successors.append({
                                "node": neighbor,
                                "rd": round(rd, 2),
                                "feasible": True,
                            })
                    except Exception:
                        pass

            runtime_ms = (time.perf_counter() - t0) * 1000

            # EIGRP converges fast due to pre-computed feasible successors
            convergence_ms = runtime_ms * 0.3 if feasible_successors else runtime_ms * 1.2

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=best_path,
                cost=fd,
                hop_count=len(best_path) - 1,
                runtime_ms=runtime_ms,
                convergence_ms=convergence_ms,
                reachable=True,
                metadata={
                    "feasible_successors": feasible_successors,
                    "successor": best_path[1] if len(best_path) > 1 else None,
                    "feasible_distance": round(fd, 2),
                    "metric_type": "composite (BW+Delay)",
                },
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
