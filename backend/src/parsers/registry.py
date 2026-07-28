"""Maps file extensions to the parser that handles them.

This is the one place that knows which concrete parsers exist. Callers ask for
a parser by filename and get back something satisfying the Parser interface,
without naming PdfParser (or any future DocxParser) themselves.
"""

import os

from parsers.base import Parser, UnsupportedFileTypeError
from parsers.pdf_parser import PdfParser

# Parsers are stateless, so one shared instance per type is enough.
_PARSERS_BY_EXTENSION: dict[str, Parser] = {
    ".pdf": PdfParser(),
}


def get_parser_for(filename: str) -> Parser:
    """Return the parser registered for this filename's extension.

    Raises UnsupportedFileTypeError when nothing can handle it.
    """
    extension = os.path.splitext(filename)[1].lower()
    parser = _PARSERS_BY_EXTENSION.get(extension)
    if parser is None:
        raise UnsupportedFileTypeError(f"No parser available for '{extension}' files")
    return parser


def is_supported(filename: str) -> bool:
    """Return True if this file can be parsed — use to skip un-ingestable uploads."""
    return os.path.splitext(filename)[1].lower() in _PARSERS_BY_EXTENSION
