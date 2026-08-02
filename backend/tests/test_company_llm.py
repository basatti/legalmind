"""Tests for the company-hosted LLM provider (LEG-63).

No server is contacted. A mock transport stands in for the network, so these
tests check the two things that are actually this class's job: that it builds
the right request, and that every way the call can fail becomes an LLMError
rather than something unexpected escaping into the service above it.
"""

import json

import httpx
import pytest

from services.company_llm import CompanyLLMProvider
from services.llm import LLMError


def transport_returning(payload: object, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, json=payload)

    return httpx.MockTransport(handler)


def provider(**kwargs) -> CompanyLLMProvider:
    kwargs.setdefault("api_url", "https://example.invalid")
    kwargs.setdefault("api_key", "sk-test")
    return CompanyLLMProvider(**kwargs)


# --- the happy path --------------------------------------------------------


def test_the_reply_text_is_returned() -> None:
    payload = {"choices": [{"message": {"content": "42 days [1]."}}]}
    p = provider(transport=transport_returning(payload))

    reply = p.generate("how long?")

    print(f"reply={reply!r}")
    assert reply == "42 days [1]."


def test_the_request_carries_the_prompt_model_auth_and_zero_temperature() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    p = provider(
        model="test-model",
        api_url="http://example:8443",
        api_key="sk-secret",
        transport=httpx.MockTransport(handler),
    )
    p.generate("the prompt")

    print(seen)
    assert seen["model"] == "test-model"
    assert seen["messages"] == [{"role": "user", "content": "the prompt"}]
    assert seen["temperature"] == 0
    assert seen["url"] == "http://example:8443/v1/chat/completions"
    assert seen["auth"] == "Bearer sk-secret"


def test_a_trailing_slash_on_the_api_url_does_not_double_up() -> None:
    p = provider(api_url="http://example:8443/")
    assert p.api_url == "http://example:8443"


# --- every way it can fail -------------------------------------------------


def test_an_error_status_becomes_an_llm_error() -> None:
    p = provider(transport=transport_returning({"error": "model not found"}, status_code=404))

    with pytest.raises(LLMError) as caught:
        p.generate("q")

    print(f"raised: {caught.value}")
    assert "404" in str(caught.value)


def test_an_unreachable_server_becomes_an_llm_error() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    p = provider(transport=httpx.MockTransport(refuse))

    with pytest.raises(LLMError) as caught:
        p.generate("q")

    print(f"raised: {caught.value}")
    assert "Could not reach" in str(caught.value)


def test_a_reply_without_the_expected_shape_becomes_an_llm_error() -> None:
    """A 200 that contains no answer must not surface as a KeyError upstairs."""
    p = provider(transport=transport_returning({"unexpected": "shape"}))

    with pytest.raises(LLMError):
        p.generate("q")


def test_an_empty_choices_list_becomes_an_llm_error() -> None:
    p = provider(transport=transport_returning({"choices": []}))

    with pytest.raises(LLMError):
        p.generate("q")


# --- configuration ---------------------------------------------------------


def test_url_key_and_model_come_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPANY_API_URL", "https://from-env:8443")
    monkeypatch.setenv("COMPANY_API_KEY", "sk-from-env")
    monkeypatch.setenv("COMPANY_LLM_MODEL", "from-env-model")

    p = CompanyLLMProvider()

    print(f"url={p.api_url} model={p.model}")
    assert p.api_url == "https://from-env:8443"
    assert p.api_key == "sk-from-env"
    assert p.model == "from-env-model"


def test_explicit_arguments_win_over_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("COMPANY_API_URL", "https://from-env:8443")
    monkeypatch.setenv("COMPANY_API_KEY", "sk-from-env")

    p = provider(api_url="https://explicit:8443", api_key="sk-explicit")

    assert p.api_url == "https://explicit:8443"
    assert p.api_key == "sk-explicit"


def test_missing_url_or_key_raises_clearly(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("COMPANY_API_URL", raising=False)
    monkeypatch.delenv("COMPANY_API_KEY", raising=False)

    with pytest.raises(KeyError):
        CompanyLLMProvider()
