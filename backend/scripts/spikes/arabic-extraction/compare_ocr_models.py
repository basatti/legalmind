"""Run several OCR models over the same pages and score them the same way.

    uv run --no-project --python 3.12 --with transformers --with torch \
        --with torchvision --with accelerate --with pillow --with safetensors \
        python scripts/compare_ocr_models.py 16 21

--no-project keeps uv from rebuilding backend/.venv for 3.12. torchvision is
needed because the processor bundles a video handler that imports it, even
though nothing here processes video.

Add --sdk to also run the base model through its own glmocr package, which
includes the layout-analysis stage (needs: --with glmocr).

Two models, one question. zai-org/GLM-OCR is the base: 0.9B, MIT licence, top of
the document-parsing leaderboard - but Arabic is not one of its eight listed
languages. sherif1313/Arabic-GLM-OCR-v2 is a community fine-tune of it aimed at
Arabic, with no published accuracy numbers and a card that advertises "intelligent
spelling correction" as a feature. For a legal transcript that is not a feature;
it is the failure that made gemma4 unusable (قاصر عقلا -> قاصر عقار, which reads
perfectly and changes who the case is about).

So this measures three things per page:

  * agreement with the twin-font decoder - the only independent evidence, since
    the decoder reads font tables and shares no machinery with a vision model
  * agreement between the two models - where they diverge is where fine-tuning
    changed something, which is where autocorrection would show up
  * seconds per page - EasyOCR's 82s/page on CPU is the bar to beat

Both models run through the same transformers code path on purpose. If their
outputs differ, that difference is the weights and nothing else.
"""

import gc
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from extract_glmocr import pick_dtype  # noqa: E402
from extract_ocr import DPI, agreement, decoded, render  # noqa: E402

HERE = Path(__file__).resolve().parent
DEFAULT_PDF = Path.home() / "Downloads" / "ahkam.pdf"

BASE = "zai-org/GLM-OCR"
ARABIC = "sherif1313/Arabic-GLM-OCR-v2"

# A judgment page runs well past the fine-tune card's suggested 512; at that
# setting the output stops mid-sentence and looks like a model failure.
MAX_NEW_TOKENS = 2048

# Naming the forbidden edits is what stopped fabrication in the gemma4 work -
# not sternness in general. "Text Recognition:" is the phrasing the fine-tune
# was trained on, so it stays as the opening.
#
# Caveat worth knowing: the base model may have been trained on different task
# prompts, which its own SDK would supply correctly. Running it here with the
# fine-tune's prompt is an approximation, and --sdk is the honest version.
PROMPT = (
    "Text Recognition: Extract the Arabic text exactly as printed. "
    "Do not correct spelling. Do not complete words. Do not change any number. "
    "If something is unreadable, output [?] rather than a guess."
)


def load(model_id: str):
    from transformers import AutoModelForImageTextToText, AutoProcessor

    print(f"\n=== {model_id} ===")
    print("  loading (~2GB, downloads on first run) ...", flush=True)

    dtype = pick_dtype()
    processor = AutoProcessor.from_pretrained(model_id, trust_remote_code=True)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
    )
    model.eval()
    print(f"  running on {next(model.parameters()).device} as {dtype}")
    return processor, model


def unload(processor, model) -> None:
    """Free one model before loading the next; two at once is needless memory."""
    import torch

    del processor, model
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def read_page(processor, model, image: Path) -> str:
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
        # Greedy. Sampling is where invented text comes from, so for a
        # transcription task it is simply switched off - which also makes
        # temperature irrelevant, whatever the model card suggests.
        generated = model.generate(
            **inputs,
            max_new_tokens=MAX_NEW_TOKENS,
            do_sample=False,
            repetition_penalty=1.1,
        )

    new_tokens = generated[0][inputs["input_ids"].shape[1]:]
    return processor.decode(new_tokens, skip_special_tokens=True).strip()


def run_transformers(model_id: str, images: dict[int, Path]) -> dict[int, tuple[str, float]]:
    processor, model = load(model_id)
    out = {}
    for page, image in images.items():
        started = time.monotonic()
        text = read_page(processor, model, image)
        elapsed = time.monotonic() - started
        print(f"  page {page}: {len(text)} chars in {elapsed:.1f}s")
        out[page] = (text, elapsed)
    unload(processor, model)
    return out


def run_sdk(images: dict[int, Path]) -> dict[int, tuple[str, float]]:
    """The base model through its own package, which adds the layout stage.

    That stage is a large part of why it tops the leaderboard, and reading order
    on the boxed panels is exactly our weak spot - so it is worth measuring
    separately from the plain transformers path.
    """
    try:
        from glmocr import parse
    except ImportError:
        print("\n  glmocr package not installed - skipping --sdk run.")
        print("  Add --with glmocr, or check the package name in the repo README.")
        return {}

    print(f"\n=== {BASE} via glmocr SDK (with layout analysis) ===")
    out = {}
    for page, image in images.items():
        started = time.monotonic()
        result = parse(str(image))
        elapsed = time.monotonic() - started
        text = getattr(result, "text", None) or str(result)
        print(f"  page {page}: {len(text)} chars in {elapsed:.1f}s")
        out[page] = (text.strip(), elapsed)
    return out


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    pages = [int(a) for a in args if a.isdigit()]
    pdf = Path(next((a for a in args if not a.isdigit()), DEFAULT_PDF))
    use_sdk = "--sdk" in sys.argv

    # 16 has a decoder reading to check against; 21 is where the decoder gives
    # up entirely, so it is the page that shows whether a model adds anything.
    if not pages:
        pages = [16, 21]

    scratch = HERE / "_glmocr_images"
    images = {}
    for page in pages:
        print(f"page {page}: rendering at {DPI} DPI ...", flush=True)
        images[page] = render(pdf, page, scratch)

    reference = {page: decoded(page, pdf) for page in pages}
    for page, text in reference.items():
        print(f"  decoder, page {page}: {len(text)} chars")

    runs: dict[str, dict[int, tuple[str, float]]] = {
        BASE: run_transformers(BASE, images),
        ARABIC: run_transformers(ARABIC, images),
    }
    if use_sdk:
        sdk = run_sdk(images)
        if sdk:
            runs[f"{BASE} (SDK)"] = sdk

    print("\n" + "=" * 68)
    print("agreement with the twin-font decoder (EasyOCR scored 92% on page 16)")
    print("=" * 68)
    header = "model".ljust(38) + "".join(f"p{p}".rjust(10) for p in pages)
    print(header)
    for name, result in runs.items():
        cells = ""
        for page in pages:
            text = result.get(page, ("", 0.0))[0]
            cells += f"{agreement(text, reference[page]):.1%}".rjust(10)
        print(name.ljust(38) + cells)

    print("\nagreement between base and fine-tune (low = fine-tuning changed the text)")
    for page in pages:
        base_text = runs[BASE].get(page, ("", 0.0))[0]
        arabic_text = runs[ARABIC].get(page, ("", 0.0))[0]
        print(f"  page {page}: {agreement(base_text, arabic_text):.1%}")

    print("\nseconds per page (EasyOCR was 82s on CPU)")
    for name, result in runs.items():
        times = [f"{result[p][1]:.1f}s" for p in pages if p in result]
        print(f"  {name.ljust(36)} {'  '.join(times)}")

    out = HERE / "result_ocr_models.txt"
    with out.open("w", encoding="utf-8") as fh:
        fh.write(f"OCR model comparison @ {DPI} DPI, greedy\n")
        fh.write("=" * 68 + "\n\n")
        for page in pages:
            fh.write(f"########## PAGE {page} ##########\n\n")
            for name, result in runs.items():
                text, elapsed = result.get(page, ("(not run)", 0.0))
                score = agreement(text, reference[page])
                fh.write(f"===== {name} — {score:.1%} agreement, {elapsed:.1f}s =====\n")
                fh.write(f"{text}\n\n")
            fh.write("===== twin-font decoder =====\n")
            fh.write(f"{reference[page] or '(nothing recovered)'}\n\n")

    print(f"\nWrote {out}")
    if os.name == "nt":
        subprocess.Popen(["notepad.exe", str(out)])


if __name__ == "__main__":
    main()
