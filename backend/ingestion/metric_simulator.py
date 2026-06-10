"""
RouteScope — Metric Simulator + Real Collector Blend

Primary source: real measurements from Layer 1 collectors
  - netmiko_collector  : real interface bandwidth/loss via GNS3 telnet
  - iperf3_collector   : real TCP throughput / UDP jitter (needs IPERF3_SERVER)
  - scapy_collector    : real ICMP latency (needs Npcap on Windows)
  - pyshark_collector  : real packet capture throughput (needs tshark)

Fallback: statistical simulation for any metric not covered by live data.
"""
import asyncio
import logging
import math
import random
import time
from typing import Optional

import numpy as np

from ..config import settings

logger = logging.getLogger(__name__)


def _log_normal(mean: float, sigma: float = 0.3) -> float:
    """Log-normal random sample, always positive."""
    return float(np.random.lognormal(np.log(mean), sigma))


def _clamp(val: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, val))


class LinkMetrics:
    """Holds the live metric state for one link."""

    def __init__(self, link_id: str, base_latency: float, base_bandwidth: float):
        self.link_id = link_id
        self.base_latency = base_latency
        self.base_bandwidth = base_bandwidth

        # Start with realistic but varied initial values
        self.latency: float = _log_normal(base_latency, 0.2)
        self.bandwidth: float = base_bandwidth
        self.utilization: float = random.uniform(5, 40)
        self.packet_loss: float = float(np.random.pareto(5) * 0.5)
        self.jitter: float = _log_normal(max(base_latency * 0.1, 0.5), 0.4)
        self.cost: float = self._compute_cost()

        # Internal dynamics
        self._phase_offset: float = random.uniform(0, 2 * math.pi)
        self._burst_until: float = 0.0

    def _compute_cost(self) -> float:
        """
        Dynamic routing cost formula:
          cost = latency × (1 + util²) × loss_penalty × bw_penalty
        """
        util_factor = 1.0 + (self.utilization / 100.0) ** 2
        loss_factor = 1.0 / max(1.0 - self.packet_loss / 100.0, 0.01)
        bw_factor = 1.0 + (100.0 / max(self.bandwidth, 1.0)) * 0.1
        return round(self.latency * util_factor * loss_factor * bw_factor, 4)

    def step(self, t: float, congestion_boost: float = 0.0) -> dict:
        """
        Advance metrics by one time step.
        `t`               — monotonic time (seconds)
        `congestion_boost`— extra utilization from congestion simulation (0–100)
        Returns a dict of updated fields.
        """
        # Sinusoidal utilization cycle (period 60s) + congestion boost
        base_util = 20 + 35 * math.sin(t / 30 + self._phase_offset) ** 2
        base_util = _clamp(base_util + congestion_boost, 0, 100)

        # Random burst events
        if t > self._burst_until and random.random() < 0.02:
            self._burst_until = t + random.uniform(2, 8)

        if t < self._burst_until:
            base_util = _clamp(base_util + random.uniform(20, 50), 0, 100)

        # Smooth latency with base + utilization-induced queuing delay
        queuing_delay = base_util ** 1.5 / 1000  # ms
        target_latency = self.base_latency + queuing_delay + _log_normal(0.5, 0.5)
        # Low-pass filter (alpha = 0.3)
        self.latency = _clamp(0.7 * self.latency + 0.3 * target_latency, 0.1, 500)

        # Utilization
        self.utilization = _clamp(
            0.8 * self.utilization + 0.2 * base_util + random.gauss(0, 1), 0, 100
        )

        # Packet loss: low normally, spikes with high utilization
        if self.utilization > 80:
            target_loss = random.uniform(1, 5)
        elif self.utilization > 60:
            target_loss = random.uniform(0.1, 1)
        else:
            target_loss = float(np.random.pareto(8)) * 0.2
        self.packet_loss = _clamp(0.9 * self.packet_loss + 0.1 * target_loss, 0, 30)

        # Jitter
        self.jitter = _clamp(
            _log_normal(max(self.latency * 0.05, 0.1), 0.5), 0.01, 50
        )

        self.cost = self._compute_cost()

        return {
            "link_id": self.link_id,
            "latency": round(self.latency, 3),
            "bandwidth": round(self.bandwidth, 1),
            "utilization": round(self.utilization, 2),
            "packet_loss": round(self.packet_loss, 4),
            "jitter": round(self.jitter, 3),
            "cost": round(self.cost, 4),
        }


class MetricSimulator:
    """
    Background task: ticks all link metrics every METRIC_UPDATE_INTERVAL s
    and pushes updates to the graph_builder and WebSocket manager.

    Real-data cache: updated by Layer 1 collectors every REAL_COLLECT_INTERVAL s.
    Any metric present in the cache overrides the simulated value.
    """

    # How often to hit the real collectors (seconds) — separate from sim tick
    REAL_COLLECT_INTERVAL = 10.0

    def __init__(self):
        self._links: dict[str, LinkMetrics] = {}
        self._congestion_map: dict[str, float] = {}  # link_id → extra utilization
        self._running: bool = False
        self._start_time: float = time.monotonic()
        # Real data cache: {link_id: {metric: value, "_ts": timestamp}}
        self._real_cache: dict[str, dict] = {}
        self._last_real_collect: float = 0.0
        self._topology: dict = {}          # updated by init_links

    def init_links(self, links: list[dict]):
        """Initialise metric state for each link in the topology."""
        self._links.clear()
        self._topology = {"links": links}
        for lnk in links:
            lid = lnk["id"]
            self._links[lid] = LinkMetrics(
                lid,
                lnk.get("base_latency", 5.0),
                lnk.get("base_bandwidth", 100.0),
            )
        logger.info("MetricSimulator initialised with %d links", len(self._links))

    def set_congestion(self, link_id: str, boost: float):
        """Inject artificial congestion on a link (extra utilization %)."""
        if boost <= 0:
            self._congestion_map.pop(link_id, None)
        else:
            self._congestion_map[link_id] = _clamp(boost, 0, 100)

    def get_all_metrics(self) -> dict[str, dict]:
        """Return current snapshot of all link metrics."""
        return {
            lid: {
                "link_id": lm.link_id,
                "latency": round(lm.latency, 3),
                "bandwidth": round(lm.bandwidth, 1),
                "utilization": round(lm.utilization, 2),
                "packet_loss": round(lm.packet_loss, 4),
                "jitter": round(lm.jitter, 3),
                "cost": round(lm.cost, 4),
            }
            for lid, lm in self._links.items()
        }

    def tick(self) -> list[dict]:
        """Advance all links by one step; return list of updated metric dicts."""
        t = time.monotonic() - self._start_time
        updates = []
        for lid, lm in self._links.items():
            boost = self._congestion_map.get(lid, 0.0)
            updates.append(lm.step(t, boost))
        return updates

    async def _run_real_collectors(self):
        """
        Call all Layer 1 collectors and merge results into self._real_cache.
        Runs every REAL_COLLECT_INTERVAL seconds.
        """
        from .gns3_client import gns3_client
        from .netmiko_collector import collect_link_metrics
        from .iperf3_collector import measure as iperf3_measure
        from ..config import settings as cfg

        now = time.monotonic()

        # --- Netmiko: real bandwidth/loss per link via GNS3 console ---
        try:
            netmiko_data = await collect_link_metrics(self._topology, gns3_client)
            for lid, metrics in netmiko_data.items():
                entry = self._real_cache.setdefault(lid, {})
                entry.update(metrics)
                entry["_ts"] = now
            if netmiko_data:
                logger.debug("Netmiko updated %d links", len(netmiko_data))
        except Exception as exc:
            logger.debug("Netmiko collector error: %s", exc)

        # --- iperf3: real bandwidth + jitter (all links share same server) ---
        if cfg.IPERF3_SERVER:
            try:
                iperf_data = await iperf3_measure(cfg.IPERF3_SERVER)
                if iperf_data:
                    for lid in self._links:
                        entry = self._real_cache.setdefault(lid, {})
                        if "bandwidth_mbps" in iperf_data:
                            entry["bandwidth"] = iperf_data["bandwidth_mbps"]
                        if "jitter_ms" in iperf_data:
                            entry["jitter"] = iperf_data["jitter_ms"]
                        if "packet_loss" in iperf_data:
                            entry["packet_loss"] = iperf_data["packet_loss"]
                        entry["_ts"] = now
                    logger.debug("iperf3 updated all links: %s", iperf_data)
            except Exception as exc:
                logger.debug("iperf3 collector error: %s", exc)

    def _apply_real_cache(self, sim_update: dict) -> dict:
        """
        Overlay real measurements onto a simulated update dict.
        Only overrides fields present in the cache and not older than 30 s.
        """
        lid = sim_update["link_id"]
        entry = self._real_cache.get(lid)
        if not entry:
            return sim_update

        age = time.monotonic() - entry.get("_ts", 0)
        if age > 30.0:
            return sim_update

        result = dict(sim_update)
        for field in ("bandwidth", "utilization", "packet_loss", "jitter"):
            if field in entry:
                result[field] = entry[field]
        return result

    async def run_continuous(self):
        """
        Async background loop: tick metrics, update graph, broadcast via WS.
        Every REAL_COLLECT_INTERVAL seconds also calls real collectors and
        blends their data into the tick output.
        """
        from .graph_builder import graph_builder
        from ..api.websocket import ws_manager

        self._running = True
        logger.info("MetricSimulator background loop started (real collectors active)")

        while self._running:
            # Trigger real collectors on cadence (non-blocking — fire and forget)
            now = time.monotonic()
            if now - self._last_real_collect >= self.REAL_COLLECT_INTERVAL:
                self._last_real_collect = now
                asyncio.create_task(self._run_real_collectors())

            # Tick simulated metrics
            sim_updates = self.tick()

            # Blend: override simulated values with real measurements where available
            updates = [self._apply_real_cache(u) for u in sim_updates]

            # Update the graph in-place
            graph_builder.apply_metric_updates(updates)

            # Broadcast lightweight metric diff via WebSocket
            await ws_manager.broadcast(
                {"type": "metric_update", "data": updates}
            )

            await asyncio.sleep(settings.METRIC_UPDATE_INTERVAL)

    def stop(self):
        self._running = False


# Singleton
metric_simulator = MetricSimulator()
