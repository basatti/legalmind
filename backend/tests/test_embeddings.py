"""Tests for the embedding providers (LEG-13, stage 3)."""

import pytest

from embeddings import EmbeddingProvider, OfflineEmbeddingProvider


def length_of(vector: list[float]) -> float:
    return sum(value * value for value in vector) ** 0.5


# ---------------------------------------------------------------------------
# Shape of the result — what stage 4 depends on
# ---------------------------------------------------------------------------


def test_returns_one_vector_per_input() -> None:
    vectors = OfflineEmbeddingProvider().embed(["first", "second", "third"])
    assert len(vectors) == 3


def test_every_vector_has_the_declared_width() -> None:
    provider = OfflineEmbeddingProvider(dimensions=32)
    vectors = provider.embed(["first", "second"])
    assert all(len(vector) == provider.dimensions for vector in vectors)


def test_dimensions_reports_what_was_configured() -> None:
    assert OfflineEmbeddingProvider(dimensions=64).dimensions == 64


def test_an_empty_batch_returns_no_vectors() -> None:
    assert OfflineEmbeddingProvider().embed([]) == []


def test_results_come_back_in_the_order_they_were_sent() -> None:
    """Callers pair chunks to vectors by position, so order is a hard contract."""
    provider = OfflineEmbeddingProvider()
    batched = provider.embed(["alpha", "beta", "gamma"])
    one_at_a_time = [provider.embed([text])[0] for text in ("alpha", "beta", "gamma")]
    assert batched == one_at_a_time


# ---------------------------------------------------------------------------
# Determinism — what the content-hash / idempotency requirement rests on
# ---------------------------------------------------------------------------


def test_the_same_text_always_produces_the_same_vector() -> None:
    """Re-ingesting an unchanged document must not produce different vectors,
    or 'have I already ingested this?' stops having a meaningful answer."""
    provider = OfflineEmbeddingProvider()
    assert provider.embed(["a lease clause"]) == provider.embed(["a lease clause"])


def test_two_providers_agree_with_each_other() -> None:
    """Determinism must survive a restart, not just repeated calls in one process."""
    first = OfflineEmbeddingProvider(dimensions=32)
    second = OfflineEmbeddingProvider(dimensions=32)
    assert first.embed(["a lease clause"]) == second.embed(["a lease clause"])


def test_different_texts_produce_different_vectors() -> None:
    vectors = OfflineEmbeddingProvider().embed(["cat", "termination clause"])
    assert vectors[0] != vectors[1]


# ---------------------------------------------------------------------------
# Normalisation — what cosine similarity assumes (LEG-14)
# ---------------------------------------------------------------------------


def test_every_vector_has_length_one() -> None:
    vectors = OfflineEmbeddingProvider(dimensions=32).embed(["short", "a much longer piece"])
    assert all(length_of(vector) == pytest.approx(1.0) for vector in vectors)


def test_text_length_does_not_change_vector_length() -> None:
    """A long chunk and a short chunk both land on the sphere, so similarity
    depends on direction alone."""
    provider = OfflineEmbeddingProvider()
    short, long = provider.embed(["cat", "cat " * 500])
    assert length_of(short) == pytest.approx(length_of(long))


# ---------------------------------------------------------------------------
# Edge cases and contract
# ---------------------------------------------------------------------------


def test_empty_text_still_produces_a_usable_vector() -> None:
    vector = OfflineEmbeddingProvider().embed([""])[0]
    assert length_of(vector) == pytest.approx(1.0)


def test_arabic_text_is_embedded_like_any_other() -> None:
    vectors = OfflineEmbeddingProvider().embed(["نظام حماية الطفل", "child protection law"])
    assert all(length_of(vector) == pytest.approx(1.0) for vector in vectors)
    assert vectors[0] != vectors[1]


def test_dimensions_must_be_positive() -> None:
    with pytest.raises(ValueError):
        OfflineEmbeddingProvider(dimensions=0)


def test_the_interface_cannot_be_used_directly() -> None:
    with pytest.raises(TypeError):
        EmbeddingProvider()  # type: ignore[abstract]
