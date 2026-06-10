"""
RouteScope — Failure Injector

Simulates network failure events on the graph builder:
  - link_failure      : remove a specific edge
  - node_failure      : remove a node and all its edges
  - multi_link        : remove multiple edges simultaneously
  - cascading         : iteratively remove overloaded links post-failure
  - maintenance       : graceful drain (cost → ∞ before removal)
  - congestion        : artificial utilization boost on selected links
"""
import asyncio
import logging
from enum import Enum
from typing import Optional

from ..ingestion.graph_builder import graph_builder
from ..ingestion.metric_simulator import metric_simulator

logger = logging.getLogger(__name__)


class FailureType(str, Enum):
    LINK = "link_failure"
    NODE = "node_failure"
    MULTI_LINK = "multi_link"
    CASCADING = "cascading"
    MAINTENANCE = "maintenance"
    CONGESTION = "congestion"


# Tracks current active failures for UI state
_active_failures: list[dict] = []


async def inject_failure(event: dict) -> dict:
    """
    Inject a failure event into the graph.

    event = {
        "type": FailureType,
        "elements": [{"source": "R1", "target": "R2"} | {"node": "R3"}],
        "congestion_pct": 80  # for congestion type
    }
    Returns a summary of what was affected.
    """
    event_type = event.get("type")
    elements = event.get("elements", [])
    affected = []

    if event_type == FailureType.LINK:
        for el in elements:
            src, tgt = el.get("source"), el.get("target")
            if src and tgt:
                graph_builder.fail_edge(src, tgt)
                affected.append(f"{src}↔{tgt}")
                logger.info("Link failure injected: %s ↔ %s", src, tgt)

    elif event_type == FailureType.NODE:
        for el in elements:
            node = el.get("node")
            if node:
                graph_builder.fail_node(node)
                affected.append(node)
                logger.info("Node failure injected: %s", node)

    elif event_type == FailureType.MULTI_LINK:
        for el in elements:
            src, tgt = el.get("source"), el.get("target")
            if src and tgt:
                graph_builder.fail_edge(src, tgt)
                affected.append(f"{src}↔{tgt}")
        logger.info("Multi-link failure: %d links removed", len(affected))

    elif event_type == FailureType.CASCADING:
        # Phase 1: inject primary failure
        for el in elements:
            src, tgt = el.get("source"), el.get("target")
            if src and tgt:
                graph_builder.fail_edge(src, tgt)
                affected.append(f"{src}↔{tgt}")

        # Phase 2: identify overloaded links (util > 90%) and remove them
        g = graph_builder.snapshot()
        cascade_removed = []
        for u, v, data in g.edges(data=True):
            if data.get("utilization", 0) > 90:
                graph_builder.fail_edge(u, v)
                cascade_removed.append(f"{u}↔{v}")
        affected.extend(cascade_removed)
        logger.info("Cascading failure: %d additional links removed", len(cascade_removed))

    elif event_type == FailureType.MAINTENANCE:
        # Graceful: boost cost to ∞ for 1s, then remove
        for el in elements:
            src, tgt = el.get("source"), el.get("target")
            if src and tgt:
                g = graph_builder._graph
                if g.has_edge(src, tgt):
                    g[src][tgt]["cost"] = 1e9  # drain traffic
                affected.append(f"{src}↔{tgt}")
        await asyncio.sleep(1)
        for el in elements:
            src, tgt = el.get("source"), el.get("target")
            if src and tgt:
                graph_builder.fail_edge(src, tgt)
        logger.info("Planned maintenance: %s drained and removed", affected)

    elif event_type == FailureType.CONGESTION:
        congestion_pct = float(event.get("congestion_pct", 80))
        for el in elements:
            lid = el.get("link_id")
            src, tgt = el.get("source"), el.get("target")
            # Resolve link_id from source+target when not provided directly
            if not lid and src and tgt:
                g = graph_builder._graph
                if g.has_edge(src, tgt):
                    lid = g[src][tgt].get("link_id")
                elif g.has_edge(tgt, src):
                    lid = g[tgt][src].get("link_id")
            if lid:
                metric_simulator.set_congestion(lid, congestion_pct)
                # Use readable label for the affected list
                src_label = graph_builder._graph.nodes.get(src, {}).get("label", src) if src else lid
                tgt_label = graph_builder._graph.nodes.get(tgt, {}).get("label", tgt) if tgt else ""
                label = f"{src_label}↔{tgt_label}" if tgt_label else lid
                affected.append(label)
        logger.info("Congestion injected on %d links at %.0f%%", len(affected), congestion_pct)

    failure_record = {
        "type": event_type,
        "affected": affected,
        "description": event.get("description", ""),
    }
    _active_failures.append(failure_record)

    return {
        "success": True,
        "event_type": event_type,
        "affected": affected,
        "active_failure_count": len(_active_failures),
    }


async def clear_failures() -> dict:
    """Restore all failures and clear congestion."""
    graph_builder.restore_all()
    # Clear all congestion
    for lnk in graph_builder._raw_topology.get("links", []):
        metric_simulator.set_congestion(lnk["id"], 0)
    _active_failures.clear()
    logger.info("All failures cleared")
    return {"success": True, "message": "All failures cleared and topology restored"}


def get_active_failures() -> list[dict]:
    return list(_active_failures)
