"""Tests for structure-aware case chunking (LEG-13)."""

import pytest

from chunkers import Case, CaseChunker, CaseMetadata, CaseSection


def _case(sections: list[tuple[str, str]], **meta) -> Case:
    return Case(
        metadata=CaseMetadata(case_id=meta.pop("case_id", "C-1"), **meta),
        sections=tuple(CaseSection(name=name, text=text) for name, text in sections),
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_rejects_overlap_equal_to_window_size() -> None:
    with pytest.raises(ValueError, match="overlap"):
        CaseChunker(window_size=5, overlap=5)


def test_rejects_negative_overlap() -> None:
    with pytest.raises(ValueError, match="overlap"):
        CaseChunker(window_size=5, overlap=-1)


def test_rejects_non_positive_window_size() -> None:
    with pytest.raises(ValueError, match="window_size"):
        CaseChunker(window_size=0, overlap=0)


# ---------------------------------------------------------------------------
# Section boundaries are never crossed
# ---------------------------------------------------------------------------


def test_two_short_sections_stay_in_separate_chunks_even_under_one_window() -> None:
    """A window big enough to hold both sections combined must not merge
    them — facts and verdict are different things, chunk() must not blend
    them just because they'd both fit in one window."""
    case = _case([("الوقائع", "a b c"), ("نص الحكم", "d e f")])
    chunks = CaseChunker(window_size=200, overlap=40).chunk(case)
    assert [c.section for c in chunks] == ["الوقائع", "نص الحكم"]
    assert chunks[0].body == "a b c"
    assert chunks[1].body == "d e f"


def test_overlap_never_bridges_a_section_boundary() -> None:
    case = _case([("الوقائع", "a b c d e"), ("الأسباب", "f g h i j")])
    chunks = CaseChunker(window_size=5, overlap=2).chunk(case)
    # Each section is exactly one window here (5 words, window_size=5), so
    # there should be exactly one chunk per section, with no words from
    # الوقائع's tail leaking into الأسباب's chunk.
    assert len(chunks) == 2
    assert chunks[0].body == "a b c d e"
    assert chunks[1].body == "f g h i j"


def test_a_long_section_still_slides_a_window_with_overlap_inside_itself() -> None:
    words = list("abcdefgh")  # 8 words
    case = _case([("الوقائع", " ".join(words))])
    chunks = CaseChunker(window_size=5, overlap=2).chunk(case)
    assert [c.body for c in chunks] == ["a b c d e", "d e f g h"]
    assert [c.section for c in chunks] == ["الوقائع", "الوقائع"]


# ---------------------------------------------------------------------------
# Header — what "connects" chunks of the same case
# ---------------------------------------------------------------------------


def test_header_carries_case_id_and_section() -> None:
    case = _case([("الوقائع", "some facts")], case_id="4630103285-1446")
    chunk = CaseChunker().chunk(case)[0]
    assert "4630103285-1446" in chunk.header
    assert "الوقائع" in chunk.header


def test_header_includes_court_city_and_date_when_present() -> None:
    case = _case(
        [("الوقائع", "some facts")],
        case_id="C-1",
        court="المحكمة التجارية",
        city="بريدة",
        date="٤ ذو الحِجّة ١٤٤٦",
    )
    chunk = CaseChunker().chunk(case)[0]
    assert "المحكمة التجارية" in chunk.header
    assert "بريدة" in chunk.header
    assert "٤ ذو الحِجّة ١٤٤٦" in chunk.header


def test_header_omits_missing_optional_fields_cleanly() -> None:
    """ALARB has no court/city/date — the header must not print 'None'."""
    case = _case([("الوقائع", "some facts")], case_id="ALARB-0")
    chunk = CaseChunker().chunk(case)[0]
    assert "None" not in chunk.header


def test_text_property_is_header_plus_body() -> None:
    case = _case([("الوقائع", "some facts")], case_id="C-1")
    chunk = CaseChunker().chunk(case)[0]
    assert chunk.text == f"{chunk.header}\n{chunk.body}"


# ---------------------------------------------------------------------------
# Every chunk knows its place within the case
# ---------------------------------------------------------------------------


def test_chunk_index_and_total_in_case_are_consistent() -> None:
    case = _case([("الوقائع", "a b c"), ("الأسباب", "d e f"), ("نص الحكم", "g h i")])
    chunks = CaseChunker(window_size=200, overlap=40).chunk(case)
    assert [c.chunk_index for c in chunks] == [0, 1, 2]
    assert all(c.total_in_case == 3 for c in chunks)


def test_every_chunk_carries_the_same_case_id() -> None:
    case = _case([("الوقائع", "a b c"), ("نص الحكم", "d e f")], case_id="C-42")
    chunks = CaseChunker().chunk(case)
    assert all(c.case_id == "C-42" for c in chunks)


# ---------------------------------------------------------------------------
# One case never leaks into the next
# ---------------------------------------------------------------------------


def test_chunking_two_cases_separately_never_links_or_continues_them() -> None:
    chunker = CaseChunker(window_size=200, overlap=40)
    case_a = _case([("الوقائع", "a b c")], case_id="A")
    case_b = _case([("الوقائع", "x y z")], case_id="B")

    chunks_a = chunker.chunk(case_a)
    chunks_b = chunker.chunk(case_b)

    assert all(c.case_id == "A" for c in chunks_a)
    assert all(c.case_id == "B" for c in chunks_b)
    # Each case's own numbering starts fresh — case B's index isn't offset
    # by however many chunks case A produced.
    assert chunks_a[0].chunk_index == 0
    assert chunks_b[0].chunk_index == 0


def test_empty_section_produces_no_chunk() -> None:
    case = _case([("الوقائع", ""), ("نص الحكم", "g h i")])
    chunks = CaseChunker().chunk(case)
    assert [c.section for c in chunks] == ["نص الحكم"]
