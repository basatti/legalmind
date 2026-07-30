"""Tests for the document parsers (LEG-57)."""

import pytest

from parsers import (
    ParsedPage,
    Parser,
    ParserError,
    PdfParser,
    UnsupportedFileTypeError,
    get_parser_for,
    is_supported,
)
from parsers.pdf_parser import _visual_to_logical


def _escape(text: str) -> str:
    """Escape the three characters that are special inside a PDF text string."""
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def build_pdf(pages: list[str]) -> bytes:
    """Build a minimal but valid PDF holding one line of text per page.

    Written by hand so the tests need no binary fixture files committed to the
    repo and no extra library just to produce them. Pass an empty string for a
    page to imitate a scan: a page that exists but carries no text layer.
    """
    count = len(pages)
    page_ids = [4 + 2 * i for i in range(count)]
    content_ids = [5 + 2 * i for i in range(count)]

    objects: dict[int, bytes] = {}
    kids = " ".join(f"{pid} 0 R" for pid in page_ids)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {count} >>".encode()
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"

    for index, text in enumerate(pages):
        stream = f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET".encode()
        objects[page_ids[index]] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 3 0 R >> >> "
            f"/Contents {content_ids[index]} 0 R >>"
        ).encode()
        objects[content_ids[index]] = (
            f"<< /Length {len(stream)} >>\nstream\n".encode() + stream + b"\nendstream"
        )

    out = bytearray(b"%PDF-1.4\n")
    offsets: dict[int, int] = {}
    for number in sorted(objects):
        offsets[number] = len(out)
        out += f"{number} 0 obj\n".encode() + objects[number] + b"\nendobj\n"

    xref_offset = len(out)
    total = max(objects) + 1
    out += f"xref\n0 {total}\n".encode()
    out += b"0000000000 65535 f \n"
    for number in range(1, total):
        out += f"{offsets[number]:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {total} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode()
    return bytes(out)


# ---------------------------------------------------------------------------
# PdfParser — the happy path
# ---------------------------------------------------------------------------


def test_parse_returns_one_entry_per_page() -> None:
    pdf = build_pdf(["First page text", "Second page text", "Third page text"])
    assert len(PdfParser().parse(pdf)) == 3


def test_parse_numbers_pages_starting_at_one() -> None:
    pdf = build_pdf(["First page text", "Second page text"])
    pages = PdfParser().parse(pdf)
    assert [page.page_number for page in pages] == [1, 2]


def test_parse_extracts_the_text_of_each_page() -> None:
    pdf = build_pdf(["Lease agreement clause one", "Termination clause two"])
    pages = PdfParser().parse(pdf)
    assert pages[0].text == "Lease agreement clause one"
    assert pages[1].text == "Termination clause two"


def test_parse_keeps_text_with_a_page_that_has_none() -> None:
    """A blank cover page is normal — only an entirely empty document is a failure."""
    pdf = build_pdf(["", "Real content on page two"])
    pages = PdfParser().parse(pdf)
    assert pages[0].text == ""
    assert pages[1].text == "Real content on page two"


# ---------------------------------------------------------------------------
# PdfParser — the ways a PDF ruins your day
# ---------------------------------------------------------------------------


def test_parse_rejects_a_file_that_is_not_a_pdf() -> None:
    with pytest.raises(ParserError):
        PdfParser().parse(b"This is a text file someone renamed to .pdf")


def test_parse_rejects_empty_content() -> None:
    with pytest.raises(ParserError):
        PdfParser().parse(b"")


def test_parse_rejects_a_scanned_pdf_with_no_text_layer() -> None:
    """Every page empty means images of paper — pypdf reads it happily and
    returns nothing, so the parser has to catch it explicitly."""
    pdf = build_pdf(["", "", ""])
    with pytest.raises(ParserError, match="OCR"):
        PdfParser().parse(pdf)


# ---------------------------------------------------------------------------
# Rebuilding right-to-left text from visually-ordered glyphs
# ---------------------------------------------------------------------------


def test_ligature_glyphs_are_not_split_when_reversing() -> None:
    """A ligature glyph decodes to its letters already in reading order, so
    reversing must move it as one unit. Reversing character-by-character is
    what turns المحكمة into املحكمة."""
    visual = ["ة", "م", "ك", "ح", "لم", "ا"]
    assert _visual_to_logical(visual) == "المحكمة"


def test_plain_letters_are_reversed_into_reading_order() -> None:
    assert _visual_to_logical(["د", "م", "لح", "ا"]) == "الحمد"


def test_digits_keep_their_own_left_to_right_order() -> None:
    """٣٣٦٨٣٦١٧ must not come back as ٧١٦٣٨٦٣٣ — a reversed case number is
    worse than no case number."""
    visual = ["٣", "٣", "٦", "٨", "٣", "٦", "١", "٧", " ", "م", "ق", "ر"]
    assert _visual_to_logical(visual) == "رقم ٣٣٦٨٣٦١٧"


def test_a_date_drawn_as_separate_groups_stays_one_number() -> None:
    visual = ["١", "٤", "٣", "٣", " ", "/", " ", "١", "١", " ", "/", " ", "٣", "٠"]
    assert _visual_to_logical(visual) == "١٤٣٣ / ١١ / ٣٠"


def test_a_colon_stays_with_the_arabic_label_not_the_number() -> None:
    visual = ["١", "٢", ":", " ", "م", "ق", "ر"]
    assert _visual_to_logical(visual) == "رقم :١٢"


def test_latin_only_text_is_left_alone() -> None:
    assert _visual_to_logical(list("Lease clause")) == "Lease clause"


# ---------------------------------------------------------------------------
# The interface contract
# ---------------------------------------------------------------------------


def test_parser_interface_cannot_be_used_directly() -> None:
    """Parser is a shape, not a device — Python must refuse to build one."""
    with pytest.raises(TypeError):
        Parser()  # type: ignore[abstract]


def test_parsed_page_cannot_be_modified_after_parsing() -> None:
    import dataclasses

    page = ParsedPage(page_number=1, text="original")
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.text = "tampered"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_registry_returns_a_pdf_parser_for_pdf_files() -> None:
    assert isinstance(get_parser_for("contract.pdf"), PdfParser)


def test_registry_ignores_extension_casing() -> None:
    assert isinstance(get_parser_for("SCAN.PDF"), PdfParser)


def test_registry_rejects_a_file_type_with_no_parser() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        get_parser_for("evidence_photo.png")


def test_registry_rejects_a_file_with_no_extension() -> None:
    with pytest.raises(UnsupportedFileTypeError):
        get_parser_for("README")


def test_is_supported_answers_without_raising() -> None:
    assert is_supported("contract.pdf") is True
    assert is_supported("evidence_photo.png") is False
