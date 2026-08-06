"""OCR the page image with a vision model, then cross-check it against the decoder.

Run with uv so the model's dependencies stay out of the backend environment:

    uv run --no-project --python 3.12 --with transformers --with torch \
        --with torchvision --with accelerate --with pillow --with safetensors \
        python scripts/extract_glmocr.py 16 21

--no-project matters: without it uv treats backend/.venv as the project
environment and tries to rebuild it for 3.12. torchvision matters because the
processor bundles a video handler that imports it even though we never use it.

This is the same experiment as extract_ocr.py with a different reader. EasyOCR
matches shapes to letters; this one is a small vision-language model trained
only for transcription, so it reads a page the way a person does - with some
idea of what a document looks like. That helps on the boxed panels, where the
decoder scrambles and EasyOCR has no layout sense.

The catch is stated on the model's own card: it "may attempt autocorrect if not
properly constrained". That is the failure that made gemma4 unusable - it turned
قاصر عقلا (mentally incapacitated) into قاصر عقار (real-estate), which reads
perfectly and changes who the case is about. So two guards here:

  1. The prompt forbids correction explicitly, and sampling is off.
  2. Every run is scored against the twin-font decoder, which shares no
     machinery with it. Agreement is the only evidence either one is right.

Guard 2 is the important one. A model that autocorrects produces fluent output,
so it cannot be caught by reading it - only by diffing it against something
that failed differently.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_ocr import DPI, agreement, decoded, render  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PDF = Path.home() / "Downloads" / "ahkam.pdf"

MODEL = "sherif1313/Arabic-GLM-OCR-v2"

# A full judgment page runs well past the card's suggested 512. Too low and the
# output is silently truncated mid-sentence, which looks like a model failure
# and is not one.
MAX_NEW_TOKENS = 2048

# The card's own example prompt is bare "Text Recognition:". That is the phrasing
# the model was fine-tuned on, so it stays as the instruction - but the earlier
# gemma4 work showed that naming the forbidden edits is what actually stops
# fabrication, so the constraint is spelled out rather than implied.
PROMPT = (
    "Text Recognition: Extract the Arabic text exactly as printed. "
    "Do not correct spelling. Do not complete words. Do not change any number. "
    "If something is unreadable, output [?] rather than a guess."
)


def pick_dtype():
    """Choose the number format the hardware can actually run fast.

    This is not cosmetic. bfloat16 needs an Ampere card or newer (compute 8.0);
    on a GTX 1060, which is Pascal, it is either unsupported or emulated and
    crawls. float32 is the safe CPU choice - a 1B model costs little memory and
    bfloat16 matmul on a CPU without AMX is slower than plain float32.
    """
    import torch

    if not torch.cuda.is_available():
        return torch.float32
    major, _ = torch.cuda.get_device_capability()
    return torch.bfloat16 if major >= 8 else torch.float16


def load():
    """Build the model once. Loading is far slower than inference here."""
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    print(f"  loading {MODEL} (~2.2GB, downloads on first run) ...", flush=True)
    dtype = pick_dtype()
    processor = AutoProcessor.from_pretrained(MODEL, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        MODEL,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    device = next(model.parameters()).device
    print(f"  running on {device} as {dtype}, torch {torch.__version__}")
    if device.type == "cpu" and torch.cuda.device_count() == 0:
        print("  (no CUDA device visible - see the GPU note in this file's docstring)")
    return processor, model


def read_page(processor, model, image: Path) -> str:
    """One page image in, transcribed text out."""
    import torch

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "url": str(image)},
                {"type": "text", "text": PROMPT},
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        # do_sample=False makes this greedy: the model always takes its most
        # likely next token. Sampling is where invented text comes from, so for
        # transcription it is simply switched off - temperature is irrelevant
        # once it is, whatever the card suggests.
        generated = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            repetition_penalty=1.1,
        )

    # generate() returns the prompt as well as the answer; keep only what was added.
    new_tokens = generated[0][inputs["input_ids"].shape[1]:]
    return processor.decode(new_tokens, skip_special_tokens=True).strip()


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = [int(a) for a in args if a.isdigit()]
    pdf = Path(next((a for a in args if not a.isdigit()), DEFAULT_PDF))

    # 16 has a decoder reading to check against; 21 is where the decoder gives
    # up entirely, so it is the page that shows whether this adds anything.
    if not pages:
        pages = [16, 21]

    scratch = HERE / "_glmocr_images"
    processor, model = load()
    report = []

    for page in pages:
        print(f"\npage {page}: rendering at {DPI} DPI ...", flush=True)
        image = render(pdf, page, scratch)

        started = time.monotonic()
        text = read_page(processor, model, image)
        print(f"  model: {len(text)} chars in {time.monotonic() - started:.1f}s")

        dec_text = decoded(page, pdf)
        print(f"  decoder: {len(dec_text)} chars")

        score = agreement(text, dec_text)
        print(f"  agreement: {score:.1%}")

        report.append((page, text, dec_text, score))

    out = HERE / "result_glmocr.txt"
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
