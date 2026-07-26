"""Text chunking interfaces — stage 2 of the RAG ingestion pipeline (LEG-13).

Takes the page-numbered text produced by the parsers and splits it into pieces
small enough to embed. Knows nothing about cases, documents, or storage.

Mirrors the Parser pattern in parsers/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from parsers import ParsedPage


@dataclass(frozen=True)
class Chunk:
    """One piece of a document, ready to be embedded.

    sequence is 0-based and unique within a document, in reading order. It is
    what lets retrieval fetch the chunks either side of a match (LEG-14) —
    without it, a chunk cut mid-sentence cannot be repaired.

    page_number says which page the text came from, so an answer can cite it.
    """

    sequence: int
    page_number: int
    text: str


class Chunker(ABC):
    """Common interface for splitting parsed pages into embeddable chunks."""

    @abstractmethod
    def chunk(self, pages: list[ParsedPage]) -> list[Chunk]:
        """Split parsed pages into chunks, in document order.

        Returns chunks numbered from 0 with no gaps, so that sequence n+1 is
        genuinely the next piece of text after sequence n.
        """
