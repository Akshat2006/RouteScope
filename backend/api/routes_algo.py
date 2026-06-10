"""
RouteScope — Algorithm API Routes

GET  /api/algorithms          → list all registered algorithms
POST /api/compute             → run all algorithms for given src/dst
GET  /api/algorithms/colors   → algorithm → color mapping
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..algorithms import ALGORITHM_REGISTRY
from ..engine.algorithm_runner import run_all_algorithms
from ..ingestion.graph_builder import graph_builder

router = APIRouter(tags=["algorithms"])


class ComputeRequest(BaseModel):
    source: str
    destination: str


@router.get("/algorithms")
async def list_algorithms():
    """List all registered routing algorithms and their metadata."""
    return {
        "algorithms": [
            {"name": algo.name, "color": algo.color}
            for algo in ALGORITHM_REGISTRY
        ],
        "count": len(ALGORITHM_REGISTRY),
    }


@router.get("/algorithms/colors")
async def get_colors():
    """Return algorithm → color hex mapping for frontend."""
    return {algo.name: algo.color for algo in ALGORITHM_REGISTRY}


@router.post("/compute")
async def compute(request: ComputeRequest):
    """Run all routing algorithms on the current graph snapshot."""
    nodes = graph_builder.node_ids
    if request.source not in nodes:
        raise HTTPException(404, f"Source node '{request.source}' not found")
    if request.destination not in nodes:
        raise HTTPException(404, f"Destination node '{request.destination}' not found")
    if request.source == request.destination:
        raise HTTPException(400, "Source and destination must be different")

    graph_snap = graph_builder.snapshot()
    results = await run_all_algorithms(graph_snap, request.source, request.destination)

    # Broadcast to all WS clients
    from ..api.websocket import ws_manager
    await ws_manager.broadcast({"type": "algo_results", "data": results})

    return results
