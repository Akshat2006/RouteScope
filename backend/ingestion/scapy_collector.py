"""
Layer 1 — Scapy Traceroute Collector

Runs ICMP traceroute to each reachable node IP and returns real hop latency.
On Windows requires Npcap (installed with Wireshark).

Falls back silently when Scapy is not available or nodes have no IP addresses.
"""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)


def _scapy_available() -> bool:
    try:
        import scapy.all  # noqa: F401
        return True
    except Exception:
        return False


def _icmp_ping(target_ip: str, count: int = 3, timeout: float = 2.0) -> Optional[float]:
    """
    Send ICMP echo requests, return average RTT in ms or None on failure.
    Runs synchronously — call from executor.
    """
    try:
        from scapy.all import IP, ICMP, sr1
        rtts = []
        for _ in range(count):
            pkt = IP(dst=target_ip) / ICMP()
            t0 = time.perf_counter()
            reply = sr1(pkt, timeout=timeout, verbose=False)
            if reply is not None:
                rtts.append((time.perf_counter() - t0) * 1000)
        return round(sum(rtts) / len(rtts), 3) if rtts else None
    except Exception as exc:
        logger.debug("Scapy ICMP ping to %s failed: %s", target_ip, exc)
        return None


def _traceroute_latency(target_ip: str, max_ttl: int = 15,
                        timeout: float = 2.0) -> Optional[float]:
    """
    Run ICMP traceroute and return total RTT to target in ms.
    Uses the last responding hop as the latency estimate.
    """
    try:
        from scapy.all import IP, ICMP, sr
        pkts = [IP(dst=target_ip, ttl=ttl) / ICMP() for ttl in range(1, max_ttl + 1)]
        t0 = time.perf_counter()
        answered, _ = sr(pkts, timeout=timeout, verbose=False)
        elapsed_ms = (time.perf_counter() - t0) * 1000

        if not answered:
            return None

        # Find the reply closest to the target
        for sent, recv in sorted(answered, key=lambda p: p[0].ttl, reverse=True):
            if recv.src == target_ip:
                return round(elapsed_ms, 3)

        # Return latency to the last responding hop
        last = max(answered, key=lambda p: p[0].ttl)
        return round(elapsed_ms, 3)
    except Exception as exc:
        logger.debug("Scapy traceroute to %s failed: %s", target_ip, exc)
        return None


async def probe_host(ip: str) -> Optional[float]:
    """
    Async wrapper: probe `ip` with ICMP ping (fast), falling back to traceroute.
    Returns latency in ms or None.
    """
    if not _scapy_available():
        return None
    loop = asyncio.get_event_loop()
    rtt = await loop.run_in_executor(None, _icmp_ping, ip, 3, 1.5)
    if rtt is not None:
        return rtt
    return await loop.run_in_executor(None, _traceroute_latency, ip, 10, 1.5)


async def collect_node_latencies(node_ip_map: dict[str, str]) -> dict[str, float]:
    """
    Probe each node IP concurrently.
    node_ip_map: {node_id: ip_address}
    Returns {node_id: latency_ms}.
    """
    if not _scapy_available() or not node_ip_map:
        return {}

    tasks = {nid: probe_host(ip) for nid, ip in node_ip_map.items()}
    results: dict[str, float] = {}
    for nid, coro in tasks.items():
        try:
            rtt = await coro
            if rtt is not None:
                results[nid] = rtt
        except Exception as exc:
            logger.debug("Probe %s failed: %s", nid, exc)
    return results
