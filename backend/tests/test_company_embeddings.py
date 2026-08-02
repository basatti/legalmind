"""Tests for the company-hosted embedding provider (LEG-58).

No server is contacted. A mock transport stands in for the network.
"""

import json

import httpx
import pytest

from embeddings.company_api import CompanyEmbeddingProvider, EmbeddingError


def transport_returning(payload: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


def provider(**kwargs) -> CompanyEmbeddingProvider:
    kwargs.setdefault("api_url", "https://example.invalid")
    kwargs.setdefault("api_key", "sk-test")
    kwargs.setdefault("dimensions", 4)
    return CompanyEmbeddingProvider(**kwargs)


def embedding_payload(vectors: list[list[float]]) -> dict:
    return {
        "data": [
            {"object": "embedding", "index": i, "embedding": vector}
            for i, vector in enumerate(vectors)
        ],
        "model": "bge-m3",
        "object": "list",
    }


# --- the happy path --------------------------------------------------------


def test_returns_one_vector_per_input_in_order() -> None:
    payload = embedding_payload([[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]])
    p = provider(transport=transport_returning(payload))

    vectors = p.embed(["first", "second"])

    print(vectors)
    assert vectors == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]


def test_out_of_order_index_fields_are_reordered_to_match_the_request() -> None:
    """The API is allowed to return rows out of order — index says where each
    one actually belongs, and callers pair vectors to inputs by position."""
    payload = {
        "data": [
            {"index": 1, "embedding": [0.0, 1.0, 0.0, 0.0]},
            {"index": 0, "embedding": [1.0, 0.0, 0.0, 0.0]},
        ]
    }
    p = provider(transport=transport_returning(payload))

    vectors = p.embed(["first", "second"])

    assert vectors == [[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]


def test_an_empty_batch_returns_no_vectors_and_makes_no_request() -> None:
    called = False

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=embedding_payload([]))

    p = provider(transport=httpx.MockTransport(handler))
    assert p.embed([]) == []
    assert not called


def test_dimensions_reports_the_configured_width() -> None:
    assert provider(dimensions=1024).dimensions == 1024


def test_the_request_carries_the_model_input_and_auth() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json=embedding_payload([[1.0, 0.0, 0.0, 0.0]]))

    p = provider(
        model="test-model",
        api_url="http://example:8443",
        api_key="sk-secret",
        transport=httpx.MockTransport(handler),
    )
    p.embed(["hello"])

    print(seen)
    assert seen["model"] == "test-model"
    assert seen["input"] == ["hello"]
    assert seen["url"] == "http://example:8443/v1/embeddings"
    assert seen["auth"] == "Bearer sk-secret"


def test_a_trailing_slash_on_the_api_url_does_not_double_up() -> None:
    p = provider(api_url="http://example:8443/")
    assert p.api_url == "http://example:8443"


# --- every way it can fail -------------------------------------------------


def test_an_error_status_becomes_an_embedding_error() -> None:
    p = provider(transport=transport_returning({"error": "bad request"}, status_code=400))

    with pytest.raises(EmbeddingError) as caught:
        p.embed(["q"])

    print(f"raised: {caught.value}")
    assert "400" in str(caught.value)


def test_an_unreachable_server_becomes_an_embedding_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    p = provider(transport=httpx.MockTransport(refuse))

    with pytest.raises(EmbeddingError) as caught:
        p.embed(["q"])

    print(f"raised: {caught.value}")
    assert "Could not reach" in str(caught.value)


def test_a_reply_without_the_expected_shape_becomes_an_embedding_error() -> None:
    p = provider(transport=transport_returning({"unexpected": "shape"}))

    with pytest.raises(EmbeddingError):
        p.embed(["q"])


def test_a_wrong_vector_count_becomes_an_embedding_error() -> None:
    """Asked for 2, got 1 back — must not silently misalign the rest."""
    p = provider(transport=transport_returning(embedding_payload([[1.0, 0.0, 0.0, 0.0]])))

    with pytest.raises(EmbeddingError, match="Expected 2"):
        p.embed(["first", "second"])


def test_a_wrong_vector_width_becomes_an_embedding_error() -> None:
    p = provider(dimensions=1024, transport=transport_returning(embedding_payload([[0.0, 0.0]])))

    with pytest.raises(EmbeddingError, match="1024"):
        p.embed(["q"])


# --- configuration ---------------------------------------------------------


def test_url_key_and_model_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPANY_API_URL", "https://from-env:8443")
    monkeypatch.setenv("COMPANY_API_KEY", "sk-from-env")
    monkeypatch.setenv("COMPANY_EMBEDDING_MODEL", "from-env-model")

    p = CompanyEmbeddingProvider()

    print(f"url={p.api_url} model={p.model}")
    assert p.api_url == "https://from-env:8443"
    assert p.api_key == "sk-from-env"
    assert p.model == "from-env-model"


def test_missing_url_or_key_raises_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPANY_API_URL", raising=False)
    monkeypatch.delenv("COMPANY_API_KEY", raising=False)

    with pytest.raises(KeyError):
        CompanyEmbeddingProvider()
