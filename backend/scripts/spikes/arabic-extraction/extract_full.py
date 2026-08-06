"""Extract a legal case into chunks: crop, OCR, clean, repair, chunk.

    uv run --python 3.12 --with easyocr --with pillow --with numpy \
        --with httpx --with python-dotenv --with fonttools --with pypdf \
        python scripts/extract_full.py 16 17

Pipeline, and why each stage is there:

  1. CROP - split the page above each section heading. This is what makes a
     chunk a chunk, and it keeps a heading with the text it introduces.
  2. OCR - EasyOCR on each crop separately. Reads pixels, so broken font
     tables are irrelevant, and a small single-topic crop beats a whole page
     (the article slash in `٢/٢٥٨` survives cropping and is lost without it).
  3. CLEAN - gemma4, allowed to fix only four named OCR error classes and
     required to write [?] for anything else. Naming the permitted edits is
     what stops fabrication; a vague "be faithful" instruction did not, and
     produced عقلا -> عقار on an earlier attempt.
  4. REPAIR - the boxed header panel only. OCR clips characters at its
     detection-box edges, and the panel is where that hurts most because it
     holds the case number and the dates. Measured on page 16: the box for
     `تاريخها:١٤٣٣` stopped 186px short of the neighbouring date's box and cut
     off the leading `١`, reporting `٤٣٣` at confidence 0.94 - the highest on
     the page, so confidence cannot be used to catch it. The same edge effect
     turned `رقم القرار` into `قم القرار`. The twin-font decoder reads the
     panel exactly right, so panel lines are taken from it instead.
  5. CHUNK - CaseChunker windows any section too long to embed well, never
     crossing a section boundary, and stamps every chunk with the case id.

Nothing here is specific to one file. Each stage degrades to the next-best
option on its own evidence: no red rules found -> split on whitespace; no
panel fill found -> nothing is repaired; decoder reads nothing (a normal PDF,
or a scan) -> OCR output is used unchanged. A repair can only ever replace a
line the decoder demonstrably covers, so text is never silently dropped.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

import httpx
import numpy as np
from dotenv import load_dotenv
from PIL import Image

HERE = Path(__file__).resolve().parent
load_dotenv(HERE.parent / ".env")
sys.path.insert(0, str(HERE.parent / "src"))

from chunkers.case_chunker import Case, CaseChunker, CaseMetadata, CaseSection  # noqa: E402

DECODER = HERE / "twin_font_decode.py"
DEFAULT_PDF = Path.home() / "Downloads" / "ahkam.pdf"
OUTPUT = HERE / "result_full.txt"
MODEL = "gemma4"
DPI = 300
MARGIN = 12
MIN_SECTION_HEIGHT = 40
MIN_SECTION_GAP = 55
INK_THRESHOLD = 200
WINDOW_WORDS = 200
OVERLAP_WORDS = 40

# A panel cell is filled with a light tint - measured [237 212 203] on page 16 -
# whereas the heading rules and the page banner are dark red, around [164 38 44].
# The brightness cut is what separates a fill from ink, so this asks "coloured
# but still light" rather than naming the publisher's particular pink.
FILL_MIN_BRIGHTNESS = 180
FILL_MIN_WIDTH = 0.5   # fraction of the row that must be tinted
FILL_MIN_HEIGHT = 15   # px; thinner coloured runs are rules, not cells
PANEL_MIN_CELLS = 2    # one tinted strip is decoration; several are a table

# Sections appear in this order on a case summary page. We label by position
# because the headings themselves are unreadable in every method we have.
SUMMARY_SECTION_ORDER = ["المفاتيح", "السند الشرعي أو النظامي", "ملخص الدعوى"]

OCR_PROMPT = """\
Below is Arabic text produced by OCR from one section of a Saudi legal judgment.
The reading order is broadly right. The known OCR errors are:

  * date separators are lost, e.g. "٠٦ ٠٧ ١٤٣٥" was printed as ١٤٣٥/٠٧/٠٦
  * a leading digit can be split off, e.g. "٤٣٣ ا" was printed as ١٤٣٣
  * adjacent words run together, e.g. "فقدحكم" is "فقد حكم"
  * decorative section headings come out as nonsense letter runs

Clean it up under these rules:

1. Fix ONLY the four error types listed above.
2. Do NOT change any other word. Do not correct spelling, do not complete a
   phrase, do not rewrite legal wording, do not translate or summarise.
3. If a run of letters is unreadable nonsense, replace it with [?] and nothing
   else. Do NOT guess what a heading said.
4. Never invent a digit. If a number is unclear, write [?] rather than a guess.
5. Output the cleaned text only. No preamble, no commentary.

--- BEGIN OCR TEXT ---
{page_text}
--- END OCR TEXT ---
"""


# ----------------------------------------------------------------- rendering

def poppler_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for exe in packages.glob(f"*Poppler*/**/{name}.exe"):
        return str(exe)
    sys.exit(f"{name} not found. Run: winget install oschwartz10612.Poppler")


def render(pdf: Path, page: int, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [poppler_tool("pdftoppm"), "-png", "-r", str(DPI),
         "-f", str(page), "-l", str(page), str(pdf), str(out_dir / f"p{page}")],
        check=True, capture_output=True,
    )
    images = sorted(out_dir.glob(f"p{page}*.png"))
    if not images:
        sys.exit(f"no image rendered for page {page}")
    return images[0]


# ------------------------------------------------------------------ cropping

def red_bands(image: Image.Image) -> tuple[list[tuple[int, int]], list[tuple[int, int]]]:
    """Separate red script (headings) from red horizontal rules (underlines).

    Measured on page 16: a heading is ~100px tall with 78-207 red pixels per
    row; its underline is 8-9px tall with ~1000 of 2008 pixels red. So width
    tells them apart cleanly.
    """
    rgb = np.asarray(image.convert("RGB")).astype(int)
    height, width = rgb.shape[:2]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    per_row = ((r > g + 40) & (r > b + 40) & (r > 80)).sum(axis=1)

    bands, start = [], None
    for y in range(height):
        if per_row[y] > 5:
            if start is None:
                start = y
        elif start is not None:
            bands.append((start, y))
            start = None
    if start is not None:
        bands.append((start, height))

    rules = [(a, b) for a, b in bands
             if b - a <= 20 and per_row[a:b].max() > width * 0.33]
    script = [(a, b) for a, b in bands
              if b - a >= 60 and per_row[a:b].max() <= width * 0.33]
    return script, rules


def fill_bands(image: Image.Image) -> list[tuple[int, int]]:
    """Rows filled with a light colour - the cells of a boxed table.

    Deliberately not "find the header panel". Any document that lays facts out
    in tinted cells gets the same treatment, and a document with no tinted
    cells simply yields nothing here and is left entirely to OCR.
    """
    rgb = np.asarray(image.convert("RGB")).astype(int)
    height, width = rgb.shape[:2]
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    tinted = ((r > g + 8) & (r > b + 8) & (b > FILL_MIN_BRIGHTNESS)).sum(axis=1)
    wide = tinted > width * FILL_MIN_WIDTH

    bands, start = [], None
    for y in range(height):
        if wide[y]:
            if start is None:
                start = y
        elif start is not None:
            if y - start >= FILL_MIN_HEIGHT:
                bands.append((start, y))
            start = None
    if start is not None and height - start >= FILL_MIN_HEIGHT:
        bands.append((start, height))
    return bands


def find_sections(image: Image.Image) -> list[tuple[int, int]]:
    """Cut ABOVE each heading, so a heading stays with the text it introduces.

    Cutting at the underline instead would leave every heading stranded at the
    bottom of the previous section - which is how `ملخص الدعوى` ended up
    dangling off the end of the articles block on an earlier run.

    A heading is identified as red script immediately followed by a red rule.
    That pairing is what distinguishes a real section heading from the boxed
    panel's coloured fill, which has no underline.
    """
    height = image.height
    script, rules = red_bands(image)

    tops = []
    for a, b in script:
        # An underline sits within ~40px below the heading it belongs to.
        if any(0 <= rule_a - b <= 40 for rule_a, _ in rules):
            tops.append(a)

    if tops:
        edges = [0, *sorted(tops), height]
        return [
            (edges[i], edges[i + 1]) for i in range(len(edges) - 1)
            if edges[i + 1] - edges[i] >= MIN_SECTION_HEIGHT
        ]

    grey = np.asarray(image.convert("L"))
    width = grey.shape[1]
    ink = (grey[:, int(width * 0.10):int(width * 0.90)] < INK_THRESHOLD).any(axis=1)
    out, start, blank = [], None, 0
    for y in range(height):
        if ink[y]:
            if start is None:
                start = y
            blank = 0
        elif start is not None:
            blank += 1
            if blank >= MIN_SECTION_GAP:
                if y - blank - start >= MIN_SECTION_HEIGHT:
                    out.append((start, y - blank))
                start, blank = None, 0
    if start is not None and height - start >= MIN_SECTION_HEIGHT:
        out.append((start, height))
    return out


# ----------------------------------------------------------------- the stages

def ocr(image_path: Path) -> str:
    import easyocr

    global _reader
    try:
        reader = _reader
    except NameError:
        print("  loading EasyOCR ...", flush=True)
        reader = _reader = easyocr.Reader(["ar"], gpu=False, verbose=False)
    return "\n".join(reader.readtext(str(image_path), detail=0, paragraph=True)).strip()


def clean(text: str) -> str:
    with httpx.Client(timeout=600.0) as client:
        response = client.post(
            f"{os.environ['COMPANY_API_URL'].rstrip('/')}/v1/chat/completions",
            headers={"Authorization": f"Bearer {os.environ['COMPANY_API_KEY']}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": OCR_PROMPT.format(page_text=text)}],
                "temperature": 0,
            },
        )
    if response.status_code != 200:
        raise RuntimeError(f"{MODEL} returned {response.status_code}: {response.text[:200]}")
    return response.json()["choices"][0]["message"]["content"].strip()


def decode_page(page: int, pdf: Path) -> str:
    """Independent reading of the page straight from the PDF's font tables."""
    done = subprocess.run(
        [sys.executable, str(DECODER), str(page), str(pdf)],
        capture_output=True, cwd=str(HERE),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if done.returncode != 0:
        return ""
    text, collecting = [], False
    for line in done.stdout.decode("utf-8", "replace").splitlines():
        if re.match(rf"^PAGE {page} — ", line):
            collecting = True
            continue
        if collecting:
            if "known-correct strings" in line or set(line.strip()) == {"="}:
                if text:
                    break
                continue
            text.append(line.strip())
    return "\n".join(text).strip()


def words(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ً-ْ]", "", text)
    return [w for w in re.findall(r"[ء-ي]+", text) if len(w) > 2]


def panel_repair(section_ocr: str, decoded: str) -> tuple[str, int]:
    """Replace panel lines OCR mangled with the decoder's reading of them.

    Lines are matched by word overlap, never by looking for particular field
    labels, so this carries to any document whose panel says something else.
    A decoder line is taken as belonging here when most of its words also
    appear in this section's OCR - that shared vocabulary is the only evidence
    the two are reading the same part of the page.

    An OCR line survives untouched unless the decoder lines account for most
    of its words. That is what keeps the swap from deleting anything: the
    title above the panel is drawn in a decorative font the decoder cannot
    read, so no decoder line covers it, so it stays exactly as OCR saw it.

    Returns the repaired text and how many decoder lines were used, so a run
    that repaired nothing is visible in the report rather than silent.
    """
    ocr_vocabulary = set(words(section_ocr))
    if not ocr_vocabulary:
        return section_ocr, 0

    taken, covered = [], set()
    for line in decoded.splitlines():
        theirs = words(line)
        if len(theirs) < 2:
            continue
        # U+FFFD is the decoder admitting it could not map a glyph, which
        # happens on the decorative title above the panel. OCR reads that line
        # correctly, so a line carrying that mark is never allowed to win.
        if "�" in line:
            continue
        if sum(w in ocr_vocabulary for w in theirs) / len(theirs) >= 0.6:
            taken.append(line.strip())
            covered |= set(theirs)
    if not taken:
        return section_ocr, 0

    survivors = []
    for line in section_ocr.splitlines():
        mine = words(line)
        if mine and sum(w in covered for w in mine) / len(mine) >= 0.6:
            continue  # the decoder has this line, and reads it correctly
        if line.strip():
            survivors.append(line.strip())
    return "\n".join(survivors + taken), len(taken)


def invented(before: str, after: str) -> list[str]:
    """Words gemma4 produced that are not in the OCR text or a split of it."""
    raw = words(before)
    joined = "".join(raw)
    return sorted({w for w in words(after) if w not in raw and w not in joined})


# ------------------------------------------------------------------ pipeline

def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = [int(a) for a in args if a.isdigit()] or [16, 17]
    pdf = Path(next((a for a in args if not a.isdigit()), DEFAULT_PDF))

    scratch = HERE / "_full_images"
    sections: list[CaseSection] = []
    notes: list[str] = []

    for page in pages:
        print(f"\npage {page}: rendering ...", flush=True)
        image = Image.open(render(pdf, page, scratch))
        bands = find_sections(image)
        cells = fill_bands(image)

        # One decode per page, shared by every panel section on it. An empty
        # result here - a normal PDF, or a scan - simply disables repair.
        decoded = decode_page(page, pdf)
        print(f"  {len(bands)} sections, {len(cells)} filled cells, "
              f"decoder read {len(decoded)} chars")

        body_seen = 0
        for index, (top, bottom) in enumerate(bands, start=1):
            crop_path = scratch / f"p{page}_s{index}.png"
            image.crop((0, max(0, top - MARGIN), image.width,
                        min(image.height, bottom + MARGIN))).save(crop_path)

            started = time.monotonic()
            raw = ocr(crop_path)
            if not raw:
                print(f"  section {index}: empty, skipped")
                continue

            is_panel = sum(top <= a and b <= bottom for a, b in cells) >= PANEL_MIN_CELLS
            if is_panel and decoded:
                # No gemma4 here. The decoder's panel text is already exact,
                # and every model pass is another chance to alter a digit.
                text, swapped = panel_repair(raw, decoded)
                source = f"OCR + decoder ({swapped} lines repaired)"
                made_up: list[str] = []
            else:
                text = clean(raw)
                made_up = invented(raw, text)
                source = "OCR + gemma4"

            print(f"  section {index} ({bottom - top}px): {len(text)} chars, "
                  f"{time.monotonic() - started:.0f}s, {source}"
                  f"{'  INVENTED: ' + ', '.join(made_up) if made_up else ''}")

            # The first section of a summary page is the title and boxed panel;
            # the headed sections then follow in a fixed order, so they can be
            # labelled by position without reading the headings themselves.
            if index == 1 and is_panel:
                label = "العنوان والبيانات"
            elif body_seen < len(SUMMARY_SECTION_ORDER) and index > 1:
                label = SUMMARY_SECTION_ORDER[body_seen]
                body_seen += 1
            else:
                label = "نص الحكم"

            sections.append(CaseSection(name=label, text=text))
            notes.append(f"page {page} section {index} ({bottom - top}px) "
                         f"-> {label}: {source}; invented: "
                         f"{', '.join(made_up) if made_up else 'nothing'}")

    # The page range given on the command line is one case, so the id is
    # derived from the file and its first page rather than from any Arabic
    # field name - that keeps it working on a document worded differently.
    case = Case(
        metadata=CaseMetadata(case_id=f"{pdf.stem}-p{pages[0]}"),
        sections=tuple(sections),
    )
    chunks = CaseChunker(window_size=WINDOW_WORDS, overlap=OVERLAP_WORDS).chunk(case)
    print(f"\n{len(sections)} sections -> {len(chunks)} chunks")

    report = [
        "PIPELINE: crop above each heading -> EasyOCR per section -> gemma4 cleanup,\n"
        "except boxed panels, which are repaired from the twin-font decoder instead.\n"
        f"MODEL: {MODEL}   DPI: {DPI}   PAGES: {', '.join(map(str, pages))}\n"
        f"CHUNKING: CaseChunker, {WINDOW_WORDS}-word windows, {OVERLAP_WORDS} overlap,\n"
        "never crossing a section boundary.\n"
        "CHECK: 'invented' lists words gemma4 produced that are NOT in the raw OCR.\n"
        "Anything listed there is a fabrication - treat it as suspect.\n"
        + "=" * 66,
        "\nSECTIONS\n" + "\n".join(notes) + "\n" + "=" * 66 + "\n",
    ]
    for chunk in chunks:
        report.append(
            f"--- chunk {chunk.chunk_index + 1} of {chunk.total_in_case} ---\n"
            f"{chunk.header}\n\n{chunk.body}\n"
        )

    OUTPUT.write_text("\n".join(report), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    if os.name == "nt":
        subprocess.Popen(["notepad.exe", str(OUTPUT)])


if __name__ == "__main__":
    main()
