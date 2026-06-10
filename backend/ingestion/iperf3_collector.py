"""
Layer 1 — iperf3 Collector

Runs iperf3 client to measure real TCP throughput and UDP jitter/loss
against an iperf3 server.  Set IPERF3_SERVER in .env to enable.

Falls back silently when iperf3 binary is not installed or server unreachable.
"""
import asyncio
import json
import logging
import shutil

logger = logging.getLogger(__name__)

_IPERF3_BIN = shutil.which("iperf3") or shutil.which("iperf3.exe")


async def _run_iperf3_tcp(server: str, port: int = 5201, duration: int = 3) -> dict:
    """
    Run TCP iperf3 for `duration` seconds.
    Returns {bandwidth_mbps, retransmits}.
    """
    if not _IPERF3_BIN:
        return {}
    try:
        proc = await asyncio.create_subprocess_exec(
            _IPERF3_BIN, "-c", server, "-p", str(port),
            "-t", str(duration), "-J", "--connect-timeout", "3000",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=duration + 8)
        data = json.loads(stdout)
        end = data.get("end", {})
        sent = end.get("sum_sent", {})
        bps = sent.get("bits_per_second", 0)
        retrans = sent.get("retransmits", 0)
        return {
            "bandwidth_mbps": round(bps / 1_000_000, 2),
            "retransmits": retrans,
        }
    except Exception as exc:
        logger.debug("iperf3 TCP failed: %s", exc)
        return {}


async def _run_iperf3_udp(server: str, port: int = 5201, duration: int = 3,
                           bitrate: str = "10M") -> dict:
    """
    Run UDP iperf3 for `duration` seconds.
    Returns {jitter_ms, packet_loss_pct}.
    """
    if not _IPERF3_BIN:
        return {}
    try:
        proc = await asyncio.create_subprocess_exec(
            _IPERF3_BIN, "-c", server, "-p", str(port),
            "-u", "-b", bitrate, "-t", str(duration), "-J",
            "--connect-timeout", "3000",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=duration + 8)
        data = json.loads(stdout)
        end = data.get("end", {})
        recv = end.get("sum", {})
        jitter_ms   = recv.get("jitter_ms", 0.0)
        lost        = recv.get("lost_packets", 0)
        total       = recv.get("packets", 1)
        loss_pct    = (lost / max(total, 1)) * 100.0
        return {
            "jitter_ms": round(jitter_ms, 3),
            "packet_loss": round(loss_pct, 4),
        }
    except Exception as exc:
        logger.debug("iperf3 UDP failed: %s", exc)
        return {}


async def measure(server: str, port: int = 5201) -> dict:
    """
    Run both TCP and UDP iperf3 measurements against `server`.
    Returns merged metric dict: {bandwidth_mbps, jitter_ms, packet_loss}.
    Falls back to {} when iperf3 is unavailable.
    """
    if not _IPERF3_BIN:
        logger.debug("iperf3 binary not found — skipping")
        return {}
    if not server:
        return {}

    tcp_res, udp_res = await asyncio.gather(
        _run_iperf3_tcp(server, port),
        _run_iperf3_udp(server, port),
        return_exceptions=True,
    )

    result: dict = {}
    if isinstance(tcp_res, dict):
        result.update(tcp_res)
    if isinstance(udp_res, dict):
        result.update(udp_res)
    if result:
        logger.info("iperf3 → %s", result)
    return result
