"""
RouteScope — Failure Injection API Routes

POST   /api/failure/inject      → inject a failure event
DELETE /api/failure/clear       → restore all topology
GET    /api/failure/active       → list active failures
POST   /api/congestion/set      → set artificial congestion on a link
DELETE /api/congestion/clear    → clear congestion on all links
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional

from ..engine.failure_injector import (
    inject_failure, clear_failures, get_active_failures, FailureType
)
from ..ingestion.graph_builder import graph_builder
from ..engine.algorithm_runner import run_all_algorithms

router = APIRouter(tags=["failures"])


class FailureElement(BaseModel):
    source: Optional[str] = None
    target: Optional[str] = None
    node: Optional[str] = None
    link_id: Optional[str] = None


class FailureRequest(BaseModel):
    type: FailureType
    elements: list[FailureElement]
    description: str = ""
    congestion_pct: float = 80.0
    # Optional: auto-recompute after injection
    recompute_source: Optional[str] = None
    recompute_destination: Optional[str] = None


class CongestionRequest(BaseModel):
    link_id: str
    congestion_pct: float = 80.0


@router.post("/failure/inject")
async def inject(request: FailureRequest):
    """Inject a failure event and optionally recompute all algorithms."""
    event = {
        "type": request.type,
        "elements": [e.model_dump() for e in request.elements],
        "description": request.description,
        "congestion_pct": request.congestion_pct,
    }

    result = await inject_failure(event)

    # Broadcast failure event to all WS clients
    from ..api.websocket import ws_manager
    from ..ingestion.graph_builder import graph_builder
    from ..engine.metrics_engine import compute_graph_health

    graph_data = graph_builder.to_dict()
    health = compute_graph_health(graph_builder.snapshot())

    await ws_manager.broadcast({
        "type": "failure_event",
        "data": {
            **result,
            "graph": graph_data,
            "health": health,
        },
    })

    # Auto-recompute if src/dst provided
    algo_results = None
    if request.recompute_source and request.recompute_destination:
        graph_snap = graph_builder.snapshot()
        algo_results = await run_all_algorithms(
            graph_snap,
            request.recompute_source,
            request.recompute_destination,
        )
        await ws_manager.broadcast({"type": "algo_results", "data": algo_results})

    return {**result, "algo_results": algo_results}


@router.delete("/failure/clear")
async def clear():
    """Restore full topology."""
    result = await clear_failures()

    from ..api.websocket import ws_manager
    from ..engine.metrics_engine import compute_graph_health

    graph_data = graph_builder.to_dict()
    health = compute_graph_health(graph_builder.snapshot())
    await ws_manager.broadcast({
        "type": "graph_update",
        "data": graph_data,
        "health": health,
    })

    return result


@router.get("/failure/active")
async def active_failures():
    """Return list of currently active failure events."""
    return {"failures": get_active_failures(), "count": len(get_active_failures())}


@router.post("/congestion/set")
async def set_congestion(request: CongestionRequest):
    """Set artificial congestion on a specific link."""
    from ..ingestion.metric_simulator import metric_simulator
    metric_simulator.set_congestion(request.link_id, request.congestion_pct)
    return {
        "success": True,
        "link_id": request.link_id,
        "congestion_pct": request.congestion_pct,
    }


@router.delete("/congestion/clear")
async def clear_congestion():
    """Clear congestion on all links."""
    from ..ingestion.metric_simulator import metric_simulator
    from ..ingestion.graph_builder import graph_builder
    for lnk in graph_builder._raw_topology.get("links", []):
        metric_simulator.set_congestion(lnk["id"], 0)
    return {"success": True}
