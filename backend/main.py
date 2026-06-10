"""
RouteScope — FastAPI Application Entry Point

Startup sequence:
  1. Initialize SQLite database (create tables)
  2. Layer 1: Build NetworkX graph from GNS3 / simulated topology
  3. Layer 2: tier_selector selects backend (Tier 1 NetworkX / Tier 2 Neo4j)
             and persists the graph in the appropriate store
  4. Start metric simulator background loop (every 2s)

Routes mounted:
  /api/graph          → routes_graph
  /api/algorithms     → routes_algo
  /api/failure        → routes_failure
  /api/experiments    → routes_experiment
  /ws                 → WebSocket endpoint
  /docs               → Swagger UI (auto)
  /health             → health check
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .ingestion.graph_builder import graph_builder
from .ingestion.metric_simulator import metric_simulator
from .api.routes_graph import router as graph_router
from .api.routes_algo import router as algo_router
from .api.routes_failure import router as failure_router
from .api.routes_experiment import router as experiment_router
from .api.websocket import router as ws_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: startup → yield → shutdown."""
    logger.info("RouteScope starting up…")

    # Init DB
    await init_db()
    logger.info("Database initialised")

    # Build graph
    await graph_builder.initialize()

    # Start metric simulator background loop
    asyncio.create_task(metric_simulator.run_continuous())
    logger.info("Metric simulator started")

    yield  # ← application runs here

    # Shutdown
    metric_simulator.stop()
    from .ingestion.gns3_client import gns3_client
    from .graph_storage import tier_selector
    await gns3_client.close()
    tier_selector.close()
    logger.info("RouteScope shut down cleanly")


app = FastAPI(
    title="RouteScope API",
    description="Network routing analysis and visualization platform",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS — allow Vite dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(graph_router, prefix="/api")
app.include_router(algo_router, prefix="/api")
app.include_router(failure_router, prefix="/api")
app.include_router(experiment_router, prefix="/api")
app.include_router(ws_router)


@app.get("/health", tags=["meta"])
async def health():
    """Health check endpoint."""
    from .api.websocket import ws_manager
    from .ingestion.gns3_client import gns3_client
    from .graph_storage import tier_selector
    return {
        "status": "ok",
        "gns3_live": gns3_client.is_live,
        "simulation_mode": settings.SIMULATION_MODE,
        "ws_connections": ws_manager.connection_count,
        "graph_nodes": len(graph_builder.node_ids),
        "storage_tier": tier_selector.active_tier,
    }
