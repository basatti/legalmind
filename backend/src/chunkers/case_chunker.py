"""Structure-aware chunking for whole legal cases (LEG-13).

Unlike FixedSizeChunker (which slides a window across a single parsed PDF's
pages), this operates on a whole *case* made of named sections — facts,
reasoning, cited law, verdict — coming from a structured source such as the
ALARB dataset or a scraped court-portal record.

Design choices, and why:

* Sections are chunked independently. A sliding window is only applied
  *within* one section; it never crosses a section boundary. Facts and
  verdict are semantically distinct — blending them via overlap would
  produce a chunk that reads as neither.
* Every chunk carries the same case_id and a prepended header line. That is
  what "connects" chunks belonging to one case: a retrieval step can group
  hits by case_id, and an embedding model sees enough context (case id,
  court, section) to make sense of a chunk read in isolation — "حكمت الدائرة
  بإلزام..." means little on its own without knowing which case it's from.
* Nothing here carries state between one case and the next. chunk()
  processes one Case and returns a self-contained result, so two cases
  chunked back-to-back can never share an overlapping window or a
  continued index — a new case is always a hard boundary.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CaseMetadata:
    """Identifying facts about one case, independent of its section text."""

    case_id: str
    court: str | None = None
    city: str | None = None
    date: str | None = None


@dataclass(frozen=True)
class CaseSection:
    """One named part of a case, e.g. ("الوقائع", "تتحصل وقائع...")."""

    name: str
    text: str


@dataclass(frozen=True)
class Case:
    """A whole legal case, ready to be split into chunks."""

    metadata: CaseMetadata
    sections: tuple[CaseSection, ...]


@dataclass(frozen=True)
class CaseChunk:
    """One chunk of one case, carrying enough to stand alone and to be
    traced back to the case and section it came from."""

    header: str
    body: str
    case_id: str
    section: str
    chunk_index: int  # position within this case, across all its sections
    total_in_case: int

    @property
    def text(self) -> str:
        """Header plus body — what actually gets embedded."""
        return f"{self.header}\n{self.body}"


def _build_header(metadata: CaseMetadata, section: str) -> str:
    parts = [f"القضية {metadata.case_id}"]
    if metadata.court:
        parts.append(metadata.court)
    if metadata.city:
        parts.append(metadata.city)
    if metadata.date:
        parts.append(metadata.date)
    parts.append(f"القسم: {section}")
    return "[" + " | ".join(parts) + "]"


class CaseChunker:
    """Sliding-window chunker that never crosses a section or case boundary.

    - window_size: max words per chunk.
    - overlap: words repeated between consecutive chunks of the *same*
      section (must be < window_size).
    """

    def __init__(self, window_size: int = 200, overlap: int = 40):
        if window_size <= 0:
            raise ValueError("window_size must be positive")
        if overlap < 0:
            raise ValueError("overlap must not be negative")
        if overlap >= window_size:
            raise ValueError("overlap must be smaller than window_size")
        self.window_size = window_size
        self.overlap = overlap
        self.step = window_size - overlap

    def _windows(self, text: str) -> list[str]:
        words = text.split()
        if not words:
            return []
        windows = []
        start = 0
        while start < len(words):
            end = start + self.window_size
            windows.append(" ".join(words[start:end]))
            if end >= len(words):
                break
            start += self.step
        return windows

    def chunk(self, case: Case) -> list[CaseChunk]:
        """Split one case into chunks. Section order is preserved; within a
        section, a long text becomes several overlapping windows."""
        pieces = [
            (section.name, window)
            for section in case.sections
            for window in self._windows(section.text)
        ]
        total = len(pieces)
        return [
            CaseChunk(
                header=_build_header(case.metadata, section_name),
                body=body,
                case_id=case.metadata.case_id,
                section=section_name,
                chunk_index=index,
                total_in_case=total,
            )
            for index, (section_name, body) in enumerate(pieces)
        ]
