"""Tests for the text chunkers (LEG-13, stage 2)."""

import dataclasses

import pytest

from chunkers import Chunk, Chunker, FixedSizeChunker
from parsers import ParsedPage


def page(number: int, text: str) -> ParsedPage:
    return ParsedPage(page_number=number, text=text)


def words(count: int, word: str = "contract") -> str:
    """A page of identical whole words, so a mid-word cut is easy to spot."""
    return " ".join([word] * count)


def digits(length: int) -> str:
    """Text with no whitespace at all, so cuts land at exact offsets."""
    return "".join(str(index % 10) for index in range(length))


# ---------------------------------------------------------------------------
# Splitting
# ---------------------------------------------------------------------------


def test_a_short_page_becomes_a_single_chunk() -> None:
    chunks = FixedSizeChunker().chunk([page(1, "One short clause.")])
    assert len(chunks) == 1
    assert chunks[0].text == "One short clause."


def test_a_long_page_is_split_into_several_chunks() -> None:
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(1, words(100))])
    assert len(chunks) > 1


def test_no_chunk_is_larger_than_the_configured_size() -> None:
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(1, words(200))])
    assert all(len(chunk.text) <= 100 for chunk in chunks)


def test_cuts_prefer_whole_words() -> None:
    """A chunk should not end halfway through a word when a space is nearby."""
    chunker = FixedSizeChunker(chunk_size=100, overlap=0)
    chunks = chunker.chunk([page(1, words(100))])
    assert chunks[0].text.split()[-1] == "contract"


def test_overlap_does_not_begin_mid_word() -> None:
    """The overlap rewind must land on a word boundary, not an arbitrary offset."""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(1, words(100))])
    assert all(chunk.text.split()[0] == "contract" for chunk in chunks)


# ---------------------------------------------------------------------------
# Sequence numbers — what makes neighbour lookup possible later (LEG-14)
# ---------------------------------------------------------------------------


def test_sequence_numbers_start_at_zero_and_have_no_gaps() -> None:
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(1, words(200))])
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))


def test_sequence_numbers_continue_across_pages() -> None:
    """Numbering is per document, not per page — otherwise the last chunk of
    page 1 and the first of page 2 would not look like neighbours."""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(1, words(50)), page(2, words(50))])
    assert [chunk.sequence for chunk in chunks] == list(range(len(chunks)))
    assert len({chunk.page_number for chunk in chunks}) == 2


def test_chunks_never_span_a_page_boundary() -> None:
    """Every chunk must belong to exactly one page so a citation cannot lie."""
    chunker = FixedSizeChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk([page(4, words(40)), page(9, words(40))])
    assert {chunk.page_number for chunk in chunks} == {4, 9}


# ---------------------------------------------------------------------------
# Overlap
# ---------------------------------------------------------------------------


def test_overlap_repeats_the_end_of_the_previous_chunk() -> None:
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    chunks = chunker.chunk([page(1, digits(200))])
    assert chunks[0].text[-10:] == chunks[1].text[:10]


def test_zero_overlap_repeats_nothing() -> None:
    chunker = FixedSizeChunker(chunk_size=50, overlap=0)
    chunks = chunker.chunk([page(1, digits(200))])
    rejoined = "".join(chunk.text for chunk in chunks)
    assert rejoined == digits(200)


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------


def test_an_empty_page_produces_no_chunks() -> None:
    assert FixedSizeChunker().chunk([page(1, "")]) == []


def test_a_whitespace_only_page_produces_no_chunks() -> None:
    assert FixedSizeChunker().chunk([page(1, "   \n\n   ")]) == []


def test_an_empty_page_does_not_consume_a_sequence_number() -> None:
    chunks = FixedSizeChunker().chunk([page(1, ""), page(2, "Real content.")])
    assert len(chunks) == 1
    assert chunks[0].sequence == 0
    assert chunks[0].page_number == 2


# ---------------------------------------------------------------------------
# Configuration and contract
# ---------------------------------------------------------------------------


def test_chunk_size_must_be_positive() -> None:
    with pytest.raises(ValueError):
        FixedSizeChunker(chunk_size=0)


def test_overlap_cannot_reach_half_the_chunk_size() -> None:
    with pytest.raises(ValueError):
        FixedSizeChunker(chunk_size=100, overlap=51)


def test_overlap_cannot_be_negative() -> None:
    with pytest.raises(ValueError):
        FixedSizeChunker(chunk_size=100, overlap=-1)


def test_chunker_interface_cannot_be_used_directly() -> None:
    with pytest.raises(TypeError):
        Chunker()  # type: ignore[abstract]


def test_chunk_cannot_be_modified_after_creation() -> None:
    chunk = Chunk(sequence=0, page_number=1, text="original")
    with pytest.raises(dataclasses.FrozenInstanceError):
        chunk.text = "tampered"  # type: ignore[misc]
