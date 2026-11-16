"""
In-memory vector similarity index.
Supports Cosine Similarity and Euclidean Distance with Top-K search.
Zero external dependencies required.
"""

import heapq
import json
import math
from typing import Any, Dict, List, Optional, Tuple


class VectorIndex:
    """Manages an in-memory collection of vectors for similarity search."""

    def __init__(self, name: str, dimension: Optional[int] = None) -> None:
        self.name = name
        self.dimension = dimension
        self.vectors: Dict[str, List[float]] = {}
        self.norms: Dict[str, float] = {}
        self.metadata: Dict[str, Dict[str, Any]] = {}

    def add(
        self,
        vector_id: str,
        vector: List[float],
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        if self.dimension is None:
            self.dimension = len(vector)
        elif len(vector) != self.dimension:
            raise ValueError(
                f"Vector dimension mismatch: expected {self.dimension}, got {len(vector)}"
            )

        norm = math.sqrt(sum(x * x for x in vector))
        self.vectors[vector_id] = vector
        self.norms[vector_id] = norm
        if meta:
            self.metadata[vector_id] = meta
        elif vector_id in self.metadata:
            del self.metadata[vector_id]

    def delete(self, vector_id: str) -> bool:
        if vector_id in self.vectors:
            del self.vectors[vector_id]
            del self.norms[vector_id]
            self.metadata.pop(vector_id, None)
            return True
        return False

    def search(
        self,
        query: List[float],
        top_k: int = 10,
        metric: str = "cosine",
    ) -> List[Dict[str, Any]]:
        """
        Search for top_k nearest neighbors.
        For 'cosine', returns highest similarity first (1.0 = identical).
        For 'euclidean', returns lowest distance first (0.0 = identical).
        """
        if self.dimension and len(query) != self.dimension:
            raise ValueError(
                f"Query dimension mismatch: expected {self.dimension}, got {len(query)}"
            )

        if not self.vectors:
            return []

        metric = metric.lower()
        results: List[Tuple[float, str]] = []

        if metric == "cosine":
            query_norm = math.sqrt(sum(x * x for x in query))
            if query_norm == 0:
                raise ValueError("Query vector has zero magnitude")

            for vid, vec in self.vectors.items():
                v_norm = self.norms[vid]
                if v_norm == 0:
                    similarity = 0.0
                else:
                    dot_product = sum(q * v for q, v in zip(query, vec))
                    similarity = dot_product / (query_norm * v_norm)
                results.append((similarity, vid))

            # Sort descending for cosine similarity
            results.sort(key=lambda item: item[0], reverse=True)

        elif metric == "euclidean":
            for vid, vec in self.vectors.items():
                dist = math.sqrt(sum((q - v) ** 2 for q, v in zip(query, vec)))
                results.append((dist, vid))

            # Sort ascending for Euclidean distance
            results.sort(key=lambda item: item[0])

        else:
            raise ValueError(f"Unknown metric '{metric}', expected 'cosine' or 'euclidean'")

        top_results = results[:top_k]
        output = []
        for score, vid in top_results:
            item = {
                "id": vid,
                "score": round(score, 6),
                "metric": metric,
                "metadata": self.metadata.get(vid, {}),
            }
            output.append(item)

        return output

    def info(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "dimension": self.dimension or 0,
            "count": len(self.vectors),
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "dimension": self.dimension,
            "items": [
                {
                    "id": vid,
                    "vector": self.vectors[vid],
                    "metadata": self.metadata.get(vid),
                }
                for vid in self.vectors
            ],
        }


class VectorManager:
    """Manages multiple vector indexes."""

    def __init__(self) -> None:
        self.indexes: Dict[str, VectorIndex] = {}

    def get_or_create(self, name: str, dimension: Optional[int] = None) -> VectorIndex:
        if name not in self.indexes:
            self.indexes[name] = VectorIndex(name, dimension)
        return self.indexes[name]

    def get(self, name: str) -> Optional[VectorIndex]:
        return self.indexes.get(name)

    def delete_index(self, name: str) -> bool:
        if name in self.indexes:
            del self.indexes[name]
            return True
        return False

    def list_indexes(self) -> List[Dict[str, Any]]:
        return [idx.info() for idx in self.indexes.values()]

    def count(self) -> int:
        return sum(len(idx.vectors) for idx in self.indexes.values())
