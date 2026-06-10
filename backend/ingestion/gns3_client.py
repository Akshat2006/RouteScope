"""
RouteScope — GNS3 REST API Client

Fetches project topology (nodes + links) from GNS3.
Falls back to a realistic simulated topology if GNS3 is unreachable.
"""
import asyncio
import logging
from typing import Optional

import httpx

from ..config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default simulated topology (10-node enterprise-like network)
# Used when GNS3 is unavailable or SIMULATION_MODE=True
# ---------------------------------------------------------------------------
DEFAULT_TOPOLOGY = {
    "nodes": [
        {"id": "R1",  "label": "R1-Core",   "x": 400, "y": 200, "type": "router"},
        {"id": "R2",  "label": "R2-Dist",   "x": 200, "y": 350, "type": "router"},
        {"id": "R3",  "label": "R3-Dist",   "x": 400, "y": 400, "type": "router"},
        {"id": "R4",  "label": "R4-Dist",   "x": 600, "y": 350, "type": "router"},
        {"id": "R5",  "label": "R5-Access", "x": 100, "y": 500, "type": "router"},
        {"id": "R6",  "label": "R6-Access", "x": 280, "y": 540, "type": "router"},
        {"id": "R7",  "label": "R7-Access", "x": 460, "y": 540, "type": "router"},
        {"id": "R8",  "label": "R8-Access", "x": 640, "y": 500, "type": "router"},
        {"id": "R9",  "label": "R9-Edge",   "x": 300, "y": 660, "type": "router"},
        {"id": "R10", "label": "R10-Edge",  "x": 500, "y": 660, "type": "router"},
    ],
    "links": [
        # Core ↔ Distribution
        {"id": "L1",  "source": "R1", "target": "R2", "base_latency": 2,  "base_bandwidth": 1000},
        {"id": "L2",  "source": "R1", "target": "R3", "base_latency": 1,  "base_bandwidth": 1000},
        {"id": "L3",  "source": "R1", "target": "R4", "base_latency": 2,  "base_bandwidth": 1000},
        # Distribution ↔ Access
        {"id": "L4",  "source": "R2", "target": "R5", "base_latency": 5,  "base_bandwidth": 100},
        {"id": "L5",  "source": "R2", "target": "R6", "base_latency": 4,  "base_bandwidth": 100},
        {"id": "L6",  "source": "R3", "target": "R6", "base_latency": 3,  "base_bandwidth": 100},
        {"id": "L7",  "source": "R3", "target": "R7", "base_latency": 3,  "base_bandwidth": 100},
        {"id": "L8",  "source": "R4", "target": "R7", "base_latency": 5,  "base_bandwidth": 100},
        {"id": "L9",  "source": "R4", "target": "R8", "base_latency": 4,  "base_bandwidth": 100},
        # Cross-links (redundancy)
        {"id": "L10", "source": "R5", "target": "R8", "base_latency": 8,  "base_bandwidth": 50},
        {"id": "L11", "source": "R6", "target": "R9", "base_latency": 6,  "base_bandwidth": 50},
        {"id": "L12", "source": "R7", "target": "R9", "base_latency": 6,  "base_bandwidth": 50},
        {"id": "L13", "source": "R7", "target": "R10","base_latency": 7,  "base_bandwidth": 50},
        {"id": "L14", "source": "R8", "target": "R10","base_latency": 5,  "base_bandwidth": 50},
        {"id": "L15", "source": "R9", "target": "R10","base_latency": 3,  "base_bandwidth": 100},
        # Distribution ↔ Distribution (diagonal links)
        {"id": "L16", "source": "R2", "target": "R3", "base_latency": 3,  "base_bandwidth": 500},
        {"id": "L17", "source": "R3", "target": "R4", "base_latency": 3,  "base_bandwidth": 500},
    ],
}


class GNS3Client:
    """
    Fetches live topology from GNS3.
    Falls back to DEFAULT_TOPOLOGY on connection failure.
    """

    def __init__(self):
        self._project_id: Optional[str] = settings.GNS3_PROJECT_ID
        self._base_url = settings.GNS3_URL.rstrip("/")
        self._auth = (settings.GNS3_USER, settings.GNS3_PASS)
        self._client: Optional[httpx.AsyncClient] = None
        self.is_live: bool = False

    async def _ensure_client(self):
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                auth=self._auth,
                timeout=5.0,
                headers={"Content-Type": "application/json"},
            )

    async def _discover_project(self) -> Optional[str]:
        """Pick the first active GNS3 project."""
        try:
            await self._ensure_client()
            r = await self._client.get(f"{self._base_url}/v2/projects")
            r.raise_for_status()
            projects = r.json()
            active = [p for p in projects if p.get("status") == "opened"]
            if active:
                return active[0]["project_id"]
            if projects:
                return projects[0]["project_id"]
        except Exception as exc:
            logger.warning("GNS3 project discovery failed: %s", exc)
        return None

    def reset_project(self) -> None:
        """Clear cached project ID so the next fetch re-discovers the open project."""
        self._project_id = settings.GNS3_PROJECT_ID  # restore env override or None

    async def fetch_topology(self) -> dict:
        """
        Return topology dict: {nodes, links}.
        Tries GNS3 first; falls back to simulation on any error.
        Always re-discovers the currently open project (no stale ID caching).
        """
        if settings.SIMULATION_MODE:
            self.is_live = False
            return DEFAULT_TOPOLOGY

        try:
            await self._ensure_client()

            # Always re-discover so switching projects in GNS3 is picked up immediately
            self._project_id = await self._discover_project()

            if not self._project_id:
                raise RuntimeError("No GNS3 project found")

            nodes_r = await self._client.get(
                f"{self._base_url}/v2/projects/{self._project_id}/nodes"
            )
            nodes_r.raise_for_status()

            links_r = await self._client.get(
                f"{self._base_url}/v2/projects/{self._project_id}/links"
            )
            links_r.raise_for_status()

            raw_nodes = nodes_r.json()
            raw_links = links_r.json()

            nodes = [
                {
                    "id": n["node_id"],
                    "label": n.get("name", n["node_id"]),
                    "x": n.get("x", 0),
                    "y": n.get("y", 0),
                    "type": n.get("node_type", "router"),
                }
                for n in raw_nodes
            ]

            # Build a node-id lookup
            node_ids = {n["id"] for n in nodes}
            links = []
            for i, lnk in enumerate(raw_links):
                endpoints = lnk.get("nodes", [])
                if len(endpoints) >= 2:
                    src = endpoints[0]["node_id"]
                    tgt = endpoints[1]["node_id"]
                    if src in node_ids and tgt in node_ids:
                        links.append(
                            {
                                "id": lnk.get("link_id", f"L{i}"),
                                "source": src,
                                "target": tgt,
                                "base_latency": 5,
                                "base_bandwidth": 100,
                                # kept for netmiko_collector interface mapping
                                "_raw_endpoints": endpoints,
                            }
                        )

            self.is_live = True
            logger.info(
                "GNS3 topology loaded: %d nodes, %d links", len(nodes), len(links)
            )
            return {"nodes": nodes, "links": links}

        except Exception as exc:
            logger.warning("GNS3 unreachable (%s) — using simulated topology", exc)
            self.is_live = False
            return DEFAULT_TOPOLOGY

    async def close(self):
        if self._client and not self._client.is_closed:
            await self._client.aclose()


# Singleton
gns3_client = GNS3Client()
