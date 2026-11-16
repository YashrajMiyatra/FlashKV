"""
FlashKV: High-performance, Redis-compatible in-memory database with real-time Vector Search and Web UI.
"""

__version__ = "1.0.0"

from .server import FlashKVServer
from .store import DataStore
from .vector import VectorIndex, VectorManager
from .aof import AOFManager

__all__ = ["FlashKVServer", "DataStore", "VectorIndex", "VectorManager", "AOFManager"]
