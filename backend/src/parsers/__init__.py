"""Document parsers — stage 1 of the RAG ingestion pipeline (LEG-13).

Turns uploaded document bytes into page-numbered text. Knows nothing about
cases, storage, or embeddings.
"""

from parsers.base import ParsedPage, Parser, ParserError, UnsupportedFileTypeError
from parsers.pdf_parser import PdfParser
from parsers.registry import get_parser_for, is_supported, supported_extensions

__all__ = [
    "ParsedPage",
    "Parser",
    "ParserError",
    "PdfParser",
    "UnsupportedFileTypeError",
    "get_parser_for",
    "is_supported",
    "supported_extensions",
]
