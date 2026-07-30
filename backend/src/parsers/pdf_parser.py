"""PDF implementation of the Parser interface, backed by pypdf.

Text is rebuilt from raw glyph codes rather than pypdf's ``extract_text()``.
That is more work, but it is the only way to read the Arabic legal PDFs this
product ingests correctly. Three defects in those files are handled here:

1. **Broken ligatures.** Arabic PDFs store glyphs in *visual* order (rightmost
   glyph first). A ligature glyph such as لم maps, via the font's ToUnicode
   table, to its two letters in *logical* order. A extractor that reverses the
   visual run character-by-character therefore also reverses the ligature's
   two letters, turning المحكمة into املحكمة. Reversing whole glyph *units*
   instead — keeping each ligature's expansion intact — reproduces the text
   exactly. This is why every off-the-shelf extractor mangles these documents
   in the same way, and why the fix belongs at the glyph level.

2. **Reversed numbers.** Digits run left-to-right even inside right-to-left
   text, so they must not be reversed along with the Arabic. Without this,
   case number ٣٣٦٨٣٦١٧ reads back as ٧١٦٣٨٦٣٣ — the single worst failure for
   a legal product, since case numbers and dates are what make a ruling
   citable.

3. **Off-page ghost text.** Some pages carry an invisible duplicate of the
   next page's body positioned outside the page box (x ≈ -442 on a page
   0..482 wide). It is not visible in a reader but every extractor picks it
   up. Fragments outside the MediaBox are dropped.

KNOWN LIMITATION — boxed metadata. The المفاتيح (keywords) and السند الشرعي
(legal basis) panels are set in a different font whose embedded ToUnicode
table is itself corrupt: 26 of its entries map different glyphs onto the same
character, and the subset font carries no ``cmap`` table to recover the truth
from. Those panels therefore come out unreliable no matter which library
reads them, and no post-processing can repair them from the text layer alone.
Recovering them needs OCR over that region of the page. The ruling body,
which is the bulk of every document, is unaffected.

KNOWN LIMITATION — tatweel (ـ, U+0640). Some documents embed this purely
typographic elongation mark directly in the text layer for line
justification; it shows up as visible noise in the output (~0.3% of
characters in one tested document). A blind strip was tried and reverted:
tatweel sometimes stands in for a genuinely dropped ligature (e.g. a missing
lam in خلال), and a fix that cannot tell the two apart risks silently turning
a real word into a different real word — worse than leaving visible noise in
place. Left unstripped until a fix can reliably distinguish the two cases.
"""

import io
import re
from typing import Any

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import ContentStream

from parsers.base import ParsedPage, Parser, ParserError

_HEX = r"<([0-9A-Fa-f]+)>"

# Digits keep left-to-right order inside right-to-left text. Latin letters are
# included so an English word inside an Arabic sentence survives too.
_LTR_CHAR = re.compile(r"[0-9A-Za-z٠-٩۰-۹]")
# A date such as ١٤٣٣/١١/٣٠ is drawn as three separately positioned groups.
# These characters keep such a number together as one left-to-right run, but
# only when digits sit on both sides — so the colon in "رقم القضية: ٣٣٦٨٣٦١٧"
# stays with the Arabic label instead of being pulled into the number.
_LTR_JOINERS = "/.,:  "
_ARABIC = re.compile(r"[؀-ۿ]")
# Glyphs whose ToUnicode entry is a replacement character carry no text.
_UNMAPPED = "�"

# A font's decoding table, and one positioned run of glyphs off the page.
_Font = dict[str, Any]
_Fragment = dict[str, Any]


def _decode_utf16be(digits: str) -> str:
    """Turn a ToUnicode target like '06440645' into its characters."""
    return "".join(chr(int(digits[i : i + 4], 16)) for i in range(0, len(digits), 4))


def _parse_tounicode(font: Any) -> dict[int, str]:
    """Build {glyph code -> unicode text} from a font's ToUnicode CMap.

    A single code can map to several characters — that is exactly how a
    ligature glyph declares which letters it stands for, and preserving that
    grouping is what makes the reversal in _visual_to_logical correct.
    """
    mapping: dict[int, str] = {}
    if "/ToUnicode" not in font:
        return mapping
    try:
        data = font["/ToUnicode"].get_data().decode("latin-1")
    except Exception:
        return mapping

    for block in re.findall(r"beginbfchar(.*?)endbfchar", data, re.S):
        for src, dst in re.findall(_HEX + r"\s*" + _HEX, block):
            mapping[int(src, 16)] = _decode_utf16be(dst)

    for block in re.findall(r"beginbfrange(.*?)endbfrange", data, re.S):
        for lo, _hi, array in re.findall(_HEX + r"\s*" + _HEX + r"\s*\[(.*?)\]", block, re.S):
            for offset, dst in enumerate(re.findall(_HEX, array)):
                mapping[int(lo, 16) + offset] = _decode_utf16be(dst)
        for lo, hi, dst in re.findall(_HEX + r"\s*" + _HEX + r"\s*" + _HEX, block):
            start, end, base = int(lo, 16), int(hi, 16), int(dst, 16)
            if end - start > 0xFFFF:
                continue
            for offset in range(end - start + 1):
                mapping.setdefault(start + offset, chr(base + offset))
    return mapping


def _page_fonts(page: Any) -> dict[str, _Font]:
    """Collect the decoding table for every font the page can use."""
    fonts: dict[str, _Font] = {}
    try:
        resources = page["/Resources"]["/Font"]
    except Exception:
        return fonts
    for name in resources:
        try:
            font = resources[name].get_object()
        except Exception:
            continue
        fonts[name] = {
            "two_byte": str(font.get("/Subtype")) == "/Type0",
            "map": _parse_tounicode(font),
        }
    return fonts


def _units_from_bytes(raw: bytes, font: _Font) -> list[str]:
    """Decode a show-text string into one entry per glyph.

    Type0 fonts address glyphs with two bytes, simple fonts with one. A font
    with no ToUnicode table is assumed to be a plain Latin one, which keeps
    ordinary English PDFs working.
    """
    mapping = font["map"]
    units = []
    if font["two_byte"]:
        for i in range(0, len(raw) - 1, 2):
            units.append(mapping.get((raw[i] << 8) | raw[i + 1], ""))
    else:
        for byte in raw:
            units.append(mapping.get(byte, chr(byte) if not mapping else ""))
    return units


def _visual_to_logical(units: list[str]) -> str:
    """Reverse a visually-ordered right-to-left run back into reading order.

    Reversal happens over glyph units, never over characters, so a ligature
    stays intact. Runs of digits and Latin are held together and keep their
    own left-to-right order.
    """
    if not any(_ARABIC.search(u) for u in units):
        return "".join(units)  # Latin text is already in reading order.

    is_ltr = [bool(len(u) == 1 and _LTR_CHAR.match(u)) for u in units]

    # Bridge separators that have a left-to-right character on both sides, so
    # the parts of one number stay a single run.
    index = 0
    while index < len(units):
        if units[index] in _LTR_JOINERS:
            end = index
            while end < len(units) and units[end] in _LTR_JOINERS:
                end += 1
            before = index > 0 and is_ltr[index - 1]
            after = end < len(units) and is_ltr[end]
            if before and after:
                for position in range(index, end):
                    is_ltr[position] = True
            index = end
        else:
            index += 1

    segments: list[list[str]] = []
    index = 0
    while index < len(units):
        if is_ltr[index]:
            start = index
            while index < len(units) and is_ltr[index]:
                index += 1
            segments.append(units[start:index])  # kept in original order
        else:
            segments.append([units[index]])
            index += 1

    segments.reverse()
    return "".join(unit for segment in segments for unit in segment)


def _extract_fragments(page: Any, reader: PdfReader) -> list[_Fragment]:
    """Pull every positioned run of text off a page, still in visual order."""
    fonts = _page_fonts(page)
    try:
        stream = ContentStream(page.get_contents(), reader)
    except Exception as exc:
        raise ParserError(f"Could not read page content stream: {exc}") from exc

    fragments: list[_Fragment] = []
    current: str | None = None
    matrix = [1.0, 0.0, 0.0, 1.0, 0.0, 0.0]
    line = list(matrix)
    leading = 0.0

    def show(items: Any) -> None:
        font = fonts.get(current) if current is not None else None
        if font is None:
            return
        units: list[str] = []
        for item in items:
            raw = getattr(item, "original_bytes", None)
            if raw is not None:
                units.extend(u for u in _units_from_bytes(raw, font) if u != _UNMAPPED)
        if any(unit.strip() for unit in units):
            fragments.append({"x": matrix[4], "y": matrix[5], "units": units})

    def newline() -> None:
        nonlocal matrix, line
        line = [*line[:4], line[4], line[5] - leading]
        matrix = list(line)

    for operands, operator in stream.operations:
        try:
            if operator == b"Tf":
                current = operands[0]
            elif operator == b"Tm":
                matrix = [float(v) for v in operands]
                line = list(matrix)
            elif operator in (b"Td", b"TD"):
                shift_x, shift_y = float(operands[0]), float(operands[1])
                if operator == b"TD":
                    leading = -shift_y
                line = [*line[:4], line[4] + shift_x, line[5] + shift_y]
                matrix = list(line)
            elif operator == b"TL":
                leading = float(operands[0])
            elif operator == b"T*":
                newline()
            elif operator == b"Tj":
                show([operands[0]])
            elif operator == b"TJ":
                show(operands[0])
            elif operator in (b"'", b'"'):
                newline()
                show([operands[-1]])
        except (TypeError, ValueError, IndexError):
            continue  # A malformed operator should not lose the whole page.
    return fragments


def _page_text(page: Any, reader: PdfReader) -> str:
    """Rebuild one page's text in reading order."""
    left, _bottom, right, _top = (float(v) for v in page.mediabox)
    fragments = [f for f in _extract_fragments(page, reader) if left - 1 <= f["x"] <= right + 1]

    rows: dict[float, list[_Fragment]] = {}
    for fragment in fragments:
        rows.setdefault(round(fragment["y"]), []).append(fragment)

    lines = []
    for y in sorted(rows, reverse=True):  # top of the page downwards
        # The whole line is assembled in visual order — left to right, exactly
        # as it appears on the page — and flipped once at the end. Reversing
        # each fragment on its own instead would scramble any number whose
        # parts are drawn as separate fragments, such as a date.
        units: list[str] = []
        for fragment in sorted(rows[y], key=lambda f: f["x"]):
            if units:
                units.append(" ")  # gaps are drawn as movement, not spaces
            units.extend(fragment["units"])
        text = re.sub(r" {2,}", " ", _visual_to_logical(units))
        # The parts of a date are drawn apart, so close the gaps back up.
        text = re.sub(r"(?<=[0-9٠-٩]) ?([/.]) ?(?=[0-9٠-٩])", r"\1", text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


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
        """Pull text from a single page, converting failures into ParserError."""
        try:
            return _page_text(reader.pages[page_number - 1], reader)
        except ParserError:
            raise
        except Exception as exc:
            raise ParserError(f"Could not extract text from page {page_number}: {exc}") from exc
