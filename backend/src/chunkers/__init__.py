"""Document chunkers — stage 2 of the RAG ingestion pipeline (LEG-13).

Cuts text into embeddable pieces. Two shapes of input, two chunkers:
FixedSizeChunker for a parsed PDF's pages, CaseChunker for a structured case
(facts/reasoning/verdict, or law articles). Neither knows about storage or
embeddings.
"""

from chunkers.base import Chunk, Chunker
from chunkers.case_chunker import Case, CaseChunk, CaseChunker, CaseMetadata, CaseSection
from chunkers.fixed_size import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, FixedSizeChunker

__all__ = [
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_OVERLAP",
    "Case",
    "CaseChunk",
    "CaseChunker",
    "CaseMetadata",
    "CaseSection",
    "Chunk",
    "Chunker",
    "FixedSizeChunker",
]
