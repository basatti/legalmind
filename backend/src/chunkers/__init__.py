"""Text chunkers — stage 2 of the RAG ingestion pipeline (LEG-13).

Splits page-numbered text into embeddable pieces. Knows nothing about cases,
documents, or storage.
"""

from chunkers.base import Chunk, Chunker
from chunkers.fixed_size import FixedSizeChunker

__all__ = [
    "Chunk",
    "Chunker",
    "FixedSizeChunker",
]
