"""
RouteScope — LFA (Loop-Free Alternates) / rLFA

RFC 5286 — IP Fast Reroute using Loop-Free Alternates.

For each link (S→N) on the primary path, an alternate next-hop (N') is
loop-free if it satisfies the inequality:

    D(N', D) < D(N', S) + D(S, D)   ← node-protecting LFA

Where D(X, Y) = shortest path distance from X to Y.

rLFA (Remote LFA): if no direct LFA exists, find a P-space node reachable
via a tunnel as the repair endpoint.
"""
import time
from typing import Dict, Optional
import networkx as nx
from .base import BaseRoutingAlgorithm, AlgorithmResult


def _shortest_paths_from(graph: nx.Graph, node: str) -> Dict[str, float]:
    """Dijkstra SSSP from a node; returns {node: distance} dict."""
    try:
        lengths = nx.single_source_dijkstra_path_length(graph, node, weight="cost")
        return dict(lengths)
    except Exception:
        return {}


class LFAAlgorithm(BaseRoutingAlgorithm):
    name = "LFA/rLFA"
    color = "#55efc4"  # mint green

    def compute(self, graph: nx.Graph, source: str, destination: str, **kwargs) -> AlgorithmResult:
        t0 = time.perf_counter()
        try:
            if source not in graph or destination not in graph:
                raise nx.NetworkXError("Node not in graph")

            # Step 1: Compute primary (Dijkstra) path
            primary_path = nx.dijkstra_path(graph, source, destination, weight="cost")
            primary_cost = nx.dijkstra_path_length(graph, source, destination, weight="cost")

            # Step 2: Pre-compute D(X, dest) and D(X, source) for all X
            d_from_src = _shortest_paths_from(graph, source)
            d_to_dest = _shortest_paths_from(graph, destination)
            d_src_to_dest = d_from_src.get(destination, float("inf"))

            # Step 3: For each link on primary path, find LFA
            lfa_table = {}
            for i in range(len(primary_path) - 1):
                s_node = primary_path[i]
                n_node = primary_path[i + 1]

                d_from_n = _shortest_paths_from(graph, n_node)

                best_lfa = None
                best_lfa_cost = float("inf")
                lfa_type = None

                for candidate in graph.neighbors(s_node):
                    if candidate == n_node:
                        continue  # skip primary next-hop

                    d_from_cand = _shortest_paths_from(graph, candidate)
                    d_c_to_d = d_from_cand.get(destination, float("inf"))
                    d_c_to_s = d_from_cand.get(s_node, float("inf"))
                    d_s_to_d = d_src_to_dest

                    # Node-protecting LFA condition (RFC 5286)
                    if d_c_to_d < d_c_to_s + d_s_to_d:
                        edge_cost = graph[s_node][candidate].get("cost", 1.0)
                        total = edge_cost + d_c_to_d
                        if total < best_lfa_cost:
                            best_lfa = candidate
                            best_lfa_cost = total
                            lfa_type = "LFA"

                # rLFA: if no direct LFA, look for P-space node
                if best_lfa is None:
                    for p_node in graph.nodes():
                        if p_node in (s_node, n_node, destination):
                            continue
                        d_s_to_p = d_from_src.get(p_node, float("inf"))
                        d_p_to_d = _shortest_paths_from(graph, p_node).get(destination, float("inf"))
                        d_p_to_n = _shortest_paths_from(graph, p_node).get(n_node, float("inf"))

                        # P-space condition: D(P,D) < D(N,S)+D(S,D)  avoiding N
                        if d_p_to_d < d_from_n.get(s_node, float("inf")) + d_s_to_dest:
                            if d_s_to_p + d_p_to_d < best_lfa_cost:
                                best_lfa = p_node
                                best_lfa_cost = d_s_to_p + d_p_to_d
                                lfa_type = "rLFA"
                                break

                lfa_table[f"{s_node}→{n_node}"] = {
                    "lfa_node": best_lfa,
                    "lfa_type": lfa_type,
                    "lfa_cost": round(best_lfa_cost, 4) if best_lfa else None,
                    "protected": best_lfa is not None,
                }

            coverage = sum(1 for v in lfa_table.values() if v["protected"]) / max(len(lfa_table), 1)
            runtime_ms = (time.perf_counter() - t0) * 1000

            return AlgorithmResult(
                algorithm=self.name,
                color=self.color,
                path=primary_path,
                cost=primary_cost,
                hop_count=len(primary_path) - 1,
                runtime_ms=runtime_ms,
                # LFA converges nearly instantly (pre-computed alternates)
                convergence_ms=max(runtime_ms * 0.1, 5.0),
                reachable=True,
                metadata={
                    "lfa_table": lfa_table,
                    "coverage_pct": round(coverage * 100, 1),
                    "total_links_protected": sum(1 for v in lfa_table.values() if v["protected"]),
                },
            )
        except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXError):
            runtime_ms = (time.perf_counter() - t0) * 1000
            return self._unreachable(self.name, self.color, runtime_ms)
