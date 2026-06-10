"""
RouteScope — WebSocket Manager & Router

Manages all active WebSocket connections and provides broadcast capability.
Endpoint: GET /ws
"""
import json
import logging
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)

router = APIRouter()


class WebSocketManager:
    """Tracks all connected clients and broadcasts JSON messages."""

    def __init__(self):
        self._connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.append(ws)
        logger.info("WS client connected. Total: %d", len(self._connections))

    def disconnect(self, ws: WebSocket):
        if ws in self._connections:
            self._connections.remove(ws)
        logger.info("WS client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, message: Any):
        """Send a JSON message to all connected clients."""
        if not self._connections:
            return
        payload = json.dumps(message, default=str)
        dead = []
        for ws in self._connections:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_to(self, ws: WebSocket, message: Any):
        """Send a JSON message to a single client."""
        try:
            await ws.send_text(json.dumps(message, default=str))
        except Exception as exc:
            logger.warning("Failed to send WS message: %s", exc)
            self.disconnect(ws)

    @property
    def connection_count(self) -> int:
        return len(self._connections)


# Singleton — imported by metric_simulator, failure_injector, etc.
ws_manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """
    WebSocket endpoint.

    Server → Client messages:
      {"type": "graph_update",  "data": {...}}
      {"type": "metric_update", "data": [...]}
      {"type": "algo_results",  "data": {...}}
      {"type": "failure_event", "data": {...}}

    Client → Server messages (via WS for low-latency):
      {"type": "compute",  "source": "R1", "destination": "R5"}
      {"type": "ping"}
    """
    from ..ingestion.graph_builder import graph_builder
    from ..engine.algorithm_runner import run_all_algorithms_for_nodes
    from ..engine.metrics_engine import compute_graph_health

    await ws_manager.connect(ws)

    from ..graph_storage import tier_selector
    # Send initial graph state to newly connected client
    graph_data = graph_builder.to_dict()
    health = compute_graph_health(graph_builder.snapshot())
    await ws_manager.send_to(ws, {
        "type": "graph_update",
        "data": graph_data,
        "health": health,
        "storage_tier": tier_selector.active_tier,
        "storage_backend": tier_selector.backend_name,
    })

    try:
        while True:
            raw = await ws.receive_text()
            msg = json.loads(raw)
            msg_type = msg.get("type")

            if msg_type == "ping":
                await ws_manager.send_to(ws, {"type": "pong"})

            elif msg_type == "compute":
                source = msg.get("source")
                destination = msg.get("destination")
                if source and destination:
                    # Layer 2: tier_selector.get_graph() picks the right backend
                    results = await run_all_algorithms_for_nodes(source, destination)
                    await ws_manager.send_to(ws, {
                        "type": "algo_results",
                        "data": results,
                    })

            elif msg_type == "get_graph":
                graph_data = graph_builder.to_dict()
                health = compute_graph_health(graph_builder.snapshot())
                await ws_manager.send_to(ws, {
                    "type": "graph_update",
                    "data": graph_data,
                    "health": health,
                })

    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        ws_manager.disconnect(ws)
