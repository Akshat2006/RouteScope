# backend/algorithms/__init__.py
"""
Algorithm registry — all algorithms are instantiated here.
Import ALGORITHM_REGISTRY wherever you need all algorithms.
"""
from .dijkstra import DijkstraAlgorithm
from .bellman_ford import BellmanFordAlgorithm
from .ospf_ispf import OSPFiSPFAlgorithm
from .cspf import CSPFAlgorithm
from .lfa import LFAAlgorithm
from .ecmp import ECMPAlgorithm

ALGORITHM_REGISTRY = [
    DijkstraAlgorithm(),
    BellmanFordAlgorithm(),
    OSPFiSPFAlgorithm(),
    CSPFAlgorithm(),
    LFAAlgorithm(),
    ECMPAlgorithm(),
]

__all__ = ["ALGORITHM_REGISTRY"]
