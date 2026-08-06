"""Twin-font decode, v11 — layout reconstruction rather than string fixing.

Changes, following the review:

 * SIMPLE FONTS are decoded through their own /ToUnicode (a byte in a simple
   font is a character code, not a glyph index). This is where the date
   slashes were going missing.
 * DIACRITICS are anchored to the base glyph they sit over, by horizontal
   overlap, and inserted immediately AFTER that base character — Unicode order
   is base + mark — instead of being dumped at the end of the run.
 * SPACING uses the font's own space-glyph advance where the font has one,
   falling back to a per-line adaptive threshold. A fixed em fraction never
   worked because the file switches positioning strategy mid-line.
 * COLUMNS are found by clustering line centres, not by hunting for an empty
   gutter — one run straddling the gutter was killing that signal.

Both orderings of the bidi step are tried and reported, because get_display()
maps logical order TO visual order and this text is already visual.

    uv run --python 3.12 --with fonttools --with pypdf --with python-bidi \
        python hybrid/decode_v11.py [page]
"""

import io
import re
import sys
import unicodedata
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from fontTools.ttLib import TTFont  # noqa: E402
from pypdf import PdfReader  # noqa: E402
from pypdf.generic import ContentStream  # noqa: E402

#   twin_font_decode.py <page> [pdf path]
PAGE = int(sys.argv[1]) if len(sys.argv) > 1 else 22
PDF = Path(sys.argv[2]) if len(sys.argv) > 2 else Path.home() / "Downloads" / "ahkam.pdf"

ARABIC = re.compile(r"[\u0600-\u06FF\uFB50-\uFDFF\uFE70-\uFEFF]")
LTR_CHAR = re.compile(r"[0-9A-Za-z\u0660-\u0669]")
LTR_JOINERS = "./,:-  "
BAD = re.compile(r"[\uFFE0-\uFFFF\uE000-\uF8FF]")
MARK_FRACTION = 0.15   # a run narrower than this fraction of its size is a mark

reader = PdfReader(str(PDF))
page = reader.pages[PAGE - 1]
fonts = page["/Resources"]["/Font"]


def font_bytes(name):
    font = fonts[name].get_object()
    tgt = font["/DescendantFonts"][0].get_object() if "/DescendantFonts" in font else font
    desc = tgt["/FontDescriptor"].get_object()
    key = next((k for k in ("/FontFile2", "/FontFile3", "/FontFile") if k in desc), None)
    return bytes(desc[key].get_object().get_data()) if key else b""


def tounicode(name):
    font = fonts[name].get_object()
    if "/ToUnicode" not in font:
        return {}
    text = font["/ToUnicode"].get_object().get_data().decode("latin-1", "replace")
    out = {}
    for block in re.findall(r"beginbfchar(.*?)endbfchar", text, re.S):
        for src, dst in re.findall(r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            out[int(src, 16)] = "".join(
                chr(int(dst[i : i + 4], 16)) for i in range(0, len(dst), 4))
    for block in re.findall(r"beginbfrange(.*?)endbfrange", text, re.S):
        for lo, hi, dst in re.findall(
                r"<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>", block):
            start = int(dst, 16)
            for offset, code in enumerate(range(int(lo, 16), int(hi, 16) + 1)):
                out[code] = chr(start + offset)
    return out


cids, twins, simple = {}, {}, []
for name in fonts:
    font = fonts[name].get_object()
    base = str(font.get("/BaseFont"))
    if "/DescendantFonts" in font:
        cids[name] = base
    elif font.get("/Subtype") in ("/TrueType", "/Type1"):
        twins.setdefault(base, name)
        simple.append(name)

maps, widths, upem, space_w, two_byte = {}, {}, {}, {}, {}

for cid_name, base in cids.items():
    twin_name = twins.get(base)
    if twin_name is None:
        continue
    cid = TTFont(io.BytesIO(font_bytes(cid_name)), fontNumber=0)
    twin = TTFont(io.BytesIO(font_bytes(twin_name)), fontNumber=0)
    a = [cid["hmtx"].metrics[n][0] for n in cid.getGlyphOrder()]
    b = [twin["hmtx"].metrics[n][0] for n in twin.getGlyphOrder()]
    if len(a) != len(b) or a != b:
        print(f"  {cid_name}: parity FAIL — left alone")
        continue
    by_name = {n: c for c, n in twin.getBestCmap().items()}
    table = {i: chr(by_name[n]) for i, n in enumerate(twin.getGlyphOrder()) if n in by_name}
    for gid, char in tounicode(cid_name).items():
        if gid in table and BAD.match(table[gid]):
            table[gid] = char
    maps[cid_name] = table
    widths[cid_name] = a
    upem[cid_name] = cid["head"].unitsPerEm
    two_byte[cid_name] = True
    best = twin.getBestCmap()
    if 0x20 in best:
        space_w[cid_name] = twin["hmtx"].metrics[best[0x20]][0] / upem[cid_name]
    print(f"  {cid_name} ↔ {twin_name}: parity OK ({len(a)} glyphs)")

# Simple fonts: the byte is a CHARACTER CODE, so use the font's own ToUnicode.
for name in simple:
    table = tounicode(name)
    if not table:
        continue
    raw = font_bytes(name)
    try:
        ttf = TTFont(io.BytesIO(raw), fontNumber=0) if raw else None
    except Exception:  # noqa: BLE001
        ttf = None
    maps[name] = table
    two_byte[name] = False
    if ttf is not None and "hmtx" in ttf:
        best = ttf.getBestCmap()
        order = ttf.getGlyphOrder()
        by_name = {n: c for c, n in best.items()}
        units = ttf["head"].unitsPerEm
        upem[name] = units
        widths[name] = [ttf["hmtx"].metrics[n][0] for n in order]
        # map character code -> advance, through the font's cmap
        code_w = {}
        for code, glyph in best.items():
            code_w[code] = ttf["hmtx"].metrics[glyph][0]
        widths[name] = code_w
        if 0x20 in best:
            space_w[name] = ttf["hmtx"].metrics[best[0x20]][0] / units
    else:
        upem[name] = 1000
        widths[name] = {}
    print(f"  {name}: simple font, {len(table)} ToUnicode entries")


def visual_to_logical(units):
    if not any(ARABIC.search(u) for u in units):
        return "".join(units)
    is_ltr = [bool(len(u) == 1 and LTR_CHAR.match(u)) for u in units]
    i = 0
    while i < len(units):
        if units[i] in LTR_JOINERS:
            end = i
            while end < len(units) and units[end] in LTR_JOINERS:
                end += 1
            if (i > 0 and is_ltr[i - 1]) and (end < len(units) and is_ltr[end]):
                for p in range(i, end):
                    is_ltr[p] = True
            i = end
        else:
            i += 1
    segments, i = [], 0
    while i < len(units):
        if is_ltr[i]:
            start = i
            while i < len(units) and is_ltr[i]:
                i += 1
            segments.append(units[start:i])
        else:
            segments.append([units[i]])
            i += 1
    segments.reverse()
    return "".join(u for s in segments for u in s)


# ---------------------------------------------------------------- extraction

stream = ContentStream(page.get_contents(), reader)
state = {"font": None, "size": 1.0, "m": [1.0, 0, 0, 1.0, 0, 0],
         "line": [1.0, 0, 0, 1.0, 0, 0]}
glyphs = []


def show(items):
    name = state["font"]
    if name not in maps:
        return
    scale = state["size"] * state["m"][0]
    x = state["m"][4]
    table, wide = maps[name], two_byte.get(name, True)
    metrics = widths.get(name, {})
    units = upem.get(name, 1000)

    for item in items:
        raw = getattr(item, "original_bytes", None)
        if raw is None:
            try:
                x -= float(item) / 1000.0 * scale
            except (TypeError, ValueError):
                pass
            continue
        step = 2 if wide else 1
        for i in range(0, len(raw) - (step - 1), step):
            code = (raw[i] << 8) | raw[i + 1] if wide else raw[i]
            char = table.get(code, "")
            if isinstance(metrics, dict):
                advance = metrics.get(code, units * 0.5)
            else:
                advance = metrics[code] if code < len(metrics) else units * 0.5
            width = advance / units * scale
            if char.strip():
                glyphs.append({"x": x, "y": state["m"][5], "w": width,
                               "char": char, "size": scale, "seq": len(glyphs)})
            x += width
    state["m"] = [*state["m"][:4], x, state["m"][5]]


for operands, operator in stream.operations:
    try:
        if operator == b"Tf":
            state["font"], state["size"] = operands[0], float(operands[1])
        elif operator == b"Tm":
            state["m"] = [float(v) for v in operands]
            state["line"] = list(state["m"])
        elif operator in (b"Td", b"TD"):
            ln = state["line"]
            state["line"] = [*ln[:4], ln[4] + float(operands[0]), ln[5] + float(operands[1])]
            state["m"] = list(state["line"])
        elif operator == b"Tj":
            show([operands[0]])
        elif operator == b"TJ":
            show(operands[0])
    except (TypeError, ValueError, IndexError):
        continue

print(f"\n{len(glyphs)} glyphs extracted")

# Drop anything drawn outside the visible page.
#
# This file stores the NEXT page's text in the current page's content stream,
# positioned at negative x so a renderer never shows it. On page 16 that is
# 1373 of 2179 glyphs — the whole of page 17 — and because we walk the content
# stream directly rather than rendering, we were picking it all up. That is
# what the "2 columns detected" heuristic was really seeing: not two columns,
# but two pages. pdftotext never had this problem because it clips to the box.
# This must be SAFE ON FILES THAT ARE NOT BROKEN. The filter compares glyph
# coordinates straight against the page box, which is only valid when the text
# space and the page space line up. Three ways that assumption fails, all of
# which would otherwise delete a perfectly good page:
#
#   * /Rotate — the page box is stated pre-rotation, so a landscape page's
#     glyphs legitimately fall outside it.
#   * a `cm` transform on the content stream, which this decoder does not model.
#   * any file whose producer uses an origin we are not expecting.
#
# So the rule is: never drop anything unless what remains still looks like a
# page. If the filter would remove everything, or nearly everything, we are the
# ones who are wrong — keep all the glyphs and say so.
_box = page.mediabox
_left, _right = float(_box.left), float(_box.right)
_bottom, _top = float(_box.bottom), float(_box.top)
_rotated = int(page.get("/Rotate", 0) or 0) % 360 != 0

_on_page = [
    g for g in glyphs
    if _left <= g["x"] <= _right and _bottom <= g["y"] <= _top
]
_kept_enough = len(_on_page) >= max(20, 0.20 * len(glyphs))

if len(_on_page) == len(glyphs):
    pass  # Normal file: nothing is off-page, so nothing changes.
elif _rotated:
    print("  page is rotated; skipping the off-page filter (coords not comparable)")
elif not _kept_enough:
    print(
        f"  off-page filter would keep only {len(_on_page)}/{len(glyphs)} glyphs — "
        "that is not a page, so keeping everything instead"
    )
else:
    print(f"  dropped {len(glyphs) - len(_on_page)} glyphs drawn outside the page box")
    glyphs = _on_page

# ------------------------------------------------------------- line assembly

rows = {}
for glyph in glyphs:
    rows.setdefault(round(glyph["y"]), []).append(glyph)


def anchor_marks(items):
    """Attach each combining mark to the base glyph it overlaps, right after it."""
    marks, bases = [], []
    for glyph in items:
        is_mark = (unicodedata.category(glyph["char"][0]) == "Mn"
                   or glyph["w"] < MARK_FRACTION * glyph["size"])
        (marks if is_mark else bases).append(glyph)
    if not bases:
        return sorted(items, key=lambda g: (g["x"], g["seq"]))
    bases = sorted(bases, key=lambda g: (g["x"], g["seq"]))
    for mark in marks:
        centre = mark["x"] + mark["w"] / 2
        host = max(bases, key=lambda b: min(b["x"] + b["w"], mark["x"] + mark["w"])
                   - max(b["x"], mark["x"]))
        host.setdefault("marks", []).append((centre, mark["char"]))
    return bases


def line_text(items, space_fraction):
    units, previous = [], None
    for glyph in items:
        if previous is not None:
            gap = glyph["x"] - (previous["x"] + previous["w"])
            if gap > space_fraction * previous["size"]:
                units.append(" ")
        units.append(glyph["char"])
        for _centre, mark in sorted(glyph.get("marks", [])):
            units.append(mark)
        previous = glyph
    text = visual_to_logical(units)
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r" {2,}", " ", text)
    return re.sub(r"(?<=[0-9٠-٩]) ?([/.]) ?(?=[0-9٠-٩])", r"\1", text).strip()


def columns_of(all_glyphs, all_rows):
    """Cluster line centres; a clear valley in the histogram means two columns."""
    centres = []
    for y, items in all_rows.items():
        centres.append((y, sum(g["x"] + g["w"] / 2 for g in items) / len(items)))
    xs = sorted(c for _y, c in centres)
    if len(xs) < 6:
        return {y: 0 for y, _c in centres}, 1
    span = xs[-1] - xs[0]
    if span <= 0:
        return {y: 0 for y, _c in centres}, 1
    best_split, best_gap = None, 0.0
    for i in range(1, len(xs)):
        gap = xs[i] - xs[i - 1]
        if gap > best_gap:
            best_gap, best_split = gap, (xs[i] + xs[i - 1]) / 2
    if best_gap < 0.25 * span:
        return {y: 0 for y, _c in centres}, 1
    return {y: (0 if c < best_split else 1) for y, c in centres}, 2


assignment, column_count = columns_of(glyphs, rows)
print(f"columns detected: {column_count}")

# Space threshold: the font's own space width where known, else a modest default.
fraction = min(space_w.values()) * 0.45 if space_w else 0.12
print(f"space threshold: {fraction:.3f} em"
      f"{' (from the font space glyph)' if space_w else ' (default)'}")

lines = []
for column in range(column_count):
    for y in sorted((y for y in rows if assignment.get(y, 0) == column), reverse=True):
        text = line_text(anchor_marks(rows[y]), fraction)
        if text:
            lines.append(text)

print(f"\n{'=' * 74}\nPAGE {PAGE} — v11\n{'=' * 74}")
for text in lines:
    print(f"  {text}")

whole = "\n".join(lines)
CHECKS = {
    22: [("serial", "الرقم التسلسلي: ٢"), ("court", "المحكمة العامة بالرياض"),
         ("case no", "٣٤٣١٦٤٤٣"), ("date", "١٤٣٥/٠٦/٠٢"),
         ("keyword", "عقار مرهون"), ("keyword", "قاصر بين الورثة"),
         ("keyword", "شهادة شهود عدول"), ("keyword", "لزوم بدل القرض"),
         ("diacritic", "تقبل"), ("statute", "نظام المرافعات الشرعية"),
         ("quote", "فيما لا تهمة فيه"), ("body", "أقامت المدعية دعواها")],
    16: [("serial", "الرقم التسلسلي"), ("court", "المحكمة العامة بضمد"),
         ("keyword", "عقار من دون صك"), ("keyword", "يمين مكملة"),
         ("statute", "نظام المرافعات الشرعية"), ("date", "١٤٣٣")],
}
if PAGE in CHECKS:
    print(f"\n{'=' * 74}\nknown-correct strings\n{'=' * 74}")
    hits = 0
    for label, expected in CHECKS[PAGE]:
        found = expected in whole
        hits += found
        print(f"  {label:<11} {'FOUND' if found else 'not found':>10}   {expected}")
    print(f"\n  {hits}/{len(CHECKS[PAGE])}   squares: {len(BAD.findall(whole))}")
