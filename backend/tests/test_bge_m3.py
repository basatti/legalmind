"""Tests for the BGE-M3 provider wrapper (LEG-58).

These exercise this wrapper's own logic only — batching, order,
normalisation, dimension validation — via a fake encoder standing in for
the real model. They never load BGE-M3 itself, so they run in milliseconds
and don't need `sentence-transformers` installed (it's an optional extra,
kept out of CI's default install on purpose — see pyproject.toml).
"""

import math

import pytest

from embeddings.bge_m3 import DIMENSIONS, BgeM3EmbeddingProvider


class FakeEncoder:
    """Deterministic stand-in for BGE-M3 — same shape, computable output."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[float(i + 1)] * DIMENSIONS for i, _ in enumerate(texts)]


class WrongWidthEncoder:
    """Simulates a misconfigured model producing the wrong vector width."""

    def encode(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


def provider() -> BgeM3EmbeddingProvider:
    return BgeM3EmbeddingProvider(model=FakeEncoder())


# ---------------------------------------------------------------------------
# Shape of the result
# ---------------------------------------------------------------------------


def test_dimensions_reports_the_real_models_width() -> None:
    assert provider().dimensions == DIMENSIONS


def test_returns_one_vector_per_input() -> None:
    vectors = provider().embed(["a", "b", "c"])
    assert len(vectors) == 3


def test_every_vector_has_the_declared_width() -> None:
    vectors = provider().embed(["a"])
    assert len(vectors[0]) == DIMENSIONS


def test_an_empty_batch_returns_no_vectors() -> None:
    assert provider().embed([]) == []


# ---------------------------------------------------------------------------
# Normalisation — required for cosine similarity to behave (LEG-14)
# ---------------------------------------------------------------------------


def test_vectors_are_normalised_to_unit_length() -> None:
    vectors = provider().embed(["a", "b"])
    for vector in vectors:
        length = math.sqrt(sum(value * value for value in vector))
        assert length == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Contract with the database column
# ---------------------------------------------------------------------------


def test_a_model_returning_the_wrong_width_is_rejected() -> None:
    with pytest.raises(ValueError, match="1024"):
        BgeM3EmbeddingProvider(model=WrongWidthEncoder()).embed(["a"])


def test_constructing_with_an_injected_model_never_touches_sentence_transformers() -> None:
    """If this test can even run, sentence_transformers was never imported —
    constructing with model= skips _load_default_model entirely."""
    import sys

    assert "sentence_transformers" not in sys.modules
    BgeM3EmbeddingProvider(model=FakeEncoder())
    assert "sentence_transformers" not in sys.modules
