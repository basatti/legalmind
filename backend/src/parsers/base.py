"""Document parsing interfaces.

Supporting a new file type means adding a new Parser subclass — never editing
an existing one (open/closed principle). Everything downstream in the ingestion
pipeline depends on the Parser interface, never on a concrete implementation,
so a fake parser can stand in during tests.

Mirrors the StorageBackend pattern in foundation/storage.py.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass


class ParserError(Exception):
    """Raised when a document cannot be turned into usable text."""


class UnsupportedFileTypeError(ParserError):
    """Raised when no parser is registered for a file's extension."""


@dataclass(frozen=True)
class ParsedPage:
    """One page of extracted text.

    page_number is 1-based so it matches how a reader counts pages — it is
    carried through chunking and embedding so that an answer can later cite
    the page it came from.
    """

    page_number: int
    text: str


class Parser(ABC):
    """Common interface for turning raw document bytes into text."""

    @abstractmethod
    def parse(self, content: bytes) -> list[ParsedPage]:
        """Extract text from document bytes, one entry per page.

        Takes bytes rather than a path so the parser works the same whether the
        file came from local disk, object storage, or an in-memory test fixture.

        Raises ParserError if the document cannot be read, or if it contains no
        extractable text at all.
        """
