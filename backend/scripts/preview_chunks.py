"""Manual smoke-test: parse a PDF and print the chunks it produces.

Usage:
    uv run python scripts/preview_chunks.py path/to/file.pdf [--full]

By default each chunk is printed truncated to 200 characters; pass --full
to print the whole chunk text.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from chunkers import FixedSizeChunker  # noqa: E402
from parsers import PdfParser  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf_path", type=Path)
    parser.add_argument("--chunk-size", type=int, default=800, help="max characters per chunk")
    parser.add_argument("--overlap", type=int, default=100, help="characters shared between chunks")
    parser.add_argument("--full", action="store_true", help="print full chunk text, not a preview")
    parser.add_argument("--pages", help="1-based inclusive page range, e.g. 16-26")
    args = parser.parse_args()

    content = args.pdf_path.read_bytes()
    pages = PdfParser().parse(content)

    if args.pages:
        first, last = (int(part) for part in args.pages.split("-"))
        pages = [page for page in pages if first <= page.page_number <= last]

    chunks = FixedSizeChunker(chunk_size=args.chunk_size, overlap=args.overlap).chunk(pages)

    print(f"{len(pages)} pages -> {len(chunks)} chunks\n")
    for c in chunks:
        text = c.text if args.full else (c.text[:200] + ("…" if len(c.text) > 200 else ""))
        print(f"--- chunk {c.sequence} (page {c.page_number}, {len(c.text.split())} words) ---")
        print(text)
        print()


if __name__ == "__main__":
    main()
