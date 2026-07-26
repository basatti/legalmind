"""PDF implementation of the Parser interface, backed by pypdf."""

import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from parsers.base import ParsedPage, Parser, ParserError


def _normalise(text: str) -> str:
    """Tidy raw extracted text.

    PDF extraction leaves trailing spaces and long runs of blank lines. Those
    are stripped, but single blank lines are kept because they usually mark a
    real paragraph break, which the chunker will want later.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


class PdfParser(Parser):
    """Extracts text from PDF bytes.

    Two failure modes are worth knowing about:

    * Encrypted PDFs. Many are "encrypted" only to restrict printing and open
      fine with an empty password, so that is tried before giving up.
    * Scanned PDFs. These are photographs of paper with no text layer. pypdf
      reads them without error and returns nothing at all, so an empty result
      is treated as a failure rather than passing an empty document down the
      pipeline. Handling those needs OCR, which is out of scope here.
    """

    def parse(self, content: bytes) -> list[ParsedPage]:
        try:
            reader = PdfReader(io.BytesIO(content))
        except (PdfReadError, OSError, ValueError) as exc:
            raise ParserError(f"Could not read PDF: {exc}") from exc

        if reader.is_encrypted and not self._try_decrypt(reader):
            raise ParserError("PDF is password-protected and cannot be parsed")

        pages = [
            ParsedPage(page_number=number, text=_normalise(self._extract(reader, number)))
            for number in range(1, len(reader.pages) + 1)
        ]

        if not pages:
            raise ParserError("PDF contains no pages")

        if all(not page.text for page in pages):
            raise ParserError("PDF contains no extractable text — it may be a scan requiring OCR")

        return pages

    @staticmethod
    def _try_decrypt(reader: PdfReader) -> bool:
        """Attempt to open an encrypted PDF with an empty password."""
        try:
            return bool(reader.decrypt(""))
        except (PdfReadError, NotImplementedError):
            return False

    @staticmethod
    def _extract(reader: PdfReader, page_number: int) -> str:
        """Pull text from a single page, converting pypdf failures into ParserError."""
        try:
            return reader.pages[page_number - 1].extract_text() or ""
        except Exception as exc:
            raise ParserError(f"Could not extract text from page {page_number}: {exc}") from exc
