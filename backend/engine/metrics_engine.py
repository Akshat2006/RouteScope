"""
RouteScope — Metrics Engine

Computes survivability scores and per-algorithm performance metrics.

Survivability Score (0–1):
    S = w_reach × reachability + w_perf × path_quality + w_conv × convergence_speed

Where:
    reachability     = fraction of algorithms that found a path
    path_quality     = 1 - (cost / max_possible_cost)    normalised
    convergence_speed = 1 - (convergence_ms / worst_convergence_ms)
"""
import math
from typing import List

import networkx as nx

from ..algorithms.base import AlgorithmResult

# Survivability score weights
W_REACH = 0.40
W_PERF  = 0.35
W_CONV  = 0.25


def compute_survivability(results: List[AlgorithmResult], graph: nx.Graph) -> float:
    """
    Compute an overall survivability score [0, 1] across all algorithm results.
    """
    if not results:
        return 0.0

    # Reachability component
    reachable_count = sum(1 for r in results if r.reachable)
    reachability = reachable_count / len(results)

    if reachability == 0:
        return 0.0

    # Path quality component (lower cost = better, normalised)
    costs = [r.cost for r in results if r.reachable and r.cost < float("inf")]
    if costs:
        min_cost = min(costs)
        max_cost = max(costs) if max(costs) > 0 else 1.0
        avg_cost = sum(costs) / len(costs)
        path_quality = 1.0 - (avg_cost - min_cost) / max(max_cost - min_cost, 1.0)
    else:
        path_quality = 0.0

    # Convergence speed component (faster = better, normalised)
    conv_times = [r.convergence_ms for r in results if r.reachable]
    if conv_times:
        max_conv = max(conv_times) if max(conv_times) > 0 else 1.0
        avg_conv = sum(conv_times) / len(conv_times)
        convergence_speed = 1.0 - (avg_conv / max_conv)
    else:
        convergence_speed = 0.0

    score = W_REACH * reachability + W_PERF * path_quality + W_CONV * convergence_speed
    return round(max(0.0, min(1.0, score)), 4)


def compute_per_algorithm_score(result: AlgorithmResult, all_results: List[AlgorithmResult]) -> float:
    """Per-algorithm survivability contribution."""
    if not result.reachable:
        return 0.0

    costs = [r.cost for r in all_results if r.reachable and r.cost < float("inf")]
    conv_times = [r.convergence_ms for r in all_results if r.reachable]

    min_cost = min(costs) if costs else 1.0
    max_cost = max(costs) if costs else 1.0
    cost_score = 1.0 - (result.cost - min_cost) / max(max_cost - min_cost, 1.0)

    max_conv = max(conv_times) if conv_times else 1.0
    conv_score = 1.0 - (result.convergence_ms / max(max_conv, 1.0))

    return round(0.5 * cost_score + 0.5 * conv_score, 4)


def compute_graph_health(graph: nx.Graph) -> dict:
    """
    Compute graph-level health indicators for the dashboard.
    """
    edges = list(graph.edges(data=True))
    if not edges:
        return {"health": 0, "avg_utilization": 0, "congested_links": 0}

    utils = [d.get("utilization", 0) for _, _, d in edges]
    losses = [d.get("packet_loss", 0) for _, _, d in edges]
    latencies = [d.get("latency", 0) for _, _, d in edges]

    avg_util = sum(utils) / len(utils)
    congested = sum(1 for u in utils if u > 75)
    avg_loss = sum(losses) / len(losses)
    avg_latency = sum(latencies) / len(latencies)

    # Health score: 1 = perfect, 0 = extremely degraded
    util_health = 1.0 - (avg_util / 100)
    loss_health = 1.0 - min(avg_loss / 10, 1.0)
    health = 0.6 * util_health + 0.4 * loss_health

    return {
        "health_score": round(health, 3),
        "avg_utilization_pct": round(avg_util, 2),
        "avg_latency_ms": round(avg_latency, 3),
        "avg_packet_loss_pct": round(avg_loss, 4),
        "congested_links": congested,
        "total_links": len(edges),
        "node_count": graph.number_of_nodes(),
        "connected": nx.is_connected(graph) if graph.number_of_nodes() > 0 else False,
    }
