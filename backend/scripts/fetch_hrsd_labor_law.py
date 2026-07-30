"""Fetch نظام العمل (the Labor Law) from HRSD's site and chunk it (LEG-13).

HRSD publishes the law across 16 pages, one per الباب (Part) — see
https://hrsd.gov.sa/knowledge-centre/نظام-العمل for the table of contents.
Each page's <main> content is clean, server-rendered HTML with articles
marked "المادة <ordinal>:". Unlike labor_system.pdf, there is no font
corruption to work around here — this is the reason that PDF was dropped
in favor of this source.

Usage:
    uv run --with requests,beautifulsoup4 python scripts/fetch_hrsd_labor_law.py
"""

import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _corpus_io import write_cases_jsonl, write_chunks_jsonl  # noqa: E402

from chunkers import Case, CaseChunker, CaseMetadata, CaseSection  # noqa: E402

SOURCE = "hrsd_labor_law"

# One node id per الباب, in order, from the table of contents.
_NODE_IDS = [
    5575978,
    5575980,
    5575987,
    5575994,
    5576001,
    5576008,
    5576015,
    5576022,
    5576027,
    5576029,
    5576036,
    5576041,
    5576043,
    5576050,
    5576057,
    5576064,
]

# An article heading is its own line, ending in a colon, e.g. "المادة الأولى:"
# or "المادة السابعة  :" (the site is inconsistent about spacing before the
# colon, hence \s*).
_ARTICLE_RE = re.compile(r"^(المادة\s+[^\n:]+?)\s*:\s*$", re.MULTILINE)


def _fetch_page_text(node_id: int) -> str:
    url = f"https://hrsd.gov.sa/node/{node_id}"
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    main = soup.find("main")
    return main.get_text("\n", strip=True) if main else ""


def _split_into_articles(text: str) -> list[CaseSection]:
    """Split one page's text into one CaseSection per المادة heading.

    Text before the first heading (chapter titles like "الفصل الأول") is
    dropped; text between one heading and the next becomes that article's
    body, including any chapter heading that falls inside it — a small,
    accepted imprecision rather than building full الباب/الفصل tracking.
    """
    matches = list(_ARTICLE_RE.finditer(text))
    sections = []
    for i, match in enumerate(matches):
        name = match.group(1).strip()
        start = match.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            sections.append(CaseSection(name=name, text=body))
    return sections


def fetch_labor_law() -> Case:
    all_sections: list[CaseSection] = []
    for node_id in _NODE_IDS:
        page_text = _fetch_page_text(node_id)
        all_sections.extend(_split_into_articles(page_text))
    return Case(metadata=CaseMetadata(case_id="نظام العمل"), sections=tuple(all_sections))


def main() -> None:
    case = fetch_labor_law()
    print(f"{len(case.sections)} articles fetched across {len(_NODE_IDS)} pages")
    chunks = CaseChunker(window_size=200, overlap=40).chunk(case)
    print(f"-> {len(chunks)} chunks\n")

    cases_path = write_cases_jsonl(SOURCE, [case])
    chunks_path = write_chunks_jsonl(SOURCE, chunks)
    print(f"wrote {cases_path}")
    print(f"wrote {chunks_path}")

    for c in chunks[:4]:
        print("---", f"chunk {c.chunk_index}/{c.total_in_case - 1}", "---")
        print(c.text)
        print()


if __name__ == "__main__":
    main()
