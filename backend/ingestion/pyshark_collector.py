"""
Layer 1 — pyshark Packet Capture Collector

Uses pyshark (tshark wrapper) to capture live traffic on a network interface
and derive real throughput (bytes/sec) and packet rates.

On Windows: requires Wireshark/tshark installed (adds tshark to PATH).
Falls back silently when tshark is not available.
"""
import asyncio
import logging
import shutil
import time
from typing import Optional

logger = logging.getLogger(__name__)

_TSHARK_BIN = shutil.which("tshark") or shutil.which("tshark.exe")


def _pyshark_available() -> bool:
    if not _TSHARK_BIN:
        return False
    try:
        import pyshark  # noqa: F401
        return True
    except Exception:
        return False


async def capture_throughput(
    interface: str,
    duration: float = 3.0,
    packet_count: int = 500,
) -> dict:
    """
    Capture packets on `interface` for `duration` seconds (or `packet_count`
    packets, whichever comes first).

    Returns {bytes_per_sec, packets_per_sec, utilization_mbps}.
    Returns {} when pyshark/tshark is not installed.
    """
    if not _pyshark_available():
        logger.debug("pyshark/tshark not available — skipping capture")
        return {}

    try:
        import pyshark

        loop = asyncio.get_event_loop()

        def _capture() -> dict:
            cap = pyshark.LiveCapture(
                interface=interface,
                tshark_path=_TSHARK_BIN,
            )
            t0 = time.perf_counter()
            total_bytes = 0
            pkt_count = 0

            for pkt in cap.sniff_continuously(packet_count=packet_count):
                elapsed = time.perf_counter() - t0
                if elapsed >= duration:
                    break
                try:
                    total_bytes += int(pkt.length)
                    pkt_count += 1
                except Exception:
                    pass

            elapsed = max(time.perf_counter() - t0, 0.001)
            cap.close()

            bps  = total_bytes / elapsed
            mbps = bps / 1_000_000
            pps  = pkt_count / elapsed
            return {
                "bytes_per_sec":    round(bps, 1),
                "packets_per_sec":  round(pps, 1),
                "utilization_mbps": round(mbps, 4),
            }

        result = await asyncio.wait_for(
            loop.run_in_executor(None, _capture),
            timeout=duration + 5.0,
        )
        logger.info("pyshark capture on %s → %s", interface, result)
        return result

    except asyncio.TimeoutError:
        logger.debug("pyshark capture timed out on %s", interface)
        return {}
    except Exception as exc:
        logger.debug("pyshark capture failed: %s", exc)
        return {}


async def list_interfaces() -> list[str]:
    """Return available network interfaces via tshark -D."""
    if not _TSHARK_BIN:
        return []
    try:
        proc = await asyncio.create_subprocess_exec(
            _TSHARK_BIN, "-D",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=5)
        lines = stdout.decode(errors="replace").splitlines()
        return [ln.split(None, 1)[-1].strip() for ln in lines if ln.strip()]
    except Exception:
        return []
