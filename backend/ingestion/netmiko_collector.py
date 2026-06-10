"""
Layer 1 — Netmiko / Telnet Collector

Connects to router consoles through GNS3 (telnet) and reads real interface
statistics via `ip -s link show`.  Derives per-link bandwidth utilization and
packet loss from byte/error deltas between successive samples.

Works with FRR Docker containers and any Linux-based GNS3 node.
Falls back silently when a console is unreachable.
"""
import asyncio
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------
# Byte-delta state for rate calculation
# -----------------------------------------------------------------------
# {node_id -> {iface -> (rx_bytes, tx_bytes, rx_errors, rx_packets, ts)}}
_prev: dict[str, dict[str, tuple]] = {}


def _parse_ip_link_stats(raw: str) -> dict[str, dict]:
    """
    Parse `ip -s link show` output into per-interface dicts.
    Returns {iface: {rx_bytes, tx_bytes, rx_packets, tx_packets, rx_errors, rx_dropped}}.
    """
    result: dict[str, dict] = {}
    iface: Optional[str] = None
    state = ""
    for line in raw.splitlines():
        line = line.strip()
        m = re.match(r"^\d+:\s+(\S+?)[@:]", line)
        if m:
            iface = m.group(1)
            result[iface] = {
                "rx_bytes": 0, "tx_bytes": 0,
                "rx_packets": 0, "tx_packets": 0,
                "rx_errors": 0, "rx_dropped": 0,
            }
            state = ""
            continue
        if iface is None:
            continue
        if re.match(r"^\s*RX:", line):
            state = "rx_header"
            continue
        if re.match(r"^\s*TX:", line):
            state = "tx_header"
            continue
        nums = line.split()
        if state == "rx_header" and len(nums) >= 4:
            try:
                result[iface]["rx_bytes"]   = int(nums[0])
                result[iface]["rx_packets"] = int(nums[1])
                result[iface]["rx_errors"]  = int(nums[2])
                result[iface]["rx_dropped"] = int(nums[3])
            except ValueError:
                pass
            state = ""
            continue
        if state == "tx_header" and len(nums) >= 2:
            try:
                result[iface]["tx_bytes"]   = int(nums[0])
                result[iface]["tx_packets"] = int(nums[1])
            except ValueError:
                pass
            state = ""
    return result


async def _telnet_cmd(host: str, port: int, cmd: str, timeout: float = 6.0) -> Optional[str]:
    """
    Open a raw telnet connection to a GNS3 console port, run one command,
    return the output.
    """
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=4.0
        )
        # Drain any banner / login prompt
        try:
            await asyncio.wait_for(reader.read(2048), timeout=2.0)
        except asyncio.TimeoutError:
            pass

        # Send newline to get a shell prompt
        writer.write(b"\n")
        await asyncio.sleep(0.4)
        try:
            await asyncio.wait_for(reader.read(2048), timeout=1.5)
        except asyncio.TimeoutError:
            pass

        # Send the actual command
        writer.write((cmd + "\n").encode())
        await asyncio.sleep(1.2)

        buf = b""
        while True:
            try:
                chunk = await asyncio.wait_for(reader.read(4096), timeout=1.0)
                if not chunk:
                    break
                buf += chunk
            except asyncio.TimeoutError:
                break

        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return buf.decode("utf-8", errors="replace")

    except Exception as exc:
        logger.debug("Telnet %s:%d failed: %s", host, port, exc)
        return None


async def _get_compute_hosts(gns3_client) -> dict[str, str]:
    """Return {compute_id: console_host} from the GNS3 /v2/computes endpoint."""
    hosts: dict[str, str] = {"local": "127.0.0.1"}
    try:
        await gns3_client._ensure_client()
        r = await gns3_client._client.get(
            f"{gns3_client._base_url}/v2/computes"
        )
        r.raise_for_status()
        for c in r.json():
            hosts[c["compute_id"]] = c.get("host", "127.0.0.1")
    except Exception as exc:
        logger.debug("Could not fetch compute hosts: %s", exc)
    return hosts


async def _get_node_console_map(gns3_client, project_id: str,
                                compute_hosts: dict[str, str]) -> dict[str, dict]:
    """
    Return {node_id: {host, port, iface_prefix}} for nodes that have a console port.
    """
    result: dict[str, dict] = {}
    try:
        await gns3_client._ensure_client()
        r = await gns3_client._client.get(
            f"{gns3_client._base_url}/v2/projects/{project_id}/nodes"
        )
        r.raise_for_status()
        for n in r.json():
            port = n.get("console")
            if not port:
                continue
            cid = n.get("compute_id", "local")
            host = compute_hosts.get(cid, "127.0.0.1")
            result[n["node_id"]] = {
                "host": host,
                "port": port,
                "name": n.get("name", n["node_id"]),
            }
    except Exception as exc:
        logger.debug("Could not fetch node console map: %s", exc)
    return result


def _iface_name(adapter: int, port: int) -> str:
    """Map GNS3 adapter/port to Linux interface name (eth{port})."""
    return f"eth{port}"


async def collect_link_metrics(
    topology: dict,
    gns3_client,
) -> dict[str, dict]:
    """
    Connect to each node console, parse interface stats, return per-link metrics.

    Returns {link_id: {bandwidth_mbps, utilization, packet_loss}}.
    Latency is NOT measured here (needs ping/traceroute, see scapy_collector).
    """
    if not gns3_client.is_live or not gns3_client._project_id:
        return {}

    compute_hosts = await _get_compute_hosts(gns3_client)
    node_console = await _get_node_console_map(
        gns3_client, gns3_client._project_id, compute_hosts
    )
    if not node_console:
        return {}

    # Collect raw stats from each node concurrently
    async def collect_node(node_id: str, info: dict) -> tuple[str, Optional[dict]]:
        raw = await _telnet_cmd(info["host"], info["port"], "ip -s link show")
        if raw is None:
            return node_id, None
        return node_id, _parse_ip_link_stats(raw)

    tasks = [collect_node(nid, info) for nid, info in node_console.items()]
    node_stats: dict[str, Optional[dict]] = {}
    for nid, stats in await asyncio.gather(*tasks, return_exceptions=False):
        node_stats[nid] = stats

    now = time.monotonic()
    link_metrics: dict[str, dict] = {}

    for link in topology.get("links", []):
        endpoints = link.get("_raw_endpoints")  # set by gns3_client if available
        if not endpoints or len(endpoints) < 2:
            continue

        lid = link["id"]
        src_ep, tgt_ep = endpoints[0], endpoints[1]
        src_node = src_ep.get("node_id")
        src_iface = _iface_name(src_ep.get("adapter_number", 0), src_ep.get("port_number", 0))

        stats = (node_stats.get(src_node) or {}).get(src_iface)
        if not stats:
            continue

        rx_b  = stats["rx_bytes"]
        tx_b  = stats["tx_bytes"]
        rx_pk = stats["rx_packets"]
        rx_er = stats["rx_errors"] + stats["rx_dropped"]

        prev = (_prev.get(src_node) or {}).get(src_iface)
        _prev.setdefault(src_node, {})[src_iface] = (rx_b, tx_b, rx_pk, rx_er, now)

        if prev is None:
            continue

        p_rx_b, p_tx_b, p_rx_pk, p_rx_er, p_ts = prev
        dt = max(now - p_ts, 0.1)

        rx_rate_bps = (rx_b - p_rx_b) / dt
        tx_rate_bps = (tx_b - p_tx_b) / dt
        total_bps   = rx_rate_bps + tx_rate_bps
        total_mbps  = total_bps / 1_000_000

        base_bw = link.get("base_bandwidth", 100.0)
        utilization = min((total_mbps / max(base_bw, 1.0)) * 100.0, 100.0)

        dpk = max(rx_pk - p_rx_pk, 0)
        der = max(rx_er - p_rx_er, 0)
        pkt_loss = (der / dpk * 100.0) if dpk > 0 else 0.0

        link_metrics[lid] = {
            "bandwidth": base_bw,
            "utilization": round(utilization, 2),
            "packet_loss": round(min(pkt_loss, 30.0), 4),
        }

    return link_metrics
