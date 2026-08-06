"""Twin-font decode first, LLM for layout only, then verify nothing was invented.

The two halves fail in opposite directions, which is why combining them works:

  * twin_font_decode.py gets the *characters* right — `قاصر عقلا`, `المرافعات
    الشرعية`, every digit — but assembles them into the wrong *lines*, because
    it detects two columns on a one-column page and splices the header panel
    into the body paragraphs.
  * An LLM over the raw pdftotext layer produced fluent text that silently
    changed `عقلا` (mentally incapacitated) into `عقار` (real estate). Fluent
    and wrong is the worst outcome for legal text.

So the LLM is given work it cannot fabricate its way through: the characters
already arrive correct, and its only job is to put lines back in order. That
turns into a mechanical guarantee — a pure reordering must preserve the exact
multiset of characters. verify() checks that and prints anything the model
added or dropped, so a fabrication cannot pass silently the way it did before.

    python scripts/extract_hybrid.py
"""

import os
import re
import shutil
import subprocess
import sys
import time
import unicodedata
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import httpx

# ---- settings you can change -------------------------------------------------

MODEL = "gemma4"
FIRST_PAGE = 16
LAST_PAGE = 21
HERE = Path(__file__).resolve().parent
DECODER = HERE / "twin_font_decode.py"
PDF = Path.home() / "Downloads" / "ahkam.pdf"
OUTPUT = HERE / "result_hybrid.txt"

PROMPT = """\
Below are lines of Arabic text recovered from one page of a Saudi legal judgment.
The characters are already correct. The LINE ORDER is not: a boxed header panel
has been spliced into the middle of the body paragraphs, so header fragments
appear inside body sentences.

Your only job is to put the lines back in order:

1. Every piece of text in the input must appear in your output EXACTLY ONCE.
   Do not drop a line. Do not repeat a line. This is checked automatically.
2. Move text ONLY. Do NOT add, delete, or change a single character - not a
   letter, not a digit, not a punctuation mark. Do not fix spelling. Do not
   complete a phrase. Do not translate or summarise.
3. Keep the paragraphs in the order they already appear. Only pull out
   fragments that were spliced in from somewhere else.
4. IF this page has a boxed header panel (court name, case number, dates),
   put those fields first, each on its own line. Most pages have no such
   panel - in that case change nothing about the paragraph order.
5. One run of letters may be unreadable scrambled glyphs. Leave it exactly as
   it is, on its own line. Do not attempt to repair it.
6. Output the reordered text only. No preamble, no commentary.

--- BEGIN DECODED PAGE ---
{page_text}
--- END DECODED PAGE ---
"""


def decode_page(page: int, pdf: Path = PDF) -> str:
    """Run the twin-font decoder and pull just the page text out of its report."""
    result = subprocess.run(
        [sys.executable, str(DECODER), str(page), str(pdf)],
        capture_output=True,
        cwd=str(HERE),
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    if result.returncode != 0:
        sys.exit(f"decoder failed on page {page}: {result.stderr.decode('utf-8', 'replace')[:400]}")

    out = result.stdout.decode("utf-8", "replace")

    # The decoder prints diagnostics, then a banner, then the page indented by
    # two spaces, then a checks section. Take only the middle part.
    lines: list[str] = []
    collecting = False
    for line in out.splitlines():
        if re.match(rf"^PAGE {page} — ", line):
            collecting = True
            continue
        if collecting:
            if "known-correct strings" in line or set(line.strip()) == {"="}:
                if lines:
                    break
                continue
            lines.append(line[2:] if line.startswith("  ") else line)

    return "\n".join(lines).strip()


def pdftotext_page(pdf: Path, page: int) -> str:
    """Ordinary text-layer extraction, for files that do not have the defect."""
    exe = shutil.which("pdftotext")
    if not exe:
        packages = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages"
        exe = next((str(p) for p in packages.glob("*Poppler*/**/pdftotext.exe")), None)
    if not exe:
        return ""

    done = subprocess.run(
        [exe, "-f", str(page), "-l", str(page), "-enc", "UTF-8", str(pdf), "-"],
        capture_output=True,
    )
    return done.stdout.decode("utf-8", "replace") if done.returncode == 0 else ""


def readability(text: str) -> int:
    """Crude score: real letters are good, replacement characters are very bad.

    Used only to choose between two extractions of the SAME page, so it does
    not need to be meaningful in absolute terms - just ordered correctly.
    """
    letters = len(re.findall(r"[ء-ي٠-٩A-Za-z]", text))
    broken = text.count("�") + len(re.findall(r"[-￠-￿]", text))
    return letters - 8 * broken


def extract_page(pdf: Path, page: int) -> tuple[str, str]:
    """Pick the better extraction for this page. Returns (text, method).

    The twin-font decoder is not a general PDF reader - it understands the
    font layout of one particular producer, and on an ordinary PDF it can
    return nothing at all. So it never gets used on trust: whatever it
    produces is scored against plain pdftotext, and the better one wins. A
    file without the defect therefore comes out exactly as pdftotext read it.
    """
    plain = pdftotext_page(pdf, page)
    try:
        decoded = decode_page(page, pdf)
    except SystemExit:
        decoded = ""

    if readability(decoded) > readability(plain):
        return decoded, "twin-font decode"
    return plain.strip(), "pdftotext"


def ask_model(prompt: str) -> str:
    api_url = os.environ["COMPANY_API_URL"].rstrip("/")
    api_key = os.environ["COMPANY_API_KEY"]

    with httpx.Client(timeout=600.0) as client:
        response = client.post(
            f"{api_url}/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={
                "model": MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
            },
        )

    if response.status_code != 200:
        sys.exit(f"{MODEL} returned {response.status_code}: {response.text[:300]}")

    return response.json()["choices"][0]["message"]["content"]


def significant(text: str) -> Counter:
    """Count the characters a pure reordering must preserve.

    Whitespace is excluded because rejoining lines legitimately moves it, and
    the bidi/formatting marks are excluded because they are invisible controls
    rather than content.
    """
    cleaned = unicodedata.normalize("NFKC", text)
    cleaned = re.sub(r"[​-‏‪-‮⁦-⁩]", "", cleaned)
    return Counter(c for c in cleaned if not c.isspace())


def verify(before: str, after: str) -> list[str]:
    """Report what the model invented or dropped. Empty list = clean.

    Character counts alone say "3 alifs went missing", which is true but not
    actionable. Whole lines are what actually go missing, so name those first
    and fall back to characters only for changes too small to be a line.
    """
    src, out = significant(before), significant(after)
    if not (src - out) and not (out - src):
        return []

    problems = []
    squash = lambda s: re.sub(r"\s+", "", s)
    after_squashed = squash(after)

    for line in before.splitlines():
        stripped = line.strip()
        if len(stripped) > 12 and squash(stripped) not in after_squashed:
            # Could be dropped outright or edited; either way it no longer
            # appears verbatim, which is what the reorder-only rule forbids.
            problems.append(f"LINE LOST OR CHANGED: {stripped[:70]}")

    for char, count in (out - src).items():
        problems.append(f"ADDED   {char!r} ×{count}")
    for char, count in (src - out).items():
        problems.append(f"DROPPED {char!r} ×{count}")
    return problems


def chunk_text(text: str, target: int = 260) -> list[str]:
    """Break a page into short readable pieces, splitting on sentence ends.

    The decoder returns wrapped display lines, so joining them and re-splitting
    on Arabic full stops gives units that read as sentences rather than as
    whatever width the original page happened to use.
    """
    flat = re.sub(r"\s*\n\s*", " ", text).strip()
    pieces = re.split(r"(?<=[.؟!])\s+", flat)

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if current and len(current) + len(piece) > target:
            chunks.append(current.strip())
            current = piece
        else:
            current = f"{current} {piece}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def main() -> None:
    chunks: list[str] = []
    all_problems: list[str] = []

    for page in range(FIRST_PAGE, LAST_PAGE + 1):
        print(f"page {page}: extracting ...", end=" ", flush=True)
        decoded, method = extract_page(PDF, page)
        print(f"[{method}]", end=" ", flush=True)
        if not decoded:
            print("no text recovered, skipping")
            continue

        if "--no-llm" in sys.argv:
            # Decode-only. Cannot lose a line by construction, and gives the
            # same bytes every run - which matters if these chunks are ever
            # going to be embedded and stored.
            print(f"{len(decoded)} chars, no LLM")
            tidied = decoded
        else:
            print(f"{len(decoded)} chars, asking {MODEL} ...", end=" ", flush=True)
            started = time.monotonic()
            tidied = ask_model(PROMPT.format(page_text=decoded))
            elapsed = time.monotonic() - started
            print(f"{elapsed:.1f}s", end=" ")

        problems = verify(decoded, tidied)
        all_problems += [f"page {page}: {p}" for p in problems]
        print(f"{len(problems)} character changes")

        for number, chunk in enumerate(chunk_text(tidied), start=1):
            chunks.append(f"--- page {page} · chunk {number} ---\n{chunk}")

    report = "\n".join(all_problems) if all_problems else "none - nothing added or dropped"
    header = (
        f"MODEL: {MODEL} (layout only, on twin-font decoded text)\n"
        f"PAGES: {FIRST_PAGE}-{LAST_PAGE}\n"
        f"{'=' * 60}\n"
        f"CHARACTER-CONSERVATION CHECK\n"
        f"{report}\n"
        f"{'=' * 60}\n\n"
    )
    if "--no-llm" in sys.argv:
        header = header.replace(
            f"MODEL: {MODEL} (layout only, on twin-font decoded text)",
            "MODEL: none - twin-font decode only",
        )
    OUTPUT.write_text(header + "\n\n".join(chunks), encoding="utf-8")

    print(f"\nWrote {OUTPUT}")
    print(f"Character changes across all pages: {len(all_problems)}")
    subprocess.Popen(["notepad.exe", str(OUTPUT)])


if __name__ == "__main__":
    main()
