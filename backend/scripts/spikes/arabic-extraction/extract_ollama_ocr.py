"""OCR a page with a vision model served by Ollama, then score it against the decoder.

No uv juggling needed - Ollama holds the model, so this only needs the standard
library plus poppler for rendering:

    python scripts/extract_ollama_ocr.py 16 21

First run the pull once:

    ollama pull hf.co/Makadi86/Arabic-GLM-OCR-v2-GGUF

Why this route rather than transformers. The GTX 1060 has 4GB and is a Pascal
card, which is older than bfloat16 support and has weak float16 arithmetic.
PyTorch either crashes or crawls. Ollama's engine quantises the weights, splits
layers between the card and the processor when VRAM runs out, and needs no CUDA
build of torch. It also sidesteps the transformers processor entirely, which is
what pulled in torchvision for a video handler we never use.

The measurement is the same as extract_ocr.py: agreement with the twin-font
decoder, because the two read the page through completely different machinery
and neither is trustworthy alone. See that file for the reasoning.
"""

import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_ocr import DPI, agreement, decoded, render  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PDF = Path.home() / "Downloads" / "ahkam.pdf"

MODEL = os.environ.get("OLLAMA_OCR_MODEL", "hf.co/Makadi86/Arabic-GLM-OCR-v2-GGUF")
ENDPOINT = os.environ.get("OLLAMA_HOST", "http://localhost:11434").rstrip("/") + "/api/generate"

# Naming the forbidden edits is what stopped fabrication in the gemma4 work, and
# this model's own card advertises "intelligent spelling correction" as a
# feature - which for a legal transcript is the thing we must switch off.
PROMPT = (
    "Text Recognition: Extract the Arabic text exactly as printed. "
    "Do not correct spelling. Do not complete words. Do not change any number. "
    "If something is unreadable, output [?] rather than a guess."
)

# A judgment page runs well past the 512 the model card suggests; at that limit
# the output stops mid-sentence and looks like a failure that is not one.
MAX_TOKENS = 2048


def read_page(image: Path, timeout: int = 900) -> str:
    """Send one page image to Ollama and return the transcription."""
    payload = {
        "model": MODEL,
        "prompt": PROMPT,
        "images": [base64.b64encode(image.read_bytes()).decode("ascii")],
        "stream": False,
        "options": {
            # Greedy decoding. Sampling is where invented text comes from, so
            # for transcription it is switched off outright.
            "temperature": 0,
            "top_k": 1,
            "num_predict": MAX_TOKENS,
            "repeat_penalty": 1.1,
        },
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.load(response).get("response", "").strip()
    except urllib.error.HTTPError as err:
        detail = err.read().decode("utf-8", "replace")
        sys.exit(f"Ollama returned {err.code}: {detail}\nIs `ollama serve` running?")
    except urllib.error.URLError as err:
        sys.exit(f"Could not reach Ollama at {ENDPOINT}: {err.reason}")


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = [int(a) for a in args if a.isdigit()]
    pdf = Path(next((a for a in args if not a.isdigit()), DEFAULT_PDF))

    # 16 has a decoder reading to check against; 21 is where the decoder gives
    # up entirely, so it shows whether this model adds anything at all.
    if not pages:
        pages = [16, 21]

    scratch = HERE / "_glmocr_images"
    report = []

    print(f"model: {MODEL}")
    for page in pages:
        print(f"\npage {page}: rendering at {DPI} DPI ...", flush=True)
        image = render(pdf, page, scratch)

        started = time.monotonic()
        text = read_page(image)
        print(f"  model: {len(text)} chars in {time.monotonic() - started:.1f}s")

        dec_text = decoded(page, pdf)
        print(f"  decoder: {len(dec_text)} chars")

        score = agreement(text, dec_text)
        print(f"  agreement: {score:.1%}   (EasyOCR scored 92% on page 16)")

        report.append((page, text, dec_text, score))

    out = HERE / "result_ollama_ocr.txt"
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"OCR: {MODEL} @ {DPI} DPI, greedy\n")
        fh.write("=" * 60 + "\n\n")
        for page, text, dec_text, score in report:
            fh.write(f"===== PAGE {page} — agreement with decoder: {score:.1%} =====\n\n")
            fh.write(f"--- {MODEL} ---\n{text}\n\n")
            fh.write(f"--- twin-font decoder ---\n{dec_text or '(nothing recovered)'}\n\n")

    print(f"\nWrote {out}")
    print("Compare against result_ocr.txt to see where this and EasyOCR disagree.")
    if os.name == "nt":
        subprocess.Popen(["notepad.exe", str(out)])


if __name__ == "__main__":
    main()
