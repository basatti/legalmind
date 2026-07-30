"""Shared JSONL writers for the reference-corpus fetch scripts (LEG-13).

Every source (ALARB, HRSD labor law, the MoJ portal) produces the same two
files, tagged with a `source` field so they can be told apart once combined:

    cases.jsonl   -- one line per Case, before chunking (the reproducibility
                     layer: re-chunk from here later without re-fetching).
    chunks.jsonl  -- one line per CaseChunk, ready to embed.

Each fetch script owns and overwrites its own pair of files (cases_<source>.jsonl,
chunks_<source>.jsonl) rather than appending to a shared file, so re-running a
script is idempotent instead of accumulating duplicates.
"""

import json
from collections.abc import Iterable
from pathlib import Path

from chunkers import Case, CaseChunk

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "corpus"


def write_cases_jsonl(source: str, cases: Iterable[Case]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"cases_{source}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for case in cases:
            record = {
                "source": source,
                "case_id": case.metadata.case_id,
                "court": case.metadata.court,
                "city": case.metadata.city,
                "date": case.metadata.date,
                "sections": [{"name": s.name, "text": s.text} for s in case.sections],
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def write_chunks_jsonl(source: str, chunks: Iterable[CaseChunk]) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"chunks_{source}.jsonl"
    with path.open("w", encoding="utf-8") as fh:
        for chunk in chunks:
            record = {
                "source": source,
                "case_id": chunk.case_id,
                "section": chunk.section,
                "chunk_index": chunk.chunk_index,
                "total_in_case": chunk.total_in_case,
                "header": chunk.header,
                "body": chunk.body,
                "text": chunk.text,
            }
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path
