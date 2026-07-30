"""Persist the full ALARB dataset (commercial-court cases) to JSONL (LEG-13).

ALARB has no case number, court, city, or date columns -- each row is just
case_facts / court_reasoning / applicable_laws / verdict, so the row's
position in its split (train/test) is used as case_id.

Usage:
    uv run --with datasets,pandas python scripts/fetch_alarb.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from _corpus_io import write_cases_jsonl, write_chunks_jsonl  # noqa: E402

from chunkers import Case, CaseChunker, CaseMetadata, CaseSection  # noqa: E402

SOURCE = "alarb"

_SECTION_LABELS = {
    "case_facts": "الوقائع",
    "court_reasoning": "الأسباب",
    "applicable_laws": "السند النظامي",
    "verdict": "نص الحكم",
}


def _row_to_case(split: str, index: int, row: dict) -> Case:
    def as_text(column: str) -> str:
        value = row[column]
        return "\n".join(value) if isinstance(value, list) else value

    sections = tuple(
        CaseSection(name=label, text=as_text(column)) for column, label in _SECTION_LABELS.items()
    )
    return Case(metadata=CaseMetadata(case_id=f"ALARB-{split}-{index}"), sections=sections)


def main() -> None:
    from datasets import load_dataset

    chunker = CaseChunker(window_size=200, overlap=40)
    all_cases: list[Case] = []
    all_chunks = []

    for split in ("train", "test"):
        dataset = load_dataset("THIQAH-RD/ALARB", split=split)
        print(f"{split}: {len(dataset)} rows")
        for i in range(len(dataset)):
            case = _row_to_case(split, i, dataset[i])
            all_cases.append(case)
            all_chunks.extend(chunker.chunk(case))

    print(f"\ntotal cases: {len(all_cases)}")
    print(f"total chunks: {len(all_chunks)}")

    cases_path = write_cases_jsonl(SOURCE, all_cases)
    chunks_path = write_chunks_jsonl(SOURCE, all_chunks)
    print(f"wrote {cases_path}")
    print(f"wrote {chunks_path}")


if __name__ == "__main__":
    main()
