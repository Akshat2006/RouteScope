"""
RouteScope — Congestion Simulator

Provides a clean interface for injecting artificial congestion on links.
Wraps metric_simulator.set_congestion() with bulk and timed operations.
"""
import asyncio
import logging
from typing import Optional
from ..ingestion.metric_simulator import metric_simulator

logger = logging.getLogger(__name__)


async def inject_congestion(link_id: str, pct: float, duration_seconds: Optional[float] = None):
    """
    Inject artificial congestion on a link.
    If duration_seconds is set, congestion auto-clears after that time.
    """
    metric_simulator.set_congestion(link_id, pct)
    logger.info("Congestion %.0f%% on %s", pct, link_id)

    if duration_seconds:
        await asyncio.sleep(duration_seconds)
        metric_simulator.set_congestion(link_id, 0)
        logger.info("Congestion cleared on %s after %.0fs", link_id, duration_seconds)


async def inject_bulk_congestion(link_ids: list[str], pct: float):
    """Inject congestion on multiple links simultaneously."""
    for lid in link_ids:
        metric_simulator.set_congestion(lid, pct)
    logger.info("Bulk congestion %.0f%% on %d links", pct, len(link_ids))


def clear_all_congestion(topology_links: list[dict]):
    """Clear congestion on all links."""
    for lnk in topology_links:
        metric_simulator.set_congestion(lnk["id"], 0)
    logger.info("All congestion cleared (%d links)", len(topology_links))
