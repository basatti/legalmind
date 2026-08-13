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


def content_matches_extension(filename: str, content: bytes) -> bool:
    """Return True if these bytes look like the type the filename claims to be.

    A name and its contents are unrelated: renaming a file changes nothing
    inside it, and the extension check above reads only the name. Without this,
    anything renamed to `.pdf` was accepted, stored, queued, and then failed in
    the background worker hours later -- where the person who uploaded it, and
    could have fixed it, never saw the result.

    Only the opening signature is checked, which is a genuine limit worth being
    clear about: a truncated or corrupt PDF still begins with `%PDF-` and still
    passes here. This catches the file that was never a PDF at all. Files that
    are the right type but unreadable for some other reason fail in the worker,
    and reporting *those* is a separate piece of work.
    """
    parser = _PARSERS_BY_EXTENSION.get(os.path.splitext(filename)[1].lower())

    if parser is None:
        return False

    if not parser.MAGIC_BYTES:
        return True

    return content.startswith(parser.MAGIC_BYTES)


def supported_extensions() -> list[str]:
    """Every extension this registry can parse, for callers that have to say so.

    Exists so a rejection message can name what *is* accepted without keeping a
    second copy of the list — the copy would be the thing that goes stale.
    """
    return sorted(_PARSERS_BY_EXTENSION)
