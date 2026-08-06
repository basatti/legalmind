# Arabic PDF extraction — spike

A frozen snapshot of an investigation into getting clean, chunkable text out of
the `ahkam.pdf` legal-case corpus. **Not production code.** Nothing here is
imported by the app, nothing is linted (`scripts/spikes` is excluded in
`pyproject.toml`), and nothing is covered by tests.

It is here so the next person building real extraction starts from the answers
rather than rediscovering them. Roughly 1,900 lines of it are measurements, and
the measurements are worth more than the code.

## The problem

Arabic text in these PDFs **silently corrupts** on extraction. Not an error, not
a crash — plausible-looking text that is wrong. `pypdf`, `pdfminer` and
`pdfplumber` all fail identically, so it is not a library bug: the font tables
in the file map glyphs to the wrong characters.

Worse, the corruption is *readable*. That is what makes it dangerous for legal
text, and it is the thread running through everything below.

## Read in this order

**1. `twin_font_decode.py`** (385 lines) — the foundation. Decodes the page from
the PDF's own embedded font tables. Gets **characters** right — `قاصر عقلا`,
`المرافعات الشرعية`, every digit — and gets **lines** wrong, because it detects
two columns on a one-column page and splices the header panel into the body.
Every other script here scores itself against this one.

**2. `extract_full.py`** (451 lines) — the most complete pipeline, and the thing
to build on. Five stages: crop → OCR → clean → repair → chunk.

**3. `extract_hybrid.py`** (293 lines) — the anti-fabrication idea, and the
cleverest thing in the folder. See below.

Then, if you want the engine comparison: `extract_ocr.py` (EasyOCR),
`extract_glmocr.py` (GLM-OCR via transformers), `extract_ollama_ocr.py`
(Arabic-GLM-OCR-v2 via Ollama), `compare_ocr_models.py` (several, scored alike).

The four `result_*.txt` files are recorded output from real runs, not examples.

## The pipeline in `extract_full.py`

1. **CROP** — split the page above each section heading. This is what makes a
   chunk a chunk, and keeps a heading with the text it introduces.
2. **OCR** — EasyOCR on each crop separately. Reads pixels, so broken font
   tables are irrelevant, and a small single-topic crop beats a whole page.
3. **CLEAN** — `gemma4`, allowed to fix only four named OCR error classes and
   required to write `[?]` for anything else.
4. **REPAIR** — boxed header panels only, taken from the decoder instead of OCR.
5. **CHUNK** — `CaseChunker`, 200-word windows, 40 overlap, never crossing a
   section boundary, every chunk stamped with the case id.

Each stage degrades to the next-best option on its own evidence: no red rules
found → split on whitespace; no panel fill found → repair nothing; decoder reads
nothing (an ordinary PDF, or a scan) → use OCR unchanged. A repair can only ever
replace a line the decoder demonstrably covers, so text is never silently
dropped.

## The findings that cost days

**LLMs fabricate, fluently, and confidence does not catch it.**
`gemma4` turned `قاصر عقلا` (mentally incapacitated) into `قاصر عقار` (real
estate). It reads perfectly and changes who the case is about. This is the
single most important thing in this folder.

**What stopped it: naming the permitted edits.** A vague "be faithful"
instruction did not work. Listing exactly four allowed correction classes and
requiring `[?]` for anything else did.

**And what proves it stopped: a mechanical check, not a promise.**
`extract_hybrid.py` gives the model only *reordering* work — the characters
arrive already correct from the decoder. A pure reordering must preserve the
exact multiset of characters, so `verify()` can diff them and print anything
added or dropped. A fabrication cannot pass silently. **Any future LLM stage
should be shaped so its output is checkable this way.**

**OCR clips characters at detection-box edges, and confidence is useless there.**
Measured on page 16: the box for `تاريخها:١٤٣٣` stopped 186px short of its
neighbour and cut the leading `١`, reporting `٤٣٣` at confidence **0.94 — the
highest on the page**. The same edge effect turned `رقم القرار` into
`قم القرار`. This is why boxed panels are repaired from the decoder rather than
trusted from OCR.

**EasyOCR keeps Arabic-Indic digits. Tesseract converts them to Latin** — which
is disqualifying for case numbers and dates.

**300 DPI beat 600+** on this document. Higher was worse, not better.

**Cropping is not cosmetic.** The article slash in `٢/٢٥٨` survives cropping and
is lost without it.

**Two independent readers are the only trustworthy signal.** The decoder reads
font tables; OCR reads pixels. They share no machinery, so for both to be wrong
the same way they would have to fail identically. Agreement is evidence;
either one alone is not.

## Measured agreement

From the `result_*.txt` files, page 16, agreement with the twin-font decoder:

| reader | agreement |
|---|---|
| EasyOCR @ 300 DPI | 20.7% |
| Arabic-GLM-OCR-v2 (Ollama) | 0.2% |

**Read these as a relative ranking, not as accuracy.** The decoder's *line
order* is scrambled on this page, so raw string agreement is low even where both
readers are individually fine. What the numbers establish is that the
Arabic-GLM-OCR fine-tune was not usable, and EasyOCR was.

`result_full.txt` is the one to look at for the pipeline actually working — each
section reports `invented: nothing`.

## Still unsolved

- **The decoder's layout.** Characters right, lines wrong. Column detection
  fires on a one-column page. This is the highest-value thing left.
- **`compare_ocr_models.py` was never concluded.** It runs, but no model has
  been picked on its evidence.
- **Nothing is wired into ingestion.** `extract_full.py` produces chunks via
  `CaseChunker`, but nothing writes them through the real pipeline.
- **One document.** Everything here is measured on `ahkam.pdf` pages 16–21. It
  is not known how much generalises to the rest of the corpus.

## Running them

⚠️ **The source PDF is not in the repo.** These scripts default to
`~/Downloads/ahkam.pdf`. Get the corpus separately.

Dependencies are deliberately kept out of `backend/.venv` — they are large and
none of them belong in the app:

```bash
# twin-font decoder
uv run --python 3.12 --with fonttools --with pypdf --with python-bidi \
    python twin_font_decode.py

# EasyOCR cross-check
uv run --python 3.12 --with easyocr --with pillow python extract_ocr.py 16

# the full pipeline
uv run --python 3.12 --with easyocr --with pillow --with numpy --with httpx \
    --with python-dotenv --with fonttools --with pypdf \
    python extract_full.py 16 17
```

`--no-project` is needed for the transformers-based ones, or uv tries to rebuild
`backend/.venv` for 3.12. Poppler is required for page rendering. The Ollama
route exists because a 4GB Pascal GPU predates bfloat16 and PyTorch either
crashes or crawls on it — Ollama quantises and splits layers instead.

## Related

- `backend/src/parsers/pdf_parser.py` — the real parser in the app
- `backend/src/chunkers/case_chunker.py` — used by `extract_full.py` stage 5
- Whether OCR belongs in the product at all is a scope decision for Bassel, not
  one to settle from this folder.
