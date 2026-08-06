"""OCR the page image, then cross-check it against the twin-font decoder.

Run with uv so easyocr's dependencies stay out of the backend environment:

    uv run --python 3.12 --with easyocr --with pillow python scripts/extract_ocr.py 16
    uv run --python 3.12 --with easyocr --with pillow python scripts/extract_ocr.py 16 --llm

Why OCR is worth adding even though the decoder mostly works: the two methods
fail for unrelated reasons. The decoder reads the PDF's font tables, so it is
immune to image quality but helpless when the font tables lie or are missing -
it returns nothing at all on page 21 and on ordinary PDFs. OCR reads pixels, so
it does not care about font encoding at all, but it can misread a character.

Neither is trustworthy alone. Agreement between them is, because for both to be
wrong the same way they would have to fail identically, and they have no shared
machinery. So this prints an agreement score per page rather than claiming
either output is correct.

Measured previously and worth not rediscovering: EasyOCR keeps Arabic-Indic
digits (Tesseract converts them to Latin, which is disqualifying here), and
300 DPI beat 600+ on this document.
"""

import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

HERE = Path(__file__).resolve().parent
DECODER = HERE / "twin_font_decode.py"
DEFAULT_PDF = Path.home() / "Downloads" / "ahkam.pdf"
DPI = 300  # Measured best for EasyOCR on this document; 600+ was worse.


def poppler_tool(name: str) -> str:
    found = shutil.which(name)
    if found:
        return found
    packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
    for exe in packages.glob(f"*Poppler*/**/{name}.exe"):
        return str(exe)
    sys.exit(f"{name} not found. Run: winget install oschwartz10612.Poppler")


def render(pdf: Path, page: int, out_dir: Path) -> Path:
    """Rasterise one page. OCR needs pixels, not a content stream."""
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / f"page{page}"
    subprocess.run(
        [
            poppler_tool("pdftoppm"), "-png", "-r", str(DPI),
            "-f", str(page), "-l", str(page),
            str(pdf), str(prefix),
        ],
        check=True,
        capture_output=True,
    )
    images = sorted(out_dir.glob(f"page{page}*.png"))
    if not images:
        sys.exit(f"pdftoppm produced no image for page {page}")
    return images[0]


def ocr(image: Path) -> str:
    """EasyOCR, Arabic. Reader construction is the slow part, so build it once."""
    import easyocr

    global _reader
    try:
        reader = _reader
    except NameError:
        print("  loading EasyOCR model ...", flush=True)
        reader = _reader = easyocr.Reader(["ar"], gpu=False, verbose=False)

    # paragraph=True groups detected boxes into reading-order blocks, which is
    # the part the decoder gets wrong, so it is worth having here.
    lines = reader.readtext(str(image), detail=0, paragraph=True)
    return "\n".join(lines)


def decoded(page: int, pdf: Path) -> str:
    """The twin-font decoder's version of the same page, for comparison."""
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


def normalise(text: str) -> str:
    """Strip everything that is presentation rather than content, then compare."""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[ً-ْ​-‏‪-‮]", "", text)
    return re.sub(r"[^ء-ي٠-٩]", "", text)


def agreement(a: str, b: str) -> float:
    """How much of the two extractions is literally the same text."""
    left, right = normalise(a), normalise(b)
    if not left or not right:
        return 0.0
    return SequenceMatcher(None, left, right).ratio()


# OCR fails differently from the decoder, so it needs its own instruction. The
# decoder's prompt says "the characters are correct, only the order is wrong",
# which is false here: OCR gets the order right and the characters wrong -
# it drops date separators, splits ١٤٣٣ into "٤٣٣ ا", and runs words together.
#
# Note the tension this creates. Fixing those REQUIRES changing characters, so
# the character-conservation check that protected us on the decoder cannot be
# applied. That check is what caught gemma4 turning عقلا into عقار. Removing it
# means trusting the model again, which is why this stays behind a flag.
OCR_PROMPT = """\
Below is Arabic text produced by OCR from one page of a Saudi legal judgment.
The reading order is broadly right. The known OCR errors are:

  * date separators are lost, e.g. "٠٦ ٠٧ ١٤٣٥" was printed as ١٤٣٥/٠٧/٠٦
  * a leading digit can be split off, e.g. "٤٣٣ ا" was printed as ١٤٣٣
  * adjacent words run together, e.g. "فقدحكم" is "فقد حكم"
  * decorative section headings come out as nonsense letter runs

Clean it up under these rules:

1. Fix ONLY the four error types listed above: date separators, split digits,
   run-together words, and word spacing.
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


def tidy_with_llm(text: str) -> str:
    """Optional gemma4 pass over the OCR output."""
    sys.path.insert(0, str(HERE))
    from extract_hybrid import ask_model

    return ask_model(OCR_PROMPT.format(page_text=text))


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = [int(a) for a in args if a.isdigit()]
    pdf = Path(next((a for a in args if not a.isdigit()), DEFAULT_PDF))
    use_llm = "--llm" in sys.argv

    if not pages:
        pages = [16, 21]

    scratch = HERE / "_ocr_images"
    report = []

    for page in pages:
        print(f"\npage {page}: rendering at {DPI} DPI ...", flush=True)
        image = render(pdf, page, scratch)

        started = time.monotonic()
        ocr_text = ocr(image)
        print(f"  OCR: {len(ocr_text)} chars in {time.monotonic() - started:.1f}s")

        dec_text = decoded(page, pdf)
        print(f"  decoder: {len(dec_text)} chars")

        score = agreement(ocr_text, dec_text)
        print(f"  agreement: {score:.1%}")

        raw_ocr = ocr_text
        if use_llm:
            started = time.monotonic()
            ocr_text = tidy_with_llm(ocr_text)
            print(f"  after gemma4: {len(ocr_text)} chars in {time.monotonic() - started:.1f}s")
            print(f"  agreement OCR->gemma4: {agreement(raw_ocr, ocr_text):.1%}")

        report.append((page, ocr_text, dec_text, score, raw_ocr if use_llm else None))

    out = HERE / "result_ocr.txt"
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"OCR: EasyOCR(ar) @ {DPI} DPI{'  + gemma4 layout pass' if use_llm else ''}\n")
        fh.write("=" * 60 + "\n\n")
        for page, ocr_text, dec_text, score, raw_ocr in report:
            fh.write(f"===== PAGE {page} — agreement with decoder: {score:.1%} =====\n\n")
            if raw_ocr is not None:
                fh.write(f"--- OCR, raw ---\n{raw_ocr}\n\n")
                fh.write(f"--- OCR, after gemma4 ---\n{ocr_text}\n\n")
            else:
                fh.write(f"--- OCR ---\n{ocr_text}\n\n")
            fh.write(f"--- twin-font decoder ---\n{dec_text or '(nothing recovered)'}\n\n")

    print(f"\nWrote {out}")
    if os.name == "nt":
        subprocess.Popen(["notepad.exe", str(out)])


if __name__ == "__main__":
    main()
