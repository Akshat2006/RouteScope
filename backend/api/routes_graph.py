"""
RouteScope — Graph API Routes

GET  /api/graph           → current graph (nodes + edges + metrics)
GET  /api/graph/health    → graph health indicators
GET  /api/graph/nodes     → list all node IDs
POST /api/graph/refresh   → re-fetch topology from GNS3
"""
from fastapi import APIRouter
from ..ingestion.graph_builder import graph_builder
from ..ingestion.gns3_client import gns3_client
from ..ingestion.metric_simulator import metric_simulator
from ..engine.metrics_engine import compute_graph_health

router = APIRouter(tags=["graph"])


@router.get("/graph")
async def get_graph():
    """Return the current live graph state."""
    data = graph_builder.to_dict()
    health = compute_graph_health(graph_builder.snapshot())
    return {
        "graph": data,
        "health": health,
        "live": gns3_client.is_live,
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
    }


@router.get("/graph/health")
async def get_health():
    """Return health indicators for the current graph."""
    return compute_graph_health(graph_builder.snapshot())


@router.get("/graph/nodes")
async def get_nodes():
    """Return all node IDs (for source/destination dropdowns)."""
    g = graph_builder.to_dict()
    return {"nodes": [{"id": n["id"], "label": n["label"]} for n in g["nodes"]]}


@router.post("/graph/refresh")
async def refresh_topology():
    """Re-fetch topology from GNS3 and reinitialise graph."""
    await graph_builder.initialize()
    data = graph_builder.to_dict()

    # Broadcast updated graph via WebSocket
    from ..api.websocket import ws_manager
    from ..engine.metrics_engine import compute_graph_health
    health = compute_graph_health(graph_builder.snapshot())
    from ..graph_storage import tier_selector
    await ws_manager.broadcast({
        "type": "graph_update",
        "data": data,
        "health": health,
        "storage_tier": tier_selector.active_tier,
        "storage_backend": tier_selector.backend_name,
    })

    return {
        "success": True,
        "node_count": len(data["nodes"]),
        "edge_count": len(data["edges"]),
        "live": gns3_client.is_live,
        "storage_tier": tier_selector.active_tier,
        "storage_backend": tier_selector.backend_name,
    }


@router.post("/graph/tier")
async def switch_tier(body: dict):
    """
    Switch storage tier at runtime without restart.
    Body: {"tier": 1} or {"tier": 2}
    """
    from ..graph_storage import tier_selector
    from ..config import settings
    from ..api.websocket import ws_manager

    tier = int(body.get("tier", 1))
    if tier not in (1, 2):
        return {"success": False, "error": "tier must be 1 or 2"}

    graph = graph_builder.snapshot()

    if tier == 1:
        await tier_selector._activate_tier1(graph)
    else:
        await tier_selector._activate_tier2(graph, settings)

    data = graph_builder.to_dict()
    health = compute_graph_health(graph_builder.snapshot())
    await ws_manager.broadcast({
        "type": "graph_update",
        "data": data,
        "health": health,
        "storage_tier": tier_selector.active_tier,
        "storage_backend": tier_selector.backend_name,
    })

    return {
        "success": True,
        "active_tier": tier_selector.active_tier,
        "backend": tier_selector.backend_name,
        "node_count": graph.number_of_nodes(),
    }


@router.get("/graph/metrics")
async def get_metrics():
    """Return current per-link metrics snapshot."""
    return metric_simulator.get_all_metrics()


@router.get("/graph/collectors")
async def get_collector_status():
    """
    Show which metrics are coming from real collectors vs simulation,
    and when each collector last fired.
    """
    import time
    import shutil

    cache = metric_simulator._real_cache
    now = time.monotonic()

    links_status = {}
    for lid, entry in cache.items():
        age = round(now - entry.get("_ts", 0), 1)
        real_fields = [k for k in entry if not k.startswith("_")]
        links_status[lid] = {
            "real_fields": real_fields,
            "age_seconds": age,
            "stale": age > 30,
        }

    return {
        "gns3_live": gns3_client.is_live,
        "collectors": {
            "netmiko": {
                "available": True,
                "description": "Telnet → router console → ip -s link show",
            },
            "iperf3": {
                "available": bool(shutil.which("iperf3") or shutil.which("iperf3.exe")),
                "server_configured": bool(__import__("backend.config", fromlist=["settings"]).settings.IPERF3_SERVER),
                "description": "Real TCP throughput + UDP jitter measurement",
            },
            "scapy": {
                "available": _check_scapy(),
                "description": "ICMP traceroute → real hop latency",
            },
            "pyshark": {
                "available": bool(shutil.which("tshark") or shutil.which("tshark.exe")),
                "description": "Packet capture → real throughput (needs Wireshark)",
            },
        },
        "real_data_cache": links_status,
        "last_collect_age_seconds": round(now - metric_simulator._last_real_collect, 1),
        "collect_interval_seconds": metric_simulator.REAL_COLLECT_INTERVAL,
    }


def _check_scapy() -> bool:
    try:
        import scapy.all  # noqa: F401
        return True
    except Exception:
        return False
