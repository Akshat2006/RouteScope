"""
RouteScope — Layer 2: Graph Storage

Exposes a single tier_selector singleton. All code above Layer 2
calls tier_selector.get_graph() and receives a NetworkX graph
regardless of which backend (NetworkX / Neo4j) is active.
"""
from .tier_selector import tier_selector

__all__ = ["tier_selector"]
