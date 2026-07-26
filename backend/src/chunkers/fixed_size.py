"""Fixed-size implementation of the Chunker interface."""

from chunkers.base import Chunk, Chunker
from parsers import ParsedPage


class FixedSizeChunker(Chunker):
    """Splits each page into overlapping windows of roughly equal size.

    This is the fallback chunker: it assumes nothing about the text, so it
    works on contracts, letters and messy scan output alike. Documents that
    genuinely have structure — Saudi statutes divided into مادة, numbered
    contract clauses — deserve their own Chunker that cuts on those boundaries
    instead, because a boundary a human drafter chose beats any guess.

    Chunks never span a page boundary, so each one has a single unambiguous
    page to cite. Text broken across a page break is repaired at retrieval
    time by fetching neighbouring sequence numbers, not here.
    """

    def __init__(self, chunk_size: int = 800, overlap: int = 100) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= overlap <= chunk_size // 2:
            raise ValueError("overlap must be between 0 and half of chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, pages: list[ParsedPage]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for page in pages:
            for text in self._split(page.text):
                chunks.append(Chunk(sequence=len(chunks), page_number=page.page_number, text=text))
        return chunks

    def _split(self, text: str) -> list[str]:
        """Split one page into overlapping pieces, preferring word boundaries."""
        text = text.strip()
        if not text:
            return []

        pieces: list[str] = []
        start = 0
        while start < len(text):
            end = self._find_end(text, start)
            piece = text[start:end].strip()
            if piece:
                pieces.append(piece)
            if end >= len(text):
                break
            start = self._align_forward(text, max(end - self.overlap, start + 1), end)
        return pieces

    def _find_end(self, text: str, start: int) -> int:
        """Where this piece should end, backing up to whitespace so words stay whole.

        Only backs up as far as halfway through the window. A long run with no
        spaces at all gets a hard cut rather than producing a tiny chunk.
        """
        end = start + self.chunk_size
        if end >= len(text):
            return len(text)

        candidate = end
        while candidate > start + self.chunk_size // 2:
            if text[candidate - 1].isspace():
                return candidate
            candidate -= 1
        return end

    @staticmethod
    def _align_forward(text: str, index: int, limit: int) -> int:
        """Move index forward to the start of a whole word, never past limit.

        The overlap rewind lands at an arbitrary offset, which would let a chunk
        begin mid-word — "nt's Name" instead of "Student's Name". Capped at
        limit so no text is ever skipped, even in a long run with no spaces.
        """
        while index < limit and not text[index - 1].isspace():
            index += 1
        return index
