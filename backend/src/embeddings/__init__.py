"""Embedding providers — stage 3 of the RAG ingestion pipeline (LEG-13).

Turns chunk text into vectors. Knows nothing about cases, documents, or storage.
"""

from embeddings.base import EmbeddingProvider, Vector
from embeddings.offline import OfflineEmbeddingProvider

__all__ = [
    "EmbeddingProvider",
    "OfflineEmbeddingProvider",
    "Vector",
]
