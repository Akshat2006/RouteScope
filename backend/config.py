"""
RouteScope — Central Configuration
Loads from environment variables or .env file.
"""
from pathlib import Path
from pydantic_settings import BaseSettings
from typing import Optional

_ENV_FILE = Path(__file__).parent / ".env"


class Settings(BaseSettings):
    # GNS3 Server
    GNS3_URL: str = "http://localhost:3080"
    GNS3_USER: str = "admin"
    GNS3_PASS: str = "admin"
    GNS3_PROJECT_ID: Optional[str] = None  # auto-discover if None

    # Database
    DATABASE_URL: str = "sqlite+aiosqlite:///./routescope.db"

    # Simulation mode (use synthetic metrics instead of live capture)
    SIMULATION_MODE: bool = True

    # Metric update interval (seconds)
    METRIC_UPDATE_INTERVAL: float = 2.0

    # Algorithm execution timeout (seconds)
    ALGORITHM_TIMEOUT: float = 30.0

    # CORS origins
    CORS_ORIGINS: list = ["http://localhost:5173", "http://localhost:3000", "http://localhost:8001"]

    # iPerf3 server (for live bandwidth measurement)
    IPERF3_SERVER: Optional[str] = None

    # Netmiko default device type
    NETMIKO_DEVICE_TYPE: str = "cisco_ios"

    # ----------------------------------------------------------------
    # Layer 2: Graph Storage — tier thresholds (spec §9.1)
    # ----------------------------------------------------------------
    # Tier 1 (NetworkX in-memory)      : node_count ≤ TIER1_MAX_NODES
    # Tier 2 (Neo4j Community)         : TIER1_MAX_NODES < node_count ≤ TIER2_MAX_NODES
    # Tier 3 (Neo4j Cluster + Kafka)   : node_count > TIER2_MAX_NODES [future]
    TIER1_MAX_NODES: int = 50_000
    TIER2_MAX_NODES: int = 500_000

    # Neo4j connection (Tier 2)
    NEO4J_URI:  str = "bolt://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASS: str = "routescope"

    # Force a specific storage tier regardless of node count (0 = auto)
    # Set to 2 to demo Neo4j backend with a small topology
    FORCE_STORAGE_TIER: int = 0

    class Config:
        env_file = str(_ENV_FILE)
        env_file_encoding = "utf-8"


settings = Settings()
