"""
RouteScope — Parallel Algorithm Runner

Runs all registered algorithms simultaneously on a graph snapshot
obtained from the Layer 2 tier_selector.

Tier 1: ThreadPoolExecutor  (NetworkX in-memory; GIL-bound, acceptable at scale)
Tier 2: ProcessPoolExecutor (ego_graph from Neo4j; bypasses GIL for true CPU parallelism)

Graph source: tier_selector.get_graph(source, destination)
  Tier 1 → full deep-copied NetworkX graph
  Tier 2 → ego_graph(source ∪ destination, radius=10) extracted from Neo4j
"""
import logging
import time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, TimeoutError as FuturesTimeout
from typing import Optional

import networkx as nx

from ..algorithms import ALGORITHM_REGISTRY
from ..algorithms.base import AlgorithmResult
from ..config import settings
from ..engine.metrics_engine import compute_survivability

logger = logging.getLogger(__name__)

# Tier 1: shared thread pool, sized to algorithm count
_thread_executor = ThreadPoolExecutor(max_workers=len(ALGORITHM_REGISTRY) + 2)
# Tier 2: process pool created lazily on first Tier 2 request
_process_executor: Optional[ProcessPoolExecutor] = None


def _get_executor(use_processes: bool):
    global _process_executor
    if use_processes:
        if _process_executor is None:
            _process_executor = ProcessPoolExecutor(
                max_workers=len(ALGORITHM_REGISTRY) + 2
            )
        return _process_executor
    return _thread_executor


def _run_single(algo, graph: nx.Graph, source: str, destination: str) -> AlgorithmResult:
    """Run one algorithm; catch all exceptions so one failure does not block others."""
    try:
        return algo.compute(graph, source, destination)
    except Exception as exc:
        logger.error("Algorithm %s failed: %s", algo.name, exc)
        return AlgorithmResult(
            algorithm=algo.name,
            color=algo.color,
            path=[],
            cost=float("inf"),
            hop_count=0,
            runtime_ms=0.0,
            convergence_ms=0.0,
            reachable=False,
            metadata={"error": str(exc)},
        )


async def run_all_algorithms(
    graph: nx.Graph,
    source: str,
    destination: str,
) -> dict:
    """
    Run all algorithms in parallel on the provided graph snapshot.
    Returns a dict ready for JSON serialisation / WebSocket broadcast.
    """
    import asyncio
    from ..graph_storage import tier_selector

    t_total = time.perf_counter()

    # Tier 2+ uses ProcessPoolExecutor to bypass GIL for CPU-bound graph traversal
    use_processes = tier_selector.active_tier >= 2
    executor = _get_executor(use_processes)

    # Submit all algorithms simultaneously — identical graph copy per algorithm
    futures = {
        executor.submit(_run_single, algo, graph, source, destination): algo.name
        for algo in ALGORITHM_REGISTRY
    }

    results = []
    loop = asyncio.get_event_loop()

    for future, name in futures.items():
        try:
            result = await loop.run_in_executor(
                None,
                lambda f=future: f.result(timeout=settings.ALGORITHM_TIMEOUT),
            )
            results.append(result)
        except FuturesTimeout:
            logger.warning("Algorithm %s timed out", name)
        except Exception as exc:
            logger.error("Algorithm %s runner error: %s", name, exc)

    total_ms = (time.perf_counter() - t_total) * 1000
    survivability = compute_survivability(results, graph)

    return {
        "source": source,
        "destination": destination,
        "results": [r.to_dict() for r in results],
        "total_runtime_ms": round(total_ms, 3),
        "survivability_score": round(survivability, 4),
        "algorithm_count": len(results),
        "tier": tier_selector.active_tier,
    }


async def run_all_algorithms_for_nodes(source: str, destination: str) -> dict:
    """
    Entry point for WebSocket 'compute' messages.
    Fetches the tier-appropriate graph from Layer 2 then runs all algorithms.
    """
    from ..graph_storage import tier_selector
    graph = tier_selector.get_graph(source, destination)
    return await run_all_algorithms(graph, source, destination)
