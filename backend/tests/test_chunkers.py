"""Tests for the document chunkers (LEG-57)."""

import pytest

from chunkers import Chunk, Chunker, FixedSizeChunker
from parsers import ParsedPage


def page(number: int, text: str) -> ParsedPage:
    return ParsedPage(page_number=number, text=text)


def words(count: int, stem: str = "word") -> str:
    """A predictable run of distinct words, e.g. 'word0 word1 word2'."""
    return " ".join(f"{stem}{index}" for index in range(count))


# --- interface -------------------------------------------------------------


def test_fixed_size_chunker_satisfies_the_interface() -> None:
    assert isinstance(FixedSizeChunker(), Chunker)


def test_chunker_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        Chunker()  # type: ignore[abstract]


# --- basic behaviour -------------------------------------------------------


def test_short_page_becomes_a_single_chunk() -> None:
    chunks = FixedSizeChunker().chunk([page(1, "a short page")])
    assert chunks == [Chunk(sequence=0, page_number=1, text="a short page")]


def test_no_pages_produces_no_chunks() -> None:
    assert FixedSizeChunker().chunk([]) == []


def test_empty_page_is_skipped() -> None:
    chunks = FixedSizeChunker().chunk([page(1, ""), page(2, "real text")])
    assert [c.page_number for c in chunks] == [2]


def test_whitespace_only_page_is_skipped() -> None:
    assert FixedSizeChunker().chunk([page(1, "   \n\n  ")]) == []


# --- splitting -------------------------------------------------------------


def test_long_page_is_split_into_several_chunks() -> None:
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(1, words(60))])
    assert len(chunks) > 1


def test_no_chunk_exceeds_the_size_limit() -> None:
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(1, words(60))])
    assert all(len(c.text) <= 50 for c in chunks)


def test_words_are_never_split_across_chunks() -> None:
    original = words(60)
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(1, original)])
    allowed = set(original.split())
    assert all(word in allowed for c in chunks for word in c.text.split())


def test_every_word_survives_somewhere() -> None:
    original = words(60)
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(1, original)])
    seen = {word for c in chunks for word in c.text.split()}
    assert seen == set(original.split())


def test_a_single_word_longer_than_the_limit_is_still_emitted() -> None:
    giant = "x" * 200
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(1, giant)])
    assert [c.text for c in chunks] == [giant]


# --- overlap ---------------------------------------------------------------


def test_consecutive_chunks_share_text() -> None:
    chunks = FixedSizeChunker(chunk_size=50, overlap=20).chunk([page(1, words(60))])
    first_tail = set(chunks[0].text.split())
    second_head = set(chunks[1].text.split())
    assert first_tail & second_head


def test_zero_overlap_shares_nothing() -> None:
    chunks = FixedSizeChunker(chunk_size=50, overlap=0).chunk([page(1, words(60))])
    assert not set(chunks[0].text.split()) & set(chunks[1].text.split())


# --- page numbers and sequence ---------------------------------------------


def test_page_number_is_carried_onto_every_chunk() -> None:
    chunks = FixedSizeChunker(chunk_size=50, overlap=10).chunk([page(7, words(60))])
    assert all(c.page_number == 7 for c in chunks)


def test_chunks_never_span_a_page_boundary() -> None:
    chunker = FixedSizeChunker(chunk_size=1000, overlap=100)
    chunks = chunker.chunk([page(1, "first page text"), page(2, "second page text")])
    assert [c.text for c in chunks] == ["first page text", "second page text"]


def test_sequence_runs_across_the_whole_document() -> None:
    chunker = FixedSizeChunker(chunk_size=50, overlap=10)
    chunks = chunker.chunk([page(1, words(40)), page(2, words(40))])
    assert [c.sequence for c in chunks] == list(range(len(chunks)))


# --- configuration ---------------------------------------------------------


@pytest.mark.parametrize("size", [0, -1])
def test_chunk_size_must_be_positive(size: int) -> None:
    with pytest.raises(ValueError, match="chunk_size"):
        FixedSizeChunker(chunk_size=size)


@pytest.mark.parametrize("overlap", [-1, 50, 80])
def test_overlap_must_be_smaller_than_chunk_size(overlap: int) -> None:
    with pytest.raises(ValueError, match="overlap"):
        FixedSizeChunker(chunk_size=50, overlap=overlap)
