"""Fixed-size chunking, the default strategy.

Packs whole words up to a size limit, then starts the next chunk slightly
before the previous one ended. The overlap is a bet that an idea is shorter
than the overlap window, so an idea cut in half still survives whole inside
one chunk. It is only a bet — the real fix is fetching neighbouring chunks at
retrieval time, which is why Chunk carries a sequence number.

Works on words rather than raw character offsets so a chunk can never begin or
end mid-word. Runs of whitespace are collapsed as a side effect; a
paragraph-aware chunker can be added later as a second Chunker if that matters.
"""

from chunkers.base import Chunk, Chunker
from parsers.base import ParsedPage

DEFAULT_CHUNK_SIZE = 800
DEFAULT_OVERLAP = 100


class FixedSizeChunker(Chunker):
    """Cuts each page into fixed-size, overlapping, word-aligned chunks."""

    def __init__(
        self,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        if chunk_size <= 0:
            raise ValueError("chunk_size must be positive")
        if not 0 <= overlap < chunk_size:
            raise ValueError("overlap must be non-negative and smaller than chunk_size")
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, pages: list[ParsedPage]) -> list[Chunk]:
        chunks: list[Chunk] = []
        for page in pages:
            for text in self._split(page.text):
                chunks.append(Chunk(sequence=len(chunks), page_number=page.page_number, text=text))
        return chunks

    def _split(self, text: str) -> list[str]:
        """Cut one page's text into overlapping pieces."""
        words = text.split()
        if not words:
            return []

        pieces: list[str] = []
        start = 0
        while start < len(words):
            end = self._fill(words, start)
            pieces.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start = self._rewind(words, start, end)
        return pieces

    def _fill(self, words: list[str], start: int) -> int:
        """Index one past the last word that fits in a chunk starting at start."""
        end = start
        used = 0
        while end < len(words):
            addition = len(words[end]) + (1 if end > start else 0)
            if used + addition > self.chunk_size:
                break
            used += addition
            end += 1
        # A single word longer than chunk_size would fit nowhere. Emit it whole
        # and move on rather than dropping it or looping forever.
        return end if end > start else start + 1

    def _rewind(self, words: list[str], start: int, end: int) -> int:
        """Where the next chunk begins — back over whole words worth ~overlap characters.

        Never returns start itself, so every loop makes progress.
        """
        used = 0
        index = end
        while index - 1 > start:
            addition = len(words[index - 1]) + 1
            if used + addition > self.overlap:
                break
            used += addition
            index -= 1
        return index
