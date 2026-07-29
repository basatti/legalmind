"""Chunking interfaces.

Stage 2 of the ingestion pipeline: the text a Parser produced is cut into
pieces small enough to embed. A whole document embeds to one blurred vector
that matches every question equally badly, so the cutting is what makes
retrieval sharp.

Adding a smarter strategy later means adding a new Chunker subclass, never
editing an existing one (open/closed principle). Everything downstream depends
on the Chunker interface, so a fake chunker can stand in during tests.

Mirrors the Parser pattern in parsers/base.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from parsers.base import ParsedPage


@dataclass(frozen=True)
class Chunk:
    """One piece of a document, ready to be embedded.

    sequence is 0-based and runs across the whole document, not per page, so
    neighbouring chunks can be fetched at retrieval time — chunk 8 sits between
    chunk 7 and chunk 9 even when a page boundary falls between them.

    page_number is carried through from the ParsedPage this text came from, so
    an answer built on this chunk can cite the page a reader would turn to.
    """

    sequence: int
    page_number: int
    text: str


class Chunker(ABC):
    """Common interface for cutting parsed pages into embeddable pieces."""

    @abstractmethod
    def chunk(self, pages: list[ParsedPage]) -> list[Chunk]:
        """Cut parsed pages into chunks, in document order.

        Takes the parser's output rather than one joined string so page numbers
        survive into each chunk. Pages with no text are skipped rather than
        emitted as empty chunks.

        Returns an empty list when there is nothing to chunk. That is not an
        error here — the parser is the stage that decides whether a document
        was readable at all.
        """
