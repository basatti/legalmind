"""Document chunkers — stage 2 of the RAG ingestion pipeline (LEG-13).

Cuts parsed pages into embeddable pieces. Knows nothing about cases, storage,
or embeddings.
"""

from chunkers.base import Chunk, Chunker
from chunkers.fixed_size import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, FixedSizeChunker

__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "Chunk",
    "Chunker",
    "FixedSizeChunker",
]
